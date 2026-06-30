"""
Zentrale Konfiguration des News-Agent.

Enthält ausschließlich statische Konfiguration (Themen, Feeds, Profile, Settings).
Geheimnisse (API-Keys, App-Passwörter) werden NICHT hier gehalten, sondern zur
Laufzeit aus Environment-Variablen gelesen (lokal via .env, in der GitHub Action
aus GitHub Secrets). Siehe README / Spec §8.

Scope v1: nur das Thema "ai_news" ist aktiv. "medtech" ist geparkt
(enabled=False) und kann später additiv reaktiviert werden
(siehe PROJECT_OVERVIEW.md §10).
"""

# ---------------------------------------------------------------------------
# Claude / Anthropic
# ---------------------------------------------------------------------------
# Default-Modell (Fallback für Prozesse ohne eigene Zuordnung).
ANTHROPIC_MODEL = "claude-sonnet-4-6"

# Modell je Prozess (Kostenoptimierung): Die Newsletter-Zerlegung ist reine
# Extraktion und der mit Abstand größte Token-Verbraucher — dafür reicht das
# günstigere Haiku ($1/$5 statt $3/$15). Die RSS-Bewertung bleibt auf Sonnet.
ANTHROPIC_MODELS = {
    "rss": "claude-sonnet-4-6",
    "newsletter": "claude-haiku-4-5",
}

# Kostendeckel: maximale Anzahl RSS-Artikel pro Thema, die an Claude zur
# Bewertung gehen (nach Keyword-Sortierung die Top-N).
MAX_ARTICLES_TO_RATE = 30

# Newsletter-Zerlegung: so viele Mails werden in EINEM Claude-Aufruf gebündelt
# (statt 1 Call pro Mail). Spart wiederholten Prompt-Overhead und Calls;
# kleine Gruppen begrenzen Prompt-Größe und Fehler-Auswirkung pro Call.
NEWSLETTER_BATCH_SIZE = 5

# ---------------------------------------------------------------------------
# Headlines / Cross-Posting
# ---------------------------------------------------------------------------
HEADLINE_MAX_WORDS = 10        # harte Obergrenze für Newsletter-Headlines
NEWSLETTER_TOP_N_IN_AI = 5     # so viele Top-Newsletter-Items zusätzlich im AI-News-Tab

# ---------------------------------------------------------------------------
# RSS-Themen
# ---------------------------------------------------------------------------
TOPICS = {
    "ai_news": {
        "name": "AI News",
        "enabled": True,
        "lookback_hours": 72,  # Lab-Blogs posten nur wenige Male pro Woche
        "feeds": [
            "https://openai.com/news/rss.xml",
            "https://huggingface.co/blog/feed.xml",
            "https://research.google/blog/rss/",
            "https://www.technologyreview.com/feed/",
            # Deaktiviert (liefern aktuell keine nutzbaren Daten):
            #   anthropic.com/rss.xml      -> 404 (URL existiert nicht mehr)
            #   marktechpost.com/feed/     -> liefert kein valides XML (Anti-Bot)
            # Bei Bedarf mit funktionierender URL wieder aufnehmen.
        ],
        "keywords": [
            "model", "release", "open source", "open-weight", "API",
            "agent", "fine-tuning", "benchmark", "multimodal", "reasoning",
            "inference", "RAG", "LLM", "GPT", "Claude", "Gemini", "Llama",
            "tool", "framework", "research", "paper",
        ],
        "profile": (
            "Sicht eines praxisorientierten AI-Anwenders, der am Ball bleiben "
            "will. Relevant sind: neue Modelle und Releases, konkrete Tools und "
            "Frameworks, APIs sowie Forschung mit klarem Praxisbezug. Weniger "
            "relevant: reine Meinungsstücke, Hype ohne Substanz, Unternehmens-PR "
            "ohne Produktnutzen."
        ),
    },

    # --- GEPARKT (Scope v1): MedTech ist deaktiviert. Der Collector iteriert
    #     generisch über TOPICS und überspringt enabled=False automatisch.
    #     Reaktivierung: enabled=True + dritter Dashboard-Tab (siehe §10).
    "medtech": {
        "name": "MedTech",
        "enabled": False,
        "lookback_hours": 26,
        "feeds": [
            "https://www.medtechdive.com/feeds/news/",
            "https://www.massdevice.com/feed/",
            "https://www.fiercepharma.com/rss/xml",
            "https://www.fiercebiotech.com/rss/xml",
            "https://www.biopharmadive.com/feeds/news/",
            "https://medcitynews.com/feed/",
        ],
        "keywords": [
            "acquisition", "merger", "M&A", "private equity", "deal",
            "dermatology", "aesthetics", "FDA", "funding", "IPO",
        ],
        "profile": (
            "Sicht eines PE-Investors mit MedTech-/Dermatologie-Fokus. Relevant "
            "sind Deal- und Marktnachrichten (M&A, Finanzierungen, Markteintritte, "
            "Regulatorik) mit Bezug zu Dermatologie/Ästhetik."
        ),
    },
}

# ---------------------------------------------------------------------------
# Gmail-Newsletter-Quelle (AI) — Zugriff via IMAP (App-Passwort)
# ---------------------------------------------------------------------------
NEWSLETTER = {
    "enabled": True,
    "name": "AI Newsletter",

    # SCHRITT 1: simpel — auf Gmails eigenen Spamfilter verlassen. Wir lesen nur
    # den Posteingang (INBOX); was in [Gmail]/Spam liegt, wird nicht erfasst.
    "imap_folder": "INBOX",
    "only_unread": True,             # entspricht "is:unread"
    "lookback_days": 2,              # entspricht "newer_than:2d"
    "max_messages": 25,              # Kostendeckel
    "max_body_chars": 3500,          # Body-Kürzung pro Mail (Token-Deckel)

    "profile": (
        "Zerlege die Newsletter-Mail in ihre einzelnen Stories/Items. Extrahiere "
        "nur AI-relevante Stories (Modelle, Tools, Releases, Forschung mit "
        "Praxisbezug). Werbung, Sponsoren-Blöcke, Job-Listings und reine "
        "Meinungsstücke ignorieren. Jede Headline ist nüchtern und konkret, "
        "kein Clickbait, maximal 10 Wörter, auf Deutsch."
    ),

    # --- Vorbereitet für SCHRITT 2 (Newsletter-Härtung, jetzt NICHT aktiv) ---
    # "strategy": "gmail_spam",        # später: "allowlist" | "label"
    # "allowed_senders": [],           # später mit echten Abo-Absendern füllen
    # "imap_folder": "Newsletter",     # später bei Label-/Ordner-Strategie
    # "content_spam_check": False,     # später: True für inhaltlichen Claude-Check
}

# ---------------------------------------------------------------------------
# Gmail-Zugang via App-Passwort (IMAP lesen + SMTP senden)
#   Secrets: GMAIL_ADDRESS + GMAIL_APP_PASSWORD
#   Voraussetzung: 2FA am Konto aktiv, App-Passwort erzeugt.
# ---------------------------------------------------------------------------
IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465                      # SSL

# ---------------------------------------------------------------------------
# E-Mail-Versand (Briefing per Gmail an die eigene Hauptadresse)
# ---------------------------------------------------------------------------
EMAIL = {
    "enabled": True,
    # Empfänger (Liste); per Env EMAIL_TO (kommagetrennt) überschreibbar.
    "to": [
        "mail@tobiasreich.de",
        "elena.sroka@gmail.com",
    ],
    "subject_prefix": "AI-Briefing",
    # Absender = das Gmail-Konto aus GMAIL_ADDRESS.
}

# ---------------------------------------------------------------------------
# State (Newsletter-Dedupe)
# ---------------------------------------------------------------------------
STATE_FILE = "state/seen_ids.json"
SEEN_IDS_MAX = 500   # FIFO-Begrenzung der gespeicherten Message-IDs

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
OUTPUT_DIR = "output"
DASHBOARD_FILE = "output/dashboard.html"
