# Marathon Trainer

A personal phone web app for a 26-week marathon block (first run Thu Oct 29 2026 → race Sun Apr 25 2027),
starting from a 2:20 half marathon, with a half marathon on Sun Dec 6, working toward a 3:30 marathon.

## What it does

- **Today** – the day's workout with pace targets, which shoe to wear, one-tap Done / Partial / Skip,
  optional details (distance, time, effort), and **Send to watch**.
- **Week** – the 7-day plan, planned vs. completed km, tap a day for details, send the whole week to Garmin.
- **Streaks** – a 26-week heatmap of every day plus current/longest streaks and perfect weeks.
  Planned rest days keep your streak alive; a skipped or unlogged run breaks it.
- **Progress** – predicted marathon time, progress toward 3:30, weight trend, training paces, shoe km, test results.
- **Weight** – log a weigh-in whenever you like (one per day; a second entry replaces the first) and
  optionally copy it to Garmin Connect.

## Moving workouts

- **Missed a run?** On the rest day after it, Today shows *"You missed Tue's workout - Do it today
  instead"*: the run and the rest day swap, and the next run stays as planned. A missed Saturday long
  run can be done on Sunday instead of the recovery run.
- **↔ Move to another day** on any upcoming or missed workout: pick a day later in the same week.
  A rest day swaps; a day with a run offers **Replace** (that run is skipped and the week total drops)
  or **Swap** (the two runs trade days). Races are fixed; logged days and past days can't be used.
  A warning appears when two hard days end up back to back.
- **Garmin:** a moved workout that was already sent to the watch is re-sent for its new day, and a
  replaced one is removed. A run Garmin finds on a rest day right after a missed workout brings up
  *"Count it as Tue's workout?"*.
- **↺ Undo this week's moves** on the Week screen restores the original plan until a moved workout is
  logged. Moved days are never rewritten by later plan updates.

## Garmin, both ways

- **App → watch:** *Send to watch* uploads the workout with pace targets and schedules it on your
  Garmin calendar; sync the watch and it appears under today's workout.
- **Watch → app:** when the app opens (at most every 10 minutes) or you tap *Get finished runs from Garmin*,
  it reads your running activities since the plan began and marks the matching day's workout
  done (or partial if under 80% of the planned distance), with real distance, time, pace and average HR.
  Runs you logged by hand are never overwritten; runs on rest days are ignored.
  Test results (time trials) still need the test time entered by hand.

## Dec 6 half marathon

Weeks 3-7 are a half-marathon block inside the marathon plan:

| Week | Tue | Thu | Sat | Sun |
|---|---|---|---|---|
| 3 (Nov 9) | 3 x 1.5 km threshold | easy 7 + strides | 15 km, last 3 @ half pace | recovery 5 |
| 4 (Nov 16) | **5K time trial** - picks the race goal | easy 7 | 18 km | recovery 4 |
| 5 (Nov 23) | 3 x 2 km @ half pace | easy 6 | 12 km rehearsal, 6 @ half pace | recovery 4 |
| 6 (Nov 30) | 4 x 1 km @ half pace | easy 5 | shakeout 3 km | **race** |
| 7 (Dec 7) | recovery week: easy runs only | | | |

Half pace (zone H) comes from the race goal chosen on **Progress**: Stretch 1:55, A 2:05, B 2:10,
C 2:15 (default until the 5K test; ★ marks the goal that fits current fitness). Changing the goal
updates every half-pace workout; re-send the week to the watch. Log the finish time on race day and
the result resets your training paces for the marathon build that resumes in week 8.

Heart rate: easy days show a ceiling (78% of max HR; max estimated from age 36 = 183, editable on
Progress).

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

## Install on your Android phone (Termux, no cloud)

Everything runs on the phone: the server only listens on `127.0.0.1`, so nothing on your
Wi-Fi or the internet can reach it.

1. Install **Termux** from [F-Droid](https://f-droid.org/packages/com.termux/) (not the outdated Play Store build).
   Optional, also from F-Droid: **Termux:Widget** (home-screen button) and **Termux:Boot** (start when the phone boots).
2. In Termux:
   ```bash
   curl -fsSLo setup.sh https://raw.githubusercontent.com/vikaskumarbiddareddy/PythonProjects/main/marathon_app/termux/setup.sh
   bash setup.sh
   ```
3. Connect Garmin (type your password at the prompt; it is **not** saved, only Garmin's login tokens are):
   ```bash
   marathon garmin
   ```
4. Open the app: `marathon`. In Chrome tap **⋮ → Install app** (or *Add to Home screen*).

| Command | What it does |
|---|---|
| `marathon` | start the server if needed and open the app |
| `marathon stop` / `restart` / `status` | control the server |
| `marathon garmin` | (re)connect Garmin |
| `marathon update` | download the latest version (keeps your data) |
| `marathon log` | show the server log |

### Updating

1. Changes are committed and pushed to GitHub.
2. On the phone: `marathon update` (downloads the code, installs any new packages, restarts the server).
   Then close and reopen the app.
3. `marathon status` shows the installed version.

The phone follows one branch, `main` by default. To follow another (e.g. to try a feature branch):
`marathon update <branch>`; it is remembered for later updates. Switch back with `marathon update main`.
Your training log, settings and Garmin tokens are never touched by an update; save a backup first anyway
for big changes.

Settings and data live in `~/.marathon/` (private to Termux): `env` (random `APP_KEY`, allowed hosts),
`data/marathon.db`, `garmin_tokens/`. Use **Progress → Save backup** now and then; backups contain
training data only, never Garmin credentials.

**If Garmin login fails on the phone** (Garmin sometimes blocks logins that don't look like a browser,
and the browser-like `curl_cffi` package has no Android build): run
`GARMIN_TOKENS=./garmin_tokens python -m app.garmin_login` on a computer and copy the `garmin_tokens`
folder to `~/.marathon/garmin_tokens` on the phone.

### Security model

- Server bound to `127.0.0.1` only.
- A random `APP_KEY` is required on every request (stored as an httpOnly, SameSite cookie), so other apps
  on the phone can't use the API.
- `ALLOWED_HOSTS=127.0.0.1,localhost` blocks DNS-rebinding from websites; writes must be
  `application/json`, which other websites can't send without a CORS preflight that is never granted.
- The Garmin password is never stored; tokens are written owner-only.

## Run it locally (computer)

```bash
cd marathon_app
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
pytest
```

Open http://localhost:8000.

## Settings (environment variables)

| Variable | Purpose |
|---|---|
| `APP_KEY` | Required on every request when set (the Termux setup generates one). Open `/?key=<APP_KEY>` once; a cookie keeps you signed in. |
| `ALLOWED_HOSTS` | Comma-separated Host names to accept, e.g. `127.0.0.1,localhost`. |
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
