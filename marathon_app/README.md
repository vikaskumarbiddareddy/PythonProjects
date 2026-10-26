# Marathon Trainer

A personal phone web app for a 26-week marathon block (Oct 26 2026 → race Sun Apr 25 2027),
starting from a 2:30 half marathon and working toward a 3:30 marathon.

## What it does

- **Today** – the day's workout with pace targets, which shoe to wear, one-tap Done / Partial / Skip,
  optional details (distance, time, effort), and **Send to watch**.
- **Week** – the 7-day plan, planned vs. completed km, tap a day for details, send the whole week to Garmin.
- **Streaks** – a 26-week heatmap of every day plus current/longest streaks and perfect weeks.
  Planned rest days keep your streak alive; a skipped or unlogged run breaks it.
- **Progress** – predicted marathon time, progress toward 3:30, training paces, shoe km, test results.

## How the plan adapts

- Workouts are stored by pace *zone* (Easy, Marathon, Threshold, Interval, Repetition), not fixed paces.
  Paces come from your current fitness (Jack Daniels' VDOT).
- **Time trials** in weeks 4 (5K), 12 (10K), 14 (half marathon) and 20 (10K): log the result and every
  future workout's paces update.
- **Consistency bonus**: every 3 consecutive weeks with ≥90% of runs completed nudges your paces
  0.5 VDOT faster (max +1.5). The next test result replaces the bonus with measured fitness.
- Shoe choice: Magic Speed 5 for tests, the race and sessions with ≥4 km of fast running;
  Pegasus 42 for everything else.

Plan structure: Base (1–8), Build (9–16), Marathon-specific (17–23), Taper (24–26).
4 runs a week: Tue quality, Thu easy/steady, Sat long, Sun recovery. Every 4th week is a cutback.
Peak week ~62 km with a 32 km long run.

## Run it locally

```bash
cd marathon_app
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --host 0.0.0.0
pytest
```

Open http://localhost:8000 (or your computer's IP from your phone on the same Wi-Fi).

## Settings (environment variables)

| Variable | Purpose |
|---|---|
| `APP_KEY` | **Set this when hosting.** Open `https://your-app/?key=<APP_KEY>` once on your phone; a cookie keeps you signed in. |
| `GARMIN_EMAIL`, `GARMIN_PASSWORD` | Enables Send to watch. Tokens are cached so the password is only used on first login. |
| `MARATHON_DB` | SQLite file path (default `data/marathon.db`). |
| `GARMIN_TOKENS` | Garmin token folder (default `data/garmin_tokens`). |

If your Garmin account uses 2-step verification, run once on the server:
`python -m app.garmin_login` and type the code when asked.

## Hosting

The app needs a host with a **persistent disk** (it's SQLite). Build the `Dockerfile` and mount a
volume at `/data` – e.g. Fly.io or Railway with a volume. Hosts with ephemeral disks
(e.g. Render's free tier) would wipe your log on every restart.

On your phone, open the app and use **Add to Home Screen** – it then opens like a normal app.

## Garmin note

Garmin pushing uses the unofficial [`garminconnect`](https://github.com/cyberjunky/python-garminconnect)
library. It works today but Garmin can change things without notice; the rest of the app keeps working
if it breaks. `garmin_push_test.py` is the original feasibility test.
