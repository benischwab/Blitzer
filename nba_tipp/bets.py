"""Wettvorschlaege: sichere und zugleich profitable Einzelwetten und Kombiwetten.

Grundidee
- Fuer jede Wettoption (Sieg, Handicap, Over/Under) wird die Wahrscheinlichkeit p
  berechnet (Buchmacher + Modell kombiniert).
- "Profitabel" heisst: Erwartungswert p * Quote - 1 > 0. Als Referenz dient die
  DraftKings-Quote; fuer Sporttip wird die *Mindestquote* angegeben, ab der die
  Wette lohnt (inkl. Sicherheitspuffer).
- "Sicher" heisst: hohe Trefferwahrscheinlichkeit. Unter den profitablen Optionen
  werden die mit der hoechsten Wahrscheinlichkeit bevorzugt.
- Kombis: nur ein Tipp pro Spiel (sonst sind die Ereignisse abhaengig),
  Gesamtwahrscheinlichkeit = Produkt, Gesamtquote = Produkt.
"""
import itertools
import math

from .model import MARKET_WEIGHT
from .prob import american_to_decimal, devig

MIN_EDGE = 0.03          # Sicherheitspuffer fuer die Mindestquote (+3 % Erwartungswert)
MIN_P_SINGLE = 0.55
MIN_P_LEG = 0.60         # Mindestwahrscheinlichkeit pro Kombi-Tipp
MAX_LEGS_POOL = 16


def win_prob_home(f, odds):
    """Siegwahrscheinlichkeit Heimteam: Moneyline-Markt (ohne Marge) + Modell."""
    dh = american_to_decimal((odds or {}).get("ml_home"))
    da = american_to_decimal((odds or {}).get("ml_away"))
    if dh and da:
        mk, _ = devig(dh, da)
        return MARKET_WEIGHT * mk + (1 - MARKET_WEIGHT) * f.p_home_win(model_only=True)
    return f.p_home_win()


class Leg:
    def __init__(self, game, market, side, line, p, dk_american=None):
        self.game = game
        self.game_id = game["id"]
        self.matchup = f"{game['away']['abbr']} @ {game['home']['abbr']}"
        self.market, self.side, self.line, self.p = market, side, line, p
        self.dk = american_to_decimal(dk_american) if dk_american else None

    @property
    def label(self):
        if self.market == "ml":
            return f"Sieg {self.side}"
        if self.market == "spread":
            return f"{self.side} {self.line:+.1f}"
        return f"{'Over' if self.side == 'over' else 'Under'} {self.line}"

    @property
    def ev(self):
        return None if self.dk is None else self.p * self.dk - 1

    @property
    def min_odds(self):
        return (1 + MIN_EDGE) / self.p

    def to_dict(self):
        return {"game_id": self.game_id, "matchup": self.matchup, "market": self.market,
                "side": self.side, "line": self.line, "p": round(self.p, 4), "dk": self.dk,
                "label": self.label}


def game_legs(ctx, g):
    f = ctx.forecast(g)
    odds = g.get("odds") or {}
    H, A = g["home"]["abbr"], g["away"]["abbr"]
    legs = []
    ph = win_prob_home(f, odds)
    legs.append(Leg(g, "ml", H, None, ph, odds.get("ml_home")))
    legs.append(Leg(g, "ml", A, None, 1 - ph, odds.get("ml_away")))
    if "home_spread" in odds:
        hs = odds["home_spread"]
        pc = f.p_home_cover(hs)
        legs.append(Leg(g, "spread", H, hs, pc, odds.get("spread_odds_home")))
        legs.append(Leg(g, "spread", A, -hs, 1 - pc, odds.get("spread_odds_away")))
    if "total" in odds:
        L = odds["total"]
        po = f.p_over(L)
        legs.append(Leg(g, "total", "over", L, po, odds.get("total_odds_over")))
        legs.append(Leg(g, "total", "under", L, 1 - po, odds.get("total_odds_under")))
    return legs


def all_legs(ctx, games):
    return [leg for g in games for leg in game_legs(ctx, g)]


def safe_singles(legs, n=5):
    """Profitable Tipps (EV > 0 zur DK-Quote), sortiert nach Sicherheit.
    Reicht das nicht, wird mit den wahrscheinlichsten Tipps aufgefuellt (dann zaehlt
    die Mindestquote)."""
    pool = [l for l in legs if l.p >= MIN_P_SINGLE and l.dk]
    prof = sorted((l for l in pool if l.ev >= MIN_EDGE), key=lambda l: (-l.p, -l.ev))
    rest = sorted((l for l in pool if l.ev < MIN_EDGE and l.dk >= 1.3), key=lambda l: (-l.ev, -l.p))
    return prof[:n], rest[:max(0, 3 - len(prof))]


class Combo:
    def __init__(self, legs):
        self.legs = legs
        self.p = math.prod(l.p for l in legs)
        self.has_dk = all(l.dk for l in legs)
        self.dk = math.prod(l.dk for l in legs) if self.has_dk else None
        self.ev = self.p * self.dk - 1 if self.has_dk else None
        self.min_odds = (1 + MIN_EDGE) / self.p
        # Schaetzung der Buchmacherquote, falls (noch) keine DK-Quote: faire Quote - 5 % Marge
        self.est_odds = self.dk if self.has_dk else math.prod(0.95 / l.p for l in legs)

    def to_dict(self):
        return {"legs": [l.to_dict() for l in self.legs], "p": round(self.p, 4), "dk": round(self.dk, 3)}


def best_combos(legs, size, min_odds, n=1):
    """Kombi mit maximaler Trefferwahrscheinlichkeit unter den profitablen (EV>0).
    Gibt (kombis, profitabel?) zurueck."""
    def combos(pool):
        res = []
        for combo in itertools.combinations(pool, size):
            if len({l.game_id for l in combo}) < size:
                continue
            c = Combo(list(combo))
            if c.est_odds >= min_odds:
                res.append(c)
        return res

    # 1) profitabel zur DraftKings-Quote, davon die sicherste
    pool = sorted((l for l in legs if l.dk and l.p >= MIN_P_LEG), key=lambda l: -(l.p * l.dk))
    prof = sorted((c for c in combos(pool[:MAX_LEGS_POOL]) if c.ev >= MIN_EDGE), key=lambda c: (-c.p, -c.ev))
    if prof:
        return prof[:n], True
    # 2) sonst: sicherste Kombi (auch Spiele ohne DK-Linie, dann nur Sieg-Tipps),
    #    lohnt nur, wenn Sporttip mindestens die Mindestquote bietet
    pool = sorted((l for l in legs if l.p >= MIN_P_LEG and (l.dk or l.market == "ml")),
                  key=lambda l: -l.p)[:MAX_LEGS_POOL]
    return sorted(combos(pool), key=lambda c: -c.p)[:n], False


def consistent_props(ctx, games, n=5, target=0.75):
    """Spieler-Linien mit hoher Trefferquote: fuer die konstantesten Spieler die
    hoechste Linie, bei der P(Over) noch >= target ist."""
    rows = []
    for g in games:
        H, A = g["home"]["abbr"], g["away"]["abbr"]
        for team, opp in ((H, A), (A, H)):
            for p in ctx.projections(team, opp):
                for stat in ("pts", "reb", "ast", "pra"):
                    m, sd = p.mean[stat], p.sd[stat]
                    if m < (12 if stat in ("pts", "pra") else 5):
                        continue
                    line = None
                    for k in range(0, 40):
                        cand = math.floor(m) + 0.5 - k
                        if cand < 0:
                            break
                        if p.p_over(stat, cand) >= target:
                            line = cand
                            break
                    if line is None:
                        continue
                    rows.append((sd / m, p, stat, line, p.p_over(stat, line), f"{g['away']['abbr']} @ {H}"))
    rows.sort(key=lambda r: r[0])
    seen, out = set(), []
    for r in rows:
        if r[1].name in seen:
            continue
        seen.add(r[1].name)
        out.append(r)
        if len(out) >= n:
            break
    return out
