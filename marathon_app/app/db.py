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
    "half_race": "2026-12-06",
    "goal_time_s": 3 * 3600 + 30 * 60,
    "half_goal_s": 2 * 3600 + 15 * 60,  # goal C until the 5K test picks the real one
    "max_hr": paces.max_hr_for_age(36),
    # The 2:30 half was an off day; 2:20 is the agreed starting point.
    "initial_test": {"distance_km": paces.HALF_KM, "time_s": 2 * 3600 + 20 * 60},
}
PLAN_KEYS = ("plan_start", "race_day", "first_run", "half_race")
PLAN_REVISION = 2  # bump when the plan changes; _apply_revisions updates existing installs
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
    avg_hr INTEGER,
    moved_from TEXT,  -- date this workout was originally planned on (see moves.py)
    moved_to TEXT,    -- on a day emptied by a move: where its workout went
    replaced TEXT,    -- title of the run this workout replaced
    original TEXT     -- JSON of the day's planned content before any move, for undo
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
            _apply_revisions(conn)
            return
        set_setting(conn, "plan_revision", PLAN_REVISION)
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
        plan = generate_plan(*(date.fromisoformat(DEFAULTS[k]) for k in PLAN_KEYS))
        conn.executemany(
            """INSERT INTO workouts (date, week, phase, kind, title, steps, shoe, planned_km, notes, test_distance_km)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(w.date.isoformat(), w.week, w.phase, w.kind, w.title, json.dumps(w.steps), w.shoe,
              w.planned_km, w.notes, w.test_distance_km) for w in plan],
        )


def _migrate(conn) -> None:
    """Add columns introduced after a database was first created."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(workouts)")}
    for col, decl in (("garmin_activity_id", "TEXT"), ("avg_hr", "INTEGER"), ("moved_from", "TEXT"),
                      ("moved_to", "TEXT"), ("replaced", "TEXT"), ("original", "TEXT")):
        if col not in have:
            conn.execute(f"ALTER TABLE workouts ADD COLUMN {col} {decl}")


def _apply_revisions(conn, today: date | None = None) -> None:
    """Bring a database created by an older version up to the current plan.

    Only future days that are still unlogged and not moved are rewritten; anything
    already done, skipped, partial, synced from Garmin or moved is left as it was.
    """
    revision = get_setting(conn, "plan_revision") or 1
    if revision >= PLAN_REVISION:
        return
    today = today or date.today()
    if revision < 2:
        for key in ("half_race", "half_goal_s", "max_hr"):
            conn.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", (key, json.dumps(DEFAULTS[key])))
        old, new = 2 * 3600 + 30 * 60, DEFAULTS["initial_test"]["time_s"]
        conn.execute(
            "UPDATE fitness SET time_s = ?, vdot = ? WHERE source = 'initial' AND time_s = ?",
            (new, paces.vdot_from_race(paces.HALF_KM, new), old),
        )
    plan = generate_plan(*(date.fromisoformat(get_setting(conn, k)) for k in PLAN_KEYS))
    for w in plan:
        if w.date < today:
            continue
        conn.execute(
            """UPDATE workouts SET week = ?, phase = ?, kind = ?, title = ?, steps = ?, shoe = ?, planned_km = ?,
                   notes = ?, test_distance_km = ?
               WHERE date = ? AND status = 'planned' AND actual_km IS NULL AND garmin_activity_id IS NULL
                 AND original IS NULL""",
            (w.week, w.phase, w.kind, w.title, json.dumps(w.steps), w.shoe, w.planned_km, w.notes,
             w.test_distance_km, w.date.isoformat()),
        )
    set_setting(conn, "plan_revision", PLAN_REVISION)


def get_setting(conn, key):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else DEFAULTS.get(key)


def set_setting(conn, key, value) -> None:
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))


def row_to_workout(row) -> dict:
    w = dict(row)
    w["steps"] = json.loads(w["steps"])
    return w


# --- backup / restore -------------------------------------------------------

BACKUP_VERSION = 1
BACKUP_TABLES = ("settings", "workouts", "fitness", "weights", "shoes")  # no Garmin credentials or tokens


def export_all(conn) -> dict:
    return {
        "app": "marathon-trainer",
        "version": BACKUP_VERSION,
        "tables": {t: [dict(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in BACKUP_TABLES},
    }


def import_all(conn, data: dict) -> None:
    """Replace all training data with a backup. Raises ValueError for anything that isn't one."""
    if data.get("app") != "marathon-trainer" or data.get("version") != BACKUP_VERSION:
        raise ValueError("Not a Marathon Trainer backup file")
    tables = data.get("tables") or {}
    if not tables.get("workouts"):
        raise ValueError("Backup has no workouts")
    try:
        for t in BACKUP_TABLES:
            columns = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
            conn.execute(f"DELETE FROM {t}")
            for row in tables.get(t, []):
                keys = [k for k in row if k in columns]  # tolerate columns added or removed since
                conn.execute(f"INSERT INTO {t} ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
                             [row[k] for k in keys])
    except Exception as e:
        conn.rollback()
        raise ValueError(f"Backup could not be restored: {e}") from e
