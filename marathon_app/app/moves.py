"""Moving workouts within their week.

Every plan day is one row keyed by date, so a move exchanges the *content* of two
rows (what is planned) and leaves the dates alone:

- swap:    the two days trade content (a run and a rest day, or two runs).
- replace: the workout takes over a day that had another run; that run is dropped
           and the workout's old day becomes rest, so the week's total goes down.

Before a row first changes, its content is saved in `original`, which is what
"undo this week's moves" restores. Moves stay inside one week, never go into the
past (except accepting a run Garmin already found), and never touch a race or a
day that has been logged.
"""

import json
from datetime import date, timedelta

CONTENT = ("kind", "title", "steps", "shoe", "planned_km", "notes", "test_distance_km",
           "garmin_workout_id", "replaced")
HARD = {"quality", "test", "long", "race"}
REST_CONTENT = {"kind": "rest", "title": "Rest day", "steps": "[]", "shoe": None, "planned_km": 0.0,
                "test_distance_km": None, "garmin_workout_id": None, "replaced": None}


class MoveError(ValueError):
    pass


def _row(conn, day: str) -> dict:
    row = conn.execute("SELECT * FROM workouts WHERE date = ?", (day,)).fetchone()
    if not row:
        raise MoveError(f"No plan day on {day}")
    return dict(row)


def _logged(r: dict) -> bool:
    return r["status"] != "planned" or r["actual_km"] is not None or r["garmin_activity_id"] is not None


def _dow(day: str) -> str:
    return f"{date.fromisoformat(day):%a %-d}"


def _check_source(r: dict) -> None:
    if r["kind"] == "rest":
        raise MoveError("Rest days can't be moved; move a workout onto them instead")
    if r["kind"] == "race":
        raise MoveError("Race day is fixed")
    if _logged(r):
        raise MoveError("This workout is already logged")


def _save_original(conn, r: dict) -> None:
    if r["original"] is None:
        conn.execute("UPDATE workouts SET original = ? WHERE date = ?",
                     (json.dumps({k: r[k] for k in CONTENT}), r["date"]))


def _write(conn, day: str, content: dict, moved_from: str | None, moved_to: str | None) -> None:
    sets = ", ".join(f"{k} = ?" for k in CONTENT)
    conn.execute(f"UPDATE workouts SET {sets}, moved_from = ?, moved_to = ? WHERE date = ?",
                 [content[k] for k in CONTENT] + [moved_from, moved_to, day])


def _origin(r: dict, now_on: str) -> str | None:
    """Where this content was originally planned, or None if that is where it now sits."""
    home = r["moved_from"] or r["date"]
    return None if home == now_on else home


def _warning(conn, day: str) -> str | None:
    """Warn when the hard workout on `day` now sits next to another hard day."""
    r = _row(conn, day)
    if r["kind"] not in HARD:
        return None
    d = date.fromisoformat(day)
    for other in (d - timedelta(days=1), d + timedelta(days=1)):
        n = conn.execute("SELECT kind, title FROM workouts WHERE date = ?", (other.isoformat(),)).fetchone()
        if n and n["kind"] in HARD:
            first, second = sorted([(d, r["title"]), (other, n["title"])])
            return (f"Hard days back to back: {first[1]} ({first[0]:%a}) and {second[1]} ({second[0]:%a}). "
                    "Keep the next run very easy.")
    return None


def options(conn, src_day: str, today: date) -> list[dict]:
    """Days this workout can move to: the rest of its week from today, minus races and logged days."""
    src = _row(conn, src_day)
    _check_source(src)
    rows = conn.execute("SELECT * FROM workouts WHERE week = ? ORDER BY date", (src["week"],)).fetchall()
    out = []
    for r in map(dict, rows):
        if r["date"] == src_day or date.fromisoformat(r["date"]) < today or r["kind"] == "race" or _logged(r):
            continue
        out.append({"date": r["date"], "kind": r["kind"], "title": r["title"],
                    "modes": ["swap"] if r["kind"] == "rest" else ["replace", "swap"]})
    return out


def move(conn, src_day: str, dst_day: str, mode: str, today: date, allow_past: bool = False) -> dict:
    """Move the workout on src_day to dst_day. Returns {"warning", "garmin"} where garmin lists
    the follow-up calendar actions: ("push", date) to re-send, ("delete", workout_id) to remove."""
    src, dst = _row(conn, src_day), _row(conn, dst_day)
    _check_source(src)
    if src["week"] != dst["week"]:
        raise MoveError("Workouts can only move within their week")
    if src_day == dst_day:
        raise MoveError("Pick a different day")
    if date.fromisoformat(dst_day) < today and not allow_past:
        raise MoveError("Can't move a workout into the past")
    if dst["kind"] == "race":
        raise MoveError("Race day is fixed")
    if _logged(dst):
        raise MoveError("That day is already logged")
    if dst["kind"] == "rest":
        mode = "swap"
    if mode not in ("swap", "replace"):
        raise MoveError("Choose replace or swap")

    _save_original(conn, src)
    _save_original(conn, dst)
    actions = []
    if src["garmin_workout_id"]:
        actions.append(("push", dst_day))
    src_content = {k: src[k] for k in CONTENT}
    if mode == "swap":
        dst_content = {k: dst[k] for k in CONTENT}
        if dst["kind"] == "rest":
            dst_content["notes"] = f"Workout moved to {_dow(dst_day)}."
            _write(conn, src_day, dst_content, None, dst_day)
        else:
            _write(conn, src_day, dst_content, _origin(dst, src_day), None)
            if dst["garmin_workout_id"]:
                actions.append(("push", src_day))
        _write(conn, dst_day, src_content, _origin(src, dst_day), None)
    else:
        if dst["garmin_workout_id"]:
            actions.append(("delete", dst["garmin_workout_id"]))
        src_content["replaced"] = dst["title"]
        _write(conn, dst_day, src_content, _origin(src, dst_day), None)
        _write(conn, src_day, {**REST_CONTENT, "notes": f"Workout moved to {_dow(dst_day)}."}, None, dst_day)
    return {"warning": _warning(conn, dst_day) or (_warning(conn, src_day) if mode == "swap" else None),
            "garmin": actions}


def undo_week(conn, week: int) -> dict:
    """Restore every moved day of a week to its original plan, if none of them is logged yet."""
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM workouts WHERE week = ? AND original IS NOT NULL ORDER BY date", (week,))]
    if not rows:
        raise MoveError("Nothing was moved this week")
    if any(_logged(r) for r in rows):
        raise MoveError("A moved workout is already logged, so the moves can't be undone")
    actions = []
    for r in rows:
        content = json.loads(r["original"])
        sets = ", ".join(f"{k} = ?" for k in CONTENT)
        conn.execute(f"UPDATE workouts SET {sets}, moved_from = NULL, moved_to = NULL, original = NULL "
                     "WHERE date = ?", [content[k] for k in CONTENT] + [r["date"]])
        if content["garmin_workout_id"]:
            actions.append(("push", r["date"]))
    return {"garmin": actions}


def pending_missed(conn, today: date) -> dict | None:
    """The shortcut offered on today's card after a missed run.

    Offered when the missed run is the last one before today in the same week, with only
    rest days in between ("until the next run"), and today is a rest day (swap) or, for a
    missed long run, today's run gives way to it (replace).
    """
    t = conn.execute("SELECT * FROM workouts WHERE date = ?", (today.isoformat(),)).fetchone()
    if not t or _logged(dict(t)) or t["kind"] == "race":
        return None
    t = dict(t)
    for r in conn.execute("SELECT * FROM workouts WHERE week = ? AND date < ? ORDER BY date DESC",
                          (t["week"], t["date"])):
        r = dict(r)
        if r["kind"] == "rest":
            continue
        if _logged(r) or r["kind"] == "race":
            return None
        if t["kind"] == "rest":
            mode = "swap"
        elif r["kind"] == "long":
            mode = "replace"
        else:
            return None
        return {"date": r["date"], "title": r["title"], "planned_km": r["planned_km"],
                "mode": mode, "today_title": t["title"]}
    return None
