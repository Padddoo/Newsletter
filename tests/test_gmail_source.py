import _stubs; _stubs.install()

import base64
import os
import tempfile
import types
import unittest
from unittest.mock import patch

import gmail_source as gs


def _b64(s: bytes) -> str:
    return base64.urlsafe_b64encode(s).decode()


class ExtractionTests(unittest.TestCase):
    def test_html_to_text_and_links(self):
        html = ('<h1>AI Update</h1><p>New model from '
                '<a href="https://lab.example/model">ExampleLab</a> released.</p>'
                '<script>var x=1;</script>'
                '<a href="https://news.example/s2">Story two</a>'
                '<a href="mailto:foo@bar.com">mail</a>')
        text, links = gs._html_to_text_and_links(html)
        self.assertIn("AI Update", text)
        self.assertNotIn("var x", text)                       # script ignoriert
        self.assertIn(("ExampleLab", "https://lab.example/model"), links)
        self.assertIn(("Story two", "https://news.example/s2"), links)
        self.assertTrue(all(u.startswith("http") for _, u in links))  # mailto raus

    def test_decode(self):
        raw = "Hällo & Wörld\nzeile"
        self.assertEqual(gs._decode(_b64(raw.encode())), raw)

    def test_walk_parts_prefers_plain_links_from_html(self):
        payload = {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64(b"Plain body http://x/p")}},
            {"mimeType": "text/html", "body": {"data": _b64(b'<a href="http://x/h">h</a>')}},
        ]}
        plain, html = gs._walk_parts(payload)
        body, links = gs._body_and_links(plain, html)
        self.assertEqual(body, "Plain body http://x/p")       # plain bevorzugt
        self.assertIn(("h", "http://x/h"), links)             # Links aus HTML

    def test_plain_only_link_fallback(self):
        body, links = gs._body_and_links("see https://only.example/x now", None)
        self.assertEqual(links, [("https://only.example/x", "https://only.example/x")])


class SeenIdsTests(unittest.TestCase):
    def test_fifo_cap_and_dedupe(self):
        tmp = tempfile.mkdtemp()
        with patch.object(gs, "STATE_FILE", os.path.join(tmp, "seen.json")), \
             patch.object(gs, "SEEN_IDS_MAX", 3):
            self.assertEqual(gs.load_seen_ids(), [])
            gs.mark_seen(["a", "b"])
            gs.mark_seen(["b", "c", "d"])                     # b ist Duplikat
            self.assertEqual(gs.load_seen_ids(), ["b", "c", "d"])  # FIFO cap 3


class FetchTests(unittest.TestCase):
    def test_fetch_skips_seen_ids(self):
        fake = {
            "m1": {"payload": {"headers": [{"name": "From", "value": "News A"},
                                           {"name": "Subject", "value": "Issue 1"}],
                               "mimeType": "text/html",
                               "body": {"data": _b64(b'<a href="http://a/1">link</a>')}}},
            "m2": {"payload": {"headers": [{"name": "From", "value": "News B"},
                                           {"name": "Subject", "value": "Issue 2"}],
                               "mimeType": "text/plain",
                               "body": {"data": _b64(b"plain http://b/2")}}},
        }

        class Exe:
            def __init__(self, v): self.v = v
            def execute(self): return self.v

        class Msgs:
            def list(self, **k):
                return Exe({"messages": [{"id": "m1"}, {"id": "m2"}, {"id": "old"}]})
            def get(self, userId, id, format):
                return Exe(fake[id])

        class Svc:
            def users(self):
                return types.SimpleNamespace(messages=lambda: Msgs())

        tmp = tempfile.mkdtemp()
        with patch.object(gs, "STATE_FILE", os.path.join(tmp, "seen.json")), \
             patch.object(gs, "build_service", lambda: Svc()):
            gs.mark_seen(["old"])
            res = gs.fetch_newsletters()
        self.assertEqual([r["subject"] for r in res], ["Issue 1", "Issue 2"])
        self.assertEqual(res[0]["links"], [("link", "http://a/1")])


if __name__ == "__main__":
    unittest.main()
