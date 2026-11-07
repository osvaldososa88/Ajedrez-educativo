import chess
from django.db import migrations


CHAPTER_TITLE = 'Si no capturan el peón: 4.d3, 4.Nc3 y 4.d4'
SOURCE_URL = 'https://www.youtube.com/watch?v=xvweTRkDitI'
INTRO = (
    'Si las blancas no aceptan el peón de f5, la transcripción destaca '
    '4.d3 y el contraataque central 4.d4; también puedes practicar el '
    'desarrollo 4.Nc3 como alternativa. El instructor propone ...Bc5 '
    'contra 4.d3. Las demás ramas son continuaciones legales de práctica '
    'y no se presentan como líneas atribuidas al video.'
)
LINES = (
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'd3', 'Bc5'),
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'Nc3', 'd5'),
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'd4', 'fxe4', 'Nxe5', 'd5'),
)
REQUIRED_MOVES = {
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4'): 'f5',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'd3'): 'Bc5',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'Nc3'): 'd5',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'd4'): 'fxe4',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'd4', 'fxe4', 'Nxe5'): 'd5',
}
COMMENTS = {
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5'): (
        'El Gambito Rousseau ofrece el peón de f y provoca una decisión en el centro.'
    ),
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'd3'): (
        'Una forma prudente de sostener el centro sin capturar el peón.'
    ),
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'd3', 'Bc5'): (
        'El instructor recomienda desarrollar el alfil y mantener la presión sobre f2.'
    ),
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'Nc3'): (
        'Desarrollo una pieza sin aceptar el peón; esta rama sirve para practicar otra respuesta.'
    ),
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'Nc3', 'd5'): (
        'El avance central ataca el alfil de c4. Esta continuación legal se incluye como práctica.'
    ),
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'd4'): (
        'El video destaca el contraataque central como la respuesta más crítica.'
    ),
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'd4', 'fxe4'): (
        'El peón captura en e4 y ataca el caballo de f3.'
    ),
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'd4', 'fxe4', 'Nxe5'): (
        'El caballo captura el peón central.'
    ),
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'f5', 'd4', 'fxe4', 'Nxe5', 'd5'): (
        'El avance ataca el alfil de c4 y disputa el centro.'
    ),
}
HINTS = [
    'El gambito está en el peón de f5. Si no lo capturan, elige una respuesta para el centro.',
]


def _build_tree():
    board = chess.Board()
    tree = []
    for line in LINES:
        candidates = tree
        path = []
        board.reset()
        for san in line:
            move = board.parse_san(san)
            node = next(
                (item for item in candidates if item['uci'] == move.uci()),
                None,
            )
            if node is None:
                next_board = board.copy()
                next_board.push(move)
                node = {
                    'san': san,
                    'uci': move.uci(),
                    'fen': next_board.fen(),
                    'comment': COMMENTS.get(tuple(path + [san]), ''),
                    'main': not candidates,
                    'accepted': True,
                    'required': REQUIRED_MOVES.get(tuple(path)) == san,
                    'hints': HINTS if tuple(path) == (
                        'e4', 'e5', 'Nf3', 'Nc6', 'Bc4',
                    ) else [],
                    'variations': [],
                }
                candidates.append(node)
            board.push(move)
            path.append(san)
            candidates = node['variations']
    return tree


def add_rousseau_chapter(apps, schema_editor):
    Lesson = apps.get_model('lessons', 'Lesson')
    LessonChapter = apps.get_model('lessons', 'LessonChapter')
    lesson = Lesson.objects.filter(slug='gambito-rousseau').first()
    if not lesson or LessonChapter.objects.filter(lesson=lesson, order=5).exists():
        return

    LessonChapter.objects.create(
        lesson=lesson,
        title=CHAPTER_TITLE,
        intro=INTRO,
        start_fen=chess.STARTING_FEN,
        tree=_build_tree(),
        source_url=SOURCE_URL,
        order=5,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('lessons', '0006_make_black_opening_intros_playable'),
    ]

    operations = [
        migrations.RunPython(add_rousseau_chapter, migrations.RunPython.noop),
    ]
