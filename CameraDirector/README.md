# Camera Director

An Android app that records video on its own from a timed **shot script**:
start recording, wait, zoom in over N seconds, hold, zoom back out, stop. Put the phone
on a tripod, press Start, and walk away.

## v1 features
- Shot scripts made of steps: **Start recording**, **Zoom** (level, duration, linear/smooth easing),
  **Hold**, **Refocus (center)**, **Stop recording**.
- Presets: "Zoom in, then out", "Slow push-in", "Punch zoom", "Breathing zoom". Create, edit, copy, delete your own.
- Start **now**, after a **countdown** (3–300 s), or **at a clock time**.
- Live preview with REC indicator, current/next step, progress and an emergency STOP.
- Tap-to-focus and a manual zoom slider before starting.
- Videos are saved as MP4 (1080p, falls back to 720p) in `Movies/CameraDirector`.

## Getting the APK
Every push that touches `CameraDirector/` runs the **Build Camera Director APK** workflow.
Open the repo's **Actions** tab → latest run → download the **CameraDirector-apk** artifact
(a zip containing `app-debug.apk`), then install it on the phone (allow "install unknown apps").

The APK is signed with the committed `app/debug.keystore`, so newer builds install over older ones.

## Notes
- Requires Android 10+.
- Keep the app open on screen while a script runs (the screen stays on). Android doesn't let apps use the camera from the background.
- Zoom is always centred; zoom levels beyond what the phone supports are clamped.

## Build locally
```
cd CameraDirector
./gradlew assembleDebug
```
