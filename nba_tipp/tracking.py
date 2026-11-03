"""Speichert die abgegebenen Tipps und wertet sie nach Spielende aus (Bilanz).

So sieht man laufend, ob die Vorschlaege tatsaechlich treffen und Gewinn bringen –
das Modell passt sich damit nicht blind an, aber du siehst schwarz auf weiss,
wie gut es aktuell ist.
"""
import json
import os

from .espn import DATA_DIR

PATH = os.path.join(DATA_DIR, "tipps.json")


def load():
    if os.path.exists(PATH):
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"games": {}, "singles": {}, "combos": {}}


def save(state):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=0)


def record(state, day_key, games_pred, singles, combos):
    """Ersetzt die Tipps eines Spieltags durch den neuesten Stand vor Spielbeginn.
    Tipps auf Spiele, die bereits laufen (nicht mehr in games_pred), bleiben stehen."""
    open_ids = set(games_pred)
    for gid, pred in games_pred.items():
        state["games"][gid] = pred
    old_s = [l for l in state["singles"].get(day_key, []) if l["game_id"] not in open_ids]
    state["singles"][day_key] = old_s + [l.to_dict() for l in singles if l.game_id in open_ids]
    old_c = [c for c in state["combos"].get(day_key, [])
             if any(l["game_id"] not in open_ids for l in c["legs"])]
    new_c = [c.to_dict() for c in combos if all(l.game_id in open_ids for l in c.legs)]
    state["combos"][day_key] = old_c + new_c


def leg_result(leg, results):
    """True/False/None (offen) bzw. 'push'."""
    g = results.get(leg["game_id"])
    if not g:
        return None
    hp, ap = g["home_pts"], g["away_pts"]
    home = g["home"]["abbr"]
    if leg["market"] == "ml":
        return (hp > ap) == (leg["side"] == home)
    if leg["market"] == "spread":
        diff = (hp - ap) if leg["side"] == home else (ap - hp)
        v = diff + leg["line"]
        return "push" if v == 0 else v > 0
    if leg["market"] == "total":
        t = hp + ap
        if t == leg["line"]:
            return "push"
        return (t > leg["line"]) == (leg["side"] == "over")
    return None


def summary(state, results):
    """Bilanz: Einzeltipps und Kombis, Einsatz je 1 Fr. zur DraftKings-Quote."""
    out = {}
    for kind in ("singles", "combos"):
        n = hits = 0
        profit = 0.0
        recent = []
        for day in sorted(state[kind]):
            for item in state[kind][day]:
                legs = item["legs"] if kind == "combos" else [item]
                res = [leg_result(l, results) for l in legs]
                if any(r is None for r in res):
                    continue
                if any(r is False for r in res):
                    won, odds = False, 0
                else:
                    won = True
                    odds = 1.0
                    for l, r in zip(legs, res):
                        odds *= 1.0 if r == "push" else (l["dk"] or 1.0)
                n += 1
                hits += won
                profit += (odds - 1) if won else -1
                recent.append((day, " + ".join(l["label"] + f" ({l['matchup']})" for l in legs), won))
        out[kind] = {"n": n, "hits": hits, "profit": profit, "recent": recent[-5:]}
    # Kalibrierung der Siegwahrscheinlichkeiten
    n = correct = 0
    brier = 0.0
    for gid, pred in state["games"].items():
        g = results.get(gid)
        if not g:
            continue
        y = 1 if g["home_pts"] > g["away_pts"] else 0
        n += 1
        correct += int((pred["p_home"] > 0.5) == bool(y))
        brier += (pred["p_home"] - y) ** 2
    out["games"] = {"n": n, "correct": correct, "brier": brier / n if n else None}
    return out
