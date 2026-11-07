"""Contenido del Gambito Rousseau basado en la transcripción del video fuente."""

SOURCE_URL = 'https://www.youtube.com/watch?v=xvweTRkDitI'

LESSON = {
    'slug': 'gambito-rousseau',
    'title': 'Gambito Rousseau',
    'family': 'Italiana',
    'eco': 'C50',
    'icon': '♟️',
    'color': 'DARK',
    'student_color': 'black',
    'order': 40,
    'source_url': SOURCE_URL,
    'summary': (
        'Defensa agresiva contra la Italiana con 3...f5. Practica la captura '
        'del peón, las ideas de ...e4 y ...Nd4, y la respuesta a 4.d4. '
        'Contenido parafraseado de la transcripción proporcionada; los árboles '
        'se validan con las reglas del ajedrez y Stockfish se consulta por separado.'
    ),
}

CHAPTERS = [
    {
        'title': 'El plan del gambito y la captura 4.exf5',
        'intro': (
            'El gambito se plantea con 3...f5: las negras ofrecen el peón de '
            'flanco para apartar el peón central blanco. Si se captura, responde '
            'con ...e4 y aprovecha el tiempo ganado contra el caballo de f3. '
            'La línea principal de este capítulo sigue la idea explicada en el '
            'video; la retirada temprana del caballo se muestra como alternativa.'
        ),
        'moves': [
            ('e4', ''),
            ('e5', ''),
            ('Nf3', ''),
            ('Nc6', ''),
            ('Bc4', 'La Italiana: el alfil blanco apunta a f7.'),
            ('f5', 'El Rousseau ofrece el peón de f y busca desviar el centro blanco.'),
            ('exf5', 'Las blancas aceptan el peón ofrecido.'),
            ('e4', 'El avance ataca el caballo de f3 y gana espacio en el centro.'),
            ('Qe2', 'La dama blanca presiona el peón avanzado.'),
            ('Qe7', 'La dama negra se coloca detrás del peón y sostiene la idea central.'),
            ('Ng1', 'El caballo vuelve a su casilla inicial para salir del ataque.'),
            ('Nf6', 'Desarrolla una pieza y prepara el enroque.'),
        ],
        'sides': [
            (9, [[
                ('Ng1', 'La retirada inmediata del caballo también aparece en la transcripción.'),
                ('d5', 'El avance ataca el alfil de c4 y gana un tiempo de desarrollo.'),
                ('Bb3', 'El alfil se aparta de la diagonal del peón.'),
            ]]),
        ],
        'required': {
            'e4 e5 Nf3 Nc6 Bc4': 'f5',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5': 'e4',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2': 'Qe7',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1': 'Nf6',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Ng1': 'd5',
        },
        'hints': {
            'e4 e5 Nf3 Nc6 Bc4': [
                'Busca una jugada de flanco que desvíe el peón central blanco.',
                'El gambito empieza con el avance del peón de f.',
            ],
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5': [
                'El avance central gana un tiempo sobre el caballo de f3.',
            ],
        },
    },
    {
        'title': 'La táctica contra 7.d3',
        'intro': (
            'Tras la captura y la secuencia de damas, 7.d3 parece desarrollar '
            'el alfil y amenaza el peón de e4. La respuesta ...Nd4 crea una '
            'amenaza sobre c2; si la dama se aparta a d1, aparece el jaque '
            'descubierto que describe el instructor.'
        ),
        'moves': [
            ('e4', ''),
            ('e5', ''),
            ('Nf3', ''),
            ('Nc6', ''),
            ('Bc4', ''),
            ('f5', 'El gambito ofrece el peón de f para desviar el centro.'),
            ('exf5', ''),
            ('e4', 'El peón avanzado ataca el caballo de f3.'),
            ('Qe2', ''),
            ('Qe7', 'La dama sostiene el peón de e4.'),
            ('Ng1', ''),
            ('Nf6', 'Desarrolla el caballo y prepara ...Nd4.'),
            ('d3', 'Las blancas sostienen el centro y abren la diagonal del alfil.'),
            ('Nd4', 'El caballo salta con ataque a la dama y amenaza ...Nxc2+.'),
            ('Qd1', 'La dama mantiene protegido el punto de c2.'),
            ('Nxc2+', 'El caballo entra con jaque y ataca la torre de a1.'),
            ('Qxc2', 'La dama captura el caballo para responder al jaque.'),
            ('exd3+', 'El peón de e4 despeja la columna de la dama y da jaque.'),
        ],
        'required': {
            'e4 e5 Nf3 Nc6 Bc4': 'f5',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5': 'e4',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2': 'Qe7',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1': 'Nf6',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1 Nf6 d3': 'Nd4',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1 Nf6 d3 Nd4 Qd1': 'Nxc2+',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1 Nf6 d3 Nd4 Qd1 Nxc2+ Qxc2': 'exd3+',
        },
        'hints': {
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1 Nf6 d3': [
                'Busca un salto de caballo que ataque la dama y cree una amenaza en c2.',
                'El caballo de c6 puede entrar en d4.',
            ],
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1 Nf6 d3 Nd4 Qd1 Nxc2+ Qxc2': [
                'Al mover el peón de e4 se abre la columna de la dama negra.',
            ],
        },
    },
    {
        'title': 'El salto ...Nd4 contra 7.Nc3',
        'intro': (
            'Si las blancas desarrollan el caballo de b1 en lugar de jugar d3, '
            '...Nd4 vuelve a atacar la dama. Tras Qd1, el instructor recomienda '
            'el avance ...d5 para atacar el alfil y sostener la iniciativa.'
        ),
        'moves': [
            ('e4', ''),
            ('e5', ''),
            ('Nf3', ''),
            ('Nc6', ''),
            ('Bc4', ''),
            ('f5', 'El Rousseau ofrece un peón para luchar por el centro.'),
            ('exf5', ''),
            ('e4', 'El peón ataca el caballo de f3.'),
            ('Qe2', ''),
            ('Qe7', ''),
            ('Ng1', ''),
            ('Nf6', 'Desarrolla y completa la idea de la línea principal.'),
            ('Nc3', 'Las blancas desarrollan el caballo de b1.'),
            ('Nd4', 'El salto vuelve a atacar la dama y crea amenazas en c2.'),
            ('Qd1', 'La dama se retira y conserva la defensa de c2.'),
            ('d5', 'El peón ataca el alfil y disputa el centro.'),
        ],
        'required': {
            'e4 e5 Nf3 Nc6 Bc4': 'f5',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5': 'e4',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2': 'Qe7',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1': 'Nf6',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1 Nf6 Nc3': 'Nd4',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1 Nf6 Nc3 Nd4 Qd1': 'd5',
        },
    },
    {
        'title': 'El sacrificio ...Nf3+ en la línea de ...d5',
        'intro': (
            'En la línea con d3, ...Nd4 y ...d5, el avance c3 ataca el caballo '
            'de d4. La transcripción propone ...Nf3+ como sacrificio táctico. '
            'Explora las distintas capturas blancas; las respuestas del árbol '
            'reproducen la idea del video y no implican que cada continuación '
            'sea forzada.'
        ),
        'moves': [
            ('e4', ''),
            ('e5', ''),
            ('Nf3', ''),
            ('Nc6', ''),
            ('Bc4', ''),
            ('f5', 'El gambito ofrece el peón de f para desviar el centro.'),
            ('exf5', ''),
            ('e4', ''),
            ('Qe2', ''),
            ('Qe7', ''),
            ('Ng1', ''),
            ('Nf6', ''),
            ('d3', ''),
            ('Nd4', 'El caballo ataca la dama y crea amenazas en c2.'),
            ('Qd1', ''),
            ('d5', 'El avance gana tiempo sobre el alfil.'),
            ('c3', 'El peón ataca el caballo de d4.'),
            ('Nf3+', 'El caballo entra en f3 con jaque y se ofrece a las capturas.'),
            ('gxf3', 'La captura con peón conserva la dama, pero abre la columna g.'),
            ('exf3+', 'El peón de e4 captura en f3 y continúa el jaque.'),
        ],
        'sides': [
            (19, [
                [('Qxf3', 'La dama puede capturar el caballo, pero queda expuesta al peón de e4.'), ('exf3', 'El peón captura la dama en f3.')],
                [('Nxf3', 'El caballo de g1 puede capturar el caballo sacrificado.'), ('exf3+', 'El peón de e4 captura en f3 y despeja la columna de la dama.')],
            ]),
        ],
        'required': {
            'e4 e5 Nf3 Nc6 Bc4': 'f5',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5': 'e4',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2': 'Qe7',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1': 'Nf6',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1 Nf6 d3': 'Nd4',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1 Nf6 d3 Nd4 Qd1': 'd5',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1 Nf6 d3 Nd4 Qd1 d5 c3': 'Nf3+',
            'e4 e5 Nf3 Nc6 Bc4 f5 exf5 e4 Qe2 Qe7 Ng1 Nf6 d3 Nd4 Qd1 d5 c3 Nf3+ gxf3': 'exf3+',
        },
    },
    {
        'title': 'La respuesta a 4.d4',
        'intro': (
            'La transcripción identifica 4.d4 como el contraataque central más '
            'preciso. Se practica ...fxe4 y ...d5, seguido de la secuencia táctica '
            'con Qh5+, ...g6 y Nxg6. La línea está presentada como contenido del '
            'instructor, no como una variante forzada: puedes evaluar cualquier '
            'posición con Stockfish desde el panel.'
        ),
        'moves': [
            ('e4', ''),
            ('e5', ''),
            ('Nf3', ''),
            ('Nc6', ''),
            ('Bc4', ''),
            ('f5', 'El gambito plantea una lucha inmediata por el centro.'),
            ('d4', 'El contraataque central es la respuesta más crítica según la explicación del video.'),
            ('fxe4', 'El peón de f captura en e4 y ataca el caballo de f3.'),
            ('Nxe5', 'El caballo captura el peón central de e5.'),
            ('d5', 'El avance ataca el alfil y disputa el centro.'),
            ('Qh5+', 'La dama da jaque por la diagonal hacia el rey negro.'),
            ('g6', 'El peón bloquea el jaque y ataca la dama.'),
            ('Nxg6', 'El caballo captura el peón de g6, siguiendo la línea del video.'),
            ('hxg6', 'El peón de h captura el caballo.'),
            ('Qxg6+', 'La dama captura en g6 con jaque.'),
            ('Kd7', 'El rey se desplaza para salir del jaque.'),
            ('Bxd5', 'El alfil captura el peón central.'),
            ('Nge7', 'El caballo se desarrolla y protege la posición.'),
            ('Qxe4', 'La dama captura el peón de e4.'),
            ('Nxd5', 'El caballo captura el alfil de d5.'),
            ('Qxd5+', 'La dama recupera el caballo con jaque.'),
            ('Bd6', 'El alfil interrumpe el jaque y desarrolla una pieza.'),
        ],
        'sides': [
            (11, [[
                ('Bb5', 'En lugar del jaque de dama, el alfil también puede retirarse a b5.'),
                ('Nf6', 'Desarrolla el caballo mientras se mantiene la presión central.'),
            ]]),
        ],
        'required': {
            'e4 e5 Nf3 Nc6 Bc4': 'f5',
            'e4 e5 Nf3 Nc6 Bc4 f5 d4': 'fxe4',
            'e4 e5 Nf3 Nc6 Bc4 f5 d4 fxe4 Nxe5': 'd5',
            'e4 e5 Nf3 Nc6 Bc4 f5 d4 fxe4 Nxe5 d5 Qh5+': 'g6',
            'e4 e5 Nf3 Nc6 Bc4 f5 d4 fxe4 Nxe5 d5 Qh5+ g6 Nxg6': 'hxg6',
            'e4 e5 Nf3 Nc6 Bc4 f5 d4 fxe4 Nxe5 d5 Qh5+ g6 Nxg6 hxg6 Qxg6+': 'Kd7',
            'e4 e5 Nf3 Nc6 Bc4 f5 d4 fxe4 Nxe5 d5 Qh5+ g6 Nxg6 hxg6 Qxg6+ Kd7 Bxd5': 'Nge7',
            'e4 e5 Nf3 Nc6 Bc4 f5 d4 fxe4 Nxe5 d5 Qh5+ g6 Nxg6 hxg6 Qxg6+ Kd7 Bxd5 Nge7 Qxe4': 'Nxd5',
            'e4 e5 Nf3 Nc6 Bc4 f5 d4 fxe4 Nxe5 d5 Qh5+ g6 Nxg6 hxg6 Qxg6+ Kd7 Bxd5 Nge7 Qxe4 Nxd5 Qxd5+': 'Bd6',
            'e4 e5 Nf3 Nc6 Bc4 f5 d4 fxe4 Nxe5 d5 Bb5': 'Nf6',
        },
        'hints': {
            'e4 e5 Nf3 Nc6 Bc4 f5 d4': [
                'Responde al contraataque central capturando el peón de e4.',
                'El peón de f5 puede tomar el peón central.',
            ],
            'e4 e5 Nf3 Nc6 Bc4 f5 d4 fxe4 Nxe5': [
                'El avance de d7 a d5 ataca el alfil de c4.',
            ],
            'e4 e5 Nf3 Nc6 Bc4 f5 d4 fxe4 Nxe5 d5 Qh5+': [
                'Interpone el peón de g para responder al jaque.',
            ],
        },
    },
]
