# Blitzerkarte Olten

Interaktive Karte der festen und semistationären Geschwindigkeitsmessanlagen rund um Olten.

## Daten

| Datei | Inhalt |
| --- | --- |
| `data/blitzer.json` | Standorte, Quellen und Kennzahlen aus der Verkehrsstatistik |
| `data/basemap.json` | Vereinfachtes Strassennetz aus OpenStreetMap (ODbL) |

Quellen:

- **Stationär und semistationär:** [Polizei Kanton Solothurn, so.ch/radar](https://so.ch/verwaltung/departement-des-innern/polizei/praevention/verkehr/radarstandorte/). Die Kapo nennt nur Gemeinde und Strasse. Die Koordinaten stammen aus OpenStreetMap. Das Feld `lage` sagt, wie genau ein Punkt ist (`genau`, `kreuzung`, `ungefaehr`).
- **Genauere Positionen:** Solothurnerstrasse (Kreuzung Rainstrasse) und Winznau (Lichtsignal Oberdorfstrasse) stimmen mit den OSM-Lichtsignalen und der Radar-Datenbank von lesvoitures.fr überein. Für Olten und Winznau stehen in den Popups Monatsdurchschnitte aus der Kapo-Radarstatistik von Nov. 2013 bis Feb. 2015.
- **Gemeldete Kontrollen (`kontrollen`):** 22 vergangene Kontrollen aus Kapo-Medienmitteilungen von 2015 bis 2026, gruppiert nach Strasse. Die Kapo meldet fast nur Raserfälle. Die Anzahl ist darum kein Mass dafür, wie oft an einer Strasse kontrolliert wird. Die Messstelle selbst nennt die Kapo nie, der Punkt liegt auf der genannten Strasse.
- **Kanton Bern (Wynau, Aarwangen):** nur in OpenStreetMap erfasst, nicht amtlich bestätigt.
- **Mobile Kontrollen:** Aktuelle Standorte werden nicht veröffentlicht und hier nicht gesammelt. Die Karte zeigt nur die Jahreszahlen aus der [Polizeilichen Verkehrsstatistik 2025](https://so.ch/fileadmin/internet/ddi/ddi-kapo/Ueber_uns/Statistiken/PVS_2025.pdf).
- **Kanton Aargau (Aarburg, Zofingen usw.):** Dort gibt es laut SRF nur eine feste Anlage, in Baden. Deshalb ist auf der Karte keine eingetragen.

Öffentliche Warnungen vor Verkehrskontrollen sind nach Art. 98a SVG strafbar. Diese Karte enthält deshalb nur Standorte, die die Polizei selbst veröffentlicht, und feste Anlagen. Meldungen zu mobilen Kontrollen gehören nicht hinein.

## Lokal ansehen

```sh
python3 -m http.server
# dann http://localhost:8000 öffnen
```

Direkt per Doppelklick (`file://`) laden die JSON-Dateien nicht.

## Aktualisieren

Die semistationären Standorte wechseln, die Kapo aktualisiert die Liste meist am Donnerstag.

```sh
python3 tools/check_radar.py   # zeigt neue Standorte auf so.ch/radar (markiert mit NEU)
```

Neue Standorte trägt man von Hand in `data/blitzer.json` ein (Koordinaten, `lage`, `stand`).

Seite neu bauen, nachdem `src/index.template.html` geändert wurde:

```sh
python3 tools/build_page.py
```

Strassennetz neu erzeugen: Overpass-Exporte laden (siehe Kommentar in `tools/build_basemap.py`) und
`python3 tools/build_basemap.py roads.json city.json places.json` ausführen.
