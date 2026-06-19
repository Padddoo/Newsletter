# News-Agent (GitHub-hosted)

Täglich laufender News-Agent, vollständig auf GitHub gehostet (GitHub Actions).
Erstellt ein priorisiertes **AI-Briefing** aus zwei Quellen — **AI-RSS** und
**AI-Newsletter (Gmail via IMAP)** — und verschickt es per **Telegram** und
**E-Mail** (Gmail SMTP); das Dashboard liegt als Action-Artefakt bereit.

> **Scope v1:** nur das Thema **AI**. MedTech ist geparkt und später additiv
> reaktivierbar. Details siehe [`PROJECT_OVERVIEW.md`](./PROJECT_OVERVIEW.md).

## Dokumente
- [`News_Spec.md`](./News_Spec.md) — verbindliche Bau-Anleitung (v1.0).
- [`PROJECT_OVERVIEW.md`](./PROJECT_OVERVIEW.md) — Arbeitsplan mit Phasen & Checklisten.

## Struktur
```
src/
├── config.py          # Themen, Feeds, Profile, Settings
├── collector.py       # AI-RSS sammeln + vorfiltern
├── gmail_source.py    # Gmail-Newsletter via IMAP → Stories
├── analyst.py         # Claude: priorisieren + Headlines ≤10 Wörter
├── deliver.py         # Dashboard (2 Tabs) + Telegram + E-Mail (SMTP)
└── run.py             # Orchestrierung
state/seen_ids.json    # Dedupe-Status (von der Action gepflegt)
```

## Lokale Entwicklung
```bash
pip install -r requirements.txt
# Secrets via .env bereitstellen (siehe unten), dann:
python src/run.py
```

## Secrets / Environment-Variablen
Geheimnisse stehen ausschließlich in Environment-Variablen (lokal `.env`, in der
Action GitHub Secrets) — **nie im Code**.

| Variable | Pflicht |
|----------|---------|
| `ANTHROPIC_API_KEY` | ja |
| `GMAIL_ADDRESS` | ja (Newsletter-Postfach) |
| `GMAIL_APP_PASSWORD` | ja (Gmail-App-Passwort, 2FA nötig) |
| `TELEGRAM_BOT_TOKEN` | optional (Telegram) |
| `TELEGRAM_CHAT_ID` | optional (Telegram) |
| `EMAIL_TO` | optional (Empfänger, kommagetrennt für mehrere; sonst Default aus `config.py`) |

> **Gmail-Zugang:** App-Passwort (IMAP zum Lesen, SMTP zum Senden) — kein OAuth.
> 2-Faktor-Auth am Konto aktivieren, dann ein App-Passwort erzeugen. Siehe
> [`SETUP.md`](./SETUP.md).
