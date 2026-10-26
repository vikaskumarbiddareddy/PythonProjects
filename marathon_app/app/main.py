"""FastAPI server: JSON API for the phone UI plus the static web app itself.

The client sends its local date as ?today=YYYY-MM-DD so "today" always matches
the runner's phone, wherever the server is hosted.

If APP_KEY is set, every request needs it: open /?key=<APP_KEY> once and a
long-lived cookie keeps the phone signed in (works for home-screen apps too).
"""

import hmac
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, garmin, paces, progress

STATIC = Path(__file__).resolve().parent.parent / "static"
APP_KEY = os.environ.get("APP_KEY")
KEY_COOKIE = "marathon_key"


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    yield


app = FastAPI(title="Marathon Trainer", lifespan=lifespan)


@app.middleware("http")
async def require_key(request: Request, call_next):
    if not APP_KEY:
        return await call_next(request)
    given = request.query_params.get("key")
    if given and hmac.compare_digest(given, APP_KEY):
        response = RedirectResponse(request.url.path or "/")
        response.set_cookie(KEY_COOKIE, APP_KEY, max_age=400 * 86400, httponly=True, samesite="lax",
                            secure=request.url.scheme == "https")
        return response
    if hmac.compare_digest(request.cookies.get(KEY_COOKIE, ""), APP_KEY):
        return await call_next(request)
    return PlainTextResponse("Private app. Open the link with ?key=... once on this device.", status_code=401)


# --- helpers ----------------------------------------------------------------

def _today(today: str | None) -> date:
    return date.fromisoformat(today) if today else date.today()


def _all(conn) -> list[dict]:
    return [db.row_to_workout(r) for r in conn.execute("SELECT * FROM workouts ORDER BY date")]


def _tests(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM fitness ORDER BY date, id")]


def _fitness(conn, workouts, today):
    return progress.training_fitness(workouts, _tests(conn), today)


def _with_paces(w: dict, zones: dict, today: date) -> dict:
    """Attach human-readable pace ranges to each step for display."""
    def walk(steps):
        out = []
        for s in steps:
            s = dict(s)
            if s["type"] == "repeat":
                s["steps"] = walk(s["steps"])
            elif s.get("zone") in zones:
                fast, slow = zones[s["zone"]]
                s["pace"] = f"{paces.fmt_pace(fast)}–{paces.fmt_pace(slow)} /km"
                s["zone_name"] = paces.ZONE_NAMES[s["zone"]]
            out.append(s)
        return out

    w = dict(w)
    w["steps"] = walk(w["steps"])
    w["state"] = progress.day_state(w, today)
    return w


def _get(conn, day: str) -> dict:
    row = conn.execute("SELECT * FROM workouts WHERE date = ?", (day,)).fetchone()
    if not row:
        raise HTTPException(404, f"No workout on {day}")
    return db.row_to_workout(row)


def _week_number(conn, today: date) -> int:
    start = date.fromisoformat(db.get_setting(conn, "plan_start"))
    return max(1, min(26, (today - start).days // 7 + 1))


# --- read endpoints ---------------------------------------------------------

@app.get("/api/dashboard")
def dashboard(today: str | None = None):
    t = _today(today)
    with db.connect() as conn:
        workouts = _all(conn)
        fit = _fitness(conn, workouts, t)
        zones = paces.zone_paces(fit["vdot"])
        by_date = {w["date"]: w for w in workouts}
        today_w = by_date.get(t.isoformat())
        tomorrow_w = by_date.get((t + timedelta(days=1)).isoformat())
        race_day = date.fromisoformat(db.get_setting(conn, "race_day"))
        return {
            "today": t.isoformat(),
            "week": _week_number(conn, t),
            "days_to_race": (race_day - t).days,
            "workout": _with_paces(today_w, zones, t) if today_w else None,
            "tomorrow": _with_paces(tomorrow_w, zones, t) if tomorrow_w else None,
            "streaks": progress.streaks(workouts, t),
            "predicted_marathon": paces.fmt_time(fit["predicted_marathon_s"]),
            "garmin_configured": garmin.configured(),
        }


@app.get("/api/week")
def week(today: str | None = None, week: int | None = Query(None, ge=1, le=26)):
    t = _today(today)
    with db.connect() as conn:
        workouts = _all(conn)
        n = week or _week_number(conn, t)
        zones = paces.zone_paces(_fitness(conn, workouts, t)["vdot"])
        items = [_with_paces(w, zones, t) for w in workouts if w["week"] == n]
        return {
            "week": n,
            "phase": items[0]["phase"],
            "planned_km": round(sum(w["planned_km"] for w in items), 1),
            "done_km": round(sum(w["actual_km"] or (w["planned_km"] if w["status"] == "done" else 0)
                                 for w in items), 1),
            "completion": round(progress.week_completion(items), 2),
            "workouts": items,
        }


@app.get("/api/heatmap")
def heatmap(today: str | None = None):
    t = _today(today)
    with db.connect() as conn:
        workouts = _all(conn)
        return {"days": progress.heatmap(workouts, t), "streaks": progress.streaks(workouts, t)}


@app.get("/api/progress")
def progress_view(today: str | None = None):
    t = _today(today)
    with db.connect() as conn:
        workouts = _all(conn)
        fit = _fitness(conn, workouts, t)
        goal_s = db.get_setting(conn, "goal_time_s")
        goal_vdot = paces.vdot_for_goal(paces.MARATHON_KM, goal_s)
        start_vdot = _tests(conn)[0]["vdot"]
        shoes = []
        for s in conn.execute("SELECT * FROM shoes"):
            km = conn.execute(
                """SELECT COALESCE(SUM(COALESCE(actual_km, planned_km)), 0) FROM workouts
                   WHERE shoe = ? AND status IN ('done', 'partial')""", (s["name"],)).fetchone()[0]
            shoes.append({"name": s["name"], "km": round(s["start_km"] + km, 1), "retire_km": s["retire_km"]})
        return {
            "vdot": fit["vdot"],
            "measured_vdot": fit["measured_vdot"],
            "bonus": fit["bonus"],
            "next_bonus_in": fit["next_bonus_in"],
            "predicted_marathon": paces.fmt_time(fit["predicted_marathon_s"]),
            "predicted_half": paces.fmt_time(paces.predict_time_s(fit["vdot"], paces.HALF_KM)),
            "goal": paces.fmt_time(goal_s),
            "goal_vdot": round(goal_vdot, 1),
            "goal_progress": round(max(0.0, (fit["vdot"] - start_vdot) / (goal_vdot - start_vdot)), 3),
            "zones": [{"zone": z, "name": paces.ZONE_NAMES[z], "fast": paces.fmt_pace(f), "slow": paces.fmt_pace(s)}
                      for z, (f, s) in paces.zone_paces(fit["vdot"]).items()],
            "tests": [{**r, "time": paces.fmt_time(r["time_s"]), "vdot": round(r["vdot"], 1)} for r in _tests(conn)],
            "shoes": shoes,
        }


# --- write endpoints --------------------------------------------------------

class LogIn(BaseModel):
    status: str = Field(pattern="^(planned|done|partial|skipped)$")
    actual_km: float | None = Field(None, ge=0, le=100)
    actual_time: str | None = None  # h:mm:ss of the whole run
    test_time: str | None = None  # result of the time-trial portion only
    rpe: int | None = Field(None, ge=1, le=10)
    comment: str | None = None


@app.post("/api/workouts/{day}/log")
def log_workout(day: str, body: LogIn):
    with db.connect() as conn:
        w = _get(conn, day)
        if w["kind"] == "rest":
            raise HTTPException(400, "Rest days don't need logging")
        try:
            actual_s = paces.parse_time(body.actual_time) if body.actual_time else None
            test_s = paces.parse_time(body.test_time) if body.test_time else None
        except ValueError as e:
            raise HTTPException(400, str(e))
        conn.execute(
            """UPDATE workouts SET status = ?, actual_km = ?, actual_time_s = ?, rpe = ?, comment = ?
               WHERE date = ?""",
            (body.status, body.actual_km, actual_s, body.rpe, body.comment, day),
        )
        # Re-logging replaces this workout's earlier result rather than adding a second one.
        conn.execute("DELETE FROM fitness WHERE source = ?", (f"workout:{day}",))
        if test_s and w["test_distance_km"] and body.status == "done":
            conn.execute(
                "INSERT INTO fitness (date, distance_km, time_s, vdot, source) VALUES (?, ?, ?, ?, ?)",
                (day, w["test_distance_km"], test_s, paces.vdot_from_race(w["test_distance_km"], test_s),
                 f"workout:{day}"),
            )
    return {"ok": True}


class FitnessIn(BaseModel):
    date: str
    distance_km: float = Field(gt=0, le=50)
    time: str


@app.post("/api/fitness")
def add_fitness(body: FitnessIn):
    try:
        time_s = paces.parse_time(body.time)
        date.fromisoformat(body.date)
    except ValueError as e:
        raise HTTPException(400, str(e))
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO fitness (date, distance_km, time_s, vdot, source) VALUES (?, ?, ?, ?, 'manual')",
            (body.date, body.distance_km, time_s, paces.vdot_from_race(body.distance_km, time_s)),
        )
    return {"ok": True}


class PushIn(BaseModel):
    date: str | None = None
    week: int | None = Field(None, ge=1, le=26)


@app.post("/api/garmin/push")
def garmin_push(body: PushIn, today: str | None = None):
    t = _today(today)
    with db.connect() as conn:
        workouts = _all(conn)
        vdot = _fitness(conn, workouts, t)["vdot"]
        if body.date:
            targets = [_get(conn, body.date)]
        elif body.week:
            targets = [w for w in workouts if w["week"] == body.week]
        else:
            raise HTTPException(400, "Give a date or a week")
        targets = [w for w in targets if w["kind"] != "rest" and date.fromisoformat(w["date"]) >= t]
        if not targets:
            raise HTTPException(400, "Nothing upcoming to send")
        try:
            api = garmin.login()
            pushed = []
            for w in targets:
                wid = garmin.push(api, w, vdot)
                conn.execute("UPDATE workouts SET garmin_workout_id = ? WHERE date = ?", (wid, w["date"]))
                conn.commit()
                pushed.append(w["date"])
        except garmin.GarminError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(502, f"Garmin Connect error: {e}")
    return {"pushed": pushed}


SYNC_EVERY_S = 10 * 60


@app.post("/api/garmin/sync")
def garmin_sync(today: str | None = None, force: bool = False):
    """Pull finished runs from Garmin and mark the matching workouts done."""
    t = _today(today)
    now = datetime.now(timezone.utc)
    with db.connect() as conn:
        last = db.get_setting(conn, "last_garmin_sync")
        if not force and last and (now - datetime.fromisoformat(last)).total_seconds() < SYNC_EVERY_S:
            return {"skipped": True, "updated": [], "unplanned": []}
        start = db.get_setting(conn, "plan_start")
        try:
            runs = garmin.fetch_runs(garmin.login(), start, t.isoformat())
        except garmin.GarminError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(502, f"Garmin Connect error: {e}")
        updates, unplanned = garmin.match_runs(_all(conn), runs)
        for u in updates:
            conn.execute(
                """UPDATE workouts SET status = :status, actual_km = :actual_km, actual_time_s = :actual_time_s,
                   avg_hr = :avg_hr, garmin_activity_id = :garmin_activity_id WHERE date = :date""", u)
        db.set_setting(conn, "last_garmin_sync", now.isoformat())
    return {"skipped": False, "updated": [u["date"] for u in updates], "unplanned": unplanned}


# --- weight -----------------------------------------------------------------

class WeightIn(BaseModel):
    date: str
    kg: float = Field(gt=20, lt=300)
    note: str | None = None
    to_garmin: bool = False


@app.get("/api/weight")
def weights():
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM weights ORDER BY date")]
    return {
        "entries": rows,
        "latest": rows[-1] if rows else None,
        "change_kg": round(rows[-1]["kg"] - rows[0]["kg"], 1) if len(rows) > 1 else None,
    }


@app.post("/api/weight")
def add_weight(body: WeightIn):
    try:
        date.fromisoformat(body.date)
    except ValueError as e:
        raise HTTPException(400, str(e))
    with db.connect() as conn:
        # One weigh-in per day: a second entry on the same day replaces the first.
        conn.execute(
            """INSERT INTO weights (date, kg, note) VALUES (?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET kg = excluded.kg, note = excluded.note""",
            (body.date, round(body.kg, 1), body.note),
        )
    garmin_saved = None
    if body.to_garmin and garmin.configured():
        try:
            garmin.login().add_weigh_in(round(body.kg, 1), unitKey="kg", timestamp=f"{body.date}T08:00:00")
            garmin_saved = True
        except Exception:
            garmin_saved = False  # saved locally either way
    return {"ok": True, "garmin_saved": garmin_saved}


@app.delete("/api/weight/{entry_id}")
def delete_weight(entry_id: int):
    with db.connect() as conn:
        conn.execute("DELETE FROM weights WHERE id = ?", (entry_id,))
    return {"ok": True}


# --- static web app ---------------------------------------------------------

app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/sw.js")
def service_worker():
    # Served from the root so its scope covers the whole app.
    return FileResponse(STATIC / "sw.js", media_type="application/javascript")
