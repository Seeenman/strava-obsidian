"""Fetch Strava run/bike activities for a given date and write them to a
daily markdown log file.

Reads credentials from .env (STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET,
STRAVA_REFRESH_TOKEN), refreshes the access token, fetches activities whose
local start date matches the target date, filters to runs and bicycle rides,
and writes the per-activity stats into a log file named
`log-<year>-<month>-<day>-<dayofweek>.md` in the chosen directory. If the
file does not yet exist it is created from `log-template.md`.

Usage:
    python get_activities.py                                 # today, current dir
    python get_activities.py --date 2026-05-27               # specific date
    python get_activities.py --dir /path/to/vault            # output directory
    python get_activities.py --date 2026-05-27 --dir ./logs  # both
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"

METERS_PER_MILE = 1609.344
METERS_PER_FOOT = 0.3048

PLACEHOLDER = "[time of day]"
TEMPLATE_FILENAME = "log-template.md"


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


def fetch_activities_for_date(access_token: str, target_date: dt.date) -> list[dict[str, Any]]:
    """Return activities whose local start date equals target_date.

    Uses a UTC ±1 day window via the API's after/before params (so we don't
    miss activities recorded in any timezone), then filters by local date.
    """
    start_utc = dt.datetime.combine(
        target_date - dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc
    )
    end_utc = dt.datetime.combine(
        target_date + dt.timedelta(days=1), dt.time.max, tzinfo=dt.timezone.utc
    )
    after = int(start_utc.timestamp())
    before = int(end_utc.timestamp())

    activities: list[dict[str, Any]] = []
    page = 1
    while True:
        resp = requests.get(
            ACTIVITIES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"after": after, "before": before, "per_page": 100, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        activities.extend(batch)
        page += 1

    matched: list[dict[str, Any]] = []
    for a in activities:
        local_str = a.get("start_date_local") or ""
        if not local_str:
            continue
        try:
            local_dt = dt.datetime.fromisoformat(local_str.rstrip("Z"))
        except ValueError:
            continue
        if local_dt.date() == target_date:
            matched.append(a)
    return matched


def sport(act: dict[str, Any]) -> str:
    return act.get("sport_type") or act.get("type") or ""


def is_run(act: dict[str, Any]) -> bool:
    return "Run" in sport(act)


def is_bike(act: dict[str, Any]) -> bool:
    s = sport(act)
    return "Ride" in s or "Bike" in s


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return ""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def format_time_of_day(start_date_local: str) -> str:
    parsed = dt.datetime.fromisoformat(start_date_local.rstrip("Z"))
    return parsed.strftime("%-I:%M%p")


def render_data_line(act: dict[str, Any]) -> str:
    distance_mi = (act.get("distance") or 0) / METERS_PER_MILE
    duration = format_duration(act.get("moving_time") or act.get("elapsed_time"))
    elev_ft = (act.get("total_elevation_gain") or 0) / METERS_PER_FOOT
    avg_hr = act.get("average_heartrate")
    max_hr = act.get("max_heartrate")
    avg_hr_s = f"{avg_hr:.0f}" if avg_hr is not None else ""
    max_hr_s = f"{max_hr:.0f}" if max_hr is not None else ""
    return (
        f"- 📏{distance_mi:.2f} mi, ⏱️{duration}, ⛰️{elev_ft:.0f} ft, "
        f"↔️❤️{avg_hr_s} bpm, ⬆️❤️{max_hr_s} bpm"
    )


def ensure_log_file(log_path: Path, template_path: Path) -> None:
    if log_path.exists():
        return
    if not template_path.exists():
        raise FileNotFoundError(f"template not found: {template_path}")
    shutil.copy(template_path, log_path)


def parse_blocks(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Split lines into (heading_line, body_lines) blocks.

    The first element holds any preamble before the first '# ' heading; its
    heading is the empty string.
    """
    blocks: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_body: list[str] = []
    for line in lines:
        if line.startswith("# "):
            blocks.append((current_heading, current_body))
            current_heading = line
            current_body = []
        else:
            current_body.append(line)
    blocks.append((current_heading, current_body))
    return blocks


def render_blocks(blocks: list[tuple[str, list[str]]]) -> str:
    out: list[str] = []
    for heading, body in blocks:
        if heading:
            out.append(heading)
        out.extend(body)
    return "".join(out)


def is_run_heading(heading: str) -> bool:
    return heading.startswith("# Run")


def is_bike_heading(heading: str) -> bool:
    return heading.startswith("# Bike")


def fill_block(
    heading: str, body: list[str], act: dict[str, Any]
) -> tuple[str, list[str]]:
    time_str = format_time_of_day(act["start_date_local"])
    new_heading = heading.replace(PLACEHOLDER, time_str)
    new_body: list[str] = []
    replaced = False
    for line in body:
        if not replaced and "📏" in line:
            newline = "\n" if line.endswith("\n") else ""
            new_body.append(render_data_line(act) + newline)
            replaced = True
        else:
            new_body.append(line)
    return new_heading, new_body


def find_template_block(
    blocks: list[tuple[str, list[str]]], type_check
) -> tuple[str, list[str]] | None:
    """Return a pristine copy of the first heading/body of the given type."""
    for heading, body in blocks:
        if type_check(heading):
            return heading, list(body)
    return None


def existing_times(
    blocks: list[tuple[str, list[str]]], type_check
) -> set[str]:
    """Times of day already written under headings of the given type."""
    times: set[str] = set()
    for heading, _ in blocks:
        if not type_check(heading) or PLACEHOLDER in heading:
            continue
        # Strip leading "# Run " or "# Bike " and trailing whitespace/newline.
        rest = heading.split(" ", 2)
        if len(rest) >= 3:
            times.add(rest[2].strip())
    return times


def fill_or_insert(
    blocks: list[tuple[str, list[str]]],
    activities: list[dict[str, Any]],
    type_check,
    template_block: tuple[str, list[str]] | None,
) -> list[tuple[str, list[str]]]:
    if not activities:
        return blocks

    already_logged = existing_times(blocks, type_check)
    pending = [
        a for a in activities
        if format_time_of_day(a["start_date_local"]) not in already_logged
    ]
    if not pending:
        return blocks

    result = list(blocks)
    idx = 0

    # Pass 1: fill any heading with a [time of day] placeholder.
    for i, (heading, body) in enumerate(result):
        if idx >= len(pending):
            break
        if type_check(heading) and PLACEHOLDER in heading:
            result[i] = fill_block(heading, body, pending[idx])
            idx += 1

    # Pass 2: append fresh copies of the template block for any remainder.
    if idx < len(pending) and template_block is not None:
        # Insert after the last existing block of this type so order is
        # preserved (Runs stay grouped, Bikes stay grouped).
        insert_at = len(result)
        for i, (heading, _) in enumerate(result):
            if type_check(heading):
                insert_at = i + 1
        while idx < len(pending):
            t_heading, t_body = template_block
            result.insert(insert_at, fill_block(t_heading, list(t_body), pending[idx]))
            insert_at += 1
            idx += 1

    return result


def integrate_activities(
    blocks: list[tuple[str, list[str]]], activities: list[dict[str, Any]]
) -> list[tuple[str, list[str]]]:
    runs = sorted(
        [a for a in activities if is_run(a)],
        key=lambda a: a.get("start_date_local", ""),
    )
    bikes = sorted(
        [a for a in activities if is_bike(a)],
        key=lambda a: a.get("start_date_local", ""),
    )
    run_template = find_template_block(blocks, is_run_heading)
    bike_template = find_template_block(blocks, is_bike_heading)
    blocks = fill_or_insert(blocks, runs, is_run_heading, run_template)
    blocks = fill_or_insert(blocks, bikes, is_bike_heading, bike_template)
    return blocks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        help="date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--dir",
        default=".",
        help="directory in which to read/write the log file (default: current directory)",
    )
    args = parser.parse_args()

    if args.date:
        try:
            target_date = dt.date.fromisoformat(args.date)
        except ValueError:
            print(
                f"ERROR: invalid date {args.date!r}, expected YYYY-MM-DD",
                file=sys.stderr,
            )
            return 1
    else:
        target_date = dt.date.today()

    script_dir = Path(__file__).resolve().parent
    load_dotenv(dotenv_path=script_dir / ".env")
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
    all_activities = fetch_activities_for_date(access_token, target_date)
    activities = [a for a in all_activities if is_run(a) or is_bike(a)]

    out_dir = Path(args.dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"log-{target_date.strftime('%Y-%m-%d')}-{target_date.strftime('%a')}.md"
    log_path = out_dir / filename
    template_path = script_dir / TEMPLATE_FILENAME

    ensure_log_file(log_path, template_path)

    with open(log_path, encoding="utf-8") as f:
        lines = f.readlines()

    blocks = parse_blocks(lines)
    blocks = integrate_activities(blocks, activities)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(render_blocks(blocks))

    n_runs = sum(1 for a in activities if is_run(a))
    n_bikes = sum(1 for a in activities if is_bike(a))
    print(
        f"Wrote {len(activities)} activities ({n_runs} run, {n_bikes} bike) "
        f"for {target_date} to {log_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
