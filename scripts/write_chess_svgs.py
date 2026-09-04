"""Generate original Staunton-style SVG chess pieces for Ajedrez Escolar."""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "static" / "img" / "pieces"

WHITE = {
    "fill": "#f7f1e4",
    "stroke": "#2f2a24",
    "detail": "#c9b89a",
    "shine": "#ffffff",
}
BLACK = {
    "fill": "#2a2b30",
    "stroke": "#e4d6bb",
    "detail": "#16171b",
    "shine": "#4a4c55",
}

HEAD = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45" role="img">
'''
TAIL = "</svg>\n"


def g(palette, extra=""):
    return (
        f'<g fill="{palette["fill"]}" stroke="{palette["stroke"]}" '
        f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"{extra}>'
    )


def pawn(p):
    return f'''{HEAD}{g(p)}
  <path d="M22.5 9.5c-2.07 0-3.75 1.68-3.75 3.75 0 .92.34 1.76.9 2.4-2.7 1.35-4.65 4.4-4.65 7.85 0 1.55.55 2.95 1.45 4.05C13.3 29.1 11 32 11 35.5h23c0-3.5-2.3-6.4-5.45-7.95.9-1.1 1.45-2.5 1.45-4.05 0-3.45-1.95-6.5-4.65-7.85.56-.64.9-1.48.9-2.4 0-2.07-1.68-3.75-3.75-3.75z"/>
</g>
<ellipse cx="22.5" cy="13.2" rx="2.2" ry="2.1" fill="{p["shine"]}" stroke="none" opacity="0.35"/>
{TAIL}'''


def rook(p):
    return f'''{HEAD}{g(p)}
  <path d="M11 14.5V9.5h4.2v3.2h3.3V9.5h8V12.7h3.3V9.5H34v5"/>
  <path d="M11 14.5h23v4.2H11z"/>
  <path d="M13.2 18.7h18.6v11.6H13.2z"/>
  <path d="M11 30.3h23v3.4H11z"/>
  <path d="M9.5 33.7h26v3.6h-26z"/>
</g>
<path d="M16.2 22.4h12.6" fill="none" stroke="{p["detail"]}" stroke-width="1.2"/>
<path d="M16.2 26.6h12.6" fill="none" stroke="{p["detail"]}" stroke-width="1.2"/>
{TAIL}'''


def knight(p, face_right=True):
    # Original horse-head silhouette; black knights face left by convention.
    path = (
        "M12.2 35.8h21.6c0-3.1-1.5-5.2-3.8-6.4 1.4-1.6 2.4-3.6 2.4-5.8 "
        "0-1.8-.6-3.4-1.6-4.7 2.2-2.6 3.4-5.4 3.2-8.4-.2-2.8-1.8-4.6-4.2-5.2 "
        "-1.9-.5-3.6.1-5 .9-1.1-1.2-2.8-2-4.7-2-2.3 0-4.1.9-5.2 2.4 "
        "C12.4 8.4 10.8 10.6 10 13.4c-.7 2.4-.4 4.8.8 7 1 1.8 1.6 2.6 1.4 4.2 "
        "-.2 1.8-1.5 3-2.6 4.2 1.8.2 3.4 1.1 3.8 2.8.3 1.3-.2 2.4-1.2 3.2z"
    )
    transform = ' transform="translate(45,0) scale(-1,1)"' if not face_right else ""
    eye_fill = p["stroke"]
    return f'''{HEAD}{g(p, transform)}
  <path d="{path}"/>
  <ellipse cx="24.4" cy="14.3" rx="1.15" ry="1.35" fill="{eye_fill}" stroke="none"/>
  <circle cx="29.5" cy="16.1" r="1.05" fill="{eye_fill}" stroke="none"/>
</g>
{TAIL}'''


def bishop(p):
    return f'''{HEAD}{g(p)}
  <path d="M22.5 8.4c1.35 0 2.45 1.1 2.45 2.45S23.85 13.3 22.5 13.3 20.05 12.2 20.05 10.85 21.15 8.4 22.5 8.4z"/>
  <path d="M22.5 13.3c4.8 3.4 8.1 8.4 8.1 13.4 0 3.1-1.7 5.4-4.4 6.6H18.8c-2.7-1.2-4.4-3.5-4.4-6.6 0-5 3.3-10 8.1-13.4z"/>
  <path d="M14.2 33.3h16.6v2.2H14.2z"/>
  <path d="M11.4 35.5h22.2v3.3H11.4z"/>
</g>
<path d="M20.4 18.2l4.4 8.6" fill="none" stroke="{p["stroke"]}" stroke-width="1.4" stroke-linecap="round"/>
<path d="M22.5 16.6v4.4" fill="none" stroke="{p["stroke"]}" stroke-width="1.3" stroke-linecap="round"/>
{TAIL}'''


def queen(p):
    return f'''{HEAD}{g(p)}
  <circle cx="9.6" cy="12.4" r="1.85"/>
  <circle cx="16.05" cy="9.6" r="1.85"/>
  <circle cx="22.5" cy="8.4" r="1.95"/>
  <circle cx="28.95" cy="9.6" r="1.85"/>
  <circle cx="35.4" cy="12.4" r="1.85"/>
  <path d="M9.6 12.4l3.4 11.4h19l3.4-11.4-6.3 6.2-6.6-8.3-6.6 8.3z"/>
  <path d="M13.2 23.8h18.6c.6 3.6-1.2 7.2-4.6 8.7H17.8c-3.4-1.5-5.2-5.1-4.6-8.7z"/>
  <path d="M14.4 32.5h16.2v2.4H14.4z"/>
  <path d="M11.2 34.9h22.6v3.6H11.2z"/>
</g>
<circle cx="22.5" cy="27.2" r="1.6" fill="{p["shine"]}" stroke="{p["stroke"]}" stroke-width="1"/>
{TAIL}'''


def king(p):
    return f'''{HEAD}{g(p)}
  <path d="M20.4 6.2h4.2v2.4h2.5v2.5h-2.5V13.6h-4.2v-2.5h-2.5V8.6h2.5z"/>
  <path d="M12.6 16.4h19.8c.4 1.2.4 2.6 0 3.8H12.6c-.4-1.2-.4-2.6 0-3.8z"/>
  <path d="M14.2 20.2h16.6c1.1 4.6-.6 9.4-4.8 11.6H19c-4.2-2.2-5.9-7-4.8-11.6z"/>
  <path d="M14.6 31.8h15.8v2.5H14.6z"/>
  <path d="M11.2 34.3h22.6v3.7H11.2z"/>
</g>
<path d="M22.5 19.4v8.4" fill="none" stroke="{p["stroke"]}" stroke-width="1.5" stroke-linecap="round"/>
<path d="M18.8 23.6h7.4" fill="none" stroke="{p["stroke"]}" stroke-width="1.5" stroke-linecap="round"/>
{TAIL}'''


PIECES = {
    "wP": pawn(WHITE),
    "bP": pawn(BLACK),
    "wR": rook(WHITE),
    "bR": rook(BLACK),
    "wN": knight(WHITE, face_right=True),
    "bN": knight(BLACK, face_right=False),
    "wB": bishop(WHITE),
    "bB": bishop(BLACK),
    "wQ": queen(WHITE),
    "bQ": queen(BLACK),
    "wK": king(WHITE),
    "bK": king(BLACK),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, svg in PIECES.items():
        (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")
        print(f"wrote {name}.svg")


if __name__ == "__main__":
    main()
