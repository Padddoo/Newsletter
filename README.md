# News-Agent (GitHub-hosted)

Täglich laufender News-Agent, vollständig auf GitHub gehostet (GitHub Actions +
GitHub Pages). Erstellt ein priorisiertes **AI-Briefing** aus zwei Quellen —
**AI-RSS** und **AI-Newsletter (Gmail)** — und veröffentlicht es als Dashboard
auf GitHub Pages, plus optionalem Telegram-Push.

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
├── gmail_source.py    # Gmail-Newsletter → Stories
├── analyst.py         # Claude: priorisieren + Headlines ≤10 Wörter
├── deliver.py         # Dashboard (2 Tabs) + Telegram
└── run.py             # Orchestrierung
scripts/oauth_setup.py # einmaliger lokaler OAuth-Flow
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
| `GMAIL_CLIENT_ID` | ja |
| `GMAIL_CLIENT_SECRET` | ja |
| `GMAIL_REFRESH_TOKEN` | ja |
| `TELEGRAM_BOT_TOKEN` | optional (Telegram) |
| `TELEGRAM_CHAT_ID` | optional (Telegram) |
