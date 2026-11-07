"""Crea la lección del Gambito Rousseau sin modificar otras lecciones."""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.lessons import pgn_builder
from apps.lessons.models import Lesson, LessonChapter
from apps.lessons.pgn_importer import parse_chapter
from apps.lessons.rousseau_data import CHAPTERS, LESSON


def _annotate_tree(tree, required, hints):
    found = set()

    def visit(nodes, path):
        prefix = ' '.join(path)
        for node in nodes:
            if required.get(prefix) == node['san']:
                node['required'] = True
                found.add((prefix, node['san']))
            if prefix in hints:
                node['hints'] = hints[prefix]
            visit(node.get('variations', []), path + [node['san']])

    visit(tree, [])
    missing = set(required.items()) - found
    if missing:
        raise CommandError(
            'No se encontraron jugadas obligatorias en el árbol: '
            + ', '.join(f'{path}: {move}' for path, move in sorted(missing))
        )


def _build_chapters():
    records = []
    for order, source in enumerate(CHAPTERS):
        pgn_fields = {
            key: value
            for key, value in source.items()
            if key not in ('required', 'hints')
        }
        pgn = pgn_builder.build_chapter_pgn(
            study=LESSON['title'],
            url=LESSON['source_url'],
            **pgn_fields,
        )
        problems = pgn_builder.validate_pgn(pgn)
        if problems:
            raise CommandError(
                f'PGN inválido en "{source["title"]}": ' + '; '.join(problems)
            )

        parsed = parse_chapter(pgn)
        if parsed is None:
            raise CommandError(f'No se pudo leer el capítulo "{source["title"]}".')
        tree = parsed['variations']
        _annotate_tree(tree, source.get('required', {}), source.get('hints', {}))
        records.append({
            'title': source['title'],
            'intro': source['intro'],
            'start_fen': parsed['fen'],
            'tree': tree,
            'source_url': LESSON['source_url'],
            'order': order,
        })
    return records


class Command(BaseCommand):
    help = 'Crea la lección Gambito Rousseau sin sobrescribir contenido existente.'

    def handle(self, *args, **options):
        if Lesson.objects.filter(slug=LESSON['slug']).exists():
            raise CommandError(
                f'Ya existe la lección "{LESSON["slug"]}"; no se modificó ningún contenido.'
            )

        chapters = _build_chapters()
        with transaction.atomic():
            if Lesson.objects.filter(slug=LESSON['slug']).exists():
                raise CommandError(
                    f'Ya existe la lección "{LESSON["slug"]}"; no se modificó ningún contenido.'
                )
            lesson = Lesson.objects.create(
                slug=LESSON['slug'],
                title=LESSON['title'],
                family=LESSON['family'],
                eco=LESSON['eco'],
                icon=LESSON['icon'],
                color=Lesson.Color[LESSON['color']],
                student_color=LESSON['student_color'],
                order=LESSON['order'],
                source_url=LESSON['source_url'],
                summary=LESSON['summary'],
                is_published=True,
            )
            LessonChapter.objects.bulk_create([
                LessonChapter(lesson=lesson, **chapter)
                for chapter in chapters
            ])

        self.stdout.write(self.style.SUCCESS(
            f'Creada "{lesson.title}" con {len(chapters)} capítulos publicados.'
        ))
