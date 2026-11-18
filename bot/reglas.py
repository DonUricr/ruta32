"""Traductor por reglas (sin inteligencia artificial): convierte publicaciones del grupo, avisos del
MOPT y noticias en reportes con el formato de data/reportes.js.

Es conservador a propósito: ante la duda no genera reporte. Lo que se le escape lo puede afinar
el análisis con Claude en modo emergencia."""
import hashlib
import re
from datetime import datetime, timedelta

from comun import CR, coma, norm

GRUPO = "Grupo “Ruta 32 y su Estado Original”"
URL_GRUPO = "https://www.facebook.com/groups/ruta32ysuestadooficial/"
URL_MOPT = "https://www.facebook.com/MOPTcostarica/"

# ── qué pasa: (tipo, expresión). El orden es la prioridad cuando un mensaje dice varias cosas.
TIPOS = [
    ("cierre", r"\b(cerrad[oa]s?|serrad[oa]|cerraron|cierran|(acaban? de|van a|volvieron a) cerrar|cierre (total|preventivo|del paso|de la (ruta|via|32))|no hay paso|sin paso|no (estan )?dejan? (pasar|entrar))\b|\bcierre\b"),
    ("reapertura", r"\b(ya )?(abrieron|habrieron|reabr\w+|habilitad[oa]|se (procede a la )?apertura|apertura de la ruta|ya hay paso|ya (esta|estan) (abierto|pasando)|paso libre|ya se puede pasar)\b"),
    ("regulado", r"\b(paso regulado|regulando el paso|un (solo )?carril (habilitado|abierto)|solo (un|1) carril|paso alterno)\b"),
    ("accidente", r"\b(accidente|choque|chocaron|colision|coalicion|volco|volcado|volcamiento|se fue al guindo|cayo al guindo|prensad[oa]s?|atropell\w+)\b"),
    ("derrumbe", r"\b(derrumbe|deslizamiento|desprendimiento|caida de material|cayo material|cae material|cayendo material|material en la (via|carretera|calle|calzada)|piedras en la (via|carretera|calle)|terraplen|arbol (caido|en (la )?via))\b"),
    ("varado", r"\b(varad[oa]s?)\b"),
    ("presa", r"\b(presa|preson|presas|pegad[oa]|transito (lento|detenido)|tortuguismo|fila de)\b"),
    ("clima", r"\b(neblina|niebla|aguacero|llueve|lloviendo|mucha lluvia|lluvia fuerte|fuertes lluvias)\b"),
    ("normal", r"\b(despejad[oa]|fluid[oa]|todo bien|sin problemas|excelentes condiciones|buenas condiciones|perfectas condiciones|lind[oa]|limpi[oa]|(acabo|acabamos) de (pasar|subir|bajar)|ya pas(e|amos)|pasamos)\b"),
]
NEGADO = r"\bno (esta|estaba|estan|hay|habia|hubo|tiene) (\w+ ){0,2}"
PREGUNTA = re.compile(r"^(alguien|alguno|como (esta|se encuentra)|que tal|hay paso|esta (abierto|cerrado)|sigue|saben|sabe|me pueden|podrian|buen[oa]s? (dias|tardes|noches)[,!. ]+(alguien|como|me|que))|\?\s*$")
FUERA = re.compile(r"\b(siquirres|guacimo|matina|moin|limon centro|batan|pocora|jimenez|cariari|liverpool|pacuare|rio hondo|bomba santa clara|doña lela|dona lela|tibas|santo domingo)\b")
ZURQUI = re.compile(r"\b(zurqu|cerro|tunel|braulio|peaje|sucio|montana|sustos|descanso|chupadero|ventanas?|teleferico|quebrada gonzalez|hondura|ruta 32|la 32|#32)")

FRASE = {"cierre": "que el paso está cerrado", "reapertura": "que ya hay paso", "regulado": "paso regulado",
         "accidente": "un accidente", "derrumbe": "caída de material", "varado": "un vehículo varado",
         "presa": "presa", "clima": "lluvia o neblina", "normal": "que el paso está despejado"}
SENTIDO_TXT = {"1:2": "sentido San José → Limón", "2:1": "sentido Limón → San José", "ambos": "en ambos sentidos"}


def clasificar(t):
    """Devuelve el tipo principal de un texto normalizado, o None."""
    limpio = re.sub(NEGADO + r"(cerrad\w*|presa|neblina|lluvia|varad\w*|accidente\w*)", " ", t)
    # "poca neblina", "llovizna leve" o "sin lluvia" no cuentan como mal clima
    limpio = re.sub(r"\b(poca|poco|leve|algo de|un poco de|sin) (neblina|lluvia|llovizna)\b", " ", limpio)
    limpio = re.sub(r"\bno (hay|habia|hubo) (\w+ )?(presa|neblina|lluvia|varados?|accidentes?)\b", " despejado ", limpio)
    for tipo, patron in TIPOS:
        if re.search(patron, limpio):
            return tipo
    return None


def es_pregunta(t):
    return bool(PREGUNTA.search(t)) and not re.search(r"\b(acabo de pasar|acabamos de pasar|vengo|recien pas|ya pas|reporte)\b", t)


def _num(s):
    return float(s.replace(",", "."))


def ubicar(t, lugares):
    """Devuelve {"km": x} o {"kmIni": a, "kmFin": b} y el nombre del lugar (o None)."""
    rango = re.search(r"\b(?:km|kms|kilometros?|kl|klm)\.?\s*(\d{1,2}(?:[.,]\d)?)\s*(?:al|a|y|-|hasta( el)?)\s*(?:km\s*)?(\d{1,2}(?:[.,]\d)?)\b", t)
    if rango:
        a, b = sorted((_num(rango.group(1)), _num(rango.group(3))))
        if 0 < a < b <= 62:
            return {"kmIni": a, "kmFin": b}, None
    lista = re.search(r"\bkilometros? ((?:\d{1,2}(?:[.,]\d)?(?:, | y |,| ))+\d{1,2}(?:[.,]\d)?)", t)
    if lista:
        nums = sorted(_num(n) for n in re.findall(r"\d{1,2}(?:[.,]\d)?", lista.group(1)))
        if nums and 0 < nums[0] and nums[-1] <= 62 and len(nums) > 1:
            return {"kmIni": nums[0], "kmFin": nums[-1]}, None
    uno = re.search(r"\b(?:km|kilometro|kl|klm|k)\.?\s*(\d{1,2}(?:[.,]\d)?)\b", t)
    if uno and 0 < _num(uno.group(1)) <= 62:
        return {"km": _num(uno.group(1))}, None
    tunel = re.search(r"(\d+(?:[.,]\d)?|un|una|1)\s*(km|kilometros?|kms)\s*(antes|despues|abajo|pasando)?\s*(del|de la|el)?\s*tunel", t)
    if tunel:
        d = 1.0 if tunel.group(1) in ("un", "una") else _num(tunel.group(1))
        if d <= 20:
            km = 19.8 - d if tunel.group(3) == "antes" or re.search(r"(hacia|sentido|para) (san jose|sj|chepe)", t) and not tunel.group(3) else 20.4 + d
            return {"km": round(km, 1)}, "túnel Zurquí"
    for l in lugares:
        patron = re.sub(r"^(el|la|los|las) ", "", l["patron"])
        if re.search(r"\b" + re.escape(patron) + r"\b", t):
            return ({"km": l["km"]} if "km" in l else {"kmIni": l["kmIni"], "kmFin": l["kmFin"]}), l["nombre"]
    if re.search(r"\bdescanso\b", t) and not re.search(r"\bprimer descanso\b", t):
        return {"km": 30.3}, "Descanso Largo"
    if re.search(r"\btunel\b", t):
        return {"km": 20.1}, "túnel Zurquí"
    if re.search(r"\bpeaje\b", t):
        return {"km": 14.2}, "peaje del Zurquí"
    return {}, None


def sentido(t):
    if re.search(r"\bambos sentidos\b", t):
        return "ambos"
    if re.search(r"\b1\s*[-:=]\s*2\b|\b(sj|san jose)\s*[-/]?\s*(limon|guapiles)\b|\b(hacia|para|rumbo a|sentido) (limon|guapiles|el caribe)\b|\bbajando\b", t):
        return "1:2"
    if re.search(r"\b2\s*[-:=]\s*1\b|\b(limon|guapiles|gua)\s*[-/]?\s*(sj|san jose)\b|\b(hacia|para|rumbo a|sentido) (san jose|sj|chepe)\b|\bsubiendo a san jose\b", t):
        return "2:1"
    return None


def describir_lugar(loc, nombre):
    if "kmIni" in loc:
        return f"entre los km {coma(loc['kmIni'])} y {coma(loc['kmFin'])}"
    if "km" in loc:
        return f"cerca de {nombre} (km {coma(loc['km'])})" if nombre else f"en el km {coma(loc['km'])}"
    return ""


def _hora(valor):
    try:
        return datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


# ── grupo de usuarios ────────────────────────────────────────────────────────────────────────────
def mensajes_del_grupo(publicaciones):
    """Aplana publicaciones y comentarios en mensajes individuales con su hora."""
    for p in publicaciones:
        if p.get("texto") and p.get("hora"):
            yield {"id": p["id"], "url": p["url"], "texto": p["texto"], "hora": p["hora"], "aprox": p.get("horaAprox", True), "comentario": False}
        for c in p.get("comentarios", []):
            if c.get("texto") and c.get("hora"):
                hhmm = c["hora"][11:16].replace(":", "")
                yield {"id": f"{p['id']}-c{hhmm}", "url": p["url"], "texto": c["texto"], "hora": c["hora"], "aprox": c.get("horaAprox", True), "comentario": True}


def reportes_del_grupo(publicaciones, lugares, emergencia):
    """Convierte lo leído del grupo en reportes de usuarios, juntando los mensajes que dicen lo mismo."""
    candidatos = []
    for m in mensajes_del_grupo(publicaciones):
        t = norm(m["texto"])
        if len(t) < 6 or es_pregunta(t):
            continue
        tipo = clasificar(t)
        if not tipo:
            continue
        if tipo == "normal" and re.search(r"\b(abierto|habilitado)\b", t) and emergencia:
            tipo = "reapertura"  # durante un cierre, "está abierto" equivale a avisar la reapertura
        loc, nombre = ubicar(t, lugares)
        # Mensajes sobre otros tramos de la 32 (Guápiles–Limón) quedan fuera; también los de
        # accidentes o presas sin ninguna señal de que sean en el Zurquí.
        if FUERA.search(t) and not ZURQUI.search(t):
            continue
        if not loc and tipo in ("accidente", "varado", "presa", "derrumbe") and not ZURQUI.search(t):
            continue
        if "km" in loc and loc["km"] > 50 or "kmIni" in loc and loc["kmIni"] > 50:
            continue
        candidatos.append({**m, "tipo": tipo, "loc": loc, "lugar": nombre, "sentido": sentido(t), "dt": _hora(m["hora"])})

    # Juntar: mismo tipo, cerca en el mapa (o ambos sin lugar) y dentro de 2 horas.
    grupos = []
    for c in sorted(candidatos, key=lambda x: x["dt"]):
        km = c["loc"].get("km", c["loc"].get("kmIni"))
        for g in grupos:
            gkm = g[0]["loc"].get("km", g[0]["loc"].get("kmIni"))
            cerca = (km is None and gkm is None) or (km is not None and gkm is not None and abs(km - gkm) <= 2)
            if g[0]["tipo"] == c["tipo"] and cerca and c["dt"] - g[-1]["dt"] <= timedelta(hours=2):
                g.append(c)
                break
        else:
            grupos.append([c])

    reportes = []
    for g in grupos:
        base, ultimo, n = g[0], g[-1], len(g)
        loc = next((x["loc"] for x in g if x["loc"]), {})
        nombre = next((x["lugar"] for x in g if x["loc"]), None)
        sent = next((x["sentido"] for x in reversed(g) if x["sentido"]), None)
        quien = "Un usuario reporta" if n == 1 else f"{n} usuarios reportan"
        donde = describir_lugar(loc, nombre)
        partes = [f"{quien} {FRASE[base['tipo']]}" + (f" {donde}" if donde else ""), SENTIDO_TXT.get(sent, "")]
        original = ", ".join(p for p in partes if p) + "."
        if base["tipo"] == "reapertura":
            simple = original + " Es una posible reapertura: falta la confirmación oficial."
        else:
            simple = original + " Es un reporte de usuarios, sin confirmar."
        r = {"id": base["id"], "hora": ultimo["hora"], "horaAprox": ultimo["aprox"], "fuente": "usuarios", "tipo": base["tipo"],
             "sentido": sent, "origen": GRUPO + (" (comentario)" if base["comentario"] else ""), "url": base["url"],
             "original": original[:200], "simple": simple[:600], **loc}
        if n > 1:
            r["confirmaciones"] = n
        reportes.append(r)
    return reportes


# ── avisos oficiales y noticias ──────────────────────────────────────────────────────────────────
def _motivo(t, loc):
    for patron, texto in [(r"caida de material|cayo material|material caido", "Caída de material"),
                          (r"deslizamiento|derrumbe", "Deslizamiento"),
                          (r"accidente|colision|choque|volcamiento|volcado", "Accidente"),
                          (r"lluvia|saturaci|preventiv", "Cierre preventivo por lluvia"),
                          (r"trabajos|mantenimiento|demarcaci|bacheo|recarpeteo", "Trabajos en la vía")]:
        if re.search(patron, t):
            if "kmIni" in loc:
                return f"{texto} entre los km {coma(loc['kmIni'])} y {coma(loc['kmFin'])}"
            if "km" in loc:
                return f"{texto} en el km {coma(loc['km'])}"
            return texto
    return None


def _plan(texto):
    frases = re.split(r"(?<=[.!])\s+", texto)
    # solo lo que se anuncia (no lo que ya se está haciendo), cortado en frases completas
    plan = ""
    for f in frases:
        if re.search(r"(se realizar|valoraci|se informar|hora de apertura|se estima|se espera|se habilitar|permanecera)", norm(f)):
            f = re.sub(r"\s*#\S+", "", f).strip()
            if len(plan) + len(f) + 1 > 240:
                break
            plan = (plan + " " + f).strip()
    return plan or None


def _alternas(texto):
    t = norm(texto)
    alternas = []
    for m in re.finditer(r"\b(?:rn|ruta(?: nacional)?)\s*(\d{1,3})\s+por\s+([a-z ]+?)\s+para\s+((?:vehiculos|automotores) (?:pesados|livianos)|livianos|pesados)", t):
        lugar = m.group(2).strip().title()
        para = "vehículos pesados" if "pesado" in m.group(3) else "vehículos livianos"
        alternas.append({"via": f"Ruta {m.group(1)} por {lugar}", "para": para})
    return alternas[:4] or None


def reporte_oficial(texto, hora, url, id_, fuente="oficial", origen="MOPT (Facebook)"):
    """Un aviso del MOPT (o una nota de prensa) -> reporte, o None si no es sobre el Zurquí."""
    t = norm(texto)
    if not re.search(r"\b(ruta 32|ruta nacional 32|rn 32|zurqui|braulio carrillo)\b", t):
        return None
    if FUERA.search(t) and not re.search(r"zurqui|braulio|tunel|rio sucio|peaje", t):
        return None
    # el tipo se decide sin la frase de rutas alternas ("se mantienen habilitadas la RN 10…")
    sin_alternas = " ".join(f for f in re.split(r"(?<=[.!])\s+", t) if not re.search(r"\b(rn \d+|ruta \d+ por|rutas? alternas?|para viajar al caribe)", f))
    if re.search(r"(determinar (la )?hora de apertura|se determine la apertura|permanece cerrad|continua cerrad|se mantiene cerrad)", sin_alternas):
        tipo = "cierre"  # una actualización mientras la ruta sigue cerrada
    elif re.search(r"\b(apertura|habilita\w*|reabr\w+|se reanuda)\b", sin_alternas):
        tipo = "reapertura"
    elif re.search(r"\b(cierre|cerrad[oa]|se cierra|cierran)\b", sin_alternas):
        tipo = "cierre"
    elif re.search(r"paso regulado", t):
        tipo = "regulado"
    else:
        tipo = clasificar(t)
        if tipo in (None, "normal", "presa", "clima"):
            tipo = "obras" if re.search(r"trabaj|limpieza|remover|mantenimiento", t) else None
    if not tipo:
        return None
    loc, _ = ubicar(t, [])
    r = {"id": id_, "hora": hora, "horaAprox": False, "fuente": fuente, "tipo": tipo, "sentido": "ambos" if tipo in ("cierre", "reapertura") else None,
         "origen": origen, "url": url, "original": re.split(r"(?<=[.!])\s+", texto.strip())[0][:200], **loc}
    motivo, plan, alternas = _motivo(t, loc), _plan(texto), _alternas(texto)
    quien = "El MOPT" if fuente == "oficial" else "La prensa"
    accion = {"cierre": "informa el cierre de la Ruta 32 en el Zurquí", "reapertura": "anuncia la reapertura de la Ruta 32 en el Zurquí",
              "regulado": "informa paso regulado en la Ruta 32", "obras": "informa trabajos en la Ruta 32"}.get(tipo, f"reporta {FRASE.get(tipo, tipo)} en la Ruta 32")
    simple = f"{quien} {accion}" + (f": {motivo[0].lower() + motivo[1:]}" if motivo and tipo != "reapertura" else "") + "."
    r["simple"] = simple[:600]
    if tipo in ("cierre", "regulado") and motivo:
        r["motivo"] = motivo[:120]
    if tipo in ("cierre", "regulado", "obras") and plan:
        r["plan"] = plan
    if alternas:
        r["alternas"] = alternas
    return r


def reportes_del_mopt(publicaciones):
    reportes = []
    for p in publicaciones:
        if not p.get("texto") or not p.get("hora"):
            continue
        # Con "hace 1 día" o más, Facebook ya no da la hora: el aviso es viejo y su hora sería inventada.
        if (p.get("minutos") or 0) >= 1440:
            continue
        dt = datetime.fromisoformat(p["hora"]).astimezone(CR)
        url = p["url"] if p.get("tieneEnlace") else URL_MOPT
        # el id sale del texto: la dirección y la hora que muestra Facebook cambian entre lecturas
        huella = hashlib.sha1(norm(p["texto"])[:300].encode()).hexdigest()[:8]
        r = reporte_oficial(p["texto"], p["hora"], url, f"mopt-{huella}")
        if r:
            r["horaAprox"] = p.get("horaAprox", False)
            reportes.append(r)
    return reportes
