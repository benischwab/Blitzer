"""Baut data/basemap.json (vereinfachtes Strassennetz) aus Overpass-JSON-Exporten.

Aufruf: python3 tools/build_basemap.py roads.json city.json places.json
Daten: (c) OpenStreetMap-Mitwirkende, ODbL.
"""
import json, sys

def perp(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** .5
    t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return ((x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2) ** .5

def simplify(pts, eps):
    if len(pts) < 3:
        return pts
    i, d = max(((i, perp(pts[i], pts[0], pts[-1])) for i in range(1, len(pts) - 1)), key=lambda t: t[1])
    if d <= eps:
        return [pts[0], pts[-1]]
    return simplify(pts[:i + 1], eps)[:-1] + simplify(pts[i:], eps)

CLASS = {"motorway": "mw", "motorway_link": "mw", "trunk": "tr", "trunk_link": "tr",
         "primary": "pr", "secondary": "se", "tertiary": "lo", "residential": "lo",
         "unclassified": "lo", "living_street": "lo"}

def main(roads, city, places):
    feats = {}
    for f in (roads, city):
        for e in json.load(open(f, encoding="utf-8"))["elements"]:
            if e["type"] != "way" or "geometry" not in e:
                continue
            t = e["tags"]
            c = CLASS.get(t.get("highway")) or ("wa" if t.get("waterway") == "river" else "rl" if t.get("railway") == "rail" else None)
            if not c:
                continue
            pts = [(round(g["lon"], 5), round(g["lat"], 5)) for g in e["geometry"]]
            pts = simplify(pts, 0.00004 if c == "lo" else 0.00008)
            feats.setdefault(c, []).append([[p[1], p[0]] for p in pts])
    labels = []
    for e in json.load(open(places, encoding="utf-8"))["elements"]:
        n = e["tags"].get("name")
        if n:
            labels.append({"n": n, "p": e["tags"]["place"], "lat": round(e["lat"], 5), "lon": round(e["lon"], 5)})
    out = {"attribution": "© OpenStreetMap-Mitwirkende (ODbL)", "lines": feats, "places": labels}
    json.dump(out, open("data/basemap.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

if __name__ == "__main__":
    main(*sys.argv[1:4])
