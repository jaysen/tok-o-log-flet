"""User settings, read from a TOML file.

The file lives at ``$XDG_CONFIG_HOME/tokolog-flet/config.toml`` (``~/.config`` if unset).
``$TOKOLOG_FLET_CONFIG`` overrides that path, e.g. to use a local file while developing.
It is optional: a missing file or missing keys fall back to the defaults below.
The app edits it by opening it in the default editor, created from ``config.example.toml``
first if missing, and reloads it whenever it changes.
"""

import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

from tokolog_flet.log import (
    DEFAULT_DATE_FORMAT,
    DEFAULT_FILE,
    DEFAULT_LINE_FORMAT,
    DEFAULT_TIME_FORMAT,
    EVENT_NAMES,
    FILE_PLACEHOLDERS,
    LINE_PLACEHOLDERS,
    MODES,
    template_error,
)
from tokolog_flet.sound import FINISH_SOUND

DEFAULT_MINUTES = 25
# A profile's mode when it allows both; also how a profile undoes the default's mode.
ANY_MODE = "any"
# Every setting, commented; ships inside the package.
TEMPLATE = files("tokolog_flet") / "config.example.toml"
# What a profile's [lines] table can be keyed by.
LINE_KEYS = {*EVENT_NAMES, *MODES, *(f"{mode}.{event}" for mode in MODES for event in EVENT_NAMES)}


class ConfigError(Exception):
    """The config file exists but cannot be used."""


def default_log_folder() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "tokolog-flet" / "log"


@dataclass(frozen=True)
class Profile:
    """Timer defaults and log settings: what a profile can set."""

    default_minutes: float = DEFAULT_MINUTES
    # Used when the label field is left empty; blank falls back to the mode.
    default_label: str = ""
    # The only mode the profile allows, countdown or stopwatch; None allows either.
    mode: str | None = None
    log_folder: Path = field(default_factory=default_log_folder)
    log_file: str = DEFAULT_FILE
    log_date_format: str = DEFAULT_DATE_FORMAT
    log_time_format: str = DEFAULT_TIME_FORMAT
    log_line_format: str = DEFAULT_LINE_FORMAT
    # Lines for particular events or modes, as EventLog.lines; the rest use log_line_format.
    log_lines: dict[str, str] = field(default_factory=dict, hash=False)
    # Played when a countdown finishes; None for silence.
    finish_sound: Path | None = FINISH_SOUND

    @property
    def default_seconds(self) -> float:
        return self.default_minutes * 60


DEFAULT_PROFILE = "default"


@dataclass(frozen=True)
class Config(Profile):
    """The default profile (``[profiles.default]``) plus the named ones."""

    profiles: dict[str, Profile] = field(default_factory=dict, hash=False)

    def profile(self, name: str) -> Profile:
        """The named profile; the default one for ``default`` or a name not in the file."""
        return self.profiles.get(name, self)


def config_path() -> Path:
    if override := os.environ.get("TOKOLOG_FLET_CONFIG"):
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "tokolog-flet" / "config.toml"


def create_config(path: Path) -> None:
    """Write the commented template to ``path``, unless a file is already there."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")


def open_in_editor(path: Path) -> None:
    """Open ``path`` in the system's default app for it, without waiting."""
    if sys.platform == "win32":
        os.startfile(path)
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def config_mtime(path: Path) -> int | None:
    """When ``path`` last changed, to notice edits; None if it doesn't exist."""
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def read_settings(path: Path) -> dict[str, Any]:
    """The file's raw contents; empty if it does not exist."""
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from e


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    return parse_config(read_settings(path), path)


def parse_config(data: dict[str, Any], path: Path) -> Config:
    """Validate raw settings; ``path`` is only used for messages and relative folders."""
    tables = _section(data, "profiles", path)
    for name, table in tables.items():
        # "Default" would read as the built-in profile while being a separate one.
        if name != DEFAULT_PROFILE and name.strip().lower() == DEFAULT_PROFILE:
            raise ConfigError(f"{path}: profiles.{name}: the default profile is [profiles.default]")
        if not isinstance(table, dict):
            raise ConfigError(f"{path}: [profiles.{name}] must be a table")

    default = _parse_profile(tables.get(DEFAULT_PROFILE, {}), Profile(), DEFAULT_PROFILE, path)
    # The others override the default profile, not the built-in values.
    profiles = {
        name: _parse_profile(table, default, name, path)
        for name, table in tables.items()
        if name != DEFAULT_PROFILE
    }
    return Config(**vars(default), profiles=profiles)


def _parse_profile(table: dict[str, Any], base: Profile, name: str, path: Path) -> Profile:
    """``base`` with whatever ``table``, the profile called ``name``, sets."""
    prefix = f"profiles.{name}."
    minutes = table.get("default_minutes", base.default_minutes)
    # bool is an int subclass, so `true` would otherwise pass as 1 minute.
    if isinstance(minutes, bool) or not isinstance(minutes, int | float) or minutes <= 0:
        raise ConfigError(f"{path}: {prefix}default_minutes must be a positive number")

    label = table.get("default_label", base.default_label)
    if not isinstance(label, str):
        raise ConfigError(f"{path}: {prefix}default_label must be a string")

    mode = table.get("mode", base.mode or ANY_MODE)
    if mode not in (*MODES, ANY_MODE):
        raise ConfigError(f"{path}: {prefix}mode must be {', '.join(MODES)} or {ANY_MODE}")

    folder = table.get("folder")
    if folder is None:
        log_folder = base.log_folder
    elif isinstance(folder, str) and folder:
        # Relative paths are taken from the config file's folder, not wherever the app runs.
        log_folder = path.parent / Path(folder).expanduser()
    else:
        raise ConfigError(f"{path}: {prefix}folder must be a non-empty string")

    file = table.get("file", base.log_file)
    if not _is_filename(file):
        raise ConfigError(f"{path}: {prefix}file must be a non-empty file name, without folders")
    _check_template(file, f"{prefix}file", FILE_PLACEHOLDERS, path)
    # The date ends up in the file name, so it follows the same rules.
    date_format = table.get("date_format", base.log_date_format)
    if not _is_filename(date_format):
        raise ConfigError(
            f"{path}: {prefix}date_format must be a non-empty string, without / or \\"
        )

    time_format = table.get("time_format", base.log_time_format)
    if not isinstance(time_format, str) or not time_format:
        raise ConfigError(f"{path}: {prefix}time_format must be a non-empty string")

    line_format = table.get("line_format", base.log_line_format)
    if not isinstance(line_format, str):
        raise ConfigError(f"{path}: {prefix}line_format must be a string")
    _check_template(line_format, f"{prefix}line_format", LINE_PLACEHOLDERS, path)
    lines = _parse_lines(table, base, prefix, path)

    sound = table.get("finish_sound")
    if sound is None:
        finish_sound = base.finish_sound
    elif sound is True:
        finish_sound = FINISH_SOUND
    elif sound is False:
        finish_sound = None
    elif isinstance(sound, str) and sound:
        # Relative paths are taken from the config file's folder, like folder.
        finish_sound = path.parent / Path(sound).expanduser()
    else:
        raise ConfigError(f"{path}: {prefix}finish_sound must be true, false or a file path")

    return Profile(
        default_minutes=minutes,
        default_label=label.strip(),
        mode=None if mode == ANY_MODE else mode,
        log_folder=log_folder,
        log_file=file,
        log_date_format=date_format,
        log_time_format=time_format,
        log_line_format=line_format,
        log_lines=lines,
        finish_sound=finish_sound,
    )


def _parse_lines(table: dict[str, Any], base: Profile, prefix: str, path: Path) -> dict[str, str]:
    """The profile's ``lines`` table, keyed ``stop``, ``countdown`` or ``countdown.stop``."""
    if "lines" not in table:
        # A profile that sets its own line_format means it for every event, rather than
        # keeping lines it inherited from the default profile.
        return {} if "line_format" in table else base.log_lines
    raw = table["lines"]
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: [{prefix}lines] must be a table")
    lines: dict[str, str] = {}
    for key, value in raw.items():
        # Unquoted, countdown.stop = "..." is a table in TOML: countdown = {stop = "..."}.
        if key in MODES and isinstance(value, dict):
            items = [(f"{key}.{event}", line) for event, line in value.items()]
        else:
            items = [(key, value)]
        for name, line in items:
            if name not in LINE_KEYS:
                raise ConfigError(
                    f"{path}: {prefix}lines.{name}: not an event ({', '.join(EVENT_NAMES)}), "
                    f"a mode ({', '.join(MODES)}) or mode.event"
                )
            if not isinstance(line, str):
                raise ConfigError(f"{path}: {prefix}lines.{name} must be a string")
            _check_template(line, f"{prefix}lines.{name}", LINE_PLACEHOLDERS, path)
            lines[name] = line
    return lines


def _check_template(template: str, key: str, placeholders: tuple[str, ...], path: Path) -> None:
    if error := template_error(template, placeholders):
        known = ", ".join(f"{{{name}}}" for name in placeholders)
        raise ConfigError(f"{path}: {key}: {error} (available: {known})")


def _is_filename(value: object) -> bool:
    return isinstance(value, str) and bool(value) and not any(c in value for c in "/\\")


def _section(data: dict[str, Any], name: str, path: Path) -> dict[str, Any]:
    section = data.get(name, {})
    if not isinstance(section, dict):
        raise ConfigError(f"{path}: [{name}] must be a table")
    return section
