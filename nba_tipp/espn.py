"""Datenbeschaffung ueber die oeffentliche ESPN-API (mit lokalem Cache)."""
import datetime as dt
import json
import os
import time
import urllib.request

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SEASON_TYPES = {2, 3, 5}  # Regular Season, Playoffs, Play-In


def _get(url: str, retries: int = 3) -> dict:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "nba-tipp/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"Abruf fehlgeschlagen: {url}: {last}")


def scoreboard(day: dt.date) -> dict:
    return _get(f"{BASE}/scoreboard?dates={day:%Y%m%d}&limit=50")


def summary(event_id: str) -> dict:
    return _get(f"{BASE}/summary?event={event_id}")


def injuries() -> dict:
    """{team_abbr: [{name, status, comment}]}"""
    d = _get(f"{BASE}/injuries")
    out = {}
    for team in d.get("injuries", []):
        lst = []
        for inj in team.get("injuries", []):
            a = inj.get("athlete", {})
            abbr = (a.get("team") or {}).get("abbreviation")
            lst.append({
                "id": str(a.get("id") or ""),
                "name": a.get("displayName", "?"),
                "status": inj.get("status", "?"),
                "comment": inj.get("shortComment", ""),
                "date": inj.get("date", ""),
                "team": abbr,
            })
        if lst:
            key = lst[0]["team"] or team.get("displayName")
            out[key] = lst
    return out


def news(limit=100) -> list[dict]:
    """Aktuelle NBA-Schlagzeilen: [{headline, description, published, team_ids}]"""
    d = _get(f"{BASE}/news?limit={limit}")
    out = []
    for a in d.get("articles", []):
        out.append({
            "headline": a.get("headline", ""),
            "description": a.get("description", ""),
            "published": a.get("published", ""),
            "team_ids": {str(c.get("teamId")) for c in a.get("categories", [])
                         if c.get("type") == "team" and c.get("teamId")},
            "url": ((a.get("links") or {}).get("web") or {}).get("href", ""),
        })
    return out


# --------------------------------------------------------------------------
# Spiele parsen
# --------------------------------------------------------------------------

def _team(c):
    t = c["team"]
    return {"id": t["id"], "abbr": t["abbreviation"], "name": t.get("displayName", t["abbreviation"])}


def parse_odds(comp: dict) -> dict | None:
    odds = comp.get("odds") or []
    if not odds:
        return None
    o = odds[0]
    res = {"provider": (o.get("provider") or {}).get("name", "?")}
    if o.get("spread") is not None:
        res["home_spread"] = float(o["spread"])
    if o.get("overUnder") is not None:
        res["total"] = float(o["overUnder"])
    ml = o.get("moneyline") or {}
    for side in ("home", "away"):
        v = ((ml.get(side) or {}).get("close") or {}).get("odds")
        if v:
            res[f"ml_{side}"] = v
    ps = o.get("pointSpread") or {}
    for side in ("home", "away"):
        v = ((ps.get(side) or {}).get("close") or {}).get("odds")
        if v:
            res[f"spread_odds_{side}"] = v
    tot = o.get("total") or {}
    for side in ("over", "under"):
        v = ((tot.get(side) or {}).get("close") or {}).get("odds")
        if v:
            res[f"total_odds_{side}"] = v
    if "home_spread" not in res and "total" not in res and "ml_home" not in res:
        return None
    return res


def parse_event(e: dict) -> dict:
    c = e["competitions"][0]
    home = next(x for x in c["competitors"] if x["homeAway"] == "home")
    away = next(x for x in c["competitors"] if x["homeAway"] == "away")
    st = e["status"]["type"]
    g = {
        "id": e["id"],
        "date": e["date"],
        "season_type": (e.get("season") or {}).get("type"),
        "status": st.get("name"),
        "completed": bool(st.get("completed")),
        "neutral": bool(c.get("neutralSite")),
        "home": _team(home),
        "away": _team(away),
        "odds": parse_odds(c),
    }
    if g["completed"]:
        g["home_pts"] = int(home.get("score") or 0)
        g["away_pts"] = int(away.get("score") or 0)
    return g


def parse_box(sm: dict) -> dict:
    """{team_abbr: [ {id,name,min,pts,reb,ast,fg3,starter} ]}"""
    out = {}
    for team in sm.get("boxscore", {}).get("players", []):
        abbr = team["team"]["abbreviation"]
        rows = []
        for block in team.get("statistics", []):
            names = block.get("names") or block.get("labels") or []
            idx = {n: i for i, n in enumerate(names)}
            for a in block.get("athletes", []):
                if a.get("didNotPlay") or not a.get("stats"):
                    continue
                s = a["stats"]

                def num(key, s=s):
                    i = idx.get(key)
                    if i is None or i >= len(s):
                        return 0.0
                    v = s[i]
                    if "-" in v and key in ("3PT",):
                        v = v.split("-")[0]
                    try:
                        return float(v)
                    except ValueError:
                        return 0.0
                mins = num("MIN")
                if mins <= 0:
                    continue
                rows.append({
                    "id": str(a["athlete"]["id"]),
                    "name": a["athlete"]["displayName"],
                    "min": mins, "pts": num("PTS"), "reb": num("REB"),
                    "ast": num("AST"), "fg3": num("3PT"),
                    "starter": bool(a.get("starter")),
                })
        out[abbr] = rows
    return out


# --------------------------------------------------------------------------
# Saison-Cache
# --------------------------------------------------------------------------

def _cache_path(season_year: int) -> str:
    return os.path.join(DATA_DIR, f"season_{season_year}.json")


def load_cache(season_year: int) -> dict:
    p = _cache_path(season_year)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"games": {}, "done_dates": []}


def save_cache(season_year: int, cache: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_cache_path(season_year), "w", encoding="utf-8") as f:
        json.dump(cache, f, separators=(",", ":"))


def update_season(today_et: dt.date, log=print) -> tuple[int, dict]:
    """Laedt alle abgeschlossenen Spiele der laufenden Saison (inkrementell)."""
    sb = scoreboard(today_et)
    season = sb["leagues"][0]["season"]
    year = season["year"]
    start = dt.date.fromisoformat(season["startDate"][:10])
    cache = load_cache(year)
    done = set(cache["done_dates"])
    day = start
    new_games = 0
    while day < today_et:
        key = day.isoformat()
        if key not in done:
            events = scoreboard(day).get("events", [])
            all_final = True
            for e in events:
                g = parse_event(e)
                if g["season_type"] not in SEASON_TYPES:
                    continue
                if not g["completed"]:
                    all_final = False
                    continue
                if g["id"] in cache["games"]:
                    continue
                try:
                    g["box"] = parse_box(summary(g["id"]))
                except RuntimeError as err:
                    log(f"  Boxscore fehlt fuer {g['id']}: {err}")
                    g["box"] = {}
                g.pop("odds", None)
                cache["games"][g["id"]] = g
                new_games += 1
            if all_final:
                done.add(key)
        day += dt.timedelta(days=1)
    cache["done_dates"] = sorted(done)
    save_cache(year, cache)
    if new_games:
        log(f"{new_games} neue Spiele geladen (total {len(cache['games'])}).")
    return year, cache


def upcoming(day_et: dt.date) -> list[dict]:
    games = []
    for e in scoreboard(day_et).get("events", []):
        g = parse_event(e)
        if g["season_type"] in SEASON_TYPES and not g["completed"]:
            games.append(g)
    return games
