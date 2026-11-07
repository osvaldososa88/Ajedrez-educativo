from django.db import migrations


def set_default_student_colors(apps, schema_editor):
    Lesson = apps.get_model('lessons', 'Lesson')
    Lesson.objects.filter(
        slug__in=('siciliana-enigmatica', 'holandesa-enigmatica'),
    ).update(student_color='black')


def restore_default_student_colors(apps, schema_editor):
    Lesson = apps.get_model('lessons', 'Lesson')
    Lesson.objects.filter(
        slug__in=('siciliana-enigmatica', 'holandesa-enigmatica'),
    ).update(student_color='white')


class Migration(migrations.Migration):

    dependencies = [
        ('lessons', '0004_lesson_student_color'),
    ]

    operations = [
        migrations.RunPython(
            set_default_student_colors,
            restore_default_student_colors,
        ),
    ]
