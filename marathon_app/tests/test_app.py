import os
from collections import defaultdict
from datetime import date, timedelta

import pytest

from app import paces, progress
from app.plan import MAGIC_SPEED, PEGASUS, WEEKS, generate_plan

START, RACE = date(2026, 10, 26), date(2027, 4, 25)
JSON = {"content-type": "application/json"}  # the server requires it on every write


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


def test_first_run_turns_earlier_runs_into_rest():
    plan = generate_plan(START, RACE, first_run=date(2026, 10, 29))
    week1 = [w for w in plan if w.week == 1]
    assert [w.kind for w in week1] == ["rest", "rest", "rest", "easy", "rest", "long", "recovery"]
    assert week1[1].steps == [] and week1[1].shoe is None
    assert sum(w.kind != "rest" for w in plan if w.week == 2) == 4


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
                             "notes": w.notes, "planned_km": w.planned_km}, paces.zone_paces(28.0)).to_dict()
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
    assert client.get("/api/dashboard?today=2026-10-27").json()["workout"]["kind"] == "rest"  # starts Thursday
    t = "today=2026-10-29"
    d = client.get(f"/api/dashboard?{t}").json()
    assert d["week"] == 1 and d["workout"]["title"] == "Easy 6 km + strides"
    assert d["workout"]["steps"][0]["pace"].endswith("/km")

    r = client.post(f"/api/workouts/2026-10-29/log?{t}", json={"status": "done", "actual_km": 6.4})
    assert r.status_code == 200
    s = client.get(f"/api/heatmap?{t}").json()["streaks"]
    assert s["current_days"] == 4 and s["runs_done"] == 1

    assert client.get(f"/api/week?{t}").json()["done_km"] == 6.4
    assert client.post(f"/api/workouts/2026-10-27/log?{t}", json={"status": "done"}).status_code == 400


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
    r = client.post("/api/garmin/push?today=2026-10-29", json={"date": "2026-10-29"})
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


# --- Garmin -> app sync -----------------------------------------------------

def test_fetch_runs_merges_days_and_filters_type():
    from app.garmin import fetch_runs

    class FakeApi:
        def get_activities_by_date(self, start, end):
            return [
                {"activityId": 1, "startTimeLocal": "2026-10-29 07:00:00", "distance": 4000, "duration": 1800,
                 "averageHR": 140, "activityType": {"typeKey": "running"}},
                {"activityId": 2, "startTimeLocal": "2026-10-29 18:00:00", "distance": 2000, "duration": 900,
                 "averageHR": 155, "activityType": {"typeKey": "treadmill_running"}},
                {"activityId": 3, "startTimeLocal": "2026-10-30 07:00:00", "distance": 20000, "duration": 3600,
                 "activityType": {"typeKey": "cycling"}},
            ]

    runs = fetch_runs(FakeApi(), "2026-10-26", "2026-10-31")
    assert list(runs) == ["2026-10-29"]
    assert runs["2026-10-29"] == {"km": 6.0, "time_s": 2700, "ids": ["1", "2"], "avg_hr": 145}


def test_match_runs_rules():
    from app.garmin import match_runs

    def w(day, kind="easy", status="planned", planned=6.0, gid=None):
        return {"date": day, "kind": kind, "status": status, "planned_km": planned, "garmin_activity_id": gid}

    run = lambda km: {"km": km, "time_s": 2400, "ids": ["9"], "avg_hr": 150}
    workouts = [w("d1"), w("d2"), w("d3", kind="rest"), w("d4", status="done"), w("d5", status="done", gid="8"),
                w("d6", status="skipped"), w("d7", kind="test", planned=9)]
    runs = {"d1": run(6.1), "d2": run(4.0), "d3": run(5), "d4": run(6), "d5": run(6.2), "d6": run(6), "d7": run(3)}
    updates, unplanned = match_runs(workouts, runs)
    result = {u["date"]: u["status"] for u in updates}
    assert result == {"d1": "done", "d2": "partial", "d5": "done", "d6": "done", "d7": "done"}
    assert unplanned == ["d3"]  # run on a rest day; d4 was logged by hand and is left alone


def test_sync_endpoint(client, monkeypatch):
    from app import garmin
    monkeypatch.setattr(garmin, "login", lambda: object())
    monkeypatch.setattr(garmin, "fetch_runs", lambda api, s, e: {
        "2026-10-29": {"km": 6.3, "time_s": 2900, "ids": ["42"], "avg_hr": 147}})
    r = client.post("/api/garmin/sync?today=2026-10-30", headers=JSON).json()
    assert r["updated"] == ["2026-10-29"]
    w = client.get("/api/week?today=2026-10-30").json()["workouts"][3]
    assert (w["status"], w["actual_km"], w["avg_hr"], w["garmin_activity_id"]) == ("done", 6.3, 147, "42")
    assert client.post("/api/garmin/sync?today=2026-10-30", headers=JSON).json()["skipped"]  # throttled
    assert not client.post("/api/garmin/sync?today=2026-10-30&force=true", headers=JSON).json()["skipped"]


# --- weight -----------------------------------------------------------------

def test_weight_entries(client):
    assert client.get("/api/weight").json() == {"entries": [], "latest": None, "change_kg": None}
    client.post("/api/weight", json={"date": "2026-10-26", "kg": 78.4})
    client.post("/api/weight", json={"date": "2026-11-02", "kg": 77.9})
    client.post("/api/weight", json={"date": "2026-11-02", "kg": 77.6})  # same day replaces
    d = client.get("/api/weight").json()
    assert [e["kg"] for e in d["entries"]] == [78.4, 77.6]
    assert d["change_kg"] == -0.8 and d["latest"]["date"] == "2026-11-02"
    assert client.post("/api/weight", json={"date": "2026-11-03", "kg": 5}).status_code == 422
    client.delete(f"/api/weight/{d['entries'][0]['id']}", headers=JSON)
    assert len(client.get("/api/weight").json()["entries"]) == 1


def test_migration_adds_columns(tmp_path, monkeypatch):
    import sqlite3
    from app import db
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE workouts (id INTEGER PRIMARY KEY, date TEXT UNIQUE NOT NULL, week INTEGER NOT NULL, "
                "phase TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, steps TEXT NOT NULL, shoe TEXT, "
                "planned_km REAL NOT NULL, notes TEXT NOT NULL DEFAULT '', test_distance_km REAL, "
                "status TEXT NOT NULL DEFAULT 'planned', actual_km REAL, actual_time_s INTEGER, rpe INTEGER, "
                "comment TEXT, garmin_workout_id TEXT)")
    old.commit(); old.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    with db.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(workouts)")}
    assert {"garmin_activity_id", "avg_hr"} <= cols


# --- security & backup ------------------------------------------------------

def test_writes_must_be_json(client):
    r = client.post("/api/weight", data={"date": "2026-11-01", "kg": "70"})  # what a cross-site form sends
    assert r.status_code == 415
    assert client.delete("/api/weight/1").status_code == 415


def test_backup_round_trip(client):
    t = "today=2026-10-29"
    client.post(f"/api/workouts/2026-10-29/log?{t}", json={"status": "done", "actual_km": 6.1})
    client.post("/api/weight", json={"date": "2026-10-29", "kg": 78.0})
    r = client.get(f"/api/backup?{t}")
    assert "marathon-backup-2026-10-29.json" in r.headers["content-disposition"]
    backup = r.json()
    assert set(backup["tables"]) == {"settings", "workouts", "fitness", "weights", "shoes"}
    assert not any(w in str(backup).lower() for w in ("password", "token", "oauth"))

    client.post(f"/api/workouts/2026-10-29/log?{t}", json={"status": "skipped"})
    client.delete(f"/api/weight/{backup['tables']['weights'][0]['id']}", headers=JSON)
    assert client.post("/api/restore", json=backup).json() == {"ok": True}
    assert client.get(f"/api/week?{t}").json()["workouts"][3]["status"] == "done"
    assert client.get("/api/weight").json()["latest"]["kg"] == 78.0

    assert client.post("/api/restore", json={"app": "other"}).status_code == 400
    assert client.get(f"/api/week?{t}").json()["workouts"][3]["status"] == "done"  # untouched


def test_host_check(tmp_path, monkeypatch):
    import importlib
    from fastapi.testclient import TestClient
    from app import db, main
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "h.db")
    monkeypatch.setenv("ALLOWED_HOSTS", "127.0.0.1,localhost")
    fresh = importlib.reload(main)
    try:
        with TestClient(fresh.app, base_url="http://127.0.0.1:8765") as c:
            assert c.get("/api/weight").status_code == 200
        with TestClient(fresh.app, base_url="http://evil.example") as c:
            assert c.get("/api/weight").status_code == 400
    finally:
        monkeypatch.delenv("ALLOWED_HOSTS")
        importlib.reload(main)


# --- Dec 6 half-marathon block ----------------------------------------------

HALF = date(2026, 12, 6)


@pytest.fixture(scope="module")
def half_plan():
    return generate_plan(START, RACE, date(2026, 10, 29), HALF)


def test_half_block_structure(half_plan):
    from app.plan import HALF_BLOCK_KM
    by_week = defaultdict(list)
    for w in half_plan:
        by_week[w.week].append(w)
    for week, km in HALF_BLOCK_KM.items():
        items = by_week[week]
        assert sum(w.kind != "rest" for w in items) == 4
        assert [w.date.weekday() for w in items if w.kind == "rest"] == [0, 2, 4]
        assert abs(sum(w.planned_km for w in items) - km) <= 1, week
    race = next(w for w in half_plan if w.date == HALF)
    assert (race.kind, race.test_distance_km, race.shoe) == ("race", 21.0975, MAGIC_SPEED)
    assert race.steps[0]["zone"] == "H"
    assert max(w.planned_km for w in by_week[4] + by_week[5] + by_week[6] if w.kind == "long") == 18
    assert all(w.kind in ("rest", "easy", "long", "recovery") for w in by_week[7])  # recovery week
    assert by_week[4][1].kind == "test" and "race goal" in by_week[4][1].notes
    # Weeks outside the block are the normal marathon plan.
    normal = generate_plan(START, RACE, date(2026, 10, 29))
    assert [(w.date, w.title) for w in half_plan if w.week in (1, 2) or w.week >= 8] == \
           [(w.date, w.title) for w in normal if w.week in (1, 2) or w.week >= 8]


def test_half_race_must_be_week_6_sunday():
    with pytest.raises(ValueError):
        generate_plan(START, RACE, half_race=date(2026, 12, 5))


def test_half_goal_zone_and_hr():
    z = paces.zone_paces(30.3, paces.parse_time("2:10:00"))
    assert list(z) == ["E", "M", "H", "T", "I", "R"]
    assert paces.fmt_pace(sum(z["H"]) / 2) == "6:10"
    assert "H" not in paces.zone_paces(30.3)
    assert paces.max_hr_for_age(36) == 183 and paces.easy_hr_ceiling(183) == 143


def test_garmin_targets_half_pace(half_plan):
    from app.garmin import build_workout
    w = next(x for x in half_plan if x.title.startswith("Half pace 3 x 2 km"))
    zones = paces.zone_paces(30.3, paces.parse_time("2:10:00"))
    payload = build_workout({"week": w.week, "title": w.title, "steps": w.steps, "shoe": w.shoe,
                             "notes": w.notes, "planned_km": w.planned_km}, zones).to_dict()
    interval = payload["workoutSegments"][0]["workoutSteps"][1]["workoutSteps"][0]
    fast, slow = zones["H"]
    assert interval["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    assert interval["targetValueOne"] == pytest.approx(1000 / slow)


def test_new_install_has_half_block_and_2_20_start(client):
    t = "today=2026-11-03"
    p = client.get(f"/api/progress?{t}").json()
    assert p["tests"][0]["time"] == "2:20:00" and p["tests"][0]["vdot"] == 30.3
    assert p["half"]["goal"] == "2:15:00" and p["half"]["recommended"] == "C"
    assert {o["label"]: o["five_k"] for o in p["half"]["options"]}["Stretch"] == "24:59"
    assert p["max_hr"] == 183 and p["hr_zones"][0]["high"] == 143
    d = client.get(f"/api/dashboard?{t}").json()
    assert d["next_race"] == {"date": "2026-12-06", "label": "Half", "days": 33}
    w5 = client.get(f"/api/week?week=5&{t}").json()
    assert w5["phase"] == "Half-marathon prep"
    tue = w5["workouts"][1]
    assert tue["steps"][1]["steps"][0]["pace"] == "6:19–6:29 /km"  # 2:15 goal pace +-5 s
    assert w5["workouts"][3]["hr_hint"] == "Easy effort: keep heart rate under 143 bpm"


def test_set_half_goal_and_max_hr(client):
    t = "today=2026-11-03"
    assert client.post("/api/half-goal", json={"time": "2:05:00"}).status_code == 200
    w5 = client.get(f"/api/week?week=5&{t}").json()
    assert w5["workouts"][1]["steps"][1]["steps"][0]["pace"] == "5:50–6:00 /km"
    assert client.get(f"/api/progress?{t}").json()["half"]["goal"] == "2:05:00"
    assert client.post("/api/half-goal", json={"time": "9:99"}).status_code == 400
    assert client.post("/api/half-goal", json={"time": "0:50:00"}).status_code == 400
    assert client.post("/api/max-hr", json={"max_hr": 188}).status_code == 200
    assert client.get(f"/api/progress?{t}").json()["hr_zones"][0]["high"] == 147
    assert client.post("/api/max-hr", json={"max_hr": 90}).status_code == 422


def test_revision_upgrades_existing_phone_install(tmp_path, monkeypatch):
    """A database from the previous version gets the half block on future unlogged days only."""
    import json as _json
    from app import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "phone.db")
    db.init_db()
    old_plan = generate_plan(START, RACE, date(2026, 10, 29))
    with db.connect() as conn:  # rewind it to how the previous version left it
        conn.execute("DELETE FROM settings WHERE key IN ('plan_revision', 'half_race', 'half_goal_s', 'max_hr')")
        conn.execute("UPDATE fitness SET time_s = 9000, vdot = 27.9 WHERE source = 'initial'")
        for w in old_plan:
            conn.execute("UPDATE workouts SET week=?, phase=?, kind=?, title=?, steps=?, shoe=?, planned_km=?, "
                         "notes=?, test_distance_km=? WHERE date=?",
                         (w.week, w.phase, w.kind, w.title, _json.dumps(w.steps), w.shoe, w.planned_km, w.notes,
                          w.test_distance_km, w.date.isoformat()))
        conn.execute("UPDATE workouts SET status='done', actual_km=8 WHERE date='2026-11-03'")  # logged today
        conn.execute("UPDATE workouts SET status='skipped' WHERE date='2026-11-12'")  # future but already logged
        old_nov12 = conn.execute("SELECT title FROM workouts WHERE date='2026-11-12'").fetchone()["title"]
        db._apply_revisions(conn, today=date(2026, 11, 3))
        rows = {r["date"]: dict(r) for r in conn.execute("SELECT * FROM workouts")}
        settings = {r["key"]: _json.loads(r["value"]) for r in conn.execute("SELECT * FROM settings")}
        initial = conn.execute("SELECT * FROM fitness WHERE source = 'initial'").fetchone()
    assert rows["2026-11-03"]["status"] == "done" and rows["2026-11-03"]["actual_km"] == 8
    assert rows["2026-11-12"]["status"] == "skipped" and rows["2026-11-12"]["title"] == old_nov12
    assert rows["2026-12-06"]["title"] == "HALF MARATHON RACE"
    assert rows["2026-11-21"]["title"] == "Long run 18 km"
    assert rows["2026-10-31"]["title"] == "Long run 12 km"  # past days untouched
    assert settings["plan_revision"] == 2 and settings["half_goal_s"] == 8100 and settings["max_hr"] == 183
    assert initial["time_s"] == 8400 and round(initial["vdot"], 1) == 30.3
    with db.connect() as conn:  # running it again changes nothing
        before = [dict(r) for r in conn.execute("SELECT * FROM workouts")]
        db._apply_revisions(conn, today=date(2026, 11, 3))
        assert [dict(r) for r in conn.execute("SELECT * FROM workouts")] == before


def test_half_race_result_resets_paces(client):
    t = "today=2026-12-06"
    before = client.get(f"/api/progress?{t}").json()["measured_vdot"]
    r = client.post(f"/api/workouts/2026-12-06/log?{t}", json={"status": "done", "test_time": "2:08:30"})
    assert r.status_code == 200
    p = client.get(f"/api/progress?{t}").json()
    assert p["measured_vdot"] > before and p["tests"][-1]["time"] == "2:08:30"
    assert p["half"]["result"] is True


def test_app_files_are_revalidated_and_versioned(client):
    import hashlib
    from app.main import STATIC
    r = client.get("/")
    assert r.headers["cache-control"] == "no-cache"
    version = hashlib.sha256((STATIC / "app.js").read_bytes()).hexdigest()[:10]
    assert f'src="/static/app.js?v={version}"' in r.text
    assert "/static/style.css?v=" in r.text
    assert client.get(f"/static/app.js?v={version}").headers["cache-control"] == "no-cache"
    assert client.get("/sw.js").headers["cache-control"] == "no-cache"


# --- moving workouts --------------------------------------------------------
# Week 3 (Nov 9-15): Mon rest, Tue cruise intervals, Wed rest, Thu easy 7, Fri rest,
# Sat long 15 (last 3 @ half pace), Sun recovery 5.

def _week(client, t, n=3):
    return {w["date"]: w for w in client.get(f"/api/week?week={n}&today={t}").json()["workouts"]}


def _move(client, src, dst, mode="swap", t="2026-11-11"):
    return client.post(f"/api/workouts/{src}/move?today={t}", json={"to": dst, "mode": mode})


def test_missed_run_moves_to_rest_day(client):
    t = "2026-11-11"  # Wed, the day after missing Tuesday's workout
    d = client.get(f"/api/dashboard?today={t}").json()
    assert d["missed"] == {"date": "2026-11-10", "title": "Cruise intervals 3 x 1.5 km", "planned_km": 9.0,
                           "mode": "swap", "today_title": "Rest day"}
    before = client.get(f"/api/week?week=3&today={t}").json()["planned_km"]
    r = _move(client, "2026-11-10", t)
    assert r.status_code == 200 and r.json()["warning"] is None
    w = _week(client, t)
    assert w["2026-11-11"]["title"] == "Cruise intervals 3 x 1.5 km" and w["2026-11-11"]["moved_from"] == "2026-11-10"
    assert w["2026-11-10"]["kind"] == "rest" and w["2026-11-10"]["moved_to"] == "2026-11-11"
    assert w["2026-11-12"]["title"] == "Easy 7 km + strides"  # the next run is untouched
    assert client.get(f"/api/week?week=3&today={t}").json()["planned_km"] == before
    assert client.get(f"/api/dashboard?today={t}").json()["missed"] is None
    # Yesterday is now a rest day, so it no longer breaks the streak.
    days = {c["date"]: c["state"] for c in client.get(f"/api/heatmap?today={t}").json()["days"]}
    assert days["2026-11-10"] == "rest" and days["2026-11-11"] == "today"


def test_missed_long_run_replaces_sunday_recovery(client):
    t = "2026-11-15"
    assert client.get(f"/api/dashboard?today={t}").json()["missed"]["mode"] == "replace"
    before = client.get(f"/api/week?week=3&today={t}").json()["planned_km"]
    assert _move(client, "2026-11-14", t, "replace", t).status_code == 200
    w = _week(client, t)
    assert w[t]["title"].startswith("Long run 15 km") and w[t]["replaced"] == "Recovery 5 km"
    assert w["2026-11-14"]["kind"] == "rest"
    assert client.get(f"/api/week?week=3&today={t}").json()["planned_km"] == pytest.approx(before - 5)  # total drops


def test_swap_two_runs_and_back_to_back_warning(client):
    t = "2026-11-09"
    r = _move(client, "2026-11-12", "2026-11-14", "swap", t)  # Thu easy <-> Sat long
    assert r.status_code == 200
    w = _week(client, t)
    assert w["2026-11-12"]["title"].startswith("Long run") and w["2026-11-12"]["moved_from"] == "2026-11-14"
    assert w["2026-11-14"]["title"] == "Easy 7 km + strides" and w["2026-11-14"]["moved_from"] == "2026-11-12"
    # The Tue workout moved to Wed now sits right before Thursday's (swapped-in) long run.
    assert _move(client, "2026-11-10", "2026-11-11", "swap", t).json()["warning"].startswith("Hard days back to back")


def test_move_rules(client):
    t = "2026-11-11"
    assert _move(client, "2026-11-12", "2026-11-16", t=t).status_code == 400  # next week
    assert _move(client, "2026-11-12", "2026-11-09", t=t).status_code == 400  # into the past
    assert _move(client, "2026-11-11", "2026-11-13", t=t).status_code == 400  # rest day as source
    assert _move(client, "2026-12-06", "2026-12-05", t=t).status_code == 400  # race is fixed
    assert _move(client, "2026-12-05", "2026-12-06", "replace", t=t).status_code == 400  # can't replace a race
    client.post(f"/api/workouts/2026-11-12/log?today={t}", json={"status": "done"})
    assert _move(client, "2026-11-12", "2026-11-13", t=t).status_code == 400  # already logged
    opts = client.get(f"/api/workouts/2026-11-14/move-options?today={t}").json()["options"]
    assert [(o["date"], o["modes"]) for o in opts] == [
        ("2026-11-11", ["swap"]), ("2026-11-13", ["swap"]), ("2026-11-15", ["replace", "swap"])]


def test_undo_week_moves(client):
    t = "2026-11-09"
    original = _week(client, t)
    _move(client, "2026-11-14", "2026-11-15", "replace", t)
    _move(client, "2026-11-10", "2026-11-11", "swap", t)
    assert client.post(f"/api/weeks/3/undo-moves?today={t}", headers=JSON).status_code == 200
    after = _week(client, t)
    keys = ("kind", "title", "planned_km", "moved_from", "moved_to", "replaced", "original")
    assert all({k: after[d][k] for k in keys} == {k: original[d][k] for k in keys} for d in original)
    assert client.post(f"/api/weeks/3/undo-moves?today={t}", headers=JSON).status_code == 400  # nothing left
    _move(client, "2026-11-10", "2026-11-11", "swap", t)
    client.post(f"/api/workouts/2026-11-11/log?today={t}", json={"status": "done"})
    assert client.post(f"/api/weeks/3/undo-moves?today={t}", headers=JSON).status_code == 400  # logged


def test_no_shortcut_when_next_run_already_came(client):
    # Tue missed, today is Thu (an easy run day): Tuesday's window has closed.
    assert client.get("/api/dashboard?today=2026-11-12").json()["missed"] is None


def test_garmin_follows_moves(tmp_path, monkeypatch):
    from app import db, moves
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "g.db")
    db.init_db()
    with db.connect() as conn:
        conn.execute("UPDATE workouts SET garmin_workout_id = 'w14' WHERE date = '2026-11-14'")
        conn.execute("UPDATE workouts SET garmin_workout_id = 'w15' WHERE date = '2026-11-15'")
        r = moves.move(conn, "2026-11-14", "2026-11-15", "replace", date(2026, 11, 9))
        assert r["garmin"] == [("push", "2026-11-15"), ("delete", "w15")]
        row = conn.execute("SELECT garmin_workout_id FROM workouts WHERE date = '2026-11-15'").fetchone()
        assert row["garmin_workout_id"] == "w14"  # travels with the workout, re-sent for the new date


def test_late_garmin_run_counts_as_missed_workout(client, monkeypatch):
    from app import garmin
    monkeypatch.setattr(garmin, "login", lambda: object())
    monkeypatch.setattr(garmin, "fetch_runs", lambda api, s, e: {
        "2026-11-11": {"km": 9.1, "time_s": 3300, "ids": ["77"], "avg_hr": 150}})
    t = "2026-11-11"
    assert client.post(f"/api/garmin/sync?today={t}", headers=JSON).json()["late_run"] is True
    d = client.get(f"/api/dashboard?today={t}").json()
    assert d["late_run"]["missed"] == "2026-11-10" and d["missed"] is None
    assert client.post(f"/api/late-run/accept?today={t}", headers=JSON).status_code == 200
    w = _week(client, t)
    assert w[t]["title"] == "Cruise intervals 3 x 1.5 km" and w[t]["status"] == "done" and w[t]["actual_km"] == 9.1
    assert w["2026-11-10"]["kind"] == "rest"
    assert client.get(f"/api/dashboard?today={t}").json()["late_run"] is None


def test_plan_revisions_leave_moved_days_alone(tmp_path, monkeypatch):
    from app import db, moves
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "r.db")
    db.init_db()
    with db.connect() as conn:
        moves.move(conn, "2026-11-14", "2026-11-15", "replace", date(2026, 11, 9))
        conn.execute("DELETE FROM settings WHERE key = 'plan_revision'")
        db._apply_revisions(conn, today=date(2026, 11, 9))
        assert conn.execute("SELECT kind FROM workouts WHERE date = '2026-11-14'").fetchone()["kind"] == "rest"
