"""The app's sounds: a built-in beep for each thing that happens, or a sound file of your own.

One sound plays at a time (a new one cuts off the one before), on its own thread, so the window
and the macro never wait for it.

Windows: built-in beeps through winsound, your own files through Windows' media player (MCI), which
plays .wav and .mp3 (and usually .wma, .m4a, .aac). Mac: afplay (.wav, .mp3, .m4a, .aiff, ...).
"""

import io
import math
import os
import queue
import struct
import subprocess
import sys
import tempfile
import threading
import wave

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# id, name in Settings, a few words about it, and whether it makes a sound before you change anything
EVENTS = [
    ("record_start", "Recording starts", "", True),
    ("record_stop", "Recording stops", "", True),
    ("play_start", "Playing starts", "", True),
    ("play_end", "Playing ends", "finished or stopped", True),
    ("pause", "Paused", "recording or playing", True),
    ("resume", "Resumed", "going on after a pause", True),
    ("countdown", "Countdown", "each second before playing", False),
    ("picture_seen", "Picture seen", "picture watch restarts the macro", False),
    ("error", "Problem", "playback stopped by itself or an error", True),
    ("click", "Button click", "buttons and switches in this app", False),
    ("win", "Win", "a run ended with MISSION COMPLETED", False),
    ("loss", "Loss", "a run ended with MISSION FAILED", False),
    ("fragment", "Divine fragment", "a divine fragment dropped", True),
    ("milestone", "Milestone", "a number of wins or fragments was reached", True),
    ("timed_warning", "Timed start warning", "shortly before a timed start", True),
    ("timed_countdown", "Timed start countdown", "each second before a timed or start-up play", True),
    ("recover_disconnect", "Rejoin countdown (disconnect)", "before the rejoin macro plays", True),
    ("recover_close", "Reopen countdown (game closed)", "before the game opens again", True),
]
EVENT_IDS = [e[0] for e in EVENTS]

# the built-in beeps: [(frequency, milliseconds), ...]
TONES = {
    "record_start": [(660, 70), (880, 90)],
    "record_stop": [(880, 70), (660, 90)],
    "play_start": [(784, 60), (1046, 80)],
    "play_end": [(1046, 60), (784, 60), (587, 90)],
    "pause": [(880, 70), (660, 90)],
    "resume": [(660, 70), (880, 90)],
    "countdown": [(880, 55)],
    "picture_seen": [(1318, 60), (1568, 60), (2093, 90)],
    "error": [(523, 110), (392, 160)],
    "click": [(1400, 14)],
    "win": [(784, 70), (988, 70), (1318, 120)],
    "loss": [(659, 90), (587, 90), (494, 160)],
    "fragment": [(1568, 50), (2093, 50), (2637, 50), (3136, 110)],
    "milestone": [(1046, 70), (1318, 70), (1568, 70), (2093, 140)],
    "timed_warning": [(988, 80), (0, 60), (988, 80)],
    "timed_countdown": [(784, 60)],
    "recover_disconnect": [(740, 70)],
    "recover_close": [(587, 80)],
}
OLD_VOLUMES = {"Quiet": 25, "Normal": 50, "Loud": 80}  # the volume used to be one of these words
DEFAULT_VOLUME = 50


def volume_number(value):
    """The volume as a whole number from 0 (silent) to 100 (also reads the older words)."""
    if isinstance(value, str) and value in OLD_VOLUMES:
        return OLD_VOLUMES[value]
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return DEFAULT_VOLUME


def beep_level(volume):
    """How strong the built-in beeps are (they're piercing, so they stay below full strength)."""
    return 0.8 * (volume_number(volume) / 100) ** 1.6


def file_level(volume):
    """How loud your own files play, 0 to 1 (1 = as loud as the file is)."""
    return (volume_number(volume) / 100) ** 0.75

SOUND_TYPES = [("Sounds", "*.wav *.mp3 *.m4a *.aac *.wma *.aiff *.aif *.flac"), ("All files", "*.*")]


def tone_wav(notes, volume):
    """A short WAV (bytes) playing the notes [(frequency, ms), ...], softly faded in and out."""
    rate = 22050
    frames = bytearray()
    for freq, ms in notes:
        n = int(rate * ms / 1000)
        fade = max(1, min(int(rate * 0.008), n // 2))
        for i in range(n):
            env = min(1.0, i / fade, (n - i) / fade)
            frames += struct.pack("<h", int(volume * env * 32767 * math.sin(2 * math.pi * freq * i / rate)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


class Player:
    """Plays beeps and sound files, one at a time, without anyone waiting for them."""

    ALIAS = "macrorecorder_sound"

    def __init__(self):
        self.jobs = queue.Queue()
        self.thread = None
        self.tones = {}      # (name, volume) -> WAV bytes
        self.open_file = False   # Windows: a sound file is open in the media player
        self.proc = None     # Mac: the afplay that's running

    # ------------------------------------------------------------ asking for sounds (any thread)

    def beep(self, name, volume=DEFAULT_VOLUME):
        """volume: 0 (silent) to 100."""
        volume = volume_number(volume)
        if volume > 0:
            self._ask(("beep", name, volume, None))

    def play_file(self, path, volume=DEFAULT_VOLUME, fallback=None):
        """fallback: the beep to play if the file can't be played."""
        volume = volume_number(volume)
        if volume > 0:
            self._ask(("file", path, volume, fallback))

    def stop(self, wait=True):
        """Stop the sound and let go of its file (so it can be replaced or deleted)."""
        done = threading.Event()
        self._ask(("stop", done, None, None))
        if wait:
            done.wait(2.0)

    def can_play(self, path):
        """Can this file be played here? (Windows asks its media player; elsewhere: by its ending.)"""
        if IS_WIN:
            result = []
            done = threading.Event()
            self._ask(("check", path, result, done))
            done.wait(5.0)
            return bool(result and result[0])
        return os.path.splitext(path)[1].lower() in (".wav", ".mp3", ".m4a", ".aac", ".aiff", ".aif", ".flac",
                                                     ".caf")

    def _ask(self, job):
        if not (IS_WIN or IS_MAC):
            if job[0] == "stop":
                job[1].set()
            elif job[0] == "check":
                job[3].set()
            return  # no sound here; that's fine
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        self.jobs.put(job)

    # ------------------------------------------------------------ the sound thread

    def _run(self):
        while True:
            try:
                job = self.jobs.get(timeout=0.05)
            except queue.Empty:
                self._idle()
                continue
            # a pile of waiting beeps (the PC was busy): only the newest one is worth playing
            while job[0] in ("beep", "file"):
                try:
                    newer = self.jobs.get_nowait()
                except queue.Empty:
                    break
                if newer[0] in ("beep", "file"):
                    job = newer
                else:
                    self._do(newer)
            self._do(job)

    def _do(self, job):
        kind = job[0]
        try:
            if kind == "beep":
                self._silence()
                self._beep(job[1], job[2])
            elif kind == "file":
                self._silence()
                if not self._file(job[1], job[2]) and job[3]:
                    self._beep(job[3], job[2])
            elif kind == "stop":
                self._silence()
            elif kind == "check":
                self._silence()
                ok = self._mci_open(job[1])
                self._silence()
                job[2].append(ok)
        except Exception:
            pass  # no sound is fine
        finally:
            if kind == "stop":
                job[1].set()
            elif kind == "check":
                job[3].set()

    def _tone(self, name, volume):
        key = (name, volume)
        if key not in self.tones:
            self.tones[key] = tone_wav(TONES[name], beep_level(volume))
        return self.tones[key]

    def _beep(self, name, volume):
        data = self._tone(name, volume)
        if IS_WIN:
            import winsound

            winsound.PlaySound(data, winsound.SND_MEMORY)
        elif IS_MAC:
            path = os.path.join(tempfile.gettempdir(), f"macrorecorder_{name}_{volume}_3.wav")
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(data)
            self.proc = subprocess.Popen(["afplay", path])

    def _file(self, path, volume):
        if not os.path.isfile(path):
            return False
        level = file_level(volume)
        if IS_WIN:
            if not self._mci_open(path):
                return False
            self._mci(f"setaudio {self.ALIAS} volume to {int(level * 1000)}")
            return self._mci(f"play {self.ALIAS}") == 0
        if IS_MAC:
            self.proc = subprocess.Popen(["afplay", "-v", f"{level:.3f}", path])
            return True
        return False

    def _silence(self):
        """Stop whatever is playing."""
        if IS_WIN:
            if self.open_file:
                self._mci(f"close {self.ALIAS}")
                self.open_file = False
        elif self.proc is not None:
            if self.proc.poll() is None:
                self.proc.terminate()
            self.proc = None

    # ------------------------------------------------------------ Windows' media player (MCI)

    def _mci(self, command):
        import ctypes

        return ctypes.windll.winmm.mciSendStringW(command, None, 0, None)

    def _mci_open(self, path):
        if self._mci(f'open "{path}" type mpegvideo alias {self.ALIAS}') != 0 \
                and self._mci(f'open "{path}" alias {self.ALIAS}') != 0:
            return False
        self.open_file = True
        return True

    def _idle(self):
        """Windows: the media player talks to this thread through window messages; hand them on."""
        if not IS_WIN or not self.open_file:
            return
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            msg = wintypes.MSG()
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            pass
