from pathlib import Path

import pytest

from tokolog_flet.config import (
    DEFAULT_MINUTES,
    Config,
    ConfigError,
    Profile,
    config_mtime,
    config_path,
    create_config,
    load_config,
    parse_config,
    read_settings,
)
from tokolog_flet.sound import FINISH_SOUND


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_missing_file_uses_defaults(tmp_path: Path) -> None:
    assert load_config(tmp_path / "nope.toml") == Config()
    assert Config().default_minutes == DEFAULT_MINUTES


def test_missing_key_uses_default(tmp_path: Path) -> None:
    assert load_config(write(tmp_path, "[profiles.default]\n")) == Config()


def test_reads_default_minutes(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, "[profiles.default]\ndefault_minutes = 25\n"))
    assert config.default_minutes == 25
    assert config.default_seconds == 1500


def test_accepts_fractional_minutes(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, "[profiles.default]\ndefault_minutes = 1.5\n"))
    assert config.default_seconds == 90


@pytest.mark.parametrize("value", ["0", "-1", '"25"', "true"])
def test_rejects_invalid_minutes(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError, match=r"profiles\.default\.default_minutes"):
        load_config(write(tmp_path, f"[profiles.default]\ndefault_minutes = {value}\n"))


def test_rejects_malformed_toml(tmp_path: Path) -> None:
    path = write(tmp_path, "[timer\n")
    with pytest.raises(ConfigError, match=str(path)):
        load_config(path)


@pytest.fixture(autouse=True)
def no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOKOLOG_FLET_CONFIG", raising=False)


def test_config_path_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("TOKOLOG_FLET_CONFIG", str(tmp_path / "dev.toml"))
    assert config_path() == tmp_path / "dev.toml"


def test_config_path_honours_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_path() == tmp_path / "tokolog-flet" / "config.toml"


def test_config_path_falls_back_to_dot_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert config_path() == Path.home() / ".config" / "tokolog-flet" / "config.toml"


def test_log_folder_defaults_to_xdg_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert load_config(tmp_path / "nope.toml").log_folder == tmp_path / "tokolog-flet" / "log"


def test_log_folder_relative_to_config_file(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, '[profiles.default]\nfolder = "logs"\n'))
    assert config.log_folder == tmp_path / "logs"


def test_log_folder_expands_home(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, '[profiles.default]\nfolder = "~/wiki/log"\n'))
    assert config.log_folder == Path.home() / "wiki" / "log"


@pytest.mark.parametrize("value", ['""', "5"])
def test_rejects_invalid_log_folder(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError, match=r"profiles\.default\.folder"):
        load_config(write(tmp_path, f"[profiles.default]\nfolder = {value}\n"))


def test_log_file_and_date_format_default(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nope.toml")
    assert (config.log_file, config.log_date_format) == ("{date}.log", "YYYY-MM-DD")


def test_reads_log_file_and_date_format(tmp_path: Path) -> None:
    config = load_config(
        write(tmp_path, '[profiles.default]\nfile = "flet-{date}.md"\ndate_format = "YYYYMMDD"\n')
    )
    assert (config.log_file, config.log_date_format) == ("flet-{date}.md", "YYYYMMDD")


@pytest.mark.parametrize("value", ['""', '"logs/{date}.md"', "5"])
def test_rejects_invalid_log_file(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError, match=r"profiles\.default\.file"):
        load_config(write(tmp_path, f"[profiles.default]\nfile = {value}\n"))


def test_rejects_unknown_placeholder(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"profiles\.default\.file: unknown placeholder \{dat\}"):
        load_config(write(tmp_path, '[profiles.default]\nfile = "flet-{dat}.md"\n'))


def test_line_format_default(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nope.toml")
    assert config.log_line_format == "{time}  {mode:<9}  {event:<6}  {elapsed}"


def test_accepts_label_placeholder(tmp_path: Path) -> None:
    config = load_config(
        write(tmp_path, '[profiles.default]\nfile = "{date}-{label}.md"\nline_format = "{label}"\n')
    )
    assert (config.log_file, config.log_line_format) == ("{date}-{label}.md", "{label}")


def test_reads_line_format(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, '[profiles.default]\nline_format = " - {time} {event}"\n'))
    assert config.log_line_format == " - {time} {event}"


@pytest.mark.parametrize(
    ("value", "error"),
    [
        ('"{state}"', r"unknown placeholder \{state\}"),
        ('"{time"', "expected '}'"),
        ("5", "must be a string"),
    ],
)
def test_rejects_invalid_line_format(tmp_path: Path, value: str, error: str) -> None:
    with pytest.raises(ConfigError, match=rf"profiles\.default\.line_format.*{error}"):
        load_config(write(tmp_path, f"[profiles.default]\nline_format = {value}\n"))


@pytest.mark.parametrize("value", ['""', '"YYYY/MM-DD"', "5"])
def test_rejects_invalid_date_format(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError, match=r"profiles\.default\.date_format"):
        load_config(write(tmp_path, f"[profiles.default]\ndate_format = {value}\n"))


def test_time_format_default(tmp_path: Path) -> None:
    assert load_config(tmp_path / "nope.toml").log_time_format == "HH:mm:ss"


def test_reads_time_format(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, '[profiles.default]\ntime_format = "hh:mm AM"\n'))
    assert config.log_time_format == "hh:mm AM"


@pytest.mark.parametrize("value", ['""', "5"])
def test_rejects_invalid_time_format(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError, match=r"profiles\.default\.time_format"):
        load_config(write(tmp_path, f"[profiles.default]\ntime_format = {value}\n"))


def test_read_settings_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_settings(tmp_path / "nope.toml") == {}


def test_parse_config_validates_in_memory(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"profiles\.default\.file"):
        parse_config({"profiles": {"default": {"file": "a/b"}}}, tmp_path / "config.toml")


def test_no_profiles_by_default(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nope.toml")
    assert config.profiles == {}
    assert config.profile("default") is config


def test_profile_overrides_default(tmp_path: Path) -> None:
    config = load_config(
        write(
            tmp_path,
            "[profiles.default]\ndefault_minutes = 25\n"
            'file = "{date}.md"\nline_format = "- {time} {event}"\n'
            '[profiles.work]\ndefault_minutes = 50\nfolder = "work"\nfile = "work-{date}.csv"\n',
        )
    )
    work = config.profile("work")
    assert (work.default_minutes, work.log_folder, work.log_file) == (
        50,
        tmp_path / "work",
        "work-{date}.csv",
    )
    # What the profile leaves out comes from the default profile, not the built-in values.
    assert work.log_line_format == "- {time} {event}"
    assert config.profile("missing") is config


def test_empty_profile_matches_default(tmp_path: Path) -> None:
    config = load_config(
        write(tmp_path, '[profiles.default]\nfile = "{date}.md"\n[profiles.focus]\n')
    )
    assert config.profile("focus") == Profile(log_file="{date}.md")


def test_profile_error_names_profile_key(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"profiles\.work\.line_format: unknown placeholder"):
        load_config(write(tmp_path, '[profiles.work]\nline_format = "{nope}"\n'))
    with pytest.raises(ConfigError, match=r"profiles\.work\.default_minutes"):
        load_config(write(tmp_path, "[profiles.work]\ndefault_minutes = 0\n"))


@pytest.mark.parametrize("text", ["profiles = 1\n", "[profiles]\nwork = 1\n"])
def test_rejects_non_table_profiles(tmp_path: Path, text: str) -> None:
    with pytest.raises(ConfigError, match=r"\[profiles"):
        load_config(write(tmp_path, text))


def test_rejects_default_as_profile_name(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"profiles\.Default: the default profile"):
        load_config(write(tmp_path, "[profiles.Default]\n"))


def test_default_label(tmp_path: Path) -> None:
    config = load_config(
        write(tmp_path, '[profiles.default]\ndefault_label = " journal "\n[profiles.work]\n')
    )
    assert config.default_label == "journal"
    assert config.profile("work").default_label == "journal"
    assert Config().default_label == ""
    with pytest.raises(ConfigError, match=r"profiles\.default\.default_label"):
        load_config(write(tmp_path, "[profiles.default]\ndefault_label = 5\n"))


def test_lines(tmp_path: Path) -> None:
    config = load_config(
        write(
            tmp_path,
            "[profiles.default.lines]\n"
            'stop = "{event} {elapsed}"\n'
            'pause = ""\n'
            '"countdown.start" = "{timer_minutes}m"\n'
            '"countdown.stop" = "{timer_clock} left"\n'
            'resume = "{elapsed_hours}h elapsed"\n'
            'stopwatch.finish = "done"\n'  # unquoted: a nested table in TOML
            "[profiles.focus]\n"
            '[profiles.work]\nline_format = "{event}"\n'
            '[profiles.mixed]\nline_format = "{event}"\n[profiles.mixed.lines]\nresume = ""\n',
        )
    )
    expected = {
        "stop": "{event} {elapsed}",
        "pause": "",
        "countdown.start": "{timer_minutes}m",
        "countdown.stop": "{timer_clock} left",
        "resume": "{elapsed_hours}h elapsed",
        "stopwatch.finish": "done",
    }
    assert Config().log_lines == {}
    assert config.log_lines == expected
    assert config.profile("focus").log_lines == expected
    # Its own line_format replaces the lines it would otherwise inherit.
    assert config.profile("work").log_lines == {}
    assert config.profile("mixed").log_lines == {"resume": ""}


@pytest.mark.parametrize(
    ("lines", "error"),
    [
        ('halt = ""', r"lines\.halt: not an event"),
        ('"countdown.halt" = ""', r"lines\.countdown\.halt: not an event"),
        ("stop = 5", r"lines\.stop must be a string"),
        ('stop = "{nope}"', r"lines\.stop: unknown placeholder"),
    ],
)
def test_rejects_invalid_lines(tmp_path: Path, lines: str, error: str) -> None:
    with pytest.raises(ConfigError, match=rf"profiles\.default\.{error}"):
        load_config(write(tmp_path, f"[profiles.default.lines]\n{lines}\n"))


def test_rejects_non_table_lines(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"\[profiles\.default\.lines\] must be a table"):
        load_config(write(tmp_path, '[profiles.default]\nlines = "x"\n'))


def test_create_config_writes_template_once(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "config.toml"
    create_config(path)
    assert "[profiles.default]" in path.read_text()
    assert load_config(path) == Config()  # the template only shows the defaults
    path.write_text("# mine\n")
    create_config(path)
    assert path.read_text() == "# mine\n"


def test_config_mtime(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    assert config_mtime(path) is None
    path.write_text("")
    assert config_mtime(path) == path.stat().st_mtime_ns


def test_mode(tmp_path: Path) -> None:
    config = load_config(
        write(
            tmp_path,
            '[profiles.default]\nmode = "stopwatch"\n'
            "[profiles.inherits]\n"
            '[profiles.pomodoro]\nmode = "countdown"\n'
            '[profiles.free]\nmode = "any"\n',
        )
    )
    assert Config().mode is None
    assert config.mode == "stopwatch"
    assert config.profile("inherits").mode == "stopwatch"
    assert config.profile("pomodoro").mode == "countdown"
    assert config.profile("free").mode is None


@pytest.mark.parametrize("value", ['"timer"', '""', "5"])
def test_rejects_invalid_mode(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError, match=r"profiles\.default\.mode must be countdown, stopwatch"):
        load_config(write(tmp_path, f"[profiles.default]\nmode = {value}\n"))


def test_finish_sound_defaults_to_the_chime(tmp_path: Path) -> None:
    assert load_config(write(tmp_path, "")).finish_sound == FINISH_SOUND
    assert FINISH_SOUND.is_file()


def test_finish_sound_can_be_turned_off_per_profile(tmp_path: Path) -> None:
    config = load_config(
        write(tmp_path, "[profiles.default]\nfinish_sound = false\n[profiles.quiet]\n")
    )
    assert config.finish_sound is None
    assert config.profile("quiet").finish_sound is None


def test_finish_sound_path_is_relative_to_config(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, '[profiles.default]\nfinish_sound = "ding.wav"\n'))
    assert config.finish_sound == tmp_path / "ding.wav"


@pytest.mark.parametrize("value", ['""', "1"])
def test_rejects_invalid_finish_sound(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError, match=r"profiles\.default\.finish_sound"):
        load_config(write(tmp_path, f"[profiles.default]\nfinish_sound = {value}\n"))
