"""Fetch recent Strava activities and write them to a human-readable text file.

Reads credentials from .env (STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET,
STRAVA_REFRESH_TOKEN), refreshes the access token, calls the athlete
activities endpoint, and writes one labeled block per activity.

Usage:
    python get_activities.py                 # 30 most recent, writes activities.txt
    python get_activities.py --count 100     # last 100 activities
    python get_activities.py --output out.txt
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from typing import Any

import requests
from dotenv import load_dotenv

TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"

METERS_PER_MILE = 1609.344
METERS_PER_FOOT = 0.3048


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Exchange the refresh token for a short-lived access token."""
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise RuntimeError(f"no access_token in response: {payload}")
    return access_token


def fetch_activities(access_token: str, count: int) -> list[dict[str, Any]]:
    """Fetch up to `count` most recent activities, paginating as needed."""
    per_page = min(count, 200)  # Strava max is 200
    activities: list[dict[str, Any]] = []
    page = 1
    while len(activities) < count:
        remaining = count - len(activities)
        resp = requests.get(
            ACTIVITIES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"per_page": min(per_page, remaining), "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        activities.extend(batch)
        page += 1
    return activities[:count]


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "n/a"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


def format_distance(meters: float | None) -> str:
    if meters is None:
        return "n/a"
    km = meters / 1000.0
    mi = meters / METERS_PER_MILE
    return f"{km:.2f} km ({mi:.2f} mi)"


def format_elevation(meters: float | None) -> str:
    if meters is None:
        return "n/a"
    ft = meters / METERS_PER_FOOT
    return f"{meters:.0f} m ({ft:.0f} ft)"


def format_hr(value: float | None) -> str:
    if value is None:
        return "n/a (not recorded)"
    return f"{value:.0f} bpm"


def format_start(start_date_local: str | None) -> str:
    """Strava returns start_date_local as ISO-8601 in the athlete's local TZ
    but with a trailing Z. We parse and reformat as 'YYYY-MM-DD HH:MM:SS'.
    """
    if not start_date_local:
        return "n/a"
    # Strip trailing Z if present — value is already in local time
    s = start_date_local.rstrip("Z")
    try:
        parsed = dt.datetime.fromisoformat(s)
    except ValueError:
        return start_date_local
    return parsed.strftime("%Y-%m-%d %H:%M:%S (local)")


def render_block(act: dict[str, Any]) -> str:
    lines = [
        f"Name:           {act.get('name', '(unnamed)')}",
        f"ID:             {act.get('id')}",
        f"Type:           {act.get('sport_type') or act.get('type', 'n/a')}",
        f"Start:          {format_start(act.get('start_date_local'))}",
        f"Distance:       {format_distance(act.get('distance'))}",
        f"Elapsed time:   {format_duration(act.get('elapsed_time'))}",
        f"Moving time:    {format_duration(act.get('moving_time'))}",
        f"Elevation gain: {format_elevation(act.get('total_elevation_gain'))}",
        f"Avg HR:         {format_hr(act.get('average_heartrate'))}",
        f"Max HR:         {format_hr(act.get('max_heartrate'))}",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=30,
                        help="number of most recent activities to fetch (default 30)")
    parser.add_argument("--output", default="activities.txt",
                        help="output file path (default activities.txt)")
    args = parser.parse_args()

    load_dotenv()
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")
    missing = [k for k, v in [
        ("STRAVA_CLIENT_ID", client_id),
        ("STRAVA_CLIENT_SECRET", client_secret),
        ("STRAVA_REFRESH_TOKEN", refresh_token),
    ] if not v]
    if missing:
        print(f"ERROR: missing env vars: {', '.join(missing)}", file=sys.stderr)
        print("Run authorize.py to obtain a refresh token.", file=sys.stderr)
        return 1

    access_token = refresh_access_token(client_id, client_secret, refresh_token)
    activities = fetch_activities(access_token, args.count)

    header = (
        f"# Strava activities — {len(activities)} most recent\n"
        f"# Generated: {dt.datetime.now().isoformat(timespec='seconds')}\n"
    )
    blocks = [render_block(a) for a in activities]
    body = ("\n\n" + "-" * 60 + "\n\n").join(blocks)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(header + "\n" + body + "\n")

    print(f"Wrote {len(activities)} activities to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
