"""
Opening Book Service for Ajedrez Educativo.

Handles matching current game move history against configured opening lines/repertoires.
Detects user deviations immediately and passes control to Stockfish seamlessly while
strictly validating move legality.
"""
import logging
import chess
from .models import Bot, OpeningLine

logger = logging.getLogger(__name__)


class OpeningBookService:
    @classmethod
    def get_opening_move(cls, bot: Bot, game_moves_uci: list, board: chess.Board) -> str:
        """
        Determines if the bot has an opening move configured for the current position.

        Args:
            bot: The Bot instance.
            game_moves_uci: List of UCI moves played so far in the game (e.g. ['e2e4', 'c7c5']).
            board: python-chess Board representing the current position.

        Returns:
            UCI move string (e.g. 'g1f3') if in opening book; None if out of book / deviated.
        """
        if not bot or bot.opening_mode == Bot.OpeningMode.PURE_STOCKFISH:
            return None

        bot_turn_color = 'WHITE' if board.turn == chess.WHITE else 'BLACK'

        # Determine active openings
        openings = []
        specific_op = bot.specific_opening_white if board.turn == chess.WHITE else bot.specific_opening_black
        if specific_op and specific_op.is_active:
            openings.append(specific_op)

        if bot.opening_mode == Bot.OpeningMode.REPERTOIRE or not openings:
            for rep_op in bot.repertoire_openings.filter(is_active=True):
                if rep_op not in openings:
                    openings.append(rep_op)

        if not openings:
            return None

        current_ply = len(game_moves_uci)

        for opening in openings:
            lines = opening.lines.filter(is_active=True).order_by('-priority', 'id')
            for line in lines:
                # Filter by bot color if specified
                if line.bot_color != OpeningLine.BotColor.ANY:
                    if line.bot_color != bot_turn_color:
                        continue

                moves_list = line.moves_uci or []
                if not isinstance(moves_list, list) or len(moves_list) <= current_ply:
                    continue

                # Check prefix matching: did previous moves match this opening line?
                if moves_list[:current_ply] == game_moves_uci:
                    next_uci = moves_list[current_ply]
                    try:
                        next_move = chess.Move.from_uci(next_uci)
                        if next_move in board.legal_moves:
                            logger.info(
                                "Opening Book MATCH: bot=%s, opening=%s, line=%s, move=%s",
                                bot.display_name, opening.name, line.name, next_uci
                            )
                            return next_uci
                    except ValueError:
                        continue

        logger.info(
            "Opening Book DEVIATION / Out of book: bot=%s, ply=%s. Passing control to Stockfish.",
            bot.display_name, current_ply
        )
        return None
