"""Macro Recorder: record mouse and keyboard actions, then replay them.

Hotkeys (work even when the window is not focused; change them in Settings > General):
    F9   start / stop recording
    F10  pause / resume recording
    F11  play the current macro
    F12  stop playback

Hotkeys and the playback speed are remembered in %APPDATA%\\MacroRecorder\\settings.json
(on a Mac: ~/Library/Application Support/MacroRecorder/settings.json).

Recordings are saved as .macro files you can share with friends, Windows or Mac. To open one,
use Open..., double-click it (after "Link .macro files"), or drag it onto the app.
"""

import json
import os
import queue
import sys
import random
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from pynput import keyboard, mouse
except ImportError:  # pragma: no cover - shown to the user at startup
    print("pynput is missing. Install it with:  py -m pip install pynput")
    sys.exit(1)

try:
    import background
except ImportError:  # not on Windows
    background = None

import diag
import importers
import run_history
import stats
import macro_steps as workflow
import platform_keys
import raw_mouse
import window_tools

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

import lazy

# loaded the first time a picture is used (OpenCV and numpy take a moment to load); None when they're
# missing, which turns the picture options off
image_watch = lazy.module("image_watch") if lazy.available("cv2", "numpy", "mss") else None

FILE_VERSION = 1
SCREEN_TARGET = "Whole screen (normal)"
FILE_EXT = ".macro"
FILE_TYPES = [("Macro files", "*.macro *.json"), ("All files", "*.*")]
OPEN_FILE_TYPES = [
    ("All macro files", "*.macro *.json *.luvmacro *.rec *.mcr *.ahk"),
    ("This app's macros", "*.macro *.json"),
    ("luvmacro", "*.luvmacro"),
    ("TinyTask", "*.rec"),
    ("Macro Recorder (Jitbit)", "*.mcr"),
    ("AutoHotkey script", "*.ahk"),
    ("All files", "*.*"),
]
MOVE_INTERVAL = 0.01  # record at most one mouse move every 10 ms

HOTKEY_ACTIONS = ("record", "pause", "play", "stop")
HOTKEY_LABELS = {"record": "Record / stop recording", "pause": "Pause / resume recording",
                 "play": "Play", "stop": "Stop playback"}
DEFAULT_HOTKEYS = {"record": "f9", "pause": "f10", "play": "f11", "stop": "f12"}

SPEED_PRESETS = ["0.25x", "0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x", "3x", "4x", "8x"]
MIN_SPEED, MAX_SPEED = 0.01, 100.0

RESOLUTIONS = ["1280x720", "1366x768", "1600x900", "1920x1080", "2560x1440", "3840x2160",
               "1280x800", "1440x900", "1680x1050", "1920x1200", "2560x1600",
               "1280x1024", "2560x1080", "3440x1440"]
AUTO_PREFIX = "Auto"  # "Play on" box: use the screen's own size
SAME_AS_PLAY = "Same as your screen"  # "Made for" box: size unknown, don't change positions


def parse_resolution(text):
    """'1920x1080', '1920 x 1080', 'Auto (2560x1440)' -> (1920, 1080); None if there's no size in it."""
    import re

    m = re.search(r"(\d{3,5})\s*[x×*,]\s*(\d{3,5})", str(text))
    if not m:
        return None
    w, h = int(m.group(1)), int(m.group(2))
    return (w, h) if 320 <= w <= 16000 and 200 <= h <= 9000 else None


def format_resolution(size):
    return f"{size[0]}x{size[1]}"


def scale_events(events, src, dst):
    """Copy of events with mouse positions moved from a src-sized screen to a dst-sized one.

    Everything is scaled by the same amount (the height ratio) around the middle of the screen.
    In a 3D game like Roblox the picture is fitted to the screen's height, so this keeps a click
    on the same thing in the world even when the screen's shape differs (16:9 vs 16:10 or
    ultrawide). For screens of the same shape it's the same as stretching both ways.
    Relative mouse moves (camera turning) are left alone: they don't depend on screen size."""
    if not src or not dst or tuple(src) == tuple(dst):
        return [dict(ev) for ev in events]
    sw, sh = src
    dw, dh = dst
    f = dh / sh
    out = []
    for ev in events:
        ev = dict(ev)
        if "x" in ev and "y" in ev:
            ev["x"] = max(0, min(dw - 1, round(dw / 2 + (ev["x"] - sw / 2) * f)))
            ev["y"] = max(0, min(dh - 1, round(dh / 2 + (ev["y"] - sh / 2) * f)))
        out.append(ev)
    return out


def drop_stray_clicks(events):
    """Leave out mouse button presses that were never let go of in the recording (and lets go that
    were never pressed). They happen when the click that started or stopped recording was half
    caught (like pressing the Record button): played back, that button would stay held down
    the whole run."""
    held = {}  # button -> index of its press
    drop = set()
    for i, ev in enumerate(events):
        if not isinstance(ev, dict) or ev.get("type") != "click":
            continue
        button = ev.get("button")
        if ev.get("pressed"):
            if button in held:
                drop.add(held[button])  # pressed again without a let go in between
            held[button] = i
        elif button in held:
            del held[button]
        else:
            drop.add(i)
    drop.update(held.values())
    if not drop:
        return events
    return [ev for i, ev in enumerate(events) if i not in drop]


def scale_events_rect(events, src, dst):
    """Copy of events with mouse positions moved from one game window to another.

    src and dst are the windows' insides on the screen as (x, y, w, h). Like scale_events, it's
    scaled by the height around the middle (how Roblox fits its picture), so it also works when the
    window moved, changed size or has another shape."""
    sx, sy, sw, sh = src
    dx, dy, dw, dh = dst
    f = dh / sh
    out = []
    for ev in events:
        ev = dict(ev)
        if "x" in ev and "y" in ev:
            ev["x"] = round(dx + dw / 2 + (ev["x"] - sx - sw / 2) * f)
            ev["y"] = round(dy + dh / 2 + (ev["y"] - sy - sh / 2) * f)
        out.append(ev)
    return out


# result titles are big: compared at about this height they're still told apart well (true match
# about 90%, other screens about 30% on AOT:R) and a look is about 7 times quicker
RESULT_WORK_HEIGHT = 24
CAMERA_STEP = 0.004  # recorded camera movement is added up into one step every 4 ms (250 a second)
MAX_MACRO_DEPTH = 6  # macros that play macros that play macros...
AUTO_STOP_THEN = {"nothing": "Nothing more", "close": "Close the game", "sleep": "Put the PC to sleep",
                  "shutdown": "Shut the PC down"}
AUTO_STOP_WARN_SECONDS = 300  # Discord is told this long before a timed stop
RECOVER_MATCH = 0.9  # a disconnect picture must match at least this well (see _watch_match_ok)
GAME_GONE_SECONDS = 5  # the game's windows must be gone this long before it counts as closed
# the last this many seconds before each action, playback checks the clock without resting (exact
# timing). Windows rests accurately to about a millisecond, so this is kept short: the longer it is,
# the more CPU playback takes from the game when actions come close together (mouse moves).
SPIN_SECONDS = 0.001
HEALTH_EVERY = 30 * 60  # seconds between the "Health:" lines in the log while playing
AWAY_GRACE = 0.4  # seconds another window may be in front before playback pauses (windows changing)


def settings_path():
    if IS_MAC:
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "MacroRecorder", "settings.json")


def load_settings():
    try:
        with open(settings_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


BUILTIN_PICTURE = "retry_default.png"  # comes with the app (bundled into the .exe)
BUILTIN_PICTURE_SCREEN_H = 1080
# the word "Disconnected" from Roblox's Disconnected box (Kong's 2560x1440 screen). Only the word: the
# whole box matched only on its bright parts scored up to 0.86 on ordinary game screens, the word 0.62
BUILTIN_DISCONNECT = "disconnected_default.png"
BUILTIN_DISCONNECT_SCREEN_H = 1440
# AOT:R's gold "MISSION COMPLETED" title (Kong's picture), the built-in "mission completed" picture
BUILTIN_WIN_PICTURE = "completed_default.png"
BUILTIN_WIN_PICTURE_SCREEN_H = 1440
# and its gold "MISSION FAILED" title, the built-in "mission failed" picture (also taken at 1440p)
BUILTIN_LOSS_PICTURE = "failed_default.png"
BUILTIN_LOSS_PICTURE_SCREEN_H = 1440
RESULTS_MATCH_DEFAULT = 80  # the real titles score about 85-92 %, the other title about 55-66 %


def resource_path(name):
    """A file that ships with the app: inside the .exe when built, else next to this script."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def watch_dir():
    """Where the pictures to watch for are kept."""
    return os.path.join(os.path.dirname(settings_path()), "watch_pictures")


class SavedPicture(dict):
    """A picture to look for, from a file in the pictures folder. pic["img"] reads the file the first
    time it's used (so the app starts without loading OpenCV); everything else is there at once."""

    def __init__(self, path, **fields):
        super().__init__(**fields)
        self.path = path

    def __missing__(self, key):
        if key != "img":
            raise KeyError(key)
        img = self["img"] = image_watch.load_image(self.path)
        return img


def saved_picture(file, **fields):
    """A SavedPicture for a file in the pictures folder, or None if the file is gone."""
    path = os.path.join(watch_dir(), file)
    return SavedPicture(path, file=file, **fields) if os.path.isfile(path) else None


# what a watched picture does when it shows (Picture watch): name, a few words
WATCH_ACTIONS = [
    ("restart", "Start the macro over", "the run is finished: start again from the beginning"),
    ("recover", "Disconnected: play my rejoin macro, then go on",
     "for Roblox's Disconnected box: plays your rejoin macro, checks you're back, then the macro starts over"),
    ("play", "Play another macro, then start over", "for a screen that needs a few steps first"),
    ("switch", "Switch to another macro for good", "from now on that macro plays (and loops) instead of this one"),
    ("skip", "Skip to the next step", "the step that's playing ends at once"),
    ("key", "Press a key", "then the macro goes on"),
    ("wait", "Wait", "the macro stands still for some seconds, then goes on"),
    ("stop", "Stop the macro", "and say why"),
    ("nothing", "Nothing", "it only counts for another picture's \"only when … also shows\""),
]
WATCH_ACTION_NAMES = {k: n for k, n, _ in WATCH_ACTIONS}
WATCH_INLINE = ("skip", "key", "wait", "nothing")  # the macro goes on after these
WATCH_NEED_MACRO = ("play", "switch", "recover")
# what's remembered for each watched picture besides its file (None / missing = the usual)
WATCH_FIELDS = ("screen_h", "name", "action", "macro", "key", "seconds", "click", "cooldown", "also", "counts",
                "tries", "confirm_file", "confirm_screen_h", "confirm_seconds")


# where a picture is kept in the Picture watch window and when it's used (2.9): its group's id, on
# (kept only when False), the macros it's used for (none = every macro), which built-in picture it is
GROUP_FIELDS = ("group", "on", "macros", "builtin")
GROUP_GENERAL, GROUP_AOTR, GROUP_MINE = "general", "aotr", "mine"
# the pictures that come with the app: key -> (file, screen height it was taken at, result kind or
# None for a watched picture, its built-in settings)
BUILTINS = {
    "retry": (BUILTIN_PICTURE, BUILTIN_PICTURE_SCREEN_H, None, {"name": "RETRY"}),
    "disconnect": (BUILTIN_DISCONNECT, BUILTIN_DISCONNECT_SCREEN_H, None,
                   {"name": "Disconnected", "action": "recover"}),
    "completed": (BUILTIN_WIN_PICTURE, BUILTIN_WIN_PICTURE_SCREEN_H, stats.WIN, {"name": "MISSION COMPLETED"}),
    "failed": (BUILTIN_LOSS_PICTURE, BUILTIN_LOSS_PICTURE_SCREEN_H, stats.LOSS, {"name": "MISSION FAILED"}),
}


def group_fields(entry):
    """The group fields of a picture's settings entry that are usable."""
    out = {}
    if isinstance(entry.get("group"), str) and entry["group"]:
        out["group"] = entry["group"]
    if entry.get("on") is False:
        out["on"] = False
    macros = entry.get("macros")
    if isinstance(macros, list) and macros:
        out["macros"] = [m for m in macros if isinstance(m, str) and m]
    if entry.get("builtin") in BUILTINS:
        out["builtin"] = entry["builtin"]
    return out


def picture_group(pic):
    """The id of the group a picture is in (built-in pictures start in AOT:R, others in My pictures)."""
    return pic.get("group") or (GROUP_AOTR if pic.get("builtin") else GROUP_MINE)


def watch_entry(pic):
    """What settings keep of a watched picture."""
    out = {"file": pic["file"], "screen_h": pic.get("screen_h")}
    for k in WATCH_FIELDS:
        if pic.get(k) not in (None, "", False) or (k in ("click", "counts") and pic.get(k) is False):
            out[k] = pic[k]
    out.update(group_fields(pic))
    return out


def watch_picture_from(entry):
    """A watched picture from its settings entry, or None when its file is gone."""
    if not isinstance(entry, dict) or not entry.get("file"):
        return None
    fields = {k: entry[k] for k in WATCH_FIELDS if k in entry}
    fields.update(group_fields(entry))
    fields.setdefault("screen_h", None)
    return saved_picture(entry["file"], **fields)


def watch_counts(pic):
    """Whether this picture showing means a run is finished (counted in the results)."""
    counts = pic.get("counts")
    return pic.get("action", "restart") == "restart" if counts is None else bool(counts)


def watch_name(pic, number=None):
    return pic.get("name") or (f"picture {number}" if number else "the picture")


def picture_thumb(pic, max_w, max_h):
    """(Tk picture, width, height) of a picture to look for, shrunk to fit. Read by Tk straight from
    its PNG file when it isn't loaded yet (no OpenCV needed)."""
    if "img" not in pic and getattr(pic, "path", None):
        try:
            photo = tk.PhotoImage(file=pic.path)
            w, h = photo.width(), photo.height()
            step = max(1, -(-w // max_w), -(-h // max_h))
            return (photo.subsample(step) if step > 1 else photo), w, h
        except tk.TclError:
            pass
    img = pic["img"]
    h, w = img.shape[:2]
    return tk.PhotoImage(data=image_watch.png_data(img, max_w, max_h)), w, h


def int_setting(settings, name, default, low, high):
    try:
        return max(low, min(high, int(settings.get(name, default))))
    except (TypeError, ValueError):
        return default


def simplify_moves(events, tolerance=1.0):
    """Mouse positions that lie on the straight, evenly paced line between their neighbours (within
    `tolerance` pixels, in place and in time) are left out. The move after a left-out stretch gets
    "s": 1, so expand_moves() puts the in-between positions back when the macro is opened. Clicks,
    keys, scrolling and camera turns are never touched."""
    out = []
    run = []

    def flush():
        if not run:
            return
        a = 0
        kept = [run[0]]
        while a < len(run) - 1:
            b = a + 1
            # stretch the line from run[a] as far as every point in between stays on it
            while b + 1 < len(run):
                A, C = run[a], run[b + 1]
                span = C["t"] - A["t"]
                if span <= 0:
                    break
                ok = True
                for m in range(a + 1, b + 2):
                    B = run[m]
                    f = (B["t"] - A["t"]) / span
                    if abs(A["x"] + (C["x"] - A["x"]) * f - B["x"]) > tolerance or \
                            abs(A["y"] + (C["y"] - A["y"]) * f - B["y"]) > tolerance:
                        ok = False
                        break
                if not ok:
                    break
                b += 1
            ev = dict(run[b])
            if b > a + 1:
                ev["s"] = 1  # glide here from the previous position
            kept.append(ev)
            a = b
        out.extend(kept)
        run.clear()

    for ev in events:
        if ev.get("type") == "move" and "x" in ev:
            run.append(ev)
        else:
            flush()
            out.append(ev)
    flush()
    return out


MAX_GLIDE = 10.0  # seconds
MAX_EXPANDED = 2_000_000  # actions


MAX_NESTING = 50  # groups inside groups, in a macro file


def expand_steps(steps):
    """expand_moves() for every recorded part of a macro made of steps, with one limit for the whole
    file (MAX_EXPANDED actions), so many parts can't add up to more. A file that goes over it, or
    whose groups are nested more than MAX_NESTING deep, raises ValueError."""
    total = 0

    def go(actions, depth):
        nonlocal total
        if depth > MAX_NESTING:
            raise ValueError("its groups are nested too deeply")
        for a in actions:
            if not isinstance(a, dict):
                continue
            if a.get("kind") == "recorded" and isinstance(a.get("events"), list):
                a["events"] = expand_moves(a["events"], budget=MAX_EXPANDED - total)
                total += len(a["events"])
                if total > MAX_EXPANDED:
                    raise ValueError("it has too many actions")
            if isinstance(a.get("actions"), list):
                go(a["actions"], depth + 1)
    go(steps, 0)
    return steps


def expand_moves(events, step=0.01, budget=None):
    """Puts back the positions simplify_moves() left out: a move marked "s" is reached from the
    move before it in steps of `step` seconds, as a real mouse would have reported them.
    budget: at most how many actions the result may have (MAX_EXPANDED at most)."""
    if not any(isinstance(ev, dict) and ev.get("s") for ev in events):
        return events
    budget = MAX_EXPANDED if budget is None else max(0, min(MAX_EXPANDED, budget))
    import math

    def number(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    out = []
    last_move = None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "move" and ev.get("s") and last_move is not None and \
                all(number(q.get(k)) for q in (last_move, ev) for k in ("t", "x", "y")):
            A, C = last_move, ev
            span = C["t"] - A["t"]
            # a file from somewhere else can't make the app run out of memory: a glide is at most
            # MAX_GLIDE seconds (a real one is far shorter) and a macro at most MAX_EXPANDED actions
            n = int(round(span / step)) if 0 < span <= MAX_GLIDE else 0  # (round: 0.3 / 0.01 is 29.999...)
            n = min(n, max(0, budget - len(out)))
            for k in range(1, n):
                f = k * step / span
                out.append({"type": "move", "x": round(A["x"] + (C["x"] - A["x"]) * f),
                            "y": round(A["y"] + (C["y"] - A["y"]) * f), "t": round(A["t"] + k * step, 4)})
            ev = {k: v for k, v in ev.items() if k != "s"}
        elif ev.get("s"):
            ev = {k: v for k, v in ev.items() if k != "s"}
        out.append(ev)
        last_move = ev if ev.get("type") == "move" else None  # (stretches never go past other actions)
    return out


def dump_macro(data, f):
    """Write a macro file compactly: one action per line, no extra spaces (about half the size of
    the old layout, and quicker to open). Any program that reads JSON still reads it."""
    events = data.get("events", [])
    head = {k: v for k, v in data.items() if k != "events"}
    compact = {"separators": (",", ":"), "ensure_ascii": False}
    start = json.dumps(head, **compact)[:-1]
    f.write(start + ("," if head else "") + '"events":[\n')
    f.write(",\n".join(json.dumps(ev, **compact) for ev in events))
    f.write("\n]}\n")


SETTINGS_WRITE_DELAY = 0.4  # seconds after the last change before the settings file is written
_settings_write = {"lock": threading.Lock(), "text": None, "path": None, "timer": None, "written": {}}


def save_settings(data, now=False):
    """Remember the settings. They're written to the file a moment after the last change (flipping a
    few switches in a row is one write, not one each), at once with now=True, and always before the
    app closes (flush_settings)."""
    w = _settings_write
    try:
        text = json.dumps(data, indent=1)  # (made now: the settings may change again before the write)
    except Exception:
        return  # not being able to remember settings shouldn't stop the app
    with w["lock"]:
        w["text"], w["path"] = text, settings_path()
        if not now and w["timer"] is None:
            w["timer"] = threading.Timer(SETTINGS_WRITE_DELAY, flush_settings)
            w["timer"].daemon = True
            w["timer"].start()
    if now:
        flush_settings()


def flush_settings():
    """Write the settings that are waiting to be written, now."""
    w = _settings_write
    with w["lock"]:
        text, path = w["text"], w["path"]
        w["text"] = None
        if w["timer"] is not None:
            w["timer"].cancel()
            w["timer"] = None
        if text is None or w["written"].get(path) == text:
            return  # nothing new
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            w["written"][path] = text
        except Exception:
            pass  # not being able to remember settings shouldn't stop the app


import atexit  # noqa: E402

atexit.register(flush_settings)


def parse_speed(text):
    """'1.5', '1.5x', ' 2 X ' -> float, or None if it isn't a usable speed."""
    text = str(text).strip().lower().rstrip("x").strip().replace(",", ".")
    try:
        speed = float(text)
    except ValueError:
        return None
    if not (MIN_SPEED <= speed <= MAX_SPEED):
        return None
    return speed


def format_speed(speed):
    return f"{speed:g}x"


def make_dpi_aware():
    """Use real screen pixels on Windows so recorded and replayed positions match."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ---------------------------------------------------------------- key <-> json
#
# In files, "vk" is always a Windows key code, also for macros recorded on a Mac, so a macro
# plays the same keys on both. A Mac key with no Windows match is kept as "mac_vk".

def native_vk_to_win(vk):
    """This computer's key code for a key -> the Windows key code (None if there's no match)."""
    if IS_WIN:
        return vk
    if IS_MAC:
        return platform_keys.MAC_TO_WIN.get(vk)
    return None


def key_to_data(key):
    if isinstance(key, keyboard.Key):
        return {"special": key.name}
    data = {}
    vk = getattr(key, "vk", None)
    if vk is not None:
        win_vk = native_vk_to_win(vk)
        if win_vk is not None:
            data["vk"] = win_vk
        elif IS_MAC:
            data["mac_vk"] = vk
    char = getattr(key, "char", None)
    if char is not None:
        data["char"] = char
    return data


def data_to_key(data):
    """The pynput key to press for recorded key data, or None if this computer has no such key."""
    if "special" in data:
        return keyboard.Key.__members__.get(data["special"])  # e.g. Insert or Pause: not on a Mac
    if IS_WIN and "vk" in data:
        return keyboard.KeyCode.from_vk(data["vk"])
    if IS_MAC:
        if "mac_vk" in data:
            return keyboard.KeyCode.from_vk(data["mac_vk"])
        mac_vk = platform_keys.WIN_TO_MAC.get(data.get("vk"))
        if mac_vk is not None:
            return keyboard.KeyCode.from_vk(mac_vk)
    if data.get("char"):
        return keyboard.KeyCode.from_char(data["char"])
    if not IS_WIN and "vk" in data:
        name = platform_keys.win_vk_name(data["vk"])
        if name and len(name) == 1:
            return keyboard.KeyCode.from_char(name.lower())
    return None


def key_to_vk(data):
    """Windows virtual-key code for a recorded key (used by background playback)."""
    if "vk" in data:
        return data["vk"]
    if "special" in data:
        return keyboard.Key[data["special"]].value.vk
    if "char" in data and sys.platform == "win32":
        import ctypes

        scan = ctypes.windll.user32.VkKeyScanW
        scan.argtypes, scan.restype = [ctypes.c_wchar], ctypes.c_short
        code = scan(data["char"])
        if code != -1:
            return code & 0xFF
    return None


def hotkey_id(key):
    """A stable text id for a key, used to match and remember hotkeys: 'f9', 'vk:65', 'char:a'."""
    if isinstance(key, keyboard.Key):
        return key.name
    vk = getattr(key, "vk", None)
    if vk is not None and native_vk_to_win(vk) is not None:
        return f"vk:{native_vk_to_win(vk)}"
    char = getattr(key, "char", None)
    if char:
        return f"char:{char.lower()}"
    return None


def hotkey_is_valid(key_id):
    if not isinstance(key_id, str):
        return False
    if key_id.startswith("vk:"):
        return key_id[3:].isdigit()
    if key_id.startswith("char:"):
        return len(key_id) > 5
    return key_id in keyboard.Key.__members__


NUMPAD_NAMES = {106: "Num *", 107: "Num +", 109: "Num -", 110: "Num .", 111: "Num /"}


def hotkey_name(key_id):
    """Readable name for a hotkey id, for buttons and the hotkeys window."""
    if key_id.startswith("char:"):
        return key_id[5:].upper()
    if key_id.startswith("vk:"):
        vk = int(key_id[3:])
        if 96 <= vk <= 105:
            return f"Num {vk - 96}"
        if vk in NUMPAD_NAMES:
            return NUMPAD_NAMES[vk]
        if sys.platform == "win32":
            import ctypes

            user32 = ctypes.windll.user32
            char = user32.MapVirtualKeyW(vk, 2) & 0xFFFF  # MAPVK_VK_TO_CHAR
            if 32 < char < 0xD800:
                return chr(char).upper()
            scan = user32.MapVirtualKeyW(vk, 0)
            if scan:
                buf = ctypes.create_unicode_buffer(32)
                if user32.GetKeyNameTextW(scan << 16, buf, 32):
                    return buf.value
        return platform_keys.win_vk_name(vk) or f"Key {vk}"
    name = key_id.replace("_", " ")
    for side in (" l", " r"):
        if name.endswith(side):
            name = ("Left " if side == " l" else "Right ") + name[:-2]
    name = name.title()
    if IS_MAC:
        return name.replace("Alt", "Option").replace("Cmd", "Command")
    return name.replace("Cmd", "Win")


def button_from_name(name):
    return mouse.Button[name]


_virtual_screen = [0.0, None]  # [when asked, (x, y, w, h) of all screens together]


def _all_screens():
    now = time.monotonic()
    if _virtual_screen[1] is None or now - _virtual_screen[0] > 2.0:
        import ctypes

        u = ctypes.windll.user32
        _virtual_screen[:] = [now, tuple(u.GetSystemMetrics(i) for i in (76, 77, 78, 79))]
    return _virtual_screen[1]


def move_to(mouse_ctrl, x, y):
    """Put the mouse at x, y (screen pixels) the way a real mouse gets there. Windows: as mouse input
    (SendInput, absolute over all screens), which games like Roblox notice and draw their pointer
    for; only setting the cursor position (SetCursorPos) moves it without the game seeing it, so
    its pointer stayed where it was until the real mouse moved. Then the exact pixel is set too."""
    x, y = int(x), int(y)
    if IS_WIN:
        try:
            import ctypes

            u = ctypes.windll.user32
            vx, vy, vw, vh = _all_screens()
            if vw > 1 and vh > 1:
                nx = round((x - vx) * 65535 / (vw - 1))
                ny = round((y - vy) * 65535 / (vh - 1))
                # MOVE | ABSOLUTE | VIRTUALDESK
                u.mouse_event(0x0001 | 0x8000 | 0x4000, max(0, min(65535, nx)), max(0, min(65535, ny)), 0, 0)
        except Exception:
            pass
    mouse_ctrl.position = (x, y)


def move_relative(mouse_ctrl, dx, dy, held_buttons=()):
    """Nudge the mouse by dx, dy like a real mouse does. Games that lock the cursor (camera turning)
    only react to this kind of movement, not to setting the cursor position."""
    if IS_WIN:
        import ctypes

        ctypes.windll.user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)  # MOUSEEVENTF_MOVE
    elif IS_MAC:
        _mac_move_relative(int(dx), int(dy), held_buttons)
    else:
        mouse_ctrl.move(dx, dy)


def _mac_move_relative(dx, dy, held_buttons):
    """Mac: a mouse-moved event that carries the movement itself (delta X/Y), which is what a
    game reads while it holds the cursor still. Untested in Roblox on a real Mac."""
    import Quartz

    here = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    names = {getattr(b, "name", b) for b in held_buttons}
    if "right" in names:
        kind, button = Quartz.kCGEventRightMouseDragged, Quartz.kCGMouseButtonRight
    elif "left" in names:
        kind, button = Quartz.kCGEventLeftMouseDragged, Quartz.kCGMouseButtonLeft
    else:
        kind, button = Quartz.kCGEventMouseMoved, Quartz.kCGMouseButtonLeft
    ev = Quartz.CGEventCreateMouseEvent(None, kind, (here.x + dx, here.y + dy), button)
    Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventDeltaX, dx)
    Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventDeltaY, dy)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def mac_prepare_pynput():
    """pynput's Mac keyboard listener reads the keyboard layout on its own thread, which newer
    macOS versions stop the app for (it must happen on the main thread). Read it once here, on
    the main thread, and hand the listener that copy."""
    import contextlib

    from pynput.keyboard import _darwin

    with _darwin.keycode_context() as context:
        cached = context

    @contextlib.contextmanager
    def cached_context():
        yield cached

    _darwin.keycode_context = cached_context


def mac_missing_permissions():
    """Mac permissions that aren't given yet, as readable names."""
    missing = []
    try:
        import HIServices

        if not HIServices.AXIsProcessTrusted():
            missing.append("Accessibility")
    except Exception:
        pass
    try:
        import Quartz

        if hasattr(Quartz, "CGPreflightScreenCaptureAccess") and not Quartz.CGPreflightScreenCaptureAccess():
            missing.append("Screen Recording")
    except Exception:
        pass
    return missing


# ---------------------------------------------------------------- recorder app

class MacroRecorder:
    def __init__(self, root):
        self.root = root
        self.events = []  # each: {"t": seconds since start, "type": ..., ...}
        self.recording = False
        self.paused = False
        self.playing = False
        self.start_time = 0.0
        self.paused_total = 0.0
        self.pause_started = 0.0
        self.last_move = 0.0
        self.stop_play = threading.Event()
        self.ui_queue = queue.Queue()
        self.current_file = None
        self.win_rect = (0, 0, 0, 0)  # this window's position, so clicks on it aren't recorded
        self.countdown_left = 0  # seconds left before playback starts (shown in the status line)
        self.play_note = ""  # what playback is doing right now, shown in the status line
        self.watch_pictures = []  # pictures to watch for: {"img", "file", "screen_h"}
        self.macro_screen = None  # (w, h) the current macro was made on; None = unknown
        # the program the macro was recorded in: {"exe", "title", "client": [x, y, w, h]} or None
        self.macro_program = None
        # the macro as steps (Edit window); None = just self.events (one recorded step)
        self.actions = None
        # set by the Edit window: the next recording goes to it (callback(events)) instead of
        # replacing the open macro
        self.record_into = None
        self.record_saved = None
        self.record_countdown_left = 0  # seconds left before recording starts
        self.record_countdown_job = None
        self.window_samples = {}  # while recording: window -> [times seen, its info]
        self.raw_mouse = None  # reads camera movement while recording (Windows)
        self.camera_dx = self.camera_dy = 0
        self.camera_last = 0.0
        self.stop_reason = None  # why playback stopped by itself (shown afterwards), None = normal
        # mission results: pictures that mean a run was won ("win") or lost ("loss")
        self.result_pictures = []  # {"img", "file", "screen_h", "kind"}
        self.result_matchers = []
        self.result_state = {}
        self.session = stats.Session()
        self.macro_vary = None  # the open macro's own "Small random timing" choice (from its file)
        self.macro_profile = None  # the settings profile linked to the open macro
        self.auto_stop = None
        self.auto_stopped = None
        self.play_vary = None
        self.away_started = None  # core window only: when playback paused because the game left the front
        self.away_total = 0.0

        self.settings = load_settings()
        diag.setup(os.path.dirname(settings_path()))
        self.hotkeys = dict(DEFAULT_HOTKEYS)  # action -> hotkey id
        saved = self.settings.get("hotkeys")
        if isinstance(saved, dict):
            for action in HOTKEY_ACTIONS:
                if hotkey_is_valid(saved.get(action)):
                    self.hotkeys[action] = saved[action]
        if len(set(self.hotkeys.values())) != len(HOTKEY_ACTIONS):
            self.hotkeys = dict(DEFAULT_HOTKEYS)  # a key used twice: start over with the defaults
        self.capture_callback = None  # set while the hotkeys window waits for a key press
        self.hotkey_window = None

        self.screen_w = root.winfo_screenwidth()
        self.screen_h = root.winfo_screenheight()

        self.kb_ctrl = keyboard.Controller()
        self.mouse_ctrl = mouse.Controller()

        self._build_ui()

        self.kb_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        self.mouse_listener = mouse.Listener(
            on_move=self._on_move, on_click=self._on_click, on_scroll=self._on_scroll
        )
        self.kb_listener.start()
        self.mouse_listener.start()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._process_ui_queue)
        self._refresh()

    # ------------------------------------------------------------ UI

    def _build_ui(self):
        self.root.title("Macro Recorder")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        frame = ttk.Frame(self.root, padding=12)
        frame.grid()

        self.status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.status_var, font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        self.info_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.info_var).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 8))

        self.btn_record = ttk.Button(frame, command=self.toggle_record)
        self.btn_pause = ttk.Button(frame, command=self.toggle_pause)
        self.btn_play = ttk.Button(frame, command=self.play)
        self.btn_stop = ttk.Button(frame, command=self.stop_playback)
        for i, b in enumerate((self.btn_record, self.btn_pause, self.btn_play, self.btn_stop)):
            b.grid(row=2, column=i, padx=2, pady=2, sticky="ew")

        opts = ttk.Frame(frame)
        opts.grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 4))
        ttk.Label(opts, text="Repeat:").grid(row=0, column=0)
        self.repeat_var = tk.IntVar(value=1)
        ttk.Spinbox(opts, from_=1, to=9999, width=6, textvariable=self.repeat_var).grid(row=0, column=1, padx=(2, 8))
        self.loop_var = tk.BooleanVar(value=bool(self.settings.get("loop", True)))
        ttk.Checkbutton(opts, text="Loop forever", variable=self.loop_var,
                        command=self._save_settings).grid(row=0, column=2, padx=(0, 8))
        ttk.Label(opts, text="Speed:").grid(row=0, column=3)
        saved_speed = parse_speed(self.settings.get("speed", 1)) or 1.0
        self.speed_var = tk.StringVar(value=format_speed(saved_speed))
        self.speed_box = ttk.Combobox(opts, width=6, textvariable=self.speed_var, values=SPEED_PRESETS)
        self.speed_box.grid(row=0, column=4, padx=2)
        # type any speed (like 1.3 or 2.5x); it's tidied up when you leave the box or press Enter
        self.speed_box.bind("<FocusOut>", lambda e: self._check_speed(quiet=True))
        self.speed_box.bind("<Return>", lambda e: self._check_speed(quiet=True))
        self.speed_box.bind("<<ComboboxSelected>>", lambda e: self._check_speed(quiet=True))

        ready = ttk.Frame(frame)
        ready.grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(ready, text="Get ready:").grid(row=0, column=0)
        try:
            saved_delay = max(0, min(600, int(self.settings.get("ready_seconds", 3))))
        except (TypeError, ValueError):
            saved_delay = 3
        self.ready_var = tk.IntVar(value=saved_delay)
        ttk.Spinbox(ready, from_=0, to=600, width=5, textvariable=self.ready_var,
                    command=self._save_settings).grid(row=0, column=1, padx=2)
        ttk.Label(ready, text="seconds before playing (0 = start at once)").grid(row=0, column=2)

        self.btn_keys = ttk.Button(ready, text="Hotkeys...", command=self.open_hotkeys)
        self.btn_keys.grid(row=0, column=3, padx=(12, 0))

        # experimental: play into one window in the background
        self.target_windows = []  # [(hwnd, title)]
        self.target_var = tk.StringVar(value=SCREEN_TARGET)
        tgt = ttk.Frame(frame)
        tgt.grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(tgt, text="Play into:").grid(row=0, column=0)
        self.target_box = ttk.Combobox(tgt, width=38, state="readonly", textvariable=self.target_var,
                                       postcommand=self._refresh_windows)
        self.target_box.grid(row=0, column=1, padx=2)
        if background is None:
            self.target_box.config(state="disabled")
        self._refresh_windows()

        self.btn_save = ttk.Button(frame, text="Save...", command=self.save)
        self.btn_load = ttk.Button(frame, text="Open...", command=self.load)
        self.btn_clear = ttk.Button(frame, text="Clear", command=self.clear)
        self.btn_save.grid(row=4, column=0, padx=2, pady=(6, 0), sticky="ew")
        self.btn_load.grid(row=4, column=1, padx=2, pady=(6, 0), sticky="ew")
        self.btn_clear.grid(row=4, column=2, padx=2, pady=(6, 0), sticky="ew")
        if sys.platform == "win32":
            self.btn_link = ttk.Button(frame, text="Link .macro files", command=self.link_file_type)
            self.btn_link.grid(row=4, column=3, padx=2, pady=(6, 0), sticky="ew")

        self._build_resolution_ui(frame)
        self._build_watch_ui(frame)

    def _build_resolution_ui(self, frame):
        """Screen size the macro was made for, and the one to play it on (positions are scaled)."""
        box = ttk.LabelFrame(frame, text="Screen size", padding=8)
        box.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        own = format_resolution((self.screen_w, self.screen_h))
        ttk.Label(box, text="Macro recorded at:").grid(row=0, column=0, sticky="w")
        self.made_for_var = tk.StringVar(value=SAME_AS_PLAY)
        self.made_for_box = ttk.Combobox(box, width=17, textvariable=self.made_for_var,
                                         values=[SAME_AS_PLAY] + RESOLUTIONS)
        self.made_for_box.grid(row=0, column=1, padx=(4, 12), sticky="w")
        self.made_for_box.bind("<<ComboboxSelected>>", lambda e: self._read_made_for(quiet=True))
        self.made_for_box.bind("<FocusOut>", lambda e: self._read_made_for(quiet=True))
        self.made_for_box.bind("<Return>", lambda e: self._read_made_for(quiet=True))

        ttk.Label(box, text="Your screen:").grid(row=0, column=2, sticky="w")
        self.auto_label = f"{AUTO_PREFIX} ({own})"
        saved = self.settings.get("play_resolution")
        start = self.auto_label
        if isinstance(saved, str) and parse_resolution(saved):
            start = format_resolution(parse_resolution(saved))
        self.play_on_var = tk.StringVar(value=start)
        self.play_on_box = ttk.Combobox(box, width=17, textvariable=self.play_on_var,
                                        values=[self.auto_label] + RESOLUTIONS)
        self.play_on_box.grid(row=0, column=3, padx=4, sticky="w")
        for ev in ("<<ComboboxSelected>>", "<FocusOut>", "<Return>"):
            self.play_on_box.bind(ev, lambda e: self._read_play_on(quiet=True))
        ttk.Label(box, text="Some macros were recorded in fullscreen, so those only work in fullscreen.\n"
                            "The app itself works properly in windowed mode too.\n"
                            "The left box is filled in from the macro file and is usually right, so leave it.\n"
                            "\"Your screen\" is found by itself (Auto).",
                  foreground="#b00000", justify="left").grid(row=1, column=0, columnspan=4, sticky="w",
                                                             pady=(6, 0))

    def _read_play_on(self, quiet=False):
        """The screen size to play on: (w, h), or None if the box doesn't hold a size."""
        text = self.play_on_var.get().strip()
        if not text or text.lower().startswith(AUTO_PREFIX.lower()):
            self.play_on_var.set(self.auto_label)
            self.settings.pop("play_resolution", None)
            save_settings(self.settings)
            return (self.screen_w, self.screen_h)
        size = parse_resolution(text)
        if size is None:
            if not quiet:
                messagebox.showerror("Macro Recorder", "\"Your screen\" must be a size like 1920x1080, or Auto.")
            return None
        self.play_on_var.set(format_resolution(size))
        self.settings["play_resolution"] = format_resolution(size)
        save_settings(self.settings)
        return size

    def _read_made_for(self, quiet=False):
        """Reads the "Macro made for" box into self.macro_screen. False if it doesn't hold a size."""
        text = self.made_for_var.get().strip()
        if not text or text.lower().startswith("same"):
            self.macro_screen = None
            self.made_for_var.set(SAME_AS_PLAY)
            return True
        size = parse_resolution(text)
        if size is None:
            if not quiet:
                messagebox.showerror("Macro Recorder",
                                     "\"Macro recorded at\" must be a size like 1920x1080, or \"Same as your screen\".")
            return False
        self.macro_screen = size
        self.made_for_var.set(format_resolution(size))
        return True

    def _show_made_for(self):
        self.made_for_var.set(format_resolution(self.macro_screen) if self.macro_screen else SAME_AS_PLAY)

    def _build_watch_ui(self, frame):
        """'Watch for a picture': while playing, start the macro over when a picture shows on screen."""
        box = ttk.LabelFrame(frame, text="Watch for a picture", padding=8)
        box.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        s = self.settings
        # defaults: a tested AOT:R setup, so a friend only has to open their own macro
        self.watch_var = tk.BooleanVar(value=bool(s.get("watch_enabled", True)))
        self.watch_check = ttk.Checkbutton(
            box, variable=self.watch_var, command=self._save_settings,
            text="While playing, watch for these pictures (Change… says what each one does when it shows)")
        self.watch_check.grid(row=0, column=0, columnspan=4, sticky="w")

        buttons = ttk.Frame(box)
        buttons.grid(row=1, column=0, columnspan=4, sticky="w", pady=4)
        self.btn_pick = ttk.Button(buttons, text="Add from screen...", command=self.pick_watch_picture)
        self.btn_pick_file = ttk.Button(buttons, text="Add picture file...", command=self.load_watch_picture)
        self.btn_test = ttk.Button(buttons, text="Test now", command=self.test_watch_picture)
        self.btn_pick.grid(row=0, column=0, padx=(0, 4))
        self.btn_pick_file.grid(row=0, column=1, padx=4)
        self.btn_builtin = ttk.Button(buttons, text="Add built-in RETRY", command=self.add_builtin_picture)
        self.btn_test.grid(row=0, column=4, padx=4)
        self.btn_builtin.grid(row=0, column=2, padx=4)
        self.btn_builtin_dc = ttk.Button(buttons, text="Add built-in Disconnected",
                                         command=self.add_builtin_disconnect)
        self.btn_builtin_dc.grid(row=0, column=3, padx=4)
        self.watch_list = ttk.Frame(box)  # one row per picture: thumbnail + Remove
        self.watch_list.grid(row=2, column=0, columnspan=4, sticky="w")

        row = ttk.Frame(box)
        row.grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.watch_click_var = tk.BooleanVar(value=bool(s.get("watch_click", False)))
        ttk.Label(row, text="When it shows:").grid(row=0, column=0)
        ttk.Checkbutton(row, variable=self.watch_click_var, command=self._save_settings,
                        text="click on it (like a Retry button),").grid(row=0, column=1, padx=4)
        ttk.Label(row, text="wait").grid(row=0, column=2)
        self.watch_wait_var = tk.IntVar(value=int_setting(s, "watch_wait", 3, 0, 600))
        ttk.Spinbox(row, from_=0, to=600, width=5, textvariable=self.watch_wait_var,
                    command=self._save_settings).grid(row=0, column=3, padx=2)
        ttk.Label(row, text="s, then start the macro over.").grid(row=0, column=4)

        row1 = ttk.Frame(box)
        row1.grid(row=5, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Label(row1, text="Match:").grid(row=0, column=0)
        self.watch_match_var = tk.IntVar(value=int_setting(s, "watch_match", 85, 50, 99))
        ttk.Spinbox(row1, from_=50, to=99, width=4, textvariable=self.watch_match_var,
                    command=self._save_settings).grid(row=0, column=1, padx=2)
        ttk.Label(row1, text="%").grid(row=0, column=2)

        row2 = ttk.Frame(box)
        row2.grid(row=4, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Label(row2, text="If the macro ends before the picture shows, wait up to").grid(row=0, column=0)
        self.watch_end_var = tk.IntVar(value=int_setting(s, "watch_end_wait", 3, 0, 3600))
        ttk.Spinbox(row2, from_=0, to=3600, width=5, textvariable=self.watch_end_var,
                    command=self._save_settings).grid(row=0, column=1, padx=2)
        ttk.Label(row2, text="s for it").grid(row=0, column=2)

        self.watch_bg_var = tk.BooleanVar(value=bool(s.get("watch_ignore_bg", True)))
        ttk.Checkbutton(row1, variable=self.watch_bg_var, command=self._save_settings,
                        text="Ignore the background around text").grid(row=0, column=3, padx=(12, 0))

        # safety: a picture that keeps showing (a stuck screen) mustn't restart the macro forever
        row3 = ttk.Frame(box)
        row3.grid(row=6, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Label(row3, text="Safety limit: stop if it starts over more than").grid(row=0, column=0)
        self.watch_limit_var = tk.IntVar(value=int_setting(s, "watch_limit_count", 10, 0, 1000))
        ttk.Spinbox(row3, from_=0, to=1000, width=5, textvariable=self.watch_limit_var,
                    command=self._save_settings).grid(row=0, column=1, padx=2)
        ttk.Label(row3, text="times in").grid(row=0, column=2)
        self.watch_limit_s_var = tk.IntVar(value=int_setting(s, "watch_limit_seconds", 60, 1, 3600))
        ttk.Spinbox(row3, from_=1, to=3600, width=5, textvariable=self.watch_limit_s_var,
                    command=self._save_settings).grid(row=0, column=3, padx=2)
        ttk.Label(row3, text="s  (0 = no limit)").grid(row=0, column=4)
        self.watch_shift_var = tk.BooleanVar(value=bool(s.get("watch_shift_lock", True)))
        ttk.Checkbutton(box, variable=self.watch_shift_var, command=self._save_settings,
                        text="Before clicking it, press Shift if the mouse pointer is hidden (Roblox Shift Lock)"
                        ).grid(row=7, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self.watch_embed_var = tk.BooleanVar(value=bool(s.get("watch_save_with_macro", True)))
        ttk.Checkbutton(box, variable=self.watch_embed_var, command=self._save_settings,
                        text="Save these pictures inside the macros you save (friends get them with the macro)"
                        ).grid(row=8, column=0, columnspan=4, sticky="w", pady=(4, 0))

        self.watch_widgets = [self.watch_check, self.btn_pick, self.btn_pick_file, self.btn_test,
                              self.btn_builtin, self.btn_builtin_dc]
        self.watch_remove_buttons = []
        if image_watch is None:
            self.watch_var.set(False)
            ttk.Label(self.watch_list, foreground="gray",
                      text="Not available: this copy was built without picture support.").grid(sticky="w")
            return
        saved = s.get("watch_pictures")
        if not isinstance(saved, list):
            # first start: the built-in pictures are added by the Picture watch setup (picture_window.py)
            saved = []
        for entry in saved:
            pic = watch_picture_from(entry)
            if pic is not None:  # (picture file gone: forget it)
                self.watch_pictures.append(pic)
        self._show_watch_pictures()

    def _show_watch_pictures(self):
        for child in self.watch_list.winfo_children():
            child.destroy()
        self.watch_thumbs = []
        self.watch_remove_buttons = []
        if not self.watch_pictures:
            ttk.Label(self.watch_list, text="No picture yet", foreground="gray").grid(sticky="w")
        for i, pic in enumerate(self.watch_pictures):
            thumb, w, h = picture_thumb(pic, 300, 50)
            self.watch_thumbs.append(thumb)
            # the picture and its size in two labels: a label with a picture can't show the
            # background picture behind its text
            cell = ttk.Frame(self.watch_list)
            cell.grid(row=i, column=0, sticky="w", pady=1)
            ttk.Label(cell, image=thumb).pack(side="left")
            ttk.Label(cell, text=f"  {w} x {h}").pack(side="left")
            b = ttk.Button(self.watch_list, text="Remove", command=lambda i=i: self._remove_watch_picture(i))
            b.grid(row=i, column=1, padx=(8, 0))
            self.watch_remove_buttons.append(b)
        self.settings["watch_pictures"] = [watch_entry(p) for p in self.watch_pictures]
        save_settings(self.settings)

    def add_builtin_picture(self):
        """Add the RETRY picture that comes with the app (AOT:R's Retry button, taken on a 1080p screen)."""
        if self.recording or self.playing:
            return
        try:
            self._add_watch_picture(image_watch.load_image(resource_path(BUILTIN_PICTURE)),
                                    screen_h=BUILTIN_PICTURE_SCREEN_H, fields={"builtin": "retry", "name": "RETRY"})
        except Exception as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't add the built-in picture:\n{exc}")

    def add_builtin_disconnect(self):
        """Add the word "Disconnected" (Roblox's Disconnected box) with the action that plays a rejoin
        macro; the rejoin macro itself is chosen with Change…."""
        if self.recording or self.playing:
            return
        try:
            self._add_watch_picture(image_watch.load_image(resource_path(BUILTIN_DISCONNECT)),
                                    screen_h=BUILTIN_DISCONNECT_SCREEN_H,
                                    fields={"name": "Disconnected", "action": "recover", "builtin": "disconnect"})
        except Exception as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't add the built-in picture:\n{exc}")

    def _add_watch_picture(self, img, screen_h=None, fields=None):
        name = f"picture_{int(time.time() * 1000)}.png"
        image_watch.save_image(os.path.join(watch_dir(), name), img)
        self.watch_pictures.append(dict({"img": img, "file": name, "screen_h": screen_h}, **(fields or {})))
        self.watch_var.set(True)
        self._save_settings()
        self._show_watch_pictures()
        self._refresh()

    def _remove_watch_picture(self, index):
        if self.recording or self.playing or index >= len(self.watch_pictures):
            return
        pic = self.watch_pictures.pop(index)
        try:
            os.remove(os.path.join(watch_dir(), pic["file"]))
        except OSError:
            pass
        self._show_watch_pictures()
        self._refresh()

    def _refresh_windows(self):
        names = [SCREEN_TARGET]
        self.target_windows = []
        if background is not None:
            own = self.root.winfo_toplevel().title()
            for hwnd, title in background.list_windows():
                if title in (own, "Program Manager"):
                    continue
                self.target_windows.append((hwnd, title))
                names.append(f"[background] {title}")
        self.target_box.config(values=names)
        if self.target_var.get() not in names:
            self.target_var.set(SCREEN_TARGET)

    def _selected_hwnd(self):
        label = self.target_var.get()
        for hwnd, title in self.target_windows:
            if label == f"[background] {title}":
                return hwnd
        return None

    def _refresh(self):
        if self.record_countdown_left > 0:
            state = f"Get ready... recording starts in {self.record_countdown_left}"
        elif self.recording:
            state = "Recording paused" if self.paused else "Recording..."
        elif self.playing and self.countdown_left > 0:
            state = f"Get ready... starting in {self.countdown_left}"
        elif self.playing:
            state = self.play_note or "Playing..."
        else:
            state = "Ready"
        self.status_var.set(state)
        k = {action: hotkey_name(self.hotkeys[action]) for action in HOTKEY_ACTIONS}

        name = os.path.basename(self.current_file) if self.current_file else "unsaved"
        length = self.events[-1]["t"] if self.events else 0.0
        self.info_var.set(f"{len(self.events)} actions, {length:.1f} s  ({name})")

        busy = self.recording or self.playing
        self.btn_record.config(text=f"Stop recording ({k['record']})" if self.recording
                               else f"Record ({k['record']})",
                               state="disabled" if self.playing else "normal")
        self.btn_pause.config(text=f"Resume ({k['pause']})" if self.paused else f"Pause ({k['pause']})",
                              state="normal" if self.recording else "disabled")
        self.btn_play.config(text=f"Play ({k['play']})",
                             state="disabled" if busy or not self.events else "normal")
        self.btn_stop.config(text=f"Stop ({k['stop']})", state="normal" if self.playing else "disabled")
        for b in (self.btn_save, self.btn_load, self.btn_clear, self.btn_keys):
            b.config(state="disabled" if busy else "normal")
        for b in (self.made_for_box, self.play_on_box):
            b.config(state="disabled" if busy else "normal")
        for b in self.watch_widgets + self.watch_remove_buttons:
            b.config(state="disabled" if busy or image_watch is None else "normal")

    # ------------------------------------------------------------ settings

    def _check_speed(self, quiet=False):
        """Read the speed box. Returns the speed, or None (with a message unless quiet) if it's not valid."""
        speed = parse_speed(self.speed_var.get())
        if speed is None:
            if not quiet:
                messagebox.showerror(
                    "Macro Recorder",
                    f"Speed must be a number from {MIN_SPEED:g} to {MAX_SPEED:g}, like 1.5 or 2.5x.",
                )
            return None
        self.speed_var.set(format_speed(speed))
        self._save_settings()
        return speed

    def _ready_seconds(self):
        try:
            return max(0, min(600, int(self.ready_var.get())))
        except (tk.TclError, ValueError):
            return 0

    def _save_settings(self):
        self.settings["hotkeys"] = dict(self.hotkeys)
        self.settings["loop"] = bool(self.loop_var.get())
        speed = parse_speed(self.speed_var.get())
        if speed is not None:
            self.settings["speed"] = speed
        try:
            self.settings["ready_seconds"] = max(0, min(600, int(self.ready_var.get())))
        except (tk.TclError, ValueError):
            pass
        if hasattr(self, "watch_var"):
            self.settings["watch_enabled"] = bool(self.watch_var.get())
            self.settings["watch_ignore_bg"] = bool(self.watch_bg_var.get())
            self.settings["watch_click"] = bool(self.watch_click_var.get())
            self.settings["watch_shift_lock"] = bool(self.watch_shift_var.get())
            self.settings["watch_save_with_macro"] = bool(self.watch_embed_var.get())
            for name, var, low, high in (("watch_wait", self.watch_wait_var, 0, 600),
                                         ("watch_match", self.watch_match_var, 50, 99),
                                         ("watch_end_wait", self.watch_end_var, 0, 3600),
                                         ("watch_limit_count", self.watch_limit_var, 0, 1000),
                                         ("watch_limit_seconds", self.watch_limit_s_var, 1, 3600)):
                try:
                    self.settings[name] = max(low, min(high, int(var.get())))
                except (tk.TclError, ValueError):
                    pass
        save_settings(self.settings)

    # ------------------------------------------------------------ watch for a picture

    def pick_watch_picture(self):
        """Freeze the screen and let the user drag a box around the picture to watch for."""
        if self.recording or self.playing:
            return
        self.root.withdraw()
        self.root.after(300, self._show_picker)

    def _show_picker(self, on_pick=None, on_cancel=None, hidden=()):
        """Freeze the screen and let the user drag a box. on_pick(img, screen_h) gets the picture
        (default: add it to the pictures to watch for). hidden: other windows to show again after."""
        def show_again():
            self.root.deiconify()
            stack = getattr(self, "window_stack", None)
            if stack is not None:
                stack.bring_back(list(hidden))  # (the window it was picked from in front again)
                return
            for w in hidden:
                try:
                    w.deiconify()
                except tk.TclError:
                    pass
        try:
            shot = image_watch.grab_screen()
            with image_watch.mss.mss() as sct:
                mon = image_watch.primary_monitor(sct)
        except Exception as exc:
            show_again()
            messagebox.showerror("Macro Recorder", f"Couldn't take a screenshot:\n{exc}")
            return
        h, w = shot.shape[:2]
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(f"{w}x{h}+{mon['left']}+{mon['top']}")
        canvas = tk.Canvas(win, width=w, height=h, highlightthickness=0, cursor="crosshair")
        canvas.pack()
        photo = tk.PhotoImage(data=image_watch.png_data(shot))
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.photo = photo
        tip = ("Drag a box around the picture to watch for (for a banner, just around its text and line). "
               "Esc cancels.")
        canvas.create_rectangle(0, 0, w, 36, fill="black", outline="")
        canvas.create_text(w // 2, 18, text=tip, fill="white", font=("Segoe UI", 12, "bold"))
        state = {"start": None, "rect": None}

        def close():
            win.destroy()
            show_again()

        def cancel():
            close()
            if on_cancel:
                on_cancel()

        def down(e):
            state["start"] = (e.x, e.y)
            if state["rect"]:
                canvas.delete(state["rect"])
            state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2)

        def drag(e):
            if state["start"]:
                x0, y0 = state["start"]
                canvas.coords(state["rect"], x0, y0, e.x, e.y)

        def up(e):
            if not state["start"]:
                return
            x0, y0 = state["start"]
            left, right = sorted((max(0, x0), min(w, e.x)))
            top, bottom = sorted((max(0, y0), min(h, e.y)))
            state["start"] = None
            if right - left < 10 or bottom - top < 10:
                return  # too small, probably a stray click: let them try again
            close()
            try:
                (on_pick or (lambda img, sh: self._add_watch_picture(img, screen_h=sh)))(
                    shot[top:bottom, left:right].copy(), h)
            except Exception as exc:
                messagebox.showerror("Macro Recorder", f"Couldn't use that picture:\n{exc}")

        canvas.bind("<ButtonPress-1>", down)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", up)
        win.bind("<Escape>", lambda e: cancel())
        win.focus_force()

    def load_watch_picture(self):
        if self.recording or self.playing:
            return
        path = filedialog.askopenfilename(
            filetypes=[("Pictures", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")])
        if not path:
            return
        try:
            self._add_watch_picture(image_watch.load_image(path), screen_h=None)
        except Exception as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't use that picture:\n{exc}")

    def _hide_own_window(self, screen, origin):
        """Black out this app's window on a screenshot: it shows the pictures themselves in its list,
        and they must not count as seen. (A plain black area never matches.)"""
        left, top, right, bottom = self.win_rect
        ox, oy = origin
        pad = 40  # the title bar and border too
        x0, y0 = max(0, left - ox - pad), max(0, top - oy - pad)
        x1, y1 = max(0, right - ox + pad), max(0, bottom - oy + pad)
        screen[y0:y1, x0:x1] = 0
        return screen

    def _picture_active(self, pic, path=None):
        """Whether a picture is used now: it's on, its group is on, and it's for every macro or for
        this one (path: the macro; None = the open one)."""
        if pic.get("on") is False:
            return False
        gid = picture_group(pic)
        for g in self.settings.get("picture_groups") or []:
            if isinstance(g, dict) and g.get("id") == gid:
                if g.get("on") is False:
                    return False
                break
        macros = pic.get("macros")
        if macros:
            path = path if path is not None else self.current_file
            if not path:
                return False
            key = self._macro_key(path)
            return any(isinstance(m, str) and self._macro_key(m) == key for m in macros)
        return True

    def _active_watch_pictures(self, path=None):
        return [p for p in self.watch_pictures if self._picture_active(p, path)]

    def _active_result_pictures(self, path=None):
        return [p for p in self.result_pictures if self._picture_active(p, path)]

    def _make_matchers(self):
        matchers = []
        for pic in self._active_watch_pictures():
            m = image_watch.Matcher(pic["img"], picked_screen_h=pic["screen_h"],
                                    ignore_background=bool(self.watch_bg_var.get()), screen_h=self.screen_h)
            # where it was found last time (this session): the next playback looks there first
            m.last_rect = pic.get("seen_rect")
            m.picture_entry = pic
            matchers.append(m)
        return matchers

    def test_watch_picture(self):
        """Look at the screen once and say how well each picture matches right now."""
        if not self.watch_pictures:
            messagebox.showinfo("Macro Recorder", "Add a picture first.")
            return
        self._save_settings()
        need = self.settings.get("watch_match", 80)
        try:
            screen = self._hide_own_window(image_watch.grab_screen(), image_watch.screen_origin())
            scores =[round(m.find(screen)[0] * 100) for m in self._make_matchers()]
        except Exception as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't check the screen:\n{exc}")
            return
        lines = [f"Picture {i}: {pct}%  ({'counts as seen' if pct >= need else 'not seen'})"
                 for i, pct in enumerate(scores, start=1)]
        messagebox.showinfo(
            "Macro Recorder",
            "How well each picture matches the screen right now (it counts as seen from "
            f"{need}%):\n\n" + "\n".join(lines) +
            "\n\nTry this while a picture is showing, and again while it isn't. Set Match between the two.")

    # ------------------------------------------------------------ hotkeys window

    def open_hotkeys(self):
        if self.recording or self.playing:
            return
        if self.hotkey_window is not None and self.hotkey_window.winfo_exists():
            self.hotkey_window.lift()
            return
        win = tk.Toplevel(self.root)
        self.hotkey_window = win
        win.title("Hotkeys")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.transient(self.root)
        body = ttk.Frame(win, padding=12)
        body.grid()
        ttk.Label(body, text="Click Change, then press the key you want. Esc cancels.\n"
                             "Pick keys you don't use in the game: a hotkey is never recorded or sent.",
                  justify="left").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        key_vars = {}
        change_buttons = {}

        def show():
            for action in HOTKEY_ACTIONS:
                key_vars[action].set(hotkey_name(self.hotkeys[action]))

        def finish_capture():
            self.capture_callback = None
            for b in change_buttons.values():
                b.config(state="normal")
            show()

        def start_capture(action):
            for b in change_buttons.values():
                b.config(state="disabled")
            key_vars[action].set("Press a key...")

            def got_key(key_id):  # runs on the Tk thread
                if not win.winfo_exists():
                    self.capture_callback = None
                    return
                if key_id == "esc" or key_id is None:
                    finish_capture()
                    return
                for other in HOTKEY_ACTIONS:
                    if other != action and self.hotkeys[other] == key_id:
                        # swap, so two actions never share a key
                        self.hotkeys[other] = self.hotkeys[action]
                self.hotkeys[action] = key_id
                self._save_settings()
                finish_capture()
                self._refresh()

            self.capture_callback = got_key

        for row, action in enumerate(HOTKEY_ACTIONS, start=1):
            ttk.Label(body, text=HOTKEY_LABELS[action] + ":").grid(row=row, column=0, sticky="w", pady=2)
            key_vars[action] = tk.StringVar()
            ttk.Label(body, textvariable=key_vars[action], width=16,
                      font=("Segoe UI", 10, "bold")).grid(row=row, column=1, sticky="w", padx=8)
            change_buttons[action] = ttk.Button(body, text="Change", command=lambda a=action: start_capture(a))
            change_buttons[action].grid(row=row, column=2, pady=2)

        def reset():
            self.hotkeys = dict(DEFAULT_HOTKEYS)
            self._save_settings()
            finish_capture()
            self._refresh()

        def close():
            self.capture_callback = None
            self.hotkey_window = None
            win.destroy()

        bottom = ttk.Frame(body)
        bottom.grid(row=len(HOTKEY_ACTIONS) + 1, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(bottom, text="Reset to F9-F12", command=reset).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(bottom, text="Done", command=close).grid(row=0, column=1)
        win.protocol("WM_DELETE_WINDOW", close)
        show()

    def _process_ui_queue(self):
        try:
            while True:
                action = self.ui_queue.get_nowait()
                action()
        except queue.Empty:
            pass
        r = self.root
        self.win_rect = (r.winfo_rootx(), r.winfo_rooty(),
                         r.winfo_rootx() + r.winfo_width(), r.winfo_rooty() + r.winfo_height())
        # (half as often while nothing is being recorded or played)
        busy = self.recording or self.playing or self.record_countdown_left > 0
        self.ui_queue_job = self.root.after(50 if busy else 100, self._process_ui_queue)

    def _call_ui(self, fn):
        """Run fn on the Tk thread (listeners run on their own threads)."""
        self.ui_queue.put(fn)

    # ------------------------------------------------------------ recording

    def toggle_record(self):
        if self.playing:
            return
        if self.record_countdown_left > 0:  # Record pressed again during the countdown: don't record
            self._cancel_record_countdown()
            return
        if self.recording:
            self.recording = False
            self.paused = False
            self._stop_camera()
            if self.record_into is not None:
                # recorded for the Edit window: the open macro comes back as it was
                recorded, done = drop_stray_clicks(self.events), self.record_into
                (self.events, self.actions, self.current_file, self.macro_screen, self.macro_program) = \
                    self.record_saved
                self.record_into = self.record_saved = None
                self._show_made_for()
                diag.info(f"Recording for the Edit window stopped: {len(recorded)} actions")
                self._refresh()
                self.root.after(0, lambda: done(recorded))
                return
            self.macro_program = self._recorded_program()
            n = len(self.events)
            self.events = drop_stray_clicks(self.events)
            if len(self.events) != n:
                diag.info(f"Left out {n - len(self.events)} mouse press(es) that were never let go of")
            diag.info(f"Recording stopped: {len(self.events)} actions"
                      + (f", program {self.macro_program['exe']}" if self.macro_program else ""))
        else:
            if self.record_into is None and self.events and not messagebox.askyesno(
                "Macro Recorder", "Start a new recording? The current one will be replaced."
            ):
                return
            seconds = self._record_ready_seconds()
            if seconds > 0:
                self._start_record_countdown(seconds)
                return
            self._begin_recording()
            return
        self._refresh()

    def _record_ready_seconds(self):
        """The countdown before recording starts (Settings > Recording; 0 = at once)."""
        return int_setting(self.settings, "record_ready_seconds", 3, 0, 600)

    def _start_record_countdown(self, seconds):
        self.record_countdown_left = seconds
        diag.info(f"Recording starts in {seconds} s")
        self._record_countdown_tick(seconds)
        self._refresh()
        self.record_countdown_job = self.root.after(1000, self._record_countdown_next)

    def _record_countdown_next(self):
        self.record_countdown_job = None
        if self.record_countdown_left <= 0:
            return
        self.record_countdown_left -= 1
        if self.record_countdown_left <= 0:
            self._begin_recording()
            return
        self._record_countdown_tick(self.record_countdown_left)
        self._refresh()
        self.record_countdown_job = self.root.after(1000, self._record_countdown_next)

    def _cancel_record_countdown(self):
        if self.record_countdown_job is not None:
            self.root.after_cancel(self.record_countdown_job)
            self.record_countdown_job = None
        self.record_countdown_left = 0
        diag.info("Recording cancelled during the countdown")
        done, self.record_into = self.record_into, None
        if done is not None:  # (the Edit window gets nothing, and comes back)
            self.root.after(0, lambda: done([]))
        self._refresh()

    def _record_countdown_tick(self, seconds_left):
        """Each second of the countdown before recording (the dark window plays a sound)."""

    def _recording_began(self):
        """Recording has really started (after the countdown)."""

    def _begin_recording(self):
        self.record_countdown_left = 0
        if self.record_into is not None:
            self.record_saved = (self.events, self.actions, self.current_file, self.macro_screen,
                                 self.macro_program)
        self.events = []
        self.actions = None
        self.current_file = None
        self.macro_screen = (self.screen_w, self.screen_h)  # recorded on this screen
        self.macro_program = None
        self.window_samples = {}
        self._show_made_for()
        self.paused = False
        self.paused_total = 0.0
        self.start_time = time.perf_counter()
        self.recording = True
        self._add_held_buttons()
        self._start_camera()
        diag.info("Recording started" + (" with camera movement" if self.raw_mouse else ""))
        self._recording_began()
        self._refresh()

    def _add_held_buttons(self):
        """A mouse button already held down when recording starts is recorded as pressed at the start
        (otherwise its later release would come without a press)."""
        try:
            held = window_tools.held_mouse_buttons()
            if not held:
                return
            x, y = self.mouse_ctrl.position
            for name in held:
                self.events.append({"type": "click", "x": int(x), "y": int(y), "button": name, "pressed": True,
                                    "t": 0.0})
        except Exception as exc:
            diag.error("Couldn't read held mouse buttons", exc)

    # ------------------------------------------------------------ camera movement (Windows)

    def _camera_wanted(self):
        return bool(self.settings.get("record_camera", False))

    def _start_camera(self):
        self._stop_camera()
        if not self._camera_wanted() or not raw_mouse.IS_WIN:
            return
        self.camera_dx = self.camera_dy = 0
        self.camera_last = time.perf_counter()
        rm = raw_mouse.RawMouse(self._on_raw_move)
        if rm.start():
            self.raw_mouse = rm
        else:
            diag.error("Camera recording couldn't start (Raw Input)")

    def _stop_camera(self):
        rm, self.raw_mouse = self.raw_mouse, None
        if rm is not None:
            self._flush_camera()
            rm.stop()

    def _camera_turning(self):
        """While the game hides the pointer (Shift Lock, holding the right button), mouse movement
        turns the camera: it's recorded as camera movement instead of positions."""
        if self.raw_mouse is None:
            return False
        # asked at most every 10 ms (the mouse can report up to 1000 times a second)
        now = time.perf_counter()
        cached = getattr(self, "hidden_cache", (0.0, False))
        if now - cached[0] >= 0.01:
            cached = self.hidden_cache = (now, window_tools.cursor_hidden() is True)
        return cached[1]

    def _on_raw_move(self, dx, dy):
        """The mouse itself moved (Raw Input thread). Small movements are added up into one step
        every few milliseconds, so playback sends them at the same pace the mouse did."""
        if not self._capturing() or not self._camera_turning():
            self._flush_camera()
            return
        self.camera_dx += dx
        self.camera_dy += dy
        if time.perf_counter() - self.camera_last >= CAMERA_STEP:
            self._flush_camera()

    def _flush_camera(self):
        dx, dy = self.camera_dx, self.camera_dy
        self.camera_dx = self.camera_dy = 0
        self.camera_last = time.perf_counter()
        if (dx or dy) and self.recording:
            self._add({"type": "move_rel", "dx": int(dx), "dy": int(dy)})

    # ------------------------------------------------------------ the program a macro is recorded in

    def _note_window(self):
        """While recording: remember which program's window is in front (on each click and key)."""
        try:
            hwnd = window_tools.foreground()
            if not hwnd or window_tools.pid_of(hwnd) == os.getpid():
                return
            entry = self.window_samples.get(hwnd)
            if entry is None:
                info = window_tools.program_info(hwnd)
                if info is None:
                    return
                entry = self.window_samples[hwnd] = [0, info]
            entry[0] += 1
        except Exception:
            pass

    def _recorded_program(self):
        if not self.window_samples:
            return None
        return max(self.window_samples.values(), key=lambda e: e[0])[1]

    def toggle_pause(self):
        if not self.recording:
            return
        now = time.perf_counter()
        if self.paused:
            self.paused_total += now - self.pause_started
            self.paused = False
        else:
            self.pause_started = now
            self.paused = True
        self._refresh()

    def _capturing(self):
        return self.recording and not self.paused

    def _on_own_window(self, x, y):
        left, top, right, bottom = self.win_rect
        return left <= x < right and top <= y < bottom

    def _elapsed(self):
        return time.perf_counter() - self.start_time - self.paused_total

    def _add(self, event):
        event["t"] = round(self._elapsed(), 4)
        self.events.append(event)

    def _on_move(self, x, y):
        if not self._capturing() or self._camera_turning():
            return
        now = time.perf_counter()
        if now - self.last_move < MOVE_INTERVAL:
            return
        self.last_move = now
        self._add({"type": "move", "x": x, "y": y})

    def _on_click(self, x, y, button, pressed):
        if self._capturing() and not self._on_own_window(x, y):
            self._flush_camera()  # camera movement before the click stays before it
            self._add({"type": "click", "x": x, "y": y, "button": button.name, "pressed": pressed})
            if pressed:
                self._note_window()

    def _on_scroll(self, x, y, dx, dy):
        if self._capturing() and not self._on_own_window(x, y):
            self._add({"type": "scroll", "x": x, "y": y, "dx": dx, "dy": dy})

    def _hotkey_action(self, key):
        key_id = hotkey_id(key)
        for action, hk in self.hotkeys.items():
            if hk == key_id:
                return action
        return None

    def _emergency_key(self, key, pressed):
        """Keeps track of Ctrl and Alt; True when End is pressed while both are down."""
        mods = self.__dict__.setdefault("mods_down", set())
        which = {keyboard.Key.ctrl: "ctrl", keyboard.Key.ctrl_l: "ctrl", keyboard.Key.ctrl_r: "ctrl",
                 keyboard.Key.alt: "alt", keyboard.Key.alt_l: "alt", keyboard.Key.alt_r: "alt",
                 keyboard.Key.alt_gr: "alt"}.get(key)
        if which:
            mods.add(which) if pressed else mods.discard(which)
            return False
        return pressed and key == keyboard.Key.end and mods >= {"ctrl", "alt"}

    def emergency_stop(self):
        """Stop everything now: playback (also while it counts down or waits), recording and its
        countdown. Ctrl+Alt+End does this whatever the hotkeys are set to."""
        diag.info("Emergency stop")
        self.stop_play.set()
        self.capture_callback = None
        if self.record_countdown_left > 0:
            self._cancel_record_countdown()
        if self.recording:
            self.toggle_record()
        if self.playing:
            self.stop_playback()

    def _on_key_press(self, key):
        if self._emergency_key(key, True):
            self.stop_play.set()  # (at once, from this thread: works even if the window is busy)
            self._call_ui(self.emergency_stop)
            return
        callback = self.capture_callback
        if callback is not None:  # the hotkeys window is waiting for a key
            key_id = hotkey_id(key)
            self._call_ui(lambda: callback(key_id))
            return
        action = self._hotkey_action(key)
        if action is not None:
            handler = {
                "record": self.toggle_record,
                "pause": self.toggle_pause,
                "play": self.play,
                "stop": self.stop_playback,
            }[action]
            self._call_ui(handler)
            return
        if self._capturing():
            self._add({"type": "key", "key": key_to_data(key), "pressed": True})
            self._note_window()

    def _on_key_release(self, key):
        self._emergency_key(key, False)
        if self._hotkey_action(key) is not None:
            return
        if self._capturing():
            self._add({"type": "key", "key": key_to_data(key), "pressed": False})

    # ------------------------------------------------------------ playback

    def play(self):
        if self.recording or self.playing or self.record_countdown_left > 0 or not (self.events or self.actions) \
                or self.capture_callback is not None:
            return
        try:
            repeats = max(1, int(self.repeat_var.get()))
        except (tk.TclError, ValueError):
            repeats = 1
        loop = self.loop_var.get()
        speed = self._check_speed()
        if speed is None:
            return
        play_on = self._read_play_on()
        if play_on is None or not self._read_made_for():
            return
        # move mouse positions from the size the macro was made for to the size it's played on
        events = self._events_for_play(play_on)  # (the macro's steps, fitted to this screen)
        try:
            # "Play another macro" steps: those macros are read now, so a missing file shows at once
            own = (self._macro_key(self.current_file),) if self.current_file else ()
            events = self._resolve_macros(events, play_on, own)
        except Exception as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't use a \"Play another macro\" step:\n{exc}")
            return
        try:
            self.wait_matchers = self._make_wait_matchers(events)
        except Exception as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't use a \"Wait for a picture\" step:\n{exc}")
            return
        ready = self._ready_seconds()
        bg = None
        if self.target_var.get() != SCREEN_TARGET:
            hwnd = self._selected_hwnd()
            if not hwnd or not background.is_usable(hwnd):
                messagebox.showerror("Macro Recorder", "That window is gone. Pick it again in \"Play into\".")
                self._refresh_windows()
                return
            if background.is_minimized(hwnd):
                messagebox.showerror("Macro Recorder", "That window is minimized. Restore it first "
                                     "(it can stay behind other windows).")
                return
            bg = background.BackgroundPlayer(hwnd)
        self._save_settings()
        watch = None
        if image_watch is not None and self.watch_var.get() and self._active_watch_pictures():
            # (with no picture on for this macro, it plays without watching: the status line says so)
            try:
                watch = {
                    "matchers": self._make_matchers(),
                    "need": self.settings.get("watch_match", 80) / 100.0,
                    "wait": self.settings.get("watch_wait", 3),
                    "end_wait": self.settings.get("watch_end_wait", 60),
                    "click": bool(self.watch_click_var.get()),
                    "macros": {},  # file -> the steps of a macro a picture plays or switches to
                    "confirm": {},  # id(picture) -> what to look for after a rejoin macro
                }
                self._prepare_watch_actions(watch, play_on)
            except Exception as exc:
                messagebox.showerror("Macro Recorder", f"Couldn't use the picture:\n{exc}")
                return
        # "If the game closes": its rejoin macro is read now, so a missing file shows at once
        self.closed_steps = None
        closed = self._closed_settings()
        if closed["action"] == "reopen" and closed["macro"]:
            try:
                self.closed_steps = self._load_for_play(closed["macro"], play_on)
                self.wait_matchers.update(self._make_wait_matchers(self.closed_steps))
            except Exception as exc:
                messagebox.showerror("Macro Recorder", "Couldn't use the rejoin macro of \"If the game "
                                     "closes\" (Settings > Playback):\n" + str(exc))
                return
        self.result_matchers = self._build_result_matchers()
        alltime = self.settings.get("stats_all") if isinstance(self.settings.get("stats_all"), dict) else {}
        self.session = stats.Session(self._macro_name(), fragments_before=int(alltime.get("fragments", 0)))
        if watch is not None:
            watch["limit_count"] = int_setting(self.settings, "watch_limit_count", 10, 0, 1000)
            watch["limit_seconds"] = int_setting(self.settings, "watch_limit_seconds", 60, 1, 3600)
            watch["shift_lock"] = bool(self.settings.get("watch_shift_lock", True))
        self.auto_stop = self._prepare_auto_stop()
        self.auto_stopped = None
        self.play_vary = self._vary_now()
        self.stop_play.clear()
        self.stop_reason = None
        self.away_started = None
        self.away_total = 0.0
        self.playing = True
        self.countdown_left = ready
        self.play_note = ""
        if image_watch is not None and self.watch_var.get():
            n = len(watch["matchers"]) if watch else 0
            self.play_note = (f"Watching {n} picture{'s' if n != 1 else ''}" if n
                              else "Picture watch: no picture is on for this macro")
        self.play_bg = bg
        self._refresh()
        diag.info(f"Playing: {workflow.count_events(events)} recorded actions in {len(events)} step(s), speed {speed:g}, "
                  + ("loop" if loop else f"{repeats} time(s)") + (", picture watch" if watch else "")
                  + (", background window" if bg else ""))
        threading.Thread(target=self._play_worker,
                         args=(events, repeats, loop, speed, bg, ready, watch),
                         daemon=True).start()

    def _build_result_matchers(self):
        """The result pictures, ready to look for (each at its own size and two others)."""
        matchers = []
        if image_watch is not None and self.settings.get("results_enabled", True):
            for pic in self._active_result_pictures():
                # a result title can show at quite another size than when the picture was taken (other
                # screen or window size), so it's also looked for a quarter smaller and a third bigger
                base_h = pic["screen_h"] or self.screen_h
                # the size it was found at before (remembered per picture and screen) goes first; the
                # other sizes are only looked for if it isn't found at that size for a while
                known = pic.get("found_factor") if pic.get("found_screen") == [self.screen_w, self.screen_h] \
                    else None
                factors = [known] + [f for f in (1.0, 1.33, 0.75) if f != known] if known else [1.0, 1.33, 0.75]
                for f in factors:
                    try:
                        m = image_watch.Matcher(pic["img"], picked_screen_h=base_h * f, ignore_background=True,
                                                screen_h=self.screen_h, work_height=RESULT_WORK_HEIGHT)
                        m.kind = pic["kind"]
                        m.picture_id = id(pic)
                        m.picture = pic
                        m.factor = f
                        m.fallback = bool(known) and f != known
                        step = pic.get("found_step")
                        if f == known and isinstance(step, int) and 0 <= step < len(m.templates):
                            m.last_best = step  # the exact size it matched at last time is tried first
                        matchers.append(m)
                    except Exception as exc:
                        if f == 1.0:
                            diag.error("A result picture couldn't be used", exc)
        return matchers

    def macro_steps(self):
        """The macro as steps (one recorded step when it was never edited into more)."""
        return self.actions if self.actions else workflow.from_events(self.events)

    def set_steps(self, actions):
        """Replace the macro with these steps (from the Edit window)."""
        actions = workflow.ensure_ids(actions)
        if workflow.is_simple(actions):
            self.actions = None
            self.events = actions[0]["events"]
        else:
            self.actions = actions
            self.events = workflow.all_events(actions)

    def _events_for_play(self, play_on):
        """The macro's steps with mouse positions fitted to this screen, or to the game window
        when Settings > Playback > Fit to says so (and the macro knows its window)."""
        steps, self.fit_note = self._fit_steps(self.macro_steps(), self.macro_screen, self.macro_program, play_on)
        return steps

    def _fit_steps(self, steps, made_for, program, play_on):
        """(a macro's steps fitted to this screen or the game window, a note about how)."""
        note = ""
        fit = None
        if self.settings.get("fit_to", "window") == "window":
            src = (program or {}).get("client")
            dst = self._game_client_rect(program)
            if src and dst and len(src) == 4 and src[3] > 0:
                if tuple(src) == tuple(dst):
                    fit = lambda evs: [dict(ev) for ev in evs]  # noqa: E731
                else:
                    note = "fitted to the game window"
                    fit = lambda evs: scale_events_rect(evs, src, dst)  # noqa: E731
            else:
                note = ("the game window wasn't found, so it's fitted to the screen" if src
                        else "this macro doesn't know its window, so it's fitted to the screen")
        if fit is None:
            fit = lambda evs: scale_events(evs, made_for, play_on)  # noqa: E731
        # (older recordings may hold a mouse button down the whole run: see drop_stray_clicks)
        return workflow.map_points(steps, lambda evs: fit(drop_stray_clicks(evs))), note

    # ------------------------------------------------------------ macros that play other macros

    @staticmethod
    def _macro_key(path):
        return os.path.normcase(os.path.abspath(path))

    def _find_macro_file(self, path):
        """Where a macro named in a step or a picture's action is now: its saved place, or (when the
        macros were moved or shared together) the folder of the open macro."""
        if path and os.path.isfile(path):
            return path
        if path and self.current_file:
            beside = os.path.join(os.path.dirname(self.current_file), os.path.basename(path))
            if os.path.isfile(beside):
                return beside
        return None

    def _read_macro_file(self, path):
        """Another macro's steps, read without opening it in the window:
        {"steps", "screen" (w, h) or None, "program", "name"}. Raises ValueError with the reason."""
        found = self._find_macro_file(path)
        name = os.path.splitext(os.path.basename(path or ""))[0] or "?"
        if not found:
            raise ValueError(f"the macro \"{name}\" isn't there any more ({path})")
        kept = getattr(self, "file_data", None)
        try:
            program = None
            try:
                events, screen = self._read_own_file(found)
                data = self.file_data
                program = data.get("program")
                raw = data.get("actions")
                if isinstance(raw, list) and raw and all(isinstance(a, dict) for a in raw):
                    steps = workflow.ensure_ids(expand_steps(raw))
                else:
                    steps = workflow.from_events(events)
            except (ValueError, RecursionError, KeyError, TypeError, OSError):
                try:
                    imported = importers.import_file(found)
                except Exception as exc:
                    raise ValueError(f"the macro \"{name}\" couldn't be read: {exc}") from None
                if not imported.events:
                    raise ValueError(f"the macro \"{name}\" has no actions") from None
                imported.events.sort(key=lambda ev: ev["t"])
                steps = workflow.from_events(imported.events)
                screen = {"width": imported.screen[0], "height": imported.screen[1]} if imported.screen else {}
                program = imported.program
        finally:
            self.file_data = kept
        try:
            made_for = (int(screen.get("width")), int(screen.get("height")))
            if made_for[0] <= 0 or made_for[1] <= 0:
                made_for = None
        except (TypeError, ValueError, AttributeError):
            made_for = None
        return {"steps": steps, "screen": made_for, "program": program if isinstance(program, dict) else None,
                "name": name}

    def _load_for_play(self, path, play_on, chain=()):
        """Another macro's steps, fitted and ready to play (the macros it plays itself included)."""
        key = self._macro_key(self._find_macro_file(path) or path or "")
        name = os.path.splitext(os.path.basename(path or ""))[0]
        if key in chain:
            raise ValueError(f"the macro \"{name}\" would end up playing itself (macros that play each other "
                             "in a circle)")
        if len(chain) >= MAX_MACRO_DEPTH:
            raise ValueError("too many macros inside each other")
        info = self._read_macro_file(path)
        steps, _note = self._fit_steps(info["steps"], info["screen"], info["program"], play_on)
        return self._resolve_macros(steps, play_on, chain + (key,))

    def _resolve_macros(self, steps, play_on, chain=()):
        """The steps with every "Play another macro" step turned into that macro's own steps
        (a "macro" group that playback runs a number of times)."""
        out = []
        for a in steps:
            if a.get("kind") == "play_macro":
                if a.get("off"):
                    continue
                if not a.get("file"):
                    raise ValueError("a \"Play another macro\" step has no macro chosen yet: choose one in Edit")
                out.append({"kind": "macro", "id": a.get("id"), "times": max(1, int(a.get("times", 1) or 1)),
                            "counts": bool(a.get("counts", True)),
                            "name": os.path.splitext(os.path.basename(a["file"]))[0],
                            "profile": a.get("profile"),
                            "on_fail": (self._load_for_play(a["on_fail"], play_on, chain)
                                        if a.get("on_fail") else None),
                            "on_fail_name": os.path.splitext(os.path.basename(a.get("on_fail") or ""))[0],
                            "actions": self._load_for_play(a["file"], play_on, chain)})
            elif isinstance(a.get("actions"), list):
                b = dict(a)
                b["actions"] = self._resolve_macros(a["actions"], play_on, chain)
                out.append(b)
            else:
                out.append(a)
        return out

    @staticmethod
    def _has_counted_macro(steps):
        return any(a.get("kind") == "macro" and a.get("counts", True) and not a.get("off")
                   for a, _l, _i, _p in workflow.walk(steps))

    def _prepare_watch_actions(self, watch, play_on):
        """Read the macros that pictures play or switch to, and the pictures that confirm a rejoin."""
        for n, pic in enumerate(self._active_watch_pictures(), start=1):
            action = pic.get("action", "restart")
            if action in WATCH_NEED_MACRO:
                if pic.get("macro"):
                    if pic["macro"] not in watch["macros"]:
                        steps = self._load_for_play(pic["macro"], play_on)
                        watch["macros"][pic["macro"]] = steps
                        self.wait_matchers.update(self._make_wait_matchers(steps))
                elif action != "recover":
                    raise ValueError(f"{watch_name(pic, n)} has no macro chosen yet (Picture watch)")
            if action == "recover" and pic.get("confirm_file"):
                path = os.path.join(watch_dir(), pic["confirm_file"])
                if os.path.isfile(path):
                    watch["confirm"][id(pic)] = image_watch.Matcher(
                        image_watch.load_image(path), picked_screen_h=pic.get("confirm_screen_h"),
                        ignore_background=True, screen_h=self.screen_h)

    def _game_client_rect(self, program=None):
        """Where the inside of the game's window is now: the macro's program if it's open, else the
        window in front (if it isn't this app)."""
        exe = (program or self.macro_program or {}).get("exe")
        wins = window_tools.windows_of(exe) if exe else []
        if not wins:
            fg = window_tools.foreground()
            if fg and window_tools.pid_of(fg) != os.getpid():
                wins = [fg]
        return window_tools.client_rect(wins[0]) if wins else None

    def _make_wait_matchers(self, program):
        """The pictures of "Wait for a picture" steps and of If / Retry conditions, ready to look for
        (by the id of the dict that holds the picture)."""
        found = {}
        holders = []
        for a, _lst, _i, _p in workflow.walk(program):
            if a.get("off"):
                continue
            kind = a.get("kind")
            if kind == "wait_picture":
                holders.append(a)
            elif kind in ("if", "retry"):
                holders.append(a.get("condition", {}))
            elif kind == "recorded":
                holders.extend(ev for ev in a.get("events", []) if ev.get("type") == "wait_picture")
        for n, h in enumerate(holders, start=1):
            if not h.get("png"):
                raise ValueError(f"a picture step or condition ({n}) has no picture yet: choose one in Edit")
            if image_watch is None:
                raise ValueError("this copy was built without picture support")
            import base64

            import numpy as np

            data = np.frombuffer(base64.b64decode(h["png"]), np.uint8)
            img = image_watch.cv2.imdecode(data, image_watch.cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError(f"picture {n} is broken")
            found[id(h)] = image_watch.Matcher(img, picked_screen_h=h.get("screen_h"), ignore_background=True,
                                               screen_h=self.screen_h)
        return found

    def stop_playback(self):
        self.stop_play.set()

    def _set_countdown(self, seconds):
        def update():
            self.countdown_left = seconds
            self._refresh()
        self._call_ui(update)

    def _picture_seen(self):
        """The watched-for picture showed up (the dark window plays a sound here)."""

    def _set_note(self, text):
        def update():
            self.play_note = text
            self._refresh()
        self._call_ui(update)

    def _free_shift_lock(self):
        """If the game hides the pointer (Roblox's Shift Lock is on), press Shift once to get the
        pointer back, so a click can land on a button. Returns True if the pointer is visible now."""
        if window_tools.cursor_hidden() is not True:
            return True
        try:
            self.kb_ctrl.press(keyboard.Key.shift_l)
            time.sleep(0.05)
            self.kb_ctrl.release(keyboard.Key.shift_l)
        except Exception:
            return False
        time.sleep(0.3)
        ok = window_tools.cursor_hidden() is not True
        diag.info("Pressed Shift to free the mouse from Shift Lock: " + ("worked" if ok else "pointer still hidden"))
        return ok

    def _click_at(self, x, y):
        """Left-click a spot like a person would: move there, nudge so the game sees the mouse, click."""
        move_to(self.mouse_ctrl, x, y)
        time.sleep(0.05)
        move_relative(self.mouse_ctrl, 1, 0)
        time.sleep(0.05)
        move_relative(self.mouse_ctrl, -1, 0)
        time.sleep(0.1)
        self.mouse_ctrl.press(mouse.Button.left)
        time.sleep(0.06)
        self.mouse_ctrl.release(mouse.Button.left)

    def _release_held(self, bg, held_keys, held_buttons):
        """Let go of every key and mouse button the macro is holding down."""
        if bg is not None:
            try:
                bg.release_all(held_keys)
            except Exception:
                pass
            held_keys.clear()
        for k in list(held_keys):
            try:
                self.kb_ctrl.release(k)
            except Exception:
                pass
        for b in list(held_buttons):
            try:
                self.mouse_ctrl.release(b)
            except Exception:
                pass
        held_keys.clear()
        held_buttons.clear()

    def _watch_worker(self, watch, seen, done):
        """Takes screenshots and sets `seen` when one of the pictures shows up (watch["seen_pic"] says
        which, watch["seen_at"] where its middle is).

        A picture only fires again after it has gone away, so a results screen that stays up for a
        while doesn't restart the macro over and over. If it's already showing when playback
        starts, it waits for it to go away first. Each picture can also have a cooldown (seconds
        before it may fire again) and "only when picture B also shows"."""
        matchers, need = watch["matchers"], watch["need"]
        window_tools.set_thread_priority(-1)  # never in the way of playback's timing
        states = [{"armed": None, "fired": 0.0} for _ in matchers]
        checks = 0
        try:
            with image_watch.mss.mss() as sct:
                origin = image_watch.screen_origin(sct)
                while not done.is_set():
                    started = time.perf_counter()
                    # Every check (about once a second) first looks only around the spot where each
                    # picture was found before: a small part of the screen, so it's very light. A
                    # picture's whole area is searched on every 5th check (every size on every 30th).
                    # A picture never found yet: every check for the first 10, then every 3rd check,
                    # taking turns with the other such pictures (so a Disconnected box that never
                    # shows doesn't make every check a heavy one all night).
                    looks = [self._watch_look_area(m, i, checks) for i, m in enumerate(matchers)]
                    all_sizes = checks % 30 == 0
                    checks += 1
                    visible = [False] * len(matchers)
                    middles = [None] * len(matchers)
                    try:
                        # only take the parts of the screen that are looked at
                        areas = [a for a in looks if a is not None] + \
                                [m.near_last_area() for m in matchers if m.last_rect is not None]
                        region = None
                        if areas:
                            region = (min(a[0] for a in areas), min(a[1] for a in areas),
                                      max(a[2] for a in areas), max(a[3] for a in areas))
                            if region[0] <= 0 and region[1] <= 0 and region[2] >= self.screen_w and \
                                    region[3] >= self.screen_h:
                                region = None  # (the whole screen)
                        screen = self._hide_own_window(image_watch.grab_screen(sct, region), origin)
                        for i, m in enumerate(matchers):
                            score, rect = m.find_near_last(screen, good_enough=need)
                            if score < need and looks[i] is not None:
                                score, rect = m.find(screen, good_enough=need, quick=not all_sizes, area=looks[i])
                            if score >= need and self._watch_match_ok(m.picture_entry, score, rect, need):
                                visible[i] = True
                                m.picture_entry["seen_rect"] = m.last_rect
                                ox, oy = origin
                                x, y, w, h = rect
                                middles[i] = (ox + x + w // 2, oy + y + h // 2)
                    except Exception:
                        pass
                    for i, m in enumerate(matchers):
                        st, pic = states[i], m.picture_entry
                        if st["armed"] is None:
                            # a picture already on screen when playing starts waits until it has gone
                            # (a results screen left up), except a disconnect box: that one is dealt
                            # with at once, or a macro started while disconnected would never rejoin
                            st["armed"] = not visible[i] or pic.get("action") == "recover"
                        if visible[i] and st["armed"]:
                            also = pic.get("also")
                            if also and not any(visible[j] for j, other in enumerate(matchers)
                                                if other.picture_entry.get("file") == also):
                                continue  # its other picture isn't showing (yet)
                            if started - st["fired"] < float(pic.get("cooldown") or 0):
                                continue
                            if seen.is_set():
                                continue  # another picture is being dealt with: this one waits its turn
                            st["armed"] = False
                            st["fired"] = started
                            watch["seen_at"] = middles[i]
                            watch["seen_pic"] = pic
                            seen.set()
                        elif not visible[i] and looks[i] is not None:
                            st["armed"] = True  # gone (its whole area was checked): it may count again
                    # check about once a second; when a check is slow, rest at least as long as it
                    # took, so watching never uses more than about half of one CPU core
                    took = time.perf_counter() - started
                    done.wait(max(0.3, 1.0 - took, took))
        except Exception:
            pass  # screenshots don't work here: playback just goes on without watching

    def _health_worker(self, done):
        """While playing: every HEALTH_EVERY seconds, one line in the log with how heavy the app is
        (memory, CPU, threads, Windows handles), so a report shows whether something slowly grows
        during a long run."""
        began_cpu, began = time.process_time(), time.perf_counter()
        last_cpu, last = began_cpu, began
        while not done.wait(HEALTH_EVERY):
            now_cpu, now = time.process_time(), time.perf_counter()
            cpu = 100.0 * (now_cpu - last_cpu) / max(1e-6, now - last)  # (100 % = one whole core)
            last_cpu, last = now_cpu, now
            h = window_tools.process_health()
            parts = [f"playing {int((now - began) // 60)} min", f"CPU {cpu:.0f}% of one core"]
            if "memory_mb" in h:
                parts.append(f"memory {h['memory_mb']} MB")
            parts.append(f"threads {threading.active_count()}")
            if "gdi" in h:
                parts.append(f"GDI {h['gdi']}, USER {h['user']}")
            diag.info("Health: " + ", ".join(parts))

    def _watch_look_area(self, m, i, checks):
        """Where Picture watch searches for picture i on this check (besides around where it was
        last found): (x0, y0, x1, y1) on the screen, or None for not this time."""
        if m.last_rect is not None:
            due = checks % 5 == 0
        else:
            due = checks < 10 or (checks + i) % 3 == 0
        if not due:
            return None
        if m.picture_entry.get("action") == "recover":
            # Roblox's Disconnected box is always in the middle of the screen, and a match anywhere
            # else doesn't count (see _watch_match_ok), so only the middle is searched
            t = m.templates[m.last_best][0]
            pw, ph = t.shape[1] / m.work, t.shape[0] / m.work  # its size on the screen
            mx, my = self.screen_w * 0.15 + pw * 0.6 + 20, self.screen_h * 0.2 + ph * 0.6 + 20
            cx, cy = self.screen_w / 2, self.screen_h / 2
            return int(cx - mx), int(cy - my), int(cx + mx) + 1, int(cy + my) + 1
        return 0, 0, self.screen_w, self.screen_h

    def _watch_match_ok(self, pic, score, rect, need):
        """Extra care for a disconnect picture: a big box matched only on its bright parts also
        scores about 0.8 on ordinary game screens (bright sky, white text). Roblox's Disconnected
        box is always in the middle of the screen, so it must be found there, and match well."""
        if pic.get("action") != "recover" or not rect:
            return True
        if score < max(need, RECOVER_MATCH):
            return False
        x, y, w, h = rect
        cx, cy = x + w / 2, y + h / 2  # (on the main screen, which is what's grabbed)
        return abs(cx - self.screen_w / 2) <= self.screen_w * 0.15 and abs(cy - self.screen_h / 2) <= self.screen_h * 0.2

    def _play_worker(self, events, repeats, loop, speed, bg=None, ready=0, watch=None):
        held_keys, held_buttons = set(), set()
        self.held_lists = (held_keys, held_buttons)
        window_tools.set_thread_priority(1)  # playback goes before the screen checks
        window_tools.keep_awake(True)  # no sleep or screen-off during long waits (let go of below)
        seen = threading.Event()  # a watched-for picture showed up
        watch_done = threading.Event()
        # count: finished runs; restarts: when a picture did its action (for the runaway limit);
        # starts_over: when a "Start over" step ran (the same kind of limit)
        state = {"count": 0, "restarts": [], "starts_over": []}
        self.play_state = state
        try:
            # "get ready" countdown; Stop cancels it
            for left in range(ready, 0, -1):
                self._set_countdown(left)
                if self.stop_play.wait(1.0):
                    return
            self._set_countdown(0)
            self.play_game_exe = self._game_exe_now()
            closed = self._closed_watcher(bg)
            away = self._away_watcher(bg, closed) or closed
            if self.result_matchers:
                self.result_state = {}
                threading.Thread(target=self._result_worker, args=(self.result_matchers, watch_done),
                                 daemon=True).start()
            if watch is not None:
                threading.Thread(target=self._watch_worker, args=(watch, seen, watch_done),
                                 daemon=True).start()
            ctx = {"speed": speed, "bg": bg, "held": (held_keys, held_buttons), "seen": seen, "away": away,
                   "watch": watch, "state": state, "vary": self.play_vary}
            threading.Thread(target=self._health_worker, args=(watch_done,), daemon=True,
                             name="health").start()
            if self.auto_stop and self.auto_stop.get("deadline"):
                threading.Thread(target=self._auto_stop_timer, args=(self.auto_stop, watch_done),
                                 daemon=True).start()
            self.play_ctx = ctx
            self.playing_name = None  # set when a picture switched to another macro
            while True:
                times = None if loop else max(1, repeats - state["count"])
                result = self._run_passes(events, ctx, times, top=True)
                if isinstance(result, tuple) and result[0] == "switch":
                    events, self.playing_name = result[1], result[2]
                    diag.info(f"Picture watch switched to the macro \"{result[2]}\"")
                    continue
                break
        except Exception as exc:
            self.stop_reason = diag.error("Playback stopped because of an error", exc)
        finally:
            watch_done.set()
            window_tools.keep_awake(False)
            # never leave a key or mouse button stuck down
            self._release_held(bg, held_keys, held_buttons)
            self.runs_done = state["count"]
            self._call_ui(self._playback_done)

    def _run_passes(self, steps, ctx, times, top=False, counts=True):
        """Play these steps `times` times (None = until stopped), doing what picture watch asks for
        in between. Used for the macro itself (top) and for every "Play another macro" step.
        Returns "ok", "stop", "restart" (a Start over step, passed up to the macro itself) or
        ("switch", steps, name) when a picture switched to another macro."""
        watch, seen, state = ctx["watch"], ctx["seen"], ctx["state"]
        held_keys, held_buttons = ctx["held"]
        bg = ctx["bg"]
        # a macro that plays other macros doesn't count as a run itself: its parts do
        counts = counts and not self._has_counted_macro(steps)
        done = 0
        while not self.stop_play.is_set() and (times is None or done < times):
            if top and (times is None or times > 1 or watch):
                total = "" if times is None else f" of {state['count'] + times - done}"
                watching = ", watching for the picture" if watch else ""
                name = f" \"{self.playing_name}\"" if getattr(self, "playing_name", None) else ""
                self._set_note(f"Playing{name} run {state['count'] + 1}{total}{watching}...")
            if counts:
                self.run_began = (time.perf_counter(), self._play_clock())
            result = self._run_steps(steps, ctx)
            if result == "stop" or isinstance(result, tuple):
                return result
            if result == "gameback":  # the game had closed and is open again: this run starts over
                self._release_held(bg, held_keys, held_buttons)
                seen.clear()
                continue
            if result == "restart":
                if not top:
                    return result
                now = time.perf_counter()
                state["starts_over"][:] = [t for t in state["starts_over"] if now - t < 60] + [now]
                if len(state["starts_over"]) > 10:
                    self.stop_reason = ("Stopped: a \"Start over\" step ran more than 10 times in 60 s. "
                                        "Something is probably stuck.")
                    diag.error(self.stop_reason)
                    return "stop"
                self._release_held(bg, held_keys, held_buttons)
                continue  # from step 1 again (the same run)
            picture = False
            if watch is not None:
                self._release_held(bg, held_keys, held_buttons)
                last_run = top and times is not None and done + 1 >= times
                if result == "ok" and self._picture_now(ctx) != "picture" and watch["end_wait"] > 0 \
                        and not last_run:
                    # the macro ended first: give the picture some time to show up
                    deadline = time.perf_counter() + watch["end_wait"]
                    while True:
                        left = deadline - time.perf_counter()
                        if left <= 0 or self._picture_now(ctx) == "picture":
                            break
                        self._set_note(f"Macro finished, waiting for the picture ({int(left) + 1} s)...")
                        if self.stop_play.wait(min(0.25, left)):
                            return "stop"
                if self.stop_play.is_set():
                    return "stop"
                picture = seen.is_set()
            pic = (watch.get("seen_pic") or {}) if picture else {}
            action = pic.get("action", "restart")
            if not picture or watch_counts(pic):
                done += 1
                if counts:
                    state["count"] += 1
                    self._finish_run(state["count"], "picture" if picture else "end")
                    if self._auto_stop_due(state):
                        return "stop"
                    if ctx.get("on_fail") and self.session.runs and self.session.runs[-1][0] == stats.LOSS:
                        # this part of the chain was lost: its "if it fails" macro plays before going on
                        if picture:
                            self._picture_click(pic, watch)
                            seen.clear()
                        self._set_note(f"That run failed: playing \"{ctx['on_fail'][1]}\"...")
                        sub = dict(ctx, seen=threading.Event(), watch=None, on_fail=None)
                        if self._run_passes(ctx["on_fail"][0], sub, 1, counts=False) == "stop":
                            return "stop"
                        self._release_held(bg, held_keys, held_buttons)
                        continue
            if not picture:
                continue
            if top and times is not None and done >= times and action == "restart":
                break  # that was the last run: nothing to start over
            seen.clear()
            if self._picture_limit(ctx):
                return "stop"
            self._call_ui(self._picture_seen)
            self._picture_click(pic, watch)
            if action == "stop":
                self.stop_reason = f"Stopped: {watch_name(pic)} showed on screen (Picture watch says to stop then)."
                diag.info(self.stop_reason)
                return "stop"
            if action in ("play", "recover"):
                if self._play_picture_macro(pic, ctx, recover=action == "recover") == "stop":
                    return "stop"
            elif action == "switch":
                new_steps = watch["macros"].get(pic.get("macro"))
                if new_steps:
                    return ("switch", new_steps, os.path.splitext(os.path.basename(pic["macro"]))[0])
            for left in range(int(watch["wait"]), 0, -1):
                self._set_note(f"Picture seen! Starting the macro over in {left}...")
                if self.stop_play.wait(1.0):
                    return "stop"
            seen.clear()  # ignore it if it flickered during the wait
        return "stop" if self.stop_play.is_set() else "ok"

    def _picture_limit(self, ctx):
        """The runaway guard: True (and playback stops) when pictures did their actions more often
        than Picture watch > Safety limit allows. A stuck screen mustn't go on forever."""
        watch, restarts = ctx["watch"], ctx["state"]["restarts"]
        now = time.perf_counter()
        limit = watch.get("limit_count", 0)
        within = watch.get("limit_seconds", 60)
        restarts[:] = [t for t in restarts if now - t <= within] + [now]
        if limit and len(restarts) > limit:
            self.stop_reason = (f"Stopped: the picture started the macro over {len(restarts)} times "
                                f"in {within} s. Something is probably stuck (see Picture watch "
                                "> Safety limit).")
            diag.error(self.stop_reason)
            return True
        return False

    def _picture_click(self, pic, watch):
        """Click the picture that showed, when it (or "click on it" for all pictures) says so."""
        click = pic.get("click")
        if (watch["click"] if click is None else click) and watch.get("seen_at"):
            if watch.get("shift_lock"):
                self._set_note("Picture seen! Freeing the mouse from Shift Lock...")
                self._free_shift_lock()
            self._set_note("Picture seen! Clicking it...")
            self._click_at(*watch["seen_at"])

    def _picture_now(self, ctx):
        """Called by playback when a watched picture has shown. Pictures whose action lets the macro
        go on (press a key, wait, skip the step, nothing) are dealt with right here: returns None
        (go on) or "skip" (the step that's playing ends). For every other action it returns
        "picture": the run is over and _run_passes does the rest."""
        seen, watch = ctx["seen"], ctx.get("watch")
        if not seen.is_set():
            return None
        pic = (watch.get("seen_pic") or {}) if watch else {}
        action = pic.get("action", "restart")
        if action not in WATCH_INLINE:
            return "picture"
        seen.clear()
        if action == "nothing":
            return None
        if self._picture_limit(ctx):
            self.stop_play.set()
            return None
        self._call_ui(self._picture_seen)
        began = time.perf_counter()
        try:
            self._picture_click(pic, watch)
            if action == "key" and isinstance(pic.get("key"), dict):
                held_keys, held_buttons = ctx["held"]
                for pressed in (True, False):
                    ev = {"type": "key", "key": pic["key"], "pressed": pressed}
                    if ctx["bg"] is not None:
                        self._replay_event_bg(ctx["bg"], ev, held_keys)
                    else:
                        self._replay_event(ev, held_keys, held_buttons)
                    time.sleep(0.05)
            elif action == "wait":
                end = time.perf_counter() + max(0.0, float(pic.get("seconds") or 0))
                while not self.stop_play.is_set():
                    left = end - time.perf_counter()
                    if left <= 0:
                        break
                    self._set_note(f"Picture seen! Waiting {int(left) + 1} s...")
                    self.stop_play.wait(min(0.25, left))
            self._set_note("Playing...")
        finally:
            # the macro's clock didn't run meanwhile, so nothing is rushed afterwards
            self._clock_back(time.perf_counter() - began)
        return "skip" if action == "skip" else None

    def _play_picture_macro(self, pic, ctx, recover=False):
        """A picture's own macro: played once, then the main macro starts over. With recover (a
        disconnect screen): the rejoin macro is played until the screen is gone and, if one was
        chosen, the "I'm back" picture shows; each failed try waits longer. Returns "ok" or "stop"."""
        watch = ctx["watch"]
        steps = watch["macros"].get(pic.get("macro"))
        name = os.path.splitext(os.path.basename(pic.get("macro") or ""))[0]
        sub = dict(ctx, seen=threading.Event(), watch=None)  # (picture watch rests while it plays)

        def play_it():
            if not steps:
                return "ok"
            result = self._run_passes(steps, sub, 1, counts=False)
            self._release_held(ctx["bg"], *ctx["held"])
            return "stop" if result == "stop" or self.stop_play.is_set() else "ok"

        if not recover:
            self._set_note(f"Picture seen! Playing \"{name}\"...")
            return play_it()
        tries = max(1, int(pic.get("tries") or 3))
        self._recovery_event("lost", f"{watch_name(pic)} showed: trying to get back into the game.")
        own = next((m for m in watch["matchers"] if getattr(m, "picture_entry", None) is pic), None)
        confirm = watch["confirm"].get(id(pic))
        for n in range(tries):
            if n:  # wait longer before each new try: 15 s, 30 s, 60 s... (5 minutes at most)
                pause = min(300, 15 * 2 ** (n - 1))
                for left in range(pause, 0, -1):
                    self._set_note(f"Still not back in the game. Try {n + 1} of {tries} in {left} s...")
                    if self.stop_play.wait(1.0):
                        return "stop"
            self._set_note(f"Getting back into the game (try {n + 1} of {tries})"
                           + (f": playing \"{name}\"..." if steps else "..."))
            if play_it() == "stop":
                return "stop"
            self._set_note("Checking whether the game is back...")
            back = True
            if own is not None:  # the disconnect screen must be gone
                back = not self._shows(own, watch["need"], wait=0)
            if back and confirm is not None:
                back = self._shows(confirm, watch["need"],
                                   wait=max(1.0, float(pic.get("confirm_seconds") or 60)))
            if self.stop_play.is_set():
                return "stop"
            if back:
                self.session.reconnects += 1
                run_history.note("reconnects")
                self._recovery_event("back", f"Back in the game after {n + 1} "
                                     f"{'try' if n == 0 else 'tries'}. The macro goes on.")
                return "ok"
        self.session.failed_reconnects += 1
        self.stop_reason = (f"Stopped: couldn't get back into the game after {tries} "
                            f"{'try' if tries == 1 else 'tries'} ({watch_name(pic)} in Picture watch).")
        diag.error(self.stop_reason)
        self._recovery_event("failed", self.stop_reason)
        return "stop"

    def _shows(self, matcher, need, wait=0.0):
        """Whether a picture is on screen now; looks again for up to `wait` seconds until it is."""
        deadline = time.perf_counter() + wait
        while True:
            try:
                screen = self._hide_own_window(image_watch.grab_screen(), image_watch.screen_origin())
                score, _ = matcher.find(screen, good_enough=need)
            except Exception as exc:
                diag.error("Couldn't check a picture", exc)
                score = 0.0
            if score >= need:
                return True
            if time.perf_counter() >= deadline or self.stop_play.is_set():
                return False
            self.stop_play.wait(0.5)

    def _recovery_event(self, kind, text):
        """A disconnect screen showed ("lost"), the game is back ("back") or it couldn't be got back
        ("failed"). The dark window tells Discord here."""
        diag.info(f"Recovery ({kind}): {text}")

    def _macro_name(self):
        return os.path.splitext(os.path.basename(self.current_file))[0] if self.current_file else "Macro"

    def _finish_run(self, count, how):
        """A run is over: work out whether it was won, lost or unknown, add it to the session's
        results, then tell _run_finished."""
        status = stats.UNKNOWN
        if self.result_matchers:
            began_wall, began_clock = getattr(self, "run_began", (time.perf_counter(), self._play_clock()))
            status = self._run_result(began_wall)
            if status != stats.UNKNOWN:
                # the result showing now belongs to this run, even if the watcher only notices it
                # after the next run has started
                self.result_consumed = (status, time.perf_counter())
            seconds = self._play_clock() - began_clock
        else:
            seconds = self._play_clock() - getattr(self, "run_began", (0, self._play_clock()))[1]
        fragments = self._count_drops() if self.settings.get("drops_enabled", True) else 0
        self.session.add(status, seconds, fragments)
        name = getattr(self, "chain_step", None) or getattr(self, "playing_name", None) or self._macro_name()
        self.last_run = run_history.add(name, status, seconds, fragments)
        # saved after every run (on a helper thread, so the next run isn't held up): a crash or a power
        # cut loses no runs from the stats
        threading.Thread(target=run_history.save, daemon=True, name="save-runs").start()
        diag.info(f"Run {count} over ({how}): {status}, {seconds:.0f} s, {fragments} fragment(s)")
        self._run_finished(count, how)

    def _count_drops(self):
        """Divine fragments on the results screen now (counted by their pink-to-blue frame)."""
        if image_watch is None:
            return 0
        try:
            import drops

            # the drops always show in the OBTAINED row, under the result title: when the title was
            # found, only that part of the screen is taken and looked at (quicker, and nothing else
            # on screen can count)
            title = next((m.last_rect for m in list(self.result_matchers) if m.last_rect is not None), None)
            if title is not None:
                x, y, w, h = title
                # (the panel is about 1.4 times as wide as its title; a full OBTAINED row reaches its
                # sides, so a little more than the panel is taken)
                x0, x1 = max(0, int(x - 0.45 * w)), min(self.screen_w, int(x + 1.45 * w))
                y0, y1 = max(0, int(y + h)), min(self.screen_h, int(y + 14 * h))
                if x1 - x0 < 1 or y1 - y0 < 1:
                    return 0
                screen, origin = image_watch.grab_part(x0, y0, x1, y1)
                screen = self._hide_own_window(screen, origin)
            else:
                screen = self._hide_own_window(image_watch.grab_screen(), image_watch.screen_origin())
            count, _rects = drops.count_frames(screen, full_height=self.screen_h)
            if count:
                diag.info(f"Divine fragments on the results screen: {count}")
            return count
        except Exception as exc:
            diag.error("Couldn't count the drops", exc)
            return 0

    def _run_result(self, run_began):
        """"win", "loss" or "unknown" for the run that started at run_began (perf_counter time)."""
        st = self.result_state
        seen = [(t, kind) for kind, s in st.items() for t in s.get("appeared", []) if t >= run_began]
        if seen:
            return max(seen)[1]
        # not seen by the watcher yet: look at the screen once more, now
        try:
            need = self.settings.get("results_match", RESULTS_MATCH_DEFAULT) / 100.0
            # only around the spots where result pictures were seen before (about 0.01 s, so Retry
            # isn't held up); the whole screen only while no result picture was ever found
            whole = not any(self._kinds_found().values())
            region = None
            if not whole:
                areas = [m.near_last_area() for m in list(self.result_matchers) if m.last_rect is not None]
                region = (min(a[0] for a in areas), min(a[1] for a in areas),
                          max(a[2] for a in areas), max(a[3] for a in areas))
            screen = self._hide_own_window(image_watch.grab_screen(None, region), image_watch.screen_origin())
            best = self._result_scores(screen, need, whole=whole)
            if region is not None:
                self._unfound_kinds_in(screen, region, need, best)
            kind = self._best_result(best, need)
            since = st.get(kind, {}).get("since") if kind else None
            # (a picture already showing before this run started belongs to the run before)
            if kind and (since is None or since >= run_began):
                return kind
        except Exception as exc:
            diag.error("Couldn't check the result picture", exc)
        return stats.UNKNOWN

    def _unfound_kinds_in(self, screen, region, need, best):
        """A kind never found yet (like MISSION FAILED) usually shows where the other one did: look
        for it in that same small part of the screen (every size: a small part, so it's quick).
        Adds its score to best (kind -> score)."""
        x0, y0 = max(0, region[0]), max(0, region[1])
        x1, y1 = max(x0, region[2]), max(y0, region[3])
        found = self._kinds_found()
        with self._result_lock:
            for m in list(self.result_matchers):
                if not found.get(m.kind) and x1 - x0 >= 8 and y1 - y0 >= 8:
                    score, _ = m.find(screen, good_enough=need, remember=False, area=(x0, y0, x1, y1))
                    best[m.kind] = max(best.get(m.kind, 0.0), score)
        return best

    def _kinds_found(self):
        """kind -> whether one of its pictures was found on screen yet (this playback)."""
        found = {}
        for m in list(self.result_matchers):
            found[m.kind] = found.get(m.kind, False) or m.last_rect is not None
        return found

    _result_lock = threading.Lock()  # the watcher and the end-of-run check use the same pictures

    def _result_scores(self, screen, need, whole, every_size=True):
        with self._result_lock:
            return self._result_scores_now(screen, need, whole, every_size)

    def _result_scores_now(self, screen, need, whole, every_size=True):
        """every_size: a picture never found yet is looked for at all its sizes at once (the check at
        the end of a run). Otherwise (while playing) each look tries 3 other sizes, so all of them
        are covered every 5 looks without one look taking long."""
        """The best score of each kind ("win" / "loss") on a screenshot. Once a picture was found at
        one of its sizes, its other sizes aren't looked for any more (less work)."""
        scores = {}
        matchers = list(self.result_matchers)
        if whole:
            self.result_whole_checks = getattr(self, "result_whole_checks", 0) + 1
        for m in matchers:
            if m.last_rect is None and any(o is not m and o.picture_id == m.picture_id and o.last_rect is not None
                                           for o in matchers):
                continue
            if getattr(m, "fallback", False) and m.last_rect is None and \
                    getattr(self, "result_whole_checks", 0) % 6 != 5:
                continue  # the remembered size goes first; other sizes only every 6th look
            score, _ = m.find_near_last(screen, good_enough=need)
            if score < need and whole:
                # first the size it was found at before (and the ones next to it); while it was never
                # found yet, also every other size step: a title can show a few % bigger or smaller
                # than the picture, and then only matches at that exact size
                score, _ = m.find(screen, good_enough=need, quick=True)
                if score < need and m.last_rect is None:
                    main_size = getattr(m, "factor", 1.0) == (getattr(m, "picture", {}) or {}).get("found_factor", 1.0)
                    if every_size and main_size:  # (the other two sizes are covered by the watcher's turns)
                        score, _ = m.find(screen, good_enough=need)
                    elif not every_size:
                        turn = getattr(m, "size_turn", 0)
                        m.size_turn = turn + 1
                        steps = list(range(1, len(m.templates), 3))  # 1, 4, 7, ...: with their neighbours, all
                        remembered = m.last_best
                        m.last_best = steps[turn % len(steps)]
                        score, _ = m.find(screen, good_enough=need, quick=True)
                        if score < need:
                            m.last_best = remembered
            if score >= need and hasattr(m, "picture"):
                # remember this size for next time (saved with the pictures when playback ends)
                m.picture["found_factor"] = m.factor
                m.picture["found_step"] = m.last_best
                m.picture["found_screen"] = [self.screen_w, self.screen_h]
            scores[m.kind] = max(scores.get(m.kind, 0.0), score)
        if any(v >= need for v in scores.values()):
            # one result shows: before saying which, look properly (every size) for the kinds never
            # found yet, as a "failed" title can look a bit like a "completed" one
            for m in matchers:
                if m.last_rect is None and not getattr(m, "fallback", False) and \
                        not any(o.kind == m.kind and o.last_rect is not None for o in matchers):
                    score, _ = m.find(screen, good_enough=need, remember=False)  # (no lock-in on a look-alike)
                    scores[m.kind] = max(scores.get(m.kind, 0.0), score)
        return scores

    @staticmethod
    def _best_result(scores, need):
        kind = max(scores, key=scores.get) if scores else None
        return kind if kind and scores[kind] >= need else None

    def _result_worker(self, matchers, done):
        """While playing: notice when a "mission completed" or "mission failed" picture appears
        (about every 1.5 s). Each time one appears counts once, for the run that's going on."""
        need = self.settings.get("results_match", RESULTS_MATCH_DEFAULT) / 100.0
        window_tools.set_thread_priority(-1)  # never in the way of playback's timing
        checks = 0
        try:
            with image_watch.mss.mss() as sct:
                origin = image_watch.screen_origin(sct)
                while not done.is_set():
                    started = time.perf_counter()
                    # The whole screen is searched on every 4th look, and on every look while no
                    # result was ever found. Once one kind was found (MISSION COMPLETED), a kind not
                    # found yet (MISSION FAILED, if you rarely lose) is looked for where the other one
                    # showed, and the whole screen only every 8th look (it used to be every look).
                    kinds = self._kinds_found()
                    if not any(kinds.values()):
                        whole = True
                    elif all(kinds.values()):
                        whole = checks % 4 == 0
                    else:
                        whole = checks % 8 == 0
                    checks += 1
                    visible = {}
                    try:
                        region = None
                        if not whole:
                            # take only the parts of the screen around where results showed (a small
                            # box instead of the whole screen)
                            areas = [m.near_last_area() for m in list(matchers) if m.last_rect is not None]
                            if areas:
                                region = (min(a[0] for a in areas), min(a[1] for a in areas),
                                          max(a[2] for a in areas), max(a[3] for a in areas))
                        screen = self._hide_own_window(image_watch.grab_screen(sct, region), origin)
                        scores = self._result_scores(screen, need, whole, every_size=False)
                        if region is not None and not all(kinds.values()):
                            self._unfound_kinds_in(screen, region, need, scores)
                        best = self._best_result(scores, need)
                        # only the best-matching kind counts (a "failed" title can look a bit like a
                        # "completed" one)
                        visible = {kind: kind == best for kind in scores}
                    except Exception:
                        visible = {}
                    now = time.perf_counter()
                    for kind, on in visible.items():
                        s = self.result_state.setdefault(kind, {"since": None, "appeared": [], "first": True})
                        if on and s["since"] is None:
                            s["since"] = now
                            consumed = getattr(self, "result_consumed", None)
                            if consumed and consumed[0] == kind and now - consumed[1] < 15:
                                pass  # the run that just ended already counted this one
                            elif not s["first"]:  # (already showing when playing started: not this run's)
                                s["appeared"].append(now)
                        elif not on and whole:
                            s["since"] = None
                        s["first"] = False
                    took = time.perf_counter() - started
                    done.wait(max(0.5, 1.5 - took, took))
        except Exception as exc:
            diag.error("Result pictures: watching the screen failed", exc)

    # ------------------------------------------------------------ running the steps

    def _run_steps(self, steps, ctx):
        """Play a list of steps. Returns "ok", "picture" (picture watch saw its picture: this run is
        over), "stop" (stop the macro) or "restart" (start the macro again from step 1)."""
        for a in steps:
            if self.stop_play.is_set():
                return "stop"
            if ctx["seen"].is_set() and self._picture_now(ctx) == "picture":
                return "picture"
            if a.get("off"):
                continue
            result = self._run_step(a, ctx)
            if result == "skip":  # a picture's "Skip to the next step"
                continue
            if result != "ok":
                return result
        return "ok"

    def _run_step(self, a, ctx):
        kind = a.get("kind")
        held_keys, held_buttons = ctx["held"]
        bg = ctx["bg"]
        if kind == "recorded":
            return self._play_events(a.get("events", []), ctx)
        if kind == "wait":
            seconds = float(a.get("seconds", 0)) / ctx["speed"]
            vary = ctx.get("vary")
            if vary and vary["ms"]:
                seconds = max(0.0, seconds + random.uniform(-vary["ms"], vary["ms"]) / 1000.0)
            return self._pause(seconds, ctx)
        if kind == "note":
            return "ok"
        if kind == "macro":  # a "Play another macro" step: that macro's steps, a number of times
            self.chain_step = a.get("name")
            part = (self.settings.get("profiles") or {}).get(a.get("profile")) if a.get("profile") else None
            if isinstance(part, dict):
                vary = part.get("vary") if isinstance(part.get("vary"), dict) else {}
                ctx = dict(ctx, speed=parse_speed(part.get("speed", 1)) or ctx["speed"],
                           vary=({"ms": int_setting(vary, "ms", 20, 0, 500), "px": int_setting(vary, "px", 3, 0, 50)}
                                 if vary.get("on") else None))
            if a.get("on_fail"):
                ctx = dict(ctx, on_fail=(a["on_fail"], a.get("on_fail_name")))
            try:
                return self._run_passes(a.get("actions", []), ctx, max(1, int(a.get("times", 1))),
                                        counts=bool(a.get("counts", True)))
            finally:
                self.chain_step = None
        if kind == "stop":
            self.stop_reason = None
            return "stop"
        if kind == "restart":
            return "restart"
        if kind == "repeat":
            for _ in range(max(0, int(a.get("times", 1)))):
                result = self._run_steps(a.get("actions", []), ctx)
                if result != "ok":
                    return result
            return "ok"
        if kind == "if":
            if self._condition_true(a.get("condition", {})):
                return self._run_steps(a.get("actions", []), ctx)
            return "ok"
        if kind == "retry":
            tries = max(1, int(a.get("tries", 3)))
            for n in range(tries):
                result = self._run_steps(a.get("actions", []), ctx)
                if result != "ok":
                    return result
                if self._condition_true(a.get("condition", {}), wait=2.0):
                    return "ok"
                self._set_note(f"Retry: try {n + 2} of {tries}...") if n + 1 < tries else None
            return "ok"
        if kind == "wait_picture":
            waited = self._wait_for_picture(a, bg, held_keys, held_buttons, ctx["away"])
            return waited if waited in ("stop", "gameback") else "ok"
        # one-off actions: done as recorded events would be
        for ev in self._step_events(a):
            if bg is not None:
                self._replay_event_bg(bg, ev, held_keys)
            else:
                self._replay_event(ev, held_keys, held_buttons)
            if ev.get("pause"):
                result = self._pause(ev["pause"], ctx)
                if result != "ok":
                    return result
        return "ok"

    @staticmethod
    def _step_events(a):
        """The events a key / type / click / move / scroll step plays (with "pause" after some)."""
        kind = a.get("kind")
        out = []
        if kind == "key":
            mode = a.get("mode", "press")
            key = a.get("key", {})
            if mode == "down":
                out.append({"type": "key", "key": key, "pressed": True})
            elif mode == "up":
                out.append({"type": "key", "key": key, "pressed": False})
            else:
                hold = max(0.03, float(a.get("hold", 0) or 0))  # how long the key stays down
                for _ in range(max(1, int(a.get("times", 1)))):
                    out.append({"type": "key", "key": key, "pressed": True, "pause": hold})
                    out.append({"type": "key", "key": key, "pressed": False, "pause": 0.03})
        elif kind == "type":
            delay = max(0.0, float(a.get("delay", 0.02)))
            for ch in str(a.get("text", "")):
                key = {"char": ch} if ch not in "\n\r\t" else {"special": {"\n": "enter", "\r": "enter",
                                                                             "\t": "tab"}[ch]}
                if ch == " ":
                    key = {"special": "space"}
                out.append({"type": "key", "key": key, "pressed": True})
                out.append({"type": "key", "key": key, "pressed": False, "pause": delay})
        elif kind == "click":
            x, y, button, mode = a.get("x", 0), a.get("y", 0), a.get("button", "left"), a.get("mode", "click")
            out.append({"type": "move", "x": x, "y": y, "pause": 0.03})
            presses = {"click": [True, False], "double": [True, False, True, False], "down": [True],
                       "up": [False]}.get(mode, [True, False])
            hold = max(0.04, float(a.get("hold", 0) or 0)) if mode == "click" else 0.04  # how long it's held
            for pressed in presses:
                out.append({"type": "click", "x": x, "y": y, "button": button, "pressed": pressed,
                            "pause": hold if pressed else 0.04})
        elif kind == "move":
            out.append({"type": "move", "x": a.get("x", 0), "y": a.get("y", 0)})
        elif kind == "scroll":
            out.append({"type": "scroll", "dx": 0, "dy": int(a.get("amount", 0))})
        return out

    def _pause(self, seconds, ctx):
        """Wait (playback's clock, so Pause works), noticing Stop, picture watch and the game leaving."""
        end = self._play_clock() + max(0.0, seconds)
        while True:
            if self.stop_play.is_set():
                return "stop"
            if ctx["seen"].is_set():
                now = self._picture_now(ctx)
                if now:
                    return now
            if ctx["away"] is not None:
                gone = ctx["away"](*ctx["held"])
                if gone:
                    return gone if gone == "gameback" else "stop"
            left = end - self._play_clock()
            if left <= 0:
                return "ok"
            time.sleep(min(left, 0.02))

    def _play_events(self, events, ctx):
        """Recorded events, each at its own time from the start of this step."""
        speed, bg, seen, away = ctx["speed"], ctx["bg"], ctx["seen"], ctx["away"]
        held_keys, held_buttons = ctx["held"]
        start = self._play_clock()
        vary = ctx.get("vary")
        earliest = start
        offsets = {}  # mouse button -> how far its click was moved (the release lands on the same spot)
        for ev in events:
            target = start + ev["t"] / speed
            if vary:
                # a little earlier or later, never out of order
                if vary["ms"]:
                    target = max(earliest, target + random.uniform(-vary["ms"], vary["ms"]) / 1000.0)
                    earliest = target
                if vary["px"] and ev["type"] == "click" and "x" in ev:
                    if ev["pressed"] or ev["button"] not in offsets:
                        offsets[ev["button"]] = (random.randint(-vary["px"], vary["px"]),
                                                 random.randint(-vary["px"], vary["px"]))
                    dx, dy = offsets[ev["button"]] if ev["pressed"] else offsets.pop(ev["button"])
                    ev = dict(ev, x=ev["x"] + dx, y=ev["y"] + dy)
            # wait in small steps so Stop (F12) and the picture are noticed quickly
            while True:
                if self.stop_play.is_set():
                    return "stop"
                if seen.is_set():
                    now = self._picture_now(ctx)
                    if now:
                        return now
                if away is not None:
                    gone = away(held_keys, held_buttons)
                    if gone:  # waited too long for the game to come back, or it closed
                        return gone if gone == "gameback" else "stop"
                remaining = target - self._play_clock()
                if remaining <= 0:
                    break
                if remaining > SPIN_SECONDS:
                    time.sleep(min(remaining - SPIN_SECONDS * 0.75, 0.02))
                else:
                    time.sleep(0)  # the last moment: check the clock closely (steadier quick taps)
            if ev["type"] == "wait_picture":
                before = self._play_clock()
                waited = self._wait_for_picture(ev, bg, held_keys, held_buttons, away)
                if waited in ("stop", "gameback"):
                    return waited
                start += self._play_clock() - before  # the rest keeps its timing after the wait
                earliest = start
                continue
            if bg is not None:
                self._replay_event_bg(bg, ev, held_keys)
            else:
                self._replay_event(ev, held_keys, held_buttons)
        return "ok"

    def _condition_true(self, condition, wait=0.0):
        """Whether an If / Retry condition holds now ("shows": the picture is on screen, or isn't).
        wait: look again for up to that many seconds before saying it doesn't."""
        matcher = self.wait_matchers.get(id(condition))
        if matcher is None:
            return not condition.get("shows", True)
        need = max(0.5, min(0.99, condition.get("match", 85) / 100.0))
        deadline = time.perf_counter() + wait
        while True:
            try:
                screen = self._hide_own_window(image_watch.grab_screen(), image_watch.screen_origin())
                score, _ = matcher.find(screen, good_enough=need, quick=matcher.last_rect is not None)
                if score < need and matcher.last_rect is None:
                    score, _ = matcher.find(screen, good_enough=need)
            except Exception as exc:
                diag.error("Couldn't check a condition's picture", exc)
                score = 0.0
            shows = score >= need
            if shows == bool(condition.get("shows", True)):
                return True
            if time.perf_counter() >= deadline or self.stop_play.is_set():
                return False
            self.stop_play.wait(0.25)

    def _run_finished(self, count, how):
        """One run of the macro is over (how: "end" = it played to the end, "picture" = picture watch).
        The dark window sends a Discord message here, if that's set up."""

    # ------------------------------------------------------------ the game must stay in front

    def _game_exe_now(self):
        """The game being played: the macro's program, else the program in front as playing starts
        (not this app), else the last game a macro was recorded or played in. Remembered for next time."""
        exe = (self.macro_program or {}).get("exe")
        if not exe:
            fg = window_tools.foreground()
            if fg and window_tools.pid_of(fg) != os.getpid():
                exe = window_tools.exe_of(fg)
        if exe:
            self.settings["last_game_exe"] = exe
            return exe
        return self.settings.get("last_game_exe")

    def _game_windows(self):
        """The windows that count as "the game" while playing: the macro's program if it's open,
        else whatever is in front when playing starts (unless that's this app). None = don't check."""
        own = os.getpid()
        exe = (self.macro_program or {}).get("exe")
        fg = window_tools.foreground()
        if exe:
            wins = set(window_tools.windows_of(exe))
            if wins:
                return wins
        if fg and window_tools.pid_of(fg) != own:
            return {fg}
        return None

    # ------------------------------------------------------------ small random timing

    def _vary_settings(self):
        """Settings > Playback > "Small random timing": {"on", "ms" (each action up to this much
        earlier or later), "px" (clicks land up to this far from their spot)}. Off unless turned on.
        It keeps a long loop from drifting the exact same way every run; it hides nothing."""
        saved = self.settings.get("vary")
        saved = saved if isinstance(saved, dict) else {}
        return {"on": bool(saved.get("on", False)), "ms": int_setting(saved, "ms", 20, 0, 500),
                "px": int_setting(saved, "px", 3, 0, 50)}

    def _vary_now(self):
        """What to vary for the open macro: its own choice ("vary" in its file: mode "off", "own"
        with ms / px, or the usual setting), or None for exact playback."""
        own = getattr(self, "macro_vary", None)
        own = own if isinstance(own, dict) else {}
        usual = self._vary_settings()
        if own.get("mode") == "off":
            return None
        if own.get("mode") == "own":
            out = {"ms": int_setting(own, "ms", usual["ms"], 0, 500), "px": int_setting(own, "px", usual["px"], 0, 50)}
        elif usual["on"]:
            out = {"ms": usual["ms"], "px": usual["px"]}
        else:
            return None
        return out if out["ms"] or out["px"] else None

    # ------------------------------------------------------------ stopping by itself

    def _auto_stop_settings(self):
        """Settings > Playback > "Stop by itself": {"on", "runs", "fragments", "minutes", "at"
        ("HH:MM"), "finish_run", "then" (nothing | close | sleep | shutdown), "warn"}; 0 / "" = not used."""
        saved = self.settings.get("auto_stop")
        saved = saved if isinstance(saved, dict) else {}
        at = str(saved.get("at") or "").strip()
        try:
            hh, mm = at.split(":")
            at = f"{int(hh) % 24:02}:{int(mm) % 60:02}"
        except ValueError:
            at = ""
        try:
            minutes = max(0.0, min(100000.0, float(saved.get("minutes") or 0)))
        except (TypeError, ValueError):
            minutes = 0.0
        then = saved.get("then") if saved.get("then") in AUTO_STOP_THEN else "nothing"
        return {"on": bool(saved.get("on", False)), "runs": int_setting(saved, "runs", 0, 0, 1000000),
                "fragments": int_setting(saved, "fragments", 0, 0, 1000000), "minutes": minutes, "at": at,
                "finish_run": bool(saved.get("finish_run", True)), "then": then,
                "warn": bool(saved.get("warn", True))}

    def _prepare_auto_stop(self):
        """What "Stop by itself" means for the playback that starts now (None = it's off)."""
        auto = self._auto_stop_settings()
        if not auto["on"] or not (auto["runs"] or auto["fragments"] or auto["minutes"] or auto["at"]):
            return None
        now = time.time()
        deadlines = []
        if auto["minutes"]:
            deadlines.append(now + auto["minutes"] * 60)
        if auto["at"]:
            hh, mm = (int(v) for v in auto["at"].split(":"))
            lt = time.localtime(now)
            at = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mm, 0, 0, 0, -1))
            deadlines.append(at if at > now + 1 else at + 86400)
        auto["deadline"] = min(deadlines) if deadlines else None
        auto["cancelled"] = False
        auto["due"] = None
        return auto

    def cancel_auto_stop(self):
        """Keep going: "Stop by itself" is off for the playback that's running. True if it was on."""
        auto = getattr(self, "auto_stop", None)
        if not self.playing or not auto or auto["cancelled"]:
            return False
        auto["cancelled"] = True
        diag.info("Stop by itself was cancelled for this playback")
        return True

    def _auto_stop_timer(self, auto, done):
        """Waits for the time to stop at (telling Discord 5 minutes before)."""
        warn_at = auto["deadline"] - AUTO_STOP_WARN_SECONDS
        if auto["warn"] and warn_at > time.time():
            if done.wait(warn_at - time.time()):
                return
            if not auto["cancelled"]:
                self._auto_stop_warning(max(1, round((auto["deadline"] - time.time()) / 60)))
        if done.wait(max(0.0, auto["deadline"] - time.time())) or auto["cancelled"]:
            return
        auto["due"] = "the time you set was reached"
        if not auto["finish_run"]:
            self.auto_stopped = auto["due"]
            self.stop_play.set()

    def _auto_stop_warning(self, minutes):
        """The macro stops by itself in a few minutes (the dark window tells Discord)."""
        diag.info(f"Stop by itself: stopping in about {minutes} min")

    def _auto_stop_due(self, state):
        """After a run: True when "Stop by itself" says this was the last one."""
        auto = getattr(self, "auto_stop", None)
        if not auto or auto["cancelled"]:
            return False
        reason = auto["due"]
        fragments = sum(self.session.fragments)
        if auto["runs"] and state["count"] >= auto["runs"]:
            reason = f"{auto['runs']} runs were played"
        elif auto["fragments"] and fragments >= auto["fragments"]:
            reason = f"{fragments} divine fragment{'s' if fragments != 1 else ''} dropped"
        if not reason:
            return False
        self.auto_stopped = reason
        return True

    def _auto_stop_then(self):
        """After stopping by itself: close the game, or put the PC to sleep, or shut it down."""
        auto = getattr(self, "auto_stop", None) or {}
        then = auto.get("then", "nothing")
        if then == "nothing":
            return
        try:
            self._power_action(then)
        except Exception as exc:
            diag.error(f"Stop by itself: couldn't do \"{then}\"", exc)

    def _power_action(self, then):
        import subprocess

        diag.info(f"Stop by itself: {then}")
        if then == "close":
            exe = (self.macro_program or {}).get("exe") or getattr(self, "play_game_exe", None)
            for hwnd in window_tools.windows_of(exe) if exe else []:
                window_tools.close_window(hwnd)
        elif then == "sleep" and window_tools.IS_WIN:
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        elif then == "shutdown" and window_tools.IS_WIN:
            subprocess.Popen(["shutdown", "/s", "/t", "60", "/c",
                              "Macro Recorder: the macro is done. Shutting down in 1 minute."])
        elif then == "cancel_shutdown" and window_tools.IS_WIN:
            subprocess.Popen(["shutdown", "/a"])

    def _closed_settings(self):
        """Settings > Playback > "If the game closes": {"action": "wait" | "stop" | "reopen", "open":
        what to open (a link or a file), "macro": the rejoin macro, "tries", "settle": seconds to
        let the game load before the macro}."""
        saved = self.settings.get("game_closed")
        saved = saved if isinstance(saved, dict) else {}
        action = saved.get("action") if saved.get("action") in ("wait", "stop", "reopen") else "wait"
        on = bool(saved.get("on", True))
        return {"action": action if on else "wait", "chosen": action, "on": on, "open": str(saved.get("open") or "").strip(),
                "macro": str(saved.get("macro") or ""),
                "tries": int_setting(saved, "tries", 3, 1, 20),
                "settle": int_setting(saved, "settle", 20, 0, 600),
                "open_wait": int_setting(saved, "open_wait", 120, 10, 1800)}

    def _closed_watcher(self, bg):
        """A function playback calls often: when every window of the game has been gone for a few
        seconds (it crashed or was closed), it does what "If the game closes" says. It returns
        False (all fine), True (stop playback) or "gameback" (the game is open again: start the
        run over). None when there's nothing to check."""
        opts = self._closed_settings()
        exe = (self.macro_program or {}).get("exe") or getattr(self, "play_game_exe", None)
        if bg is not None or opts["action"] == "wait" or not exe or not window_tools.IS_WIN:
            return None
        steps = getattr(self, "closed_steps", None)
        state = {"last": 0.0, "since": None}

        def check(held_keys, held_buttons):
            now = time.perf_counter()
            if now - state["last"] < 1.0:
                return False
            state["last"] = now
            if window_tools.windows_of(exe):
                state["since"] = None
                return False
            if state["since"] is None:
                state["since"] = now
                return False
            if now - state["since"] < GAME_GONE_SECONDS:
                return False
            state["since"] = None
            self._release_held(None, held_keys, held_buttons)
            return self._game_closed(opts, exe, steps)
        return check

    def _open_target(self, target):
        """Open a link, shortcut or program as if it was double-clicked."""
        if hasattr(os, "startfile"):
            os.startfile(target)  # noqa: S606 (the user's own choice in Settings)
        else:
            import subprocess

            subprocess.Popen(["open", target])

    def _game_closed(self, opts, exe, steps):
        """Every window of the game is gone. Stop, or open the game again and play the rejoin macro
        (each failed try waits longer). Returns True (stop) or "gameback"."""
        if opts["action"] == "stop":
            self.stop_reason = "Stopped: the game closed (Settings > Playback > If the game closes)."
            diag.info(self.stop_reason)
            return True
        self._away_pause(False)
        self._recovery_event("lost", "The game closed. Opening it again.")
        ctx = getattr(self, "play_ctx", None) or {}
        sub = dict(ctx, seen=threading.Event(), watch=None, away=None)
        tries = opts["tries"]

        def wait_for_window(seconds, note):
            end = time.perf_counter() + seconds
            while time.perf_counter() < end:
                wins = window_tools.windows_of(exe)
                if wins:
                    return wins
                self._set_note(f"{note} ({int(end - time.perf_counter()) + 1} s)...")
                if self.stop_play.wait(1.0):
                    return []
            return window_tools.windows_of(exe)

        for n in range(tries):
            if n:
                pause = min(300, 15 * 2 ** (n - 1))
                for left in range(pause, 0, -1):
                    self._set_note(f"The game isn't back yet. Try {n + 1} of {tries} in {left} s...")
                    if self.stop_play.wait(1.0):
                        return True
            wins = window_tools.windows_of(exe)
            if not wins and opts["open"]:
                self._set_note(f"Opening the game again (try {n + 1} of {tries})...")
                try:
                    self._open_target(opts["open"])
                except Exception as exc:
                    diag.error("Couldn't open the game again", exc)
                wins = wait_for_window(opts["open_wait"], "Waiting for the game's window")
            if self.stop_play.is_set():
                return True
            if wins:
                for left in range(opts["settle"], 0, -1):
                    self._set_note(f"The game is open. Letting it load ({left} s)...")
                    if self.stop_play.wait(1.0):
                        return True
                wins = window_tools.windows_of(exe) or wins
                window_tools.force_to_front(wins[0])
                time.sleep(0.5)
            if steps and (wins or not opts["open"]):
                self._set_note("Playing the rejoin macro...")
                result = self._run_passes(steps, sub, 1, counts=False)
                self._release_held(None, *sub["held"]) if sub.get("held") else None
                if result == "stop" or self.stop_play.is_set():
                    return True
                if not wins:  # (no link to open: the rejoin macro opens the game itself)
                    wins = wait_for_window(opts["open_wait"], "Waiting for the game's window")
            if self.stop_play.is_set():
                return True
            if window_tools.windows_of(exe):
                self.session.reconnects += 1
                run_history.note("reconnects")
                self._recovery_event("back", f"The game is open again after {n + 1} "
                                     f"{'try' if n == 0 else 'tries'}. The macro starts over.")
                return "gameback"
        self.session.failed_reconnects += 1
        self.stop_reason = (f"Stopped: the game closed and couldn't be opened again after {tries} "
                            f"{'try' if tries == 1 else 'tries'}.")
        diag.error(self.stop_reason)
        self._recovery_event("failed", self.stop_reason)
        return True

    def _away_watcher(self, bg, closed=None):
        """When "Pause if the game isn't in front" is on: a function the playback loop calls often.
        If another window (a pop-up, Discord, this app) has been in front for a moment, it lets go of
        every held key and button and pauses until the game is in front again. It returns True
        when playback should stop (waited longer than the limit). None when there's nothing to check."""
        if bg is not None or not self.settings.get("pause_when_away", True) or not window_tools.IS_WIN:
            return None
        games = self._game_windows()
        if not games:
            return None
        limit = int_setting(self.settings, "away_stop_seconds", 0, 0, 3600)
        state = {"since": None, "last_check": 0.0}

        exe_of = {}  # window -> its program (asked once per window, not 20 times a second)

        def game_in_front():
            fg = window_tools.foreground()
            if fg is None or fg in games:
                return True  # (no window at all for a moment happens while windows change hands)
            exe = (self.macro_program or {}).get("exe") or (closed and getattr(self, "play_game_exe", None))
            if fg not in exe_of:
                if len(exe_of) > 200:
                    exe_of.clear()
                exe_of[fg] = window_tools.exe_of(fg)
            if exe and exe_of[fg] == exe:  # the game opened another window of its own
                games.add(fg)
                return True
            return False

        def check(held_keys, held_buttons):
            now = time.perf_counter()
            if now - state["last_check"] < 0.05 or self._user_paused():
                return False
            state["last_check"] = now
            if game_in_front():
                state["since"] = None
                return False
            if state["since"] is None:
                state["since"] = now
                return False
            if now - state["since"] < AWAY_GRACE:
                return False
            # pause: let go of everything, and wait for the game to come back
            self._release_held(None, held_keys, held_buttons)
            self._away_pause(True)
            diag.info("Paused: the game isn't in front")
            began = time.perf_counter()
            try:
                while not self.stop_play.is_set():
                    waited = time.perf_counter() - began
                    if limit and waited >= limit:
                        self.stop_reason = (f"Stopped: the game wasn't in front for {limit} s "
                                            "(Settings > Playback > Pause if the game isn't in front).")
                        diag.info(self.stop_reason)
                        return True
                    note = "Paused: the game isn't in front. Click back into the game to go on"
                    if limit:
                        note += f" (stops in {int(limit - waited) + 1} s)"
                    self._set_note(note + ".")
                    if closed is not None:  # the game may be gone altogether (crashed, closed)
                        gone = closed(held_keys, held_buttons)
                        if gone:
                            return gone
                    if game_in_front():
                        # give the game a moment to take the mouse and keyboard back
                        if self.stop_play.wait(0.3):
                            break
                        if game_in_front():
                            break
                    self.stop_play.wait(0.1)
            finally:
                self._away_pause(False)
                state["since"] = None
            self._set_note("Playing...")
            diag.info("Going on: the game is in front again")
            return False

        return check

    def _user_paused(self):
        """True while the user paused playback (the dark window's Pause key)."""
        return False

    def _away_pause(self, on):
        """Playback's clock stands still while the game isn't in front."""
        if on and self.away_started is None:
            self.away_started = time.perf_counter()
        elif not on and self.away_started is not None:
            self.away_total += time.perf_counter() - self.away_started
            self.away_started = None

    # ------------------------------------------------------------ "Wait for a picture" steps

    def _wait_for_picture(self, ev, bg, held_keys, held_buttons, away):
        """A step that waits until a picture shows on screen (up to its time limit), then maybe clicks
        it. Returns "stop" when the macro should stop, else "go on"."""
        matcher = self.wait_matchers.get(id(ev))
        if matcher is None:
            return "go on"
        need = max(0.5, min(0.99, ev.get("match", 85) / 100.0))
        timeout = float(ev.get("timeout", 30))
        began = time.perf_counter()
        found = None
        looks = 0
        with image_watch.mss.mss() as sct:
            origin = image_watch.screen_origin(sct)
            while not self.stop_play.is_set():
                if away is not None:
                    gone = away(held_keys, held_buttons)
                    if gone:
                        return gone if gone == "gameback" else "stop"
                waited = time.perf_counter() - began
                left = timeout - waited
                if timeout > 0 and left <= 0:
                    break
                label = ev.get("name") or "the picture"
                self._set_note(f"Waiting for {label}" + (f" ({int(left) + 1} s)..." if timeout > 0 else "..."))
                started = time.perf_counter()
                try:
                    # first only around where it was found before (light); the whole screen every
                    # other look, or every look while it was never found
                    whole = matcher.last_rect is None or looks % 2 == 0
                    looks += 1
                    region = None if whole else matcher.near_last_area()
                    screen = self._hide_own_window(image_watch.grab_screen(sct, region), origin)
                    score, rect = matcher.find_near_last(screen, good_enough=need)
                    if score < need and whole:
                        score, rect = matcher.find(screen, good_enough=need, quick=True)
                except Exception as exc:
                    diag.error("Wait for a picture: screenshot failed", exc)
                    score, rect = 0.0, None
                if score >= need and rect is not None:
                    x, y, w, h = rect
                    found = (origin[0] + x + w // 2, origin[1] + y + h // 2)
                    break
                # look 4 times a second; when a look is slow, rest at least as long as it took (so
                # waiting never takes more than about half of one CPU core away from the game)
                self.stop_play.wait(max(0.25, time.perf_counter() - started))
        if self.stop_play.is_set():
            return "stop"
        if found is None:
            if ev.get("otherwise") == "stop":
                self.stop_reason = f"Stopped: {ev.get('name') or 'the picture'} didn't show within {timeout:g} s."
                diag.info(self.stop_reason)
                return "stop"
            return "go on"
        if ev.get("click"):
            self._click_at(*found)
        return "go on"

    def _replay_event(self, ev, held_keys, held_buttons):
        kind = ev["type"]
        if kind == "wait_picture":
            return
        if kind == "move":
            move_to(self.mouse_ctrl, ev["x"], ev["y"])
        elif kind == "move_rel":
            move_relative(self.mouse_ctrl, ev["dx"], ev["dy"], held_buttons)
        elif kind == "click":
            button = button_from_name(ev["button"])
            if "x" in ev and self.mouse_ctrl.position != (ev["x"], ev["y"]):
                move_to(self.mouse_ctrl, ev["x"], ev["y"])
            if ev["pressed"]:
                self.mouse_ctrl.press(button)
                held_buttons.add(button)
            else:
                self.mouse_ctrl.release(button)
                held_buttons.discard(button)
        elif kind == "scroll":
            if "x" in ev and self.mouse_ctrl.position != (ev["x"], ev["y"]):
                move_to(self.mouse_ctrl, ev["x"], ev["y"])
            self.mouse_ctrl.scroll(ev["dx"], ev["dy"])
        elif kind == "key":
            key = data_to_key(ev["key"])
            if key is None:
                return  # a key this computer doesn't have
            if ev["pressed"]:
                self.kb_ctrl.press(key)
                held_keys.add(key)
            else:
                self.kb_ctrl.release(key)
                held_keys.discard(key)

    def _replay_event_bg(self, bg, ev, held_vks):
        kind = ev["type"]
        if kind in ("move_rel", "wait_picture"):
            return  # camera-style moves can't be sent to a background window
        x, y = (ev["x"], ev["y"]) if "x" in ev else self.mouse_ctrl.position
        if kind == "move":
            bg.mouse_move(x, y)
        elif kind == "click":
            bg.mouse_button(x, y, ev["button"], ev["pressed"])
        elif kind == "scroll":
            bg.scroll(x, y, ev["dx"], ev["dy"])
        elif kind == "key":
            vk = key_to_vk(ev["key"])
            if vk is None:
                return
            bg.key(vk, ev["pressed"])
            (held_vks.add if ev["pressed"] else held_vks.discard)(vk)

    def _clock_back(self, seconds):
        """Take time out of playback's clock (something else was done meanwhile)."""
        if self.away_started is None:  # (while paused the clock isn't running anyway)
            self.away_total += seconds

    def _play_clock(self):
        """The clock playback follows: it stands still while the game isn't in front (and, in the dark
        window, while playback is paused)."""
        now = self.away_started if self.away_started is not None else time.perf_counter()
        return now - self.away_total

    def _playback_done(self):
        self.playing = False
        self.countdown_left = 0
        self.play_note = ""
        self._refresh()
        diag.info("Playback ended" + (f": {self.stop_reason}" if self.stop_reason else "")
                  + (f" (stopped by itself: {self.auto_stopped})" if getattr(self, "auto_stopped", None) else ""))
        run_history.save()
        if getattr(self, "auto_stopped", None) and type(self) is MacroRecorder:
            self._auto_stop_then()
        if self.stop_reason and type(self) is MacroRecorder:  # (the dark window shows it its own way)
            messagebox.showwarning("Macro Recorder", self.stop_reason)

    # ------------------------------------------------------------ files

    def save(self):
        if not self.events:
            messagebox.showinfo("Macro Recorder", "Nothing to save yet. Record something first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=FILE_EXT, filetypes=FILE_TYPES, initialfile="my_macro" + FILE_EXT
        )
        if not path:
            return
        self._read_made_for(quiet=True)
        data = {
            "app": "macro_recorder",
            "version": FILE_VERSION,
            "events": self.events,  # positions as made, on the "screen" size below
        }
        if self.macro_screen:
            data["screen"] = {"width": self.macro_screen[0], "height": self.macro_screen[1]}
        with open(path, "w", encoding="utf-8") as f:
            dump_macro(data, f)
        self.current_file = path
        self._refresh()

    def load(self, path=None, quiet=False):
        """Open a macro file. quiet: no message boxes (an error goes to self.load_error instead).
        Returns True when the macro was opened."""
        self.load_error = None

        def fail(text):
            self.load_error = text
            if not quiet:
                messagebox.showerror("Macro Recorder", text)
            return False

        if self.recording or self.playing:
            return False
        if path is None:
            path = filedialog.askopenfilename(filetypes=OPEN_FILE_TYPES)
        if not path:
            return False
        imported = None
        self.file_data = {}
        steps = None
        try:
            events, screen = self._read_own_file(path)
            raw = self.file_data.get("actions")
            if isinstance(raw, list) and raw and all(isinstance(a, dict) for a in raw):
                # a macro with steps made in Edit (its recorded parts may be stored in a smaller form)
                try:
                    steps = expand_steps(raw)
                except (ValueError, RecursionError) as exc:
                    return fail(f"Couldn't open that file: {exc}.")
        except Exception as own_error:
            # not one of ours: try the formats of other macro recorders
            try:
                imported = importers.import_file(path)
            except importers.ImportError_ as exc:
                return fail(f"Couldn't open that file:\n{exc}")
            except Exception as exc:
                if os.path.splitext(path)[1].lower() in (FILE_EXT, ".json"):
                    exc = own_error
                return fail(f"Couldn't open that file:\n{exc}")
            if not imported.events:
                return fail("No actions could be read from that file.")
            events = imported.events
            events.sort(key=lambda ev: ev["t"])
            screen = {"width": imported.screen[0], "height": imported.screen[1]} if imported.screen else {}

        # positions stay as they are in the file; they're scaled from this size when playing
        try:
            made_for = (int(screen.get("width")), int(screen.get("height")))
            if made_for[0] <= 0 or made_for[1] <= 0:
                made_for = None
        except (TypeError, ValueError):
            made_for = None
        self.macro_screen = made_for
        self._show_made_for()
        program = imported.program if imported is not None else self.file_data.get("program")
        self.macro_program = program if isinstance(program, dict) else None
        # the macro's own choice for "Small random timing" and its linked profile (kept in its file)
        own = self.file_data if imported is None else {}
        self.macro_vary = own.get("vary") if isinstance(own.get("vary"), dict) else None
        self.macro_profile = own.get("profile") if isinstance(own.get("profile"), str) else None
        self.events = events
        self.actions = None
        if steps:
            self.set_steps(steps)
        self.current_file = path
        diag.info(f"Opened a macro: {len(events)} actions" + (f" ({imported.source})" if imported else ""))
        self._refresh()
        play_on = self._read_play_on(quiet=True)
        size_note = ""
        if made_for and play_on and made_for != play_on:
            size_note = (f"This macro was made for a {format_resolution(made_for)} screen. Mouse clicks will "
                         f"be moved to fit {format_resolution(play_on)} (see \"Screen size\"). "
                         "Play the game in fullscreen.")
        elif not made_for and any("x" in ev for ev in events):
            size_note = ("This file doesn't say which screen size it was made for. If it was made on a "
                         "different size than yours, pick that size in \"Macro recorded at\".")
        if quiet:
            return True
        if imported is None and size_note:
            messagebox.showinfo("Macro Recorder", size_note)
        if imported is not None:
            lines = [f"Opened a {imported.source} macro: {len(events)} actions, {events[-1]['t']:.1f} s."]
            if size_note:
                lines.append(size_note)
            if imported.skipped:
                lines.append(f"{imported.skipped} step(s) couldn't be converted and were left out.")
            lines.extend(dict.fromkeys(imported.notes))
            if any(ev["type"] == "move_rel" for ev in events):
                lines.append("It turns the camera with mouse movements, so play it on the whole screen, "
                             "not into a background window.")
            lines.append("Click Save... to keep it as a .macro file.")
            messagebox.showinfo("Macro Recorder", "\n\n".join(lines))
        return True

    def _read_own_file(self, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("format") == "luvmacro":
            raise ValueError("a luvmacro file")
        events = data["events"]
        if not isinstance(events, list):
            raise ValueError("this isn't a macro file")
        self.file_data = data  # the rest of the file (its program, pictures to watch for)
        return expand_moves(events), data.get("screen", {})

    def link_file_type(self):
        """Make .macro files open with this app when double-clicked (current Windows user only)."""
        import winreg

        if getattr(sys, "frozen", False):
            command = f'"{sys.executable}" "%1"'
        else:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = sys.executable
            command = f'"{pythonw}" "{os.path.abspath(__file__)}" "%1"'
        prog_id = "MacroRecorder.Macro"
        try:
            base = r"Software\Classes"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + "\\" + FILE_EXT) as k:
                winreg.SetValue(k, "", winreg.REG_SZ, prog_id)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + "\\" + prog_id) as k:
                winreg.SetValue(k, "", winreg.REG_SZ, "Macro Recorder macro")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + "\\" + prog_id + r"\shell\open\command") as k:
                winreg.SetValue(k, "", winreg.REG_SZ, command)
            import ctypes

            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # refresh file icons
        except Exception as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't link .macro files:\n{exc}")
            return
        messagebox.showinfo(
            "Macro Recorder",
            "Done. Double-clicking a .macro file now opens it here.\n"
            "If you move this program, click this button again.",
        )

    def clear(self):
        if self.events and messagebox.askyesno("Macro Recorder", "Clear the current recording?"):
            self.events = []
            self.actions = None
            self.current_file = None
            self.macro_screen = None
            self.macro_program = None
            self._show_made_for()
            self._refresh()

    def _on_close(self):
        self._save_settings()
        flush_settings()
        self._stop_camera()
        self.stop_play.set()
        self.kb_listener.stop()
        self.mouse_listener.stop()
        self.root.destroy()


MAC_PERMISSION_HELP = (
    "On a Mac, Macro Recorder needs permission to watch and control the mouse and keyboard, "
    "and to look at the screen. Still missing: {missing}.\n\n"
    "Open System Settings > Privacy & Security and turn Macro Recorder on (or Terminal, if you "
    "started it from Terminal) under:\n"
    "  - Accessibility\n  - Input Monitoring\n  - Screen Recording\n\n"
    "Then quit Macro Recorder and open it again.")


def main():
    make_dpi_aware()
    if IS_MAC:
        try:
            mac_prepare_pynput()
        except Exception:
            pass
    root = tk.Tk()
    app = MacroRecorder(root)
    # a macro file double-clicked or dragged onto the app arrives as the first argument
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        root.after(100, lambda: app.load(sys.argv[1]))
    if IS_MAC:
        # on a Mac, double-clicked or dropped files arrive as an "open document" message instead
        def open_documents(*paths):
            if paths:
                app.load(paths[0])
        root.createcommand("::tk::mac::OpenDocument", open_documents)
        missing = mac_missing_permissions()
        if missing:
            root.after(300, lambda: messagebox.showwarning(
                "Macro Recorder", MAC_PERMISSION_HELP.format(missing=", ".join(missing))))
    root.mainloop()


if __name__ == "__main__":
    # the window people use is the dark one in modern_ui.py (it builds on the class above);
    # main() above still opens the old plain window, if ever needed
    import modern_ui

    modern_ui.main()
