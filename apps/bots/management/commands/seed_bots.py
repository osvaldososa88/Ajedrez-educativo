"""
Seeds the training bots: 4 strength profiles per category and 30 bots per
category (90 total). Idempotent: re-running updates profiles/bots by their
natural keys (profile name; category+order) without duplicating anything.

Usage:  python manage.py seed_bots
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.bots.models import Bot, BotProfile

# First bots of each category use these real names (editable later from the
# Django Admin — nothing here is hardwired into views/templates).
REAL_NAMES = [
    'Mateo', 'Benjamin', 'Alexis', 'Gastón', 'JoaquinMataAbuela',
    'Santino', 'Profe Osvaldo', 'Profe Amira',
]

# Per category: (profile name, depth, move_time_ms, skill, multipv, error_p)
PROFILE_TEMPLATES = {
    Bot.Category.BEGINNER: [
        ('Principiante equilibrado', 1, 250, 1, 3, 0.35),
        ('Principiante agresivo', 1, 250, 2, 3, 0.40),
        ('Principiante táctico', 2, 300, 3, 3, 0.30),
        ('Principiante defensivo', 2, 300, 2, 4, 0.35),
    ],
    Bot.Category.INTERMEDIATE: [
        ('Intermedio equilibrado', 5, 500, 8, 3, 0.18),
        ('Intermedio agresivo', 5, 500, 9, 3, 0.20),
        ('Intermedio táctico', 6, 600, 10, 4, 0.15),
        ('Intermedio posicional', 7, 600, 9, 4, 0.15),
    ],
    Bot.Category.ADVANCED: [
        ('Avanzado equilibrado', 10, 800, 14, 3, 0.07),
        ('Avanzado táctico', 11, 800, 15, 4, 0.08),
        ('Avanzado posicional', 12, 900, 15, 4, 0.06),
        ('Avanzado defensivo', 12, 900, 16, 3, 0.05),
    ],
}

CATEGORY_SETUP = {
    # category -> (starting ELO, ELO step, [order -> real name or None])
    Bot.Category.BEGINNER: {
        'start_elo': 700, 'step': 10,
        'names': {1: 'Mateo', 2: 'Benjamin', 3: 'Alexis', 4: 'Gastón',
                  5: 'JoaquinMataAbuela', 6: 'Santino', 7: 'Profe Osvaldo',
                  8: 'Profe Amira'},
        'quotes': {
            1: 'Estoy aprendiendo a defender mis piezas.',
            2: 'Me encanta atacar, a veces sin pensar mucho.',
        },
    },
    Bot.Category.INTERMEDIATE: {
        'start_elo': 1050, 'step': 10,
        'names': {1: 'Mateo', 2: 'Alexis', 3: 'Benjamin', 4: 'Gastón',
                  5: 'Santino', 6: 'Profe Osvaldo', 7: 'Profe Amira',
                  8: 'JoaquinMataAbuela'},
        'quotes': {
            1: 'El año pasado era principiante... ¡mireme ahora!',
            2: 'Calculo variantes antes de mover.',
        },
    },
    Bot.Category.ADVANCED: {
        'start_elo': 1400, 'step': 15,
        'names': {1: 'Profe Amira', 2: 'Mateo', 3: 'Alexis', 4: 'Profe Osvaldo',
                  5: 'Benjamin', 6: 'Santino', 7: 'Gastón',
                  8: 'JoaquinMataAbuela'},
        'quotes': {
            1: 'Les voy a enseñar lo que es el ajedrez de verdad.',
            2: 'Juego posicional y no perdono los errores.',
        },
    },
}

BOTS_PER_CATEGORY = 30


class Command(BaseCommand):
    help = 'Crea/actualiza los perfiles de fuerza y los 90 bots de entrenamiento.'

    @transaction.atomic
    def handle(self, *args, **options):
        profiles_created = 0
        bots_created = 0
        bots_updated = 0

        for category, templates in PROFILE_TEMPLATES.items():
            for name, depth, move_ms, skill, multipv, error_p in templates:
                profile, created = BotProfile.objects.update_or_create(
                    name=name,
                    defaults={
                        'engine_depth': depth,
                        'move_time_ms': move_ms,
                        'skill_level': skill,
                        'multipv': multipv,
                        'error_probability': error_p,
                        'description': f'Perfil de fuerza para {name}.',
                    },
                )
                profiles_created += int(created)

        # --- Seed Openings & Opening Lines ---
        from apps.bots.models import Opening, OpeningLine

        openings_def = [
            {
                'name': 'Apertura Italiana',
                'eco': 'C50',
                'description': 'Desarrollo rápido del alfil a c4 apuntando al peón f7.',
                'line_name': 'Línea Principal Italiana',
                'moves_san': '1.e4 e5 2.Nf3 Nc6 3.Bc4',
                'moves_uci': ['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1c4'],
                'color': OpeningLine.BotColor.WHITE,
            },
            {
                'name': 'Defensa Caro-Kann',
                'eco': 'B10',
                'description': 'Estructura sólida de peones preparando d5.',
                'line_name': 'Variante Caro-Kann',
                'moves_san': '1.e4 c6 2.d4 d5',
                'moves_uci': ['e2e4', 'c7c6', 'd2d4', 'd7d5'],
                'color': OpeningLine.BotColor.BLACK,
            },
            {
                'name': 'Defensa Siciliana',
                'eco': 'B20',
                'description': 'Lucha asimétrica por el centro con c5.',
                'line_name': 'Variante Abierta',
                'moves_san': '1.e4 c5 2.Nf3 d6 3.d4 cxd4',
                'moves_uci': ['e2e4', 'c7c5', 'g1f3', 'd7d6', 'd2d4', 'c5d4'],
                'color': OpeningLine.BotColor.BLACK,
            },
            {
                'name': 'Apertura Ruy López',
                'eco': 'C60',
                'description': 'Presión inmediata sobre el caballo de c6.',
                'line_name': 'Línea Ruy López',
                'moves_san': '1.e4 e5 2.Nf3 Nc6 3.Bb5',
                'moves_uci': ['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1b5'],
                'color': OpeningLine.BotColor.WHITE,
            },
            {
                'name': 'Gambito de Dama',
                'eco': 'D06',
                'description': 'Control posicional del centro con d4 y c4.',
                'line_name': 'Línea Gambito de Dama',
                'moves_san': '1.d4 d5 2.c4',
                'moves_uci': ['d2d4', 'd7d5', 'c2c4'],
                'color': OpeningLine.BotColor.WHITE,
            },
            {
                'name': 'Defensa Francesa',
                'eco': 'C00',
                'description': 'Respuesta sólida con e6 y d5 contra e4.',
                'line_name': 'Línea Francesa',
                'moves_san': '1.e4 e6 2.d4 d5',
                'moves_uci': ['e2e4', 'e7e6', 'd2d4', 'd7d5'],
                'color': OpeningLine.BotColor.BLACK,
            },
            {
                'name': 'Defensa Holandesa',
                'eco': 'A80',
                'description': 'Respuesta agresiva contra 1.d4 buscando control en e4.',
                'line_name': 'Línea Holandesa',
                'moves_san': '1.d4 f5',
                'moves_uci': ['d2d4', 'f7f5'],
                'color': OpeningLine.BotColor.BLACK,
            },
            {
                'name': 'Sistema Colle',
                'eco': 'D05',
                'description': 'Estructura sólida de Blancas con d4, Nf3 y e3.',
                'line_name': 'Línea Sistema Colle',
                'moves_san': '1.d4 d5 2.Nf3 Nf6 3.e3',
                'moves_uci': ['d2d4', 'd7d5', 'g1f3', 'g8f6', 'e2e3'],
                'color': OpeningLine.BotColor.WHITE,
            },
        ]

        created_openings = {}
        for odef in openings_def:
            op, _ = Opening.objects.update_or_create(
                name=odef['name'],
                defaults={'eco': odef['eco'], 'description': odef['description']}
            )
            OpeningLine.objects.update_or_create(
                opening=op,
                name=odef['line_name'],
                defaults={
                    'moves_san': odef['moves_san'],
                    'moves_uci': odef['moves_uci'],
                    'bot_color': odef['color'],
                }
            )
            created_openings[odef['name']] = op

        for category, setup in CATEGORY_SETUP.items():
            profiles = list(BotProfile.objects.filter(
                name__in=[t[0] for t in PROFILE_TEMPLATES[category]]
            ).order_by('name'))
            if not profiles:
                self.stdout.write(self.style.ERROR(
                    f'No hay perfiles para la categoría {category}; ejecutá el comando de nuevo.'
                ))
                continue

            for order in range(1, BOTS_PER_CATEGORY + 1):
                display_name = setup['names'].get(order) or f"Bot {order}"
                elo = setup['start_elo'] + setup['step'] * (order - 1)
                profile = profiles[(order - 1) % len(profiles)]
                quote = setup['quotes'].get(order, '')

                bot = Bot.objects.filter(category=category, order=order).first()
                if bot is None:
                    user = Bot.create_bot_account(display_name)
                    bot = Bot(user=user, category=category, order=order)
                    bots_created += 1
                else:
                    bots_updated += 1

                bot.display_name = display_name
                bot.displayed_elo = elo
                bot.profile = profile
                bot.quote = quote
                bot.opening_mode = Bot.OpeningMode.SPECIFIC_OPENING
                bot.description = bot.description or (
                    f"Rival de entrenamiento de nivel {bot.get_category_display().lower()}."
                )

                if category == Bot.Category.BEGINNER:
                    bot.specific_opening_white = created_openings['Apertura Italiana']
                    bot.specific_opening_black = created_openings['Defensa Caro-Kann']
                elif category == Bot.Category.INTERMEDIATE:
                    bot.specific_opening_white = created_openings['Apertura Ruy López']
                    bot.specific_opening_black = created_openings['Defensa Francesa']
                else:
                    bot.specific_opening_white = created_openings['Gambito de Dama']
                    bot.specific_opening_black = created_openings['Defensa Holandesa']

                bot.save()

                # Assign appropriate openings according to difficulty tier
                if category == Bot.Category.BEGINNER:
                    bot.repertoire_openings.set([
                        created_openings['Apertura Italiana'],
                        created_openings['Defensa Caro-Kann'],
                        created_openings['Sistema Colle']
                    ])
                elif category == Bot.Category.INTERMEDIATE:
                    bot.repertoire_openings.set([
                        created_openings['Apertura Ruy López'],
                        created_openings['Defensa Francesa'],
                        created_openings['Defensa Siciliana'],
                        created_openings['Defensa Holandesa']
                    ])
                else:
                    bot.repertoire_openings.set([
                        created_openings['Gambito de Dama'],
                        created_openings['Defensa Siciliana'],
                        created_openings['Sistema Colle'],
                        created_openings['Defensa Holandesa']
                    ])

        self.stdout.write(self.style.SUCCESS(
            f"Perfiles creados: {profiles_created}. "
            f"Bots creados: {bots_created}, actualizados: {bots_updated}. "
            f"Total bots: {Bot.objects.count()}."
        ))
