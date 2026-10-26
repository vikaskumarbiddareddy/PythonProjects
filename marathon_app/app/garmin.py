"""Push planned workouts to Garmin Connect (and on to the watch) via the unofficial
`garminconnect` library.

Credentials come from GARMIN_EMAIL / GARMIN_PASSWORD; login tokens are cached in
GARMIN_TOKENS (default: data/garmin_tokens) so the password is only used once.
"""

import os
from pathlib import Path

from garminconnect import Garmin
from garminconnect.workout import ExecutableStep, RepeatGroup, RunningWorkout, WorkoutSegment

from . import paces

TOKEN_DIR = os.environ.get("GARMIN_TOKENS", str(Path(__file__).resolve().parent.parent / "data" / "garmin_tokens"))

STEP_TYPES = {"warmup": 1, "cooldown": 2, "run": 3, "recovery": 4, "repeat": 6}
STEP_KEYS = {"warmup": "warmup", "cooldown": "cooldown", "run": "interval", "recovery": "recovery", "repeat": "repeat"}
NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
PACE_TARGET = {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone", "displayOrder": 6}
DISTANCE = {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True}
TIME = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}
ITERATIONS = {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False}
# Warm-up, cool-down and strides are effort-based; no pace alerts on those.
TARGETED_ZONES = {"E", "M", "T", "I"}


class GarminError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.environ.get("GARMIN_EMAIL") and os.environ.get("GARMIN_PASSWORD")) or Path(TOKEN_DIR).exists()


def login() -> Garmin:
    if not configured():
        raise GarminError("Garmin is not set up: set GARMIN_EMAIL and GARMIN_PASSWORD on the server.")
    # Not return_on_mfa: that mode skips saving tokens, forcing a password login on every push.
    api = Garmin(os.environ.get("GARMIN_EMAIL"), os.environ.get("GARMIN_PASSWORD"), prompt_mfa=_no_mfa)
    api.login(TOKEN_DIR)
    return api


def _no_mfa() -> str:
    raise GarminError("Garmin asked for a 2-step verification code; run `python -m app.garmin_login` once.")


def _step(s: dict, order: int, zones: dict) -> tuple[ExecutableStep | RepeatGroup, int]:
    """Convert one plan step; returns the Garmin step and the next free stepOrder."""
    kind = s["type"]
    step_type = {"stepTypeId": STEP_TYPES[kind], "stepTypeKey": STEP_KEYS[kind], "displayOrder": STEP_TYPES[kind]}
    if kind == "repeat":
        children, child_order = [], order + 1
        for child in s["steps"]:
            built, child_order = _step(child, child_order, zones)
            children.append(built)
        group = RepeatGroup(
            stepOrder=order, stepType=step_type, numberOfIterations=s["reps"], workoutSteps=children,
            endCondition=ITERATIONS, endConditionValue=float(s["reps"]), skipLastRestStep=True,
        )
        return group, child_order

    if s.get("km"):
        end, value = DISTANCE, s["km"] * 1000
    else:
        end, value = TIME, s["sec"]

    target, lo, hi = NO_TARGET, None, None
    zone = s.get("zone")
    if kind == "run" and zone in TARGETED_ZONES:
        fast, slow = zones[zone]
        target, lo, hi = PACE_TARGET, 1000 / slow, 1000 / fast  # m/s; slower pace is the lower limit

    return ExecutableStep(
        stepOrder=order, stepType=step_type, endCondition=end, endConditionValue=value,
        targetType=target, targetValueOne=lo, targetValueTwo=hi,
        description=paces.ZONE_NAMES.get(zone) if zone else None,
    ), order + 1


def build_workout(w: dict, vdot: float) -> RunningWorkout:
    zones = paces.zone_paces(vdot)
    steps, order = [], 1
    for s in w["steps"]:
        built, order = _step(s, order, zones)
        steps.append(built)
    est_s = int(w["planned_km"] * zones["E"][1])
    return RunningWorkout(
        workoutName=f"W{w['week']} {w['title']}"[:80],
        description=f"Shoe: {w['shoe']}. {w['notes']}".strip(),
        estimatedDurationInSecs=est_s,
        workoutSegments=[WorkoutSegment(segmentOrder=1, sportType={"sportTypeId": 1, "sportTypeKey": "running"},
                                        workoutSteps=steps)],
    )


def push(api: Garmin, w: dict, vdot: float) -> str:
    """Upload + schedule a workout, replacing any copy pushed earlier. Returns the Garmin workout id."""
    if w.get("garmin_workout_id"):
        try:
            api.delete_workout(w["garmin_workout_id"])
        except Exception:
            pass  # already deleted in Garmin Connect
    created = api.upload_running_workout(build_workout(w, vdot))
    workout_id = str(created["workoutId"])
    api.schedule_workout(workout_id, w["date"])
    return workout_id
