"""
oauth_setup.py — EINMALIG LOKAL ausführen, um den Gmail-Refresh-Token zu erzeugen.

Hintergrund (Spec §5): Eine zustandslose GitHub Action kann keinen Browser-OAuth
durchführen. Daher wird der Refresh-Token einmal lokal erzeugt und anschließend
zusammen mit Client-ID/-Secret als GitHub Secrets hinterlegt. Zur Laufzeit baut
gmail_source.py die Credentials headless aus diesen drei Werten.

Voraussetzung:
  - In der Google Cloud Console ein OAuth-Client vom Typ "Desktop app" angelegt
    und das JSON heruntergeladen (Spec §5.1).
  - Diese Datei (client_secret*.json) liegt im AKTUELLEN Ordner.

Ausführen:
    pip install google-auth-oauthlib
    python scripts/oauth_setup.py

Das Skript schreibt KEINE Tokens ins Repo — es druckt die drei Werte nur aus.
"""
from __future__ import annotations

import glob
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

# Minimaler Scope: nur Lesen, keine Schreib-/Sende-Rechte.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> None:
    candidates = sorted(glob.glob("client_secret*.json"))
    if not candidates:
        print("FEHLER: Keine 'client_secret*.json' im aktuellen Ordner gefunden.")
        print("Bitte das OAuth-Client-JSON (Typ 'Desktop app') hierher legen.")
        sys.exit(1)
    if len(candidates) > 1:
        print("FEHLER: Mehrere 'client_secret*.json' gefunden:", candidates)
        print("Bitte nur eine Datei behalten.")
        sys.exit(1)

    client_secret_file = candidates[0]
    print(f"Verwende OAuth-Client: {client_secret_file}")

    flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
    # access_type=offline + prompt=consent erzwingen die Ausgabe eines Refresh-Tokens.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        print("\nWARNUNG: Es wurde KEIN refresh_token zurückgegeben.")
        print("Tipp: In den Google-Konto-Einstellungen den App-Zugriff entfernen")
        print("und das Skript erneut ausführen (erzwingt frische Zustimmung).")

    print("\n" + "=" * 64)
    print("Folgende Werte als GitHub Secrets hinterlegen")
    print("(Repo -> Settings -> Secrets and variables -> Actions):")
    print("=" * 64)
    print("GMAIL_REFRESH_TOKEN =", creds.refresh_token)
    print("GMAIL_CLIENT_ID     =", creds.client_id)
    print("GMAIL_CLIENT_SECRET =", creds.client_secret)
    print("=" * 64)
    print("WICHTIG: Diese Werte NICHT ins Repo committen.")


if __name__ == "__main__":
    main()
