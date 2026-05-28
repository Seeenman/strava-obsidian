# strava-obsidian

A small command-line tool that pulls a day's Strava activities and writes them
to a per-day Markdown log file suitable for an Obsidian vault. Runs, bicycle
rides, and weight-training sessions are supported.

## What it does

For a given date (today by default), `strava-obsidian` calls the Strava API
for activities whose local start time falls on that date, filters down to
runs, bicycle rides, and weight-training sessions, and writes them into a
file named `log-<year>-<month>-<day>-<dayofweek>.md` (e.g.
`log-2026-05-27-Wed.md`) in the chosen directory.

Each run or bike activity becomes a block with distance (mi), moving time,
elevation gain (ft), and average / max heart rate:

```
# Run 10:22AM
- 📏8.21 mi, ⏱️56:13, ⛰️568 ft, ↔️❤️141 bpm, ⬆️❤️167 bpm
	- Description
	- Fuel: 
```

Each weight-training activity becomes a heading line with just the start time:

```
# #Strength 4:30PM
```

If the log file does not yet exist, it is created and only blocks for
activity types that actually occurred are added. If it already exists,
`[time of day]` placeholders are filled in and any extra activities for the
day are appended. Re-running the script on the same day is idempotent —
activities whose start time is already in the file are skipped.

The included `log-template.md` documents the block format. It is no longer
read by the script (`strava-obsidian` uses templates baked into the code),
but is kept in the repo for reference.

## Setup

### 1. Python virtualenv

From the repo root:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Strava API credentials

1. Register an application at <https://www.strava.com/settings/api>. Set
   the **Authorization Callback Domain** to `localhost`.
2. Copy `.env.example` to `.env` and fill in `STRAVA_CLIENT_ID` and
   `STRAVA_CLIENT_SECRET` from the Strava settings page.
3. Run the one-time authorization helper to obtain a refresh token:

   ```
   python authorize.py
   ```

   Open the printed URL, click **Authorize**, and copy the `code` query
   parameter from the resulting (failing) localhost redirect URL into the
   prompt. The script prints a `STRAVA_REFRESH_TOKEN=...` line — paste it
   into `.env`.

The OAuth scope used is `activity:read_all`, so private activities are
included.

### 3. Shell wrapper

`strava-obsidian` is a thin shell wrapper that activates `.venv` (if
present) and runs the Python script. It's already executable; if you've
moved the repo, edit the hardcoded `SCRIPT_DIR` near the top of the file.

For convenience, symlink it onto your `$PATH`:

```
ln -s "$(pwd)/strava-obsidian" ~/.local/bin/strava-obsidian
```

## Usage

```
strava-obsidian                                  # today, into current directory
strava-obsidian --date 2026-05-27                # a specific date
strava-obsidian --dir ~/vault/daily              # write into a chosen directory
strava-obsidian --date 2026-05-27 --dir ~/vault/daily
```

Arguments:

- `--date` — date in `YYYY-MM-DD` format. Defaults to today.
- `--dir`  — directory the log file is read from / written to. Defaults to
  the current directory. Created if it doesn't exist.

The script prints a one-line summary, e.g.:

```
Wrote 3 activities (1 run, 1 bike, 1 strength) for 2026-05-27 to /…/log-2026-05-27-Wed.md
```

## Notes

- Filenames follow `log-<year>-<month>-<day>-<dayofweek>.md`, where the day
  of week is the three-letter form (`Mon`, `Tue`, …).
- Strength activities are matched by Strava `sport_type` containing
  `WeightTraining`. Run/bike matching uses `Run` / `Ride` / `Bike`
  substrings, so trail runs, virtual rides, e-bike rides, etc. all count.
- Strava's rate limits are 200 requests / 15 min and 2000 / day. This tool
  uses 1 + N requests per run (token refresh + paginated activities; for a
  single day N is typically 1).
- Heart-rate fields render as empty if the activity wasn't recorded with a
  heart-rate sensor.

## References

- Strava API reference: <https://developers.strava.com/docs/reference/>
- Strava OAuth flow: <https://developers.strava.com/docs/authentication/>
