"""Team-Ratings (Offensive/Defensive) und Spielprognosen.

Modell pro Spiel und Team:
    Punkte = mu + Heimvorteil/2 * (+1 Heim | -1 Auswaerts) + Off[team] - Def[gegner]

Geschaetzt per gewichteter Ridge-Regression: neuere Spiele zaehlen mehr
(Halbwertszeit), Ratings werden zum Ligadurchschnitt hin geschrumpft, damit
wenige Spiele am Saisonbeginn nicht ueberbewertet werden.
"""
import datetime as dt
import math

from .prob import norm_cdf

HALF_LIFE_DAYS = 40.0
RIDGE = 4.0            # Schrumpfung Richtung Liga-Schnitt (per Backtest 2025-26 gewaehlt)
HCA_PRIOR = 2.5        # Heimvorteil in Punkten (Prior)
HCA_RIDGE = 40.0
# Prognosefehler (Standardabweichung). Reines Modell: out-of-sample-Backtest 2025-26
# (Differenz 14.6, Total 21.0). Mit Buchmacherlinie kleiner (Schlusslinien ~12.5 / ~18).
MARGIN_SD_MODEL, TOTAL_SD_MODEL = 14.5, 21.0
MARGIN_SD_MARKET, TOTAL_SD_MARKET = 13.0, 18.5
B2B_PENALTY = 1.5      # Punkte Abzug am 2. Tag eines Back-to-Back
MARKET_WEIGHT = 0.70   # Gewicht der Buchmacherlinie bei der Kombination


def _solve(a, b):
    """Gauss-Elimination mit Pivotsuche (kleines, dichtes System)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        piv = m[c][c]
        if abs(piv) < 1e-12:
            continue
        for r in range(n):
            if r != c and m[r][c]:
                f = m[r][c] / piv
                row_c = m[c]
                row_r = m[r]
                for k in range(c, n + 1):
                    row_r[k] -= f * row_c[k]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def _gdate(g):
    return dt.datetime.fromisoformat(g["date"].replace("Z", "+00:00"))


class TeamModel:
    def __init__(self, games: list[dict], as_of: dt.datetime | None = None):
        self.games = sorted((g for g in games if g.get("completed")), key=_gdate)
        self.as_of = as_of or (_gdate(self.games[-1]) if self.games else dt.datetime.now(dt.timezone.utc))
        self._fit()

    def _fit(self):
        teams = sorted({g["home"]["abbr"] for g in self.games} | {g["away"]["abbr"] for g in self.games})
        self.teams = teams
        n = len(teams)
        idx = {t: i for i, t in enumerate(teams)}
        # Parameter: [mu, hca, off_0..off_n-1, def_0..def_n-1]
        P = 2 + 2 * n
        ata = [[0.0] * P for _ in range(P)]
        atb = [0.0] * P
        obs = []
        for g in self.games:
            age = (self.as_of - _gdate(g)).total_seconds() / 86400
            w = 0.5 ** (max(age, 0) / HALF_LIFE_DAYS)
            h = 0.0 if g.get("neutral") else 0.5
            H, A = idx[g["home"]["abbr"]], idx[g["away"]["abbr"]]
            for off, de, sign, pts in ((H, A, 1, g["home_pts"]), (A, H, -1, g["away_pts"])):
                # hca-Koeffizient: +0.5 fuer Heim, -0.5 fuer Gast
                x = {0: 1.0, 1: sign * h, 2 + off: 1.0, 2 + n + de: -1.0}
                obs.append((x, pts, w))
                for i, xi in x.items():
                    atb[i] += w * xi * pts
                    for j, xj in x.items():
                        ata[i][j] += w * xi * xj
        for i in range(2, P):
            ata[i][i] += RIDGE
        ata[1][1] += HCA_RIDGE
        atb[1] += HCA_RIDGE * HCA_PRIOR
        if not obs:
            ata[0][0] += 1
            atb[0] += 113.0
        beta = _solve(ata, atb)
        self.mu, self.hca = beta[0], beta[1]
        self.off = {t: beta[2 + i] for t, i in idx.items()}
        self.de = {t: beta[2 + n + i] for t, i in idx.items()}
        # Residuen -> Streuung von Differenz und Total schaetzen
        res_m, res_t, wsum = 0.0, 0.0, 0.0
        for g in self.games:
            ph, pa = self.expected_points(g["home"]["abbr"], g["away"]["abbr"], g.get("neutral", False))
            age = (self.as_of - _gdate(g)).total_seconds() / 86400
            w = 0.5 ** (max(age, 0) / HALF_LIFE_DAYS)
            res_m += w * ((g["home_pts"] - g["away_pts"]) - (ph - pa)) ** 2
            res_t += w * ((g["home_pts"] + g["away_pts"]) - (ph + pa)) ** 2
            wsum += w
        # In-sample-Residuen (nur Info; fuer Prognosen werden die Backtest-Werte genutzt)
        self.fit_margin_sd = math.sqrt(res_m / wsum) if wsum else 0.0
        self.fit_total_sd = math.sqrt(res_t / wsum) if wsum else 0.0

    def expected_points(self, home, away, neutral=False):
        h = 0.0 if neutral else self.hca / 2
        ph = self.mu + h + self.off.get(home, 0) - self.de.get(away, 0)
        pa = self.mu - h + self.off.get(away, 0) - self.de.get(home, 0)
        return ph, pa

    def net_rating(self, team):
        return self.off.get(team, 0) + self.de.get(team, 0)

    def played_yesterday(self, team, game_time: dt.datetime) -> bool:
        for g in reversed(self.games):
            if team in (g["home"]["abbr"], g["away"]["abbr"]):
                hours = (game_time - _gdate(g)).total_seconds() / 3600
                return 0 < hours < 30
        return False


class GameForecast:
    """Kombinierte Prognose (Modell + Markt) fuer ein kommendes Spiel."""

    def __init__(self, model: TeamModel, game: dict, adj_home=0.0, adj_away=0.0):
        self.game = game
        h, a = game["home"]["abbr"], game["away"]["abbr"]
        t = _gdate(game)
        ph, pa = model.expected_points(h, a, game.get("neutral", False))
        self.b2b = {h: model.played_yesterday(h, t), a: model.played_yesterday(a, t)}
        ph += adj_home - (B2B_PENALTY if self.b2b[h] else 0)
        pa += adj_away - (B2B_PENALTY if self.b2b[a] else 0)
        self.model_home, self.model_away = ph, pa
        self.model_margin = ph - pa
        self.model_total = ph + pa
        odds = game.get("odds") or {}
        self.market_margin = -odds["home_spread"] if "home_spread" in odds else None
        self.market_total = odds.get("total")
        self.margin_sd = MARGIN_SD_MODEL if self.market_margin is None else MARGIN_SD_MARKET
        self.total_sd = TOTAL_SD_MODEL if self.market_total is None else TOTAL_SD_MARKET
        w = MARKET_WEIGHT
        self.margin = self.model_margin if self.market_margin is None else w * self.market_margin + (1 - w) * self.model_margin
        self.total = self.model_total if self.market_total is None else w * self.market_total + (1 - w) * self.model_total
        self.home_pts = (self.total + self.margin) / 2
        self.away_pts = (self.total - self.margin) / 2

    # --- Wahrscheinlichkeiten -------------------------------------------
    def _msd(self, model_only):
        return MARGIN_SD_MODEL if model_only else self.margin_sd

    def _tsd(self, model_only):
        return TOTAL_SD_MODEL if model_only else self.total_sd

    def p_home_win(self, model_only=False):
        m = self.model_margin if model_only else self.margin
        return norm_cdf(m / self._msd(model_only))

    def p_home_cover(self, home_spread, model_only=False):
        """P(Heimteam deckt Handicap), z.B. home_spread=-4.5."""
        from .prob import p_over
        m = self.model_margin if model_only else self.margin
        return p_over(m, self._msd(model_only), -home_spread)

    def p_over(self, line, model_only=False):
        from .prob import p_over
        t = self.model_total if model_only else self.total
        return p_over(t, self._tsd(model_only), line)

    def p_team_over(self, side, line):
        from .prob import p_over
        mean = self.home_pts if side == "home" else self.away_pts
        # Teampunkte streuen ~ 13 Pkt
        return p_over(mean, 13.0, line)

    def value_line_total(self, threshold=0.57):
        """Hoechste Linie, bei der Over noch >= threshold, tiefste fuer Under."""
        base = math.floor(self.total) + 0.5
        over = under = None
        for k in range(-30, 31):
            line = base + k
            if self.p_over(line) >= threshold:
                over = line if over is None or line > over else over
            if 1 - self.p_over(line) >= threshold:
                under = line if under is None or line < under else under
        return over, under
