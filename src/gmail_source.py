"""
gmail_source.py — AI-Newsletter aus Gmail holen, via IMAP (App-Passwort).

Aufgabe:
  1. Per IMAP am Gmail-Konto anmelden (GMAIL_ADDRESS + GMAIL_APP_PASSWORD).
  2. Ungelesene Mails der letzten N Tage im Posteingang suchen.
  3. Pro Mail: Header (From/Subject/Date) + Body (text/plain bevorzugt, sonst
     text/html → Tags strippen, dabei Links erhalten).
  4. Body auf max_body_chars kürzen (Token-Deckel).
  5. Dedupe über bereits verarbeitete Message-IDs (state/seen_ids.json).

Die Story-Zerlegung pro Mail übernimmt anschließend analyst.py (Claude).

Zugriff bewusst read-only (IMAP SELECT readonly) — der Agent verändert nichts im
Postfach. Spam (Schritt 1): Wir lesen nur INBOX; was Gmail in [Gmail]/Spam
einsortiert, wird nicht erfasst. Härtung folgt in Schritt 2.

Nur Standardbibliothek (imaplib/email) — keine Drittanbieter-Abhängigkeit.
"""
from __future__ import annotations

import email
import imaplib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import Message
from html.parser import HTMLParser

from config import IMAP_HOST, NEWSLETTER, SEEN_IDS_MAX, STATE_FILE

_URL_RE = re.compile(r"https?://[^\s<>()\"']+")
_MAX_LINKS = 60  # Deckel pro Mail, damit der Claude-Prompt nicht explodiert
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

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
# Zugangsdaten (App-Passwort)
# ---------------------------------------------------------------------------
def get_account() -> tuple[str, str]:
    """Liefert (Adresse, App-Passwort) aus der Env; säubert Whitespace."""
    address = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    missing = [name for name, val in
               (("GMAIL_ADDRESS", address), ("GMAIL_APP_PASSWORD", password))
               if not val]
    if missing:
        raise RuntimeError(f"Fehlende Gmail-Secrets: {', '.join(missing)}")
    # App-Passwörter werden mit Leerzeichen angezeigt ("abcd efgh ijkl mnop"),
    # eingegeben werden sie ohne — interne Leerzeichen wegputzen.
    return address, password.replace(" ", "")


# ---------------------------------------------------------------------------
# Body- / Link-Extraktion
# ---------------------------------------------------------------------------
def _decode_hdr(value: str) -> str:
    """Dekodiert MIME-kodierte Header (=?utf-8?...) zu Klartext."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _part_text(part: Message) -> str:
    """Dekodiert den Text eines MIME-Parts unter Berücksichtigung des Charsets."""
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, ValueError):
        return payload.decode("utf-8", errors="replace")


def _extract_plain_html(msg: Message) -> tuple[str | None, str | None]:
    """Liefert (erster text/plain, erster text/html) aus der Mail."""
    plain: str | None = None
    html_: str | None = None
    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and plain is None:
                plain = _part_text(part)
            elif ctype == "text/html" and html_ is None:
                html_ = _part_text(part)
    elif msg.get_content_type() == "text/html":
        html_ = _part_text(msg)
    else:
        plain = _part_text(msg)
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


def _message_to_dict(msg: Message, max_body: int) -> dict:
    plain, html_ = _extract_plain_html(msg)
    body_text, links = _body_and_links(plain, html_)
    message_id = (msg.get("Message-ID") or "").strip()
    sender = _decode_hdr(msg.get("From", ""))
    subject = _decode_hdr(msg.get("Subject", ""))
    if not message_id:  # Fallback: synthetische ID aus Headern
        message_id = f"{sender}|{subject}|{msg.get('Date', '')}"
    return {
        "message_id": message_id,
        "sender": sender,
        "subject": subject,
        "date": msg.get("Date", ""),
        "body_text": body_text[:max_body],
        "links": links,
    }


# ---------------------------------------------------------------------------
# IMAP-Abruf
# ---------------------------------------------------------------------------
def _imap_since(days: int) -> str:
    d = datetime.now(timezone.utc) - timedelta(days=days)
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"


def fetch_newsletters() -> list[dict]:
    """Holt neue (noch nicht gesehene) Newsletter-Mails als strukturierte dicts."""
    if not NEWSLETTER.get("enabled", False):
        return []

    address, password = get_account()
    seen = set(load_seen_ids())
    folder = NEWSLETTER.get("imap_folder", "INBOX")
    max_messages = NEWSLETTER.get("max_messages", 25)
    max_body = NEWSLETTER.get("max_body_chars", 6000)

    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST)
    except OSError as exc:
        raise RuntimeError(f"IMAP-Verbindung fehlgeschlagen: {exc}") from exc

    listed = 0
    results: list[dict] = []
    try:
        try:
            imap.login(address, password)
        except imaplib.IMAP4.error as exc:
            raise RuntimeError(
                "IMAP-Login fehlgeschlagen — GMAIL_ADDRESS / GMAIL_APP_PASSWORD "
                "prüfen (App-Passwort, 2FA aktiv?)."
            ) from exc

        imap.select(folder, readonly=True)
        criteria: list[str] = []
        if NEWSLETTER.get("only_unread", True):
            criteria.append("UNSEEN")
        criteria += ["SINCE", _imap_since(NEWSLETTER.get("lookback_days", 2))]

        typ, data = imap.search(None, *criteria)
        if typ != "OK" or not data:
            print(f"[gmail] IMAP-Suche lieferte keinen Treffer (status {typ})")
            return []

        msg_nums = data[0].split()
        # Neueste zuerst, auf Kostendeckel begrenzen.
        msg_nums = msg_nums[::-1][:max_messages]
        listed = len(msg_nums)

        for num in msg_nums:
            typ, msg_data = imap.fetch(num, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            mail = _message_to_dict(msg, max_body)
            if mail["message_id"] in seen:
                continue
            results.append(mail)
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    print(f"[gmail] {len(results)} neue Newsletter (von {listed} gelistet, "
          f"{len(seen)} bereits gesehen)")
    return results


if __name__ == "__main__":
    for nl in fetch_newsletters():
        print(f"- {nl['subject']}  [{nl['sender']}]  "
              f"({len(nl['links'])} Links, {len(nl['body_text'])} Zeichen)")
