"""
collector.py — RSS-Quellen sammeln und vorfiltern.

Bewusst "dumm": bewertet NICHT inhaltlich, sondern
  1. lädt alle Feeds der aktivierten Themen (config.TOPICS),
  2. filtert nach Zeitfenster (lookback_hours pro Thema),
  3. dedupliziert über einen Titel-Hash,
  4. sortiert per Keyword-Treffer vor (filtert NICHT weg),
  5. deckelt auf MAX_ARTICLES_TO_RATE pro Thema (Kostendeckel).

Die eigentliche Relevanz-Bewertung passiert erst in analyst.py (Claude).

Robustheit: einzelne tote/kaputte Feeds werden übersprungen, der Lauf läuft
weiter (Spec §11).
"""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from config import MAX_ARTICLES_TO_RATE, TOPICS

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_SUMMARY_MAX_CHARS = 1000
_FEED_TIMEOUT = 20  # Sekunden pro Feed-Request (verhindert Hänger an toten Feeds)
_USER_AGENT = (
    "Mozilla/5.0 (compatible; news-agent/1.0; +https://github.com/)"
)


def _strip_html(text: str) -> str:
    """Entfernt HTML-Tags, löst Entities auf, normalisiert Whitespace."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _parse_date(entry) -> datetime | None:
    """Liest das Veröffentlichungsdatum als UTC-datetime; None falls unbekannt."""
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _source_name(parsed, feed_url: str) -> str:
    """Feed-Titel als Quellenname; Fallback auf die Domain der Feed-URL."""
    feed_meta = getattr(parsed, "feed", None)
    title = feed_meta.get("title") if feed_meta else None
    if title:
        return title.strip()
    match = re.search(r"https?://(?:www\.)?([^/]+)", feed_url)
    return match.group(1) if match else feed_url


def _title_hash(title: str) -> str:
    """Normalisierter Hash für die Dedupe (case-/whitespace-insensitiv)."""
    norm = _WS_RE.sub(" ", (title or "").lower()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _keyword_score(text: str, keywords: list[str]) -> int:
    """Anzahl der Keywords, die im Text vorkommen (nur zum Sortieren)."""
    if not text:
        return 0
    low = text.lower()
    return sum(1 for kw in keywords if kw.lower() in low)


def _fetch_feed(feed_url: str):
    """Lädt und parst einen Feed. Gibt None zurück, wenn er nicht nutzbar ist."""
    try:
        resp = requests.get(
            feed_url, timeout=_FEED_TIMEOUT, headers={"User-Agent": _USER_AGENT}
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  [skip] Feed nicht erreichbar {feed_url}: {exc}")
        return None

    parsed = feedparser.parse(resp.content)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        print(f"  [skip] Feed nicht lesbar {feed_url}: "
              f"{getattr(parsed, 'bozo_exception', '')}")
        return None
    return parsed


def collect_topic(topic_key: str, topic: dict) -> list[dict]:
    """Sammelt, filtert und sortiert die Artikel eines einzelnen Themas."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=topic["lookback_hours"])
    keywords = topic.get("keywords", [])

    articles: list[dict] = []
    seen_hashes: set[str] = set()

    for feed_url in topic.get("feeds", []):
        parsed = _fetch_feed(feed_url)
        if parsed is None:
            continue
        source = _source_name(parsed, feed_url)

        for entry in parsed.entries:
            title = (entry.get("title") or "").strip()
            url = (entry.get("link") or "").strip()
            if not title or not url:
                continue

            published = _parse_date(entry)
            # Zeitfenster: datierte Artikel müssen im Fenster liegen. Undatierte
            # Artikel werden konservativ aufgenommen (kuratierte Feeds).
            if published is not None and published < cutoff:
                continue

            h = _title_hash(title)
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            summary = _strip_html(entry.get("summary", ""))[:_SUMMARY_MAX_CHARS]
            articles.append({
                "topic": topic_key,
                "title": title,
                "url": url,
                "source": source,
                "published": published.isoformat() if published else None,
                "_published_dt": published,  # intern, nur für die Sortierung
                "summary": summary,
                "keyword_score": _keyword_score(f"{title} {summary}", keywords),
            })

    # Sortierung: Keyword-Treffer (desc), dann Aktualität (neu zuerst).
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    articles.sort(
        key=lambda a: (a["keyword_score"], a["_published_dt"] or oldest),
        reverse=True,
    )

    for a in articles:
        a.pop("_published_dt", None)  # internes Feld entfernen
    return articles[:MAX_ARTICLES_TO_RATE]


def collect_all() -> dict[str, list[dict]]:
    """Sammelt alle aktivierten Themen. Rückgabe: {topic_key: [article, ...]}."""
    result: dict[str, list[dict]] = {}
    for topic_key, topic in TOPICS.items():
        if not topic.get("enabled", False):
            continue
        print(f"[collector] Thema '{topic_key}' ({topic['name']}) ...")
        articles = collect_topic(topic_key, topic)
        print(f"[collector] '{topic_key}': {len(articles)} Artikel "
              f"(Fenster {topic['lookback_hours']}h)")
        result[topic_key] = articles
    return result


if __name__ == "__main__":
    collected = collect_all()
    for key, items in collected.items():
        print(f"\n=== {key}: {len(items)} Artikel ===")
        for a in items[:10]:
            print(f"  [{a['keyword_score']}] {a['title']}  — {a['source']}")
            print(f"        {a['url']}")
