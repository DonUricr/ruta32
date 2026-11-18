"""Lee las noticias (RSS) de medios que replican los avisos del MOPT y convierte en reportes las que
hablan de la Ruta 32 en el Zurquí. No usa ninguna cuenta: son fuentes públicas. Funciona igual en
esta computadora que en la nube (GitHub Actions)."""
import hashlib
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime

from comun import CR, ahora, iso
from reglas import reporte_oficial

FEEDS = {
    "El Observador": "https://observador.cr/feed/",
    "La Nación": "https://www.nacion.com/arc/outboundfeeds/rss/?outputType=xml",
    "El Mundo CR": "https://www.elmundo.cr/feed/",
}
CLIENTE = "Mozilla/5.0 (compatible; mapa-ruta32/1.0)"


def _texto(nodo):
    t = "".join(nodo.itertext()) if nodo is not None else ""
    return re.sub(r"<[^>]+>", " ", t).strip()


def leer_feed(nombre, url, horas):
    pedido = urllib.request.Request(url, headers={"User-Agent": CLIENTE})
    with urllib.request.urlopen(pedido, timeout=20) as r:
        raiz = ET.fromstring(r.read())
    limite = ahora() - timedelta(hours=horas)
    for item in raiz.iter("item"):
        try:
            fecha = parsedate_to_datetime(_texto(item.find("pubDate"))).astimezone(CR)
        except (TypeError, ValueError):
            continue
        if fecha < limite:
            continue
        yield {"medio": nombre, "titulo": _texto(item.find("title")), "resumen": _texto(item.find("description"))[:600],
               "url": _texto(item.find("link")), "hora": iso(fecha)}


def reportes_de_noticias(horas=24):
    """Devuelve (reportes, errores). Un medio caído no detiene a los demás."""
    reportes, errores = [], []
    for nombre, url in FEEDS.items():
        try:
            for n in leer_feed(nombre, url, horas):
                if not n["url"].startswith("https://"):
                    continue
                texto = f"{n['titulo']}. {n['resumen']}"
                huella = hashlib.sha1(n["url"].encode()).hexdigest()[:10]
                r = reporte_oficial(texto, n["hora"], n["url"], f"medios-{huella}", fuente="medios", origen=n["medio"])
                if r:
                    r["original"] = n["titulo"][:200]  # el titular, citado como titular
                    reportes.append(r)
        except Exception as e:  # red caída, feed cambiado, etc.
            errores.append(f"{nombre}: {e}")
    return reportes, errores


if __name__ == "__main__":
    import json
    rep, err = reportes_de_noticias(horas=24 * 7)
    print(json.dumps(rep, ensure_ascii=False, indent=1)[:3000])
    print(len(rep), "reportes;", "errores:", err)
