"""Streaks, heatmap states, weekly completion and adaptive training fitness."""

from datetime import date, timedelta
from itertools import groupby

from . import paces

KEPT = {"done", "partial", "rest"}

# Consistency bonus: every BONUS_BLOCK consecutive weeks at >= BONUS_THRESHOLD
# completion nudges training VDOT up by BONUS_STEP, capped at BONUS_MAX.
# A new test result replaces the bonus with real measured fitness.
BONUS_BLOCK = 3
BONUS_THRESHOLD = 0.9
BONUS_STEP = 0.5
BONUS_MAX = 1.5


def day_state(w: dict, today: date) -> str:
    d = date.fromisoformat(w["date"])
    if d > today:
        return "future"
    if w["kind"] == "rest":
        return "rest"
    if w["status"] in ("done", "partial"):
        return w["status"]
    if w["status"] == "skipped" or d < today:
        return "missed"
    return "today"


def week_completion(week_workouts: list[dict]) -> float:
    runs = [w for w in week_workouts if w["kind"] != "rest"]
    if not runs:
        return 1.0
    score = sum(1 if w["status"] == "done" else 0.5 if w["status"] == "partial" else 0 for w in runs)
    return score / len(runs)


def streaks(workouts: list[dict], today: date) -> dict:
    """workouts sorted by date. Today's pending run never breaks a streak."""
    states = [(w, day_state(w, today)) for w in workouts]
    past = [(w, s) for w, s in states if s not in ("future", "today")]

    current = 0
    for _, s in reversed(past):
        if s not in KEPT:
            break
        current += 1

    longest = run_len = 0
    for _, s in past:
        run_len = run_len + 1 if s in KEPT else 0
        longest = max(longest, run_len)

    # Week streak: consecutive fully-completed weeks, newest first.
    # The current week counts once every run in it is done.
    week_streak = 0
    for week, items in sorted(_by_week(workouts).items(), reverse=True):
        week_states = [day_state(w, today) for w in items]
        finished = all(s != "future" for s in week_states) or week_completion(items) == 1
        if not finished:
            continue
        if all(s in ("done", "rest") for s in week_states):
            week_streak += 1
        else:
            break

    runs_past = [s for w, s in past if w["kind"] != "rest"]
    return {
        "current_days": current,
        "longest_days": longest,
        "perfect_weeks": week_streak,
        "runs_done": sum(s in ("done", "partial") for s in runs_past),
        "runs_due": len(runs_past),
    }


def heatmap(workouts: list[dict], today: date) -> list[dict]:
    return [
        {"date": w["date"], "week": w["week"], "state": day_state(w, today), "title": w["title"],
         "km": w["actual_km"] if w["actual_km"] is not None else w["planned_km"]}
        for w in workouts
    ]


def _by_week(workouts):
    return {k: list(g) for k, g in groupby(sorted(workouts, key=lambda w: w["date"]), key=lambda w: w["week"])}


def training_fitness(workouts: list[dict], tests: list[dict], today: date) -> dict:
    """Latest measured VDOT plus a consistency bonus earned since that test."""
    latest = max(tests, key=lambda t: (t["date"], t["id"]))
    test_day = date.fromisoformat(latest["date"])
    this_monday = today - timedelta(days=today.weekday())

    bonus, consecutive = 0.0, 0
    for week, items in sorted(_by_week(workouts).items()):
        monday = date.fromisoformat(items[0]["date"])
        if monday <= test_day or monday >= this_monday:
            continue  # only full weeks after the test, excluding the current week
        if week_completion(items) >= BONUS_THRESHOLD:
            consecutive += 1
            if consecutive % BONUS_BLOCK == 0:
                bonus = min(BONUS_MAX, bonus + BONUS_STEP)
        else:
            consecutive = 0

    vdot = latest["vdot"] + bonus
    return {
        "measured_vdot": round(latest["vdot"], 1),
        "bonus": bonus,
        "vdot": round(vdot, 1),
        "latest_test": latest,
        "consistent_weeks": consecutive,
        "next_bonus_in": None if bonus >= BONUS_MAX else BONUS_BLOCK - consecutive % BONUS_BLOCK,
        "predicted_marathon_s": paces.predict_time_s(vdot, paces.MARATHON_KM),
    }
