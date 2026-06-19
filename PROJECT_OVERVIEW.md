# Projekt-Übersicht: News-Agent (GitHub-hosted)

> Arbeitsdokument zur schrittweisen Umsetzung von [`News_Spec.md`](./News_Spec.md) (v1.0).
> Wir haken hier ab, was erledigt ist, und arbeiten die Phasen der Reihe nach durch.
>
> **Stand:** Nur die Spec liegt vor — es existiert noch kein Code.
>
> **Scope v1 (Festlegung):** Erster Use Case ist **ausschließlich AI** — aus
> **Gmail-Newslettern** *und* **AI-RSS-Quellen**. **MedTech ist geparkt** (siehe §10).

---

## 1. Was wir bauen (in einem Satz)

Ein vollständig auf GitHub gehosteter, **täglich per Cron** laufender News-Agent.

**v1 (dieser Use Case):** Thema **AI** aus zwei Quellen — **AI-Newsletter via Gmail**
und **AI-RSS** — wird zu einem priorisierten Briefing verdichtet und als
**Dashboard mit 2 Tabs** (AI News, Newsletter) auf GitHub Pages und optional per
Telegram veröffentlicht. **MedTech ist bewusst geparkt** und wird später als
zweites Thema additiv ergänzt (§10).

### Kernprinzipien
- **Zustandslos & serverlos:** läuft komplett in GitHub Actions, kein Mac/VPS.
- **Minimaler Gmail-Scope:** nur `gmail.readonly` (Dedupe über `seen_ids.json`).
- **Kostenarm:** wenige Cent Claude/Tag, im GH-Actions-Freikontingent.
- **Schritt 1 zuerst:** Newsletter-Spam-Schutz = Gmails eigener Filter. Härtung ist Schritt 2 (§8).
- **AI-Quelle ist „warm":** durch deine Abos bereits vorkuratiert → Aufgabe = priorisieren + auf Headlines eindampfen.

---

## 2. Tech-Stack & Architektur

| Bereich | Wahl |
|---------|------|
| Sprache | Python 3.11 |
| LLM | Claude (Anthropic SDK) — Modell siehe Offene Punkte |
| Quellen | `feedparser` (AI-RSS), Gmail API (`google-api-python-client`, `google-auth`, `google-auth-oauthlib`) |
| Hosting | GitHub Actions (Cron 06:00 UTC) + GitHub Pages |
| Zustellung | `dashboard.html` (Pages) + Telegram (optional) |

**Pipeline (v1):** `collector` (AI-RSS) + `gmail_source` (Mails→Stories) → `analyst`
(Claude: priorisiert + Headlines ≤10 Wörter) → `deliver` (Dashboard 2 Tabs + Telegram) → Pages-Deploy.

---

## 3. Ziel-Repository-Struktur

```
news-agent/
├── .github/workflows/briefing.yml   # Cron + Build + Pages-Deploy
├── src/
│   ├── config.py                    # Themen, Feeds, Profile, NEWSLETTER-Block
│   ├── collector.py                 # RSS sammeln + vorfiltern (v1: nur ai_news)
│   ├── gmail_source.py              # Gmail-Newsletter → Stories
│   ├── analyst.py                   # Claude: priorisieren + Headlines ≤10 Wörter
│   ├── deliver.py                   # Dashboard (v1: 2 Tabs) + Telegram
│   └── run.py                       # Orchestrierung
├── scripts/oauth_setup.py           # einmaliger lokaler OAuth-Flow
├── state/seen_ids.json              # Dedupe-Status (wird von der Action gepflegt)
├── output/dashboard.html            # Action-Artefakt (nicht eingecheckt)
├── requirements.txt
├── .gitignore                       # output/, .env, token.json, client_secret*.json, __pycache__/
└── README.md
```

---

## 4. Phasen & Schritte (unsere Arbeitsliste)

Reihenfolge angelehnt an Spec §13. Jede Phase ist eigenständig testbar.

### Phase 0 — Grundgerüst ✅
- [x] `requirements.txt` (`feedparser`, `anthropic`, `google-api-python-client`, `google-auth`, `google-auth-oauthlib`, `requests`)
- [x] `.gitignore` (`output/`, `.env`, `token.json`, `client_secret*.json`, `__pycache__/`)
- [x] Ordnerstruktur `src/`, `scripts/`, `state/` angelegt
- [x] `README.md` (Kurzbeschreibung + Verweis auf Spec/Overview)

### Phase 1 — Konfiguration ✅
- [x] `config.py`: `TOPICS` mit **`ai_news` (enabled, 72 h)**; **`medtech` als `enabled: False`** vorbereitet (geparkt, später aktivierbar)
- [x] `config.py`: `NEWSLETTER`-Block (Schritt-1-Query `is:unread newer_than:2d`, `max_messages=25`)
- [x] Konstanten: `HEADLINE_MAX_WORDS=10`, `NEWSLETTER_TOP_N_IN_AI=5`, `ANTHROPIC_MODEL="claude-sonnet-4-6"`
- [x] Auskommentierte Schritt-2-Felder vorbereitet (allowlist/label/content_spam_check)

### Phase 2 — RSS-Collector (AI) ✅
- [x] `collector.py`: AI-Feeds einlesen, Dedupe (Titel-Hash), Zeitfenster 72 h
- [x] Keyword-Sortierung (filtert nicht weg), Rückgabe `{ "ai_news": [article,...] }`
- [x] Robustheit: tote Feeds überspringen (Timeout + Fehler-Skip), Lauf fortsetzen
- [x] Generisch über `TOPICS` iterieren (deaktiviertes `medtech` wird automatisch übersprungen)
- [x] Offline-Logiktest grün (Zeitfenster/Dedupe/Sortierung/HTML-Strip/enabled-Filter)

### Phase 3 — Gmail-Quelle ✅
- [x] `scripts/oauth_setup.py`: lokaler `InstalledAppFlow`, gibt 3 Secrets aus (schreibt nichts ins Repo)
- [x] `gmail_source.py`: headless Credentials aus 3 Secrets (Refresh-Flow, klare Fehlermeldung bei `invalid_grant`)
- [x] `fetch_newsletters()`: list → get(full) → From/Subject/Date + Body (text/plain bevorzugt)
- [x] HTML-Strip mit **Link-Erhalt** (`href`→Klartext), Body-Kürzung (~6.000 Zeichen)
- [x] Dedupe über `state/seen_ids.json` (FIFO, max. ~500 IDs)
- [x] Offline-Logiktest grün (HTML→Text+Links, base64, MIME-Walk, seen_ids-FIFO, fetch+Dedupe)

### Phase 4 — Analyst (Claude) ✅
- [x] `analyst.py` (a): AI-RSS-Bewertung → `priority`, `reason`, `summary_de` (+ Priority-Sortierung)
- [x] `analyst.py` (b): `analyze_newsletters()` → Stories als striktes JSON
- [x] Pro Story: `headline` (DE, ≤10 Wörter), `url`, `source_newsletter`, `priority`
- [x] Validierung: Headline ≤10 Wörter (hart kürzen); Stories ohne `url` verwerfen
- [x] JSON-Retry bei ungültiger Antwort (1×); RSS bleibt erhalten (neutral), Newsletter-Mail leer
- [x] Offline-Logiktest grün (Parsing/Fences, Headline-Kürzung, Validierung, Fallbacks)

### Phase 5 — Deliver (Dashboard + Telegram + E-Mail) ✅
- [x] `deliver.py`: **2 Tabs (AI News, Newsletter)** — Tab-Logik iteriert über Themen, MedTech dockt später additiv an
- [x] AI News: Karten (priority-Farbe, Quelle, `summary_de`, „Warum relevant", Link)
- [x] Newsletter-Tab: kompakte Liste, nach Absender gruppiert (`● headline — Name ↗`)
- [x] Cross-Posting: Top-`NEWSLETTER_TOP_N_IN_AI` zusätzlich im AI-Tab (Badge „aus Newsletter")
- [x] Telegram (optional): Top-AI-Prioritäten + Top-Newsletter-Headlines
- [x] **E-Mail-Versand** via Gmail (`gmail.send`): HTML-Briefing an die eigene Adresse
- [x] Offline-Logiktest grün (Dashboard-HTML, Cross-Post-Anzahl, Escaping, Telegram, E-Mail-MIME)

### Phase 6 — Orchestrierung ✅
- [x] `run.py`: collect (AI-RSS) → fetch (Gmail) → analyze (RSS) → analyze (Newsletter) → build → telegram → e-mail → seen_ids
- [x] Headless (kein `open()`), Exit 0 bei Erfolg / Exit 1 ohne Dashboard
- [x] Gmail-Fehler dürfen AI-RSS nicht blockieren (Newsletter-Tab dann leer + Hinweis)
- [x] Nur deployen, wenn `output/dashboard.html` erzeugt wurde
- [x] Minimaler `.env`-Loader (Action-Secrets haben Vorrang); seen_ids-Update am Ende
- [x] End-to-End-Integrationstest grün (inkl. Dedupe-Lauf + Gmail-Ausfall)

### Phase 7 — GitHub Action
- [ ] `briefing.yml`: Trigger `schedule` (Cron) + `workflow_dispatch`
- [ ] `permissions`: contents/pages/id-token; `concurrency: briefing`
- [ ] Build-Job: checkout → setup-python 3.11 → pip install → `python src/run.py`
- [ ] Secrets als `env` injizieren (siehe §5)
- [ ] State-Commit (`state/seen_ids.json`) + `upload-pages-artifact`
- [ ] Deploy-Job: `deploy-pages@v4`

### Phase 8 — Tests / Akzeptanz (Spec §12)
- [ ] Unit-Test: Headline-Längen-Validierung (≤10 Wörter)
- [ ] Cross-Posting: genau `NEWSLETTER_TOP_N_IN_AI` Items im AI-Tab
- [ ] Dedupe: zweiter Lauf erzeugt keine doppelten Stories
- [ ] Resilienz: toter Feed bricht Lauf nicht ab
- [ ] Secrets-Hygiene: kein Secret in Logs/Dashboard

### Phase 9 — GitHub-Einrichtung (Nutzer-Schritte, Spec §16)
- [ ] Repo privat anlegen, Code hochladen
- [ ] Alle Pflicht-Secrets setzen (§5)
- [ ] Pages-Source auf „GitHub Actions" (falls gewünscht)
- [ ] `workflow_dispatch`-Testlauf grün
- [ ] Cron-Lauf am Folgetag grün

---

## 5. Benötigte Secrets (GitHub Actions)

| Secret | Quelle | Pflicht |
|--------|--------|---------|
| `ANTHROPIC_API_KEY` | console.anthropic.com | ja |
| `GMAIL_CLIENT_ID` | OAuth-Client JSON | ja |
| `GMAIL_CLIENT_SECRET` | OAuth-Client JSON | ja |
| `GMAIL_REFRESH_TOKEN` | `scripts/oauth_setup.py` | ja |
| `TELEGRAM_BOT_TOKEN` | @BotFather | optional |
| `TELEGRAM_CHAT_ID` | getUpdates | optional |
| `EMAIL_TO` | Empfänger-Adresse (Default in `config.py`) | optional |

> **Achtung Scope-Erweiterung:** Für den E-Mail-Versand wurde der Gmail-Scope um
> `gmail.send` erweitert. Der vorhandene (read-only) Refresh-Token kann **nicht**
> senden — `scripts/oauth_setup.py` einmal neu ausführen und `GMAIL_REFRESH_TOKEN`
> ersetzen (Phase 9).

---

## 6. Offene Entscheidungen (vor bzw. während Umsetzung klären)

1. **Repo öffentlich oder privat?** (Pages-Sichtbarkeit, Spec §9). Empfehlung: **privat**.
2. **Cron-Uhrzeit** final in UTC (Sommer-/Winterzeit). Spec-Default: `0 6 * * *`.
3. **Claude-Modell:** Spec nennt `claude-opus-4-6`. Aktuell verfügbar sind neuere
   Modelle — vor Implementierung auf ein aktuelles Modell festlegen.
4. **Telegram** aktiv ja/nein (optionaler Block).
5. **AI-Profil** (Anwender-Sicht) + Keyword-Sortierung für `ai_news` finalisieren.
6. **AI-RSS-Feedliste** bestätigen (Spec §4.2: openai, anthropic, huggingface,
   marktechpost, google research, technologyreview) — passt das, oder ergänzen?

---

## 7. Definition of Done (v1, abgeleitet aus Spec §1.3)

- [ ] Action läuft täglich automatisch (Cron) und ist manuell auslösbar
- [ ] AI-RSS und Gmail-Newsletter werden eingelesen (MedTech in v1 geparkt)
- [ ] Claude erzeugt pro Story Headline (≤10 Wörter) + Quell-Link
- [ ] Dashboard auf Pages mit 2 Tabs (AI News, Newsletter)
- [ ] Top-Newsletter-Items erscheinen zusätzlich im AI-News-Tab
- [ ] Briefing wird zusätzlich per E-Mail (Gmail `gmail.send`) verschickt
- [ ] Secrets ausschließlich in GitHub Secrets
- [ ] Ein Lauf kostet nur wenige Cent und bleibt im Freikontingent
- [ ] Newsletter-Spam-Schutz = Gmail-Filter (Härtung = Schritt 2)

---

## 8. Bewusst NICHT in diesem Projekt: Newsletter-Härtung (Schritt 2, Spec §15)

Absender-Allowlist, Label-Strategie und inhaltlicher Spam-/Werbe-Check via Claude.
Die Config wird so vorbereitet, dass diese Härtung später **additiv** andocken kann.

---

## 9. Empfohlener nächster Schritt

**Phase 0 + 1** zusammen umsetzen (Grundgerüst + `config.py` mit **nur `ai_news`
aktiv** + `NEWSLETTER`), da alles Weitere darauf aufbaut. Davor kurz die **Offenen
Entscheidungen** (§6, v. a. Claude-Modell + AI-Feedliste) klären, damit `config.py`
direkt korrekt ist.

---

## 10. Geparkt: MedTech (späteres zweites Thema)

MedTech ist **nicht Teil von v1**, der Code bleibt aber dafür offen: `medtech` als
Topic mit `enabled: False`, der Collector iteriert generisch über `TOPICS`, und das
2-Tab-Dashboard ist so gebaut, dass ein dritter Tab additiv andockt.

**Grund fürs Parken:** Die Ausgangslage ist in einem ersten Schritt schwach — die
generischen Branchen-Feeds liefern „MedTech allgemein", nicht die gewünschte Niche
(Dermatologie-/Ästhetik-M&A mit PE-Deal-Relevanz). Im Gegensatz dazu ist die
AI-Quelle durch deine Abos bereits vorkuratiert.

**Roadmap zur Reaktivierung (nach Nutzen sortiert):**
1. **Google-News-Such-Feeds** statt/zusätzlich zu generischen Feeds — bringt
   gezielte Queries auf die RSS-Seite, ohne Architekturänderung
   (`https://news.google.com/rss/search?q=...`).
2. **Claude-Profil schärfen** (hart auf Deal-/Markt-Relevanz filtern).
3. **Niche-Quellen** nachrüsten (Deal-Wires, dermatologie-spezifische Publikationen).
4. **Feedback-Schleife**: nützliche Items markieren → Queries/Keywords/Profil nachziehen.

**Reaktivierung** = `medtech` auf `enabled: True` + dritter Tab im Dashboard.
