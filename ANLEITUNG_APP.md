# Anleitung: NBA-Tipps aufs Handy

Zwei Wege – du kannst beide nutzen:

- **A) ntfy-App** → kurze Push-Nachricht mit den Tipps (empfohlen, ~5 Minuten)
- **B) GitHub-App** → ganzer Bericht mit allen Spielen und Tabellen

---

## A) Push-Nachrichten mit ntfy

### Schritt 1 – App installieren
1. Öffne den **App Store** (iPhone) bzw. **Google Play** (Android).
2. Suche nach **ntfy** (Symbol: weisses Glöckchen, Entwickler „Philipp Heckel“).
3. Installieren und öffnen.
4. Fragt die App nach **Mitteilungen erlauben** → **Erlauben** tippen.

### Schritt 2 – Thema abonnieren
1. In der App unten rechts auf **+** tippen.
2. Bei **Topic name** genau eingeben:

   ```
   blitzer-nba-88e29717
   ```

   (Den Namen nicht weitergeben – wer ihn kennt, kann deine Nachrichten mitlesen.)
3. **Use another server** NICHT anhaken (Standard `ntfy.sh` bleibt).
4. **Subscribe** tippen. Das Thema erscheint jetzt in der Liste.

### Schritt 3 – Thema bei GitHub hinterlegen (am Computer am einfachsten)
1. Öffne <https://github.com/benischwab/Blitzer/settings/secrets/actions>
   (oder: Repository **Blitzer** → **Settings** → links **Secrets and variables** → **Actions**).
2. Grüner Knopf **New repository secret**.
3. **Name:** `NTFY_TOPIC`
4. **Secret:** `blitzer-nba-88e29717`
5. **Add secret** klicken.

### Schritt 4 – Testen
1. Öffne <https://github.com/benischwab/Blitzer/actions/workflows/daily-report.yml>.
2. Rechts **Run workflow** → Mode **report** → grüner Knopf **Run workflow**.
3. Nach 1–2 Minuten kommt die Push-Nachricht aufs Handy.

Ab jetzt kommt die Nachricht automatisch:
- **16:30 Uhr** (Sommerzeit 17:30): Tagesbericht mit Tipps und Kombis
- **20:30 / 23:15 / 00:30 Uhr**: nur wenn sich etwas geändert hat (Ausfall, Linie, Tipp)

Tipp auf die Nachricht öffnet den ausführlichen Bericht bei GitHub.

---

## B) Ganzer Bericht in der GitHub-App

1. **GitHub** aus dem App Store / Google Play installieren und mit deinem Konto
   (`benischwab`) anmelden.
2. Mitteilungen erlauben, wenn gefragt.
3. In der App: **Profil** (unten rechts) → **Zahnrad / Settings** → **Notifications**
   → Push-Benachrichtigungen einschalten (mindestens „Participating“ / „Mentions“).
4. Jeder neue Bericht ist ein **Issue** im Repository Blitzer und erwähnt dich – du
   bekommst also eine Mitteilung. Zu finden unter: Repository **Blitzer** → **Issues**.
5. Updates am Abend erscheinen als **Kommentar** im gleichen Issue.

---

## So nutzt du den Bericht beim Wetten auf Sporttip

1. Bericht öffnen → Abschnitt **Wett-Vorschläge**.
2. Tipp auf Sporttip suchen (gleiches Spiel, gleiche Linie, z.B. „DAL +12.5“).
3. **Sporttip-Quote mit der Mindestquote vergleichen:**
   - Sporttip-Quote **≥ Mindestquote** → Wette lohnt sich.
   - Sporttip-Quote **< Mindestquote** → auslassen.
4. Bei Kombis gilt dasselbe für die **Gesamtquote** der Kombi.
5. Hat Sporttip eine andere Linie (z.B. 221.5 statt 218.5)? Am Computer prüfen mit:

   ```
   python -m nba_tipp check DET total 221.5 under 1.87
   ```

6. Einsatz klein halten (z.B. 1–3 % deines Wettbudgets pro Tipp). Auch Tipps mit
   70 % Chance gehen regelmässig verloren.

Hilfe bei Spielsucht: [sos-spielsucht.ch](https://www.sos-spielsucht.ch) · Tel. 0800 040 080
