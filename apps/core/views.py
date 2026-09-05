from django.http import HttpResponse
from django.views.decorators.http import require_GET
from django.conf import settings
import os


@require_GET
def service_worker(request):
    """Sirve el Service Worker desde la raíz para que controle toda la app."""
    sw_path = os.path.join(settings.BASE_DIR, 'static', 'sw.js')
    with open(sw_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return HttpResponse(content, content_type='application/javascript; charset=utf-8')


@require_GET
def manifest(request):
    """Sirve el manifest.json desde la raíz."""
    manifest_path = os.path.join(settings.BASE_DIR, 'static', 'manifest.json')
    with open(manifest_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return HttpResponse(content, content_type='application/manifest+json; charset=utf-8')