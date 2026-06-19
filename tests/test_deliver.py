import _stubs; _stubs.install()

import os
import smtplib
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
            return types.SimpleNamespace(ok=True, status_code=200, text="{}")

        env = {"TELEGRAM_BOT_TOKEN": "TOK", "TELEGRAM_CHAT_ID": "42"}
        with patch.dict(os.environ, env), \
             patch.object(requests, "post", fake_post):
            ok = deliver.send_telegram(_analyzed(), _stories())
        self.assertTrue(ok)
        self.assertIn("/botTOK/sendMessage", captured["url"])
        self.assertEqual(captured["data"]["chat_id"], "42")
        self.assertIn("GPT-5", captured["data"]["text"])

    def test_returns_false_on_api_error(self):
        def fake_post(url, data=None, timeout=None):
            return types.SimpleNamespace(
                ok=False, status_code=400,
                text='{"ok":false,"description":"Bad Request: chat not found"}')

        env = {"TELEGRAM_BOT_TOKEN": "TOK", "TELEGRAM_CHAT_ID": "999"}
        with patch.dict(os.environ, env), patch.object(requests, "post", fake_post):
            self.assertFalse(deliver.send_telegram(_analyzed(), _stories()))


class _FakeSMTP:
    """Fake smtplib.SMTP_SSL als Context-Manager, fängt send_message ab."""
    sent = {}

    def __init__(self, host, port):
        _FakeSMTP.sent.clear()

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def login(self, user, password): _FakeSMTP.sent["login"] = (user, password)
    def send_message(self, msg): _FakeSMTP.sent["msg"] = msg


class EmailTests(unittest.TestCase):
    def test_sends_to_all_config_recipients(self):
        with patch.object(deliver.gmail_source, "get_account",
                          lambda: ("bot@nl.com", "apppw")), \
             patch.object(deliver.smtplib, "SMTP_SSL", _FakeSMTP), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMAIL_TO", None)
            ok = deliver.send_email(_analyzed(), _stories())
        self.assertTrue(ok)
        self.assertEqual(_FakeSMTP.sent["login"], ("bot@nl.com", "apppw"))
        msg = _FakeSMTP.sent["msg"]
        self.assertEqual(msg["To"], "mail@tobiasreich.de, elena.sroka@gmail.com")
        self.assertEqual(msg["From"], "bot@nl.com")
        self.assertTrue(msg["Subject"].startswith("AI-Briefing"))
        self.assertIn("GPT-5", msg.as_string())

    def test_empty_email_to_falls_back_to_default(self):
        # Die Action setzt EMAIL_TO immer; bei fehlendem Secret als leerer String.
        with patch.object(deliver.gmail_source, "get_account",
                          lambda: ("bot@nl.com", "apppw")), \
             patch.object(deliver.smtplib, "SMTP_SSL", _FakeSMTP), \
             patch.dict(os.environ, {"EMAIL_TO": ""}):
            ok = deliver.send_email(_analyzed(), _stories())
        self.assertTrue(ok)
        self.assertEqual(_FakeSMTP.sent["msg"]["To"],
                         "mail@tobiasreich.de, elena.sroka@gmail.com")

    def test_env_email_to_overrides_with_comma_list(self):
        with patch.object(deliver.gmail_source, "get_account",
                          lambda: ("bot@nl.com", "apppw")), \
             patch.object(deliver.smtplib, "SMTP_SSL", _FakeSMTP), \
             patch.dict(os.environ, {"EMAIL_TO": "a@x.com, b@y.com , a@x.com"}):
            ok = deliver.send_email(_analyzed(), _stories())
        self.assertTrue(ok)
        # kommagetrennt geparst, getrimmt, dedupliziert
        self.assertEqual(_FakeSMTP.sent["msg"]["To"], "a@x.com, b@y.com")


if __name__ == "__main__":
    unittest.main()
