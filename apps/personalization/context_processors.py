from .chess_theme_registry import resolve_user_appearance, PIECE_SETS, BOARD_THEMES


def chess_appearance(request):
    """
    Context processor to inject visual chess preferences into all templates.
    """
    user = getattr(request, 'user', None)
    piece_set, board_theme, is_custom = resolve_user_appearance(user)

    return {
        'user_piece_set': piece_set,
        'user_board_theme': board_theme,
        'is_custom_appearance': is_custom,
        'chess_piece_sets': PIECE_SETS,
        'chess_board_themes': BOARD_THEMES,
    }
