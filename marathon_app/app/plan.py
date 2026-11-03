"""26-week marathon plan generator.

Workouts are stored as structured steps that reference pace zones (E/M/T/I/R,
plus H = half-marathon goal pace), not absolute paces, so every future workout
speeds up automatically when the runner's fitness (VDOT) or race goal changes.

Week layout (4 run days, long run Saturday):
    Mon rest | Tue quality | Wed rest | Thu easy/steady | Fri rest | Sat long | Sun recovery
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

PEGASUS = "Pegasus 42"
MAGIC_SPEED = "Magic Speed 5"

# (weekly km, long run km) per week, 1-indexed. Every 4th week is a cutback.
WEEKS = [
    # Base 1-8
    (30, 12), (32, 13), (35, 14), (28, 11), (36, 15), (38, 16), (40, 17), (32, 13),
    # Build 9-16
    (42, 18), (44, 19), (46, 21), (36, 16), (47, 22), (49, 21.1), (50, 24), (40, 18),
    # Marathon-specific 17-23
    (54, 25), (57, 27), (60, 29), (46, 20), (62, 32), (60, 28), (52, 24),
    # Taper 24-26
    (44, 22), (34, 16), (20, 0),
]
PLAN_WEEKS = len(WEEKS)

# Optional half-marathon race on the Sunday of week 6, prepared in weeks 3-6
# with a recovery week 7. Planned km per week for that block:
HALF_WEEKS = range(3, 8)
HALF_RACE_WEEK = 6
HALF_BLOCK_KM = {3: 36, 4: 38, 5: 32, 6: 37, 7: 25}


def phase_for(week: int, half: bool = False) -> str:
    if half and week in HALF_WEEKS:
        return "Recovery" if week > HALF_RACE_WEEK else "Half-marathon prep"
    if week <= 8:
        return "Base"
    if week <= 16:
        return "Build"
    if week <= 23:
        return "Marathon-specific"
    return "Taper"


# --- step helpers -----------------------------------------------------------

def wu(km=2.0):
    return {"type": "warmup", "km": km, "zone": "E"}


def cd(km=1.5):
    return {"type": "cooldown", "km": km, "zone": "E"}


def run(km=None, zone="E", sec=None):
    return {"type": "run", "km": km, "sec": sec, "zone": zone}


def jog(sec):
    return {"type": "recovery", "sec": sec, "zone": None}


def repeat(n, *steps):
    return {"type": "repeat", "reps": n, "steps": list(steps)}


RECOVERY_KM_PER_MIN = 0.13  # rough jog distance used for planned-km estimates


def steps_km(steps) -> float:
    total = 0.0
    for s in steps:
        if s["type"] == "repeat":
            total += s["reps"] * steps_km(s["steps"])
        elif s.get("km"):
            total += s["km"]
        elif s.get("sec"):
            total += s["sec"] / 60 * RECOVERY_KM_PER_MIN
    return total


def quality_session(main, total_km, wu_km=2.0):
    """Warm-up + main set + cool-down that fills the session out to total_km."""
    main_km = steps_km(main)
    cd_km = max(1.5, round(total_km - wu_km - main_km, 1))
    return [wu(wu_km), *main, cd(cd_km)]


def strides(n=6):
    return repeat(n, run(sec=20, zone="R"), jog(60))


# --- workout model ----------------------------------------------------------

@dataclass
class Workout:
    date: date
    week: int
    phase: str
    kind: str  # rest | easy | recovery | long | quality | test | race
    title: str
    steps: list = field(default_factory=list)
    shoe: str | None = None
    notes: str = ""
    test_distance_km: float | None = None  # set for time trials -> updates fitness

    @property
    def planned_km(self) -> float:
        return round(steps_km(self.steps), 1)


def _tuesday(week: int, km: float) -> tuple[str, str, list, float | None]:
    """(title, kind, steps, test_distance) for the week's quality session."""
    q = lambda title, main, wu_km=2.0: (title, "quality", quality_session(main, km, wu_km), None)
    match week:
        case 1 | 8:
            return ("Easy + strides", "easy", [run(round(km - 1.5, 1)), strides(6)], None)
        case 2:
            return q("Fartlek 6 x 1 min", [repeat(6, run(sec=60, zone="I"), jog(120))])
        case 3:
            return q("Fartlek 8 x 1 min", [repeat(8, run(sec=60, zone="I"), jog(120))])
        case 4:
            return ("5K time trial", "test", quality_session([run(5, None)], km), 5.0)
        case 5:
            return q("Cruise intervals 3 x 1.5 km", [repeat(3, run(1.5, "T"), jog(120))])
        case 6:
            return q("Cruise intervals 4 x 1.5 km", [repeat(4, run(1.5, "T"), jog(120))])
        case 7:
            return q("Hill repeats 8 x 60 s", [repeat(8, run(sec=60, zone=None), jog(90))])
        case 9:
            return q("Intervals 5 x 1 km", [repeat(5, run(1, "I"), jog(120))])
        case 10:
            return q("Tempo 2 x 3 km", [repeat(2, run(3, "T"), jog(180))])
        case 11:
            return q("Intervals 6 x 1 km", [repeat(6, run(1, "I"), jog(120))])
        case 12 | 20:
            return ("10K time trial", "test", quality_session([run(10, None)], km), 10.0)
        case 13:
            return q("Tempo 6 km", [run(6, "T")])
        case 14:
            return ("Easy + strides (race week)", "easy", [run(round(km - 1.5, 1)), strides(4)], None)
        case 15:
            return q("Tempo 4 x 2 km", [repeat(4, run(2, "T"), jog(120))])
        case 16:
            return q("Intervals 6 x 800 m", [repeat(6, run(0.8, "I"), jog(120))])
        case 17 | 21:
            return q("Tempo 3 x 3 km", [repeat(3, run(3, "T"), jog(150))])
        case 18:
            return q("Tempo 2 x 4 km", [repeat(2, run(4, "T"), jog(180))])
        case 19:
            return q("Tempo 5 x 1.6 km", [repeat(5, run(1.6, "T"), jog(120))])
        case 22:
            return q("Marathon pace 10 km", [run(10, "M")])
        case 23:
            return q("Tempo 4 x 1.6 km", [repeat(4, run(1.6, "T"), jog(120))])
        case 24:
            return q("Tempo 3 x 2 km", [repeat(3, run(2, "T"), jog(120))])
        case 25:
            return q("Marathon pace 6 km", [run(6, "M")])
        case 26:
            return q("Sharpener 4 x 1 km @ MP", [repeat(4, run(1, "M"), jog(90))], 1.5)
    raise ValueError(week)


# Long runs with a marathon-pace finish: week -> km at M pace.
LONG_MP_KM = {15: 5, 17: 8, 19: 10, 22: 14, 23: 8, 24: 8}


def _long_run(week: int, km: float) -> tuple[str, str, list, float | None]:
    if week == 14:
        return ("Half marathon test race", "test", [wu(1.5), run(21.1, None), cd(1.0)], 21.0975)
    mp = LONG_MP_KM.get(week)
    if mp:
        return (f"Long run {km:g} km, last {mp} km @ MP", "long", [run(km - mp), run(mp, "M")], None)
    return (f"Long run {km:g} km", "long", [run(km)], None)


def _thursday(week: int, km: float) -> tuple[str, list]:
    if week >= 17 and week not in (20, 26):
        mp = 3 if week < 21 else 5
        return (f"Steady {km:g} km with {mp} km @ MP", [run(round(km - mp - 1, 1)), run(mp, "M"), run(1)])
    if week <= 8:
        return (f"Easy {km:g} km + strides", [run(round(km - 1, 1)), strides(4)])
    return (f"Easy {km:g} km", [run(km)])


def _half_block(week: int) -> list[tuple]:
    """Day specs (offset, kind, title, steps, notes, test_km) for runs in the half-marathon block."""
    match week:
        case 3:
            return [
                (1, "quality", "Cruise intervals 3 x 1.5 km",
                 quality_session([repeat(3, run(1.5, "T"), jog(120))], 9), "", None),
                (3, "easy", "Easy 7 km + strides", [run(6), strides(4)], "", None),
                (5, "long", "Long run 15 km, last 3 km @ half pace", [run(12), run(3, "H")],
                 "Finish at your half-marathon goal pace: controlled, not racing.", None),
                (6, "recovery", "Recovery 5 km", [run(5)], "Very easy. Slower than you think.", None),
            ]
        case 4:
            return [
                (1, "test", "5K time trial", quality_session([run(5, None)], 9),
                 "All-out effort. Your result updates your paces and picks your Dec 6 race goal.", 5.0),
                (3, "easy", "Easy 7 km", [run(7)], "", None),
                (5, "long", "Long run 18 km", [run(18)], "Your longest run before the race. Keep it easy.", None),
                (6, "recovery", "Recovery 4 km", [run(4)], "Very easy. Slower than you think.", None),
            ]
        case 5:
            return [
                (1, "quality", "Half pace 3 x 2 km",
                 quality_session([repeat(3, run(2, "H"), jog(120))], 10), "Lock in your race pace.", None),
                (3, "easy", "Easy 6 km", [run(6)], "", None),
                (5, "long", "Race rehearsal 12 km, 6 km @ half pace", [run(4), run(6, "H"), run(2)],
                 "Wear your Magic Speed 5 and race-day kit; practise your drinks and gels.", None),
                (6, "recovery", "Recovery 4 km", [run(4)], "Very easy. Slower than you think.", None),
            ]
        case 6:
            return [
                (1, "quality", "Sharpener 4 x 1 km @ half pace",
                 quality_session([repeat(4, run(1, "H"), jog(90))], 8), "Short and sharp. Race week.", None),
                (3, "easy", "Easy 5 km", [run(5)], "", None),
                (5, "easy", "Shakeout 3 km + strides", [run(2), strides(4)], "Loosen up. Lay out your kit.", None),
                (6, "race", "HALF MARATHON RACE", [run(21.1, "H")],
                 "First 5 km 5-10 s/km slower than goal, settle into goal pace, push from 16 km if you feel strong.",
                 21.0975),
            ]
        case 7:
            note = "Recovery week after the race: no workouts, keep it truly easy."
            return [
                (1, "easy", "Easy 5 km", [run(5)], note, None),
                (3, "easy", "Easy 6 km", [run(6)], note, None),
                (5, "long", "Easy long run 10 km", [run(10)], note, None),
                (6, "recovery", "Recovery 4 km", [run(4)], "Very easy. Slower than you think.", None),
            ]
    raise ValueError(week)


def _shoe_for(kind: str, steps) -> str:
    fast = {"T", "I", "R", "M", "H"}

    def fast_km(ss):
        return sum(
            (s["reps"] * fast_km(s["steps"])) if s["type"] == "repeat"
            else (s.get("km") or 0) if s.get("zone") in fast else 0
            for s in ss
        )

    if kind in ("test", "race"):
        return MAGIC_SPEED
    # Plated shoe for proper workouts and MP rehearsals; daily trainer for the rest.
    return MAGIC_SPEED if fast_km(steps) >= 4 else PEGASUS


def generate_plan(start: date, race_day: date, first_run: date | None = None,
                  half_race: date | None = None) -> list[Workout]:
    """start must be a Monday; race_day is the Sunday of week 26.

    Runs scheduled before first_run become rest days (an easier entry into week 1).
    half_race, if given, must be the Sunday of week 6 and replaces weeks 3-7 with
    the half-marathon block.
    """
    if start.weekday() != 0:
        raise ValueError("Plan must start on a Monday")
    if race_day != start + timedelta(weeks=PLAN_WEEKS - 1, days=6):
        raise ValueError("Race day must be the Sunday of the final plan week")
    if half_race and half_race != start + timedelta(weeks=HALF_RACE_WEEK - 1, days=6):
        raise ValueError(f"Half-marathon race must be the Sunday of week {HALF_RACE_WEEK}")

    workouts: list[Workout] = []
    for i, (week_km, long_km) in enumerate(WEEKS):
        week = i + 1
        monday = start + timedelta(weeks=i)
        phase = phase_for(week, half=bool(half_race))
        day = lambda offset: monday + timedelta(days=offset)

        rest_km = week_km - long_km
        tue_km, thu_km, sun_km = (round(rest_km * f) for f in (0.40, 0.35, 0.25))
        if week == 26:
            tue_km, thu_km, sun_km = 8, 6, 0

        def add(offset, kind, title, steps=(), notes="", test_km=None):
            if first_run and day(offset) < first_run and kind != "rest":
                kind, title, steps, notes, test_km = "rest", "Rest day", (), f"Training starts {first_run:%A}.", None
            steps = list(steps)
            shoe = _shoe_for(kind, steps) if kind != "rest" else None
            workouts.append(Workout(day(offset), week, phase, kind, title, steps, shoe, notes, test_km))

        add(0, "rest", "Rest day", notes="Mobility or an easy walk is fine.")

        if half_race and week in HALF_WEEKS:
            runs = {spec[0]: spec for spec in _half_block(week)}
            for offset in range(1, 7):
                if offset in runs:
                    add(*runs[offset])
                else:
                    add(offset, "rest", "Rest day", notes="Rest before the long run." if offset == 4 else "")
            continue

        title, kind, steps, test_km = _tuesday(week, tue_km)
        # Time trials run long; take the excess off Sunday to protect the cutback week.
        excess = steps_km(steps) - tue_km
        if kind == "test" and excess > 0 and sun_km:
            sun_km = max(3, round(sun_km - excess))
        notes = "All-out effort. Your result updates your training paces." if kind == "test" else ""
        add(1, kind, title, steps, notes, test_km)

        add(2, "rest", "Rest day")

        title, steps = _thursday(week, thu_km)
        add(3, "easy", title, steps)

        add(4, "rest", "Rest day", notes="Rest before the long run.")

        if week == 26:
            add(5, "easy", "Shakeout 3 km + strides", [run(2), strides(4)])
            add(6, "race", "MARATHON RACE DAY", [run(42.2, "M")],
                notes="Start 5-10 s/km slower than goal pace for the first 5 km.", test_km=42.195)
            continue

        title, kind, steps, test_km = _long_run(week, long_km)
        notes = "Race it! Your result updates your training paces." if kind == "test" else ""
        add(5, kind, title, steps, notes, test_km)

        add(6, "recovery", f"Recovery {sun_km:g} km", [run(sun_km)],
            notes="Very easy. Slower than you think.")
    return workouts
