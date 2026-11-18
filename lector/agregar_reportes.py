"""Valida reportes nuevos y los incorpora a data/reportes.js.

Uso:
    python lector/agregar_reportes.py nuevos.json          # agrega / actualiza
    python lector/agregar_reportes.py --revisar            # solo valida el archivo actual

`nuevos.json` es una lista de reportes con este formato (ver lector/LECTOR.md):
    {"id": "fb-123", "hora": "2026-11-15T21:28:00-06:00", "horaAprox": false,
     "fuente": "usuarios" | "oficial", "tipo": "cierre", "sentido": "1:2" | "2:1" | "ambos" | null,
     "km": 28.0  (o "kmIni"/"kmFin", o nada = todo el Zurquí),
     "origen": "...", "url": "https://...", "original": "cita corta", "simple": "explicación",
     opcionales: "confirmaciones": 3, "motivo": "...", "plan": "...", "alternas": [{"via": "...", "para": "..."}]}

Un reporte con un id que ya existe reemplaza al anterior (sirve para corregir).
Los reportes de más de DIAS_HISTORIAL días se eliminan.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / "data" / "reportes.js"
DIAS_HISTORIAL = 7
KM_MIN, KM_MAX = 0.0, 62.5
TIPOS = {"cierre", "reapertura", "regulado", "derrumbe", "accidente", "clima", "presa", "varado", "obras", "normal"}
FUENTES = {"usuarios", "oficial", "medios"}
SENTIDOS = {"1:2", "2:1", "ambos", None}
CAMPOS = ["id", "hora", "horaAprox", "fuente", "tipo", "km", "kmIni", "kmFin", "sentido", "origen", "url", "original", "simple",
          "confirmaciones", "motivo", "plan", "alternas"]
CABECERA = """// Reportes de la ruta. Lo escribe lector/agregar_reportes.py: no editar a mano
// (para corregir un reporte, volver a pasarlo por el script con el mismo id).
//
// fuente:  "usuarios" (rápido, sin confirmar) · "oficial" (MOPT, Conavi, Tránsito) · "medios" (noticias que replican avisos)
// tipo:    cierre · reapertura · regulado · derrumbe · accidente · clima · presa · varado · obras · normal
// km / kmIni+kmFin: ubicación sobre la ruta; sin ninguno = todo el Zurquí (peaje – Cruce de Río Frío)
// sentido: "1:2" (San José → Limón) · "2:1" (Limón → San José) · "ambos" · null
// No se guardan nombres de quienes publican: solo el contenido del reporte y el enlace a la fuente.
"""


def leer_actual():
    if not ARCHIVO.exists():
        return []
    texto = ARCHIVO.read_text(encoding="utf-8")
    m = re.search(r"window\.R32_REPORTES\s*=\s*(\[.*\])\s*;", texto, re.S)
    if not m:
        raise SystemExit("No encuentro window.R32_REPORTES en data/reportes.js")
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise SystemExit(f"data/reportes.js no es JSON válido ({e}). Hay que corregirlo a mano antes de seguir.")


def validar(r):
    """Devuelve la lista de problemas de un reporte (vacía si está bien)."""
    p = []
    if not isinstance(r.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", r["id"]):
        p.append("id ausente o con caracteres raros")
    try:
        h = datetime.fromisoformat(r.get("hora", ""))
        if h.tzinfo is None:
            p.append("hora sin zona horaria (usar -06:00)")
        elif h > datetime.now(timezone.utc) + timedelta(minutes=10):
            p.append("hora en el futuro")
    except (TypeError, ValueError):
        p.append("hora no es una fecha ISO")
    if r.get("fuente") not in FUENTES:
        p.append(f"fuente debe ser una de {sorted(FUENTES)}")
    if r.get("tipo") not in TIPOS:
        p.append(f"tipo debe ser uno de {sorted(TIPOS)}")
    if r.get("sentido") not in SENTIDOS:
        p.append('sentido debe ser "1:2", "2:1", "ambos" o null')
    for k in ("km", "kmIni", "kmFin"):
        if k in r and r[k] is not None and not (isinstance(r[k], (int, float)) and KM_MIN <= r[k] <= KM_MAX):
            p.append(f"{k} fuera de la ruta ({KM_MIN}–{KM_MAX})")
    if ("kmIni" in r) != ("kmFin" in r):
        p.append("kmIni y kmFin van juntos")
    elif "kmIni" in r and isinstance(r["kmIni"], (int, float)) and isinstance(r["kmFin"], (int, float)) and r["kmIni"] >= r["kmFin"]:
        p.append("kmIni debe ser menor que kmFin")
    if "km" in r and "kmIni" in r:
        p.append("usar km o kmIni/kmFin, no ambos")
    for k, largo in (("origen", 120), ("original", 200), ("simple", 600)):
        if not isinstance(r.get(k), str) or not r[k].strip():
            p.append(f"falta {k}")
        elif len(r[k]) > largo:
            p.append(f"{k} demasiado largo (máx. {largo})")
    if not isinstance(r.get("url"), str) or not r["url"].startswith("https://"):
        p.append("url debe empezar con https://")
    # campos opcionales de un cierre: por qué se cerró, qué va a hacer la autoridad y por dónde pasar
    for k, largo in (("motivo", 120), ("plan", 240)):
        if k in r and (not isinstance(r[k], str) or not r[k].strip() or len(r[k]) > largo):
            p.append(f"{k} debe ser un texto de hasta {largo} caracteres")
    if "alternas" in r:
        a = r["alternas"]
        if not isinstance(a, list) or not a or len(a) > 4 or not all(
                isinstance(x, dict) and set(x) == {"via", "para"} and all(isinstance(v, str) and 0 < len(v) <= 80 for v in x.values()) for x in a):
            p.append('alternas debe ser una lista de hasta 4 elementos {"via": "...", "para": "..."}')
    if "confirmaciones" in r and not (isinstance(r["confirmaciones"], int) and 1 <= r["confirmaciones"] <= 500):
        p.append("confirmaciones debe ser un número entero")
    extra = set(r) - set(CAMPOS)
    if extra:
        p.append(f"campos no reconocidos: {sorted(extra)}")
    return p


def escribir(reportes):
    reportes.sort(key=lambda r: datetime.fromisoformat(r["hora"]), reverse=True)
    lineas = ",\n".join("  " + json.dumps({k: r[k] for k in CAMPOS if k in r}, ensure_ascii=False) for r in reportes)
    generado = datetime.now(timezone(timedelta(hours=-6))).isoformat(timespec="seconds")
    ARCHIVO.write_text(f'{CABECERA}window.R32_ACTUALIZADO = "{generado}";\nwindow.R32_REPORTES = [\n{lineas}\n];\n', encoding="utf-8", newline="\n")


def main():
    actual = leer_actual()
    if len(sys.argv) == 2 and sys.argv[1] == "--revisar":
        malos = {r.get("id", "?"): validar(r) for r in actual if validar(r)}
        print(f"{len(actual)} reportes; {len(malos)} con problemas")
        for i, p in malos.items():
            print(f"  {i}: {'; '.join(p)}")
        sys.exit(1 if malos else 0)
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    nuevos = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if not isinstance(nuevos, list):
        raise SystemExit("El archivo debe contener una lista de reportes")
    errores = {r.get("id", f"#{i}"): validar(r) for i, r in enumerate(nuevos) if validar(r)}
    if errores:
        print("No se agregó nada. Corregir primero:")
        for i, p in errores.items():
            print(f"  {i}: {'; '.join(p)}")
        sys.exit(1)
    agregados, actualizados, eliminados, total = incorporar(nuevos)
    print(f"{agregados} nuevos, {actualizados} actualizados, {eliminados} vencidos o descartados eliminados; total {total}")


def incorporar(nuevos, descartar=()):
    """Agrega o reemplaza reportes (ya validados) y quita los de `descartar`. También lo usa el bot.
    Devuelve (agregados, actualizados, eliminados, total)."""
    actual = leer_actual()
    por_id = {r["id"]: r for r in actual}
    agregados = sum(1 for r in nuevos if r["id"] not in por_id)
    por_id.update({r["id"]: r for r in nuevos})
    for i in descartar:
        por_id.pop(i, None)
    limite = datetime.now(timezone.utc) - timedelta(days=DIAS_HISTORIAL)
    # el último aviso confiable de cierre o reapertura se conserva aunque sea viejo: define el estado de la ruta
    estado = [r for r in por_id.values() if r["fuente"] != "usuarios" and r["tipo"] in ("cierre", "reapertura", "normal")]
    ancla = max(estado, key=lambda r: datetime.fromisoformat(r["hora"]))["id"] if estado else None
    vigentes = [r for r in por_id.values() if datetime.fromisoformat(r["hora"]) >= limite or r["id"] == ancla]
    escribir(vigentes)
    return agregados, len(nuevos) - agregados, len(actual) + agregados - len(vigentes), len(vigentes)


if __name__ == "__main__":
    main()
