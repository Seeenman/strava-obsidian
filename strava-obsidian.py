"""Fetch Strava run/bike/weight-training activities for a given date and
write them to a daily markdown log file.

Reads credentials from .env (STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET,
STRAVA_REFRESH_TOKEN), refreshes the access token, fetches activities whose
local start date matches the target date, filters to runs, bicycle rides,
and weight-training sessions, and writes the per-activity stats into a log
file named `log-<year>-<month>-<day>-<dayofweek>.md` in the chosen
directory.

If the file does not yet exist it is created empty; only blocks for activity
types that actually occurred are added. If the file already exists, any
`[time of day]` placeholders are filled and extra activities are appended.

Usage:
    python strava-obsidian.py                                 # today, current dir
    python strava-obsidian.py --date 2026-05-27               # specific date
    python strava-obsidian.py --dir /path/to/vault            # output directory
    python strava-obsidian.py --date 2026-05-27 --dir ./logs  # both
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
ACTIVITY_URL = "https://www.strava.com/api/v3/activities"  # single activity detail

METERS_PER_MILE = 1609.344
METERS_PER_FOOT = 0.3048

PLACEHOLDER = "[time of day]"


# --- Activity kinds ---------------------------------------------------------

@dataclass(frozen=True)
class ActivityKind:
    """One supported activity type and the markdown block used for it."""
    name: str                        # short label for logging
    heading_prefix: str              # "# Run", "# Bike", "# #Strength"
    sport_keywords: tuple[str, ...]  # match Strava's sport_type substring
    template_lines: tuple[str, ...]  # heading + body lines for fresh blocks

    def matches_activity(self, act: dict[str, Any]) -> bool:
        s = act.get("sport_type") or act.get("type") or ""
        return any(k in s for k in self.sport_keywords)

    def matches_heading(self, heading: str) -> bool:
        return heading.startswith(self.heading_prefix)

    @property
    def has_description(self) -> bool:
        """True if this kind's template has a `- Description` bullet to fill."""
        return any("- Description" in line for line in self.template_lines)


# Body shared by Run and Bike. Strength has no body — just a heading line.
_RUN_BIKE_BODY = (
    "- 📏 mi, ⏱️, ⛰️ ft, ↔️❤️ bpm, ⬆️❤️ bpm\n",
    "\t- Description\n",
    "\t- Fuel: \n",
)

KINDS: tuple[ActivityKind, ...] = (
    ActivityKind(
        name="run", heading_prefix="# Run",
        sport_keywords=("Run",),
        template_lines=("# Run [time of day]\n", *_RUN_BIKE_BODY),
    ),
    ActivityKind(
        name="bike", heading_prefix="# Bike",
        sport_keywords=("Ride", "Bike"),
        template_lines=("# Bike [time of day]\n", *_RUN_BIKE_BODY),
    ),
    ActivityKind(
        name="strength", heading_prefix="# #Strength",
        sport_keywords=("WeightTraining",),
        template_lines=("# #Strength [time of day]\n",),
    ),
)


# --- Strava API -------------------------------------------------------------

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
    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"no access_token in response: {payload}")
    return token


def fetch_activities_for_date(
    access_token: str, target_date: dt.date
) -> list[dict[str, Any]]:
    """Return activities whose local start date equals target_date.

    Uses a ±1-day UTC window on the API's after/before params so we don't
    miss activities recorded in any timezone, then filters by local date.
    """
    start = dt.datetime.combine(
        target_date - dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc
    )
    end = dt.datetime.combine(
        target_date + dt.timedelta(days=1), dt.time.max, tzinfo=dt.timezone.utc
    )
    base_params = {
        "after": int(start.timestamp()),
        "before": int(end.timestamp()),
        "per_page": 100,
    }

    activities: list[dict[str, Any]] = []
    page = 1
    while True:
        resp = requests.get(
            ACTIVITIES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={**base_params, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        activities.extend(batch)
        page += 1

    def started_on_target_date(a: dict[str, Any]) -> bool:
        s = a.get("start_date_local") or ""
        try:
            return dt.datetime.fromisoformat(s.rstrip("Z")).date() == target_date
        except ValueError:
            return False

    return [a for a in activities if started_on_target_date(a)]


def fetch_activity_detail(access_token: str, activity_id: int) -> dict[str, Any]:
    """Fetch one activity's DetailedActivity. Needed for fields like
    `description` that aren't included in the list endpoint's SummaryActivity.
    """
    resp = requests.get(
        f"{ACTIVITY_URL}/{activity_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# --- Formatting -------------------------------------------------------------

def format_duration(seconds: int | float | None) -> str:
    """`h:mm:ss` for >=1h, `m:ss` for shorter activities, `""` for None."""
    if seconds is None:
        return ""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def format_time_of_day(start_date_local: str) -> str:
    parsed = dt.datetime.fromisoformat(start_date_local.rstrip("Z"))
    return parsed.strftime("%-I:%M%p")


def render_data_line(act: dict[str, Any]) -> str:
    distance_mi = (act.get("distance") or 0) / METERS_PER_MILE
    duration = format_duration(act.get("moving_time") or act.get("elapsed_time"))
    elev_ft = (act.get("total_elevation_gain") or 0) / METERS_PER_FOOT
    avg_hr = act.get("average_heartrate")
    max_hr = act.get("max_heartrate")
    avg = f"{avg_hr:.0f}" if avg_hr else ""
    mx = f"{max_hr:.0f}" if max_hr else ""
    return (
        f"- 📏{distance_mi:.2f} mi, ⏱️{duration}, ⛰️{elev_ft:.0f} ft, "
        f"↔️❤️{avg} bpm, ⬆️❤️{mx} bpm"
    )


# --- Markdown blocks --------------------------------------------------------

Block = tuple[str, list[str]]  # (heading_line, body_lines)


def parse_blocks(lines: list[str]) -> list[Block]:
    """Split lines into (heading, body) blocks at every `# ` heading.

    The first block always holds the preamble (lines before any heading) and
    uses `""` as its heading.
    """
    blocks: list[Block] = []
    heading = ""
    body: list[str] = []
    for line in lines:
        if line.startswith("# "):
            blocks.append((heading, body))
            heading, body = line, []
        else:
            body.append(line)
    blocks.append((heading, body))
    return blocks


def render_blocks(blocks: list[Block]) -> str:
    out: list[str] = []
    for heading, body in blocks:
        if heading:
            out.append(heading)
        out.extend(body)
    return "".join(out)


def fill_block(heading: str, body: list[str], act: dict[str, Any]) -> Block:
    """Fill `[time of day]`, the 📏 data line, and the Description bullet."""
    new_heading = heading.replace(
        PLACEHOLDER, format_time_of_day(act["start_date_local"])
    )
    description = (act.get("description") or "").strip()
    new_body: list[str] = []
    for line in body:
        newline = "\n" if line.endswith("\n") else ""
        if "📏" in line:
            new_body.append(render_data_line(act) + newline)
        elif description and line.strip() == "- Description":
            indent = line[: len(line) - len(line.lstrip())]
            # Each non-empty line of the Strava description becomes its own
            # bullet at the same indent level. The first line keeps the
            # "Description:" label; subsequent lines become bare bullets.
            desc_lines = [s.strip() for s in description.splitlines() if s.strip()]
            new_body.append(f"{indent}- Description: {desc_lines[0]}" + newline)
            for extra in desc_lines[1:]:
                new_body.append(f"{indent}- {extra}" + newline)
        else:
            new_body.append(line)
    return new_heading, new_body


def existing_times(blocks: list[Block], kind: ActivityKind) -> set[str]:
    """Times of day already written under filled headings of the given kind."""
    times: set[str] = set()
    for heading, _ in blocks:
        if not kind.matches_heading(heading) or PLACEHOLDER in heading:
            continue
        # Heading shape: "# Run 10:22AM", "# Bike 3:04PM", "# #Strength 4:30PM"
        parts = heading.strip().rsplit(" ", 1)
        if len(parts) == 2:
            times.add(parts[1])
    return times


def fill_or_insert(
    blocks: list[Block],
    activities: list[dict[str, Any]],
    kind: ActivityKind,
) -> list[Block]:
    """Fill `[time of day]` placeholders for this kind, then append the rest."""
    if not activities:
        return blocks

    already = existing_times(blocks, kind)
    pending = [
        a for a in activities
        if format_time_of_day(a["start_date_local"]) not in already
    ]
    if not pending:
        return blocks

    result = list(blocks)
    idx = 0

    # Pass 1: fill any heading with a [time of day] placeholder.
    for i, (heading, body) in enumerate(result):
        if idx >= len(pending):
            break
        if kind.matches_heading(heading) and PLACEHOLDER in heading:
            result[i] = fill_block(heading, body, pending[idx])
            idx += 1

    # Pass 2: append fresh blocks built from the kind's template. Insert after
    # the last existing block of this kind so same-kind blocks stay grouped;
    # if there are none yet, fall back to appending at the end of the file.
    if idx < len(pending):
        insert_at = len(result)
        for i, (heading, _) in enumerate(result):
            if kind.matches_heading(heading):
                insert_at = i + 1
        for act in pending[idx:]:
            block = fill_block(
                kind.template_lines[0], list(kind.template_lines[1:]), act
            )
            result.insert(insert_at, block)
            insert_at += 1

    return result


def enrich_with_description(
    activities: list[dict[str, Any]],
    blocks: list[Block],
    access_token: str,
) -> None:
    """Mutate `activities` in place, attaching Strava's free-form `description`.

    Description is only on the DetailedActivity schema, so each lookup costs
    one extra API call. We skip:
      - kinds whose template has no `- Description` bullet (Strength)
      - activities already logged in `blocks` (idempotent re-runs cost nothing)
    """
    for act in activities:
        kind = next((k for k in KINDS if k.matches_activity(act)), None)
        if kind is None or not kind.has_description:
            continue
        if format_time_of_day(act["start_date_local"]) in existing_times(blocks, kind):
            continue
        detail = fetch_activity_detail(access_token, act["id"])
        act["description"] = detail.get("description")


def integrate_activities(
    blocks: list[Block], activities: list[dict[str, Any]]
) -> list[Block]:
    """Place each activity into the right kind's block(s), preserving order."""
    for kind in KINDS:
        same_kind = sorted(
            [a for a in activities if kind.matches_activity(a)],
            key=lambda a: a.get("start_date_local", ""),
        )
        blocks = fill_or_insert(blocks, same_kind, kind)
    return blocks


# --- Entry point ------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date", help="date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--dir", default=".",
        help="directory for the log file (default: current directory)",
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
    creds = {
        v: os.getenv(v) for v in
        ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN")
    }
    missing = [k for k, v in creds.items() if not v]
    if missing:
        print(f"ERROR: missing env vars: {', '.join(missing)}", file=sys.stderr)
        print("Run authorize.py to obtain a refresh token.", file=sys.stderr)
        return 1

    access_token = refresh_access_token(
        creds["STRAVA_CLIENT_ID"],
        creds["STRAVA_CLIENT_SECRET"],
        creds["STRAVA_REFRESH_TOKEN"],
    )
    activities = [
        a for a in fetch_activities_for_date(access_token, target_date)
        if any(k.matches_activity(a) for k in KINDS)
    ]

    out_dir = Path(args.dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"log-{target_date.strftime('%Y-%m-%d-%a')}.md"

    if log_path.exists():
        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = []

    blocks = parse_blocks(lines)
    # Fetch DetailedActivity (for description) only for activities we're
    # actually going to write — keeps idempotent re-runs free of extra calls.
    enrich_with_description(activities, blocks, access_token)
    blocks = integrate_activities(blocks, activities)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(render_blocks(blocks))

    summary = ", ".join(
        f"{sum(1 for a in activities if k.matches_activity(a))} {k.name}"
        for k in KINDS
    )
    print(
        f"Wrote {len(activities)} activities ({summary}) "
        f"for {target_date} to {log_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
