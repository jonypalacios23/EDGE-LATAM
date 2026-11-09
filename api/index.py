from __future__ import annotations

import sys
from pathlib import Path

from fastapi.responses import HTMLResponse


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from backend.main import app


@app.get("/", include_in_schema=False)
def pagina_principal() -> HTMLResponse:
    ruta_html = ROOT_DIR / "frontend" / "index.html"
    try:
        contenido = ruta_html.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        contenido = (
            "<!doctype html><html lang=\"es\"><meta charset=\"utf-8\">"
            "<title>EDGE LATAM</title><h1>Lista de Hoy - EDGE LATAM</h1></html>"
        )
    return HTMLResponse(
        content=contenido,
        headers={"Cache-Control": "no-store"},
    )
