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

if __name__ == "__main__":  # (the app starts by running this file: the work is done by the module "macro_recorder", which modern_ui imports)
    import modern_ui

    modern_ui.main()
    raise SystemExit

import json
import os
import queue
import sys
import random
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# (2.9.1) a picture inside a shared file (a .macro, a share file) can claim to be gigantic and fill the
# memory when it's opened; OpenCV refuses pictures bigger than this (100 megapixels, about a 13000 x
# 7500 photo: far more than any screen). Set before OpenCV is first loaded.
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(100_000_000))

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
import step_more
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
# the word "Disconnected" from Roblox's Disconnected box (a 2560x1440 screen). Only the word: the
# whole box matched only on its bright parts scored up to 0.86 on ordinary game screens, the word 0.62
BUILTIN_DISCONNECT = "disconnected_default.png"
BUILTIN_DISCONNECT_SCREEN_H = 1440
# AOT:R's gold "MISSION COMPLETED" title (the owner's picture), the built-in "mission completed" picture
BUILTIN_WIN_PICTURE = "completed_default.png"
BUILTIN_WIN_PICTURE_SCREEN_H = 1440
# and its gold "MISSION FAILED" title, the built-in "mission failed" picture (also taken at 1440p)
BUILTIN_LOSS_PICTURE = "failed_default.png"
BUILTIN_LOSS_PICTURE_SCREEN_H = 1440
LATE_RESULT_SECONDS = 30  # (2.12) a result this soon after an Unknown run goes to that run
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
    ("recover", "Disconnected: play my rejoin macro (Roblox), then go on",
     "for Roblox's Disconnected box: plays your rejoin macro, checks you're back, then the macro starts over"),
    ("play", "Play another macro, then start over", "for a screen that needs a few steps first"),
    ("switch", "Switch to another macro for good", "from now on that macro plays (and loops) instead of this one"),
    ("skip", "Skip to the next step", "the step that's playing ends at once"),
    ("key", "Press a key", "then the macro goes on"),
    ("wait", "Wait", "the macro stands still for some seconds, then goes on"),
    ("stop", "Stop the macro", "and say why"),
    ("nothing", "Nothing", "it only counts for another picture's \"only when … also shows\""),
    ("count", "Add to a counter", "counts up each time it shows (once, until it's gone again); the macro goes on"),
]
WATCH_ACTION_NAMES = {k: n for k, n, _ in WATCH_ACTIONS}
WATCH_INLINE = ("skip", "key", "wait", "nothing", "count")  # the macro goes on after these
WATCH_NEED_MACRO = ("play", "switch", "recover")
# what's remembered for each watched picture besides its file (None / missing = the usual)
WATCH_FIELDS = ("screen_h", "name", "action", "macro", "key", "seconds", "click", "cooldown", "also", "counts",
                "tries", "confirm_file", "confirm_screen_h", "confirm_seconds", "match", "ignore_bg",
                # (2.12) "Add to a counter", and a colour instead of the picture (its file is only a swatch)
                "counter", "amount", "keep", "color_on", "rgb", "tolerance", "area", "hold", "where", "x", "y",
                "x0", "y0", "x1", "y1")
# (2.9) "match" (50-99) and "ignore_bg": a picture's own Match % and Ignore background, instead of General's


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


def picture_on_by_default(pic):
    """A built-in picture is on to start with only in AOT:R; a copy anywhere else (added to another group,
    moved, or put there by mistake) starts off. Every other picture starts on."""
    return not (pic.get("builtin") in BUILTINS and picture_group(pic) != GROUP_AOTR)


def picture_on(pic):
    """Whether the picture itself is switched on ("on" is kept only when it isn't the usual)."""
    on = pic.get("on")
    return on if isinstance(on, bool) else picture_on_by_default(pic)


def set_picture_on(pic, on):
    if bool(on) == picture_on_by_default(pic):
        pic.pop("on", None)
    else:
        pic["on"] = bool(on)


def group_fields(entry):
    """The group fields of a picture's settings entry that are usable."""
    out = {}
    if isinstance(entry.get("group"), str) and entry["group"]:
        out["group"] = entry["group"]
    if entry.get("builtin") in BUILTINS:
        out["builtin"] = entry["builtin"]
    if isinstance(entry.get("on"), bool) and entry["on"] != picture_on_by_default(dict(entry, **out)):
        out["on"] = entry["on"]
    macros = entry.get("macros")
    if isinstance(macros, list) and macros:
        out["macros"] = [m for m in macros if isinstance(m, str) and m]
    return out


def picture_group(pic):
    """The id of the group a picture is in (built-in pictures start in AOT:R, others in My pictures)."""
    return pic.get("group") or (GROUP_AOTR if pic.get("builtin") else GROUP_MINE)


def watch_entry(pic):
    """What settings keep of a watched picture."""
    out = {"file": pic["file"], "screen_h": pic.get("screen_h")}
    for k in WATCH_FIELDS:
        if pic.get(k) not in (None, "", False) or (k in ("click", "counts", "ignore_bg") and pic.get(k) is False):
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
            workflow.clean_counter_step(a)  # (2.11: counters from someone's file are checked)
            workflow.clean_color_step(a)  # (2.12: and colour checks)
            step_more.clean_step(a)  # (2.12: and the new actions and options)
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


def shared_macro_path(path, folder):
    """How a macro file named inside another macro file is written there: relative to that file's
    folder when it's inside it, else only its file name. Never the whole path: a .macro gets shared,
    and a path like C:\\Users\\<name>\\... would show the Windows user name. Read back with
    MacroRecorder._find_macro_file (relative to the open macro, or beside it)."""
    if not isinstance(path, str) or not path:
        return path
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    if not folder or not os.path.isabs(path):
        return path if not os.path.isabs(path) and ".." not in path.replace("\\", "/").split("/") else name
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(folder))
    except ValueError:  # (another drive)
        return name
    if rel.startswith("..") or os.path.isabs(rel):
        return name
    return rel


def _steps_for_file(steps, folder):
    """A copy of the step tree with every other macro's path made shareable (see shared_macro_path)."""
    out = []
    for a in steps:
        if not isinstance(a, dict):
            out.append(a)
            continue
        b = a
        for key in ("file", "on_fail"):
            if a.get("kind") == "play_macro" and a.get(key):
                b = dict(b, **{key: shared_macro_path(a[key], folder)})
        for key in step_more.MACRO_KEYS:  # (2.12)
            if a.get(key):
                b = dict(b, **{key: shared_macro_path(a[key], folder)})
        if isinstance(a.get("actions"), list):
            b = dict(b, actions=_steps_for_file(a["actions"], folder))
        out.append(b)
    return out


# what a picture saved inside a .macro may carry (its png and screen_h aside), and how to check it
SHARED_PICTURE_TEXT = {"name": 60}
SHARED_PICTURE_NUMBERS = {"seconds": (0, 3600), "cooldown": (0, 3600), "confirm_seconds": (1, 3600),
                          "tries": (1, 20), "match": (50, 99)}
SHARED_PICTURE_SWITCHES = ("click", "counts", "ignore_bg")


def shared_picture_fields(entry, folder=None):
    """The fields of a picture that travels inside a .macro file, checked: known actions only, sensible
    numbers, short texts, and the macro it plays as a file name (looked for in folder, the folder
    of the macro it came with). Used both when saving (nothing of this PC's paths goes out) and when
    opening someone's macro (nothing odd comes in)."""
    out = {}
    if not isinstance(entry, dict):
        return out
    if entry.get("action") in WATCH_ACTION_NAMES:
        out["action"] = entry["action"]
    for k, n in SHARED_PICTURE_TEXT.items():
        if isinstance(entry.get(k), str) and entry[k].strip():
            out[k] = entry[k].strip()[:n]
    for k, (lo, hi) in SHARED_PICTURE_NUMBERS.items():
        v = entry.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v:
            out[k] = type(v)(min(hi, max(lo, v)))
    for k in SHARED_PICTURE_SWITCHES:
        if isinstance(entry.get(k), bool):
            out[k] = entry[k]
    key = entry.get("key")
    if isinstance(key, dict):  # (a key as recorded: {"vk": 13} / {"char": "a"} / {"special": "enter"})
        k = {}
        for name in ("vk", "mac_vk"):
            if isinstance(key.get(name), int) and not isinstance(key.get(name), bool) and 0 < key[name] < 512:
                k[name] = key[name]
        for name in ("char", "special"):
            if isinstance(key.get(name), str) and 0 < len(key[name]) <= 20:
                k[name] = key[name]
        if k:
            out["key"] = k
    if entry.get("action") == "count":  # (2.12)
        out["counter"] = workflow.clean_counter_name(entry.get("counter"))
        out["amount"] = workflow.clean_whole(entry.get("amount"), 1)
        if entry.get("keep") is True:
            out["keep"] = True
    if entry.get("color_on") is True:
        import color_check

        colour = color_check.clean({k: entry[k] for k in ("color_on", "rgb", "tolerance", "area", "hold", "where",
                                                          "x", "y", "x0", "y0", "x1", "y1") if k in entry})
        if colour.get("rgb"):
            out.update(colour)
    macro = entry.get("macro")
    if isinstance(macro, str) and macro.strip():
        name = macro.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if name.lower().endswith(FILE_EXT) and name not in (".", ".."):
            out["macro"] = os.path.join(folder, name) if folder else name
    return out


def dump_macro(data, f):
    """Write a macro file compactly: one action per line, no extra spaces (about half the size of
    the old layout, and quicker to open). Any program that reads JSON still reads it.

    Other macros it names (chain steps, a picture's rejoin macro) are written relative to the file's
    folder or as a file name only, never as a whole path of this PC."""
    folder = os.path.dirname(os.path.abspath(f.name)) if isinstance(getattr(f, "name", None), str) else None
    if isinstance(data.get("actions"), list):
        data = dict(data, actions=_steps_for_file(data["actions"], folder))
    if isinstance(data.get("watch_pictures"), list):
        pics = []
        for p in data["watch_pictures"]:
            if isinstance(p, dict) and p.get("png"):
                keep = {k: p[k] for k in ("png", "screen_h", "builtin") if k in p}
                keep.update(shared_picture_fields(p))
                if keep.get("macro"):
                    keep["macro"] = keep["macro"].replace("\\", "/").rsplit("/", 1)[-1]
                pics.append(keep)
        data = dict(data, watch_pictures=pics)
    if isinstance(data.get("program"), dict) and "title" in data["program"]:
        # (Preview 4) a window's title can hold private things (a page, a chat, a user name): files
        # keep only the program's name and the window's size
        data = dict(data, program={k: v for k, v in data["program"].items() if k != "title"})
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
        tmp = path + ".tmp"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, path)  # (a crash half way leaves the old file whole, never a cut-off one)
            w["written"][path] = text
        except Exception as exc:
            diag.error("Couldn't save the settings", exc)  # (not being able to remember them shouldn't stop the app)
            try:
                os.remove(tmp)
            except OSError:
                pass


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


def combine_checks(first, second):
    """(2.12) Two of playback's often-asked checks as one: the first one that has something to say."""
    if first is None:
        return second
    if second is None:
        return first

    def both(held_keys, held_buttons):
        return first(held_keys, held_buttons) or second(held_keys, held_buttons)
    both.before_key = getattr(first, "before_key", None) or getattr(second, "before_key", None)
    return both


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

# (2.13) the core class is built from these sections; each file holds one part of what it does
from core_settings import CoreSettingsMixin
from core_pictures import CorePicturesMixin
from core_recording import CoreRecordingMixin
from core_playback import CorePlaybackMixin
from core_steps import CoreStepsMixin
from core_watching import CoreWatchingMixin
from core_results import CoreResultsMixin
from core_guards import CoreGuardsMixin
from core_counters import CoreCountersMixin
from core_files import CoreFilesMixin


class MacroRecorder(CoreSettingsMixin, CorePicturesMixin, CoreRecordingMixin, CorePlaybackMixin, CoreStepsMixin, CoreWatchingMixin, CoreResultsMixin, CoreGuardsMixin, CoreCountersMixin, CoreFilesMixin, step_more.StepMoreMixin):
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


    # ------------------------------------------------------------ settings


    # ------------------------------------------------------------ watch for a picture


    # ------------------------------------------------------------ hotkeys window


    # ------------------------------------------------------------ recording


    # ------------------------------------------------------------ camera movement (Windows)


    # ------------------------------------------------------------ the program a macro is recorded in


    # ------------------------------------------------------------ playback


    # ------------------------------------------------------------ macros that play other macros


    # ------------------------------------------------------------ (2.12) colour checks


    # ------------------------------------------------------------ running the steps


    # ------------------------------------------------------------ the game must stay in front


    # ------------------------------------------------------------ small random timing


    # ------------------------------------------------------------ stopping by itself


    # ------------------------------------------------------------ (2.12) stuck run guard


    # ------------------------------------------------------------ "Wait for a picture" steps


    # ------------------------------------------------------------ (2.11) counters


    # ------------------------------------------------------------ files


MAC_PERMISSION_HELP = (
    "On a Mac, Macro Recorder needs permission to watch and control the mouse and keyboard, "
    "and to look at the screen. Still missing: {missing}.\n\n"
    "Open System Settings > Privacy & Security and turn Macro Recorder on (or Terminal, if you "
    "started it from Terminal) under:\n"
    "  - Accessibility\n  - Input Monitoring\n  - Screen Recording\n\n"
    "Then quit Macro Recorder and open it again.")
