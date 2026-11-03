import datetime as dt
import unittest

from nba_tipp.model import TeamModel, GameForecast
from nba_tipp.prob import (american_to_decimal, devig, ev, kelly, norm_cdf, p_over,
                           p_over_gamma)


class ProbTests(unittest.TestCase):
    def test_odds(self):
        self.assertAlmostEqual(american_to_decimal("-110"), 1.909, places=3)
        self.assertAlmostEqual(american_to_decimal("+150"), 2.5)
        a, b = devig(1.909, 1.909)
        self.assertAlmostEqual(a, 0.5)
        self.assertAlmostEqual(ev(0.55, 2.0), 0.10)
        self.assertAlmostEqual(kelly(0.55, 2.0), 0.10)
        self.assertEqual(kelly(0.4, 2.0), 0.0)

    def test_distributions(self):
        self.assertAlmostEqual(norm_cdf(0), 0.5)
        self.assertAlmostEqual(p_over(220, 18, 220.0), 0.5, places=6)
        self.assertGreater(p_over(225, 18, 220.5), 0.5)
        # Gamma: rechtsschief -> P(X > Mittelwert) < 50%
        self.assertLess(p_over_gamma(25, 7, 25), 0.5)
        self.assertGreater(p_over_gamma(25, 7, 10.5), 0.95)
        for a in (0.5, 3, 12, 80):  # Reihe und Kettenbruch muessen konsistent sein
            self.assertAlmostEqual(p_over_gamma(a, a ** 0.5, a + 1e-9),
                                   p_over_gamma(a, a ** 0.5, a - 1e-9), places=5)


def _game(i, home, away, hp, ap, day):
    return {"id": str(i), "date": f"2026-11-{day:02d}T00:00Z", "completed": True,
            "home": {"abbr": home}, "away": {"abbr": away}, "home_pts": hp, "away_pts": ap}


class ModelTests(unittest.TestCase):
    def test_strong_team_rated_higher(self):
        games, i = [], 0
        for day in range(1, 21):
            games.append(_game(i, "AAA", "BBB", 120, 100, day)); i += 1
            games.append(_game(i, "BBB", "AAA", 105, 115, day)); i += 1
        m = TeamModel(games, as_of=dt.datetime(2026, 11, 21, tzinfo=dt.timezone.utc))
        self.assertGreater(m.net_rating("AAA"), m.net_rating("BBB"))
        g = {"id": "x", "date": "2026-11-22T00:00Z", "home": {"abbr": "AAA"}, "away": {"abbr": "BBB"},
             "odds": {"home_spread": -10.0, "total": 220.0}}
        f = GameForecast(m, g)
        self.assertGreater(f.p_home_win(), 0.7)
        self.assertAlmostEqual(f.p_over(220.5) + (1 - f.p_over(220.5)), 1.0)
        # Kombination liegt zwischen Modell und Markt
        self.assertTrue(min(f.model_margin, 10) <= f.margin <= max(f.model_margin, 10))


if __name__ == "__main__":
    unittest.main()
