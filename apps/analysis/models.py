import uuid
from django.db import models
from django.conf import settings

class PositionAnalysis(models.Model):
    """
    Cached, reusable position evaluation indexed by FEN.
    Can be reused across puzzles, training, and game analyses.
    """
    fen = models.CharField(max_length=200, db_index=True, unique=True)
    score_cp = models.IntegerField(null=True, blank=True)
    mate_in = models.IntegerField(null=True, blank=True)
    best_move_uci = models.CharField(max_length=10, null=True, blank=True)
    best_move_san = models.CharField(max_length=20, null=True, blank=True)
    pv_san = models.JSONField(default=list)
    depth = models.IntegerField(default=15)
    engine_name = models.CharField(max_length=50, default='Stockfish')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        eval_str = f"{self.score_cp/100:+.2f}" if self.score_cp is not None else f"M{self.mate_in}"
        return f"Position {self.fen[:20]}... | Eval: {eval_str}"

class AnalysisJob(models.Model):
    """
    Tracks non-blocking asynchronous analysis jobs for full games or imported PGNs.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        PROCESSING = 'PROCESSING', 'En Proceso'
        COMPLETED = 'COMPLETED', 'Completado'
        FAILED = 'FAILED', 'Fallido'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey('games.Game', on_delete=models.SET_NULL, null=True, blank=True, related_name='analysis_jobs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='analysis_jobs')
    pgn_text = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    progress_percent = models.IntegerField(default=0)
    target_depth = models.IntegerField(default=12)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Job {self.id.hex[:8]} | Status: {self.status} | User: {self.user.username}"

class MoveAnalysis(models.Model):
    """
    Evaluation of an individual move in a game or PGN analysis job.
    """
    class Quality(models.TextChoices):
        BEST = 'BEST', 'Mejor Movimiento'
        GOOD = 'GOOD', 'Buen Movimiento'
        INACCURACY = 'INACCURACY', 'Inexactitud'
        MISTAKE = 'MISTAKE', 'Error'
        BLUNDER = 'BLUNDER', 'Gran Error'

    job = models.ForeignKey(AnalysisJob, on_delete=models.CASCADE, related_name='move_analyses')
    ply = models.IntegerField()
    move_san = models.CharField(max_length=20)
    move_uci = models.CharField(max_length=10)
    fen_before = models.CharField(max_length=200)
    fen_after = models.CharField(max_length=200)
    position_analysis = models.ForeignKey(PositionAnalysis, on_delete=models.SET_NULL, null=True, blank=True)
    score_cp = models.IntegerField(null=True, blank=True)
    mate_in = models.IntegerField(null=True, blank=True)
    quality = models.CharField(max_length=20, choices=Quality.choices, default=Quality.GOOD)

    class Meta:
        ordering = ['ply']

    def __str__(self):
        return f"Ply {self.ply}: {self.move_san} | Quality: {self.quality}"
