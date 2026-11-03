"""Erstellt die taegliche Zusammenfassung (Markdown, Deutsch, Zeiten in Schweizer Zeit)."""
import datetime as dt
from zoneinfo import ZoneInfo

from . import bets, espn, tracking
from .model import TeamModel, GameForecast
from .players import player_logs, team_projections, LABEL
from .prob import american_to_decimal, devig, fair_odds

TZ_CH = ZoneInfo("Europe/Zurich")
TZ_ET = ZoneInfo("America/New_York")
INJURY_FACTOR = 0.22   # Teampunkte-Abzug pro Punkt (PPG) eines ausfallenden Spielers
VALUE_THRESHOLD = 0.57  # ab dieser Wahrscheinlichkeit wird eine Linie als "lohnend" markiert
EDGE_MIN = 0.04        # Modell vs. Markt: ab 4 %-Punkten Abweichung als Hinweis
NEWS_HOURS = 36

WOCHENTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def pct(p):
    return f"{100 * p:.0f}%"


def q(p):
    return f"{fair_odds(p):.2f}"


def _ts(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class Context:
    """Laedt Daten + Modell einmal und stellt alles fuer Report/CLI bereit."""

    def __init__(self, now=None, log=print):
        self.now = now or dt.datetime.now(dt.timezone.utc)
        today_et = self.now.astimezone(TZ_ET).date()
        self.season, cache = espn.update_season(today_et, log=log)
        self.games = list(cache["games"].values())
        self.results = {g["id"]: g for g in self.games}
        self.model = TeamModel(self.games, as_of=self.now)
        self.logs = player_logs(self.games)
        try:
            self.injuries = espn.injuries()
        except RuntimeError as e:
            log(f"Verletzungsliste nicht verfuegbar: {e}")
            self.injuries = {}
        try:
            self.news = espn.news()
        except RuntimeError as e:
            log(f"News nicht verfuegbar: {e}")
            self.news = []
        self.team_game_ids = {}
        self.team_games = {}
        for g in sorted(self.games, key=lambda g: g["date"]):
            for side in ("home", "away"):
                self.team_game_ids.setdefault(g[side]["abbr"], []).append(g["id"])
                self.team_games.setdefault(g[side]["abbr"], []).append(g)
        self.today_et = today_et
        self._upcoming = None
        self._plan = None

    # --- Spielplan -------------------------------------------------------
    def upcoming(self, days_ahead=3):
        """Spiele des naechsten Spieltags (US-Datum heute, sonst die folgenden Tage).
        Ein US-Spieltag D wird in der Schweiz in der Nacht von D auf D+1 gespielt."""
        if self._upcoming is not None:
            return self._upcoming
        self.game_day = None
        self._upcoming = []
        for k in range(days_ahead + 1):
            d = self.today_et + dt.timedelta(days=k)
            games = [g for g in espn.upcoming(d) if _ts(g["date"]) >= self.now - dt.timedelta(minutes=30)]
            if games:
                self.game_day = d
                self._upcoming = sorted(games, key=lambda g: g["date"])
                break
        return self._upcoming

    def find_upcoming(self, team, days_ahead=3):
        for g in self.upcoming(days_ahead):
            if team in (g["home"]["abbr"], g["away"]["abbr"]):
                return g
        for k in range(days_ahead + 1):
            for g in espn.upcoming(self.today_et + dt.timedelta(days=k)):
                if team in (g["home"]["abbr"], g["away"]["abbr"]):
                    return g
        return None

    # --- Verletzungen, Form, News ----------------------------------------
    def out_players(self, team):
        return [i for i in self.injuries.get(team, []) if i["status"].lower() == "out"]

    def injury_is_new(self, inj, hours=24):
        t = _ts(inj.get("date", ""))
        return bool(t and (self.now - t).total_seconds() < hours * 3600)

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

    def form(self, team, n=5):
        """z.B. 'S S N S N' (neuestes zuletzt) und Punktedifferenz im Schnitt."""
        gs = self.team_games.get(team, [])[-n:]
        res, diff = [], 0
        for g in gs:
            home = g["home"]["abbr"] == team
            d = (g["home_pts"] - g["away_pts"]) * (1 if home else -1)
            res.append("S" if d > 0 else "N")
            diff += d
        return "".join(res), (diff / len(gs) if gs else 0.0)

    def team_news(self, g, n=2):
        ids = {str(g["home"]["id"]), str(g["away"]["id"])}
        out = []
        for a in self.news:
            t = _ts(a["published"])
            if not t or (self.now - t).total_seconds() > NEWS_HOURS * 3600:
                continue
            if a["team_ids"] & ids:
                out.append(a)
        return out[:n]

    # --- Prognosen -------------------------------------------------------
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

    def plan(self):
        """Alle Wettvorschlaege des Spieltags (einmal berechnet)."""
        if self._plan is None:
            games = self.upcoming()
            legs = bets.all_legs(self, games)
            singles, fill = bets.safe_singles(legs)
            c2, c2_prof = bets.best_combos(legs, 2, min_odds=1.6)
            c3, c3_prof = bets.best_combos(legs, 3, min_odds=2.4)
            self._plan = {
                "games": games, "legs": legs, "singles": singles, "fill": fill,
                "combo2": (c2, c2_prof), "combo3": (c3, c3_prof),
                "props": bets.consistent_props(self, games),
            }
        return self._plan

    def record_tips(self):
        """Speichert die aktuellen Tipps (fuer die spaetere Bilanz)."""
        p = self.plan()
        if not p["games"]:
            return
        state = tracking.load()
        preds = {}
        for g in p["games"]:
            f = self.forecast(g)
            odds = g.get("odds") or {}
            pr = {"p_home": round(bets.win_prob_home(f, odds), 4),
                  "margin": round(f.margin, 2), "total": round(f.total, 2),
                  "matchup": f"{g['away']['abbr']} @ {g['home']['abbr']}",
                  "home": g["home"]["abbr"], "away": g["away"]["abbr"],
                  "day": self.game_day.isoformat()}
            if "home_spread" in odds:
                pr["home_spread"] = odds["home_spread"]
                pr["p_cover"] = round(f.p_home_cover(odds["home_spread"]), 4)
            if "total" in odds:
                pr["line_total"] = odds["total"]
                pr["p_over"] = round(f.p_over(odds["total"]), 4)
            preds[g["id"]] = pr
        combos = []
        for cs, prof in (p["combo2"], p["combo3"]):
            if prof:
                combos += cs[:1]
        tracking.record(state, self.game_day.isoformat(), preds, p["singles"], combos)
        tracking.save(state)

    def snapshot(self):
        """Kompakter Stand fuer den Vergleich bei spaeteren Updates."""
        snap = {}
        for g in self.upcoming():
            H, A = g["home"]["abbr"], g["away"]["abbr"]
            odds = g.get("odds") or {}
            f = self.forecast(g)
            snap[g["id"]] = {
                "matchup": f"{A} @ {H}", "home": H, "away": A,
                "out": sorted(i["name"] for t in (H, A) for i in self.out_players(t)),
                "dtd": sorted(i["name"] for t in (H, A) for i in self.injuries.get(t, [])
                              if i["status"].lower() != "out"),
                "spread": odds.get("home_spread"), "total": odds.get("total"),
                "p_home": round(bets.win_prob_home(f, odds), 4),
            }
        snap["_tips"] = [l.label + " (" + l.matchup + ")" for l in self.plan()["singles"]]
        return snap


def diff_snapshots(old, new):
    """Liste relevanter Aenderungen seit dem letzten Lauf."""
    changes = []
    for gid, n in new.items():
        if gid.startswith("_"):
            continue
        o = old.get(gid)
        if not o:
            continue
        m = n["matchup"]
        for name in sorted(set(n["out"]) - set(o["out"])):
            changes.append(f"{m}: {name} fällt NEU aus")
        for name in sorted(set(o["out"]) - set(n["out"])):
            changes.append(f"{m}: {name} wieder dabei / nicht mehr out")
        if o.get("spread") is not None and n.get("spread") is not None and abs(n["spread"] - o["spread"]) >= 1.5:
            changes.append(f"{m}: Handicap {n['home']} {o['spread']:+.1f} → {n['spread']:+.1f}")
        if o.get("total") is not None and n.get("total") is not None and abs(n["total"] - o["total"]) >= 2:
            changes.append(f"{m}: Total {o['total']} → {n['total']}")
        if o.get("spread") is None and n.get("spread") is not None:
            changes.append(f"{m}: Linien jetzt verfügbar ({n['home']} {n['spread']:+.1f}, Total {n['total']})")
        if abs(n["p_home"] - o["p_home"]) >= 0.05:
            changes.append(f"{m}: Sieg {n['home']} {pct(o['p_home'])} → {pct(n['p_home'])}")
    new_tips = [t for t in new.get("_tips", []) if t not in old.get("_tips", [])]
    gone = [t for t in old.get("_tips", []) if t not in new.get("_tips", [])]
    if new_tips:
        changes.append("Neue Tipps: " + "; ".join(new_tips))
    if gone:
        changes.append("Gestrichen: " + "; ".join(gone))
    return changes


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
    t = _ts(g["date"]).astimezone(TZ_CH)
    odds = g.get("odds") or {}
    mk = market_probs(odds)
    lines = [f"### {A} @ {H} — {WOCHENTAG[t.weekday()]} {t:%H:%M} Uhr"]

    ph = bets.win_prob_home(f, odds)
    pm = f.p_home_win(model_only=True)
    s = f"**Sieg:** {H} {pct(ph)} (faire Quote {q(ph)}) · {A} {pct(1 - ph)} ({q(1 - ph)})"
    if "home_win" in mk:
        s += f" — Markt {H} {pct(mk['home_win'])}"
    lines.append(s)

    fav = H if f.margin >= 0 else A
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

    fh, dh_ = ctx.form(H)
    fa, da_ = ctx.form(A)
    lines.append(f"**Form (letzte 5):** {H} {fh} ({dh_:+.1f}) · {A} {fa} ({da_:+.1f})")

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
        outs = ctx.out_players(team)
        dtd = [i for i in ctx.injuries.get(team, []) if i["status"].lower() != "out"]

        def nm(i):
            return i["name"] + ("*" if ctx.injury_is_new(i) else "")
        if outs:
            extra.append(f"{team} out: " + ", ".join(nm(i) for i in outs))
        if dtd:
            extra.append(f"{team} fraglich: " + ", ".join(nm(i) for i in dtd))
    if extra:
        lines.append("_" + " · ".join(extra) + "_" +
                     (" (* = Meldung der letzten 24 h)" if "*" in "".join(extra) else ""))
    for a in ctx.team_news(g):
        lines.append(f"> 📰 {a['headline']}")

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


def _leg_row(l):
    ev = f"{l.ev * 100:+.1f}%" if l.ev is not None else "–"
    dk = f"{l.dk:.2f}" if l.dk else "–"
    return f"| {l.label} | {l.matchup} | {pct(l.p)} | {dk} | {ev} | **{l.min_odds:.2f}** |"


def _combo_lines(title, combo_res):
    combos, profitable = combo_res
    out = [f"**{title}**"]
    if not combos:
        return out + ["- Keine passende Kombi heute."]
    c = combos[0]
    for l in c.legs:
        out.append(f"- {l.label} ({l.matchup}) — {pct(l.p)}" + (f", DK {l.dk:.2f}" if l.dk else ""))
    dk = f"DK-Quote {c.dk:.2f} ({c.ev * 100:+.1f}%)" if c.has_dk else "DK-Quote noch nicht für alle Tipps"
    status = "profitabel zur DK-Quote" if profitable else "nur spielen, wenn Sporttip mind. die Mindestquote bietet"
    out.append(f"- **Trefferchance {pct(c.p)}** · {dk} · "
               f"**lohnt ab Sporttip-Gesamtquote {c.min_odds:.2f}** · _{status}_")
    return out


def tips_section(ctx: Context) -> list[str]:
    p = ctx.plan()
    out = ["## Wett-Vorschläge: sicher und profitabel", "",
           "_Mindestquote = ab dieser Sporttip-Quote hat die Wette einen Erwartungswert von mind. +3 %. "
           "Liegt die Sporttip-Quote darunter: auslassen._", ""]
    out.append("**Einzelwetten** (sortiert nach Sicherheit)")
    out.append("")
    out.append("| Tipp | Spiel | Chance | DK-Quote | EV (DK) | Mindestquote |")
    out.append("|---|---|---|---|---|---|")
    for l in p["singles"]:
        out.append(_leg_row(l))
    if p["fill"]:
        for l in p["fill"]:
            out.append(_leg_row(l) + " _(nur mit besserer Quote)_")
    if not p["singles"] and not p["fill"]:
        out.append("| – | Noch keine Buchmacher-Linien verfügbar | | | | |")
    out.append("")
    out += _combo_lines("Sichere 2er-Kombi", p["combo2"])
    out.append("")
    out += _combo_lines("3er-Kombi (höhere Quote)", p["combo3"])
    if p["props"]:
        out += ["", "**Sichere Spieler-Linien** (konstanteste Spieler, Chance ≈ 75 %)"]
        for _, pr, stat, line, prob, m in p["props"]:
            out.append(f"- {pr.name} ({pr.team}, {m}): über {line} {LABEL[stat]} — {pct(prob)} · "
                       f"lohnt ab Quote **{(1 + bets.MIN_EDGE) / prob:.2f}**")
    out += ["", "_Kombis: Die Chancen multiplizieren sich – ebenso die Marge des Buchmachers. "
                "Lieber 2er als 4er+, und nur, wenn die Sporttip-Gesamtquote über der Mindestquote liegt._"]
    return out


def bilanz_section(ctx: Context) -> list[str]:
    s = tracking.summary(tracking.load(), ctx.results)
    out = ["## Bilanz bisheriger Tipps"]
    g = s["games"]
    if not g["n"] and not s["singles"]["n"]:
        return out + ["_Noch keine ausgewerteten Tipps – die Bilanz baut sich ab den nächsten Spielen auf._"]
    if g["n"]:
        out.append(f"- Sieger-Prognosen: {g['correct']}/{g['n']} richtig ({g['correct'] / g['n']:.0%}), "
                   f"Brier {g['brier']:.3f}")
    for kind, name in (("singles", "Einzeltipps"), ("combos", "Kombis")):
        k = s[kind]
        if k["n"]:
            out.append(f"- {name}: {k['hits']}/{k['n']} getroffen · Gewinn {k['profit']:+.2f} Fr. "
                       f"bei 1 Fr. Einsatz pro Tipp (ROI {k['profit'] / k['n']:+.0%}, DK-Quoten)")
    last = s["singles"]["recent"] + s["combos"]["recent"]
    if last:
        out.append("- Zuletzt: " + "; ".join(f"{'✅' if w else '❌'} {t}" for _, t, w in last[-6:]))
    return out


def review_lines(ctx: Context, day=None):
    """Rueckblick: Prognose vs. Resultat fuer den letzten ausgewerteten Spieltag.
    Gibt (tag, zeilen, kurzfassung) zurueck oder (None, [], "")."""
    r = tracking.review(tracking.load(), ctx.results, day)
    if not r:
        return None, [], ""
    d = dt.date.fromisoformat(r["day"])
    out = [f"## Rückblick: Nacht {d:%d.%m.}–{d + dt.timedelta(days=1):%d.%m.}", ""]
    out.append("| Spiel | Prognose | Resultat | Sieger | Total (Prog./Ist) | O/U-Linie |")
    out.append("|---|---|---|---|---|---|")
    for x in r["rows"]:
        fav = x["home"] if x["p_home"] >= 0.5 else x["away"]
        pf = max(x["p_home"], 1 - x["p_home"])
        ou = "–"
        if x.get("ou_hit") is not None:
            ou = f"{x['ou_pick']} {x['line_total']} ({pct(x['ou_p'])}) {'✅' if x['ou_hit'] else '❌'}"
        out.append(f"| {x['matchup']} | {fav} {pct(pf)} · {x['away']} {x['pred_away']:.0f}–{x['pred_home']:.0f} {x['home']} | "
                   f"{x['away']} {x['away_pts']}–{x['home_pts']} {x['home']} | {'✅' if x['win_hit'] else '❌'} | "
                   f"{x['total_pred']:.0f} / {x['total_real']} ({x['total_real'] - x['total_pred']:+.0f}) | {ou} |")
    sm = r["summary"]
    out.append("")
    out.append(f"**Sieger richtig:** {sm['win_hits']}/{sm['n']} ({sm['win_hits'] / sm['n']:.0%}) · "
               f"**Mittlerer Fehler:** Differenz {sm['mae_margin']:.1f} Pkt, Total {sm['mae_total']:.1f} Pkt"
               + (f" · **Over/Under:** {sm['ou_hits']}/{sm['ou_n']}" if sm["ou_n"] else ""))
    tips = r["tips"]
    if tips:
        out.append("")
        out.append("**Tipps dieser Nacht:**")
        for t in tips:
            mark = {True: "✅", False: "❌", None: "⏳", "push": "↩️"}[t["result"]]
            out.append(f"- {mark} {t['text']}" + (f" (Quote {t['odds']:.2f})" if t.get("odds") else ""))
        out.append(f"- **Ergebnis:** {r['tip_hits']}/{r['tip_n']} getroffen · "
                   f"{r['tip_profit']:+.2f} Fr. bei 1 Fr. pro Tipp (DK-Quoten)")
    short = [f"Sieger {sm['win_hits']}/{sm['n']} richtig · Ø-Fehler Total {sm['mae_total']:.0f} Pkt"]
    if sm["ou_n"]:
        short[0] += f" · O/U {sm['ou_hits']}/{sm['ou_n']}"
    for x in r["rows"]:
        short.append(f"{'✅' if x['win_hit'] else '❌'} {x['away']} {x['away_pts']}–{x['home_pts']} {x['home']} "
                     f"(Prog. {x['home'] if x['p_home'] >= 0.5 else x['away']} {pct(max(x['p_home'], 1 - x['p_home']))})")
    if tips:
        short.append(f"Tipps: {r['tip_hits']}/{r['tip_n']} · {r['tip_profit']:+.2f} Fr.")
    return r["day"], out, "\n".join(short)


def build_report(ctx: Context, detail=True, changes=None) -> tuple[str, str]:
    games = ctx.upcoming()
    if not games:
        title = "NBA-Tipps: keine Spiele"
        return title, f"# {title}\n\nIn den nächsten Tagen sind keine NBA-Spiele angesetzt.\n"
    d = ctx.game_day
    title = f"NBA-Tipps für die Nacht {d:%d.%m.}–{d + dt.timedelta(days=1):%d.%m.%Y}"
    picks: list = []
    blocks = [game_block(ctx, g, picks, detail) for g in games]
    stand = ctx.now.astimezone(TZ_CH)
    out = [f"# {title}", "",
           f"Stand: {WOCHENTAG[stand.weekday()]} {stand:%d.%m. %H:%M} Uhr · {len(games)} Spiele · "
           f"Datenbasis: {len(ctx.games)} Saisonspiele · Heimvorteil {ctx.model.hca:.1f} Pkt · "
           f"Liga-Schnitt {ctx.model.mu:.1f} Pkt/Team", ""]
    if changes:
        out.append("## Änderungen seit dem letzten Bericht")
        out += [f"- {c}" for c in changes]
        out.append("")
    out += tips_section(ctx)
    out.append("")
    out.append("## Auffälligkeiten (eigenes Modell ≠ Buchmacher)")
    out.append("_Hinweise, keine sicheren Tipps: Der Markt liegt meistens richtig, v.a. früh in der Saison._")
    if picks:
        for _, txt in sorted(picks, reverse=True)[:6]:
            out.append(f"- {txt}")
    else:
        out.append("- Keine grossen Abweichungen – Markt und Modell sind sich einig.")
    out.append("")
    out += bilanz_section(ctx)
    _, rev, _ = review_lines(ctx)
    if rev:
        out += [""] + rev
    out += ["", "## Spiele"]
    for b in blocks:
        out += ["", b]
    out += ["", "---",
            "_Wahrscheinlichkeiten = 70% Buchmacherlinie (DraftKings via ESPN) + 30% eigenes Modell (Team-Ratings, "
            "Heimvorteil, Back-to-Back, Ausfälle). Spieler-Linien: 'Over bis X' = bis zu dieser Linie liegt "
            "P(Over) ≥ 57%. Keine Garantie – Wetten mit Verlustrisiko, nur mit Geld, das du verlieren kannst._"]
    return title, "\n".join(out) + "\n"


def build_short(ctx: Context, changes=None) -> str:
    """Kurzfassung fuer Push-Nachrichten."""
    games = ctx.upcoming()
    if not games:
        return "Heute keine NBA-Spiele."
    p = ctx.plan()
    rows = []
    if changes:
        rows.append("ÄNDERUNGEN:")
        rows += [f"• {c}" for c in changes[:8]]
        rows.append("")
    if p["singles"]:
        rows.append("TIPPS (ab Mindestquote):")
        for l in p["singles"][:3]:
            rows.append(f"• {l.label} ({l.matchup}) {pct(l.p)} – ab {l.min_odds:.2f}")
    for name, (combos, prof) in (("2er", p["combo2"]), ("3er", p["combo3"])):
        if combos:
            c = combos[0]
            rows.append(f"• {name}-Kombi: " + " + ".join(l.label for l in c.legs)
                        + f" – {pct(c.p)}, ab {c.min_odds:.2f}")
    rows.append("")
    for g in games:
        f = ctx.forecast(g)
        H, A = g["home"]["abbr"], g["away"]["abbr"]
        t = _ts(g["date"]).astimezone(TZ_CH)
        ph = bets.win_prob_home(f, g.get("odds"))
        fav, pp = (H, ph) if ph >= 0.5 else (A, 1 - ph)
        s = f"{t:%H:%M} {A}@{H}: {fav} {pct(pp)}"
        if f.market_total is not None:
            po = f.p_over(f.market_total)
            side, pt = ("O", po) if po >= 0.5 else ("U", 1 - po)
            s += f" · {side}{f.market_total} {pct(pt)}"
        rows.append(s)
    return "\n".join(rows)
