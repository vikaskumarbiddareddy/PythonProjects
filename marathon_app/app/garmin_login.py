"""One-time interactive Garmin login (handles 2-step verification) that caches tokens.

    GARMIN_EMAIL=... GARMIN_PASSWORD=... python -m app.garmin_login
"""

import os

from garminconnect import Garmin

from .garmin import TOKEN_DIR

if __name__ == "__main__":
    api = Garmin(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"],
                 prompt_mfa=lambda: input("Garmin verification code: "))
    api.login(TOKEN_DIR)
    print(f"Logged in as {api.get_full_name()}; tokens saved to {TOKEN_DIR}")
