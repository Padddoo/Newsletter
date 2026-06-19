# Setup-Anleitung (v1: AI-Briefing)

Vom Code im Repo bis zum täglich laufenden Agenten. Zuschnitt **v1**: Thema **AI**
(Gmail-Newsletter via IMAP + AI-RSS), Zustellung über **Telegram** und **E-Mail**
(Gmail SMTP). Dashboard liegt als Action-Artefakt bereit.

Gmail-Zugang läuft über ein **App-Passwort** (kein OAuth). Dauer: ~10 Min.

---

## 0. Was du brauchst

| Secret | Pflicht | Woher |
|--------|---------|-------|
| `ANTHROPIC_API_KEY` | ja | console.anthropic.com → API Keys |
| `GMAIL_ADDRESS` | ja | Adresse des Newsletter-Postfachs |
| `GMAIL_APP_PASSWORD` | ja | Gmail-App-Passwort (Schritt 1) |
| `TELEGRAM_BOT_TOKEN` | optional | @BotFather |
| `TELEGRAM_CHAT_ID` | optional | Telegram getUpdates |
| `EMAIL_TO` | optional | Empfänger (Default steht in `config.py`) |

> **Wichtig:** Diese Werte gehören **ausschließlich** in GitHub Secrets — nie in
> den Code, nie in Commits, nie in den Chat.

---

## 1. Gmail-App-Passwort erstellen (einmalig)

App-Passwörter setzen **2-Faktor-Authentifizierung** voraus.

1. Google-Konto (das **Newsletter-Postfach**) → [myaccount.google.com/security](https://myaccount.google.com/security).
2. **2-Step Verification** aktivieren (falls noch nicht).
3. Danach **App passwords** öffnen: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
4. Einen Namen vergeben (z. B. `news-agent`) → **Create**.
5. Google zeigt ein **16-stelliges Passwort** (4×4, mit Leerzeichen). Das ist dein
   `GMAIL_APP_PASSWORD`. (Leerzeichen sind egal — der Code entfernt sie.)

> IMAP muss bei aktuellen Gmail-Konten nicht mehr separat aktiviert werden.
> Das App-Passwort erlaubt Lesen (IMAP) **und** Senden (SMTP) — beides nutzen wir.
> Du kannst es jederzeit unter „App passwords" wieder widerrufen.

---

## 2. (Optional) Telegram einrichten

1. In Telegram **@BotFather** → `/newbot` → Namen vergeben → du erhältst den
   **`TELEGRAM_BOT_TOKEN`**.
2. Dem neuen Bot **eine Nachricht schreiben** (sonst kennt er deinen Chat nicht).
3. `https://api.telegram.org/bot<DEIN_TOKEN>/getUpdates` im Browser öffnen →
   `"chat":{"id": ...}` ablesen → das ist deine **`TELEGRAM_CHAT_ID`**
   (persönlicher Chat = positive Zahl, Gruppe = negativ; nicht der `@name`).

Ohne diese beiden Werte wird der Telegram-Versand einfach übersprungen.

---

## 3. GitHub Secrets setzen

Repo → **Settings → Secrets and variables → Actions → „New repository secret"**.
Für **jeden** Wert einmal (Name exakt, Groß-/Kleinschreibung zählt), unter
**„Secrets"** (nicht „Variables"), auf **Repository**-Ebene:

- `ANTHROPIC_API_KEY`
- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `TELEGRAM_BOT_TOKEN` *(optional)*
- `TELEGRAM_CHAT_ID` *(optional)*
- `EMAIL_TO` *(optional)*

---

## 4. Ersten Lauf auslösen

1. Repo → **„Actions"** → Workflow **„briefing"** → **„Run workflow"**.
2. Lauf öffnen, Logs ansehen:
   - **Grün** = erfolgreich. In den Logs des Schritts „Run agent" stehen z. B.
     `[gmail] N neue Newsletter`, `[telegram] gesendet`, `[email] gesendet`.
   - Das Dashboard liegt als Artefakt **„dashboard"** unten beim Lauf zum Download.

Der **Cron** (täglich 06:00 UTC ≈ 08:00 Berlin) startet den Lauf danach automatisch.

---

## 5. Häufige Stolpersteine

- **`IMAP-Login fehlgeschlagen`:** `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` prüfen;
  2FA muss aktiv und das App-Passwort gültig sein.
- **`[email] Fehler` (SMTP):** dasselbe App-Passwort gilt fürs Senden — meist
  derselbe Ursprung wie ein IMAP-Login-Fehler.
- **`[telegram] Fehler 400 … chat not found`:** falsche `TELEGRAM_CHAT_ID`, oder
  du hast dem Bot noch nie geschrieben.
- **Secret-Name vertippt:** muss exakt mit `briefing.yml` übereinstimmen.
- **Keine Newsletter (`0 neue`):** alle der letzten 2 Tage schon als gesehen
  markiert, oder im Postfach sind keine ungelesenen Mails im Zeitfenster.

---

## 6. Definition of Done

- [ ] Pflicht-Secrets gesetzt (`ANTHROPIC_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`)
- [ ] `Run workflow`-Testlauf ist grün
- [ ] Telegram- und/oder E-Mail-Briefing kommt an
- [ ] Cron-Lauf am Folgetag ebenfalls grün
