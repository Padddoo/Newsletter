import _stubs; _stubs.install()

import base64
import os
import tempfile
import types
import unittest
from unittest.mock import patch

import requests  # Stub aus _stubs

import config
import deliver


def _analyzed():
    return {"ai_news": [
        {"title": "GPT-5 <released>", "url": "http://a/1", "source": "OpenAI",
         "summary_de": "GPT-5 ist da.", "reason": "großes Release", "priority": "hoch"},
        {"title": "Kleiner Post", "url": "http://a/2", "source": "Blog",
         "summary_de": "Wenig.", "reason": "", "priority": "niedrig"},
    ]}


def _stories():
    prios = ["hoch", "hoch", "mittel", "mittel", "niedrig", "niedrig"]
    return [{"headline": f"Story {i}", "url": f"http://s/{i}",
             "source_newsletter": "AI Weekly", "priority": p}
            for i, p in enumerate(prios)]


class DashboardTests(unittest.TestCase):
    def _build(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "dashboard.html")
        with patch.object(deliver, "OUTPUT_DIR", tmp), \
             patch.object(deliver, "DASHBOARD_FILE", path):
            deliver.build_dashboard(_analyzed(), _stories())
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_two_tabs_and_escaping(self):
        html = self._build()
        self.assertIn("tab-ai_news", html)
        self.assertIn("tab-newsletter", html)
        self.assertIn("GPT-5 &lt;released&gt;", html)        # HTML-escaped
        self.assertIn("Warum relevant", html)
        self.assertIn("AI Weekly", html)                     # Newsletter-Gruppierung

    def test_cross_posting_count_is_exactly_n(self):
        html = self._build()
        self.assertEqual(html.count("aus Newsletter"), config.NEWSLETTER_TOP_N_IN_AI)


class TelegramTests(unittest.TestCase):
    def test_skipped_without_secrets(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_CHAT_ID", None)
            self.assertFalse(deliver.send_telegram(_analyzed(), _stories()))

    def test_posts_with_secrets(self):
        captured = {}

        def fake_post(url, data=None, timeout=None):
            captured["url"] = url
            captured["data"] = data
            return types.SimpleNamespace(raise_for_status=lambda: None)

        env = {"TELEGRAM_BOT_TOKEN": "TOK", "TELEGRAM_CHAT_ID": "42"}
        with patch.dict(os.environ, env), \
             patch.object(requests, "post", fake_post):
            ok = deliver.send_telegram(_analyzed(), _stories())
        self.assertTrue(ok)
        self.assertIn("/botTOK/sendMessage", captured["url"])
        self.assertEqual(captured["data"]["chat_id"], "42")
        self.assertIn("GPT-5", captured["data"]["text"])


class EmailTests(unittest.TestCase):
    def test_sends_via_gmail(self):
        sent = {}

        class Exe:
            def __init__(self, v): self.v = v
            def execute(self): return self.v

        class Msgs:
            def send(self, userId, body):
                sent["raw"] = body["raw"]
                return Exe({})

        class Users:
            def getProfile(self, userId):
                return Exe({"emailAddress": "bot@nl.com"})
            def messages(self):
                return Msgs()

        class Svc:
            def users(self):
                return Users()

        with patch.object(deliver.gmail_source, "build_service", lambda: Svc()), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMAIL_TO", None)
            ok = deliver.send_email(_analyzed(), _stories())
        self.assertTrue(ok)
        decoded = base64.urlsafe_b64decode(sent["raw"]).decode("utf-8", "replace")
        self.assertIn("To: mail@tobiasreich.de", decoded)
        self.assertIn("From: bot@nl.com", decoded)
        self.assertIn("Subject: AI-Briefing", decoded)
        self.assertIn("GPT-5", decoded)

    def test_empty_email_to_falls_back_to_default(self):
        # Die Action setzt EMAIL_TO immer; bei fehlendem Secret als leerer String.
        sent = {}

        class Exe:
            def __init__(self, v): self.v = v
            def execute(self): return self.v

        class Svc:
            def users(self):
                return types.SimpleNamespace(
                    getProfile=lambda userId: Exe({"emailAddress": "bot@nl.com"}),
                    messages=lambda: types.SimpleNamespace(
                        send=lambda userId, body: (sent.__setitem__("raw", body["raw"]) or Exe({}))))

        with patch.object(deliver.gmail_source, "build_service", lambda: Svc()), \
             patch.dict(os.environ, {"EMAIL_TO": ""}):  # leerer String wie in der Action
            ok = deliver.send_email(_analyzed(), _stories())
        self.assertTrue(ok)
        decoded = base64.urlsafe_b64decode(sent["raw"]).decode("utf-8", "replace")
        self.assertIn("To: mail@tobiasreich.de", decoded)  # Default greift trotz leerem EMAIL_TO


if __name__ == "__main__":
    unittest.main()
