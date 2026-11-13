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

import importers
import platform_keys

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

try:
    import image_watch
except ImportError:  # numpy / opencv / mss missing: the "watch for a picture" option is turned off
    image_watch = None

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


def resource_path(name):
    """A file that ships with the app: inside the .exe when built, else next to this script."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def watch_dir():
    """Where the pictures to watch for are kept."""
    return os.path.join(os.path.dirname(settings_path()), "watch_pictures")


def int_setting(settings, name, default, low, high):
    try:
        return max(low, min(high, int(settings.get(name, default))))
    except (TypeError, ValueError):
        return default


def save_settings(data):
    path = settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    except Exception:
        pass  # not being able to remember settings shouldn't stop the app


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

        self.settings = load_settings()
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
            text="While playing, start the macro over when one of these pictures shows on screen")
        self.watch_check.grid(row=0, column=0, columnspan=4, sticky="w")

        buttons = ttk.Frame(box)
        buttons.grid(row=1, column=0, columnspan=4, sticky="w", pady=4)
        self.btn_pick = ttk.Button(buttons, text="Add from screen...", command=self.pick_watch_picture)
        self.btn_pick_file = ttk.Button(buttons, text="Add picture file...", command=self.load_watch_picture)
        self.btn_test = ttk.Button(buttons, text="Test now", command=self.test_watch_picture)
        self.btn_pick.grid(row=0, column=0, padx=(0, 4))
        self.btn_pick_file.grid(row=0, column=1, padx=4)
        self.btn_builtin = ttk.Button(buttons, text="Add built-in RETRY", command=self.add_builtin_picture)
        self.btn_test.grid(row=0, column=3, padx=4)
        self.btn_builtin.grid(row=0, column=2, padx=4)
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

        self.watch_widgets = [self.watch_check, self.btn_pick, self.btn_pick_file, self.btn_test,
                              self.btn_builtin]
        self.watch_remove_buttons = []
        if image_watch is None:
            self.watch_var.set(False)
            ttk.Label(self.watch_list, foreground="gray",
                      text="Not available: this copy was built without picture support.").grid(sticky="w")
            return
        saved = s.get("watch_pictures")
        if not isinstance(saved, list):
            # first start: begin with the built-in RETRY picture, ready to use
            saved = []
            self.root.after(0, self.add_builtin_picture)
        for entry in saved:
            try:
                img = image_watch.load_image(os.path.join(watch_dir(), entry["file"]))
            except Exception:
                continue  # picture file gone: forget it
            self.watch_pictures.append({"img": img, "file": entry["file"], "screen_h": entry.get("screen_h")})
        self._show_watch_pictures()

    def _show_watch_pictures(self):
        for child in self.watch_list.winfo_children():
            child.destroy()
        self.watch_thumbs = []
        self.watch_remove_buttons = []
        if not self.watch_pictures:
            ttk.Label(self.watch_list, text="No picture yet", foreground="gray").grid(sticky="w")
        for i, pic in enumerate(self.watch_pictures):
            h, w = pic["img"].shape[:2]
            thumb = tk.PhotoImage(data=image_watch.png_data(pic["img"], 300, 50))
            self.watch_thumbs.append(thumb)
            ttk.Label(self.watch_list, image=thumb, compound="left", text=f"  {w} x {h}").grid(
                row=i, column=0, sticky="w", pady=1)
            b = ttk.Button(self.watch_list, text="Remove", command=lambda i=i: self._remove_watch_picture(i))
            b.grid(row=i, column=1, padx=(8, 0))
            self.watch_remove_buttons.append(b)
        self.settings["watch_pictures"] = [{"file": p["file"], "screen_h": p["screen_h"]}
                                           for p in self.watch_pictures]
        save_settings(self.settings)

    def add_builtin_picture(self):
        """Add the RETRY picture that comes with the app (AOT:R's Retry button, taken on a 1080p screen)."""
        if self.recording or self.playing:
            return
        try:
            self._add_watch_picture(image_watch.load_image(resource_path(BUILTIN_PICTURE)),
                                    screen_h=BUILTIN_PICTURE_SCREEN_H)
        except Exception as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't add the built-in picture:\n{exc}")

    def _add_watch_picture(self, img, screen_h=None):
        name = f"picture_{int(time.time() * 1000)}.png"
        image_watch.save_image(os.path.join(watch_dir(), name), img)
        self.watch_pictures.append({"img": img, "file": name, "screen_h": screen_h})
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
        if self.recording:
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
            for name, var, low, high in (("watch_wait", self.watch_wait_var, 0, 600),
                                         ("watch_match", self.watch_match_var, 50, 99),
                                         ("watch_end_wait", self.watch_end_var, 0, 3600)):
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

    def _show_picker(self):
        try:
            shot = image_watch.grab_screen()
            with image_watch.mss.mss() as sct:
                mon = image_watch.primary_monitor(sct)
        except Exception as exc:
            self.root.deiconify()
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
            self.root.deiconify()

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
                self._add_watch_picture(shot[top:bottom, left:right].copy(), screen_h=h)
            except Exception as exc:
                messagebox.showerror("Macro Recorder", f"Couldn't use that picture:\n{exc}")

        canvas.bind("<ButtonPress-1>", down)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", up)
        win.bind("<Escape>", lambda e: close())
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

    def _make_matchers(self):
        matchers = []
        for pic in self.watch_pictures:
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
        self.root.after(50, self._process_ui_queue)

    def _call_ui(self, fn):
        """Run fn on the Tk thread (listeners run on their own threads)."""
        self.ui_queue.put(fn)

    # ------------------------------------------------------------ recording

    def toggle_record(self):
        if self.playing:
            return
        if self.recording:
            self.recording = False
            self.paused = False
        else:
            if self.events and not messagebox.askyesno(
                "Macro Recorder", "Start a new recording? The current one will be replaced."
            ):
                return
            self.events = []
            self.current_file = None
            self.macro_screen = (self.screen_w, self.screen_h)  # recorded on this screen
            self._show_made_for()
            self.paused = False
            self.paused_total = 0.0
            self.start_time = time.perf_counter()
            self.recording = True
        self._refresh()

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
        if not self._capturing():
            return
        now = time.perf_counter()
        if now - self.last_move < MOVE_INTERVAL:
            return
        self.last_move = now
        self._add({"type": "move", "x": x, "y": y})

    def _on_click(self, x, y, button, pressed):
        if self._capturing() and not self._on_own_window(x, y):
            self._add({"type": "click", "x": x, "y": y, "button": button.name, "pressed": pressed})

    def _on_scroll(self, x, y, dx, dy):
        if self._capturing() and not self._on_own_window(x, y):
            self._add({"type": "scroll", "x": x, "y": y, "dx": dx, "dy": dy})

    def _hotkey_action(self, key):
        key_id = hotkey_id(key)
        for action, hk in self.hotkeys.items():
            if hk == key_id:
                return action
        return None

    def _on_key_press(self, key):
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

    def _on_key_release(self, key):
        if self._hotkey_action(key) is not None:
            return
        if self._capturing():
            self._add({"type": "key", "key": key_to_data(key), "pressed": False})

    # ------------------------------------------------------------ playback

    def play(self):
        if self.recording or self.playing or not self.events or self.capture_callback is not None:
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
        events = scale_events(self.events, self.macro_screen, play_on)
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
        if image_watch is not None and self.watch_var.get():
            if not self.watch_pictures:
                messagebox.showerror("Macro Recorder", "\"Watch for a picture\" is on, but there's no picture "
                                     "yet. Add one, or untick the box.")
                return
            try:
                watch = {
                    "matchers": self._make_matchers(),
                    "need": self.settings.get("watch_match", 80) / 100.0,
                    "wait": self.settings.get("watch_wait", 3),
                    "end_wait": self.settings.get("watch_end_wait", 60),
                    "click": bool(self.watch_click_var.get()),
                }
            except Exception as exc:
                messagebox.showerror("Macro Recorder", f"Couldn't use the picture:\n{exc}")
                return
        self.stop_play.clear()
        self.playing = True
        self.countdown_left = ready
        self.play_note = ""
        self._refresh()
        threading.Thread(target=self._play_worker,
                         args=(events, repeats, loop, speed, bg, ready, watch),
                         daemon=True).start()

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

    def _click_at(self, x, y):
        """Left-click a spot like a person would: move there, nudge so the game sees the mouse, click."""
        self.mouse_ctrl.position = (x, y)
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
        """Takes screenshots and sets `seen` when the picture shows up.

        It only fires again after the picture has gone away, so a results screen that stays up
        for a while doesn't restart the macro over and over. If the picture is already showing when
        playback starts, it waits for it to go away first."""
        matchers, need = watch["matchers"], watch["need"]
        armed = None
        checks = 0
        try:
            with image_watch.mss.mss() as sct:
                origin = image_watch.screen_origin(sct)
                while not done.is_set():
                    started = time.perf_counter()
                    visible = False
                    # Every check (about once a second) first looks only around the spot where each
                    # picture was found before: a small part of the screen, so it's very light.
                    # The whole screen is searched on every 5th check (or every check while a
                    # picture was never found yet), trying all sizes on every 30th.
                    all_sizes = checks % 30 == 0
                    whole = all_sizes or checks % 5 == 0 or any(m.last_rect is None for m in matchers)
                    checks += 1
                    try:
                        region = None
                        if not whole:  # only take the parts of the screen that are looked at
                            areas = [m.near_last_area() for m in matchers]
                            region = (min(a[0] for a in areas), min(a[1] for a in areas),
                                      max(a[2] for a in areas), max(a[3] for a in areas))
                        screen = self._hide_own_window(image_watch.grab_screen(sct, region), origin)
                        # any one of the pictures counts
                        for m in matchers:
                            score, rect = m.find_near_last(screen, good_enough=need)
                            if score < need and whole:
                                score, rect = m.find(screen, good_enough=need, quick=not all_sizes)
                            if score >= need:
                                visible = True
                                m.picture_entry["seen_rect"] = m.last_rect
                                ox, oy = origin
                                x, y, w, h = rect
                                watch["seen_at"] = (ox + x + w // 2, oy + y + h // 2)  # its middle
                                break
                    except Exception:
                        pass
                    if armed is None:
                        armed = not visible
                    elif visible and armed:
                        armed = False
                        seen.set()
                    elif not visible and whole:
                        armed = True  # gone (the whole screen was checked): it may count again next time
                    # check about once a second; when a check is slow, rest at least as long as it
                    # took, so watching never uses more than about half of one CPU core
                    took = time.perf_counter() - started
                    done.wait(max(0.3, 1.0 - took, took))
        except Exception:
            pass  # screenshots don't work here: playback just goes on without watching

    def _play_worker(self, events, repeats, loop, speed, bg=None, ready=0, watch=None):
        held_keys, held_buttons = set(), set()
        seen = threading.Event()  # the watched-for picture showed up
        watch_done = threading.Event()
        try:
            # "get ready" countdown; Stop cancels it
            for left in range(ready, 0, -1):
                self._set_countdown(left)
                if self.stop_play.wait(1.0):
                    return
            self._set_countdown(0)
            if watch is not None:
                threading.Thread(target=self._watch_worker, args=(watch, seen, watch_done),
                                 daemon=True).start()
            count = 0
            while not self.stop_play.is_set() and (loop or count < repeats):
                if loop or repeats > 1 or watch:
                    total = "" if loop else f" of {repeats}"
                    watching = ", watching for the picture" if watch else ""
                    self._set_note(f"Playing run {count + 1}{total}{watching}...")
                start = self._play_clock()
                for ev in events:
                    target = start + ev["t"] / speed
                    # wait in small steps so Stop (F12) and the picture are noticed quickly
                    while True:
                        if self.stop_play.is_set():
                            return
                        if seen.is_set():
                            break
                        remaining = target - self._play_clock()
                        if remaining <= 0:
                            break
                        time.sleep(min(remaining, 0.02))
                    if seen.is_set():
                        break  # the picture showed up: this run is over
                    if bg is not None:
                        self._replay_event_bg(bg, ev, held_keys)
                    else:
                        self._replay_event(ev, held_keys, held_buttons)
                if watch is not None:
                    self._release_held(bg, held_keys, held_buttons)
                    last_run = not loop and count + 1 >= repeats
                    if not seen.is_set() and watch["end_wait"] > 0 and not last_run:
                        # the macro ended first: give the picture some time to show up
                        deadline = time.perf_counter() + watch["end_wait"]
                        while not seen.is_set():
                            left = deadline - time.perf_counter()
                            if left <= 0:
                                break
                            self._set_note(f"Macro finished, waiting for the picture ({int(left) + 1} s)...")
                            if self.stop_play.wait(min(1.0, left)):
                                return
                            if seen.wait(0):
                                break
                    count += 1
                    if not (loop or count < repeats):
                        break
                    if seen.is_set():
                        seen.clear()
                        self._call_ui(self._picture_seen)
                        if watch["click"] and watch.get("seen_at"):
                            self._set_note("Picture seen! Clicking it...")
                            self._click_at(*watch["seen_at"])
                        for left in range(int(watch["wait"]), 0, -1):
                            self._set_note(f"Picture seen! Starting the macro over in {left}...")
                            if self.stop_play.wait(1.0):
                                return
                        seen.clear()  # ignore it if it flickered during the wait
                    continue
                count += 1
        finally:
            watch_done.set()
            # never leave a key or mouse button stuck down
            self._release_held(bg, held_keys, held_buttons)
            self._call_ui(self._playback_done)

    def _replay_event(self, ev, held_keys, held_buttons):
        kind = ev["type"]
        if kind == "move":
            self.mouse_ctrl.position = (ev["x"], ev["y"])
        elif kind == "move_rel":
            move_relative(self.mouse_ctrl, ev["dx"], ev["dy"], held_buttons)
        elif kind == "click":
            button = button_from_name(ev["button"])
            if "x" in ev:
                self.mouse_ctrl.position = (ev["x"], ev["y"])
            if ev["pressed"]:
                self.mouse_ctrl.press(button)
                held_buttons.add(button)
            else:
                self.mouse_ctrl.release(button)
                held_buttons.discard(button)
        elif kind == "scroll":
            if "x" in ev:
                self.mouse_ctrl.position = (ev["x"], ev["y"])
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
        if kind == "move_rel":
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

    def _play_clock(self):
        """The clock playback follows (the new window stops it while playback is paused)."""
        return time.perf_counter()

    def _playback_done(self):
        self.playing = False
        self.countdown_left = 0
        self.play_note = ""
        self._refresh()

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
            json.dump(data, f, indent=1)
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
        try:
            events, screen = self._read_own_file(path)
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
        self.events = events
        self.current_file = path
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

    @staticmethod
    def _read_own_file(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("format") == "luvmacro":
            raise ValueError("a luvmacro file")
        events = data["events"]
        if not isinstance(events, list):
            raise ValueError("this isn't a macro file")
        return events, data.get("screen", {})

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
            self.current_file = None
            self.macro_screen = None
            self._show_made_for()
            self._refresh()

    def _on_close(self):
        self._save_settings()
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
