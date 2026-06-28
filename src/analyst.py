"""
analyst.py — Bewertung & Aufbereitung durch Claude.

Zwei Pfade (Spec §6.4):
  (a) RSS-Artikel: pro Thema mit thema-spezifischem Profil bewerten →
      priority, reason ("Warum relevant"), summary_de.
  (b) Newsletter-Mails: in einzelne Stories zerlegen → headline (≤10 Wörter),
      url, source_newsletter, priority.

Robustheit (Spec §11):
  - Claude-Antwort kein valides JSON: einmal Retry, dann
      * RSS: Artikel bleiben erhalten mit neutraler Priorität (Lauf nicht blockieren),
      * Newsletter: betroffene Mail liefert keine Stories.
  - Headline > HEADLINE_MAX_WORDS: hart auf die ersten N Wörter kürzen.
  - Story ohne brauchbare URL: verwerfen.
"""
from __future__ import annotations

import json
import re

from config import ANTHROPIC_MODEL, HEADLINE_MAX_WORDS, NEWSLETTER, TOPICS

_PRIO_RANK = {"hoch": 3, "mittel": 2, "niedrig": 1}
_PRIO_ALIASES = {
    "hoch": "hoch", "high": "hoch", "hohe": "hoch",
    "mittel": "mittel", "medium": "mittel", "mid": "mittel",
    "niedrig": "niedrig", "low": "niedrig", "gering": "niedrig",
}

_client = None

# Fehlerspeicher des aktuellen Laufs: alle Claude-API-/Transportfehler (kein
# JSON-Parse-Problem). Basis für die Frühwarnung in run.py. Vor jedem Lauf via
# reset_api_errors() leeren.
_api_errors: list[str] = []

# Marker für NICHT selbstheilende Fehler: Lauf soll sichtbar fehlschlagen statt
# still ein leeres Briefing zu senden. Bewusst auf Klartext-Substrings geprüft
# (robust gegenüber SDK-Versionen).
_HARD_BLOCK_MARKERS = (
    "usage limit",        # "reached your specified API usage limits"
    "credit balance",     # Guthaben aufgebraucht
    "authentication",     # 401 — ungültiger/abgelaufener API-Key
    "invalid x-api-key",
    "permission",         # 403 — Key ohne Berechtigung
)


def reset_api_errors() -> None:
    """Leert den Fehlerspeicher. Zu Beginn jedes Laufs aufrufen."""
    _api_errors.clear()


def _record_api_error(exc: Exception) -> None:
    _api_errors.append(str(exc))


def api_errors() -> list[str]:
    """Alle in diesem Lauf aufgetretenen Claude-API-/Transportfehler."""
    return list(_api_errors)


def limit_reason() -> str | None:
    """Lesbarer Grund, falls ein nicht selbstheilender Claude-Fehler auftrat
    (Usage-Limit, fehlendes Guthaben, ungültiger API-Key, fehlende Berechtigung).
    Sonst None. Frühwarn-Signal für run.py."""
    for err in _api_errors:
        low = err.lower()
        if any(marker in low for marker in _HARD_BLOCK_MARKERS):
            return err
    return None


def _get_client():
    """Lazy-Init des Anthropic-Clients (liest ANTHROPIC_API_KEY aus der Env)."""
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic()
    return _client


def _call_claude(system: str, user: str, max_tokens: int = 4096) -> str:
    """Ein Claude-Aufruf; gibt den zusammengesetzten Text-Inhalt zurück."""
    resp = _get_client().messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(
        block.text for block in resp.content
        if getattr(block, "type", "") == "text"
    )


# ---------------------------------------------------------------------------
# Hilfsfunktionen (rein, ohne Netzwerk → gut testbar)
# ---------------------------------------------------------------------------
def truncate_headline(headline: str) -> str:
    """Kürzt auf maximal HEADLINE_MAX_WORDS Wörter (kürzen, nicht abschneiden)."""
    words = (headline or "").split()
    if len(words) > HEADLINE_MAX_WORDS:
        return " ".join(words[:HEADLINE_MAX_WORDS])
    return " ".join(words)


def _normalize_priority(value: str) -> str:
    return _PRIO_ALIASES.get((value or "").strip().lower(), "mittel")


def _clean_sender(from_header: str) -> str:
    """Extrahiert einen lesbaren Newsletter-Namen aus dem From-Header."""
    if not from_header:
        return ""
    m = re.match(r'\s*"?([^"<]+?)"?\s*<', from_header)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = re.search(r"[\w.+-]+@([\w.-]+)", from_header)
    if m:
        return m.group(1)
    return from_header.strip()


def _parse_json(text: str):
    """Parst JSON aus einer Claude-Antwort (toleriert Markdown-Fences/Prosa)."""
    if not text or not text.strip():
        raise ValueError("leere Antwort")
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # Fallback: äußersten JSON-Block extrahieren.
    for open_c, close_c in (("[", "]"), ("{", "}")):
        i, j = t.find(open_c), t.rfind(close_c)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("kein gültiges JSON in der Antwort")


def _call_and_parse(system: str, user: str, max_tokens: int):
    """Claude-Aufruf; None bei API- oder endgültigem Parse-Fehler.

    Zwei Fehlerklassen werden getrennt behandelt:
      - API-/Transportfehler (Limit, Auth, Netzwerk): erneuter Versuch mit
        JSON-Hinweis hilft nicht -> sofort abbrechen und für die Frühwarnung
        vermerken.
      - Parse-Fehler (kein gültiges JSON): einmal mit striktem JSON-Hinweis
        wiederholen (wie bisher, Spec §11).
    """
    last_parse_err = None
    for attempt in range(2):
        try:
            raw = _call_claude(system, user, max_tokens)
        except Exception as exc:
            _record_api_error(exc)
            print(f"  [warn] Claude-API-Fehler: {exc}")
            return None
        try:
            return _parse_json(raw)
        except Exception as exc:
            last_parse_err = exc
            user += ("\n\nWICHTIG: Antworte ausschließlich mit gültigem JSON, "
                     "ohne weiteren Text, ohne Markdown.")
    print(f"  [warn] Claude-Antwort nicht parsebar: {last_parse_err}")
    return None


# ---------------------------------------------------------------------------
# (a) RSS-Bewertung
# ---------------------------------------------------------------------------
def _build_rss_prompt(topic: dict, articles: list[dict]) -> tuple[str, str]:
    items = [
        {"index": i, "title": a["title"], "source": a["source"],
         "summary": (a.get("summary") or "")[:300]}
        for i, a in enumerate(articles)
    ]
    system = (
        "Du bist ein präziser Nachrichten-Analyst. Antworte ausschließlich mit "
        "gültigem JSON, ohne Markdown und ohne Erklärungen."
    )
    user = (
        f"Profil des Lesers:\n{topic['profile']}\n\n"
        "Bewerte die folgenden Artikel aus Sicht dieses Profils. Vergib je Artikel:\n"
        '- priority: "hoch", "mittel" oder "niedrig" (Relevanz fürs Profil)\n'
        '- reason: knappe deutsche Begründung "Warum relevant" (max. 15 Wörter)\n'
        "- summary_de: 1–2 nüchterne deutsche Sätze\n\n"
        f"Artikel (JSON):\n{json.dumps(items, ensure_ascii=False)}\n\n"
        "Antworte AUSSCHLIESSLICH mit einem JSON-Array dieser Form:\n"
        '[{"index": 0, "priority": "hoch", "reason": "...", "summary_de": "..."}]'
    )
    return system, user


def _apply_rss_ratings(articles: list[dict], parsed) -> list[dict]:
    ratings = parsed if isinstance(parsed, list) else parsed.get("ratings", [])
    by_index: dict[int, dict] = {}
    for r in ratings:
        try:
            by_index[int(r.get("index"))] = r
        except (TypeError, ValueError):
            continue
    out = []
    for i, a in enumerate(articles):
        r = by_index.get(i, {})
        out.append({
            **a,
            "priority": _normalize_priority(r.get("priority")),
            "reason": (r.get("reason") or "").strip(),
            "summary_de": (r.get("summary_de") or "").strip() or a.get("summary", ""),
        })
    return out


def _sort_by_priority(articles: list[dict]) -> list[dict]:
    return sorted(
        articles,
        key=lambda a: (_PRIO_RANK.get(a.get("priority", "mittel"), 2),
                       a.get("keyword_score", 0)),
        reverse=True,
    )


def _rate_topic(topic: dict, articles: list[dict]) -> list[dict]:
    system, user = _build_rss_prompt(topic, articles)
    parsed = _call_and_parse(system, user, max_tokens=4096)
    if parsed is None:
        # Graceful: Artikel behalten, neutrale Bewertung (Lauf nicht blockieren).
        for a in articles:
            a.setdefault("priority", "mittel")
            a.setdefault("reason", "")
            a.setdefault("summary_de", a.get("summary", ""))
        return _sort_by_priority(articles)
    return _sort_by_priority(_apply_rss_ratings(articles, parsed))


def analyze_all(collected: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Bewertet alle gesammelten RSS-Themen. Rückgabe: {topic_key: [article,...]}."""
    result: dict[str, list[dict]] = {}
    for topic_key, articles in collected.items():
        if not articles:
            result[topic_key] = []
            continue
        print(f"[analyst] bewerte {len(articles)} Artikel in '{topic_key}' ...")
        result[topic_key] = _rate_topic(TOPICS[topic_key], articles)
    return result


# ---------------------------------------------------------------------------
# (b) Newsletter-Zerlegung
# ---------------------------------------------------------------------------
def _build_newsletter_prompt(mail: dict) -> tuple[str, str]:
    links_list = "\n".join(
        f"{i}. {anchor or '(kein Text)'} -> {url}"
        for i, (anchor, url) in enumerate(mail.get("links", []))
    )
    system = (
        "Du bist ein präziser Nachrichten-Analyst für AI-Themen. "
        f"{NEWSLETTER['profile']} "
        "Antworte ausschließlich mit gültigem JSON, ohne Markdown."
    )
    user = (
        f"Newsletter-Absender: {mail.get('sender', '')}\n"
        f"Betreff: {mail.get('subject', '')}\n\n"
        f"Verfügbare Links (Index, Anker, URL):\n{links_list or '(keine Links gefunden)'}\n\n"
        f"Newsletter-Text:\n{mail.get('body_text', '')}\n\n"
        "Zerlege diesen Newsletter in seine einzelnen AI-relevanten Stories. Pro Story:\n"
        "- headline: deutsche Headline, MAXIMAL 10 Wörter, nüchtern, kein Clickbait\n"
        "- url: der passende vollständige Quell-Link aus der Liste oben\n"
        "- source_newsletter: Name des Newsletters\n"
        '- priority: "hoch", "mittel" oder "niedrig"\n\n'
        "Ignoriere Werbung, Sponsoren-Blöcke, Job-Listings und reine Meinungsstücke.\n\n"
        "Antworte AUSSCHLIESSLICH mit JSON dieser Form:\n"
        '{"stories": [{"headline": "...", "url": "https://...", '
        '"source_newsletter": "...", "priority": "hoch"}]}'
    )
    return system, user


def _stories_from_response(parsed, mail: dict) -> list[dict]:
    raw_stories = parsed.get("stories", []) if isinstance(parsed, dict) else parsed
    if not isinstance(raw_stories, list):
        return []
    default_source = _clean_sender(mail.get("sender", "")) or NEWSLETTER["name"]
    stories = []
    for s in raw_stories:
        if not isinstance(s, dict):
            continue
        url = (s.get("url") or "").strip()
        if not url.startswith("http"):
            continue  # Stories ohne brauchbare URL verwerfen
        headline = truncate_headline((s.get("headline") or "").strip())
        if not headline:
            continue
        stories.append({
            "headline": headline,
            "url": url,
            "source_newsletter": (s.get("source_newsletter") or "").strip() or default_source,
            "priority": _normalize_priority(s.get("priority")),
        })
    return stories


def analyze_newsletters(newsletters: list[dict]) -> tuple[list[dict], list[str]]:
    """Zerlegt alle Newsletter-Mails in eine flache Story-Liste.

    Rückgabe: (stories, processed_ids).
      - stories: alle extrahierten Newsletter-Stories.
      - processed_ids: Message-IDs der Mails, deren Claude-Analyse ERFOLGREICH
        war (auch wenn 0 Stories herauskamen, z. B. reine Werbung). NUR diese
        sollen als "gesehen" markiert werden.

    Mails, deren Analyse hart fehlschlägt (z. B. API-Limit/Netzwerk), landen
    NICHT in processed_ids — so werden sie im nächsten Lauf erneut versucht und
    gehen bei einem Claude-Ausfall nicht verloren.
    """
    stories: list[dict] = []
    processed_ids: list[str] = []
    failed = 0
    for mail in newsletters:
        system, user = _build_newsletter_prompt(mail)
        parsed = _call_and_parse(system, user, max_tokens=2048)
        if parsed is None:
            failed += 1
            continue  # Analyse fehlgeschlagen -> NICHT als gesehen markieren
        if mail.get("message_id"):
            processed_ids.append(mail["message_id"])
        stories.extend(_stories_from_response(parsed, mail))
    msg = (f"[analyst] {len(stories)} Newsletter-Stories aus "
           f"{len(newsletters)} Mails extrahiert")
    if failed:
        msg += (f" ({failed} Mail(s) wegen Analyse-Fehler übersprungen, "
                "bleiben für den nächsten Lauf ungesehen)")
    print(msg)
    return stories, processed_ids
