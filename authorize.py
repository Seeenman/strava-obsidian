"""One-time OAuth helper to obtain a Strava refresh token.

Run this once after setting STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in .env.
It will print an authorization URL, ask you to paste the resulting `code` query
parameter, exchange that code for a refresh token, and print the token for you
to save in .env as STRAVA_REFRESH_TOKEN.
"""
from __future__ import annotations

import os
import sys
import urllib.parse

import requests
from dotenv import load_dotenv

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
REDIRECT_URI = "http://localhost/exchange_token"
SCOPE = "activity:read_all"


def main() -> int:
    load_dotenv()
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("ERROR: STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET must be set in .env",
              file=sys.stderr)
        return 1

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "approval_prompt": "auto",
        "scope": SCOPE,
    }
    url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    print("1. Open this URL in your browser and click Authorize:\n")
    print(f"   {url}\n")
    print("2. You will be redirected to a localhost URL that fails to load.")
    print("   Copy the value of the `code` query parameter from the address bar.\n")
    code = input("Paste the code here: ").strip()
    if not code:
        print("ERROR: no code provided", file=sys.stderr)
        return 1

    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()

    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        print(f"ERROR: no refresh_token in response: {payload}", file=sys.stderr)
        return 1

    print("\nSuccess. Add this line to your .env file:\n")
    print(f"STRAVA_REFRESH_TOKEN={refresh_token}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
