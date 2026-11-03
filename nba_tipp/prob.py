"""Wahrscheinlichkeits- und Quoten-Hilfsfunktionen."""
import math


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def p_over(mean: float, sd: float, line: float) -> float:
    """P(X > line) fuer normalverteiltes X. Bei ganzzahligen Linien
    (Push moeglich) wird die Push-Masse herausgerechnet."""
    if sd <= 0:
        return 1.0 if mean > line else 0.0
    if float(line).is_integer():
        over = 1 - norm_cdf((line + 0.5 - mean) / sd)
        under = norm_cdf((line - 0.5 - mean) / sd)
        return over / (over + under)
    return 1 - norm_cdf((line - mean) / sd)


def american_to_decimal(odds) -> float | None:
    if odds in (None, "", "EVEN", "even"):
        return 2.0 if odds in ("EVEN", "even") else None
    try:
        o = float(str(odds).replace("+", ""))
    except ValueError:
        return None
    if o == 0:
        return None
    return 1 + (o / 100 if o > 0 else 100 / -o)


def devig(dec_a: float, dec_b: float) -> tuple[float, float]:
    """Entfernt die Buchmacher-Marge (proportionale Methode)."""
    ia, ib = 1 / dec_a, 1 / dec_b
    s = ia + ib
    return ia / s, ib / s


def fair_odds(p: float) -> float:
    return float("inf") if p <= 0 else 1 / p


def ev(p: float, decimal_odds: float) -> float:
    """Erwartungswert pro eingesetztem Franken."""
    return p * decimal_odds - 1


def kelly(p: float, decimal_odds: float) -> float:
    b = decimal_odds - 1
    if b <= 0:
        return 0.0
    return max(0.0, (b * p - (1 - p)) / b)


def _gammainc_lower_reg(a: float, x: float) -> float:
    """Regularisierte untere unvollstaendige Gammafunktion P(a, x)."""
    if x <= 0:
        return 0.0
    if x < a + 1:  # Reihenentwicklung
        term = s = 1.0 / a
        n = a
        for _ in range(500):
            n += 1
            term *= x / n
            s += term
            if abs(term) < abs(s) * 1e-12:
                break
        return s * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # Kettenbruch (Lentz) fuer die obere Funktion
    b = x + 1 - a
    c = 1 / 1e-300
    d = 1 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return 1 - math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def p_over_gamma(mean: float, sd: float, line: float) -> float:
    """P(X > line) fuer rechtsschiefe Zaehlstatistiken (Gamma-Verteilung)."""
    if mean <= 0:
        return 0.0
    shape = (mean / sd) ** 2
    scale = sd * sd / mean
    return 1 - _gammainc_lower_reg(shape, max(line, 0) / scale)
