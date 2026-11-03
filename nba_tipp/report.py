"""Erstellt die taegliche Zusammenfassung (Markdown, Deutsch, Zeiten in Schweizer Zeit)."""
import datetime as dt
from zoneinfo import ZoneInfo

from . import espn
from .model import TeamModel, GameForecast
from .players import player_logs, team_projections, LABEL
from .prob import american_to_decimal, devig, fair_odds

TZ_CH = ZoneInfo("Europe/Zurich")
TZ_ET = ZoneInfo("America/New_York")
INJURY_FACTOR = 0.22   # Teampunkte-Abzug pro Punkt (PPG) eines ausfallenden Spielers
VALUE_THRESHOLD = 0.57  # ab dieser Wahrscheinlichkeit wird eine Linie als "lohnend" markiert
EDGE_MIN = 0.04        # Modell vs. Markt: ab 4 %-Punkten Abweichung als Hinweis


WOCHENTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def pct(p):
    return f"{100 * p:.0f}%"


def q(p):
    return f"{fair_odds(p):.2f}"


class Context:
    """Laedt Daten + Modell einmal und stellt alles fuer Report/CLI bereit."""

    def __init__(self, now=None, log=print):
        self.now = now or dt.datetime.now(dt.timezone.utc)
        today_et = self.now.astimezone(TZ_ET).date()
        self.season, cache = espn.update_season(today_et, log=log)
        self.games = list(cache["games"].values())
        self.model = TeamModel(self.games, as_of=self.now)
        self.logs = player_logs(self.games)
        try:
            self.injuries = espn.injuries()
        except RuntimeError as e:
            log(f"Verletzungsliste nicht verfuegbar: {e}")
            self.injuries = {}
        self.team_game_ids = {}
        for g in sorted(self.games, key=lambda g: g["date"]):
            for side in ("home", "away"):
                self.team_game_ids.setdefault(g[side]["abbr"], []).append(g["id"])
        self.today_et = today_et

    def upcoming(self, days_ahead=3):
        """Spiele des naechsten Spieltags (US-Datum heute, sonst die folgenden Tage).
        Ein US-Spieltag D wird in der Schweiz in der Nacht von D auf D+1 gespielt."""
        for k in range(days_ahead + 1):
            d = self.today_et + dt.timedelta(days=k)
            games = [g for g in espn.upcoming(d)
                     if dt.datetime.fromisoformat(g["date"].replace("Z", "+00:00"))
                     >= self.now - dt.timedelta(minutes=30)]
            if games:
                self.game_day = d
                return sorted(games, key=lambda g: g["date"])
        self.game_day = None
        return []

    def find_upcoming(self, team, days_ahead=3):
        for k in range(days_ahead + 1):
            for g in espn.upcoming(self.today_et + dt.timedelta(days=k)):
                if team in (g["home"]["abbr"], g["away"]["abbr"]):
                    return g
        return None

    def out_players(self, team):
        return [i for i in self.injuries.get(team, []) if i["status"].lower() == "out"]

    def injury_adjustment(self, team):
        """Punkteabzug fuer ausfallende Spieler, die zuletzt regelmaessig spielten."""
        adj, notes = 0.0, []
        gids = self.team_game_ids.get(team, [])[-10:]
        for inj in self.out_players(team):
            e = self.logs.get(inj["name"])
            if not e or not gids:
                continue
            played = [l for l in e["logs"] if l["game_id"] in gids]
            share = len(played) / len(gids)
            if not played:
                continue
            ppg = sum(l["pts"] for l in played) / len(played)
            mpg = sum(l["min"] for l in played) / len(played)
            if mpg < 15:
                continue
            a = INJURY_FACTOR * ppg * share
            adj -= a
            notes.append((inj["name"], ppg, a))
        return adj, notes

    def forecast(self, g):
        h, a = g["home"]["abbr"], g["away"]["abbr"]
        adj_h, _ = self.injury_adjustment(h)
        adj_a, _ = self.injury_adjustment(a)
        return GameForecast(self.model, g, adj_h, adj_a)

    def opp_factor(self, opp):
        m = self.model
        return (m.mu - m.de.get(opp, 0)) / m.mu if m.mu else 1.0

    def projections(self, team, opp):
        outs = {i["name"] for i in self.out_players(team)}
        return team_projections(self.logs, team, self.team_game_ids.get(team, []),
                                self.opp_factor(opp), outs)


def market_probs(odds):
    """No-Vig-Wahrscheinlichkeiten aus den Buchmacherquoten."""
    if not odds:
        return {}
    res = {}
    dh, da = american_to_decimal(odds.get("ml_home")), american_to_decimal(odds.get("ml_away"))
    if dh and da:
        res["home_win"], _ = devig(dh, da)
    do, du = american_to_decimal(odds.get("total_odds_over")), american_to_decimal(odds.get("total_odds_under"))
    if do and du:
        res["over"], _ = devig(do, du)
    return res


def game_block(ctx: Context, g: dict, picks: list, detail=True) -> str:
    f = ctx.forecast(g)
    H, A = g["home"]["abbr"], g["away"]["abbr"]
    t = dt.datetime.fromisoformat(g["date"].replace("Z", "+00:00")).astimezone(TZ_CH)
    odds = g.get("odds") or {}
    mk = market_probs(odds)
    lines = [f"### {A} @ {H} — {WOCHENTAG[t.weekday()]} {t:%H:%M} Uhr"]

    ph = f.p_home_win()
    pm = f.p_home_win(model_only=True)
    s = f"**Sieg:** {H} {pct(ph)} (faire Quote {q(ph)}) · {A} {pct(1 - ph)} ({q(1 - ph)})"
    if "home_win" in mk:
        s += f" — Markt {H} {pct(mk['home_win'])}"
    lines.append(s)

    fav, dog = (H, A) if f.margin >= 0 else (A, H)
    lines.append(f"**Prognose:** {H} {f.home_pts:.1f} – {A} {f.away_pts:.1f} "
                 f"(Diff. {fav} +{abs(f.margin):.1f}, Total {f.total:.1f})")

    if f.market_margin is not None:
        hs = odds["home_spread"]
        pc = f.p_home_cover(hs)
        lines.append(f"**Handicap** {H} {hs:+.1f}: {H} deckt {pct(pc)} · {A} {-hs:+.1f} deckt {pct(1 - pc)}")
    if f.market_total is not None:
        L = f.market_total
        po = f.p_over(L)
        lines.append(f"**Over/Under {L}:** Over {pct(po)} ({q(po)}) · Under {pct(1 - po)} ({q(1 - po)})")
    vo, vu = f.value_line_total(VALUE_THRESHOLD)
    lines.append(f"**Total-Faustregel:** Over lohnt bis {vo} · Under lohnt ab {vu} (≥{pct(VALUE_THRESHOLD)})")

    # Modell vs. Markt Hinweise
    if "home_win" in mk:
        d = pm - mk["home_win"]
        if abs(d) >= EDGE_MIN:
            side, p_side, m_side = (H, pm, mk["home_win"]) if d > 0 else (A, 1 - pm, 1 - mk["home_win"])
            picks.append((abs(d), f"{A} @ {H}: Sieg {side} — Modell {pct(p_side)} vs. Markt {pct(m_side)}"))
    if f.market_total is not None:
        d = f.model_total - f.market_total
        if abs(d) >= 4:
            side = "Over" if d > 0 else "Under"
            p_side = f.p_over(f.market_total, model_only=True)
            p_side = p_side if d > 0 else 1 - p_side
            picks.append((abs(p_side - 0.5), f"{A} @ {H}: {side} {f.market_total} — Modell-Total "
                                             f"{f.model_total:.1f} ({pct(p_side)})"))
    if f.market_margin is not None:
        d = f.model_margin - f.market_margin
        if abs(d) >= 3:
            pc = f.p_home_cover(odds["home_spread"], model_only=True)
            side, p_side = (f"{H} {odds['home_spread']:+.1f}", pc) if d > 0 else (f"{A} {-odds['home_spread']:+.1f}", 1 - pc)
            picks.append((abs(p_side - 0.5), f"{A} @ {H}: Handicap {side} — Modell {pct(p_side)}"))

    extra = []
    for team in (H, A):
        if f.b2b.get(team):
            extra.append(f"{team} spielt Back-to-Back")
        _, notes = ctx.injury_adjustment(team)
        outs = ctx.out_players(team)
        dtd = [i for i in ctx.injuries.get(team, []) if i["status"].lower() != "out"]
        if outs:
            extra.append(f"{team} out: " + ", ".join(i["name"] for i in outs))
        if dtd:
            extra.append(f"{team} fraglich: " + ", ".join(i["name"] for i in dtd))
    if extra:
        lines.append("_" + " · ".join(extra) + "_")

    if detail:
        lines.append("")
        lines.append("| Spieler | Min | Pkt (Over bis / Under ab) | Reb | Ast | 3er | P+R+A |")
        lines.append("|---|---|---|---|---|---|---|")
        for team, opp in ((H, A), (A, H)):
            for p in ctx.projections(team, opp):
                vo, vu = p.value_lines("pts", VALUE_THRESHOLD)
                lines.append(
                    f"| {p.name} ({team}) | {p.minutes:.0f} | {p.mean['pts']:.1f} ({vo} / {vu}) | "
                    f"{p.mean['reb']:.1f} | {p.mean['ast']:.1f} | {p.mean['fg3']:.1f} | {p.mean['pra']:.1f} |")
    return "\n".join(lines)


def build_report(ctx: Context, detail=True) -> tuple[str, str]:
    games = ctx.upcoming()
    if not games:
        title = "NBA-Tipps: keine Spiele"
        return title, f"# {title}\n\nIn den nächsten Tagen sind keine NBA-Spiele angesetzt.\n"
    d = ctx.game_day
    title = f"NBA-Tipps für die Nacht {d:%d.%m.}–{d + dt.timedelta(days=1):%d.%m.%Y}"
    picks: list = []
    blocks = [game_block(ctx, g, picks, detail) for g in games]
    out = [f"# {title}", "",
           f"{len(games)} Spiele · Datenbasis: {len(ctx.games)} Saisonspiele · "
           f"Heimvorteil {ctx.model.hca:.1f} Pkt · Liga-Schnitt {ctx.model.mu:.1f} Pkt/Team", ""]
    out.append("## Auffälligkeiten (eigenes Modell ≠ Buchmacher)")
    out.append("_Hinweise, keine sicheren Tipps: Der Markt liegt meistens richtig, v.a. früh in der Saison._")
    if picks:
        for _, txt in sorted(picks, reverse=True)[:6]:
            out.append(f"- {txt}")
    else:
        out.append("- Keine grossen Abweichungen – Markt und Modell sind sich einig.")
    out += ["",
            "**So nutzt du das:** Wette nur, wenn die Sporttip-Quote *höher* ist als die faire Quote. "
            "Beispiel: faire Quote 1.80, Sporttip bietet 1.95 → positiver Erwartungswert.",
            ""]
    out.append("## Spiele")
    for b in blocks:
        out += ["", b]
    out += ["", "---",
            "_Wahrscheinlichkeiten = 70% Buchmacherlinie (DraftKings via ESPN) + 30% eigenes Modell (Team-Ratings, Heimvorteil, "
            "Back-to-Back, Ausfälle). Spieler-Linien: 'Over bis X' = bis zu dieser Linie liegt P(Over) ≥ 57%. "
            "Keine Garantie – Wetten mit Verlustrisiko, nur mit Geld, das du verlieren kannst._"]
    return title, "\n".join(out) + "\n"


def build_short(ctx: Context) -> str:
    """Kurzfassung fuer Push-Nachrichten (eine Zeile pro Spiel)."""
    games = ctx.upcoming()
    if not games:
        return "Heute keine NBA-Spiele."
    rows = []
    for g in games:
        f = ctx.forecast(g)
        H, A = g["home"]["abbr"], g["away"]["abbr"]
        t = dt.datetime.fromisoformat(g["date"].replace("Z", "+00:00")).astimezone(TZ_CH)
        ph = f.p_home_win()
        fav, p = (H, ph) if ph >= 0.5 else (A, 1 - ph)
        s = f"{t:%H:%M} {A}@{H}: {fav} {pct(p)} ({q(p)})"
        if f.market_total is not None:
            po = f.p_over(f.market_total)
            side, pp = ("O", po) if po >= 0.5 else ("U", 1 - po)
            s += f" · {side}{f.market_total} {pct(pp)}"
        else:
            s += f" · Total ~{f.total:.0f}"
        rows.append(s)
    picks: list = []
    for g in games:
        game_block(ctx, g, picks, detail=False)
    if picks:
        rows.append("")
        rows.append("Auffällig: " + " | ".join(t for _, t in sorted(picks, reverse=True)[:3]))
    return "\n".join(rows)
