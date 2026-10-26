"""One-time interactive Garmin login (handles 2-step verification) that caches tokens.

    python -m app.garmin_login

Asks for email and password (or reads GARMIN_EMAIL / GARMIN_PASSWORD). The password
is only used for this login and is never written to disk; the app then runs on the
cached tokens in GARMIN_TOKENS.
"""

import getpass
import os

from garminconnect import Garmin

from .garmin import TOKEN_DIR

if __name__ == "__main__":
    email = os.environ.get("GARMIN_EMAIL") or input("Garmin email: ").strip()
    password = os.environ.get("GARMIN_PASSWORD") or getpass.getpass("Garmin password (not shown, not saved): ")
    api = Garmin(email, password, prompt_mfa=lambda: input("Garmin verification code: ").strip())
    api.login(TOKEN_DIR)  # the library writes the tokens owner-only (0600 file in a 0700 folder)
    print(f"Connected to Garmin as {api.get_full_name()}. Tokens saved in {TOKEN_DIR}")
