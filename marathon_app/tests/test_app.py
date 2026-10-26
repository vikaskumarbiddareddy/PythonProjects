import os
from collections import defaultdict
from datetime import date, timedelta

import pytest

from app import paces, progress
from app.plan import MAGIC_SPEED, PEGASUS, WEEKS, generate_plan

START, RACE = date(2026, 10, 26), date(2027, 4, 25)


# --- paces ------------------------------------------------------------------

def test_vdot_matches_daniels_tables():
    # Daniels: VDOT 30 -> half 2:21:04, marathon 4:49:17
    assert abs(paces.predict_time_s(30, paces.HALF_KM) - paces.parse_time("2:21:04")) < 60
    assert abs(paces.predict_time_s(30, paces.MARATHON_KM) - paces.parse_time("4:49:17")) < 120


def test_current_fitness_and_goal():
    vdot = paces.vdot_from_race(paces.HALF_KM, paces.parse_time("2:30:00"))
    assert 27.5 < vdot < 28.5
    assert 44 < paces.vdot_for_goal(paces.MARATHON_KM, paces.parse_time("3:30:00")) < 45.5


def test_zones_are_ordered_fastest_last():
    z = paces.zone_paces(28)
    assert z["E"][1] > z["M"][0] > z["T"][0] > z["I"][0] > z["R"][0]
    for fast, slow in z.values():
        assert fast < slow


def test_parse_time():
    assert paces.parse_time("2:30:00") == 9000
    assert paces.parse_time("28:30") == 1710
    with pytest.raises(ValueError):
        paces.parse_time("90")


# --- plan -------------------------------------------------------------------

@pytest.fixture(scope="module")
def plan():
    return generate_plan(START, RACE)


def test_plan_covers_every_day_to_race(plan):
    assert len(plan) == 26 * 7
    assert plan[0].date == START and plan[-1].date == RACE
    assert plan[-1].kind == "race"


def test_four_runs_per_week_long_run_saturday(plan):
    by_week = defaultdict(list)
    for w in plan:
        by_week[w.week].append(w)
    for week, items in by_week.items():
        assert sum(w.kind != "rest" for w in items) == 4, week
        assert [w.date.weekday() for w in items if w.kind == "rest"] == [0, 2, 4]
        if week not in (14, 26):
            assert items[5].kind == "long"


def test_weekly_volume_close_to_target(plan):
    totals = defaultdict(float)
    for w in plan:
        totals[w.week] += w.planned_km
    for week, (target, _) in enumerate(WEEKS[:-1], start=1):  # race week includes the marathon
        assert abs(totals[week] - target) <= 4, (week, totals[week], target)


def test_shoes(plan):
    for w in plan:
        if w.kind == "rest":
            assert w.shoe is None
        elif w.kind in ("test", "race"):
            assert w.shoe == MAGIC_SPEED
        elif w.kind in ("recovery",) or w.title.startswith("Easy"):
            assert w.shoe == PEGASUS


def test_peak_long_run_and_tests(plan):
    assert max(w.planned_km for w in plan if w.kind == "long") == 32
    tests = [(w.week, w.test_distance_km) for w in plan if w.kind == "test"]
    assert tests == [(4, 5.0), (12, 10.0), (14, 21.0975), (20, 10.0)]


# --- streaks ----------------------------------------------------------------

def _rows(statuses: list[str], start=START):
    """Build workout dicts from a compact list: 'r' rest, 'd' done, 'p' partial, 's' skipped, '.' planned."""
    mapping = {"r": ("rest", "planned"), "d": ("easy", "done"), "p": ("easy", "partial"),
               "s": ("easy", "skipped"), ".": ("easy", "planned")}
    rows = []
    for i, c in enumerate(statuses):
        kind, status = mapping[c]
        rows.append({"date": (start + timedelta(days=i)).isoformat(), "week": i // 7 + 1, "kind": kind,
                     "status": status, "title": "x", "planned_km": 5, "actual_km": None})
    return rows


def test_streak_counts_rest_and_ignores_pending_today():
    rows = _rows("rdrdrd.")
    s = progress.streaks(rows, START + timedelta(days=6))
    assert s["current_days"] == 6
    assert s["runs_done"] == 3 and s["runs_due"] == 3


def test_missed_run_breaks_streak():
    rows = _rows("rdr.rdd")
    s = progress.streaks(rows, START + timedelta(days=6))
    assert s["current_days"] == 3
    assert s["longest_days"] == 3


def test_perfect_weeks():
    rows = _rows("rdrdrdd" + "rdrprdd" + "rdrdrdd" + "rd.....")
    s = progress.streaks(rows, START + timedelta(days=22))
    assert s["perfect_weeks"] == 1  # week 3 only; week 2 had a partial, week 4 in progress


# --- adaptive fitness -------------------------------------------------------

def test_consistency_bonus_and_reset_by_test():
    rows = _rows("rdrdrdd" * 7)
    tests = [{"id": 1, "date": START.isoformat(), "vdot": 28.0, "distance_km": 21.1, "time_s": 9000}]
    today = START + timedelta(weeks=7)
    fit = progress.training_fitness(rows, tests, today)
    # Week 1 starts on the test day so it is excluded; weeks 2-7 complete -> two bonus blocks.
    assert fit["bonus"] == 1.0 and fit["vdot"] == 29.0

    tests.append({"id": 2, "date": (START + timedelta(weeks=6)).isoformat(), "vdot": 30.0,
                  "distance_km": 10, "time_s": 3500})
    fit = progress.training_fitness(rows, tests, today)
    assert fit["bonus"] == 0 and fit["vdot"] == 30.0


def test_missed_week_resets_consecutive_count():
    rows = _rows("rdrdrdd" + "rdrdrdd" + "rdrdrdd" + "rsrsrdd" + "rdrdrdd")
    tests = [{"id": 1, "date": (START - timedelta(days=1)).isoformat(), "vdot": 28.0}]
    fit = progress.training_fitness(rows, tests, START + timedelta(weeks=5))
    assert fit["bonus"] == 0.5 and fit["consistent_weeks"] == 1


# --- garmin payload ---------------------------------------------------------

def test_garmin_workout_payload(plan):
    from app.garmin import build_workout

    w = next(x for x in plan if x.week == 5 and x.kind == "quality")
    payload = build_workout({"week": w.week, "title": w.title, "steps": w.steps, "shoe": w.shoe,
                             "notes": w.notes, "planned_km": w.planned_km}, 28.0).to_dict()
    steps = payload["workoutSegments"][0]["workoutSteps"]
    assert [s["stepType"]["stepTypeKey"] for s in steps] == ["warmup", "repeat", "cooldown"]
    rep = steps[1]
    assert rep["numberOfIterations"] == 3
    interval = rep["workoutSteps"][0]
    assert interval["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    fast, slow = paces.zone_paces(28.0)["T"]
    assert interval["targetValueOne"] == pytest.approx(1000 / slow)
    assert interval["targetValueTwo"] == pytest.approx(1000 / fast)
    assert [s["stepOrder"] for s in (steps[0], rep, *rep["workoutSteps"], steps[2])] == [1, 2, 3, 4, 5]
    assert steps[0]["targetType"]["workoutTargetTypeKey"] == "no.target"


# --- API --------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_api_flow(client):
    t = "today=2026-10-27"
    d = client.get(f"/api/dashboard?{t}").json()
    assert d["week"] == 1 and d["workout"]["title"] == "Easy + strides"
    assert d["workout"]["steps"][0]["pace"].endswith("/km")

    r = client.post(f"/api/workouts/2026-10-27/log?{t}", json={"status": "done", "actual_km": 6.4})
    assert r.status_code == 200
    s = client.get(f"/api/heatmap?{t}").json()["streaks"]
    assert s["current_days"] == 2 and s["runs_done"] == 1

    assert client.get(f"/api/week?{t}").json()["done_km"] == 6.4
    assert client.post(f"/api/workouts/2026-10-26/log?{t}", json={"status": "done"}).status_code == 400


def test_test_result_updates_paces(client):
    t = "today=2026-11-17"
    before = client.get(f"/api/progress?{t}").json()
    r = client.post(f"/api/workouts/2026-11-17/log?{t}", json={"status": "done", "test_time": "30:00"})
    assert r.status_code == 200
    after = client.get(f"/api/progress?{t}").json()
    assert after["measured_vdot"] > before["measured_vdot"]
    assert len(after["tests"]) == 2
    # re-logging replaces rather than duplicates the result
    client.post(f"/api/workouts/2026-11-17/log?{t}", json={"status": "done", "test_time": "29:30"})
    assert len(client.get(f"/api/progress?{t}").json()["tests"]) == 2


def test_garmin_not_configured(client, monkeypatch):
    for k in ("GARMIN_EMAIL", "GARMIN_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    from app import garmin
    monkeypatch.setattr(garmin, "TOKEN_DIR", "/nonexistent")
    r = client.post("/api/garmin/push?today=2026-10-27", json={"date": "2026-10-27"})
    assert r.status_code == 400 and "not set up" in r.json()["detail"]


def test_app_key_required(client, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "APP_KEY", "s3cret")
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/?key=wrong").status_code == 401
    r = client.get("/?key=s3cret", follow_redirects=False)
    assert r.status_code == 307 and "marathon_key" in r.headers["set-cookie"]
    client.cookies.set("marathon_key", "s3cret")
    assert client.get("/api/dashboard?today=2026-10-27").status_code == 200
