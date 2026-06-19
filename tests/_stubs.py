"""
Gemeinsames Test-Setup: src/ auf den Pfad legen und externe Libs durch leichte
Stubs ersetzen. So laufen die Logik-/Akzeptanztests deterministisch und ohne
Netzwerk oder Drittanbieter-Pakete (feedparser, google-*, anthropic, requests).

Jedes Testmodul ruft ganz oben `import _stubs; _stubs.install()` auf, BEVOR es
die src-Module importiert.
"""
import os
import sys
import types

_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(root, "src")
    if src not in sys.path:
        sys.path.insert(0, src)

    def mod(name: str) -> types.ModuleType:
        m = types.ModuleType(name)
        sys.modules[name] = m
        return m

    # feedparser
    fp = mod("feedparser")
    fp.parse = lambda *a, **k: None

    # requests
    req = mod("requests")
    req.RequestException = type("RequestException", (Exception,), {})
    req.get = lambda *a, **k: None
    req.post = lambda *a, **k: None

    # anthropic (analyst importiert lazy)
    anth = mod("anthropic")
    anth.Anthropic = lambda *a, **k: None

    # Hinweis: imaplib/smtplib/email sind Standardbibliothek und brauchen keine
    # Stubs; Tests patchen IMAP4_SSL / SMTP_SSL gezielt.

    _INSTALLED = True
