# strava-obsidian

Taking my own Strava data and putting it in my Obsidian vault.

## Phase 1

Query Strava's API for the most recent N activities and write the per-activity
stats to a plain text file.

Fields captured per activity:

- distance (km / mi)
- elapsed time and moving time (h:mm:ss)
- average heart rate
- max heart rate
- elevation gain (m / ft)
- start time (local)

### Setup

1. Create a Python virtual environment and install dependencies:

   ```
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Register an application at <https://www.strava.com/settings/api>. Set
   "Authorization Callback Domain" to `localhost`.

3. Copy `.env.example` to `.env` and fill in `STRAVA_CLIENT_ID` and
   `STRAVA_CLIENT_SECRET`.

4. Run the one-time authorization helper:

   ```
   python authorize.py
   ```

   Open the printed URL, click Authorize, and copy the `code` parameter from
   the localhost redirect URL into the prompt. The script will print a
   `STRAVA_REFRESH_TOKEN=...` line — paste it into `.env`.

### Usage

```
python get_activities.py                   # 30 most recent → activities.txt
python get_activities.py --count 100
python get_activities.py --output runs.txt
```

### API notes

- Uses the `activity:read_all` scope so private activities are included.
- Heart rate fields are present in `SummaryActivity` only when the activity
  was recorded with an HR sensor; missing values are rendered as `n/a`.
- Strava's rate limits are 200 requests / 15 min and 2000 / day. Each call to
  `/athlete/activities` returns up to 200 activities, so `--count 1000` costs
  5 requests.

### References

- Strava API reference: <https://developers.strava.com/docs/reference/>
- OAuth flow: <https://developers.strava.com/docs/authentication/>
