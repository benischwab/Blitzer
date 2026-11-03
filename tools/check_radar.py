"""Vergleicht die aktuelle Liste auf so.ch/radar mit data/blitzer.json.

Aufruf: python3 tools/check_radar.py
Gibt den Stand der Kapo-Liste und alle Standorte aus, die in data/blitzer.json
fehlen. Neue Standorte werden nicht automatisch eingetragen, weil die Kapo nur
Gemeinde und Strasse nennt: Koordinaten bitte von Hand setzen und "lage" angeben.
"""
import html, json, pathlib, re, urllib.request

URL = "https://so.ch/verwaltung/departement-des-innern/polizei/praevention/verkehr/radarstandorte/"
ROOT = pathlib.Path(__file__).resolve().parent.parent

def tables(page):
    out = {}
    for head, body in re.findall(r"<h3[^>]*>(.*?)</h3>(.*?)(?=<h3|\Z)", page, re.S):
        head = html.unescape(re.sub(r"<[^>]+>", "", head)).strip()
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
            cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(cells) >= 2 and cells[0]:
                rows.append((cells[0], cells[1]))
        stand = re.search(r"Stand:\s*([^<]+)", body)
        if rows:
            out[head] = {"stand": stand.group(1).strip() if stand else None, "rows": rows}
    return out

def main():
    page = urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "blitzerkarte-olten"})).read().decode("utf-8")
    data = json.loads((ROOT / "data/blitzer.json").read_text(encoding="utf-8"))
    norm = lambda o: re.split(r" \(| - ", o)[0].strip()
    known = {(s["gemeinde"], norm(s["ort"])) for s in data["standorte"] + data["ausserhalb"]}
    for head, t in tables(page).items():
        print(f"\n{head}" + (f"  (Stand {t['stand']})" if t["stand"] else ""))
        for g, o in t["rows"]:
            flag = "   " if (g, norm(o)) in known else "NEU"
            print(f"  {flag} {g}: {o}")
    print(f"\ndata/blitzer.json: Stand {data['stand']}")

if __name__ == "__main__":
    main()
