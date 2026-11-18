"""Piezas compartidas del bot: rutas, hora de Costa Rica, texto normalizado, lugares de la ruta y
acceso a los reportes (reutiliza lector/agregar_reportes.py)."""
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BOT = RAIZ / "bot"
DATOS = RAIZ / "data"
CR = timezone(timedelta(hours=-6))  # Costa Rica no tiene horario de verano

sys.path.insert(0, str(RAIZ / "lector"))
import agregar_reportes as almacen  # noqa: E402  (validar, leer_actual, incorporar)


def ahora():
    return datetime.now(CR)


def iso(dt):
    return dt.astimezone(CR).isoformat(timespec="seconds")


def norm(texto):
    """minúsculas, sin tildes y con espacios simples: para comparar con reglas."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def coma(km):
    return f"{km:.1f}".replace(".", ",").replace(",0", "")


# ── lugares: salen de data/sectores.js, exportados a data/lugares.json por bot/exportar_lugares.py
def cargar_lugares():
    archivo = DATOS / "lugares.json"
    fuente = DATOS / "sectores.js"
    if not archivo.exists() or archivo.stat().st_mtime < fuente.stat().st_mtime:
        try:
            from exportar_lugares import exportar
            exportar()
        except Exception as e:  # sin navegador (por ejemplo, en la nube): se usa el archivo que haya
            if not archivo.exists():
                raise SystemExit(f"Falta data/lugares.json y no se pudo generar: {e}")
    return json.loads(archivo.read_text(encoding="utf-8"))
