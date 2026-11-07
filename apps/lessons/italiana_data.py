"""
Partida Italiana: capítulos escritos a mano (no provienen de Lichess).

Cada capítulo se declara como jugadas y se convierte a PGN *gamebook* con
`pgn_builder.build_chapter_pgn`, que valida cada jugada con python-chess antes
de escribirla: si alguna fuese ilegal, el comando de carga aborta con un error
claro. Así el PGN generado siempre es jugable por el importador y por el alumno.

Estructura de cada capítulo:

    {
        'title':   str,
        'intro':   str,                           # comentario inicial
        'moves':   [(san, comentario), ...],      # línea principal
        'sides':   [(n, [[(san, com), ...]]), ...],  # alternativas a la jugada n
        'eco':     str,
        'opening': str,
    }
"""
from __future__ import annotations

CHAPTERS = [
    # ---------------------------------------------------------------- 1 ------
    {
        'title': 'La Partida Italiana: los primeros movimientos',
        'opening': 'Italian Game',
        'eco': 'C50',
        'intro': (
            'La Partida Italiana es la apertura más antigua que se juega todavía: '
            'aparece en los manuscritos del siglo XVI y sigue siendo la puerta de '
            'entrada al ajedrez de ataque. Después de 1.e4 e5 2.Nf3 Nc6 3.Bc4 el '
            'blanco apunta al rey negro desde el primer momento, y por eso casi '
            'toda la teoría posterior se organiza alrededor de esta posición.'
        ),
        'moves': [
            ('e4', 'Ocupación del centro: el blanco se apropia de los dos centros.'),
            ('e5', 'Respuesta simétrica. El negro también busca abrir el centro.'),
            ('Nf3', 'Desarrollo y defensa: el caballo sostiene e4 y mira a g5 y h4.'),
            ('Nc6', 'La defensa clásica: ataca e4 y protege el peón de e5.'),
            ('Bc4', 'El alfil se coloca en la diagonal larga y apunta a f7.'),
        ],
        'sides': [
            (5, [[
                ('Bb5', 'La Ruy López. En lugar de apuntar a f7, el alfil presiona '
                        'el caballo de c6. Es la variante más conocida de la '
                        'Italiana y la que se juega más en la práctica actual.'),
            ]]),
        ],
    },

    # ---------------------------------------------------------------- 2 ------
    {
        'title': 'Giuoco Piano y Giuoco Russo',
        'opening': 'Italian Game: Giuoco Piano',
        'eco': 'C53',
        'intro': (
            'Tras 3.Bc4 el negro tiene dos respuestas clásicas. 3...Bc5 es la línea '
            'principal del Giuoco Piano y mantiene la tensión; 3...Nf6, la Defensa '
            'de los dos Caballos, entrega un peón pero abre el centro de inmediato. '
            'El blanco prepara entonces con c3 o d3, jugadas lentas que permiten '
            'construir un centro grande y abrir el flanco de rey.'
        ),
        'moves': [
            ('e4', ''),
            ('e5', ''),
            ('Nf3', ''),
            ('Nc6', ''),
            ('Bc4', ''),
            ('Bc5', 'El Giuoco Piano: el alfil negro apunta a f2 y a la diagonal de '
                    'blanco, ofreciéndole un objetivo permanente.'),
            ('c3', 'Jugada de espera que sostiene d4 con el peón y prepara el '
                   'lateral de negras.'),
        ],
        'sides': [
            (5, [[('Bb5', 'La Ruy López: cambiar de plan y presionar c6.')]]),
            (6, [[('Nf6', 'Defensa de los dos Caballos: el negro entrega un peón y '
                          'abre el centro, pero entrega al blanco un ataque muy '
                          'concreto contra g7.')]]),
            (7, [[('d3', 'La variante tranquila. Sin bloquear el peón c2, el blanco '
                          'lleva sus miras al plan de apertura central y al flanco '
                          'de rey.')]]),
        ],
    },

    # ---------------------------------------------------------------- 3 ------
    {
        'title': 'El ataque al flanco de rey',
        'opening': 'Italian Game: Evans Gambit Declined',
        'eco': 'C52',
        'intro': (
            'Después de 3.Bc4 Bc5 el blanco puede acelerar el ataque con 4.d4, '
            'sacrificando un peón para abrir el centro y el flanco de rey de '
            'inmediato. Es el arranque del Ataque Evans: agresivo y muy divertido '
            'para el alumno, aunque también muy difícil y técnicamente exigente.'
        ),
        'moves': [
            ('e4', ''),
            ('e5', ''),
            ('Nf3', ''),
            ('Nc6', ''),
            ('Bc4', ''),
            ('Bc5', ''),
            ('d4', 'El blanco ofrece un peón para abrir el centro de golpe y '
                   'arrancar el ataque al rey negro antes de que se termine el '
                   'desarrollo.'),
            ('exd4', 'El negro acepta el sacrificio. Era el plan del blanco.'),
            ('O-O', 'El enroque desarrolla y pone a salvo al rey, que es justo lo '
                    'que se necesita antes de lanzar el ataque.'),
            ('Nf6', 'El negro desarrolla y ataca el peón de e4, que quedó '
                    'defendido solo por el alfil.'),
            ('c3', 'El blanco golpea en el centro antes de que el negro se '
                   'consolide, y gana espacio para d4.'),
        ],
        'sides': [
            (7, [[
                ('d3', 'La partida tranquila: sin sacrificar el peón, el blanco '
                       'construye un centro grande con c3 y d4.'),
            ]]),
        ],
    },
]
