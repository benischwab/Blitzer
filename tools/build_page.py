"""Erzeugt index.html aus src/index.template.html (Leaflet-CSS wird eingebettet).

Aufruf: python3 tools/build_page.py [--fragment ZIEL]
--fragment schreibt zusätzlich eine Version ohne <html>/<head>-Gerüst (für claude.ai-Artifacts).
"""
import sys, urllib.request, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"

def main():
    tpl = (ROOT / "src/index.template.html").read_text(encoding="utf-8")
    cache = ROOT / "src/leaflet-1.9.4.min.css"
    if not cache.exists():
        cache.write_bytes(urllib.request.urlopen(LEAFLET_CSS).read())
    body = tpl.replace("/*LEAFLET_CSS*/", cache.read_text(encoding="utf-8"))
    page = ('<!doctype html>\n<html lang="de-CH">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<style>body{margin:0}[hidden]{display:none!important}</style>\n</head>\n<body>\n'
            + body + '\n</body>\n</html>\n')
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    if "--fragment" in sys.argv:
        pathlib.Path(sys.argv[sys.argv.index("--fragment") + 1]).write_text(body, encoding="utf-8")

if __name__ == "__main__":
    main()
