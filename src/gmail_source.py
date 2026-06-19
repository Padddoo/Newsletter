"""
gmail_source.py — AI-Newsletter aus Gmail holen und in Klartext + Links überführen.

Aufgabe (Spec §6.3):
  1. Credentials headless aus 3 Secrets bauen (Spec §5.3), Gmail-Client erstellen.
  2. Ungelesene Mails der letzten 2 Tage listen (NEWSLETTER["gmail_query"]).
  3. Pro Mail: Header (From/Subject/Date) + Body (text/plain bevorzugt, sonst
     text/html → Tags strippen, dabei Links erhalten).
  4. Body auf max_body_chars kürzen (Token-Deckel).
  5. Dedupe über bereits verarbeitete Message-IDs (state/seen_ids.json), da
     gmail.readonly kein Markieren als gelesen erlaubt.

Die Story-Zerlegung pro Mail übernimmt anschließend analyst.py (Claude).

Hinweis Spam (Schritt 1): Die Query erfasst nur den Posteingang; was Gmail in den
Spam-Ordner einsortiert, wird nicht gelesen. Härtung folgt in Schritt 2 (Spec §15).
"""
from __future__ import annotations

import base64
import json
import os
import re
from html.parser import HTMLParser

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import GMAIL_SCOPES, NEWSLETTER, SEEN_IDS_MAX, STATE_FILE

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_URL_RE = re.compile(r"https?://[^\s<>()\"']+")
_MAX_LINKS = 60  # Deckel pro Mail, damit der Claude-Prompt nicht explodiert

# Block-Level-Tags, die beim Strippen zu Zeilenumbrüchen werden (Lesbarkeit).
_BLOCK_TAGS = {"br", "p", "div", "li", "tr", "table", "ul", "ol",
               "h1", "h2", "h3", "h4", "h5", "h6"}


# ---------------------------------------------------------------------------
# State / Dedupe
# ---------------------------------------------------------------------------
def load_seen_ids() -> list[str]:
    """Liest bereits verarbeitete Message-IDs; [] falls Datei fehlt/kaputt."""
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        ids = data.get("seen_ids", []) if isinstance(data, dict) else data
        return [str(x) for x in ids] if isinstance(ids, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def mark_seen(new_ids: list[str]) -> None:
    """Fügt neue IDs hinzu (FIFO, auf SEEN_IDS_MAX begrenzt) und schreibt zurück."""
    existing = load_seen_ids()
    known = set(existing)
    combined = existing + [mid for mid in new_ids if mid not in known]
    capped = combined[-SEEN_IDS_MAX:]
    os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump({"seen_ids": capped}, fh, ensure_ascii=False, indent=0)


# ---------------------------------------------------------------------------
# Credentials (headless, Spec §5.3)
# ---------------------------------------------------------------------------
def _build_credentials() -> Credentials:
    required = ("GMAIL_REFRESH_TOKEN", "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Fehlende Gmail-Secrets: {', '.join(missing)}")

    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri=_TOKEN_URI,
        scopes=GMAIL_SCOPES,
    )
    try:
        creds.refresh(Request())  # holt frischen Access-Token
    except RefreshError as exc:
        raise RuntimeError(
            "Gmail-OAuth-Refresh fehlgeschlagen (invalid_grant?). Refresh-Token "
            "neu erzeugen mit: python scripts/oauth_setup.py"
        ) from exc
    return creds


# ---------------------------------------------------------------------------
# Body- / Link-Extraktion
# ---------------------------------------------------------------------------
def _decode(data: str) -> str:
    """Dekodiert base64url-kodierte Gmail-Body-Daten zu Text."""
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode(
            "utf-8", errors="replace"
        )
    except Exception:
        return ""


def _walk_parts(payload: dict) -> tuple[str | None, str | None]:
    """Durchläuft den MIME-Baum, liefert (erster text/plain, erster text/html)."""
    plain: str | None = None
    html_: str | None = None

    def walk(part: dict) -> None:
        nonlocal plain, html_
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if mime == "text/plain" and data and plain is None:
            plain = _decode(data)
        elif mime == "text/html" and data and html_ is None:
            html_ = _decode(data)
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload or {})
    return plain, html_


class _HtmlExtractor(HTMLParser):
    """Strippt HTML zu Text und sammelt (Anker-Text, URL)-Paare."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._anchor: list[str] = []
        self._skip = 0  # innerhalb von <script>/<style>

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "a":
            self._href = dict(attrs).get("href")
            self._anchor = []
        elif tag in _BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip > 0:
            self._skip -= 1
        elif tag == "a":
            anchor = "".join(self._anchor).strip()
            if self._href and self._href.startswith("http"):
                self.links.append((anchor, self._href))
            self._href = None
            self._anchor = []
        elif tag in _BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        self.text_parts.append(data)
        if self._href is not None:
            self._anchor.append(data)


def _html_to_text_and_links(html_str: str) -> tuple[str, list[tuple[str, str]]]:
    parser = _HtmlExtractor()
    try:
        parser.feed(html_str)
    except Exception:
        pass
    return "".join(parser.text_parts), parser.links


def _urls_from_text(text: str) -> list[tuple[str, str]]:
    """Fallback: rohe URLs aus Klartext (Anker = URL)."""
    return [(u, u) for u in _URL_RE.findall(text)]


def _normalize_ws(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _dedupe_links(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for anchor, url in links:
        if url not in seen:
            seen.add(url)
            out.append((anchor, url))
        if len(out) >= _MAX_LINKS:
            break
    return out


def _body_and_links(plain: str | None, html_: str | None
                    ) -> tuple[str, list[tuple[str, str]]]:
    """Wählt den besten Body und extrahiert Links (bevorzugt aus HTML)."""
    links: list[tuple[str, str]] = []
    text_from_html = ""
    if html_:
        text_from_html, links = _html_to_text_and_links(html_)

    body_text = plain if plain else text_from_html
    if not links and body_text:
        links = _urls_from_text(body_text)

    return _normalize_ws(body_text), _dedupe_links(links)


def _headers_map(headers: list[dict]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in headers}


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------
def fetch_newsletters() -> list[dict]:
    """Holt neue (noch nicht gesehene) Newsletter-Mails als strukturierte dicts."""
    if not NEWSLETTER.get("enabled", False):
        return []

    creds = _build_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    query = NEWSLETTER["gmail_query"]
    max_messages = NEWSLETTER.get("max_messages", 25)
    max_body = NEWSLETTER.get("max_body_chars", 6000)

    listing = (
        service.users().messages()
        .list(userId="me", q=query, maxResults=max_messages)
        .execute()
    )
    messages = listing.get("messages", []) or []
    seen = set(load_seen_ids())

    results: list[dict] = []
    for ref in messages:
        mid = ref.get("id")
        if not mid or mid in seen:
            continue
        try:
            full = (
                service.users().messages()
                .get(userId="me", id=mid, format="full")
                .execute()
            )
        except Exception as exc:  # einzelne Mail überspringen, Lauf fortsetzen
            print(f"  [skip] Mail {mid} nicht ladbar: {exc}")
            continue

        payload = full.get("payload", {})
        headers = _headers_map(payload.get("headers", []))
        plain, html_ = _walk_parts(payload)
        body_text, links = _body_and_links(plain, html_)

        results.append({
            "message_id": mid,
            "sender": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "date": headers.get("date", ""),
            "body_text": body_text[:max_body],
            "links": links,
        })

    print(f"[gmail] {len(results)} neue Newsletter (von {len(messages)} gelistet, "
          f"{len(seen)} bereits gesehen)")
    return results


if __name__ == "__main__":
    for nl in fetch_newsletters():
        print(f"- {nl['subject']}  [{nl['sender']}]  "
              f"({len(nl['links'])} Links, {len(nl['body_text'])} Zeichen)")
