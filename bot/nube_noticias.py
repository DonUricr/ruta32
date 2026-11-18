"""Lector de noticias para la nube (GitHub Actions): actualiza data/noticias.js, un archivo aparte de
data/reportes.js para que la nube y la computadora nunca editen el mismo archivo. La página junta ambos.

Imprime "cambios" si el archivo cambió (el flujo de GitHub solo publica en ese caso)."""
import json
import re
from datetime import datetime, timedelta

from comun import DATOS, ahora
from noticias import reportes_de_noticias

ARCHIVO = DATOS / "noticias.js"
DIAS = 7


def leer():
    if not ARCHIVO.exists():
        return []
    m = re.search(r"window\.R32_NOTICIAS\s*=\s*(\[.*\])\s*;", ARCHIVO.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1)) if m else []


def main():
    actuales = {r["id"]: r for r in leer()}
    nuevos, errores = reportes_de_noticias(horas=12)
    for e in errores:
        print("aviso:", e)
    for r in nuevos:
        if r["id"] in actuales:
            r["hora"] = actuales[r["id"]]["hora"]  # la primera hora vista se conserva
        actuales[r["id"]] = r
    limite = ahora() - timedelta(days=DIAS)
    lista = sorted((r for r in actuales.values() if datetime.fromisoformat(r["hora"]) >= limite),
                   key=lambda r: r["hora"], reverse=True)
    lineas = ",\n".join("  " + json.dumps(r, ensure_ascii=False, sort_keys=True) for r in lista)
    contenido = ("// Noticias sobre la Ruta 32 en el Zurquí. Lo escribe bot/nube_noticias.py (GitHub Actions).\n"
                 f"window.R32_NOTICIAS = [\n{lineas}\n];\n")
    anterior = ARCHIVO.read_text(encoding="utf-8") if ARCHIVO.exists() else ""
    if contenido != anterior:
        ARCHIVO.write_text(contenido, encoding="utf-8", newline="\n")
        print("cambios")
    else:
        print("sin cambios")


if __name__ == "__main__":
    main()
