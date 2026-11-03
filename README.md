# Blitzer – NBA-Wahrscheinlichkeitsrechner für Sporttip

Sammelt jeden Tag Team- und Spielerdaten der laufenden NBA-Saison, berechnet
Wahrscheinlichkeiten für die gängigen Wettoptionen und schickt dir am Nachmittag
eine kurze Zusammenfassung der Spiele der kommenden Nacht.

**Ziel:** Schnell erkennen, ob eine Sporttip-Quote *besser* ist als die faire Quote.
Nur dann hat eine Wette einen positiven Erwartungswert.

## Was berechnet wird

| Markt | Methode |
|---|---|
| Sieg (Moneyline) | Prognostizierte Punktedifferenz → Normalverteilung |
| Handicap / Spread | dito, für jede beliebige Linie |
| Over/Under Total | Prognose Gesamtpunkte → Normalverteilung, beliebige Linie |
| Teampunkte Over/Under | Prognose Teampunkte |
| Spieler Over/Under (Pkt, Reb, Ast, 3er, P+R+A) | Gewichtete Form der letzten Spiele, Gegnerstärke, Gamma-Verteilung |

**Datenquelle:** öffentliche ESPN-API (Resultate, Boxscores, Verletzungsliste,
Linien von DraftKings). Keine Anmeldung, kein API-Schlüssel nötig.

**Teammodell:** Offensiv-/Defensiv-Rating jedes Teams per gewichteter Regression
(neuere Spiele zählen mehr), Heimvorteil, Back-to-Back-Abzug, Abzug für
ausfallende Stammspieler. Die Endprognose kombiniert **70 % Buchmacherlinie + 30 % Modell**,
weil die Schlusslinien der grossen Buchmacher sehr treffsicher sind.

**Backtest Saison 2025-26** (nur Modell, ohne Marktlinie, 1135 Spiele, immer nur mit
Daten vor dem Spiel): 68.9 % richtige Sieger, Brier-Score 0.205 (Basis 0.247),
gut kalibriert (vorhergesagte 60 % → tatsächlich 63 %, 80 % → 82 %).
Spieler-Wahrscheinlichkeiten wurden im Bereich 30–70 % auf ±5 %-Punkte kalibriert.

## Täglicher Bericht

Der GitHub-Workflow `.github/workflows/daily-report.yml` läuft täglich um
**16:30 Uhr** (Sommerzeit 17:30) – also vor den Spielen, die ab ca. 01:00 Uhr Schweizer
Zeit beginnen. Er

1. lädt neue Resultate und Boxscores (`data/`),
2. schreibt den Bericht nach `reports/JJJJ-MM-TT.md` (und `reports/latest.md`),
3. eröffnet ein GitHub-Issue mit dem Bericht → du bekommst eine Benachrichtigung
   in der GitHub-App bzw. per E-Mail,
4. schickt optional eine Push-Nachricht aufs Handy.

> Geplante Workflows laufen nur auf dem Standard-Branch (`main`). Manuell starten:
> GitHub → *Actions* → *NBA Tagesbericht* → *Run workflow*.

### Push aufs Handy (optional, empfohlen)

**ntfy (am einfachsten, gratis, ohne Konto):**
1. App „ntfy“ installieren (iOS/Android).
2. Ein schwer erratbares Thema abonnieren, z.B. `blitzer-nba-8f3k2q`.
3. Im Repository unter *Settings → Secrets and variables → Actions* das Secret
   `NTFY_TOPIC` mit genau diesem Namen anlegen.

**Telegram:** Bot über @BotFather erstellen, Secrets `TELEGRAM_BOT_TOKEN` und
`TELEGRAM_CHAT_ID` anlegen.

## Eigene Sporttip-Quoten prüfen

Sporttip hat oft leicht andere Linien als DraftKings. Gib Linie und Quote ein:

```bash
python -m nba_tipp report                                # Bericht erstellen
python -m nba_tipp spiel DET                             # alle Details zu einem Spiel
python -m nba_tipp check DET total 221.5 under 1.87      # Over/Under
python -m nba_tipp check SA spread 12.5 DAL 1.90         # Handicap: DAL +12.5
python -m nba_tipp check OKC sieg CLE 2.30               # Sieg
python -m nba_tipp check DET teamtotal DET 108.5 over 1.85
python -m nba_tipp prop "Maxey" pts 26.5 over 1.85       # Spielerwette (pts|reb|ast|fg3|pra)
python -m nba_tipp backtest                              # Treffsicherheit diese Saison
```

Ausgabe: Wahrscheinlichkeit, faire Quote, Erwartungswert und ein vorsichtiger
Einsatzvorschlag (¼-Kelly). „VALUE“ erscheint erst ab +3 % Erwartungswert.

Benötigt nur Python 3.10+, keine zusätzlichen Pakete.

## Wie lese ich den Bericht?

- **faire Quote** = 1 / Wahrscheinlichkeit. Sporttip-Quote höher → Value.
- **Over lohnt bis X / Under lohnt ab Y:** Bis zu dieser Linie liegt die
  Wahrscheinlichkeit bei mindestens 57 % (Break-even bei Quote 1.85 ist 54 %).
- **Auffälligkeiten:** Spiele, bei denen das eigene Modell deutlich vom Markt
  abweicht. Das sind Hinweise zum genaueren Hinschauen, keine sicheren Tipps.

## Wichtig

- Buchmacher sind sehr gut; ein einfaches Modell schlägt sie selten dauerhaft.
  Früh in der Saison (wenige Spiele) sind die Modellwerte besonders unsicher.
- Verletzungsmeldungen kommen oft erst kurz vor Spielbeginn. Kurz vor dem Wetten
  `python -m nba_tipp spiel TEAM` nochmals ausführen.
- Nur Geld einsetzen, das du verlieren kannst. Hilfe: [sos-spielsucht.ch](https://www.sos-spielsucht.ch).
