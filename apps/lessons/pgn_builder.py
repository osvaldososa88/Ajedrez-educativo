"""
Constructor de PGN en modo `gamebook` a partir de jugadas declaradas en Python.

Se usa para la Partida Italiana, que no proviene de un estudio de Lichess. Todas
las jugadas se validan con python-chess **antes** de escribirse: si alguna fuese
ilegal se aborta con un error claro, de modo que el PGN generado siempre es
jugable por el importador y por el alumno.
"""
from __future__ import annotations

import io

import chess
import chess.pgn


def _safe(text: str) -> str:
    """Un comentario PGN no puede contener llaves."""
    return (text or '').replace('{', '(').replace('}', ')').strip()


def _tag(text: str) -> str:
    """Un valor de cabecera PGN no puede contener comillas dobles."""
    return (text or '').replace('"', "'").strip()


def _play(board: chess.Board, san: str) -> str:
    """Juega `san` y devuelve la SAN normalizada. Aborta si es ilegal."""
    try:
        move = board.parse_san(san)
    except (ValueError, AssertionError) as exc:
        raise ValueError(
            f'Jugada ilegal {san!r} en la posición {board.fen()}'
        ) from exc
    out = board.san(move)
    board.push(move)
    return out


def _emit(board: chess.Board, san: str, comment: str) -> list[str]:
    """Devuelve los tokens PGN de una jugada (número + SAN + comentario)."""
    text = _play(board, san)
    # `board.ply()` es el número de medias jugadas *después* de la jugada actual.
    ply = board.ply()
    if board.turn == chess.BLACK:
        # Las blancas acaban de mover: ply impar -> 1. e4, 2. Nf3 ...
        token = f'{ply // 2 + 1}. {text}'
    else:
        # Los negros acaban de mover: ply par -> 1... e5, 2... Nc6 ...
        token = f'{(ply + 1) // 2}... {text}'
    return [token, '{' + _safe(comment) + '}'] if comment else [token]


def _build_side(board: chess.Board, line) -> str:
    """Construye una línea alternativa `( ... )` desde la posición de `board`."""
    # OJO: se copia el tablero *conservando la pila de jugadas* (`stack=True`).
    # Con `stack=False` `board.ply()` volvería a 0 y las alternativas se
    # numerarían desde "1." en lugar de continuar desde la jugada del autor.
    side = board.copy()
    tokens: list[str] = []
    for san, comment in line:
        tokens.extend(_emit(side, san, comment))
    return '(' + ' '.join(tokens) + ')'


def build_chapter_pgn(
    *,
    title: str,
    intro: str = '',
    moves=(),
    sides=(),
    eco: str = '',
    opening: str = '',
    study: str = '',
    url: str = '',
) -> str:
    """
    Genera un capítulo PGN completo.

    `moves`  -> línea principal: lista de tuplas `(san, comentario)`.
    `sides`  -> alternativas: lista de tuplas `(n, lineas)` donde `n` es la posición
                (1-based) de la jugada principal a la que sustituye.
    """
    board = chess.Board()
    side_map = {int(n): list(lines) for n, lines in sides}
    tokens: list[str] = []

    for index, (san, comment) in enumerate(moves, start=1):
        # Copia de la posición ANTERIOR a esta jugada: es desde donde ramifica
        # la alternativa. Se toma antes de emitir porque `_emit` hace push.
        before = board.copy() if index in side_map else None

        tokens.extend(_emit(board, san, comment))

        # En PGN una RAV se escribe DESPUÉS de la jugada a la que sustituye:
        # `... 3. Bc4 (3. Bb5 3... a6)` significa "en vez de Bc4, podía jugar Bb5".
        if before is not None:
            for line in side_map[index]:
                tokens.append(_build_side(before, line))

    headers = [
        f'[Event "{_tag(title)}"]',
        '[Site "?"]',
        '[Date "????.??.??"]',
        '[Round "?"]',
        '[White "?"]',
        '[Black "?"]',
        '[Result "*"]',
        f'[ECO "{_tag(eco) or "?"}"]',
        f'[Opening "{_tag(opening) or "?"}"]',
        f'[ChapterName "{_tag(title)}"]',
        f'[ChapterURL "{_tag(url)}"]',
        f'[StudyName "{_tag(study)}"]',
        '[ChapterMode "gamebook"]',
    ]

    body = ' '.join(tokens)
    if intro:
        body = '{' + _safe(intro) + '} ' + body

    return (
        '\n'.join(headers)
        + '\n\n'
        + body
        + ' *\n'
    )


def build_study_pgn(chapters, *, study: str, url: str = '') -> str:
    """Concatena varios capítulos en un único PGN (uno por juego)."""
    blocks = []
    for chapter in chapters:
        blocks.append(
            build_chapter_pgn(
                study=study,
                url=url,
                **chapter,
            )
        )
    return '\n'.join(blocks)


# --- Verificación opcional de un PGN recién generado -------------------------

def iter_games(pgn_text: str):
    """Itera los juegos de un PGN multipvv.

    `chess.pgn.read_game` devuelve UN juego, no un iterador: hay que llamarlo
    repetidamente sobre el mismo flujo para recorrer todos los capítulos.
    """
    stream = io.StringIO(pgn_text)
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            return
        yield game


def validate_pgn(pgn_text: str) -> list[str]:
    """Devuelve una lista de problemas detectados (vacía = todo correcto)."""
    problems: list[str] = []
    for index, game in enumerate(iter_games(pgn_text), start=1):
        if game.errors:
            problems.append(f'juego {index}: errores de sintaxis PGN: {game.errors}')

        def walk(node, board: chess.Board, path: list[str]) -> None:
            """Recorre una rama; cada alternativa hereda una COPIA del tablero."""
            for child in node.variations:
                san = child.san()          # método, no propiedad
                branch = board.copy(stack=False)
                label = f'juego {index} [{" ".join(path)} {san}]'
                try:
                    branch.push_san(san)
                except (ValueError, AssertionError) as exc:
                    problems.append(f'{label}: jugada ilegal ({exc})')
                    continue
                walk(child, branch, path + [san])

        walk(game, game.board(), [])

    return problems


def build_and_check(*, study: str, url: str = '', chapters) -> str:
    """Genera el PGN del estudio y lo valida; lanza si algo es ilegal."""
    pgn = build_study_pgn(chapters, study=study, url=url)
    problems = validate_pgn(pgn)
    if problems:
        raise ValueError(
            'Partida Italiana con jugadas inválidas:\n  - ' + '\n  - '.join(problems)
        )
    return pgn
