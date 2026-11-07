"""
Lecciones de apertura y estrategia (`apps.lessons`).

Una `Lesson` agrupa una familia de apertura (Siciliana, Holandesa, Colle,
Italiana...) y contiene varios `LessonChapter`. Cada capítulo es un "gamebook":
un árbol de variantes exportado desde un estudio de Lichess, que la sesión
interactiva valida y recorre con el tablero.

El árbol de cada capítulo se guarda serializado (`LessonChapter.tree`) en
formato JSON para que el cliente pueda navegarlo sin pedir jugadas al servidor.
"""
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils.text import slugify


class LessonQuerySet(models.QuerySet):
    def published(self):
        return self.filter(is_published=True)


class Lesson(models.Model):
    """Familia de apertura con varios capítulos de teoría."""

    class Color(models.TextChoices):
        DARK = 'DARK', 'Oscuro'
        LIGHT = 'LIGHT', 'Claro'
        MIXED = 'MIXED', 'Mixto'

    class StudentColor(models.TextChoices):
        WHITE = 'white', 'Blancas'
        BLACK = 'black', 'Negras'

    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    eco = models.CharField('Código ECO', max_length=10, blank=True)
    family = models.CharField(
        max_length=60, blank=True,
        help_text='Agrupación para ordenar la rejilla: Siciliana, Holandesa, ...',
    )
    summary = models.TextField('Resumen', blank=True)
    icon = models.CharField('Icono', max_length=8, default='📘')
    color = models.CharField(
        max_length=8, choices=Color.choices, default=Color.DARK,
        help_text='Solo visual: abre la familia como "tipo oscuro/claro" o "mixto".',
    )
    student_color = models.CharField(
        'Color para practicar', max_length=5,
        choices=StudentColor.choices, default=StudentColor.WHITE,
    )
    source_url = models.URLField('Estudio original', blank=True)
    order = models.PositiveIntegerField('Orden', default=0)
    is_published = models.BooleanField('Publicada', default=True)

    objects = LessonQuerySet.as_manager()

    class Meta:
        verbose_name = 'Lección'
        verbose_name_plural = 'Lecciones'
        ordering = ['order', 'title']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:140]
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('lesson_detail', kwargs={'slug': self.slug})


class LessonChapter(models.Model):
    """Un capítulo (= gamebook) dentro de una lección."""

    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE,
        related_name='chapters', verbose_name='Lección',
    )
    title = models.CharField(max_length=180)
    order = models.PositiveIntegerField('Orden', default=0)
    intro = models.TextField(
        'Introducción', blank=True,
        help_text='Comentario inicial del capítulo (texto del autor).',
    )
    start_fen = models.CharField(max_length=100)
    tree = models.JSONField(
        'Árbol de jugadas', default=list, blank=True,
        help_text=(
            'Nodos {san, uci, fen, comment, main, accepted, required, hints, '
            'variations}; raíz = jugadas iniciales.'
        ),
    )
    source_url = models.URLField('Capítulo original', blank=True)

    class Meta:
        verbose_name = 'Capítulo de lección'
        verbose_name_plural = 'Capítulos de lecciones'
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.lesson.title} · {self.title}'

    @property
    def number(self):
        return self.order + 1


class LessonVariantProgress(models.Model):
    """Progreso individual de un alumno en una posición/variante de capítulo."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lesson_variant_progress',
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='variant_progress',
    )
    chapter = models.ForeignKey(
        LessonChapter,
        on_delete=models.CASCADE,
        related_name='variant_progress',
    )
    branch_key = models.TextField(
        help_text='Secuencia UCI que identifica la posición o rama recorrida.',
    )
    attempts = models.PositiveIntegerField(default=0)
    mistakes = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['chapter__order', 'branch_key']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'chapter', 'branch_key'],
                name='lesson_progress_user_chapter_branch_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'lesson', 'completed']),
        ]

    def __str__(self):
        return f'{self.user} · {self.chapter} · {self.branch_key or "inicio"}'
