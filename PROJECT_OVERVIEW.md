# Projekt-Übersicht: News-Agent (GitHub-hosted)

> Arbeitsdokument zur schrittweisen Umsetzung von [`News_Spec.md`](./News_Spec.md) (v1.0).
> Wir haken hier ab, was erledigt ist, und arbeiten die Phasen der Reihe nach durch.
>
> **Stand:** Nur die Spec liegt vor — es existiert noch kein Code.

---

## 1. Was wir bauen (in einem Satz)

Ein vollständig auf GitHub gehosteter, **täglich per Cron** laufender News-Agent,
der aus drei Quellen (MedTech-RSS, AI-RSS, AI-Newsletter via Gmail) ein
priorisiertes Briefing erzeugt, das als **Dashboard mit 3 Tabs** auf GitHub Pages
und optional per Telegram veröffentlicht wird.

### Kernprinzipien
- **Zustandslos & serverlos:** läuft komplett in GitHub Actions, kein Mac/VPS.
- **Minimaler Gmail-Scope:** nur `gmail.readonly` (Dedupe über `seen_ids.json`).
- **Kostenarm:** wenige Cent Claude/Tag, im GH-Actions-Freikontingent.
- **Schritt 1 zuerst:** Spam-Schutz = Gmails eigener Filter. Härtung ist Schritt 2 (§15).

---

## 2. Tech-Stack & Architektur

| Bereich | Wahl |
|---------|------|
| Sprache | Python 3.11 |
| LLM | Claude (Anthropic SDK) — Modell siehe Offene Punkte |
| Quellen | `feedparser` (RSS), Gmail API (`google-api-python-client`, `google-auth`, `google-auth-oauthlib`) |
| Hosting | GitHub Actions (Cron 06:00 UTC) + GitHub Pages |
| Zustellung | `dashboard.html` (Pages) + Telegram (optional) |

**Pipeline:** `collector` (RSS) + `gmail_source` (Mails→Stories) → `analyst` (Claude:
priorisiert + Headlines ≤10 Wörter) → `deliver` (Dashboard + Telegram) → Pages-Deploy.

---

## 3. Ziel-Repository-Struktur

```
news-agent/
├── .github/workflows/briefing.yml   # Cron + Build + Pages-Deploy
├── src/
│   ├── config.py                    # Themen, Feeds, Profile, NEWSLETTER-Block
│   ├── collector.py                 # RSS sammeln + vorfiltern
│   ├── gmail_source.py              # Gmail-Newsletter → Stories  (NEU)
│   ├── analyst.py                   # Claude: priorisieren + Headlines ≤10 Wörter
│   ├── deliver.py                   # Dashboard (3 Tabs) + Telegram
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

### Phase 0 — Grundgerüst
- [ ] `requirements.txt` (`feedparser`, `anthropic`, `google-api-python-client`, `google-auth`, `google-auth-oauthlib`, ggf. `requests`)
- [ ] `.gitignore` (`output/`, `.env`, `token.json`, `client_secret*.json`, `__pycache__/`)
- [ ] Ordnerstruktur `src/`, `scripts/`, `state/` anlegen
- [ ] `README.md` (Kurzbeschreibung + Verweis auf Spec/Overview)

### Phase 1 — Konfiguration
- [ ] `config.py`: `TOPICS` (medtech 26 h, ai_news 72 h) mit Feeds, Keywords, Profilen
- [ ] `config.py`: `NEWSLETTER`-Block (Schritt-1-Query `is:unread newer_than:2d`, `max_messages=25`)
- [ ] Konstanten: `HEADLINE_MAX_WORDS=10`, `NEWSLETTER_TOP_N_IN_AI=5`, `ANTHROPIC_MODEL`
- [ ] Auskommentierte Schritt-2-Felder vorbereiten (allowlist/label/content_spam_check)

### Phase 2 — RSS-Collector
- [ ] `collector.py`: Feeds einlesen, Dedupe (Titel-Hash), Zeitfenster pro Thema
- [ ] Keyword-Sortierung (filtert nicht weg), Rückgabe `{topic_key: [article,...]}`
- [ ] Robustheit: tote Feeds überspringen, Lauf fortsetzen

### Phase 3 — Gmail-Quelle
- [ ] `scripts/oauth_setup.py`: lokaler `InstalledAppFlow`, gibt 3 Secrets aus (schreibt nichts ins Repo)
- [ ] `gmail_source.py`: headless Credentials aus 3 Secrets (Refresh-Flow)
- [ ] `fetch_newsletters()`: list → get(full) → From/Subject/Date + Body (text/plain bevorzugt)
- [ ] HTML-Strip mit **Link-Erhalt** (`href`→Klartext), Body-Kürzung (~6.000 Zeichen)
- [ ] Dedupe über `state/seen_ids.json` (FIFO, max. ~500 IDs)

### Phase 4 — Analyst (Claude)
- [ ] `analyst.py` (a): RSS-Bewertung pro Thema → `priority`, `reason`, `summary_de`
- [ ] `analyst.py` (b): `analyze_newsletters()` → Stories als striktes JSON
- [ ] Pro Story: `headline` (DE, ≤10 Wörter), `url`, `source_newsletter`, `priority`
- [ ] Validierung: Headline ≤10 Wörter (hart kürzen); Stories ohne `url` verwerfen
- [ ] JSON-Retry bei ungültiger Antwort (1×), sonst Thema/Newsletter leer

### Phase 5 — Deliver (Dashboard + Telegram)
- [ ] `deliver.py`: 3 Tabs (MedTech, AI News, Newsletter)
- [ ] MedTech/AI: Karten (priority-Farbe, Quelle, `summary_de`, „Warum relevant", Link)
- [ ] Newsletter-Tab: kompaktes Listenlayout (`● headline — Name ↗`)
- [ ] Cross-Posting: Top-`NEWSLETTER_TOP_N_IN_AI` zusätzlich im AI-Tab (Badge „aus Newsletter")
- [ ] Telegram (optional): Top-Prioritäten je Thema + Top-Newsletter-Headlines

### Phase 6 — Orchestrierung
- [ ] `run.py`: collect → fetch → analyze (RSS) → analyze (Newsletter) → build → telegram → seen_ids
- [ ] Headless (kein `open()`), Exit 0 bei Erfolg
- [ ] Gmail-Fehler dürfen RSS nicht blockieren (Newsletter-Tab dann leer + Hinweis)
- [ ] Nur deployen, wenn `output/dashboard.html` erzeugt wurde

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

> Laut Spec §5 liegen die drei Gmail-Werte beim Nutzer bereits vor und müssen nur
> noch als GitHub Secrets eingetragen werden.

---

## 6. Offene Entscheidungen (vor bzw. während Umsetzung klären)

1. **Repo öffentlich oder privat?** (Pages-Sichtbarkeit, Spec §9). Empfehlung: **privat**.
2. **Cron-Uhrzeit** final in UTC (Sommer-/Winterzeit). Spec-Default: `0 6 * * *`.
3. **Claude-Modell:** Spec nennt `claude-opus-4-6`. Aktuell verfügbar sind neuere
   Modelle — vor Implementierung auf ein aktuelles Modell festlegen.
4. **Telegram** aktiv ja/nein (optionaler Block).
5. **Konkrete Profile/Keywords** für MedTech (PE-Deal) und AI (Anwender) finalisieren.

---

## 7. Definition of Done (Gesamt, Spec §1.3)

- [ ] Action läuft täglich automatisch (Cron) und ist manuell auslösbar
- [ ] MedTech-RSS, AI-RSS und Gmail-Newsletter werden eingelesen
- [ ] Claude erzeugt pro Story Headline (≤10 Wörter) + Quell-Link
- [ ] Dashboard auf Pages mit 3 Tabs (MedTech, AI News, Newsletter)
- [ ] Top-Newsletter-Items erscheinen zusätzlich im AI-News-Tab
- [ ] Secrets ausschließlich in GitHub Secrets
- [ ] Ein Lauf kostet nur wenige Cent und bleibt im Freikontingent
- [ ] Newsletter-Spam-Schutz = Gmail-Filter (Härtung = Schritt 2)

---

## 8. Bewusst NICHT in diesem Projekt (Schritt 2, Spec §15)

Absender-Allowlist, Label-Strategie und inhaltlicher Spam-/Werbe-Check via Claude.
Die Config wird so vorbereitet, dass diese Härtung später **additiv** andocken kann.

---

## 9. Empfohlener nächster Schritt

**Phase 0 + 1** zusammen umsetzen (Grundgerüst + `config.py`), da alles Weitere
darauf aufbaut. Davor kurz die **Offenen Entscheidungen** (§6, v. a. Claude-Modell)
klären, damit `config.py` direkt korrekt ist.
