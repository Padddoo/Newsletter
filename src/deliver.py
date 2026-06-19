"""
deliver.py — Zustellung des Briefings.

Drei Kanäle:
  1. build_dashboard(): output/dashboard.html mit 2 Tabs (AI News, Newsletter)
     inkl. Cross-Posting der Top-Newsletter-Stories in den AI-News-Tab.
  2. send_telegram(): kompakter Push (nur wenn TELEGRAM_*-Secrets gesetzt sind).
  3. send_email(): das Briefing per Gmail (gmail.send) an die eigene Adresse.

Die Tab-Logik iteriert über die bewerteten RSS-Themen, sodass ein weiteres Thema
(z. B. reaktiviertes MedTech) später ohne Umbau als zusätzlicher Tab andockt.
"""
from __future__ import annotations

import base64
import os
from datetime import datetime
from email.message import EmailMessage
from html import escape as esc

import requests

import gmail_source
from config import (DASHBOARD_FILE, EMAIL, NEWSLETTER_TOP_N_IN_AI, OUTPUT_DIR,
                    TOPICS)

_PRIO_RANK = {"hoch": 3, "mittel": 2, "niedrig": 1}
_PRIO_LABEL = {"hoch": "Hoch", "mittel": "Mittel", "niedrig": "Niedrig"}
_PRIO_COLOR = {"hoch": "#e03131", "mittel": "#f08c00", "niedrig": "#868e96"}

_TELEGRAM_MAX = 3800  # Telegram-Limit ist 4096 Zeichen; Sicherheitspuffer


# ---------------------------------------------------------------------------
# Gemeinsame Helfer
# ---------------------------------------------------------------------------
def _today() -> str:
    return datetime.now().strftime("%d.%m.%Y")


def _top_stories(stories: list[dict], n: int) -> list[dict]:
    ranked = sorted(stories, key=lambda s: _PRIO_RANK.get(s.get("priority"), 2),
                    reverse=True)
    return ranked[:n]


# ---------------------------------------------------------------------------
# 1) Dashboard (GitHub Pages)
# ---------------------------------------------------------------------------
_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin:0; font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       background:#f6f7f9; color:#1a1a1a; }
header { padding:20px 16px; background:#0b1f3a; color:#fff; }
header h1 { margin:0; font-size:20px; }
header .date { opacity:.8; font-size:13px; margin-top:2px; }
.tabs { display:flex; gap:4px; padding:10px 12px 0; background:#0b1f3a; }
.tab { border:0; padding:10px 16px; font-size:14px; cursor:pointer; border-radius:8px 8px 0 0;
       background:#16335c; color:#cdd9ec; }
.tab.active { background:#f6f7f9; color:#0b1f3a; font-weight:600; }
.panel { display:none; padding:16px; max-width:840px; margin:0 auto; }
.panel.active { display:block; }
.section-title { font-size:13px; text-transform:uppercase; letter-spacing:.04em;
                 color:#666; margin:18px 4px 8px; }
.card { background:#fff; border-radius:10px; padding:14px 16px; margin-bottom:12px;
        border-left:5px solid #ccc; box-shadow:0 1px 2px rgba(0,0,0,.06); }
.card h3 { margin:0 0 4px; font-size:16px; line-height:1.3; }
.card h3 a { color:#0b1f3a; text-decoration:none; }
.card h3 a:hover { text-decoration:underline; }
.card .src { font-size:12px; color:#888; margin-bottom:6px; }
.card .sum { margin:6px 0; font-size:14px; line-height:1.45; }
.card .why { margin:6px 0 0; font-size:13px; color:#444; }
.prio { display:inline-block; font-size:11px; font-weight:700; color:#fff;
        padding:2px 8px; border-radius:999px; margin-bottom:6px; }
.xrow { background:#eef2fb; border-radius:8px; padding:8px 12px; margin-bottom:8px; font-size:14px; }
.xrow a { color:#0b1f3a; text-decoration:none; font-weight:600; }
.badge { display:inline-block; font-size:10px; font-weight:700; background:#3b5bdb; color:#fff;
         padding:1px 7px; border-radius:999px; margin-right:6px; text-transform:uppercase; }
.nl { color:#888; font-size:13px; }
ul.nllist { list-style:none; padding:0; margin:0; }
.nlitem { background:#fff; border-radius:8px; padding:10px 12px; margin-bottom:7px;
          font-size:14px; box-shadow:0 1px 2px rgba(0,0,0,.05); }
.nlitem a { color:#0b1f3a; text-decoration:none; font-weight:600; }
.nlgroup { font-size:12px; font-weight:700; color:#555; margin:14px 4px 6px; }
.empty { color:#888; font-style:italic; padding:8px 4px; }
"""

_TAB_JS = """
<script>
document.querySelectorAll('.tab').forEach(function(btn){
  btn.addEventListener('click', function(){
    document.querySelectorAll('.tab').forEach(function(b){ b.classList.remove('active'); });
    document.querySelectorAll('.panel').forEach(function(p){ p.classList.remove('active'); });
    btn.classList.add('active');
    document.getElementById(btn.dataset.target).classList.add('active');
  });
});
</script>
"""


def _card_html(a: dict) -> str:
    prio = a.get("priority", "mittel")
    color = _PRIO_COLOR.get(prio, "#ccc")
    why = (f"<p class='why'><strong>Warum relevant:</strong> {esc(a['reason'])}</p>"
           if a.get("reason") else "")
    return (
        f"<article class='card' style='border-left-color:{color}'>"
        f"<span class='prio' style='background:{color}'>{_PRIO_LABEL.get(prio, prio)}</span>"
        f"<h3><a href='{esc(a.get('url', ''))}' target='_blank' rel='noopener'>"
        f"{esc(a.get('title', ''))}</a></h3>"
        f"<div class='src'>{esc(a.get('source', ''))}</div>"
        f"<p class='sum'>{esc(a.get('summary_de', ''))}</p>"
        f"{why}</article>"
    )


def _xrow_html(s: dict) -> str:
    return (
        f"<div class='xrow'><span class='badge'>aus Newsletter</span>"
        f"<a href='{esc(s['url'])}' target='_blank' rel='noopener'>{esc(s['headline'])}</a>"
        f" <span class='nl'>— {esc(s['source_newsletter'])}</span></div>"
    )


def _nlitem_html(s: dict) -> str:
    return (
        f"<li class='nlitem'>"
        f"<a href='{esc(s['url'])}' target='_blank' rel='noopener'>{esc(s['headline'])}</a>"
        f" <span class='nl'>— {esc(s['source_newsletter'])} ↗</span></li>"
    )


def _ai_panel_html(articles: list[dict], stories: list[dict]) -> str:
    parts = []
    top = _top_stories(stories, NEWSLETTER_TOP_N_IN_AI)
    if top:
        parts.append("<div class='section-title'>Aus Newslettern</div>")
        parts.extend(_xrow_html(s) for s in top)
    parts.append("<div class='section-title'>RSS-Quellen</div>")
    if articles:
        parts.extend(_card_html(a) for a in articles)
    else:
        parts.append("<p class='empty'>Keine AI-News im Zeitfenster.</p>")
    return "".join(parts)


def _newsletter_panel_html(stories: list[dict]) -> str:
    if not stories:
        return "<p class='empty'>Keine Newsletter-Stories.</p>"
    # Gruppierung nach Newsletter-Absender.
    groups: dict[str, list[dict]] = {}
    for s in stories:
        groups.setdefault(s["source_newsletter"], []).append(s)
    parts = []
    for name, items in groups.items():
        parts.append(f"<div class='nlgroup'>{esc(name)}</div><ul class='nllist'>")
        parts.extend(_nlitem_html(s) for s in items)
        parts.append("</ul>")
    return "".join(parts)


def build_dashboard(analyzed: dict[str, list[dict]], stories: list[dict]) -> str:
    """Erzeugt output/dashboard.html und gibt den Pfad zurück."""
    date = _today()

    # Tabs aus den (aktivierten) RSS-Themen + fester Newsletter-Tab.
    nav, panels, first = [], [], True
    for topic_key, articles in analyzed.items():
        name = TOPICS.get(topic_key, {}).get("name", topic_key)
        active = " active" if first else ""
        nav.append(f"<button class='tab{active}' data-target='tab-{topic_key}'>"
                   f"{esc(name)}</button>")
        # Cross-Posting nur in den AI-News-Tab.
        body = (_ai_panel_html(articles, stories) if topic_key == "ai_news"
                else "".join(_card_html(a) for a in articles)
                or "<p class='empty'>Keine Artikel.</p>")
        panels.append(f"<section id='tab-{topic_key}' class='panel{active}'>{body}</section>")
        first = False

    active = " active" if first else ""
    nav.append(f"<button class='tab{active}' data-target='tab-newsletter'>Newsletter</button>")
    panels.append(f"<section id='tab-newsletter' class='panel{active}'>"
                  f"{_newsletter_panel_html(stories)}</section>")

    doc = (
        "<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>AI-Briefing {date}</title><style>{_CSS}</style></head><body>"
        f"<header><h1>AI-Briefing</h1><div class='date'>{date}</div></header>"
        f"<nav class='tabs'>{''.join(nav)}</nav>"
        f"{''.join(panels)}{_TAB_JS}</body></html>"
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"[deliver] Dashboard geschrieben: {DASHBOARD_FILE}")
    return DASHBOARD_FILE


# ---------------------------------------------------------------------------
# 2) Telegram (optional)
# ---------------------------------------------------------------------------
def _build_telegram_text(analyzed: dict[str, list[dict]], stories: list[dict]) -> str:
    lines = [f"<b>AI-Briefing – {esc(_today())}</b>"]
    for topic_key, articles in analyzed.items():
        name = TOPICS.get(topic_key, {}).get("name", topic_key)
        top = [a for a in articles if a.get("priority") in ("hoch", "mittel")][:8]
        if not top:
            continue
        lines.append(f"\n<b>{esc(name)}</b>")
        for a in top:
            lines.append(f"• <a href=\"{esc(a.get('url', ''))}\">{esc(a.get('title', ''))}</a>"
                         f" — {esc(a.get('source', ''))}")
    top_nl = _top_stories(stories, NEWSLETTER_TOP_N_IN_AI)
    if top_nl:
        lines.append("\n<b>Newsletter</b>")
        for s in top_nl:
            lines.append(f"• <a href=\"{esc(s['url'])}\">{esc(s['headline'])}</a>"
                         f" — {esc(s['source_newsletter'])}")
    text = "\n".join(lines)
    return text[:_TELEGRAM_MAX]


def send_telegram(analyzed: dict[str, list[dict]], stories: list[dict]) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[telegram] übersprungen (keine TELEGRAM_*-Secrets)")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": _build_telegram_text(analyzed, stories),
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[telegram] Fehler: {exc}")
        return False
    print("[telegram] gesendet")
    return True


# ---------------------------------------------------------------------------
# 3) E-Mail (Gmail, gmail.send)
# ---------------------------------------------------------------------------
def _build_email_html(analyzed: dict[str, list[dict]], stories: list[dict]) -> str:
    box = "background:#fff;border-left:5px solid {c};border-radius:8px;padding:12px 14px;margin:0 0 12px;"
    parts = [
        "<div style='font-family:Arial,Helvetica,sans-serif;max-width:680px;margin:0 auto;color:#1a1a1a;'>",
        f"<h1 style='font-size:20px;color:#0b1f3a;'>AI-Briefing – {esc(_today())}</h1>",
    ]

    top_nl = _top_stories(stories, NEWSLETTER_TOP_N_IN_AI)
    if top_nl:
        parts.append("<h2 style='font-size:14px;color:#666;'>Aus Newslettern</h2>")
        for s in top_nl:
            parts.append(
                f"<p style='margin:4px 0;font-size:14px;'>• "
                f"<a href='{esc(s['url'])}' style='color:#0b1f3a;'>{esc(s['headline'])}</a>"
                f" <span style='color:#888;'>— {esc(s['source_newsletter'])}</span></p>")

    for topic_key, articles in analyzed.items():
        name = TOPICS.get(topic_key, {}).get("name", topic_key)
        parts.append(f"<h2 style='font-size:16px;color:#0b1f3a;margin-top:20px;'>{esc(name)}</h2>")
        if not articles:
            parts.append("<p style='color:#888;font-style:italic;'>Keine Artikel im Zeitfenster.</p>")
        for a in articles:
            prio = a.get("priority", "mittel")
            color = _PRIO_COLOR.get(prio, "#ccc")
            why = (f"<div style='font-size:13px;color:#444;margin-top:4px;'>"
                   f"<strong>Warum relevant:</strong> {esc(a['reason'])}</div>"
                   if a.get("reason") else "")
            parts.append(
                f"<div style='{box.format(c=color)}'>"
                f"<div style='font-size:11px;font-weight:bold;color:{color};'>{_PRIO_LABEL.get(prio, prio)}</div>"
                f"<div style='font-size:16px;margin:2px 0;'>"
                f"<a href='{esc(a.get('url', ''))}' style='color:#0b1f3a;text-decoration:none;'>"
                f"{esc(a.get('title', ''))}</a></div>"
                f"<div style='font-size:12px;color:#888;'>{esc(a.get('source', ''))}</div>"
                f"<div style='font-size:14px;margin-top:6px;'>{esc(a.get('summary_de', ''))}</div>"
                f"{why}</div>")

    parts.append("<h2 style='font-size:16px;color:#0b1f3a;margin-top:20px;'>Newsletter</h2>")
    if stories:
        for s in stories:
            parts.append(
                f"<p style='margin:4px 0;font-size:14px;'>• "
                f"<a href='{esc(s['url'])}' style='color:#0b1f3a;'>{esc(s['headline'])}</a>"
                f" <span style='color:#888;'>— {esc(s['source_newsletter'])}</span></p>")
    else:
        parts.append("<p style='color:#888;font-style:italic;'>Keine Newsletter-Stories.</p>")

    parts.append("</div>")
    return "".join(parts)


def send_email(analyzed: dict[str, list[dict]], stories: list[dict]) -> bool:
    if not EMAIL.get("enabled", False):
        print("[email] deaktiviert")
        return False
    # Hinweis: Die Action setzt EMAIL_TO immer (ggf. leerer String, wenn das
    # Secret fehlt). Daher `or` statt eines get-Defaults, damit ein leerer Wert
    # auf den config.py-Default zurückfällt.
    recipient = (os.environ.get("EMAIL_TO") or EMAIL.get("to", "")).strip()
    if not recipient:
        print("[email] übersprungen (kein Empfänger konfiguriert)")
        return False

    try:
        service = gmail_source.build_service()
        sender = service.users().getProfile(userId="me").execute().get("emailAddress", "")

        msg = EmailMessage()
        msg["To"] = recipient
        if sender:
            msg["From"] = sender
        msg["Subject"] = f"{EMAIL.get('subject_prefix', 'AI-Briefing')} – {_today()}"
        msg.set_content("Dieses Briefing wird als HTML dargestellt. "
                        "Bitte einen HTML-fähigen Mail-Client verwenden.")
        msg.add_alternative(_build_email_html(analyzed, stories), subtype="html")

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
    except Exception as exc:
        print(f"[email] Fehler: {exc}")
        return False
    print(f"[email] gesendet an {recipient}")
    return True
