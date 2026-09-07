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
                bot.description = bot.description or (
                    f"Rival de entrenamiento de nivel {bot.get_category_display().lower()}."
                )
                bot.save()

        self.stdout.write(self.style.SUCCESS(
            f"Perfiles creados: {profiles_created}. "
            f"Bots creados: {bots_created}, actualizados: {bots_updated}. "
            f"Total bots: {Bot.objects.count()}."
        ))
