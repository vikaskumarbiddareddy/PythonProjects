"""SQLite storage: the plan, workout logs, fitness tests and shoes."""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from . import paces
from .plan import MAGIC_SPEED, PEGASUS, generate_plan

DB_PATH = Path(os.environ.get("MARATHON_DB", Path(__file__).resolve().parent.parent / "data" / "marathon.db"))

DEFAULTS = {
    "plan_start": "2026-10-26",
    "race_day": "2027-04-25",
    "first_run": "2026-10-29",
    "goal_time_s": 3 * 3600 + 30 * 60,
    "initial_test": {"distance_km": paces.HALF_KM, "time_s": 2 * 3600 + 30 * 60},
}
SHOES = [(PEGASUS, 700), (MAGIC_SPEED, 500)]  # name, retire-at km

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY,
    date TEXT UNIQUE NOT NULL,
    week INTEGER NOT NULL,
    phase TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    steps TEXT NOT NULL,
    shoe TEXT,
    planned_km REAL NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    test_distance_km REAL,
    status TEXT NOT NULL DEFAULT 'planned',  -- planned | done | partial | skipped
    actual_km REAL,
    actual_time_s INTEGER,
    rpe INTEGER,
    comment TEXT,
    garmin_workout_id TEXT,
    garmin_activity_id TEXT,  -- set when the run was synced from a Garmin activity
    avg_hr INTEGER
);
CREATE TABLE IF NOT EXISTS fitness (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    distance_km REAL NOT NULL,
    time_s INTEGER NOT NULL,
    vdot REAL NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS weights (
    id INTEGER PRIMARY KEY,
    date TEXT UNIQUE NOT NULL,
    kg REAL NOT NULL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS shoes (
    name TEXT PRIMARY KEY,
    start_km REAL NOT NULL DEFAULT 0,
    retire_km REAL NOT NULL
);
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables and seed the plan on first run."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        if conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0]:
            return
        for key, value in DEFAULTS.items():
            conn.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", (key, json.dumps(value)))
        for name, retire in SHOES:
            conn.execute("INSERT OR IGNORE INTO shoes (name, retire_km) VALUES (?, ?)", (name, retire))
        test = DEFAULTS["initial_test"]
        conn.execute(
            "INSERT INTO fitness (date, distance_km, time_s, vdot, source) VALUES (?, ?, ?, ?, 'initial')",
            (DEFAULTS["plan_start"], test["distance_km"], test["time_s"],
             paces.vdot_from_race(test["distance_km"], test["time_s"])),
        )
        plan = generate_plan(*(date.fromisoformat(DEFAULTS[k]) for k in ("plan_start", "race_day", "first_run")))
        conn.executemany(
            """INSERT INTO workouts (date, week, phase, kind, title, steps, shoe, planned_km, notes, test_distance_km)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(w.date.isoformat(), w.week, w.phase, w.kind, w.title, json.dumps(w.steps), w.shoe,
              w.planned_km, w.notes, w.test_distance_km) for w in plan],
        )


def _migrate(conn) -> None:
    """Add columns introduced after a database was first created."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(workouts)")}
    for col, decl in (("garmin_activity_id", "TEXT"), ("avg_hr", "INTEGER")):
        if col not in have:
            conn.execute(f"ALTER TABLE workouts ADD COLUMN {col} {decl}")


def get_setting(conn, key):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else DEFAULTS.get(key)


def set_setting(conn, key, value) -> None:
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))


def row_to_workout(row) -> dict:
    w = dict(row)
    w["steps"] = json.loads(w["steps"])
    return w
