"""Jack Daniels VDOT model: fitness from a race result, training paces and race predictions."""

import math

MARATHON_KM = 42.195
HALF_KM = 21.0975

# Training zones as fractions of VDOT (fast end, slow end are derived from the range).
ZONE_FRACTIONS = {
    "E": (0.62, 0.70),  # easy / long
    "T": (0.86, 0.89),  # threshold / tempo
    "I": (0.95, 0.98),  # intervals (VO2max)
    "R": (1.03, 1.07),  # repetitions / strides
}
ZONE_NAMES = {
    "E": "Easy",
    "M": "Marathon",
    "H": "Half-marathon goal",
    "T": "Threshold",
    "I": "Interval",
    "R": "Repetition",
}


def _vo2(v_m_per_min: float) -> float:
    return -4.60 + 0.182258 * v_m_per_min + 0.000104 * v_m_per_min**2


def _pct_max(t_min: float) -> float:
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot_from_race(distance_km: float, time_s: float) -> float:
    t_min = time_s / 60
    v = distance_km * 1000 / t_min
    return _vo2(v) / _pct_max(t_min)


def _velocity_for_vo2(vo2: float) -> float:
    """Inverse of _vo2: metres/minute that costs the given VO2."""
    a, b, c = 0.000104, 0.182258, -4.60 - vo2
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)


def predict_time_s(vdot: float, distance_km: float) -> float:
    """Race time at which the given distance yields this VDOT (bisection)."""
    lo, hi = 60.0, 12 * 3600.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if vdot_from_race(distance_km, mid) > vdot:
            lo = mid  # too fast -> needs more time
        else:
            hi = mid
    return (lo + hi) / 2


def vdot_for_goal(distance_km: float, time_s: float) -> float:
    return vdot_from_race(distance_km, time_s)


def zone_paces(vdot: float, half_goal_s: float | None = None) -> dict[str, tuple[float, float]]:
    """Seconds per km for each zone as (fast, slow).

    H (half-marathon goal pace) comes from the chosen race goal, not from fitness,
    and is only included when a goal is given.
    """
    out = {}
    for zone, (lo, hi) in ZONE_FRACTIONS.items():
        fast = 60000 / _velocity_for_vo2(hi * vdot)
        slow = 60000 / _velocity_for_vo2(lo * vdot)
        out[zone] = (fast, slow)
    mp = predict_time_s(vdot, MARATHON_KM) / MARATHON_KM
    out["M"] = (mp - 5, mp + 5)
    if half_goal_s:
        hp = half_goal_s / HALF_KM
        out["H"] = (hp - 5, hp + 5)
    order = ["E", "M", "H", "T", "I", "R"]
    return {z: out[z] for z in order if z in out}


# Heart-rate zones as fractions of max HR (for runners without a lab test).
HR_ZONES = [
    ("Easy / recovery", 0.65, 0.78),
    ("Steady / marathon", 0.78, 0.87),
    ("Threshold / half", 0.87, 0.92),
    ("Interval", 0.92, 1.00),
]


def max_hr_for_age(age: int) -> int:
    """Tanaka estimate (208 - 0.7 x age); a measured max from Garmin is better."""
    return round(208 - 0.7 * age)


def hr_zones(max_hr: int) -> list[dict]:
    return [{"name": n, "low": round(lo * max_hr), "high": round(hi * max_hr)} for n, lo, hi in HR_ZONES]


def easy_hr_ceiling(max_hr: int) -> int:
    return round(HR_ZONES[0][2] * max_hr)


def fmt_pace(sec_per_km: float) -> str:
    s = int(round(sec_per_km))
    return f"{s // 60}:{s % 60:02d}"


def fmt_time(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_time(text: str) -> int:
    """'2:30:00', '45:12' or '1:05:30' -> seconds."""
    parts = [int(p) for p in text.strip().split(":")]
    if not 2 <= len(parts) <= 3:
        raise ValueError(f"Bad time: {text!r}")
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 3600 + m * 60 + s
