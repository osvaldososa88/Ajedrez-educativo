"""
Central Registry for Chess Piece Sets and Board Themes.
Handles options, metadata, previews, and 3-level fallback priority:
  1. UserPreference (if authenticated, custom choice saved, and customization allowed)
  2. GlobalChessConfig (admin default in database)
  3. Safe Code Fallback ('staunton' / 'classic')
"""

PIECE_SETS = [
    {
        'id': 'staunton',
        'name': 'Staunton 3D Clásico',
        'description': 'Diseño tradicional Staunton con sombras suavemente esculpidas.',
        'path': 'img/pieces/staunton/',
        'preview_pieces': ['wK', 'wQ', 'wN', 'bK', 'bQ', 'bN']
    },
    {
        'id': 'cburnett',
        'name': 'Cburnett Vector',
        'description': 'Diseño plano y minimalista ampliamente utilizado en plataformas modernas.',
        'path': 'img/pieces/cburnett/',
        'preview_pieces': ['wK', 'wQ', 'wN', 'bK', 'bQ', 'bN']
    },
    {
        'id': 'merida',
        'name': 'Mérida Tradicional',
        'description': 'Estilo clásico con trazos refinados y excelente contraste.',
        'path': 'img/pieces/merida/',
        'preview_pieces': ['wK', 'wQ', 'wN', 'bK', 'bQ', 'bN']
    },
    {
        'id': 'alpha',
        'name': 'Alpha Vintage',
        'description': 'Estilo atemporal retro con siluetas muy nítidas.',
        'path': 'img/pieces/alpha/',
        'preview_pieces': ['wK', 'wQ', 'wN', 'bK', 'bQ', 'bN']
    }
]

BOARD_THEMES = [
    {
        'id': 'classic',
        'name': 'Azul Acero Clásico',
        'light_color': '#e8edf2',
        'dark_color': '#6884ab',
        'frame_color': '#2a3547',
        'highlight_selected': 'rgba(232, 176, 64, 0.45)',
        'highlight_last': 'rgba(214, 177, 70, 0.48)'
    },
    {
        'id': 'wood_green',
        'name': 'Madera Verde Bosque',
        'light_color': '#ead7b2',
        'dark_color': '#5f7a56',
        'frame_color': '#3d4a42',
        'highlight_selected': 'rgba(232, 176, 64, 0.45)',
        'highlight_last': 'rgba(214, 177, 70, 0.48)'
    },
    {
        'id': 'walnut_brown',
        'name': 'Nogal Cálido',
        'light_color': '#f0d9b5',
        'dark_color': '#b58863',
        'frame_color': '#53382c',
        'highlight_selected': 'rgba(232, 176, 64, 0.45)',
        'highlight_last': 'rgba(214, 177, 70, 0.48)'
    },
    {
        'id': 'dark_slate',
        'name': 'Pizarra Oscura',
        'light_color': '#cfd8dc',
        'dark_color': '#455a64',
        'frame_color': '#1c272c',
        'highlight_selected': 'rgba(232, 176, 64, 0.45)',
        'highlight_last': 'rgba(214, 177, 70, 0.48)'
    },
    {
        'id': 'purple',
        'name': 'Violeta Místico',
        'light_color': '#e2d5f8',
        'dark_color': '#705494',
        'frame_color': '#3a2356',
        'highlight_selected': 'rgba(232, 176, 64, 0.45)',
        'highlight_last': 'rgba(214, 177, 70, 0.48)'
    }
]

VALID_PIECE_SETS = {ps['id'] for ps in PIECE_SETS}
VALID_BOARD_THEMES = {bt['id'] for bt in BOARD_THEMES}

DEFAULT_PIECE_SET = 'staunton'
DEFAULT_BOARD_THEME = 'classic'


def get_piece_set_choices():
    return [(ps['id'], ps['name']) for ps in PIECE_SETS]


def get_board_theme_choices():
    return [(bt['id'], bt['name']) for bt in BOARD_THEMES]


def resolve_user_appearance(user=None):
    """
    Returns (piece_set_id, board_theme_id, is_custom) applying fallback chain.
    """
    from .models import GlobalChessConfig, UserAppearancePreference

    global_config = GlobalChessConfig.get_solo()
    admin_piece_set = global_config.default_piece_set if global_config.default_piece_set in VALID_PIECE_SETS else DEFAULT_PIECE_SET
    admin_board_theme = global_config.default_board_theme if global_config.default_board_theme in VALID_BOARD_THEMES else DEFAULT_BOARD_THEME
    allow_customization = global_config.allow_player_customization

    if user and user.is_authenticated and allow_customization:
        try:
            pref = user.appearance_preference
            user_piece = pref.piece_set if pref.piece_set in VALID_PIECE_SETS else None
            user_theme = pref.board_theme if pref.board_theme in VALID_BOARD_THEMES else None

            if user_piece and user_theme:
                return user_piece, user_theme, True
        except UserAppearancePreference.DoesNotExist:
            pass

    return admin_piece_set, admin_board_theme, False
