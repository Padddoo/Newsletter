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
            stories = A.analyze_newsletters([self._mail()])
        self.assertEqual(len(stories), 2)                       # URL-lose Story verworfen
        self.assertEqual(stories[0]["source_newsletter"], "AI Weekly")  # aus Sender
        self.assertEqual(len(stories[1]["headline"].split()), 10)       # hart gekürzt
        self.assertTrue(all(s["url"].startswith("http") for s in stories))

    def test_decompose_fallback_yields_nothing(self):
        with patch.object(A, "_call_claude", return_value="kaputt"):
            self.assertEqual(A.analyze_newsletters([self._mail()]), [])


if __name__ == "__main__":
    unittest.main()
