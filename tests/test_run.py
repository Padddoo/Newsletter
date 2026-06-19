import _stubs; _stubs.install()

import os
import tempfile
import types
import unittest
from datetime import datetime, timezone
from email.message import EmailMessage
from unittest.mock import patch

import analyst
import collector
import deliver
import gmail_source
import run


class FakeParsed:
    feed = {"title": "OpenAI"}
    bozo = False
    entries = [{"title": "GPT-5 released", "link": "http://a/1",
                "summary": "big model",
                "published_parsed": datetime.now(timezone.utc).timetuple()}]


def _fake_claude(system, user, max_tokens=4096):
    if "Zerlege" in user:
        return ('{"stories":[{"headline":"News mit Link","url":"http://s/1",'
                '"source_newsletter":"TLDR AI","priority":"hoch"}]}')
    return '[{"index":0,"priority":"hoch","reason":"Release","summary_de":"GPT-5 ist da."}]'


def _raw_newsletter():
    m = EmailMessage()
    m["Message-ID"] = "<m1@tldr>"
    m["From"] = "TLDR AI <hi@tldr.tech>"
    m["Subject"] = "Issue 1"
    m["Date"] = "Wed, 18 Jun 2026 10:00:00 +0000"
    m.set_content("plain")
    m.add_alternative('<p>News <a href="http://s/1">link</a></p>', subtype="html")
    return m.as_bytes()


class _FakeIMAP:
    def __init__(self, host): pass
    def login(self, addr, pw): pass
    def select(self, folder, readonly=False): return ("OK", [b"1"])
    def search(self, charset, *criteria): return ("OK", [b"1"])
    def fetch(self, num, spec): return ("OK", [(b"hdr", _raw_newsletter())])
    def logout(self): return ("BYE", [b""])


class RunIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.smtp_sent = []
        self.tg = []

        def fake_post(url, data=None, timeout=None):
            self.tg.append(data)
            return types.SimpleNamespace(ok=True, status_code=200, text="{}")

        sent = self.smtp_sent

        class FakeSMTP:
            def __init__(self, host, port): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def login(self, u, p): pass
            def send_message(self, msg): sent.append(msg)

        env = {"TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_CHAT_ID": "9",
               "GMAIL_ADDRESS": "me@gmail.com", "GMAIL_APP_PASSWORD": "app pw",
               "ANTHROPIC_API_KEY": "k"}

        self.patchers = [
            patch.object(deliver, "OUTPUT_DIR", self.tmp),
            patch.object(deliver, "DASHBOARD_FILE", os.path.join(self.tmp, "dashboard.html")),
            patch.object(gmail_source, "STATE_FILE", os.path.join(self.tmp, "seen.json")),
            patch.object(collector, "_fetch_feed", lambda url: FakeParsed()),
            patch.object(analyst, "_call_claude", _fake_claude),
            patch.object(gmail_source.imaplib, "IMAP4_SSL", _FakeIMAP),
            patch.object(deliver.smtplib, "SMTP_SSL", FakeSMTP),
            patch("requests.post", fake_post),
            patch.dict(os.environ, env),
        ]
        for p in self.patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patchers])

    def _html(self):
        with open(deliver.DASHBOARD_FILE, encoding="utf-8") as fh:
            return fh.read()

    def test_full_run(self):
        self.assertEqual(run.main(), 0)
        html = self._html()
        self.assertIn("GPT-5 released", html)
        self.assertIn("News mit Link", html)
        self.assertEqual(len(self.smtp_sent), 1)             # E-Mail gesendet
        self.assertEqual(len(self.tg), 1)                    # Telegram gesendet
        self.assertEqual(gmail_source.load_seen_ids(), ["<m1@tldr>"])

    def test_dedupe_on_second_run(self):
        self.assertEqual(run.main(), 0)
        self.assertEqual(run.main(), 0)
        # zweiter Lauf: <m1@tldr> bereits gesehen -> keine Newsletter-Story mehr
        self.assertNotIn("News mit Link", self._html())

    def test_gmail_outage_does_not_block_rss(self):
        def boom():
            raise RuntimeError("IMAP-Login fehlgeschlagen simuliert")
        with patch.object(gmail_source, "fetch_newsletters", boom):
            self.assertEqual(run.main(), 0)
        html = self._html()
        self.assertIn("GPT-5 released", html)                # RSS intakt
        self.assertIn("Keine Newsletter-Stories", html)      # Newsletter leer


if __name__ == "__main__":
    unittest.main()
