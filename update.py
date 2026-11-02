"""Holt Meldungen aus RSS-Feeds und speichert sie als JSON.
Aufruf: python update.py
Nur Python-Standardbibliothek, nichts zu installieren."""
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# Trage hier RSS-Feeds ein, deren Nutzungsbedingungen du geprüft hast.
QUELLEN = [
    # {"name": "Polizei Berlin", "url": "https://...rss"},
]

def lade_feed(quelle):
    req = urllib.request.Request(quelle["url"], headers={"User-Agent": "info-projekt/0.1"})
    with urllib.request.urlopen(req, timeout=15) as antwort:
        baum = ET.fromstring(antwort.read())
    eintraege = []
    for item in baum.iter("item"):
        eintraege.append({
            "titel": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "datum": (item.findtext("pubDate") or "").strip(),
            "quelle": quelle["name"],
        })
    return eintraege[:20]  # nur Titel + Link, kein Volltext

alle = []
for q in QUELLEN:
    try:
        alle += lade_feed(q)
    except Exception as fehler:
        print("Fehler bei", q["name"], fehler)

with open("data/meldungen.json", "w", encoding="utf-8") as f:
    json.dump({"stand": datetime.now().isoformat(timespec="minutes"), "meldungen": alle},
              f, ensure_ascii=False, indent=2)
print(len(alle), "Meldungen gespeichert")
