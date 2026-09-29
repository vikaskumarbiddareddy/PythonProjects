# Goggin – Habit Tracker

Progress log for the Goggin app. Updated as the app develops.

## Goal
Build a habit tracker with colorful dot grids, streaks and a calendar history, first as a single HTML prototype, then wrapped into an Android/iPhone app.

## Project files
| File | What it is |
|---|---|
| `goggin.html` | The working prototype (one file: HTML, CSS and JavaScript) |
| `PROGRESS.md` | This log |
| `README.md` | Short overview of the project |

## Current features (v0.1)
- Habit cards with icon, name, description and a dot grid of recent weeks
- One-tap check button to mark a habit done today
- Goals: every day, or a set number of days per week (1–7)
- Streaks: current streak, best streak, total days done
- Detail sheet: mark done, calendar, edit, archive, delete (with confirm)
- Calendar: tap past days to add or remove completions
- Editor with 21 icons and 21 colors
- Quick-start suggestions when there are no habits yet
- Archive and restore habits
- Dark theme by default, light theme when the phone uses light mode
- Data saved on the device (localStorage key `goggin-v1`)

## Data model
```json
{
  "habits": [
    {
      "id": "string",
      "name": "Read",
      "desc": "At least 10 pages",
      "icon": "book",
      "color": "#a78bfa",
      "goal": { "type": "day | week", "n": 3 },
      "done": ["2026-09-29", "2026-09-28"],
      "archived": false,
      "created": 1759100000000
    }
  ],
  "updated": 1759100000000
}
```

## To do
- [ ] Share card (image of a habit's grid to send to friends)
- [ ] Reminders / notifications (needs the phone app stage)
- [ ] Home screen widget (phone app stage)
- [ ] Reorder habits
- [ ] Settings screen (theme switch, export/import backup)
- [ ] Wrap into a phone app with Capacitor (Android first, then iOS)

## Changelog
### 2026-09-29
- Collected design references (6 screenshots) for the dot-grid style, calendar, editor and share screens.
- Named the app **Goggin**.
- Built v0.1 prototype with all features listed above.
- Briefly hosted it as a claude.ai artifact, then switched to a local development file only: removed Claude account sync, data now saves on-device.
- Created the `goggin-app` folder and this progress log.
- Added the project to the `PythonProjects` GitHub repo in the `goggin-app` folder.
