"""Catálogo, sesión interactiva y validación de jugadas de lecciones."""
from __future__ import annotations

import json
import re

import chess
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Lesson, LessonChapter, LessonVariantProgress


def _visible(request):
    """Lecciones publicadas; los autores ven además las borradas en borrador."""
    qs = Lesson.objects.all().prefetch_related('chapters')
    if request.user.is_authenticated and request.user.is_staff:
        return qs
    return qs.published()


@login_required
def lesson_index(request):
    """Catálogo de lecciones agrupado por familia de apertura."""
    lessons = list(_visible(request).order_by('order', 'title'))
    families: dict[str, list[Lesson]] = {}
    for lesson in lessons:
        families.setdefault(lesson.family or 'Otras', []).append(lesson)
    return render(request, 'lessons/index.html', {
        'lessons': lessons,
        'families': families,
    })


@login_required
def lesson_detail(request, slug):
    """Portada de la lección: lista de capítulos y acceso al primero."""
    lesson = get_object_or_404(_visible(request), slug=slug)
    chapters = list(lesson.chapters.all())
    return render(request, 'lessons/detail.html', {
        'lesson': lesson,
        'chapters': chapters,
        'first_chapter': chapters[0] if chapters else None,
    })


@login_required
def chapter_detail(request, pk):
    """Sesión de apertura con navegación entre todos los capítulos de la lección."""
    chapter = get_object_or_404(
        LessonChapter.objects.select_related('lesson').prefetch_related('lesson__chapters'),
        pk=pk,
        lesson__is_published=True,
    )
    siblings = list(chapter.lesson.chapters.all())
    position = next((i for i, c in enumerate(siblings) if c.pk == chapter.pk), 0)
    return render(request, 'lessons/chapter.html', {
        'lesson': chapter.lesson,
        'chapter': chapter,
        'chapters': siblings,
        'chapter_index': position,
        'prev_chapter': siblings[position - 1] if position > 0 else None,
        'next_chapter': siblings[position + 1] if position + 1 < len(siblings) else None,
        'lesson_progress': _lesson_progress(chapter.lesson, request.user),
        'session_chapters': [
            {
                'id': sibling.pk,
                'title': sibling.title,
                'tree_url': reverse('chapter_tree', args=[sibling.pk]),
                'play_url': reverse('chapter_play', args=[sibling.pk]),
            }
            for sibling in siblings
        ],
    })


@login_required
def chapter_tree(request, pk):
    """Árbol de jugadas del capítulo en JSON (usado por el cliente al navegar)."""
    chapter = get_object_or_404(
        LessonChapter.objects.select_related('lesson'), pk=pk, lesson__is_published=True,
    )
    return JsonResponse({
        'id': chapter.pk,
        'title': chapter.title,
        'fen': chapter.start_fen,
        'intro': chapter.intro,
        'tree': chapter.tree,
        'progress': _chapter_progress(chapter, request.user),
        'lesson_progress': _lesson_progress(chapter.lesson, request.user),
    })


def _chapter_progress(chapter, user):
    return list(
        LessonVariantProgress.objects.filter(
            chapter=chapter,
            user=user,
        ).values('branch_key', 'attempts', 'mistakes', 'completed')
    )


def _record_attempt(chapter, user, path, *, mistake=False):
    progress, _ = LessonVariantProgress.objects.get_or_create(
        user=user,
        lesson=chapter.lesson,
        chapter=chapter,
        branch_key=' '.join(path),
    )
    progress.attempts += 1
    if mistake:
        progress.mistakes += 1
    progress.save(update_fields=['attempts', 'mistakes', 'updated_at'])


def _lesson_progress(lesson, user):
    rows = LessonVariantProgress.objects.filter(lesson=lesson, user=user)
    completed_chapters = rows.filter(completed=True).values('chapter_id').distinct().count()
    completed_branches = rows.filter(completed=True).count()
    total_chapters = lesson.chapters.count()
    return {
        'completed_chapters': completed_chapters,
        'total_chapters': total_chapters,
        'completed_branches': completed_branches,
    }


def _clean_path(value):
    if not isinstance(value, list) or len(value) > 128:
        raise ValueError('La ruta de jugadas no es válida.')
    if any(
        not isinstance(uci, str)
        or not re.fullmatch(r'[a-h][1-8][a-h][1-8][qrbn]?', uci)
        for uci in value
    ):
        raise ValueError('La ruta contiene una jugada UCI no válida.')
    return value


def _resolve_path(chapter, path):
    board = chess.Board(chapter.start_fen)
    candidates = chapter.tree
    current = None
    for uci in path:
        current = next(
            (node for node in candidates if isinstance(node, dict) and node.get('uci') == uci),
            None,
        )
        if current is None:
            raise ValueError('La ruta no pertenece al árbol de este capítulo.')
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as exc:
            raise ValueError('El árbol contiene una jugada UCI no válida.') from exc
        if move not in board.legal_moves:
            raise ValueError('El árbol contiene una jugada ilegal para esta posición.')
        board.push(move)
        candidates = current.get('variations', [])
        if not isinstance(candidates, list):
            raise ValueError('El árbol del capítulo no tiene un formato válido.')
    return board, candidates, current


def _node_for_move(candidates, uci):
    return next(
        (
            node for node in candidates
            if isinstance(node, dict) and node.get('uci') == uci
        ),
        None,
    )


def _auto_reply(board, candidates, path, student_color):
    played = []
    alternatives = []
    while board.turn != student_color and candidates:
        node = next(
            (item for item in candidates if item.get('main')),
            candidates[0],
        )
        alternatives.extend(
            {'node': sibling, 'path': path.copy()}
            for sibling in candidates
            if sibling.get('uci') != node.get('uci')
        )
        move = chess.Move.from_uci(node['uci'])
        if move not in board.legal_moves:
            raise ValueError('El árbol contiene una respuesta ilegal del adversario.')
        board.push(move)
        path.append(node['uci'])
        played.append(node)
        candidates = node.get('variations', [])
    return board, candidates, path, played, alternatives


def _state_payload(chapter, user, board, candidates, current, path, played=None, **extra):
    return {
        'path': path,
        'fen': board.fen(),
        'start_fen': chapter.start_fen,
        'turn': 'white' if board.turn == chess.WHITE else 'black',
        'legal_moves': [move.uci() for move in board.legal_moves],
        'choices': candidates,
        'current': current,
        'played': played or [],
        'completed': not candidates,
        'progress': _chapter_progress(chapter, user),
        'lesson_progress': _lesson_progress(chapter.lesson, user),
        **extra,
    }


@login_required
@require_POST
def chapter_play(request, pk):
    """Inicia, navega y valida una sesión de práctica sobre el árbol existente."""
    chapter = get_object_or_404(
        LessonChapter.objects.select_related('lesson'),
        pk=pk,
        lesson__is_published=True,
    )
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError('La solicitud no tiene un formato válido.')
        action = data.get('action')
        path = _clean_path(data.get('path', []))
        color = data.get('color')
        if color not in ('white', 'black'):
            raise ValueError('Elige jugar con blancas o negras.')
        student_color = chess.WHITE if color == 'white' else chess.BLACK
        board, candidates, current = _resolve_path(chapter, path)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    if action in ('start', 'navigate'):
        played = []
        reply_choices = []
        if action == 'start':
            board, candidates, path, played, reply_choices = _auto_reply(
                board, candidates, path, student_color,
            )
        board, candidates, current = _resolve_path(chapter, path)
        return JsonResponse(_state_payload(
            chapter, request.user, board, candidates, current, path, played,
            reply_choices=reply_choices,
        ))

    if action not in ('move', 'explore'):
        return JsonResponse({'error': 'Acción de lección desconocida.'}, status=400)

    uci = data.get('uci')
    if not isinstance(uci, str) or not re.fullmatch(r'[a-h][1-8][a-h][1-8][qrbn]?', uci):
        return JsonResponse({'error': 'La jugada UCI no es válida.'}, status=400)
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return JsonResponse({'error': 'La jugada UCI no es válida.'}, status=400)
    if move not in board.legal_moves:
        if action == 'move':
            _record_attempt(chapter, request.user, path, mistake=True)
        return JsonResponse({'error': 'Esa jugada no es legal en la posición actual.'}, status=400)

    if action == 'move' and board.turn != student_color:
        return JsonResponse({'error': 'Es el turno automático del adversario.'}, status=400)

    node = _node_for_move(candidates, uci)
    if node is None:
        if action == 'move':
            _record_attempt(chapter, request.user, path)
        return JsonResponse(_state_payload(
            chapter, request.user, board, candidates, current, path,
            accepted=False,
            unmodeled=True,
            message='La jugada es legal, pero este capítulo no incluye una continuación preparada para ella.',
        ))

    required_moves = [
        item for item in candidates
        if isinstance(item, dict) and item.get('required') is True
    ]
    if action == 'move' and (
        node.get('accepted', True) is False
        or (required_moves and node.get('required') is not True)
    ):
        _record_attempt(chapter, request.user, path, mistake=True)
        return JsonResponse(_state_payload(
            chapter, request.user, board, candidates, current, path,
            accepted=False,
            unmodeled=False,
            message='La jugada está en el árbol, pero no es la respuesta esperada en esta posición.',
        ))

    if action == 'move':
        _record_attempt(chapter, request.user, path)

    board.push(move)
    path.append(uci)
    candidates = node.get('variations', [])
    played = [node]
    board, candidates, path, auto_played, reply_choices = _auto_reply(
        board, candidates, path, student_color,
    )
    played.extend(auto_played)
    board, candidates, current = _resolve_path(chapter, path)
    completed = not candidates

    if action == 'move' and completed:
        branch_progress, _ = LessonVariantProgress.objects.get_or_create(
            user=request.user,
            lesson=chapter.lesson,
            chapter=chapter,
            branch_key=' '.join(path),
        )
        if not branch_progress.completed:
            branch_progress.completed = True
            branch_progress.save(update_fields=['completed', 'updated_at'])

    return JsonResponse(_state_payload(
        chapter, request.user, board, candidates, current, path, played,
        accepted=True,
        unmodeled=False,
        completed=completed,
        reply_choices=reply_choices,
    ))