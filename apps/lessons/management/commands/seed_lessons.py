"""
Carga (o recarga) las lecciones de apertura.

Cada familia de apertura tiene su propio PGN en `apps/lessons/data/`. La
Partida Italiana no viene de Lichess: se genera con `pgn_builder` a partir de
`apps.lessons.italiana_data`, que valida cada jugada con python-chess antes de
escribirla.

El comando es IDEMPOTENTE: se puede ejecutar tantas veces como se quiera sin
duplicar lecciones ni capítulos. Cada lección se identifica por su `slug` y cada
capítulo por `(lección, order)`, así que repetirlo solo actualiza los datos.

Uso:
    python manage.py seed_lessons            # carga/actualiza todo
    python manage.py seed_lessons --reset    # borra antes de recargar
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.lessons import pgn_builder
from apps.lessons.italiana_data import CHAPTERS as ITALIANA_CHAPTERS
from apps.lessons.models import Lesson, LessonChapter
from apps.lessons.pgn_importer import DATA_DIR, iter_chapter_records

# Definición de cada lección de Lichess: qué PGN la alimenta y cómo se presenta.
LICKS = [
    {
        'file': 'siciliana.pgn',
        'slug': 'siciliana-enigmatica',
        'title': 'Siciliana Enigmática',
        'family': 'Siciliana',
        'eco': 'B32',
        'icon': '🗡️',
        'color': Lesson.Color.DARK,
        'student_color': Lesson.StudentColor.BLACK,
        'order': 10,
        'summary': (
            'Una defensa siciliana poco convencional, llena de jugadas sorpresa '
            'y truquitos tácticos. Ideal para incomoda al rival desde el '
            'primer momento.'
        ),
    },
    {
        'file': 'holandesa.pgn',
        'slug': 'holandesa-enigmatica',
        'title': 'Holandesa Enigmática',
        'family': 'Holandesa',
        'eco': 'A84',
        'icon': '🏰',
        'color': Lesson.Color.DARK,
        'student_color': Lesson.StudentColor.BLACK,
        'order': 20,
        'summary': (
            'La Defensa Holandesa con 1.d4 f5: estructuras incómodas de piezas '
            'negras que atacan el centro antes de tiempo.'
        ),
    },
    {
        'file': 'colle.pgn',
        'slug': 'sistema-colle',
        'title': 'Sistema Colle Enigmático',
        'family': 'Colle',
        'eco': 'D02',
        'icon': '🧱',
        'color': Lesson.Color.LIGHT,
        'order': 30,
        'summary': (
            'Un esquema con peones en d4 y e4 que presiona en el centro. '
            'Perfecto para aprender a construir una estructura sólida.'
        ),
    },
]



class Command(BaseCommand):
    help = 'Carga las lecciones de apertura desde los PGN de apps/lessons/data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Borra las lecciones existentes antes de cargar.',
        )

    def handle(self, *args, **options):
        if options['reset']:
            deleted, _ = Lesson.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'Borradas {deleted} lecciones.'))

        new_lessons = upd_lessons = 0
        new_chapters = upd_chapters = 0

        with transaction.atomic():
            # 1) Lecciones de Lichess (PGN multipvv).
            for spec in LICKS:
                path = DATA_DIR / spec['file']
                if not path.exists():
                    self.stderr.write(
                        self.style.ERROR(f'No encontrado: {path}; se omite.')
                    )
                    continue
                lesson, created = self._upsert_lesson(spec)
                new_lessons += created
                upd_lessons += (not created)
                c, u = self._load_records(lesson, iter_chapter_records(path))
                new_chapters += c
                upd_chapters += u
                self.stdout.write(
                    f'  {lesson.title}: {c} capítulos nuevos, {u} actualizados.'
                )

            # 2) Partida Italiana (generada y validada desde Python).
            lesson, created = self._upsert_lesson(ITALIANA)
            new_lessons += created
            upd_lessons += (not created)

            pgn_path = self._write_italiana_pgn()
            self.stdout.write(f'  PGN generado: {pgn_path.name}')
            c, u = self._load_records(lesson, iter_chapter_records(pgn_path))
            new_chapters += c
            upd_chapters += u
            self.stdout.write(
                f'  {lesson.title}: {c} capítulos nuevos, {u} actualizados.'
            )

        self.stdout.write(self.style.SUCCESS(
            f'Lecciones: {new_lessons} nuevas / {upd_lessons} actualizadas | '
            f'Capítulos: {new_chapters} nuevos / {upd_chapters} actualizados.'
        ))

    # ------------------------------------------------------------------ utils

    def _upsert_lesson(self, spec: dict) -> tuple[Lesson, bool]:
        """Crea o actualiza la lección identificada por su slug."""
        defaults = {
            'title': spec['title'],
            'family': spec['family'],
            'eco': spec.get('eco', ''),
            'summary': spec.get('summary', ''),
            'icon': spec.get('icon', '📘'),
            'color': spec.get('color', Lesson.Color.MIXED),
            'student_color': spec.get(
                'student_color', Lesson.StudentColor.WHITE,
            ),
            'order': spec.get('order', 0),
            'source_url': spec.get('source_url', ''),
            'is_published': True,
        }
        lesson, created = Lesson.objects.update_or_create(
            slug=spec['slug'], defaults=defaults
        )
        return lesson, created

    def _write_italiana_pgn(self) -> Path:
        """
        Genera `data/italiana.pgn` a partir de `italiana_data.py`.

        Si alguna jugada fuese ilegal, `build_and_check` lanza ValueError y el
        comando aborta sin tocar la base de datos (todo va en una transacción).
        """
        pgn = pgn_builder.build_and_check(
            study=ITALIANA['title'],
            url=ITALIANA.get('source_url', ''),
            chapters=ITALIANA_CHAPTERS,
        )
        path = DATA_DIR / 'italiana.pgn'
        path.write_text(pgn, encoding='utf-8')
        return path

    def _load_records(self, lesson: Lesson, records: Iterable[dict]):
        """Vuelca capítulos en la lección. Idempotente por (lección, order)."""
        created = updated = 0
        for rec in records:
            _, was_created = LessonChapter.objects.update_or_create(
                lesson=lesson,
                order=rec['order'],
                defaults={
                    'title': rec['title'],
                    'intro': rec['comment'],
                    'start_fen': rec['fen'],
                    'tree': rec['tree'],
                    'source_url': rec['url'],
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
        return created, updated

ITALIANA = {
    'slug': 'partida-italiana',
    'title': 'Partida Italiana',
    'family': 'Italiana',
    'eco': 'C50',
    'icon': '🏛️',
    'color': Lesson.Color.LIGHT,
    'student_color': Lesson.StudentColor.WHITE,
    'order': 5,
    'summary': (
        'La apertura más antigua que se juega todavía. Tres capítulos para '
        'dominar el Giuoco Piano, la Ruy López y el Ataque Evans.'
    ),
}
