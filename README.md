# Tok-o-log (flet)

Functional play with [Flet UI](https://flet.dev) - a desktop timer that logs, in a very configurable format, to a configurable file. 
In my case, I use this for task tracking in journals and project notes within my personal software-eng wiki.

## Features

- **Timer + stopwatch modes** with quick mode switching.
- **Flexible countdown input** (`25`, `1:30`, `1:00:00`, `1h30m`) and inline editing.
- **Start / pause / resume / stop / reset flow** with elapsed/display time tracking. Stop
  ends the run but keeps its time on show; Reset then clears it.
- **Finish sound** when a countdown ends: six built-in chimes and alarms or your own
  `.wav`, set per profile, optionally repeating for a set time.
- **Compact view toggle** for a minimal always-visible timer window.
- **Editable label** per session, used in log output.
- **Named profiles**, each with its own log file, line formats, countdown default, label
  and, if wanted, a single mode (e.g. a timer-only pomodoro profile).
- **Settings in a TOML file**: the gear opens it in your editor, and saving applies it.
- **Daily log files** with templated file names and line formats.
- **Customizable placeholders** for `{date}`, `{time}`, `{mode}`, `{event}`, `{elapsed}`, `{display}`, `{label}`, `{profile}`, session times and countdown details.
- **Per-event lines**: different lines for start, stop and the rest, per mode if wanted, or none at all.


## Setup

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh   # if uv is not installed
uv sync                                           # creates .venv, installs Python 3.12 if needed

uv run pre-commit install                         # .pre-commit-config.yaml  
```

Open the folder in VS Code and accept the recommended extensions; the interpreter is
preselected as `.venv`.

## Run

```sh
uv run flet run src/tokolog_flet/main.py   # hot reload while developing
uv run tokolog-flet                        # plain run via entry point
```

Or press F5 in VS Code ("Flet: run app").

To set the countdown, click its time and type e.g. `25` (minutes), `1:30`, `1:00:00` or
`1h30m`, then press Enter (Esc cancels). It starts at the profile's `default_minutes` from the config.

The shrink icon next to the gear switches to a compact view that shows just the
label, time and Start/Stop buttons, e.g. to keep a running timer in a corner. The same button
(now an expand icon) brings back the full view.

## Config

Optional. Settings are read from `~/.config/tokolog-flet/config.toml`
(or `$XDG_CONFIG_HOME/tokolog-flet/config.toml`); anything left out uses the default.

The gear icon in the top bar opens the file in your default editor. If there is no file
yet, it is first created from [config.example.toml](src/tokolog_flet/config.example.toml),
which lists every setting with comments. Saving the file applies it straight away; the app
watches it for changes. If a save leaves the file unusable, e.g. an unknown placeholder,
the app keeps the last good settings and shows the problem in a red bar until the file is
fixed. Clicking the bar opens the file again. A broken file at startup works the same way,
with the defaults standing in.

To use a different file, e.g. a local one while developing (`config.toml` is gitignored):

```sh
TOKOLOG_FLET_CONFIG=config.toml uv run tokolog-flet
```

## Log

Every start, pause, resume, stop and finish is appended to a file per day in the log folder
(`~/.local/share/tokolog-flet/log/` unless the profile sets `folder` in the config):

```text
09:30:05  countdown  start   00:00
09:42:17  countdown  pause   12:12
09:55:05  countdown  finish  25:00
```

The last column is how much time had run when the event happened.

The file name defaults to `2026-10-21.log`. To change it, e.g. to `flet-20261021.md`:

```toml
[profiles.default]
file = "flet-{date}.md"
date_format = "YYYYMMDD"   # YYYY, YY, MM and DD are replaced
time_format = "HH:mm"      # HH, hh (12-hour), mm, ss and AM (AM/PM) are replaced
line_format = "- {time} {mode} {event} {display}"
```

`line_format` can use:

| Placeholder | Value |
| --- | --- |
| `{date}`, `{time}` | when the event happened, in `date_format` / `time_format` |
| `{mode}`, `{event}` | `countdown` or `stopwatch`; `start`, `pause`, `resume`, `stop` or `finish` |
| `{elapsed}` | time run so far, pauses left out (`MM:SS` / `H:MM:SS`; not affected by `time_format`) |
| `{elapsed_minutes}` | elapsed time as decimal minutes, e.g. `90` |
| `{elapsed_hours}` | elapsed time as decimal hours, e.g. `1.5` |
| `{display}` | what the timer showed, so time left for a countdown |
| `{label}` | the label typed in the app, else the profile's `default_label`, else the mode |
| `{profile}` | the profile picked in the app |
| `{timer_minutes}` | the countdown's length in minutes, e.g. `25` (blank for a stopwatch) |
| `{timer_clock}` | the countdown's length in timer format, e.g. `25:00` (blank for a stopwatch) |
| `{timer_remaining}` | the countdown's time left (blank for a stopwatch) |
| `{started}` | clock time the session started, in `time_format` |
| `{since_start}` | time since the start, pauses included |
| `{paused}` | time spent paused (`{since_start}` minus `{elapsed}`) |

`file` can use `{date}`, `{label}` and `{profile}`. See
[config.example.toml](src/tokolog_flet/config.example.toml) for details.

To log different lines for particular events or modes, add a `lines` table to the
profile. Keys are an event (`start`, `pause`, `resume`, `stop`, `finish`), a mode
(`countdown`, `stopwatch`) or both (`countdown.stop`). The most specific match wins,
and events without one use `line_format`. An empty line means the event isn't logged:

```toml
[profiles.default]
line_format = "- {time} {event} {label}"

[profiles.default.lines]
start = "- {time} ▶ {label}"
stop = "- {started}-{time} {label} ran {elapsed}, paused {paused}"
countdown.start = "- {time} ▶ {label} ({timer_minutes}m)"
countdown.finish = "- {started}-{time} ✓ {label} {timer_minutes}m done"
pause = ""    # not logged
resume = ""
```

Skipped events still count, so the stop line above includes the pauses it didn't log.
A profile's own `lines` table replaces the default profile's, and a profile that sets
its own `line_format` takes no lines from `[profiles.default]`.

## Profiles

A profile is a named set of log settings, e.g. one for your journal and one for a work
timesheet. The label stays separate, so any label can be logged under any profile.
Every profile is a `[profiles.<name>]` table with the same keys. `[profiles.default]`
is the base: the app uses it until you pick another, and the others take whatever they
leave out from it:

```toml
[profiles.work]
default_minutes = 50
default_label = "admin"   # logged when the label field is empty
mode = "stopwatch"        # only the stopwatch; "countdown" for only the timer
folder = "~/work/timesheets"
file = "timesheet-{date}.csv"
line_format = "{date},{time},{label},{event},{elapsed}"
```

Once the config has a profile besides `default`, a picker appears at the bottom of the
window. It is locked while a timer runs or is paused, so a session stays in one log.
Switching changes where the next events go, and an untouched countdown takes the
profile's default minutes.

A profile with a `mode` switches to it and locks the Timer/Stopwatch switch.
`mode = "any"` allows both again, for a profile whose default sets one. If a timer is
running or paused when the mode changes, e.g. after editing the config, it switches once
that timer is stopped.

For example, a pomodoro profile: 25-minute focus blocks, timer only, with a line for each
block started, finished or given up, and pauses left out:

```toml
[profiles.pomodoro]
mode = "countdown"
default_minutes = 25
default_label = "focus"
time_format = "HH:mm"
line_format = "- {time} {event} {label} {elapsed}"

[profiles.pomodoro.lines]
countdown.start  = "- {time} 🍅 {label}"
countdown.finish = "- {time} 🍅 ✓ {label} ({timer_minutes} min)"
countdown.stop   = "- {time} 🍅 ✗ {label}: gave up with {timer_remaining} left"
pause  = ""
resume = ""
```

which logs, for one finished block and one cut short:

```
- 09:00 🍅 focus
- 09:25 🍅 ✓ focus (25 min)
- 09:30 🍅 report
- 09:41 🍅 ✗ report: gave up with 14:00 left
```

### Finish sound

A countdown plays a chime when it finishes. `finish_sound` picks another, in any profile:

```toml
[profiles.pomodoro]
finish_sound = "chime"    # three rising soft notes; the default, same as true
# finish_sound = "bell"   # two bell strikes
# finish_sound = "ding"   # a short, bright two-note ding
# finish_sound = "beep"   # three plain digital beeps
# finish_sound = "alarm"  # a fast two-tone alarm, the hardest to miss
# finish_sound = "gong"   # one long, low gong
# finish_sound = "~/sounds/done.wav"  # your own .wav file
# finish_sound = false    # no sound
```

The sound plays once unless `finish_sound_seconds` says how long to keep repeating it.
Reset, Start or switching to the stopwatch stops it sooner:

```toml
[profiles.pomodoro]
finish_sound = "alarm"
finish_sound_seconds = 30   # repeat for 30 seconds; 0, the default, plays it once
```

A relative path is taken from the config file's folder. Sounds play through the
system's player: `pw-play`, `paplay` or `aplay` on Linux, `afplay` on macOS.

The app reopens on the profile picked last, which it remembers in
`~/.local/state/tokolog-flet/state.json`. [config.example.toml](src/tokolog_flet/config.example.toml)
has ready-made profiles to start from: a Markdown journal, a one-line-per-session
summary, a CSV timesheet and a pomodoro.

## Check

```sh
uv run ruff format . && uv run ruff check . && uv run pyright && uv run pytest
```

`pre-commit` runs the same checks on commit, using the versions pinned in `uv.lock`.