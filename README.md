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

## Wett-Vorschläge: sicher *und* profitabel

Jeder Bericht beginnt mit konkreten Vorschlägen:

- **Einzelwetten:** alle Optionen mit mindestens +3 % Erwartungswert (zur DraftKings-Quote),
  sortiert nach Trefferwahrscheinlichkeit, also die sichersten profitablen zuerst.
- **Sichere 2er-Kombi** (Gesamtquote ≥ 1.60) und **3er-Kombi** (≥ 2.40): pro Spiel höchstens
  ein Tipp (sonst hängen die Ereignisse zusammen), Trefferchance = Produkt der Einzelchancen.
  Bevorzugt wird die Kombi mit der höchsten Trefferchance unter den profitablen.
- **Sichere Spieler-Linien:** für die konstantesten Spieler die Linie, die mit ca. 75 % trifft.
- Zu jedem Tipp die **Mindestquote**: Nur wetten, wenn Sporttip mindestens so viel bietet.

## Immer auf dem neusten Stand

Bei jedem Lauf werden neu geladen: Resultate und Boxscores, Verletzungsliste, News
(ESPN-Schlagzeilen der letzten 36 h pro Team), aktuelle Linien. Das Modell wird jedes
Mal neu berechnet (neuere Spiele zählen mehr, Form der letzten 5 Spiele wird angezeigt).

Der GitHub-Workflow `.github/workflows/daily-report.yml` läuft:

| Zeit (Winter / Sommer) | Was passiert |
|---|---|
| 16:30 / 17:30 | **Hauptbericht** → neues GitHub-Issue + Push |
| 20:30 / 21:30, 23:15 / 00:15, 00:30 / 01:30 | **Update**: nur wenn sich etwas Relevantes geändert hat (neuer Ausfall, Linie bewegt sich ≥ 1.5 Pkt, Siegchance ±5 %, Tipp neu/gestrichen) → Kommentar im Issue + Push |

Zusätzlich führt das Tool eine **Bilanz**: Alle Tipps werden gespeichert (`data/tipps.json`)
und nach Spielende ausgewertet (Trefferquote, Gewinn/Verlust bei 1 Fr. Einsatz). So siehst
du jederzeit, ob die Vorschläge aktuell funktionieren.

Gespeichert wird alles unter `reports/` und `data/`; du bekommst die Benachrichtigungen
in der GitHub-App bzw. per E-Mail und optional als Push aufs Handy.

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
python -m nba_tipp update                                # aktualisieren, Änderungen anzeigen
python -m nba_tipp tipps                                 # nur Einzel- und Kombi-Vorschläge
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

**Schritt-für-Schritt-Anleitung fürs Handy:** [ANLEITUNG_APP.md](ANLEITUNG_APP.md)

## Wichtig

- Buchmacher sind sehr gut; ein einfaches Modell schlägt sie selten dauerhaft.
  Früh in der Saison (wenige Spiele) sind die Modellwerte besonders unsicher.
- Verletzungsmeldungen kommen oft erst kurz vor Spielbeginn. Kurz vor dem Wetten
  `python -m nba_tipp spiel TEAM` nochmals ausführen.
- „Sicher“ gibt es bei Wetten nicht: Auch ein 75-%-Tipp verliert jedes vierte Mal.
  Kombis verlieren öfter als Einzelwetten, und die Marge des Buchmachers multipliziert sich.
- Nur Geld einsetzen, das du verlieren kannst. Hilfe: [sos-spielsucht.ch](https://www.sos-spielsucht.ch).
