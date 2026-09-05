"""Genera los iconos PNG para la PWA."""
from PIL import Image, ImageDraw
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(BASE_DIR, 'static', 'img')

def draw_pawn_icon(size):
    """Dibuja el icono del peón de ajedrez."""
    img = Image.new('RGBA', (size, size), (15, 23, 42, 255))  # #0f172a
    draw = ImageDraw.Draw(img)

    # Borde redondeado
    radius = int(size * 0.19)
    draw.rounded_rectangle([0, 0, size-1, size-1], radius=radius, fill=(15, 23, 42, 255), outline=(59, 130, 246, 255), width=max(2, size // 64))

    # Escala relativa
    s = size / 512.0
    cx = size / 2
    cy = size / 2

    # Base del peón
    base_y = cy + 120 * s
    base_rx = 80 * s
    base_ry = 20 * s
    draw.ellipse([cx - base_rx, base_y - base_ry, cx + base_rx, base_y + base_ry], fill=(248, 250, 252, 255))

    # Rectángulo base
    rect_top = cy + 80 * s
    rect_bottom = cy + 120 * s
    rect_left = cx - 60 * s
    rect_right = cx + 60 * s
    draw.rounded_rectangle([rect_left, rect_top, rect_right, rect_bottom], radius=8 * s, fill=(248, 250, 252, 255))

    # Cuerpo del peón
    body_points = [
        (cx - 35 * s, cy + 80 * s),
        (cx - 20 * s, cy + 20 * s),
        (cx - 20 * s, cy - 20 * s),
        (cx - 20 * s, cy - 20 * s),
        (cx - 20 * s, cy - 60 * s),
        (cx + 20 * s, cy - 60 * s),
        (cx + 20 * s, cy - 20 * s),
        (cx + 20 * s, cy + 20 * s),
        (cx + 35 * s, cy + 80 * s),
    ]
    draw.polygon(body_points, fill=(248, 250, 252, 255))

    # Cabeza del peón
    head_r = 30 * s
    draw.ellipse([cx - head_r, cy - 70 * s - head_r, cx + head_r, cy - 70 * s + head_r], fill=(248, 250, 252, 255))

    # Detalle azul en la cabeza
    detail_r = 12 * s
    draw.ellipse([cx - detail_r, cy - 70 * s - detail_r, cx + detail_r, cy - 70 * s + detail_r], fill=(59, 130, 246, 255))

    return img

def main():
    os.makedirs(IMG_DIR, exist_ok=True)

    # Icono 192x192
    icon_192 = draw_pawn_icon(192)
    icon_192.save(os.path.join(IMG_DIR, 'pwa-icon-192.png'), 'PNG')
    print(f"Generado: pwa-icon-192.png")

    # Icono 512x512
    icon_512 = draw_pawn_icon(512)
    icon_512.save(os.path.join(IMG_DIR, 'pwa-icon-512.png'), 'PNG')
    print(f"Generado: pwa-icon-512.png")

    # Icono maskable 512x512 (con más padding para safe zone)
    maskable = Image.new('RGBA', (512, 512), (15, 23, 42, 255))
    draw = ImageDraw.Draw(maskable)
    draw.rounded_rectangle([0, 0, 511, 511], radius=96, fill=(15, 23, 42, 255))
    # Dibujar el peón más pequeño para el área segura
    s = 512 / 512.0 * 0.7  # 70% del tamaño para safe zone
    cx = 256
    cy = 256

    # Base del peón
    base_y = cy + 120 * s
    base_rx = 80 * s
    base_ry = 20 * s
    draw.ellipse([cx - base_rx, base_y - base_ry, cx + base_rx, base_y + base_ry], fill=(248, 250, 252, 255))

    # Rectángulo base
    rect_top = cy + 80 * s
    rect_bottom = cy + 120 * s
    rect_left = cx - 60 * s
    rect_right = cx + 60 * s
    draw.rounded_rectangle([rect_left, rect_top, rect_right, rect_bottom], radius=8 * s, fill=(248, 250, 252, 255))

    # Cuerpo del peón
    body_points = [
        (cx - 35 * s, cy + 80 * s),
        (cx - 20 * s, cy + 20 * s),
        (cx - 20 * s, cy - 20 * s),
        (cx - 20 * s, cy - 20 * s),
        (cx - 20 * s, cy - 60 * s),
        (cx + 20 * s, cy - 60 * s),
        (cx + 20 * s, cy - 20 * s),
        (cx + 20 * s, cy + 20 * s),
        (cx + 35 * s, cy + 80 * s),
    ]
    draw.polygon(body_points, fill=(248, 250, 252, 255))

    # Cabeza del peón
    head_r = 30 * s
    draw.ellipse([cx - head_r, cy - 70 * s - head_r, cx + head_r, cy - 70 * s + head_r], fill=(248, 250, 252, 255))

    # Detalle azul en la cabeza
    detail_r = 12 * s
    draw.ellipse([cx - detail_r, cy - 70 * s - detail_r, cx + detail_r, cy - 70 * s + detail_r], fill=(59, 130, 246, 255))

    maskable.save(os.path.join(IMG_DIR, 'pwa-icon-maskable.png'), 'PNG')
    print(f"Generado: pwa-icon-maskable.png")

if __name__ == '__main__':
    main()