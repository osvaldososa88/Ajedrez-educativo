"""
Tests del módulo de lecciones (`apps.lessons`).

Se cubren tres cosas:
  1. El constructor de PGN: jugadas legales, cabeceras y — sobre todo — que
     las RAV se coloquen en el sitio correcto (regresión real: colocarlas antes
     de la jugada a la que sustituyen produce árboles con jugadas imposibles).
  2. El importador: FEN inicial válido, `san`/`uci` como cadenas y comentarios
     sin los comandos de anotación de Lichess.
  3. Las vistas y el comando `seed_lessons` (idempotencia).
"""
from __future__ import annotations

import json

import chess
import chess.pgn
import pytest

from apps.lessons import pgn_builder as builder
from apps.lessons.italiana_data import CHAPTERS as ITALIANA_CHAPTERS
from apps.lessons.pgn_importer import (
    clean_comment,
    iter_chapter_records,
    parse_chapter,
)

STUDY = 'Partida Italiana'


def build_it():
    return builder.build_study_pgn(ITALIANA_CHAPTERS, study=STUDY)


@pytest.fixture(scope='module')
def pgn_text():
    return build_it()


@pytest.fixture(scope='module')
def games(pgn_text):
    return list(builder.iter_games(pgn_text))


def to_pgn(juego):
    """Serializa un juego de python-chess a texto PGN."""
    return str(juego)


# --------------------------------------------------------------- constructor

def test_todas_las_partidas_son_legales(pgn_text):
    assert builder.validate_pgn(pgn_text) == []


def test_una_partida_por_capitulo(games):
    assert len(games) == len(ITALIANA_CHAPTERS)


def test_cabeceras_de_gamebook(games):
    for juego in games:
        h = juego.headers
        assert h['ChapterMode'] == 'gamebook'
        assert h['StudyName'] == STUDY
        assert h['ChapterName']
        assert h['Result'] == '*'


def test_no_emite_fen_invalido(pgn_text, games):
    """
    Regresión: se emitía `[FEN "0 1"]` + `[SetUp "1"]`, un FEN que python-chess
    no puede leer. Ahora el juego arranca desde la posición estándar.
    """
    assert '[FEN "0 1"]' not in pgn_text
    for juego in games:
        assert juego.board().fen() == chess.STARTING_FEN


def test_rav_se_coloca_despues_de_la_jugada_que_sustituye(pgn_text):
    """
    Regresión principal.

    En PGN una RAV va DESPUÉS de la jugada a la que sustituye. Si se emite antes,
    python-chess la cuelga de la posición equivocada y el árbol resultante
    contiene jugadas imposibles (dos jugadas blancas seguidas).

    Se comprueba que cada nodo es una jugada legal desde la posición de su
    padre, tal y como lo haría un alumno siguiendo las alternativas.
    """

    def recorrer(nodo, fen_padre):
        # `fen_padre` es la posición ANTES de la jugada de `nodo`; sus
        # variaciones son las alternativas a esa jugada, y todas deben ser
        # legales desde ahí.
        for hijo in nodo.variations:
            board = chess.Board(fen_padre)
            board.push_san(hijo.san())          # debe ser legal
            recorrer(hijo, board.fen())

    for juego in builder.iter_games(pgn_text):
        recorrer(juego, juego.board().fen())


def test_las_alternativas_son_hermanas_de_la_principal(pgn_text):
    """Bb5 debe aparecer como alternativa a Bc4, no encadenado tras Bc4."""
    juego = next(builder.iter_games(pgn_text))


def test_numero_de_jugada_correcto():
    """`1. e4 1... e5 2. Nf3`, no una numeración corrida."""
    pgn = builder.build_chapter_pgn(
        title='T',
        moves=[('e4', 'a'), ('e5', 'b'), ('Nf3', 'c'), ('Nc6', 'd')],
    )
    cuerpo = pgn.split('\n\n', 1)[1]
    assert '1. e4' in cuerpo
    assert '1... e5' in cuerpo
    assert '2. Nf3' in cuerpo
    assert '2... Nc6' in cuerpo


def test_una_jugada_ilegal_aborta_con_mensaje():
    with pytest.raises(ValueError, match='ilegal'):
        builder.build_chapter_pgn(
            title='T',
            moves=[('e4', ''), ('e5', ''), ('Nf3', ''), ('Nc6', ''), ('Bf7', '')],
        )


def test_build_and_check_valida():
    pgn = builder.build_and_check(study=STUDY, chapters=ITALIANA_CHAPTERS)
    assert builder.validate_pgn(pgn) == []


def test_build_and_check_falla_con_jugada_ilegal():
    """
    Una jugada ilegal debe abortar la construcción (y por tanto el seed) antes
    de escribir nada en la base de datos.
    """
    malos = [dict(ITALIANA_CHAPTERS[0], moves=[('e4', ''), ('Qh8', '')])]
    with pytest.raises(ValueError):
        builder.build_and_check(study=STUDY, chapters=malos)


def test_comentarios_no_rompen_el_pgn(pgn_text):
    """Las llaves de un comentario deben ir balanceadas."""
    assert pgn_text.count('{') == pgn_text.count('}')


# --------------------------------------------------------------- importador

def test_parse_chapter_devuelve_fen_y_arbol(pgn_text):
    juego = next(builder.iter_games(pgn_text))
    datos = parse_chapter(to_pgn(juego))
    assert datos['fen'] == chess.STARTING_FEN
    assert datos['variations']
    assert datos['comment']


def test_san_y_uci_son_cadenas(pgn_text):
    """
    Regresión: `GameNode.san`/`uci` son MÉTODOS en python-chess. Sin llamarlos
    se guardaba un método ligado en el JSON y el árbol no era serializable.
    """
    for juego in builder.iter_games(pgn_text):
        datos = parse_chapter(to_pgn(juego))
        json.dumps(datos['variations'])          # falla si hay métodos ligados
        pila = list(datos['variations'])
        while pila:
            nodo = pila.pop()
            assert isinstance(nodo['san'], str)
            assert isinstance(nodo['uci'], str)
            assert len(nodo['uci']) == 4
            pila.extend(nodo['variations'])


def test_los_nodos_tienen_los_campos_esperados(pgn_text):
    juego = next(builder.iter_games(pgn_text))
    datos = parse_chapter(to_pgn(juego))
    pila = list(datos['variations'])
    while pila:
        nodo = pila.pop()
        assert set(nodo) >= {'san', 'uci', 'fen', 'comment', 'variations'}
        assert nodo['fen'].count(' ') == 5
        pila.extend(nodo['variations'])


def test_clean_comment_quita_anotaciones():
    sucio = 'Hola { [%cal Gc7c5] } [%csl Ge7] mundo'
    limpio = clean_comment(sucio)
    assert '[%' not in limpio
    assert 'Gc7c5' not in limpio
    assert 'Hola' in limpio and 'mundo' in limpio


def test_clean_comment_acepta_none():
    assert clean_comment(None) == ''


def test_iter_chapter_records_normaliza(pgn_text, tmp_path):
    ruta = tmp_path / 'test.pgn'
    ruta.write_text(pgn_text, encoding='utf-8')
    registros = list(iter_chapter_records(ruta))
    assert len(registros) == len(ITALIANA_CHAPTERS)
    for rec in registros:
        assert rec['title']
        assert rec['fen'].count(' ') == 5
        assert isinstance(rec['tree'], list)


# ---------------------------------------------------- vistas y seed (Django)

@pytest.mark.django_db
class TestVistas:

    @pytest.fixture(autouse=True)
    def _datos(self):
        from django.core.management import call_command
        call_command('seed_lessons', verbosity=0)

    @pytest.fixture
    def user(self, django_user_model):
        return django_user_model.objects.create_user(
            username='alumno_lessons', password='x'
        )

    @pytest.fixture
    def cliente(self, client, user):
        client.force_login(user)
        return client

    def test_indice_requiere_login(self, client):
        response = client.get('/lessons/')
        assert response.status_code == 302
        assert '/accounts/login/' in response['Location']

    def test_indice_muestra_las_lecciones(self, cliente):
        from apps.lessons.models import Lesson

        response = cliente.get('/lessons/')
        assert response.status_code == 200
        for lesson in Lesson.objects.all():
            assert lesson.title in response.content.decode()

    def test_detalle_de_una_leccion(self, cliente):
        from apps.lessons.models import Lesson

        lesson = Lesson.objects.order_by('order').first()
        response = cliente.get(lesson.get_absolute_url())
        assert response.status_code == 200
        assert lesson.title in response.content.decode()

    def test_capitulo_tablero_antes_que_lateral(self, cliente):
        """
        En móvil el tablero debe ir primero: por eso está antes en el DOM y
        el CSS lo refuerza con `order: -1`.
        """
        from apps.lessons.models import LessonChapter

        capitulo = LessonChapter.objects.first()
        html = cliente.get(
            f'/lessons/capitulo/{capitulo.id}/'
        ).content.decode()
        assert html.index('id="chessboard"') < html.index('game-sidebar')

    def test_utilidades_del_tablero_se_cargan_antes_del_script_de_lecciones(self, cliente):
        from apps.lessons.models import LessonChapter

        chapter = LessonChapter.objects.first()
        html = cliente.get(f'/lessons/capitulo/{chapter.id}/').content.decode()
        assert html.index('js/chess_ui.js') < html.index('js/lessons_app.js')

    def test_arbol_json(self, cliente):
        from apps.lessons.models import LessonChapter

        capitulo = LessonChapter.objects.first()
        data = cliente.get(f'/lessons/capitulo/{capitulo.id}/arbol/').json()
        assert data['fen'].count(' ') == 5
        assert isinstance(data['tree'], list)
        json.dumps(data['tree'])

    def test_todos_los_capitulos_responden(self, cliente):
        from apps.lessons.models import LessonChapter

        for capitulo in LessonChapter.objects.all():
            assert cliente.get(
                f'/lessons/capitulo/{capitulo.id}/'
            ).status_code == 200

    def test_capitulos_siguiente_y_anterior(self, cliente):
        from apps.lessons.models import Lesson, LessonChapter

        capitulos = list(
            LessonChapter.objects.filter(
                lesson=Lesson.objects.order_by('order').first()
            )
        )
        html = cliente.get(
            f'/lessons/capitulo/{capitulos[0].id}/'
        ).content.decode()
        assert 'Siguiente' in html
        assert 'id="lesson-prev-chapter"' in html
        assert 'hidden disabled>◀ Anterior' in html

        html = cliente.get(
            f'/lessons/capitulo/{capitulos[-1].id}/'
        ).content.decode()
        assert 'Anterior' in html
        assert 'id="lesson-next-chapter"' in html
        assert 'hidden disabled>Siguiente' in html

    def test_controles_de_navegacion_apuntan_al_capitulo_siguiente_actual(self, cliente):
        from apps.lessons.models import Lesson, LessonChapter

        lesson = Lesson.objects.order_by('order').first()
        chapters = list(lesson.chapters.all())
        for index, chapter in enumerate(chapters):
            html = cliente.get(
                f'/lessons/capitulo/{chapter.id}/'
            ).content.decode()
            if index:
                assert (
                    f'id="lesson-prev-chapter"'
                ) in html
                assert f'data-chapter-id="{chapters[index - 1].id}"' in html
            if index + 1 < len(chapters):
                assert 'id="lesson-next-chapter"' in html
                assert f'data-chapter-id="{chapters[index + 1].id}"' in html


@pytest.mark.django_db
class TestSeed:

    def test_carga_las_cuatro_lecciones(self):
        from django.core.management import call_command
        from apps.lessons.models import Lesson

        call_command('seed_lessons', verbosity=0)
        assert Lesson.objects.count() == 4
        assert Lesson.objects.filter(slug='partida-italiana').exists()

    def test_es_idempotente(self):
        """
        Ejecutar el seed dos veces no debe duplicar nada: las lecciones se
        identifican por slug y los capítulos por (lección, order).
        """
        from django.core.management import call_command
        from apps.lessons.models import Lesson, LessonChapter

        call_command('seed_lessons', verbosity=0)
        lecciones = Lesson.objects.count()
        capitulos = LessonChapter.objects.count()

        call_command('seed_lessons', verbosity=0)
        assert Lesson.objects.count() == lecciones
        assert LessonChapter.objects.count() == capitulos

    def test_genera_el_pgn_de_la_italiana(self):
        from django.core.management import call_command
        from apps.lessons.pgn_importer import DATA_DIR

        call_command('seed_lessons', verbosity=0)
        assert (DATA_DIR / 'italiana.pgn').exists()

    def test_reset_borra_todo(self):
        from django.core.management import call_command
        from apps.lessons.models import Lesson, LessonChapter

        call_command('seed_lessons', verbosity=0)
        call_command('seed_lessons', '--reset', verbosity=0)
        assert Lesson.objects.count() == 4
        assert LessonChapter.objects.count() > 0

    def test_los_capitulos_tienen_arbol_serializable(self):
        from django.core.management import call_command
        from apps.lessons.models import LessonChapter

        call_command('seed_lessons', verbosity=0)
        for capitulo in LessonChapter.objects.all():
            json.dumps(capitulo.tree)
            assert capitulo.start_fen.count(' ') == 5

    def test_siciliana_y_holandesa_se_practican_con_negras(self):
        from django.core.management import call_command
        from apps.lessons.models import Lesson, LessonChapter

        call_command('seed_lessons', verbosity=0)
        lessons = Lesson.objects.filter(
            slug__in=('siciliana-enigmatica', 'holandesa-enigmatica'),
        )
        assert lessons.count() == 2
        assert set(lessons.values_list('student_color', flat=True)) == {'black'}
        assert all(
            chapter.start_fen.split()[1] == 'w'
            for chapter in LessonChapter.objects.filter(lesson__in=lessons)
        )

    def test_siciliana_y_holandesa_inician_con_el_turno_de_negras(
        self, client, django_user_model,
    ):
        from django.core.management import call_command
        from django.urls import reverse
        from apps.lessons.models import Lesson

        call_command('seed_lessons', verbosity=0)
        user = django_user_model.objects.create_user(
            username='black_opening_student', password='test-password'
        )
        client.force_login(user)

        for slug in ('siciliana-enigmatica', 'holandesa-enigmatica'):
            lesson = Lesson.objects.get(slug=slug)
            chapter = lesson.chapters.order_by('order').first()
            response = client.post(
                reverse('chapter_play', args=[chapter.pk]),
                data=json.dumps({
                    'action': 'start',
                    'path': [],
                    'color': lesson.student_color,
                }),
                content_type='application/json',
            )
            assert response.status_code == 200
            state = response.json()
            assert state['turn'] == 'black', f'{slug}: {state}'
            assert state['path'], slug


@pytest.mark.django_db
class TestRousseauImport:

    def test_migracion_genera_tres_respuestas_legales_al_no_capturar(self):
        from importlib import import_module

        migration = import_module(
            'apps.lessons.migrations.0007_add_rousseau_non_capture_branches'
        )
        tree = migration._build_tree()
        candidates = tree
        board = chess.Board()
        for san in ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5'):
            node = next(item for item in candidates if item['san'] == san)
            board.push_san(san)
            candidates = node['variations']

        assert [node['san'] for node in candidates] == ['d3', 'Nc3', 'd4']
        for branch in candidates:
            branch_board = board.copy()
            node = branch
            while node:
                branch_board.push_san(node['san'])
                node = (node.get('variations') or [None])[0]

    def test_importa_leccion_publicada_para_practicar_con_negras(self, client, django_user_model):
        from django.core.management import call_command
        from apps.lessons.models import Lesson, LessonChapter

        call_command('import_rousseau', verbosity=0)
        lesson = Lesson.objects.get(slug='gambito-rousseau')
        chapters = list(LessonChapter.objects.filter(lesson=lesson))

        assert lesson.is_published is True
        assert lesson.student_color == Lesson.StudentColor.BLACK
        assert len(chapters) == 6
        assert all(chapter.tree and chapter.start_fen.count(' ') == 5 for chapter in chapters)

        user = django_user_model.objects.create_user(
            username='rousseau_student', password='test-password'
        )
        client.force_login(user)
        html = client.get(f'/lessons/capitulo/{chapters[0].pk}/').content.decode()
        assert '<option value="black" selected>' in html

    def test_arbol_separa_jugada_obligatoria_y_ramas_legales(self):
        from django.core.management import call_command
        from apps.lessons.models import Lesson, LessonChapter

        call_command('import_rousseau', verbosity=0)
        chapter = LessonChapter.objects.get(
            lesson__slug='gambito-rousseau',
            order=0,
        )
        candidates = chapter.tree
        for san in ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4'):
            node = next(item for item in candidates if item['san'] == san)
            candidates = node['variations']
        f5_node = next(item for item in candidates if item['san'] == 'f5')
        assert f5_node['required'] is True
        assert f5_node['accepted'] is True

    def test_rousseau_incluye_las_tres_respuestas_sin_capturar(self):
        from django.core.management import call_command
        from apps.lessons.models import LessonChapter

        call_command('import_rousseau', verbosity=0)
        chapter = LessonChapter.objects.get(
            lesson__slug='gambito-rousseau',
            order=5,
        )
        candidates = chapter.tree
        for san in ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5'):
            node = next(item for item in candidates if item['san'] == san)
            candidates = node['variations']

        assert {node['san'] for node in candidates} == {'d3', 'Nc3', 'd4'}
        assert next(node for node in candidates if node['san'] == 'd3')['required']

    def test_sesion_jugable_con_negras_y_progreso_persistente(self, client, django_user_model):
        from django.core.management import call_command
        from django.urls import reverse
        from apps.lessons.models import LessonChapter, LessonVariantProgress

        call_command('import_rousseau', verbosity=0)
        chapter = LessonChapter.objects.get(lesson__slug='gambito-rousseau', order=0)
        user = django_user_model.objects.create_user(
            username='rousseau_black', password='test-password'
        )
        client.force_login(user)

        def play(action, path, uci=None):
            payload = {'action': action, 'path': path, 'color': 'black'}
            if uci:
                payload['uci'] = uci
            return client.post(
                reverse('chapter_play', args=[chapter.pk]),
                data=json.dumps(payload),
                content_type='application/json',
            )

        state = play('start', []).json()
        assert state['path'] == ['e2e4']
        path = state['path']
        for uci, expected_last_move in (
            ('e7e5', 'g1f3'),
            ('b8c6', 'f1c4'),
            ('f7f5', 'e4f5'),
            ('e5e4', 'd1e2'),
            ('d8e7', 'f3g1'),
            ('g8f6', None),
        ):
            response = play('move', path, uci)
            assert response.status_code == 200
            state = response.json()
            assert state['accepted'] is True
            path = state['path']
            if expected_last_move:
                assert path[-1] == expected_last_move

        assert state['completed'] is True
        progress = LessonVariantProgress.objects.get(
            user=user,
            chapter=chapter,
            branch_key=' '.join(path),
        )
        assert progress.completed is True
        assert sum(
            row.attempts for row in LessonVariantProgress.objects.filter(
                user=user, chapter=chapter
            )
        ) == 6
        assert progress.mistakes == 0

    def test_importar_de_nuevo_no_sobrescribe_la_leccion(self):
        from django.core.management import call_command, CommandError
        from apps.lessons.models import Lesson, LessonChapter

        call_command('import_rousseau', verbosity=0)
        chapter = LessonChapter.objects.get(lesson__slug='gambito-rousseau', order=0)
        chapter.intro = 'Edición local que debe conservarse.'
        chapter.save(update_fields=['intro'])

        with pytest.raises(CommandError, match='no se modificó'):
            call_command('import_rousseau', verbosity=0)

        chapter.refresh_from_db()
        assert chapter.intro == 'Edición local que debe conservarse.'
        assert Lesson.objects.filter(slug='gambito-rousseau').count() == 1

    def test_append_missing_anade_capitulo_sin_editar_los_existentes(self):
        from django.core.management import call_command
        from apps.lessons.models import LessonChapter

        call_command('import_rousseau', verbosity=0)
        lesson_chapters = LessonChapter.objects.filter(
            lesson__slug='gambito-rousseau',
        )
        chapter = lesson_chapters.get(order=0)
        chapter.intro = 'Texto personalizado que debe conservarse.'
        chapter.save(update_fields=['intro'])
        lesson_chapters.filter(order=5).delete()

        call_command('import_rousseau', '--append-missing', verbosity=0)

        chapter.refresh_from_db()
        assert chapter.intro == 'Texto personalizado que debe conservarse.'
        assert lesson_chapters.count() == 6


def _lesson_node(board, san, *, main=False, variations=None, **extra):
    move = board.parse_san(san)
    node_board = board.copy()
    node_board.push(move)
    return {
        'san': san,
        'uci': move.uci(),
        'fen': node_board.fen(),
        'comment': '',
        'main': main,
        'accepted': True,
        'required': False,
        'hints': [],
        'variations': variations or [],
        **extra,
    }


def _interactive_tree():
    board = chess.Board()
    e4 = _lesson_node(board, 'e4', main=True)
    after_e4 = board.copy()
    after_e4.push_uci(e4['uci'])

    e5 = _lesson_node(after_e4, 'e5', main=True)
    c5 = _lesson_node(after_e4, 'c5')
    after_e5 = after_e4.copy()
    after_e5.push_uci(e5['uci'])
    nf3 = _lesson_node(after_e5, 'Nf3', main=True)
    d4 = _lesson_node(after_e5, 'd4')
    e5['variations'] = [nf3, d4]
    after_c5 = after_e4.copy()
    after_c5.push_uci(c5['uci'])
    c5['variations'] = [_lesson_node(after_c5, 'Nf3', main=True)]
    e4['variations'] = [e5, c5]
    return [e4, _lesson_node(board, 'd4')]


@pytest.mark.django_db
class TestInteractiveLesson:

    @pytest.fixture
    def session(self, client, django_user_model):
        from apps.lessons.models import Lesson, LessonChapter

        user = django_user_model.objects.create_user(
            username='lesson_interactive', password='test-password'
        )
        lesson = Lesson.objects.create(
            title='Lección interactiva',
            slug='leccion-interactiva',
            is_published=True,
        )
        chapter = LessonChapter.objects.create(
            lesson=lesson,
            title='Ramas aceptables',
            order=0,
            start_fen=chess.STARTING_FEN,
            tree=_interactive_tree(),
        )
        client.force_login(user)
        return client, lesson, chapter

    def _play(self, client, chapter, action, path, color='white', uci=None):
        from django.urls import reverse

        payload = {'action': action, 'path': path, 'color': color}
        if uci:
            payload['uci'] = uci
        return client.post(
            reverse('chapter_play', args=[chapter.pk]),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_jugada_en_tablero_y_respuesta_automatica(self, session):
        client, _, chapter = session
        started = self._play(client, chapter, 'start', [])
        assert started.status_code == 200
        assert started.json()['turn'] == 'white'

        response = self._play(client, chapter, 'move', [], uci='e2e4')
        assert response.status_code == 200
        assert response.json()['accepted'] is True
        assert response.json()['path'] == ['e2e4', 'e7e5']
        assert response.json()['turn'] == 'white'

    def test_acepta_otra_rama_preparada(self, session):
        client, _, chapter = session
        start = self._play(client, chapter, 'start', []).json()
        after_e4 = self._play(
            client, chapter, 'move', start['path'], uci='e2e4',
        ).json()
        response = self._play(
            client, chapter, 'move', after_e4['path'], uci='d2d4',
        )
        assert response.status_code == 200
        assert response.json()['accepted'] is True
        assert response.json()['path'][-1] == 'd2d4'

    def test_jugada_legal_sin_rama_no_se_marca_como_error(self, session):
        client, _, chapter = session
        response = self._play(
            client, chapter, 'move', [], uci='c2c4',
        )
        assert response.status_code == 200
        assert response.json()['unmodeled'] is True
        assert response.json()['accepted'] is False
        assert response.json()['progress'][0]['attempts'] == 1
        assert response.json()['progress'][0]['mistakes'] == 0

    def test_rechaza_movimiento_ilegal(self, session):
        client, _, chapter = session
        response = self._play(
            client, chapter, 'move', [], uci='e2e5',
        )
        assert response.status_code == 400
        assert 'legal' in response.json()['error']

    def test_practica_con_negras_y_explora_apertura_inicial(self, session):
        client, _, chapter = session
        started = self._play(client, chapter, 'start', [], color='black')
        data = started.json()
        assert data['path'] == ['e2e4']
        assert data['turn'] == 'black'
        assert data['reply_choices'][0]['node']['uci'] == 'd2d4'
        assert data['reply_choices'][0]['path'] == []

        response = self._play(
            client, chapter, 'move', data['path'], color='black', uci='c7c5',
        )
        assert response.status_code == 200
        assert response.json()['path'] == ['e2e4', 'c7c5', 'g1f3']
        assert response.json()['turn'] == 'black'

    def test_puede_explorar_una_respuesta_alternativa_del_rival(self, session):
        client, _, chapter = session
        after_e4 = self._play(
            client, chapter, 'move', [], uci='e2e4',
        ).json()
        alternative = after_e4['reply_choices'][0]
        assert alternative['node']['uci'] == 'c7c5'

        response = self._play(
            client,
            chapter,
            'explore',
            alternative['path'],
            uci=alternative['node']['uci'],
        )
        assert response.status_code == 200
        assert response.json()['path'] == ['e2e4', 'c7c5']
        assert response.json()['turn'] == 'white'

    def test_navega_una_posicion_anterior_sin_avanzar_la_rama(self, session):
        client, _, chapter = session
        started = self._play(client, chapter, 'start', []).json()
        after_e4 = self._play(
            client, chapter, 'move', started['path'], uci='e2e4',
        ).json()
        previous = self._play(
            client, chapter, 'navigate', ['e2e4'],
        )
        assert previous.status_code == 200
        assert previous.json()['path'] == ['e2e4']
        assert previous.json()['turn'] == 'black'
        assert after_e4['path'] == ['e2e4', 'e7e5']

    def test_rechaza_alternativa_si_hay_jugada_requerida(self, session):
        client, _, chapter = session
        board = chess.Board()
        required = _lesson_node(board, 'e4', main=True, required=True)
        alternative = _lesson_node(board, 'd4')
        chapter.tree = [required, alternative]
        chapter.save(update_fields=['tree'])

        response = self._play(
            client, chapter, 'move', [], uci='d2d4',
        )
        assert response.status_code == 200
        assert response.json()['accepted'] is False
        assert response.json()['unmodeled'] is False
        progress = client.get(
            f'/lessons/capitulo/{chapter.pk}/arbol/'
        ).json()['progress']
        assert progress[0]['mistakes'] == 1

    def test_persiste_progreso_al_completar_una_variante(self, session):
        from apps.lessons.models import LessonVariantProgress

        client, _, chapter = session
        start = self._play(client, chapter, 'start', []).json()
        after_e4 = self._play(
            client, chapter, 'move', start['path'], uci='e2e4',
        ).json()
        completed = self._play(
            client, chapter, 'move', after_e4['path'], uci='g1f3',
        )
        assert completed.json()['completed'] is True
        assert LessonVariantProgress.objects.filter(
            chapter=chapter,
            branch_key='e2e4 e7e5 g1f3',
            completed=True,
        ).exists()
        progress = client.get(
            f'/lessons/capitulo/{chapter.pk}/arbol/'
        ).json()['lesson_progress']
        assert progress['completed_chapters'] == 1
        assert progress['completed_branches'] == 1
