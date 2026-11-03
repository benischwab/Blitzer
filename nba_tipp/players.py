"""Spieler-Projektionen fuer Over/Under-Wetten (Punkte, Rebounds, Assists, Dreier, PRA)."""
import datetime as dt
import math

from .prob import p_over_gamma

STATS = ("pts", "reb", "ast", "fg3", "pra")
LABEL = {"pts": "Pkt", "reb": "Reb", "ast": "Ast", "fg3": "3er", "pra": "P+R+A"}
# Streuungs-Prior: sd ~ c * sqrt(mean) (ueberdispersierte Zaehldaten)
SD_FACTOR = {"pts": 1.55, "reb": 1.25, "ast": 1.3, "fg3": 1.15, "pra": 1.6}
GAME_HALF_LIFE = 8.0   # Spiele
PRIOR_GAMES = 4.0      # Gewicht des Streuungs-Priors
SD_INFLATE = 1.15      # Unsicherheit der Projektion selbst (kalibriert)


def _gdate(g):
    return dt.datetime.fromisoformat(g["date"].replace("Z", "+00:00"))


def player_logs(games: list[dict]) -> dict:
    """{player_name: {"team": abbr, "id": id, "logs": [ {date, min, pts, ...} ]}}"""
    out = {}
    for g in sorted(games, key=_gdate):
        for team, rows in (g.get("box") or {}).items():
            opp = g["away"]["abbr"] if team == g["home"]["abbr"] else g["home"]["abbr"]
            for r in rows:
                e = out.setdefault(r["name"], {"team": team, "id": r["id"], "logs": []})
                e["team"] = team  # letzter Verein (Trades)
                row = dict(r)
                row["pra"] = r["pts"] + r["reb"] + r["ast"]
                row["date"] = g["date"]
                row["opp"] = opp
                row["game_id"] = g["id"]
                e["logs"].append(row)
    return out


class Projection:
    def __init__(self, name, team, logs, opp_factor=1.0, team_games=None):
        self.name, self.team = name, team
        self.games = len(logs)
        n = len(logs)
        ws = [0.5 ** ((n - 1 - i) / GAME_HALF_LIFE) for i in range(n)]
        W = sum(ws)
        self.minutes = sum(w * l["min"] for w, l in zip(ws, logs)) / W
        self.mean, self.sd = {}, {}
        for s in STATS:
            m = sum(w * l[s] for w, l in zip(ws, logs)) / W
            if s in ("pts", "fg3", "pra"):
                m *= opp_factor if s != "pra" else (1 + (opp_factor - 1) * 0.6)
            var = sum(w * (l[s] - m) ** 2 for w, l in zip(ws, logs)) / W
            prior = (SD_FACTOR[s] ** 2) * max(m, 0.5)
            k = min(n, 20)
            sd = math.sqrt((k * var + PRIOR_GAMES * prior) / (k + PRIOR_GAMES))
            self.mean[s], self.sd[s] = m, max(sd * SD_INFLATE, 0.6)
        # Anteil der Teamspiele, in denen der Spieler zuletzt gespielt hat
        self.recent_share = 1.0
        if team_games:
            last = team_games[-10:]
            played = {l["game_id"] for l in logs}
            self.recent_share = sum(1 for gid in last if gid in played) / len(last)

    def p_over(self, stat, line):
        return p_over_gamma(self.mean[stat], self.sd[stat], line)

    def value_lines(self, stat, threshold=0.57):
        """(Over lohnt bis Linie, Under lohnt ab Linie)"""
        m = self.mean[stat]
        base = math.floor(m) + 0.5
        over = under = None
        for k in range(-25, 26):
            line = base + k
            if line < 0:
                continue
            if self.p_over(stat, line) >= threshold and (over is None or line > over):
                over = line
            if 1 - self.p_over(stat, line) >= threshold and (under is None or line < under):
                under = line
        return over, under


def team_projections(logs: dict, team: str, team_game_ids: list[str], opp_factor: float,
                     out_names: set[str], min_minutes=22.0, top=4):
    res = []
    for name, e in logs.items():
        if e["team"] != team or name in out_names:
            continue
        lg = [l for l in e["logs"] if l["min"] > 0]
        if len(lg) < 3:
            continue
        p = Projection(name, team, lg[-25:], opp_factor, team_game_ids)
        if p.minutes >= min_minutes and p.recent_share >= 0.5:
            res.append(p)
    res.sort(key=lambda p: -p.mean["pts"])
    return res[:top]


def find_player(logs: dict, query: str):
    q = query.lower()
    hits = [n for n in logs if q in n.lower()]
    if not hits:
        return None
    hits.sort(key=lambda n: -len(logs[n]["logs"]))
    return hits[0]
