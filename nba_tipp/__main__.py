"""Kommandozeile.

  python -m nba_tipp report                 # Tageszusammenfassung -> reports/JJJJ-MM-TT.md
  python -m nba_tipp spiel DET              # Detail zu einem Spiel (Team-Kuerzel)
  python -m nba_tipp check DET total 221.5 over 1.87       # eigene Sporttip-Quote pruefen
  python -m nba_tipp check DET spread -3.5 DET 1.90
  python -m nba_tipp check DET sieg PHI 2.25
  python -m nba_tipp prop "Cunningham" pts 26.5 over 1.85  # Spielerwette pruefen
  python -m nba_tipp backtest               # Treffsicherheit des Modells auf dieser Saison
"""
import argparse
import datetime as dt
import math
import os
import sys

from .model import TeamModel, GameForecast
from .players import STATS, LABEL, Projection, find_player
from .prob import ev, kelly, fair_odds
from .report import Context, build_report, build_short, game_block, pct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find_game(ctx, team):
    g = ctx.find_upcoming(team.upper())
    if g:
        return g
    sys.exit(f"Kein anstehendes Spiel fuer {team} gefunden.")


def _verdict(p, odds):
    e = ev(p, odds)
    k = kelly(p, odds)
    print(f"Wahrscheinlichkeit: {pct(p)} · faire Quote {fair_odds(p):.2f} · deine Quote {odds:.2f}")
    print(f"Erwartungswert: {e * 100:+.1f}% pro Einsatz", end="")
    if e >= 0.03:
        print(f" → VALUE. Kelly-Anteil {k * 100:.1f}% (empfohlen max. 1/4 davon: {k * 25:.1f}% der Bankroll)")
    elif e > 0:
        print(" → nur knapp positiv, innerhalb der Modellunsicherheit – eher auslassen.")
    else:
        print(" → kein Value, Finger weg.")


def cmd_report(args):
    ctx = Context()
    title, md = build_report(ctx, detail=not args.kurz)
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    path = os.path.join(ROOT, "reports", f"{ctx.now.astimezone().date():%Y-%m-%d}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(ROOT, "reports", "latest.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(ROOT, "reports", "latest_title.txt"), "w", encoding="utf-8") as f:
        f.write(title)
    with open(os.path.join(ROOT, "reports", "latest_kurz.txt"), "w", encoding="utf-8") as f:
        f.write(build_short(ctx))
    print(md)
    print(f"\n[gespeichert: {path}]", file=sys.stderr)


def cmd_spiel(args):
    ctx = Context()
    g = _find_game(ctx, args.team)
    print(game_block(ctx, g, [], detail=True))


def cmd_check(args):
    ctx = Context()
    g = _find_game(ctx, args.team)
    f = ctx.forecast(g)
    H, A = g["home"]["abbr"], g["away"]["abbr"]
    m = args.markt.lower()
    print(f"{A} @ {H}")
    if m in ("sieg", "ml", "moneyline"):
        side = args.wert.upper()
        p = f.p_home_win() if side == H else 1 - f.p_home_win()
        print(f"Sieg {side}")
    elif m in ("total", "ou"):
        line = float(args.wert)
        side = args.seite.lower()
        p = f.p_over(line)
        p = p if side == "over" else 1 - p
        print(f"Total {side} {line} (Prognose {f.total:.1f})")
    elif m in ("spread", "handicap"):
        line = float(args.wert)
        side = args.seite.upper()
        home_line = line if side == H else -line
        p = f.p_home_cover(home_line)
        p = p if side == H else 1 - p
        print(f"Handicap {side} {line:+.1f} (Prognose Diff. {H} {f.margin:+.1f})")
    elif m in ("teamtotal", "tt"):
        team, line = args.wert.upper(), float(args.seite)
        side = (args.extra or "over").lower()
        p = f.p_team_over("home" if team == H else "away", line)
        p = p if side == "over" else 1 - p
        print(f"Teampunkte {team} {side} {line}")
        _verdict(p, float(args.quote_tt))
        return
    else:
        sys.exit("Markt muss sieg | total | spread | teamtotal sein")
    _verdict(p, float(args.quote if m not in ("sieg", "ml", "moneyline") else args.seite))


def cmd_prop(args):
    ctx = Context()
    name = find_player(ctx.logs, args.spieler)
    if not name:
        sys.exit("Spieler nicht gefunden.")
    e = ctx.logs[name]
    stat = args.stat.lower()
    if stat not in STATS:
        sys.exit(f"Statistik muss eine von {', '.join(STATS)} sein")
    opp = None
    g = ctx.find_upcoming(e["team"])
    if g:
        opp = g["away"]["abbr"] if g["home"]["abbr"] == e["team"] else g["home"]["abbr"]
    p = Projection(name, e["team"], e["logs"][-25:], ctx.opp_factor(opp) if opp else 1.0)
    pr = p.p_over(stat, args.linie)
    pr = pr if args.seite.lower() == "over" else 1 - pr
    print(f"{name} ({e['team']}{' vs ' + opp if opp else ''}) · {p.games} Spiele · {p.minutes:.0f} Min")
    print(f"{LABEL[stat]}: Projektion {p.mean[stat]:.1f} ± {p.sd[stat]:.1f} · letzte 5: "
          + ", ".join(f"{l[stat]:.0f}" for l in e["logs"][-5:]))
    inj = [i for i in ctx.injuries.get(e["team"], []) if i["name"] == name]
    if inj:
        print(f"ACHTUNG Verletzungsstatus: {inj[0]['status']} – {inj[0]['comment']}")
    print(f"{args.seite} {args.linie}")
    _verdict(pr, args.quote)


def cmd_backtest(args):
    """Walk-forward: fuer jeden Tag nur mit vorherigen Spielen fitten, dann vorhersagen."""
    ctx = Context()
    games = sorted(ctx.games, key=lambda g: g["date"])
    by_day = {}
    for g in games:
        by_day.setdefault(g["date"][:10], []).append(g)
    days = sorted(by_day)
    n = brier = ll = correct = 0
    abs_m = abs_t = 0.0
    base_brier = 0.0
    for i, d in enumerate(days):
        past = [g for dd in days[:i] for g in by_day[dd]]
        if len(past) < args.min_spiele:
            continue
        cutoff = dt.datetime.fromisoformat(d + "T00:00:00+00:00")
        mdl = TeamModel(past, as_of=cutoff)
        for g in by_day[d]:
            gg = dict(g)
            gg["odds"] = None
            f = GameForecast(mdl, gg)
            p = f.p_home_win()
            y = 1 if g["home_pts"] > g["away_pts"] else 0
            brier += (p - y) ** 2
            base_brier += (0.56 - y) ** 2
            ll += -math.log(max(1e-9, p if y else 1 - p))
            correct += int((p > 0.5) == bool(y))
            abs_m += abs((g["home_pts"] - g["away_pts"]) - f.margin)
            abs_t += abs((g["home_pts"] + g["away_pts"]) - f.total)
            n += 1
    if not n:
        sys.exit("Zu wenige Spiele fuer einen Backtest.")
    print(f"Backtest (nur Modell, ohne Marktlinie) ueber {n} Spiele")
    print(f"Treffer Sieger: {correct / n:.1%}")
    print(f"Brier-Score:    {brier / n:.4f} (Basis 'Heimteam 56%': {base_brier / n:.4f}, kleiner = besser)")
    print(f"Log-Loss:       {ll / n:.4f}")
    print(f"Mittl. Fehler Differenz: {abs_m / n:.1f} Pkt · Total: {abs_t / n:.1f} Pkt")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="nba_tipp", description="NBA-Wahrscheinlichkeitsrechner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report", help="Tageszusammenfassung erstellen")
    r.add_argument("--kurz", action="store_true", help="ohne Spielertabellen")
    r.set_defaults(fn=cmd_report)
    s = sub.add_parser("spiel", help="Detail zu einem Spiel")
    s.add_argument("team")
    s.set_defaults(fn=cmd_spiel)
    c = sub.add_parser("check", help="Sporttip-Quote fuer ein Spiel pruefen")
    c.add_argument("team", help="Kuerzel eines der beiden Teams, z.B. DET")
    c.add_argument("markt", help="sieg | total | spread | teamtotal")
    c.add_argument("wert", help="sieg: Team · total/spread: Linie · teamtotal: Team")
    c.add_argument("seite", help="sieg: Quote · total: over/under · spread: Team · teamtotal: Linie")
    c.add_argument("quote", nargs="?", help="Dezimalquote (bei teamtotal: over/under)")
    c.add_argument("quote_tt", nargs="?", help="nur teamtotal: Dezimalquote")
    c.set_defaults(fn=cmd_check, extra=None)
    p = sub.add_parser("prop", help="Spielerwette pruefen")
    p.add_argument("spieler")
    p.add_argument("stat", help="pts | reb | ast | fg3 | pra")
    p.add_argument("linie", type=float)
    p.add_argument("seite", choices=["over", "under"])
    p.add_argument("quote", type=float)
    p.set_defaults(fn=cmd_prop)
    b = sub.add_parser("backtest", help="Modellqualitaet pruefen")
    b.add_argument("--min-spiele", type=int, default=60)
    b.set_defaults(fn=cmd_backtest)
    args = ap.parse_args(argv)
    if args.cmd == "check" and args.markt.lower() in ("teamtotal", "tt"):
        args.extra = args.quote
    args.fn(args)


if __name__ == "__main__":
    main()
