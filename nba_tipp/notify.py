"""Versendet die Kurzfassung per Push (ntfy.sh) und/oder Telegram, falls konfiguriert.

Umgebungsvariablen (als GitHub-Secrets hinterlegen):
  NTFY_TOPIC           – frei gewaehlter, geheimer Themenname fuer die ntfy-App
  TELEGRAM_BOT_TOKEN   – Token deines Telegram-Bots (@BotFather)
  TELEGRAM_CHAT_ID     – deine Chat-ID
  REPORT_URL           – Link auf den ausfuehrlichen Bericht (optional)
"""
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def main():
    rep = os.path.join(ROOT, "reports")
    title = open(os.path.join(rep, "latest_title.txt"), encoding="utf-8").read().strip()
    body = open(os.path.join(rep, "latest_kurz.txt"), encoding="utf-8").read().strip()
    url = os.environ.get("REPORT_URL", "")
    sent = False
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        payload = {"topic": topic, "title": title, "message": body, "tags": ["basketball"]}
        if url:
            payload["click"] = url
        print("ntfy:", _post("https://ntfy.sh/", payload))
        sent = True
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if tok and chat:
        text = f"{title}\n\n{body}" + (f"\n\nDetails: {url}" if url else "")
        print("telegram:", _post(f"https://api.telegram.org/bot{tok}/sendMessage",
                                 {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True}))
        sent = True
    if not sent:
        print("Kein Push-Kanal konfiguriert (NTFY_TOPIC oder TELEGRAM_*).", file=sys.stderr)


if __name__ == "__main__":
    main()
