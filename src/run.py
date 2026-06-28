"""
run.py — Orchestrierung des täglichen Laufs (headless).

Ablauf (Spec §6.6):
  1. .env laden (lokal; in der Action kommen die Werte aus echten Env-Vars).
  2. RSS sammeln (collector).
  3. Newsletter holen (gmail_source) — falls aktiviert.
  4. RSS bewerten (analyst).
  5. Newsletter in Stories zerlegen (analyst).
  6. Dashboard bauen (deliver) — MUSS gelingen, sonst Exit != 0 (kein Deploy).
  7. Telegram senden (best effort, nur wenn Secrets gesetzt).
  8. E-Mail senden (best effort).
  9. seen_ids aktualisieren.

Robustheit (Spec §11): Ein Gmail-Fehler darf den RSS-Teil nicht blockieren — der
Newsletter-Teil bleibt dann leer. Telegram/E-Mail sind best effort. Nur wenn
output/dashboard.html erzeugt wurde, endet der Lauf mit Exit 0.
"""
from __future__ import annotations

import os
import sys

import analyst
import collector
import deliver
import gmail_source
from config import NEWSLETTER


def _load_dotenv(path: str = ".env") -> None:
    """Minimaler .env-Loader (ohne Zusatz-Dependency). Überschreibt keine
    bereits gesetzten Env-Vars (Action-Secrets haben Vorrang)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def main() -> int:
    _load_dotenv()

    # 2. RSS
    collected = collector.collect_all()

    # 3. Newsletter (robust: Fehler blockiert den RSS-Teil nicht)
    newsletters: list[dict] = []
    if NEWSLETTER.get("enabled", False):
        try:
            newsletters = gmail_source.fetch_newsletters()
        except Exception as exc:
            print(f"[run] Gmail fehlgeschlagen, fahre ohne Newsletter fort: {exc}")

    # 4. RSS bewerten
    analyzed = analyst.analyze_all(collected)

    # 5. Newsletter zerlegen. processed_ids = nur erfolgreich analysierte Mails;
    #    bei Claude-Ausfall bleiben Mails ungesehen und werden später erneut versucht.
    stories: list[dict] = []
    processed_ids: list[str] = []
    try:
        stories, processed_ids = analyst.analyze_newsletters(newsletters)
    except Exception as exc:
        print(f"[run] Newsletter-Analyse fehlgeschlagen: {exc}")

    # 6. Dashboard (Pflicht — ohne gültiges HTML kein Deploy)
    try:
        path = deliver.build_dashboard(analyzed, stories)
    except Exception as exc:
        print(f"[run] FATAL: Dashboard konnte nicht erzeugt werden: {exc}")
        return 1
    if not os.path.exists(path):
        print("[run] FATAL: dashboard.html fehlt nach build_dashboard")
        return 1

    # 7. Telegram (best effort)
    try:
        deliver.send_telegram(analyzed, stories)
    except Exception as exc:
        print(f"[run] Telegram-Fehler (ignoriert): {exc}")

    # 8. E-Mail (best effort)
    try:
        deliver.send_email(analyzed, stories)
    except Exception as exc:
        print(f"[run] E-Mail-Fehler (ignoriert): {exc}")

    # 9. seen_ids aktualisieren — NUR Mails, deren Analyse erfolgreich war.
    #    Bei Claude-Ausfall (z. B. API-Limit) bleiben die Mails ungesehen und
    #    werden im nächsten Lauf erneut verarbeitet (kein stiller Verlust).
    if processed_ids:
        try:
            gmail_source.mark_seen(processed_ids)
        except Exception as exc:
            print(f"[run] seen_ids-Update fehlgeschlagen (ignoriert): {exc}")

    n_articles = sum(len(v) for v in analyzed.values())
    print(f"[run] fertig: {n_articles} RSS-Artikel, {len(stories)} Newsletter-Stories.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
