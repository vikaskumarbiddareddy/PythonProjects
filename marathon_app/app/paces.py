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


def zone_paces(vdot: float) -> dict[str, tuple[float, float]]:
    """Seconds per km for each zone as (fast, slow)."""
    out = {}
    for zone, (lo, hi) in ZONE_FRACTIONS.items():
        fast = 60000 / _velocity_for_vo2(hi * vdot)
        slow = 60000 / _velocity_for_vo2(lo * vdot)
        out[zone] = (fast, slow)
    mp = predict_time_s(vdot, MARATHON_KM) / MARATHON_KM
    out["M"] = (mp - 5, mp + 5)
    order = ["E", "M", "T", "I", "R"]
    return {z: out[z] for z in order}


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
