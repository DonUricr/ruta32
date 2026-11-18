"""Sube a GitHub lo que el sitio público necesita, para que GitHub Pages lo muestre.

Uso:
    python lector/publicar.py          # solo los reportes (lo que hace la lectura diaria)
    python lector/publicar.py --todo   # también la página y los datos de sectores (tras cambiar el diseño)

Si la carpeta todavía no está conectada a GitHub, avisa y termina sin error: así la lectura
diaria no falla mientras el sitio no esté publicado.
"""
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVOS = ["data/reportes.js"]
TODO = ["index.html", "data/", "README.md", ".gitignore"]
FIRMA = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} falló:\n{r.stderr.strip() or r.stdout.strip()}")
    return r


def main():
    if git("rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        print("Sin publicar: la carpeta todavía no es un repositorio de git.")
        return
    if not git("remote", check=False).stdout.split():
        print("Sin publicar: la carpeta todavía no está conectada con GitHub.")
        return
    todo = "--todo" in sys.argv[1:]
    git("add", "--", *(TODO if todo else ARCHIVOS))
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("Nada nuevo para publicar.")
        return
    ahora = datetime.now(timezone(timedelta(hours=-6))).strftime("%Y-%m-%d %H:%M")
    titulo = f"Actualizar sitio ({ahora})" if todo else f"Reportes al {ahora}"
    git("commit", "-q", "-m", titulo, "-m", FIRMA)
    # por si la nube subió algo en el ínterin (por ejemplo, el lector de noticias de GitHub Actions)
    git("pull", "-q", "--rebase", "origin", "main", check=False)
    git("push", "-q", "origin", "HEAD")
    print(f"Publicado: {titulo}. GitHub Pages lo muestra en uno o dos minutos.")


if __name__ == "__main__":
    main()
