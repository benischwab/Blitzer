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


def _game_day(g):
    """US-Spieltag (Ostkueste) eines Spiels."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    t = dt.datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
    return t.astimezone(ZoneInfo("America/New_York")).date().isoformat()


def review(state, results, day=None):
    """Prognose vs. Resultat fuer einen Spieltag (Standard: letzter mit Resultaten)."""
    by_day = {}
    for gid, pred in state["games"].items():
        g = results.get(gid)
        if g:
            by_day.setdefault(pred.get("day") or _game_day(g), []).append((gid, pred, g))
    if not by_day:
        return None
    day = day or max(by_day)
    if day not in by_day:
        return None
    rows = []
    for gid, pred, g in sorted(by_day[day], key=lambda x: x[2]["date"]):
        hp, ap = g["home_pts"], g["away_pts"]
        tp, mg = pred["total"], pred["margin"]
        x = {"matchup": pred["matchup"], "home": g["home"]["abbr"], "away": g["away"]["abbr"],
             "p_home": pred["p_home"], "home_pts": hp, "away_pts": ap,
             "pred_home": (tp + mg) / 2, "pred_away": (tp - mg) / 2,
             "total_pred": tp, "total_real": hp + ap, "margin_err": abs((hp - ap) - mg),
             "win_hit": (pred["p_home"] >= 0.5) == (hp > ap), "ou_hit": None}
        if "line_total" in pred and hp + ap != pred["line_total"]:
            over = pred["p_over"] >= 0.5
            x.update(ou_pick="Over" if over else "Under", line_total=pred["line_total"],
                     ou_p=max(pred["p_over"], 1 - pred["p_over"]),
                     ou_hit=(hp + ap > pred["line_total"]) == over)
        rows.append(x)
    n = len(rows)
    ou = [x for x in rows if x["ou_hit"] is not None]
    summary = {"n": n, "win_hits": sum(x["win_hit"] for x in rows),
               "mae_margin": sum(x["margin_err"] for x in rows) / n,
               "mae_total": sum(abs(x["total_real"] - x["total_pred"]) for x in rows) / n,
               "ou_n": len(ou), "ou_hits": sum(x["ou_hit"] for x in ou)}
    tips, hits, done, profit = [], 0, 0, 0.0
    items = [("single", t) for t in state["singles"].get(day, [])] + \
            [("combo", c) for c in state["combos"].get(day, [])]
    for kind, item in items:
        legs = item["legs"] if kind == "combo" else [item]
        res = [leg_result(l, results) for l in legs]
        if any(r is False for r in res):
            result = False
        elif any(r is None for r in res):
            result = None
        elif all(r == "push" for r in res):
            result = "push"
        else:
            result = True
        odds = 1.0
        for l, r in zip(legs, res):
            odds *= 1.0 if r == "push" else (l.get("dk") or 1.0)
        label = " + ".join(f"{l['label']} ({l['matchup']})" for l in legs)
        tips.append({"text": ("Kombi: " if kind == "combo" else "") + label, "result": result,
                     "odds": odds if all(l.get("dk") for l in legs) else None})
        if result is not None:
            done += 1
            if result is True:
                hits += 1
                profit += odds - 1
            elif result is False:
                profit -= 1
    return {"day": day, "rows": rows, "summary": summary, "tips": tips,
            "tip_n": done, "tip_hits": hits, "tip_profit": profit}
