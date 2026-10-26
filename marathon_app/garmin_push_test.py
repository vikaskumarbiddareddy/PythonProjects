"""Feasibility test: can we push a structured run workout to Garmin Connect?

Builds a sample threshold session with pace targets, then (with --upload)
uploads it, schedules it on the Garmin calendar, and optionally removes it.

Credentials are read from the environment, never from the command line:
    GARMIN_EMAIL, GARMIN_PASSWORD

Usage:
    python garmin_push_test.py                 # dry run: print workout JSON only
    python garmin_push_test.py --upload        # upload + schedule for tomorrow
    python garmin_push_test.py --upload --date 2026-10-28 --cleanup
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta

from garminconnect import Garmin
from garminconnect.workout import (
    PaceTarget,
    RunningWorkout,
    WorkoutSegment,
    create_cooldown_step,
    create_recovery_step,
    create_repeat_group,
    create_targeted_distance_interval_step,
    create_warmup_step,
    pace_to_mps,
)

TOKEN_DIR = os.path.expanduser("~/.garminconnect")


def build_workout() -> RunningWorkout:
    # 4 x 1 km at 6:45-7:00 /km (threshold-ish for a 2:30 half marathoner)
    rep_target = PaceTarget(
        lower_limit=pace_to_mps(7, 0, "km"),  # slower pace = lower m/s
        upper_limit=pace_to_mps(6, 45, "km"),
    )
    repeats = create_repeat_group(
        iterations=4,
        step_order=2,
        skip_last_rest_step=True,
        workout_steps=[
            create_targeted_distance_interval_step(1000, 3, target=rep_target),
            create_recovery_step(120, 4),
        ],
    )
    return RunningWorkout(
        workoutName="TEST - 4x1km Threshold (Magic Speed 5)",
        description="Feasibility test from marathon app. Safe to delete.",
        estimatedDurationInSecs=50 * 60,
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={"sportTypeId": 1, "sportTypeKey": "running"},
                workoutSteps=[
                    create_warmup_step(600, 1),
                    repeats,
                    create_cooldown_step(600, 5),
                ],
            )
        ],
    )


def login() -> Garmin:
    # login() reuses saved tokens in TOKEN_DIR, else uses email/password and saves tokens there.
    email, password = os.environ.get("GARMIN_EMAIL"), os.environ.get("GARMIN_PASSWORD")
    if not (email and password) and not os.path.isdir(TOKEN_DIR):
        sys.exit("Set GARMIN_EMAIL and GARMIN_PASSWORD environment variables.")
    api = Garmin(email, password, prompt_mfa=lambda: input("Garmin MFA code: "))
    api.login(TOKEN_DIR)
    return api


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--upload", action="store_true")
    p.add_argument("--date", default=(date.today() + timedelta(days=1)).isoformat())
    p.add_argument("--cleanup", action="store_true", help="delete the workout afterwards")
    args = p.parse_args()

    workout = build_workout()
    print(json.dumps(workout.to_dict(), indent=2))
    if not args.upload:
        print("\nDry run OK - workout JSON built. Use --upload to send to Garmin.")
        return

    api = login()
    print(f"\nLogged in as: {api.get_full_name()}")

    created = api.upload_running_workout(workout)
    workout_id = created["workoutId"]
    print(f"Uploaded workout id={workout_id}")

    api.schedule_workout(workout_id, args.date)
    print(f"Scheduled on {args.date} - check the Garmin Connect calendar and sync your watch.")

    if args.cleanup:
        api.delete_workout(workout_id)
        print("Deleted test workout.")


if __name__ == "__main__":
    main()
