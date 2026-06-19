import _stubs; _stubs.install()

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import collector


class FakeParsed:
    def __init__(self, title, entries):
        self.feed = {"title": title}
        self.entries = entries
        self.bozo = False


def _entry(title, link, summary="", dt=None):
    e = {"title": title, "link": link, "summary": summary}
    if dt is not None:
        e["published_parsed"] = dt.timetuple()
    return e


class HelperTests(unittest.TestCase):
    def test_strip_html(self):
        self.assertEqual(collector._strip_html("<p>Hello &amp; <b>world</b></p>"),
                         "Hello & world")

    def test_keyword_score(self):
        self.assertEqual(
            collector._keyword_score("New GPT model released", ["gpt", "model", "FDA"]), 2)

    def test_title_hash_normalises(self):
        self.assertEqual(collector._title_hash("Hello  World"),
                         collector._title_hash("hello world"))


class CollectTopicTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)

    def test_window_dedupe_and_sort(self):
        entries = [
            _entry("New GPT model released", "http://x/1", "<b>big</b> release", self.now),
            _entry("Old news", "http://x/2", "", self.now - timedelta(days=5)),
            _entry("new gpt MODEL released", "http://x/3", "", self.now),  # Duplikat
            _entry("Undated tool launch", "http://x/4", "agent tool"),     # ohne Datum
        ]
        topic = {"name": "AI", "lookback_hours": 72,
                 "keywords": ["gpt", "model", "agent", "tool"], "feeds": ["u"]}
        with patch.object(collector, "_fetch_feed",
                          return_value=FakeParsed("FakeSource", entries)):
            res = collector.collect_topic("ai_news", topic)
        titles = [a["title"] for a in res]
        self.assertNotIn("Old news", titles)                 # Zeitfenster
        self.assertEqual(len(res), 2)                        # Duplikat entfernt
        self.assertEqual(res[0]["title"], "New GPT model released")  # Sortierung
        self.assertEqual(res[0]["source"], "FakeSource")
        self.assertEqual(res[0]["summary"], "big release")   # HTML gestrippt
        self.assertNotIn("_published_dt", res[0])            # internes Feld entfernt

    def test_dead_feed_does_not_crash(self):
        topic = {"name": "AI", "lookback_hours": 72, "keywords": [], "feeds": ["u"]}
        with patch.object(collector, "_fetch_feed", return_value=None):
            res = collector.collect_topic("ai_news", topic)
        self.assertEqual(res, [])

    def test_collect_all_skips_disabled_topics(self):
        entries = [_entry("x", "http://x/1", "", self.now)]
        with patch.object(collector, "_fetch_feed",
                          return_value=FakeParsed("S", entries)):
            out = collector.collect_all()
        self.assertEqual(set(out.keys()), {"ai_news"})       # medtech disabled


if __name__ == "__main__":
    unittest.main()
