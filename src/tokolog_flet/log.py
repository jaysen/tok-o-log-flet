"""Activity log: one line per timer event, in a file named after the date.

The file name and line are ``str.format`` templates, so ``{mode:<9}`` pads and
``{{`` / ``}}`` give literal braces.

Events are worked out from state changes, so the UI only has to report the timer's
state before and after each action, and on every tick.
"""

import os
import re
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tokolog_flet.timer import Countdown, State, Stopwatch, format_seconds

if TYPE_CHECKING:
    from tokolog_flet.config import Profile

DEFAULT_DATE_FORMAT = "YYYY-MM-DD"
DEFAULT_TIME_FORMAT = "HH:mm:ss"
DEFAULT_FILE = "{date}.log"
DEFAULT_LINE_FORMAT = "{time}  {mode:<9}  {event:<6}  {elapsed}"

DATE_TOKENS = re.compile("YYYY|YY|MM|DD")
TIME_TOKENS = re.compile("HH|hh|mm|ss|AM")
FILE_PLACEHOLDERS = ("date", "label", "profile")
# display is what the timer showed: remaining time for a countdown, elapsed for a stopwatch.
# The timer_ ones are blank for a stopwatch. started is the clock time of the start;
# since_start is the time since then, pauses included, and paused the part spent paused.
LINE_PLACEHOLDERS = (
    "date",
    "time",
    "mode",
    "event",
    "elapsed",
    "elapsed_hours",
    "display",
    "label",
    "profile",
    "timer_minutes",
    "timer_clock",
    "timer_remaining",
    "started",
    "since_start",
    "paused",
)

MODES = ("countdown", "stopwatch")
EVENT_NAMES = ("start", "pause", "resume", "stop", "finish")
EVENTS: dict[tuple[State, State], str] = {
    (State.IDLE, State.RUNNING): "start",
    (State.PAUSED, State.RUNNING): "resume",
    (State.RUNNING, State.PAUSED): "pause",
    (State.RUNNING, State.IDLE): "stop",
    (State.PAUSED, State.IDLE): "stop",
    (State.RUNNING, State.STOPPED): "stop",
    (State.PAUSED, State.STOPPED): "stop",
    (State.RUNNING, State.FINISHED): "finish",
}


def format_date(date_format: str, day: date) -> str:
    """Replace YYYY, YY, MM and DD, e.g. ``YYYY-MM-DD`` -> ``2026-10-21``."""
    tokens = {"YYYY": f"{day:%Y}", "YY": f"{day:%y}", "MM": f"{day:%m}", "DD": f"{day:%d}"}
    return DATE_TOKENS.sub(lambda m: tokens[m[0]], date_format)


def format_time(time_format: str, moment: datetime) -> str:
    """Replace HH, hh (12-hour), mm, ss and AM (AM or PM), e.g. ``HH:mm`` -> ``14:05``."""
    tokens = {
        "HH": f"{moment:%H}",
        "hh": f"{moment:%I}",
        "mm": f"{moment:%M}",
        "ss": f"{moment:%S}",
        "AM": "AM" if moment.hour < 12 else "PM",
    }
    return TIME_TOKENS.sub(lambda m: tokens[m[0]], time_format)


def template_error(template: str, placeholders: Iterable[str]) -> str | None:
    """Why ``template`` can't be filled from ``placeholders``, or None if it can."""
    try:
        template.format(**dict.fromkeys(placeholders, ""))
    except KeyError as e:
        return f"unknown placeholder {{{e.args[0]}}}"
    except IndexError:
        return "empty placeholder {}"
    except (ValueError, AttributeError) as e:
        return str(e)
    return None


def log_filename(file: str, date_format: str, day: date, label: str = "", profile: str = "") -> str:
    """Fill ``file``'s placeholders, e.g. ``flet-{date}.md`` -> ``flet-2026-10-21.md``."""
    return file.format(
        date=format_date(date_format, day), label=_safe(label), profile=_safe(profile)
    )


def _safe(text: str) -> str:
    """Free text for a file name; keep it from turning the name into a path."""
    return text.replace("/", "-").replace("\\", "-")


class EventLog:
    """Appends a line per event to a dated file in ``folder``.

    ``lines`` can give the line for an event (``stop``), a mode (``countdown``) or both
    (``countdown.stop``); the most specific wins, else ``line_format``. An empty line
    means the event isn't logged.
    """

    def __init__(
        self,
        folder: Path,
        file: str = DEFAULT_FILE,
        date_format: str = DEFAULT_DATE_FORMAT,
        time_format: str = DEFAULT_TIME_FORMAT,
        line_format: str = DEFAULT_LINE_FORMAT,
        now: Callable[[], datetime] = datetime.now,
        profile: str = "",
        lines: dict[str, str] | None = None,
    ) -> None:
        self.folder = folder
        self.file = file
        self.date_format = date_format
        self.time_format = time_format
        self.line_format = line_format
        self.now = now
        self.profile = profile
        self.lines = lines or {}
        self._seen: dict[str, tuple[State, float, str]] = {}
        # When each mode's running session started, by the wall clock.
        self._started: dict[str, datetime] = {}

    def use_profile(self, profile: "Profile", name: str) -> None:
        """Take the log settings of ``profile``, called ``name``.

        Same log object, so a running timer isn't taken for a fresh start.
        """
        self.folder = profile.log_folder
        self.file = profile.log_file
        self.date_format = profile.log_date_format
        self.time_format = profile.log_time_format
        self.line_format = profile.log_line_format
        self.lines = profile.log_lines
        self.profile = name

    def update(self, mode: str, timer: Stopwatch, label: str = "") -> str | None:
        """Log the event since the last update, if any, and return it.

        Raises OSError if the line can't be written; the event is not retried.
        """
        seen = timer.state, timer.elapsed, timer.display()
        before = self._seen.get(mode, (State.IDLE, 0.0, ""))
        self._seen[mode] = seen
        if event := EVENTS.get((before[0], seen[0])):
            # A stop by reset has already zeroed the timer, so report the time it had reached.
            _, elapsed, display = before if seen[0] is State.IDLE else seen
            self._write(mode, event, elapsed, display, label, timer)
        return event

    def _write(
        self, mode: str, event: str, elapsed: float, display: str, label: str, timer: Stopwatch
    ) -> None:
        stamp = self.now()
        countdown = isinstance(timer, Countdown)
        if event == "start":
            self._started[mode] = stamp
        # The session ends here, but this line still reports on it.
        started = (
            self._started.pop(mode, None)
            if event in ("stop", "finish")
            else self._started.get(mode)
        )
        since = (stamp - started).total_seconds() if started else None
        # Skipped events still count above, so a stop line can report on the whole session.
        if not (line_format := self.line_format_for(mode, event)):
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / log_filename(self.file, self.date_format, stamp, label, self.profile)
        line = line_format.format(
            date=format_date(self.date_format, stamp),
            time=format_time(self.time_format, stamp),
            mode=mode,
            event=event,
            elapsed=format_seconds(elapsed),
            elapsed_hours=f"{elapsed / 3600:g}",
            display=display,
            label=label,
            profile=self.profile,
            # Minutes as a plain number, like default_minutes: 25, or 1.5 for 1:30.
            timer_minutes=f"{timer.duration / 60:g}" if countdown else "",
            # Duration in timer display format, e.g. 25:00 or 1:30:00.
            timer_clock=format_seconds(timer.duration) if countdown else "",
            timer_remaining=display if countdown else "",
            started=format_time(self.time_format, started) if started else "",
            since_start=format_seconds(since) if since is not None else "",
            # Wall clock and timer clock can differ by a hair; never show a negative pause.
            paused=format_seconds(max(0.0, since - elapsed)) if since is not None else "",
        )
        line += "\n"
        # The file may be a note edited by hand; don't glue the line onto its last one.
        if not _ends_with_newline(path):
            line = "\n" + line
        with path.open("a", encoding="utf-8") as f:
            f.write(line)

    def line_format_for(self, mode: str, event: str) -> str:
        for key in (f"{mode}.{event}", event, mode):
            if key in self.lines:
                return self.lines[key]
        return self.line_format


def _ends_with_newline(path: Path) -> bool:
    """True for a missing or empty file too: nothing to separate from."""
    try:
        with path.open("rb") as f:
            if f.seek(0, os.SEEK_END) == 0:
                return True
            f.seek(-1, os.SEEK_END)
            return f.read(1) == b"\n"
    except FileNotFoundError:
        return True
