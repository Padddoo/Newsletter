# Setup-Anleitung (v1: AI-Briefing)

Diese Anleitung bringt dich von „Code im Repo" bis zum täglich laufenden Agenten.
Sie ist auf **v1** zugeschnitten: Thema **AI** (Gmail-Newsletter + AI-RSS),
Zustellung über **GitHub Pages**, **Telegram** und **E-Mail** (Gmail `gmail.send`).

Reihenfolge einhalten. Geschätzte Dauer: ~20–30 Min.

---

## 0. Was du brauchst

| Wert | Pflicht | Woher |
|------|---------|-------|
| `ANTHROPIC_API_KEY` | ja | console.anthropic.com → API Keys |
| `GMAIL_CLIENT_ID` | ja | Google-OAuth-Client (Schritt 1) |
| `GMAIL_CLIENT_SECRET` | ja | Google-OAuth-Client (Schritt 1) |
| `GMAIL_REFRESH_TOKEN` | ja | lokal erzeugt (Schritt 2) |
| `TELEGRAM_BOT_TOKEN` | optional | @BotFather |
| `TELEGRAM_CHAT_ID` | optional | Telegram getUpdates |
| `EMAIL_TO` | optional | Empfänger (Default steht in `config.py`) |

> **Wichtig:** Diese Werte gehören **ausschließlich** in GitHub Secrets — nie in
> den Code, nie in Commits, nie in den Chat.

---

## 1. Google Cloud / OAuth-Client (einmalig)

> Falls du das beim ersten (read-only) Setup schon erledigt hast, kannst du den
> vorhandenen OAuth-Client weiterverwenden und direkt zu **Schritt 2** springen —
> du musst dort aber wegen des neuen `gmail.send`-Scopes einen **neuen**
> Refresh-Token erzeugen.

1. [Google Cloud Console](https://console.cloud.google.com) → neues Projekt (z. B. `news-agent`).
2. **APIs & Services → Gmail API aktivieren.**
3. **OAuth consent screen:** User type *External*; App-Name + eigene E-Mail eintragen.
   App im **„Testing"-Modus** lassen, die Newsletter-Gmail-Adresse als **Test-User** hinzufügen.
4. **Scopes:** `gmail.readonly` **und** `gmail.send` hinzufügen.
5. **Credentials → Create credentials → OAuth client ID → Typ „Desktop app".**
   JSON herunterladen → enthält `client_id` und `client_secret`.

---

## 2. Refresh-Token lokal erzeugen (einmalig)

Wegen des erweiterten Scopes (`readonly` **+** `send`) muss der Token **neu**
erzeugt werden — der alte read-only-Token kann nicht senden.

```bash
# im Projektordner, mit der heruntergeladenen client_secret*.json daneben
pip install google-auth-oauthlib
python scripts/oauth_setup.py
```

- Es öffnet sich der Browser → die **Newsletter-Gmail-Adresse** wählen und zustimmen
  (ggf. „Diese App ist nicht verifiziert" → erweitert → fortfahren; im Testing-Modus normal).
- Am Ende druckt das Skript drei Werte:
  `GMAIL_REFRESH_TOKEN`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`.
- Diese gleich in Schritt 4 als Secrets eintragen. **Nicht** ins Repo committen.

> Falls **kein** `refresh_token` ausgegeben wird: im Google-Konto unter
> „Drittanbieter-Apps" den Zugriff der App entfernen und das Skript erneut laufen
> lassen (erzwingt frische Zustimmung).

---

## 3. (Optional) Telegram einrichten

1. In Telegram **@BotFather** öffnen → `/newbot` → Namen vergeben → du erhältst den
   **`TELEGRAM_BOT_TOKEN`**.
2. Dem neuen Bot **eine beliebige Nachricht schreiben** (sonst kennt er deinen Chat nicht).
3. Chat-ID holen: im Browser
   `https://api.telegram.org/bot<DEIN_TOKEN>/getUpdates` öffnen → in der JSON-Antwort
   `chat.id` ablesen → das ist deine **`TELEGRAM_CHAT_ID`**.

Lässt du beide Werte weg, wird der Telegram-Versand einfach übersprungen.

---

## 4. GitHub Secrets setzen

Repo → **Settings → Secrets and variables → Actions → „New repository secret"**.
Für **jeden** Wert einmal (Name exakt, Groß-/Kleinschreibung zählt):

- `ANTHROPIC_API_KEY`
- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GMAIL_REFRESH_TOKEN`
- `TELEGRAM_BOT_TOKEN` *(optional)*
- `TELEGRAM_CHAT_ID` *(optional)*
- `EMAIL_TO` *(optional; sonst greift der Default aus `config.py`)*

> Secrets werden in Logs automatisch als `***` maskiert und sind nach dem Speichern
> nicht mehr auslesbar (nur überschreibbar).

---

## 5. (Optional) GitHub Pages aktivieren

Nur nötig, wenn du das **öffentliche Dashboard** willst.

- Repo → **Settings → Pages → Build and deployment → Source: „GitHub Actions".**
- Nach dem ersten erfolgreichen Lauf erscheint die URL `https://<user>.github.io/<repo>/`.
- Bei privatem Repo ohne Bezahlplan ist die Seite nicht verlinkt, aber technisch
  erreichbar. Wer das nicht will: Pages weglassen — Telegram + E-Mail liefern das
  Briefing trotzdem, das Dashboard bleibt als (nicht-öffentliches) Action-Artefakt.

> Verzichtest du komplett auf Pages, kann der `deploy`-Job in
> `.github/workflows/briefing.yml` entfernt werden (sag Bescheid, dann passe ich ihn an).

---

## 6. Ersten Lauf manuell auslösen

1. Repo → Reiter **„Actions"** (ggf. Workflows einmalig aktivieren).
2. Workflow **„briefing"** wählen → **„Run workflow"**.
3. Lauf öffnen, Live-Logs ansehen:
   - **Grün** = erfolgreich. Dashboard auf Pages bzw. als Artifact; Telegram-/E-Mail-Push da.
   - **Rot** = Logs öffnen, fehlgeschlagene Stufe aufklappen, Meldung lesen (siehe unten).

---

## 7. Häufige Stolpersteine

- **`invalid_grant` bei Gmail:** Refresh-Token ungültig/abgelaufen → Schritt 2 erneut,
  neuen `GMAIL_REFRESH_TOKEN` als Secret speichern.
- **E-Mail kommt nicht / „insufficient scopes":** Token noch ohne `gmail.send` →
  Schritt 2 mit beiden Scopes neu ausführen.
- **Pages zeigt 404:** erst nach dem ersten **erfolgreichen** Lauf vorhanden;
  „Source = GitHub Actions" prüfen.
- **Secret-Name vertippt:** muss exakt mit den Namen in `briefing.yml` übereinstimmen.
- **Cron-Zeit:** läuft in **UTC** (`0 6 * * *` = 06:00 UTC). Für eine andere Zeit
  die Cron-Zeile in `briefing.yml` anpassen.

---

## 8. Definition of Done

- [ ] Pflicht-Secrets gesetzt (Anthropic + 3× Gmail)
- [ ] `workflow_dispatch`-Testlauf ist grün
- [ ] Dashboard erreichbar (Pages-URL oder Artifact), 2 Tabs sichtbar
- [ ] Telegram- und/oder E-Mail-Briefing kommt an
- [ ] Cron-Lauf am Folgetag ebenfalls grün
