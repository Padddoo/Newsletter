# Spec: News-Agent (GitHub-hosted)

**Version:** 1.0
**Ziel:** Ein vollständig auf GitHub gehosteter, täglich laufender News-Agent.
Er erstellt ein priorisiertes Briefing aus zwei Themen — **MedTech** (RSS) und
**AI** (RSS **+** Gmail-Newsletter) — und veröffentlicht es als Dashboard auf
GitHub Pages, plus optionalem Telegram-Push.

Dieses Dokument ist die verbindliche Bau-Anleitung. Ein Coding-Agent (z. B.
Codex) oder ein Mensch soll es ohne weitere Rückfragen umsetzen können.

---

## 1. Kontext & Zielbild

### 1.1 Wer nutzt das
Einzelnutzer (PE/MedTech-Hintergrund). Will morgens in <5 Minuten wissen, was
in zwei Feldern passiert ist:
- **MedTech / Dermatologie M&A & Markt** — Deal-/Markt-Relevanz für einen PE-Investor.
- **AI — Modelle, Tools & Forschung** — praktischer Nutzen, um als Anwender am Ball zu bleiben.

### 1.2 Was neu ist gegenüber der lokalen Vorversion
1. **Hosting komplett auf GitHub** (GitHub Actions + GitHub Pages). Kein lokaler
   Mac, kein VPS. Zustandslos.
2. **Zweite Datenquelle für AI:** ein gesondertes Gmail-Postfach, das diverse
   AI-Newsletter empfängt. Neue (ungelesene) Newsletter werden gelesen und in
   **Story-Headlines** zerlegt.

### 1.3 Definition of Done
- [ ] Action läuft täglich automatisch (Cron) und manuell auslösbar.
- [ ] MedTech-RSS, AI-RSS und Gmail-Newsletter werden eingelesen.
- [ ] Claude erzeugt pro Story eine **Headline mit maximal 10 Wörtern** + Quell-Link.
- [ ] Dashboard auf GitHub Pages mit **drei Tabs**: MedTech, AI News, Newsletter.
- [ ] Top-Newsletter-Items erscheinen **zusätzlich** im AI-News-Tab.
- [ ] Secrets (API-Key, OAuth) liegen ausschließlich in GitHub Secrets.
- [ ] Ein Lauf kostet nur wenige Cent (Claude) und bleibt im GH-Actions-Freikontingent.
- [ ] Newsletter-Spam-Schutz in Schritt 1 = Gmails eigener Filter (Härtung ist Schritt 2, §15).

---

## 2. Architektur-Überblick

```
                    ┌──────────────────────────────────────────┐
                    │        GitHub Actions (Cron 06:00 UTC)    │
                    └──────────────────────────────────────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         ▼                             ▼                             ▼
   ┌───────────┐               ┌───────────────┐             ┌──────────────┐
   │ RSS-Quelle │               │ RSS-Quelle    │             │ Gmail API    │
   │ MedTech    │               │ AI News       │             │ (Newsletter) │
   └─────┬──────┘               └──────┬────────┘             └──────┬───────┘
         │                             │                             │
         └───────────────┬─────────────┴──────────────┬──────────────┘
                         ▼                             ▼
                 ┌────────────────┐            ┌─────────────────────┐
                 │ collector (RSS)│            │ gmail_source        │
                 └───────┬────────┘            │ (Mails → Stories)   │
                         │                     └──────────┬──────────┘
                         └──────────────┬─────────────────┘
                                        ▼
                            ┌────────────────────────┐
                            │ analyst (Claude)       │
                            │ • priorisiert          │
                            │ • Headlines ≤10 Wörter │
                            └───────────┬────────────┘
                                        ▼
                            ┌────────────────────────┐
                            │ deliver                │
                            │ • dashboard.html (Pages)│
                            │ • Telegram (optional)  │
                            └───────────┬────────────┘
                                        ▼
                            ┌────────────────────────┐
                            │ GitHub Pages publish    │
                            └────────────────────────┘
```

**Sprachwahl:** Python 3.11. Begründung: bestehende Module (collector, analyst,
deliver) sind Python; Gmail- und Anthropic-SDKs sind ausgereift.

---

## 3. Repository-Struktur

```
news-agent/
├── .github/
│   └── workflows/
│       └── briefing.yml          # GitHub Action: Cron + Build + Pages-Deploy
├── src/
│   ├── config.py                 # Themen, Feeds, Profile, Settings
│   ├── collector.py              # RSS sammeln + vorfiltern (bestehend, leicht angepasst)
│   ├── gmail_source.py           # NEU: Gmail-Newsletter → Stories
│   ├── analyst.py                # Claude: priorisieren + Headlines ≤10 Wörter
│   ├── deliver.py                # Dashboard (3 Tabs) + Telegram
│   └── run.py                    # Orchestrierung
├── scripts/
│   └── oauth_setup.py            # NEU: einmaliger lokaler OAuth-Flow → Refresh-Token
├── output/                       # wird im Action-Lauf erzeugt (nicht eingecheckt)
│   └── dashboard.html
├── requirements.txt
├── .gitignore
└── README.md
```

`.gitignore` muss mindestens enthalten: `output/`, `.env`, `token.json`,
`client_secret*.json`, `__pycache__/`.

---

## 4. Datenquellen

### 4.1 MedTech (RSS) — unverändert
Sechs verifizierte Feeds, Zeitfenster 26 h:
```
https://www.medtechdive.com/feeds/news/
https://www.massdevice.com/feed/
https://www.fiercepharma.com/rss/xml
https://www.fiercebiotech.com/rss/xml
https://www.biopharmadive.com/feeds/news/
https://medcitynews.com/feed/
```

### 4.2 AI News (RSS) — unverändert, Zeitfenster 72 h
```
https://openai.com/news/rss.xml
https://www.anthropic.com/rss.xml
https://huggingface.co/blog/feed.xml
https://www.marktechpost.com/feed/
https://research.google/blog/rss/
https://www.technologyreview.com/feed/
```
> Zeitfenster 72 h, weil Lab-Blogs nur wenige Male pro Woche posten.

### 4.3 AI Newsletter (Gmail) — NEU
- **Postfach:** ein gesondertes Gmail-Konto, das überwiegend AI-Newsletter
  empfängt. Es ist **kein reines Newsletter-Postfach** — es treffen auch
  ungefragte Spam-/Werbe-Mails ein (aber keine „echte" persönliche Post).
- **Zugriff:** Gmail API, Scope **`https://www.googleapis.com/auth/gmail.readonly`**
  (minimaler Scope, nur Lesen — keine Schreib-/Sende-Rechte).
- **Selektion — SCHRITT 1 (dieser Spec): auf Gmail-Spamfilter verlassen.**
  Query: `is:unread newer_than:2d`.
  Gmails eigener Spamfilter wird hier als ausreichend angenommen: Was in
  `[Gmail]/Spam` einsortiert ist, durchsucht die API-Query **nicht** (sie
  erfasst nur den Posteingang). Restliches, nicht erkanntes Spam-Rauschen wird
  in Schritt 1 bewusst in Kauf genommen — es kostet ein paar Tokens und kann
  vereinzelt eine unerwünschte Headline erzeugen, blockiert aber nichts.
  > **SCHRITT 2 (separat, für Claude Code — NICHT Teil dieser Umsetzung):**
  > Absender-Allowlist und/oder Label-Filter plus ein inhaltlicher Spam-/
  > Werbe-Check, damit kein nicht-erkannter Spam mehr verarbeitet wird. Siehe
  > §15 „Ausblick Schritt 2". Die Config ist bereits so vorbereitet, dass diese
  > Härtung additiv ergänzt werden kann, ohne Schritt 1 umzubauen.
- **Read-only-Konsequenz:** Mit `gmail.readonly` kann der Agent Mails **nicht**
  als gelesen markieren. Deduplizierung über bereits verarbeitete Message-IDs
  (siehe 6.3) statt über den Gelesen-Status. Das ist bewusst so gewählt, um den
  Scope minimal zu halten.

---

## 5. OAuth-Setup (einmalig, lokal) → headless in der Action

> **Status:** Dieser Schritt ist beim Nutzer bereits abgeschlossen. Die drei
> Werte `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` liegen
> vor und müssen nur noch als GitHub Secrets eingetragen werden (siehe §8 / §16).
> Der folgende Abschnitt dokumentiert den Vorgang zur Nachvollziehbarkeit und
> für den Fall, dass der Refresh-Token neu erzeugt werden muss.

Gmail-Zugriff in einer zustandslosen Action erfordert einen **Refresh-Token**,
der einmalig lokal erzeugt und dann als GitHub Secret hinterlegt wird.

### 5.1 Google-Cloud-Vorbereitung (Nutzer, einmalig)
1. Google Cloud Console → neues Projekt (z. B. `news-agent`).
2. **APIs & Services → Gmail API aktivieren.**
3. **OAuth consent screen:** User type *External*, App-Name + eigene E-Mail
   eintragen, Scope `gmail.readonly` hinzufügen. App in **„Testing"-Modus**
   lassen und die Newsletter-Gmail-Adresse als **Test-User** eintragen
   (unter 100 Usern keine Google-Verifizierung nötig).
4. **Credentials → Create credentials → OAuth client ID → Typ „Desktop app".**
   JSON herunterladen → liefert `client_id` und `client_secret`.
   > „Desktop app" ist der Schlüssel: Google öffnet beim Flow `localhost`
   > und fängt den Code selbst ab — keine gehostete Redirect-URL nötig.

### 5.2 `scripts/oauth_setup.py` (einmalig lokal ausführen)
Verhalten:
- Liest das heruntergeladene `client_secret*.json`.
- Startet `InstalledAppFlow` mit Scope `gmail.readonly` und
  **`access_type=offline`** sowie **`prompt=consent`** (erzwingt Ausgabe eines
  Refresh-Tokens).
- Öffnet den Browser, Nutzer wählt die **Newsletter-Gmail-Adresse** und bestätigt.
- Gibt aus / speichert: `refresh_token`, `client_id`, `client_secret`.
- Druckt am Ende die drei Werte klar lesbar mit der Anweisung, sie als GitHub
  Secrets zu hinterlegen (siehe 8). Schreibt KEINE Tokens ins Repo.

Pseudocode:
```python
from google_auth_oauthlib.flow import InstalledAppFlow
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("GMAIL_REFRESH_TOKEN =", creds.refresh_token)
print("GMAIL_CLIENT_ID     =", creds.client_id)
print("GMAIL_CLIENT_SECRET =", creds.client_secret)
```

### 5.3 Runtime in der Action (headless)
`gmail_source.py` baut Credentials **ohne Browser** aus den drei Secrets:
```python
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
creds = Credentials(
    token=None,
    refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
    client_id=os.environ["GMAIL_CLIENT_ID"],
    client_secret=os.environ["GMAIL_CLIENT_SECRET"],
    token_uri="https://oauth2.googleapis.com/token",
    scopes=["https://www.googleapis.com/auth/gmail.readonly"],
)
creds.refresh(Request())   # holt frischen Access-Token
```

---

## 6. Modul-Spezifikationen

### 6.1 `config.py`
Erweitert die bestehende Struktur. Neue/relevante Felder:

```python
TOPICS = {
  "medtech": { "name":..., "enabled":True, "lookback_hours":26,
               "feeds":[...], "keywords":[...], "profile":<PE-Deal-Profil> },
  "ai_news": { "name":..., "enabled":True, "lookback_hours":72,
               "feeds":[...], "keywords":[...], "profile":<Anwender-Profil> },
}

# NEU: Gmail-Newsletter-Quelle
NEWSLETTER = {
  "enabled": True,
  "name": "AI Newsletter",
  # SCHRITT 1: simpel — auf Gmail-Spamfilter verlassen.
  "gmail_query": "is:unread newer_than:2d",
  "max_messages": 25,                          # Kostendeckel
  "profile": <Newsletter-Story-Profil, s. 6.4>,

  # --- Vorbereitet für SCHRITT 2 (für Claude Code, jetzt NICHT aktiv) ---
  # "strategy": "gmail_spam",          # später: "allowlist" | "label"
  # "allowed_senders": [],             # später mit echten Abo-Absendern füllen
  # "gmail_label": "Newsletter",       # später bei Label-Strategie
  # "content_spam_check": False,       # später: True für inhaltlichen Claude-Check
}

HEADLINE_MAX_WORDS = 10        # harte Obergrenze für Newsletter-Headlines
NEWSLETTER_TOP_N_IN_AI = 5     # so viele Top-Items zusätzlich im AI-News-Tab
ANTHROPIC_MODEL = "claude-opus-4-6"
```

### 6.2 `collector.py` — unverändert
Bestehende Logik: RSS sammeln, dedupe (Titel-Hash), Zeitfenster pro Thema,
Keyword-Sortierung (filtert nicht weg). Liefert `{topic_key: [article,...]}`.

### 6.3 `gmail_source.py` — NEU
**Aufgabe:** ungelesene Newsletter holen, Klartext extrahieren, an Claude zur
Story-Zerlegung übergeben.

Funktionen:
- `fetch_newsletters() -> list[dict]`
  1. Credentials bauen (5.3), Gmail-Client `build("gmail","v1",credentials=creds)`.
  2. `users().messages().list(userId="me", q=NEWSLETTER["gmail_query"],
     maxResults=NEWSLETTER["max_messages"])`.
     > Schritt 1: `gmail_query` ist die simple Query `is:unread newer_than:2d`.
     > Der Spam-Schutz verlässt sich auf Gmail (Spam-Ordner wird nicht
     > durchsucht). Die Härtung folgt in Schritt 2 (§15).
  3. Pro Message: `users().messages().get(..., format="full")`.
  4. Header `From`, `Subject`, `Date` auslesen.
  5. Body extrahieren: bevorzugt `text/plain`-Part; sonst `text/html` →
     Tags strippen (z. B. via `html.parser`/bleach-frei, simpel regex + unescape).
     **Links erhalten:** beim HTML-Strippen `href`-Ziele als Klartext
     mitführen, damit pro Story ein echter Quell-Link verfügbar ist.
  6. Body auf sinnvolle Länge kürzen (z. B. max. 6.000 Zeichen je Mail), um
     Token-Kosten zu deckeln.
  7. Rückgabe je Mail:
     ```python
     { "message_id":..., "sender":..., "subject":..., "date":...,
       "body_text":..., "links":[(anchor_text, url),...] }
     ```
- **Dedupe über verarbeitete IDs:** Da `gmail.readonly` kein Markieren erlaubt,
  führt der Agent eine kleine Statusdatei `state/seen_ids.json`, die nach dem
  Lauf ins Repo zurückgeschrieben wird (siehe 7.4). Bereits gesehene
  `message_id`s werden übersprungen. Fällt `state` aus, ist Dopplung an einem
  Tag der schlimmste Fall — unkritisch.

### 6.4 `analyst.py` — erweitert
Zwei Bewertungspfade:

**(a) RSS-Artikel (bestehend):** pro Thema mit thema-spezifischem `profile`,
liefert `priority`, `reason`, `summary_de`.

**(b) Newsletter-Stories (NEU):** Pro Newsletter-Mail bekommt Claude
`body_text` + `links` und die Anweisung:
- Zerlege die Mail in ihre **einzelnen Stories/Items**.
- Pro Story:
  - `headline`: **deutsche Headline, MAXIMAL 10 Wörter** (harte Grenze; bei
    Überschreitung kürzen, nicht abschneiden).
  - `url`: der zur Story passende Quell-Link aus `links` (kein Tracking-Wrapper,
    wenn ein direkter Link erkennbar ist; sonst der beste verfügbare).
  - `source_newsletter`: Absender/Name des Newsletters.
  - `priority`: hoch | mittel | niedrig (für die Top-N-Auswahl im AI-Tab).
- Antwortformat: striktes JSON
  `{"stories":[{"headline":...,"url":...,"source_newsletter":...,"priority":...}]}`.
- Validierung im Code: `headline` auf ≤ `HEADLINE_MAX_WORDS` prüfen; falls länger,
  hart auf 10 Wörter kürzen. Stories ohne `url` werden verworfen.

System-Prompt-Leitlinie (Newsletter-Profil):
> „Extrahiere nur AI-relevante Stories (Modelle, Tools, Releases, Forschung mit
> Praxisbezug). Werbung, Sponsoren-Blöcke, Job-Listings, reine Meinungsstücke
> ignorieren. Jede Headline ist nüchtern und konkret, kein Clickbait."

### 6.5 `deliver.py` — erweitert auf 3 Tabs
- Tabs: **MedTech**, **AI News**, **Newsletter**.
- **MedTech / AI News:** bestehende Karten (priority-Farbe, Quelle, `summary_de`,
  „Warum relevant", Link).
- **Newsletter-Tab:** kompaktes Listenlayout (nicht Karten), je Zeile:
  `● headline (≤10 Wörter)  — Newsletter-Name ↗`  mit Link auf `url`.
  Gruppierung nach Newsletter-Absender optional.
- **Cross-Posting:** die `NEWSLETTER_TOP_N_IN_AI` höchstpriorisierten
  Newsletter-Stories werden **zusätzlich** oben im AI-News-Tab als schlanke
  Zeile eingeblendet, klar als „aus Newsletter" markiert (kleines Badge).
- **Telegram (optional, unverändert + Newsletter-Block):** Top-Prioritäten je
  Thema + die Top-Newsletter-Headlines als Liste mit Links.

### 6.6 `run.py` — Orchestrierung
Ablauf:
1. `.env`/Secrets laden (lokal `.env`, in Action: echte Env-Vars).
2. `collected = collector.collect_all()`  (RSS).
3. `newsletters = gmail_source.fetch_newsletters()` falls `NEWSLETTER.enabled`.
4. `analyzed = analyst.analyze_all(collected)`  (RSS).
5. `stories = analyst.analyze_newsletters(newsletters)`  (Headlines ≤10 Wörter).
6. `deliver.build_dashboard(analyzed, stories)` → `output/dashboard.html`.
7. `deliver.send_telegram(analyzed, stories)` falls Telegram-Secrets gesetzt.
8. `state/seen_ids.json` aktualisieren.
9. **Kein** `open()` (headless). Exit 0 bei Erfolg.

---

## 7. GitHub Actions Workflow (`.github/workflows/briefing.yml`)

### 7.1 Trigger
```yaml
on:
  schedule:
    - cron: "0 6 * * *"     # täglich 06:00 UTC (= 08:00 Berlin Winter / 07:00? prüfen)
  workflow_dispatch: {}      # manueller Start per Button
```
> Hinweis: GitHub-Cron läuft in **UTC** und kann sich um einige Minuten
> verspäten. Für „09:00 Berlin" je nach Sommer-/Winterzeit `0 7` bzw. `0 8`
> wählen, oder bewusst fix in UTC denken.

### 7.2 Permissions & Concurrency
```yaml
permissions:
  contents: write        # für state/seen_ids.json commit
  pages: write           # für Pages-Deploy
  id-token: write
concurrency:
  group: briefing
  cancel-in-progress: false
```

### 7.3 Job-Schritte (Skizze)
```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - name: Run agent
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GMAIL_CLIENT_ID: ${{ secrets.GMAIL_CLIENT_ID }}
          GMAIL_CLIENT_SECRET: ${{ secrets.GMAIL_CLIENT_SECRET }}
          GMAIL_REFRESH_TOKEN: ${{ secrets.GMAIL_REFRESH_TOKEN }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python src/run.py
      - name: Commit state
        run: |
          git config user.name "news-agent"
          git config user.email "bot@users.noreply.github.com"
          git add state/seen_ids.json || true
          git commit -m "update seen ids" || echo "no changes"
          git push || true
      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v3
        with: { path: output }
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

### 7.4 State-Persistenz
`state/seen_ids.json` wird im Repo gehalten und im `build`-Job nach dem Lauf
committet. Damit überlebt die Newsletter-Dedupe-Liste die zustandslose Action.
Liste auf z. B. letzte 500 IDs begrenzen (FIFO), damit sie nicht unbegrenzt wächst.

---

## 8. Secrets (GitHub → Settings → Secrets and variables → Actions)

| Secret | Quelle | Pflicht |
|--------|--------|---------|
| `ANTHROPIC_API_KEY` | console.anthropic.com | ja |
| `GMAIL_CLIENT_ID` | OAuth-Client JSON | ja |
| `GMAIL_CLIENT_SECRET` | OAuth-Client JSON | ja |
| `GMAIL_REFRESH_TOKEN` | `scripts/oauth_setup.py` | ja |
| `TELEGRAM_BOT_TOKEN` | @BotFather | optional |
| `TELEGRAM_CHAT_ID` | getUpdates | optional |

Keine dieser Werte darf je im Repo, in Logs oder im Dashboard erscheinen.

---

## 9. GitHub Pages

- **Settings → Pages → Source: „GitHub Actions".**
- Dashboard erscheint unter `https://<user>.github.io/news-agent/`.
- **Sichtbarkeit:** Bei öffentlichem Repo ist die Pages-Seite **öffentlich**.
  Das Dashboard enthält keine Geheimnisse, aber sehr wohl deine kuratierten
  Interessen. **Empfehlung:** Repo **privat** halten; private Repos können Pages
  nur in kostenpflichtigen Plänen *zugriffsbeschränkt* veröffentlichen. Falls
  Pro/Team nicht vorhanden: Pages-URL ist zwar nicht verlinkt, aber theoretisch
  erreichbar. Alternative: Dashboard nur via Telegram + als Action-Artifact
  (nicht-öffentlich) bereitstellen. **Entscheidung beim Nutzer einholen.**

---

## 10. Kosten & Limits

- **GitHub Actions:** ~1–2 Min/Lauf × 30 = <60 Min/Monat. Frei (2.000 Min/Monat privat).
- **GitHub Pages:** kostenlos.
- **Gmail API:** kostenlos, großzügige Quota.
- **Claude:** RSS-Bewertung + Newsletter-Zerlegung; bei `max_messages=25` und
  gedeckelten Body-Längen wenige Cent/Tag. Über `max_messages` und
  `MAX_ARTICLES_TO_RATE` steuerbar.

---

## 11. Fehlerverhalten & Robustheit

- Einzelne tote RSS-Feeds: überspringen, Lauf fortsetzen.
- Gmail-Refresh schlägt fehl (`invalid_grant`): klare Fehlermeldung, Hinweis
  „Refresh-Token neu erzeugen" (Token kann ablaufen, wenn App im Testing-Modus
  >6 Monate ungenutzt oder Passwort geändert). Lauf darf an Gmail scheitern,
  ohne MedTech/AI-RSS zu blockieren — Newsletter-Tab dann leer mit Hinweis.
- Claude-Antwort kein valides JSON: einmal Retry, sonst Thema/Newsletter leer.
- Headline >10 Wörter: hart kürzen.
- Action darf nie mit teil-fertigem Dashboard deployen: nur deployen, wenn
  `output/dashboard.html` erzeugt wurde.

---

## 12. Akzeptanzkriterien (Tests)

1. **Manueller Lauf** (`workflow_dispatch`) erzeugt Pages-Dashboard mit 3 Tabs.
2. **Newsletter-Headlines** sind nachweislich ≤10 Wörter (Unit-Test über die
   Längen-Validierung).
3. **Cross-Posting:** genau `NEWSLETTER_TOP_N_IN_AI` Items erscheinen im AI-Tab.
4. **Dedupe:** zwei Läufe hintereinander erzeugen beim zweiten keine doppelten
   Newsletter-Stories (seen_ids greift).
5. **Secrets-Hygiene:** kein Secret taucht in Action-Logs auf.
6. **Resilienz:** ein absichtlich toter Feed bricht den Lauf nicht ab.

---

## 13. Umsetzungsreihenfolge (für den Coding-Agent)

1. Repo-Grundgerüst + `.gitignore` + `requirements.txt`
   (`feedparser`, `anthropic`, `google-api-python-client`,
   `google-auth`, `google-auth-oauthlib`).
2. `config.py` inkl. `NEWSLETTER`-Block.
3. `scripts/oauth_setup.py` + lokal Refresh-Token erzeugen (Nutzer-Schritt).
4. `gmail_source.py` (fetch + Body/Link-Extraktion + seen_ids).
5. `analyst.py` um `analyze_newsletters()` + Headline-Validierung erweitern.
6. `deliver.py` auf 3 Tabs + Cross-Posting erweitern.
7. `run.py` Orchestrierung.
8. `briefing.yml` (Cron + Build + Pages + State-Commit).
9. Secrets setzen, Pages auf „GitHub Actions" stellen.
10. `workflow_dispatch` testen, dann Cron beobachten.

> Die konkreten Klick-für-Klick-Schritte auf der GitHub-Seite (Repo anlegen,
> Code hochladen, Secrets eintragen, Pages aktivieren, Testlauf) stehen in §16.

---

## 14. Offene Entscheidungen (vor Start zu klären)

- **Repo öffentlich oder privat?** (siehe §9 — Pages-Sichtbarkeit). Empfehlung: privat.
- **Cron-Uhrzeit** final in UTC festlegen (Sommer-/Winterzeit bedenken).

---

## 15. Ausblick: Schritt 2 (separates Projekt für Claude Code)

**Nicht Teil dieser Umsetzung.** Dieser Spec liefert die funktionierende
Kernpipeline; Schritt 1 verlässt sich beim Newsletter-Spam auf Gmails eigenen
Filter. Schritt 2 härtet die Newsletter-Quelle gegen nicht-erkannten Spam:

1. **Absender-Allowlist** (`strategy="allowlist"`): Gmail-Query wird um
   `(from:a OR from:b OR ...)` aus `allowed_senders` ergänzt — nur abonnierte
   Newsletter werden gelesen.
2. **Label-Strategie** (`strategy="label"`): Nutzer richtet einen Gmail-Filter
   ein, der Abos automatisch mit Label „Newsletter" versieht; Query nutzt
   `label:Newsletter`. Pflege in Gmail statt im Code.
3. **Inhaltlicher Spam-/Werbe-Check** (`content_spam_check=True`): Eine
   leichtgewichtige Claude-Vorklassifikation verwirft Werbung, Phishing und
   Sponsoren-Blöcke, bevor die teurere Story-Zerlegung läuft.
4. **Akzeptanzkriterium Schritt 2:** Bekannter Spam-Absender im Testpostfach
   erzeugt nachweislich **keine** Story im Dashboard.

Die Config in §6.1 enthält bereits die auskommentierten Felder dafür, sodass
Schritt 2 additiv andocken kann, ohne Schritt-1-Code umzubauen.

---

## 16. GitHub-Einrichtung: Schritt-für-Schritt (für den Nutzer)

Diese Anleitung bringt dich vom leeren GitHub-Account bis zum täglich laufenden
Agenten. Sie setzt **kein** GitHub-Vorwissen voraus. Reihenfolge einhalten.

### 16.1 Voraussetzungen
- Ein GitHub-Account (kostenlos, github.com → „Sign up").
- Die vier Geheimwerte griffbereit:
  `ANTHROPIC_API_KEY`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`,
  `GMAIL_REFRESH_TOKEN` (optional zusätzlich `TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_CHAT_ID`).

### 16.2 Repository anlegen
1. Auf github.com oben rechts **„+“ → „New repository“**.
2. **Repository name:** z. B. `news-agent`.
3. **Sichtbarkeit:** **Private** wählen (Empfehlung, siehe §9).
4. Haken bei **„Add a README file“** setzen (damit das Repo nicht leer ist).
5. **„Create repository“** klicken.

### 16.3 Code ins Repo bringen
Es gibt zwei Wege — wähle einen.

**Weg A — Per Weboberfläche (kein Terminal, am einfachsten):**
1. Im Repo auf **„Add file“ → „Upload files“**.
2. Die vom Coding-Agent erzeugten Dateien/Ordner hineinziehen
   (`.github/`, `src/`, `scripts/`, `requirements.txt`, `.gitignore`, `README.md`).
   > Hinweis: Die Weboberfläche kann Ordner per Drag-and-Drop. Alternativ Dateien
   > einzeln in der richtigen Ordnerstruktur anlegen via „Add file → Create new file“
   > und den Pfad mit `/` eintippen (z. B. `src/run.py`).
3. Unten **„Commit changes“** klicken.

**Weg B — Per Git im Terminal (wenn Claude Code lokal baut):**
```bash
cd /pfad/zum/erzeugten/projekt
git init
git add .
git commit -m "initial commit: news agent"
git branch -M main
git remote add origin https://github.com/<DEIN-USERNAME>/news-agent.git
git push -u origin main
```
> Falls nach Login gefragt: GitHub verlangt statt Passwort einen „Personal
> Access Token“. Unter github.com → Settings → Developer settings → Personal
> access tokens → „Generate new token (classic)“, Scope `repo` genügt.

### 16.4 Secrets hinterlegen (NIE in den Code!)
1. Im Repo: **„Settings“** (oben im Repo-Menü).
2. Links: **„Secrets and variables“ → „Actions“**.
3. **„New repository secret“**, dann für **jeden** Wert einmal:
   - Name exakt wie unten, Value = der Geheimwert, „Add secret“.

| Name (genau so) | Wert |
|-----------------|------|
| `ANTHROPIC_API_KEY` | dein Anthropic-Key |
| `GMAIL_CLIENT_ID` | aus OAuth-Setup |
| `GMAIL_CLIENT_SECRET` | aus OAuth-Setup |
| `GMAIL_REFRESH_TOKEN` | aus OAuth-Setup |
| `TELEGRAM_BOT_TOKEN` | optional |
| `TELEGRAM_CHAT_ID` | optional |

> Secrets sind verschlüsselt, in Logs automatisch als `***` maskiert und nach
> dem Speichern nicht mehr auslesbar (nur überschreibbar). Genau so gewollt.

### 16.5 GitHub Pages aktivieren (falls Dashboard öffentlich, siehe §9)
1. Im Repo: **„Settings“ → „Pages“**.
2. Unter **„Build and deployment“ → „Source“**: **„GitHub Actions“** wählen.
3. Nach dem ersten erfolgreichen Lauf erscheint die URL
   `https://<username>.github.io/news-agent/`.
> Bei privatem Repo ohne Bezahlplan ist die Seite zwar nicht verlinkt, aber
> technisch erreichbar. Wer das nicht will: Pages weglassen und auf Telegram +
> Action-Artifact setzen (§9, Option A).

### 16.6 Ersten Lauf manuell auslösen (Test)
1. Im Repo: Reiter **„Actions“**.
2. Falls GitHub fragt, ob Workflows aktiviert werden sollen: bestätigen.
3. Links den Workflow **„briefing“** wählen.
4. Rechts **„Run workflow“ → „Run workflow“** (nutzt den `workflow_dispatch`-Trigger).
5. Der Lauf erscheint in der Liste; Klick darauf zeigt die Live-Logs.
   - **Grün** = erfolgreich. Dashboard ist auf Pages (16.5) bzw. als Artifact da.
   - **Rot** = Fehler. Logs öffnen, die fehlgeschlagene Stufe aufklappen, Meldung lesen.

### 16.7 Täglichen Automatik-Lauf prüfen
- Der Cron in `briefing.yml` (§7.1) startet den Lauf automatisch (Standard 06:00 UTC).
- GitHub-Cron kann sich um einige Minuten verspäten — normal.
- Nach dem ersten automatischen Lauf unter „Actions“ kontrollieren, dass er grün ist.

### 16.8 Häufige Stolpersteine
- **Action startet nicht automatisch nach Upload:** Bei manchen Repos müssen
  Actions unter „Actions“ einmalig aktiviert werden. Danach `workflow_dispatch` testen.
- **`invalid_grant` bei Gmail:** Refresh-Token abgelaufen/ungültig → `oauth_setup.py`
  erneut lokal laufen lassen, neuen `GMAIL_REFRESH_TOKEN` als Secret speichern.
- **Pages zeigt 404:** Erst nach dem ersten **erfolgreichen** Lauf vorhanden;
  außerdem „Source = GitHub Actions“ prüfen (16.5).
- **Secret-Name vertippt:** Muss exakt mit den Namen in `briefing.yml` übereinstimmen
  (Groß-/Kleinschreibung zählt).
- **Cron-Uhrzeit:** ist UTC. Für „09:00 Berlin“ je nach Sommer-/Winterzeit `0 7`
  bzw. `0 8` in der Cron-Zeile setzen.

### 16.9 Definition of Done (GitHub-Seite)
- [ ] Repo privat angelegt, Code hochgeladen.
- [ ] Alle Pflicht-Secrets gesetzt.
- [ ] `workflow_dispatch`-Testlauf ist grün.
- [ ] Dashboard erreichbar (Pages-URL oder Artifact), 3 Tabs sichtbar.
- [ ] Cron-Lauf am Folgetag ebenfalls grün.
