import _stubs; _stubs.install()

import unittest
from unittest.mock import patch

import analyst as A


class PureHelperTests(unittest.TestCase):
    def test_truncate_headline_caps_at_ten_words(self):
        long = "Eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf"
        self.assertEqual(len(A.truncate_headline(long).split()), 10)
        self.assertEqual(A.truncate_headline("kurz und knapp"), "kurz und knapp")

    def test_normalize_priority(self):
        self.assertEqual(A._normalize_priority("HIGH"), "hoch")
        self.assertEqual(A._normalize_priority("medium"), "mittel")
        self.assertEqual(A._normalize_priority("quatsch"), "mittel")

    def test_clean_sender(self):
        self.assertEqual(A._clean_sender('"AI Weekly" <hi@aiweekly.co>'), "AI Weekly")
        self.assertEqual(A._clean_sender("hi@aiweekly.co"), "aiweekly.co")

    def test_parse_json_variants(self):
        self.assertEqual(A._parse_json('```json\n{"a":1}\n```'), {"a": 1})
        self.assertEqual(A._parse_json("Hier: [1,2,3] danke"), [1, 2, 3])
        with self.assertRaises(ValueError):
            A._parse_json("kein json")


class RssPathTests(unittest.TestCase):
    def _articles(self):
        return [
            {"title": "GPT-5 released", "url": "http://a/1", "source": "OpenAI",
             "summary": "big", "keyword_score": 2, "topic": "ai_news"},
            {"title": "Minor post", "url": "http://a/2", "source": "Blog",
             "summary": "meh", "keyword_score": 0, "topic": "ai_news"},
        ]

    def test_analyze_all_applies_ratings_and_sorts(self):
        resp = ('[{"index":0,"priority":"hoch","reason":"Release","summary_de":"GPT-5 ist da."},'
                '{"index":1,"priority":"niedrig","reason":"egal","summary_de":"Klein."}]')
        with patch.object(A, "_call_claude", return_value=resp):
            out = A.analyze_all({"ai_news": self._articles()})
        ai = out["ai_news"]
        self.assertEqual(ai[0]["title"], "GPT-5 released")
        self.assertEqual(ai[0]["priority"], "hoch")
        self.assertEqual(ai[0]["summary_de"], "GPT-5 ist da.")
        self.assertEqual(ai[1]["priority"], "niedrig")

    def test_analyze_all_fallback_keeps_articles(self):
        with patch.object(A, "_call_claude", return_value="kein JSON"):
            out = A.analyze_all({"ai_news": self._articles()})
        self.assertEqual(len(out["ai_news"]), 2)
        self.assertTrue(all(a["priority"] == "mittel" for a in out["ai_news"]))


class NewsletterPathTests(unittest.TestCase):
    def _mail(self):
        return {"message_id": "m1", "sender": '"AI Weekly" <hi@aiweekly.co>',
                "subject": "Issue 5", "date": "today", "body_text": "...",
                "links": [("ExampleLab", "https://lab.example/x")]}

    def test_decompose_validates_headline_and_url(self):
        resp = ('{"stories": ['
                '{"headline": "Neues Modell von ExampleLab erschienen", "url": "https://lab.example/x", "priority": "hoch"},'
                '{"headline": "Story mit eins zwei drei vier fünf sechs sieben acht neun zehn elf Wörtern", "url": "https://lab.example/y", "priority": "mittel"},'
                '{"headline": "Story ohne Link", "url": "", "priority": "mittel"}'
                ']}')
        with patch.object(A, "_call_claude", return_value=resp):
            stories, processed = A.analyze_newsletters([self._mail()])
        self.assertEqual(len(stories), 2)                       # URL-lose Story verworfen
        self.assertEqual(stories[0]["source_newsletter"], "AI Weekly")  # aus Sender
        self.assertEqual(len(stories[1]["headline"].split()), 10)       # hart gekürzt
        self.assertTrue(all(s["url"].startswith("http") for s in stories))
        self.assertEqual(processed, ["m1"])  # erfolgreiche Mail -> als gesehen markierbar

    def test_decompose_fallback_yields_nothing(self):
        # Claude-Ausfall: keine Stories UND keine processed_ids -> Mail bleibt
        # ungesehen und wird im nächsten Lauf erneut versucht (kein Verlust).
        with patch.object(A, "_call_claude", return_value="kaputt"):
            stories, processed = A.analyze_newsletters([self._mail()])
        self.assertEqual(stories, [])
        self.assertEqual(processed, [])

    def test_decompose_marks_seen_even_with_zero_stories(self):
        # Claude antwortet gültig, aber ohne brauchbare Stories (z. B. reine
        # Werbung): Mail gilt als verarbeitet -> wird als gesehen markiert.
        with patch.object(A, "_call_claude", return_value='{"stories": []}'):
            stories, processed = A.analyze_newsletters([self._mail()])
        self.assertEqual(stories, [])
        self.assertEqual(processed, ["m1"])


class ApiErrorTrackingTests(unittest.TestCase):
    def setUp(self):
        A.reset_api_errors()
        self.addCleanup(A.reset_api_errors)

    def _boom(self, msg):
        def _raise(system, user, max_tokens=4096):
            raise RuntimeError(msg)
        return _raise

    def test_limit_error_is_recorded_and_detected(self):
        msg = ("Error code: 400 - {'error': {'message': 'You have reached your "
               "specified API usage limits. ...'}}")
        with patch.object(A, "_call_claude", self._boom(msg)):
            stories, processed = A.analyze_newsletters(
                [{"message_id": "m1", "sender": "x", "subject": "s",
                  "body_text": "b", "links": []}])
        self.assertEqual(stories, [])
        self.assertEqual(processed, [])              # nichts als gesehen markieren
        self.assertEqual(len(A.api_errors()), 1)
        self.assertIsNotNone(A.limit_reason())       # Frühwarnung greift

    def test_parse_error_is_not_an_api_error(self):
        # Gültiger Call, aber Müll-Antwort: das ist KEIN API-Fehler -> keine
        # Frühwarnung, damit ein einzelner Parse-Ausreißer nicht den Lauf rotfärbt.
        with patch.object(A, "_call_claude", return_value="kein json"):
            stories, processed = A.analyze_newsletters(
                [{"message_id": "m1", "sender": "x", "subject": "s",
                  "body_text": "b", "links": []}])
        self.assertEqual(stories, [])
        self.assertEqual(A.api_errors(), [])
        self.assertIsNone(A.limit_reason())

    def test_reset_clears_errors(self):
        with patch.object(A, "_call_claude", self._boom("authentication_error")):
            A.analyze_newsletters([{"message_id": "m1", "sender": "x",
                                    "subject": "s", "body_text": "b", "links": []}])
        self.assertIsNotNone(A.limit_reason())
        A.reset_api_errors()
        self.assertEqual(A.api_errors(), [])
        self.assertIsNone(A.limit_reason())


class _FakeUsage:
    def __init__(self, **kw):
        self.input_tokens = kw.get("input_tokens", 0)
        self.output_tokens = kw.get("output_tokens", 0)
        self.cache_read_input_tokens = kw.get("cache_read_input_tokens", 0)
        self.cache_creation_input_tokens = kw.get("cache_creation_input_tokens", 0)


class UsageTrackingTests(unittest.TestCase):
    def setUp(self):
        A.reset_usage()
        self.addCleanup(A.reset_usage)

    def test_record_aggregates_per_label(self):
        A._record_usage("newsletter", _FakeUsage(input_tokens=100, output_tokens=20))
        A._record_usage("newsletter", _FakeUsage(input_tokens=50, output_tokens=10))
        A._record_usage("rss", _FakeUsage(input_tokens=300, output_tokens=40))
        s = A.usage_summary()
        self.assertEqual(s["newsletter"]["calls"], 2)
        self.assertEqual(s["newsletter"]["input_tokens"], 150)
        self.assertEqual(s["newsletter"]["output_tokens"], 30)
        self.assertEqual(s["rss"]["calls"], 1)

    def test_cost_estimate_sonnet(self):
        A._record_usage("rss", _FakeUsage(input_tokens=1_000_000,
                                          output_tokens=1_000_000))
        # 1M in * $3 + 1M out * $15 = $18
        self.assertAlmostEqual(A.estimated_cost_usd("claude-sonnet-4-6"), 18.0, places=4)

    def test_cost_estimate_handles_cache_and_none(self):
        A._record_usage("rss", _FakeUsage(cache_read_input_tokens=1_000_000))
        A._record_usage("rss", None)  # darf nicht crashen
        # 1M Cache-Read * $3 * 0.1 = $0.30
        self.assertAlmostEqual(A.estimated_cost_usd("claude-sonnet-4-6"), 0.30, places=4)

    def test_reset_clears_usage(self):
        A._record_usage("rss", _FakeUsage(input_tokens=10))
        A.reset_usage()
        self.assertEqual(A.usage_summary(), {})


if __name__ == "__main__":
    unittest.main()
