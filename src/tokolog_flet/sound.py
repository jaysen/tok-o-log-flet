"""The alert played when a countdown finishes, through whatever player the system has."""

import contextlib
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

# A short chime; ships inside the package.
FINISH_SOUND = Path(str(files("tokolog_flet") / "finish.wav"))
# Tried in order on Linux and other Unixes: PipeWire, PulseAudio, then ALSA.
UNIX_PLAYERS = ("pw-play", "paplay", "aplay")


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
