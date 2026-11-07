import chess
from django.db import migrations


OLD_SICILIAN_FEN = (
    'rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1'
)
OLD_DUTCH_FEN = (
    'rnbqkbnr/ppppp1pp/8/5p2/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 2'
)


def _opening_tree(moves, required_black_move):
    board = chess.Board()
    tree = []
    candidates = tree
    for san in moves:
        move = board.parse_san(san)
        next_board = board.copy()
        next_board.push(move)
        node = {
            'san': san,
            'uci': move.uci(),
            'fen': next_board.fen(),
            'comment': '',
            'main': True,
            'accepted': True,
            'required': san == required_black_move,
            'hints': [],
            'variations': [],
        }
        candidates.append(node)
        board.push(move)
        candidates = node['variations']
    return tree


def make_black_opening_intros_playable(apps, schema_editor):
    LessonChapter = apps.get_model('lessons', 'LessonChapter')
    openings = (
        ('siciliana-enigmatica', ['e4', 'c5'], 'c5'),
        ('holandesa-enigmatica', ['d4', 'f5'], 'f5'),
    )
    for slug, moves, required_move in openings:
        chapter = LessonChapter.objects.filter(
            lesson__slug=slug,
            order=0,
        ).first()
        if chapter:
            chapter.start_fen = chess.STARTING_FEN
            chapter.tree = _opening_tree(moves, required_move)
            chapter.save(update_fields=['start_fen', 'tree'])


def restore_noninteractive_intros(apps, schema_editor):
    LessonChapter = apps.get_model('lessons', 'LessonChapter')
    old_positions = {
        'siciliana-enigmatica': OLD_SICILIAN_FEN,
        'holandesa-enigmatica': OLD_DUTCH_FEN,
    }
    for slug, fen in old_positions.items():
        chapter = LessonChapter.objects.filter(
            lesson__slug=slug,
            order=0,
        ).first()
        if chapter:
            chapter.start_fen = fen
            chapter.tree = []
            chapter.save(update_fields=['start_fen', 'tree'])


class Migration(migrations.Migration):

    dependencies = [
        ('lessons', '0005_default_black_for_sicilian_and_dutch'),
    ]

    operations = [
        migrations.RunPython(
            make_black_opening_intros_playable,
            restore_noninteractive_intros,
        ),
    ]
