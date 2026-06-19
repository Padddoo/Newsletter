import _stubs; _stubs.install()

import base64
import os
import tempfile
import types
import unittest
from datetime import datetime, timezone
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


def _fake_gmail_service(sent_email):
    msg = {"payload": {"headers": [{"name": "From", "value": '"TLDR AI" <hi@tldr.tech>'},
                                   {"name": "Subject", "value": "Issue 1"}],
                       "mimeType": "text/html",
                       "body": {"data": base64.urlsafe_b64encode(
                           b'<p>News <a href="http://s/1">link</a></p>').decode()}}}

    class Exe:
        def __init__(self, v): self.v = v
        def execute(self): return self.v

    class Msgs:
        def list(self, **k): return Exe({"messages": [{"id": "m1"}]})
        def get(self, userId, id, format): return Exe(msg)
        def send(self, userId, body):
            sent_email.append(body["raw"]); return Exe({})

    class Users:
        def messages(self): return Msgs()
        def getProfile(self, userId): return Exe({"emailAddress": "bot@nl.com"})

    class Svc:
        def users(self): return Users()

    return Svc()


class RunIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sent_email = []
        self.tg = []

        def fake_post(url, data=None, timeout=None):
            self.tg.append(data)
            return types.SimpleNamespace(raise_for_status=lambda: None)

        env = {"TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_CHAT_ID": "9",
               "GMAIL_REFRESH_TOKEN": "r", "GMAIL_CLIENT_ID": "c",
               "GMAIL_CLIENT_SECRET": "s", "ANTHROPIC_API_KEY": "k"}

        self.patchers = [
            patch.object(deliver, "OUTPUT_DIR", self.tmp),
            patch.object(deliver, "DASHBOARD_FILE", os.path.join(self.tmp, "dashboard.html")),
            patch.object(gmail_source, "STATE_FILE", os.path.join(self.tmp, "seen.json")),
            patch.object(collector, "_fetch_feed", lambda url: FakeParsed()),
            patch.object(analyst, "_call_claude", _fake_claude),
            patch.object(gmail_source, "build_service",
                         lambda: _fake_gmail_service(self.sent_email)),
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
        self.assertEqual(len(self.sent_email), 1)            # E-Mail gesendet
        self.assertEqual(len(self.tg), 1)                    # Telegram gesendet
        self.assertEqual(gmail_source.load_seen_ids(), ["m1"])

    def test_dedupe_on_second_run(self):
        self.assertEqual(run.main(), 0)
        self.assertEqual(run.main(), 0)
        # zweiter Lauf: m1 bereits gesehen -> keine Newsletter-Story mehr
        self.assertNotIn("News mit Link", self._html())

    def test_gmail_outage_does_not_block_rss(self):
        def boom():
            raise RuntimeError("invalid_grant simuliert")
        with patch.object(gmail_source, "fetch_newsletters", boom):
            self.assertEqual(run.main(), 0)
        html = self._html()
        self.assertIn("GPT-5 released", html)                # RSS intakt
        self.assertIn("Keine Newsletter-Stories", html)      # Newsletter leer


if __name__ == "__main__":
    unittest.main()
