import _stubs; _stubs.install()

import os
import tempfile
import unittest
from email.message import EmailMessage
from unittest.mock import patch

import gmail_source as gs


def _raw(message_id, subject, html):
    m = EmailMessage()
    m["Message-ID"] = message_id
    m["From"] = "AI Weekly <hi@aiweekly.co>"
    m["Subject"] = subject
    m["Date"] = "Wed, 18 Jun 2026 10:00:00 +0000"
    m.set_content("plain fallback")
    m.add_alternative(html, subtype="html")
    return m.as_bytes()


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

    def test_plain_only_link_fallback(self):
        body, links = gs._body_and_links("see https://only.example/x now", None)
        self.assertEqual(links, [("https://only.example/x", "https://only.example/x")])

    def test_extract_prefers_plain_links_from_html(self):
        m = EmailMessage()
        m.set_content("Plain body http://x/p")
        m.add_alternative('<a href="http://x/h">h</a>', subtype="html")
        plain, html = gs._extract_plain_html(m)
        body, links = gs._body_and_links(plain, html)
        self.assertEqual(body, "Plain body http://x/p")       # plain bevorzugt
        self.assertIn(("h", "http://x/h"), links)             # Links aus HTML


class AccountTests(unittest.TestCase):
    def test_strips_and_removes_spaces(self):
        env = {"GMAIL_ADDRESS": " me@gmail.com \n",
               "GMAIL_APP_PASSWORD": " abcd efgh ijkl mnop "}
        with patch.dict(os.environ, env):
            addr, pw = gs.get_account()
        self.assertEqual(addr, "me@gmail.com")
        self.assertEqual(pw, "abcdefghijklmnop")              # interne Spaces weg

    def test_missing_raises(self):
        with patch.dict(os.environ, {"GMAIL_ADDRESS": "", "GMAIL_APP_PASSWORD": ""}):
            with self.assertRaises(RuntimeError):
                gs.get_account()


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
    def test_fetch_parses_newest_first_and_dedupes(self):
        msgs = {
            b"1": _raw("<a@x>", "Issue A", '<p>Hi <a href="http://a/1">l</a></p>'),
            b"2": _raw("<b@x>", "Issue B", '<p><a href="http://b/2">two</a></p>'),
            b"3": _raw("<c@x>", "Issue C", '<p><a href="http://c/3">three</a></p>'),
        }

        class FakeIMAP:
            def login(self, addr, pw): pass
            def select(self, folder, readonly=False): return ("OK", [b"3"])
            def search(self, charset, *criteria): return ("OK", [b"1 2 3"])
            def fetch(self, num, spec): return ("OK", [(b"hdr", msgs[num])])
            def logout(self): return ("BYE", [b""])

        tmp = tempfile.mkdtemp()
        env = {"GMAIL_ADDRESS": "me@gmail.com", "GMAIL_APP_PASSWORD": "abcd efgh ijkl mnop"}
        with patch.object(gs, "STATE_FILE", os.path.join(tmp, "seen.json")), \
             patch.object(gs.imaplib, "IMAP4_SSL", lambda host: FakeIMAP()), \
             patch.dict(os.environ, env):
            gs.mark_seen(["<a@x>"])                           # A bereits gesehen
            res = gs.fetch_newsletters()

        # neueste zuerst (3,2,1); A(1) übersprungen -> [C, B]
        self.assertEqual([r["subject"] for r in res], ["Issue C", "Issue B"])
        issue_b = next(r for r in res if r["subject"] == "Issue B")
        self.assertIn(("two", "http://b/2"), issue_b["links"])
        self.assertEqual(issue_b["sender"], "AI Weekly <hi@aiweekly.co>")
        self.assertEqual(issue_b["message_id"], "<b@x>")


if __name__ == "__main__":
    unittest.main()
