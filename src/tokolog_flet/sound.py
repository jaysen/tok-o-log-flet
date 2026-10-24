"""The alert played when a countdown finishes, through whatever player the system has."""

import contextlib
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

# Built-in sounds, picked by name in the config; they ship inside the package.
SOUNDS_FOLDER = Path(str(files("tokolog_flet") / "sounds"))
SOUND_NAMES = ("chime", "bell", "ding", "beep", "alarm", "gong")
FINISH_SOUND = SOUNDS_FOLDER / "chime.wav"
# Tried in order on Linux and other Unixes: PipeWire, PulseAudio, then ALSA.
UNIX_PLAYERS = ("pw-play", "paplay", "aplay")


def builtin_sound(name: str) -> Path:
    return SOUNDS_FOLDER / f"{name}.wav"


def play(path: Path) -> None:
    """Start playing ``path`` without waiting; does nothing if no player is found."""
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return
    players = ("afplay",) if sys.platform == "darwin" else UNIX_PLAYERS
    player = next((p for p in players if shutil.which(p)), None)
    if player is None:
        return
    # aplay prints a header for every file; the others are quiet.
    args = [player, "-q", str(path)] if player == "aplay" else [player, str(path)]
    # A missed chime shouldn't stop the timer.
    with contextlib.suppress(OSError):
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
