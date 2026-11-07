"""
Importador de estudios de Lichess (PGN con modo `gamebook`) al modelo de lecciones.

Un estudio de Lichess exportado a PGN produce **un jogo por capítulo**, y cada
capítulo es una rama de teoría con comentarios. Como el objetivo aquí es que el
alumno *elija* su jugada, no solo la reproduzca, el importador convierte cada
juego en un árbol de variantes:

    raíz (posición inicial)
      └─ variations: [nodo, nodo, ...]      ← jugadas candidatas del alumno
           └─ variations: [...]             ← la siguiente decisión

Cada nodo es un diccionario JSON:

    {"san": "e4", "uci": "e2e4", "fen": "...",
     "comment": "texto del autor", "main": true, "accepted": true,
     "required": false, "hints": [], "variations": [...]}

Este formato es el que consume `LessonChapter.tree` y el cliente
`static/js/lessons_app.js`.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import chess
import chess.pgn

DATA_DIR = Path(__file__).resolve().parent / 'data'

# Anotaciones de Lichess que no son texto para el alumno.
_ANNOTATION_TAGS = re.compile(r'\[%(?:cal|csl|clk|eval|emt|cen|piece)\s+[^\]]*\]', re.I)
# Etiquetas sueltas tipo { [%cal Gc7c5] } -> se eliminan con sus llaves.
_EMPTY_BRACES = re.compile(r'\{\s*\}')
# { [%clk 0:05:00] } o { [%clk 0:05:00] }
_CLOCK = re.compile(r'\[\s*%clk[^\]]*\]', re.I)
# Normaliza espacios múltiples sin romper los saltos de línea del autor.
_MULTISPACE = re.compile(r'[ \t]+')
_MULTINEWLINE = re.compile(r'\n{3,}')


def clean_comment(text: str | None) -> str:
    """Deja el comentario legible: sin comandos de Lichess y sin ruido."""
    if not text:
        return ''
    out = _ANNOTATION_TAGS.sub('', text)
    out = _CLOCK.sub('', out)
    out = _EMPTY_BRACES.sub('', out)
    out = out.replace('{', '').replace('}', '')
    out = _MULTISPACE.sub(' ', out)
    out = _MULTINEWLINE.sub('\n\n', out)
    return out.strip()


def _board_fen(node: chess.pgn.GameNode) -> str:
    """Fen de la posición *resultante* de la jugada del nodo."""
    return node.board().fen()


def _node_to_dict(node: chess.pgn.GameNode, is_main: bool = False) -> dict:
    """
    Convierte recursivamente un nodo (y sus RAV) al diccionario JSON.

    `is_main` distingue la jugada principal del autor de las alternativas: en un
    gamebook la primera variación es "la buena" y el resto son las que el alumno
    elige para desviarse de la teoría.

    OJO: en python-chess `GameNode.san` y `GameNode.uci` son MÉTODOS, no
    propiedades. Hay que llamarlos; si no, se guardaría en el JSON un método
    ligado en lugar de la jugada.
    """
    children = [
        _node_to_dict(child, is_main=(i == 0))
        for i, child in enumerate(node.variations)
    ]
    return {
        'san': node.san(),
        'uci': node.uci(),
        'fen': _board_fen(node),
        'comment': clean_comment(node.comment),
        'main': is_main,
        'accepted': True,
        'required': False,
        'hints': [],
        'variations': children,
    }


def parse_chapter(pgn_text: str) -> dict | None:
    """
    Convierte un capítulo (un juego PGN) en un diccionario:

        {"fen", "comment", "variations", "headers"}
    """
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return None

    headers = {k: v for k, v in game.headers.items() if v}

    # Lichess marca la posición inicial con SetUp/FEN; si no, es la posición
    # estándar y `game.board()` ya devuelve el fen inicial correcto.
    start_fen = game.board().fen()
    root_comment = clean_comment(game.comment)

    variations = [
        _node_to_dict(child, is_main=(i == 0))
        for i, child in enumerate(game.variations)
    ]

    return {
        'fen': start_fen,
        'comment': root_comment,
        'variations': variations,
        'headers': headers,
    }


def iter_chapters(pgn_path: Path):
    """Itera los capítulos de un PGN multipvv devolviendo (texto, cabeceras)."""
    text = pgn_path.read_text(encoding='utf-8', errors='replace')
    for raw in _split_games(text):
        stripped = raw.strip()
        if not stripped:
            continue
        yield stripped


def _split_games(text: str):
    """
    Divide un PGN multipvv en juegos.

    No usamos `read_game` en bucle porque necesitamos el texto crudo de cada
    capítulo (con sus comentarios) para conservarlos íntegros. El corte se hace
    por la cabecera `[Event ...]` que Lichess emite al inicio de cada capítulo.
    """
    lines = text.splitlines()
    games: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        if line.startswith('[Event ') and current:
            games.append(current)
            current = []
        current.append(line)

    if current:
        games.append(current)

    return ['\n'.join(game) for game in games]


def iter_chapter_records(pgn_path: Path):
    """
    Yield de diccionarios por capítulo con los metadatos ya normalizados:

        {"title", "url", "study", "chapter_mode", "fen", "comment", "tree",
         "eco", "opening", "order"}
    """
    for index, raw in enumerate(iter_chapters(pgn_path)):
        parsed = parse_chapter(raw)
        if not parsed:
            continue
        headers = parsed['headers']
        yield {
            'title': headers.get('ChapterName') or f'Capítulo {index + 1}',
            'url': headers.get('ChapterURL', ''),
            'study': headers.get('StudyName', ''),
            'chapter_mode': headers.get('ChapterMode', ''),
            'fen': parsed['fen'],
            'comment': parsed['comment'],
            'tree': parsed['variations'],
            'eco': '' if headers.get('ECO') in (None, '?') else headers.get('ECO', ''),
            'opening': '' if headers.get('Opening') in (None, '?') else headers.get('Opening', ''),
            'order': index,
        }
