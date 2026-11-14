"""Open macros saved by other macro recorder programs.

Each importer turns a file into this app's own list of events:
    {"t": seconds, "type": "move" | "move_rel" | "click" | "scroll" | "key", ...}

Supported:
    .luvmacro   luvmacro recordings (JSON)
    .rec        TinyTask recordings
    .mcr        Macro Recorder by Jitbit (text macros)
    .ahk        simple AutoHotkey scripts (Send, Sleep, Click, MouseMove, MouseClick, Loop)
"""

import json
import os
import re
import struct
import sys


class ImportError_(Exception):
    """Raised with a message that can be shown to the user as is."""


class Imported:
    def __init__(self, source, events, screen=None):
        self.source = source      # name of the program the file came from
        self.events = events
        self.screen = screen      # (width, height) the macro was recorded on, if known
        self.program = None       # {"exe", "title", "client": [x, y, w, h]} if known
        self.skipped = 0          # lines or steps that couldn't be converted
        self.notes = []           # short sentences for the user


# ---------------------------------------------------------------- key names

_VK_NAMES = {
    # shared names (AutoHotkey, Jitbit / .NET, pynput)
    "enter": 0x0D, "return": 0x0D, "space": 0x20, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "backspace": 0x08, "bs": 0x08, "back": 0x08, "delete": 0x2E, "del": 0x2E,
    "insert": 0x2D, "ins": 0x2D, "home": 0x24, "end": 0x23,
    "pgup": 0x21, "pageup": 0x21, "prior": 0x21, "page_up": 0x21,
    "pgdn": 0x22, "pagedown": 0x22, "next": 0x22, "page_down": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "shift": 0x10, "shiftkey": 0x10, "lshift": 0xA0, "lshiftkey": 0xA0, "shiftleft": 0xA0, "shift_l": 0xA0,
    "rshift": 0xA1, "rshiftkey": 0xA1, "shiftright": 0xA1, "shift_r": 0xA1,
    "ctrl": 0x11, "control": 0x11, "controlkey": 0x11, "lctrl": 0xA2, "lcontrolkey": 0xA2,
    "controlleft": 0xA2, "ctrl_l": 0xA2, "rctrl": 0xA3, "rcontrolkey": 0xA3, "controlright": 0xA3, "ctrl_r": 0xA3,
    "alt": 0x12, "menu": 0x12, "lalt": 0xA4, "lmenu": 0xA4, "altleft": 0xA4, "alt_l": 0xA4,
    "ralt": 0xA5, "rmenu": 0xA5, "altright": 0xA5, "alt_r": 0xA5, "alt_gr": 0xA5,
    "lwin": 0x5B, "cmd": 0x5B, "cmd_l": 0x5B, "rwin": 0x5C, "cmd_r": 0x5C,
    "capslock": 0x14, "capital": 0x14, "caps_lock": 0x14, "numlock": 0x90, "num_lock": 0x90,
    "scrolllock": 0x91, "scroll": 0x91, "scroll_lock": 0x91, "printscreen": 0x2C, "print_screen": 0x2C,
    "snapshot": 0x2C, "pause": 0x13, "appskey": 0x5D, "apps": 0x5D, "menu_key": 0x5D,
    "numpadenter": 0x0D, "numpadadd": 0x6B, "add": 0x6B, "numpadsub": 0x6D, "subtract": 0x6D,
    "numpadmult": 0x6A, "multiply": 0x6A, "numpaddiv": 0x6F, "divide": 0x6F,
    "numpaddot": 0x6E, "decimal": 0x6E,
    "oemcomma": 0xBC, "oemperiod": 0xBE, "oemminus": 0xBD, "oemplus": 0xBB, "oemquestion": 0xBF,
    "oem2": 0xBF, "oemtilde": 0xC0, "oem3": 0xC0, "oemopenbrackets": 0xDB, "oem4": 0xDB,
    "oemclosebrackets": 0xDD, "oem6": 0xDD, "oempipe": 0xDC, "oem5": 0xDC,
    "oemquotes": 0xDE, "oem7": 0xDE, "oemsemicolon": 0xBA, "oem1": 0xBA,
}
for _i in range(1, 25):
    _VK_NAMES[f"f{_i}"] = 0x6F + _i
for _i in range(10):
    _VK_NAMES[f"numpad{_i}"] = 0x60 + _i
    _VK_NAMES[f"d{_i}"] = 0x30 + _i      # .NET names for the number row

_MOUSE_NAMES = {"lbutton": "left", "rbutton": "right", "mbutton": "middle",
                "xbutton1": "x1", "xbutton2": "x2"}

SHIFT_VK = 0xA0


def char_to_vk(ch):
    """(vk, needs_shift) for a typed character, or (None, False)."""
    if sys.platform == "win32":
        import ctypes

        scan = ctypes.windll.user32.VkKeyScanW
        scan.argtypes, scan.restype = [ctypes.c_wchar], ctypes.c_short
        code = scan(ch)
        if code != -1:
            return code & 0xFF, bool(code & 0x100)
    if ch.isascii() and ch.isalnum():
        return ord(ch.upper()), ch.isupper()
    if ch == " ":
        return 0x20, False
    return None, False


def name_to_vk(name):
    """VK code for a key name such as 'Enter', 'LShiftKey', 'a' or 'D5'; None if unknown."""
    n = name.strip()
    if len(n) == 1:
        return char_to_vk(n)[0]
    low = n.lower().replace(" ", "")
    if low in _VK_NAMES:
        return _VK_NAMES[low]
    m = re.fullmatch(r"(?:vk)?([0-9a-f]{2})(?:sc[0-9a-f]+)?", low)
    if low.startswith("vk") and m:
        return int(m.group(1), 16)
    m = re.fullmatch(r"<(\d+)>", low)  # pynput's "<65>" form
    if m:
        return int(m.group(1))
    return None


def key_event(t, vk, pressed):
    return {"t": round(t, 4), "type": "key", "key": {"vk": vk}, "pressed": pressed}


# ---------------------------------------------------------------- luvmacro

def _luv_key(name):
    """Turn a luvmacro key name (pynput style: 'space', 'ctrl_l', 'a') into our key data."""
    try:
        from pynput import keyboard

        if name in keyboard.Key.__members__:
            return {"special": name}
    except Exception:
        pass
    if len(name) == 1:
        vk, _ = char_to_vk(name)
        data = {"char": name}
        if vk is not None:
            data["vk"] = vk
        return data
    vk = name_to_vk(name)
    return {"vk": vk} if vk is not None else None


def import_luvmacro(text):
    data = json.loads(text)
    workflow = data.get("workflow", data)
    steps = workflow.get("steps")
    if steps is None and "events" in workflow:
        steps = [{"kind": "recorded_input", "events": workflow["events"]}]
    if not isinstance(steps, list):
        raise ImportError_("This .luvmacro file has no recorded steps in it.")

    result = Imported("luvmacro", [])
    events = result.events
    offset = 0.0  # each step starts where the previous one ended
    for step in steps:
        if not isinstance(step, dict):
            result.skipped += 1
            continue
        step_events = step.get("events")
        if isinstance(step_events, list):
            last = 0.0
            for ev in step_events:
                last = max(last, float(ev.get("t", 0)))
                conv = _convert_luv_event(ev, offset)
                if conv is None:
                    result.skipped += 1
                else:
                    events.append(conv)
            offset += last
            continue
        wait = _step_wait_seconds(step)
        if wait is not None:
            offset += wait
        else:
            result.skipped += 1

    platform = data.get("workflow", {}).get("environment", {}).get("recording", {}).get("platform", {})
    window = platform.get("window") or {}
    if window.get("width") and window.get("height"):
        result.screen = (window["width"], window["height"])
        if isinstance(window.get("x"), int) and isinstance(window.get("y"), int):
            # where the game window's inside was on the screen (for "Fit to the game window")
            result.program = {"client": [window["x"], window["y"], window["width"], window["height"]]}
    return result


def _step_wait_seconds(step):
    for key, factor in (("seconds", 1), ("duration", 1), ("delay", 1), ("ms", 0.001), ("milliseconds", 0.001)):
        if isinstance(step.get(key), (int, float)):
            return step[key] * factor
    return None


def _convert_luv_event(ev, offset):
    t = round(offset + float(ev.get("t", 0)), 4)
    kind = ev.get("type")
    if kind == "mouse_move":
        return {"t": t, "type": "move", "x": ev["x"], "y": ev["y"]}
    if kind == "mouse_delta":
        return {"t": t, "type": "move_rel", "dx": ev.get("dx", 0), "dy": ev.get("dy", 0)}
    if kind in ("mouse_down", "mouse_up"):
        out = {"t": t, "type": "click", "button": ev.get("button", "left"), "pressed": kind == "mouse_down"}
        if "x" in ev and "y" in ev:
            out["x"], out["y"] = ev["x"], ev["y"]
        return out
    if kind == "mouse_scroll":
        out = {"t": t, "type": "scroll", "dx": _notches(ev.get("dx", 0)), "dy": _notches(ev.get("dy", 0))}
        if "x" in ev and "y" in ev:
            out["x"], out["y"] = ev["x"], ev["y"]
        return out
    if kind in ("key_down", "key_up"):
        key = _luv_key(str(ev.get("key", "")))
        if key is None:
            return None
        return {"t": t, "type": "key", "key": key, "pressed": kind == "key_down"}
    return None


def _notches(value):
    """Wheel amounts may be in Windows units (120 per notch) or in notches already."""
    if abs(value) >= 120:
        return round(value / 120)
    return value


# ---------------------------------------------------------------- TinyTask

_WM = {
    0x0200: ("move", None, None),
    0x0201: ("click", "left", True), 0x0202: ("click", "left", False),
    0x0204: ("click", "right", True), 0x0205: ("click", "right", False),
    0x0207: ("click", "middle", True), 0x0208: ("click", "middle", False),
    0x020A: ("scroll", None, None),
    0x0100: ("key", None, True), 0x0101: ("key", None, False),
    0x0104: ("key", None, True), 0x0105: ("key", None, False),
}


def import_tinytask(raw):
    """TinyTask saves the Windows journal-record EVENTMSG structs as they are, 20 bytes each."""
    size = 20
    if len(raw) < size or len(raw) % size:
        raise ImportError_("This doesn't look like a TinyTask recording.")
    records = [struct.unpack_from("<IIIII", raw, i) for i in range(0, len(raw), size)]
    known = sum(1 for r in records if r[0] in _WM)
    if known < len(records) * 0.9:
        raise ImportError_("This doesn't look like a TinyTask recording.")

    result = Imported("TinyTask", [])
    start = records[0][3]
    for message, param_l, param_h, tick, hwnd in records:
        info = _WM.get(message)
        if info is None:
            result.skipped += 1
            continue
        t = ((tick - start) & 0xFFFFFFFF) / 1000.0
        kind, button, pressed = info
        x, y = _signed16(param_l), _signed16(param_h)
        if kind == "move":
            result.events.append({"t": t, "type": "move", "x": x, "y": y})
        elif kind == "click":
            result.events.append({"t": t, "type": "click", "x": x, "y": y, "button": button, "pressed": pressed})
        elif kind == "scroll":
            delta = _signed16(hwnd >> 16) if hwnd >> 16 else 0
            notches = round(delta / 120) if delta else -1
            result.events.append({"t": t, "type": "scroll", "x": x, "y": y, "dx": 0, "dy": notches})
        else:
            result.events.append(key_event(t, param_l & 0xFF, pressed))
    return result


def _signed16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


# ---------------------------------------------------------------- Jitbit Macro Recorder

def import_jitbit(text):
    result = Imported("Macro Recorder (Jitbit)", [])
    events = result.events
    t = 0.0
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(":")]
        head = parts[0].upper() if parts else ""
        if not line.strip():
            continue
        try:
            if head == "DELAY":
                t += float(parts[1]) / 1000.0
            elif head == "KEYBOARD":
                vk = name_to_vk(parts[1])
                action = parts[2].lower()
                if vk is None:
                    result.skipped += 1
                elif action == "keydown":
                    events.append(key_event(t, vk, True))
                elif action == "keyup":
                    events.append(key_event(t, vk, False))
                else:  # KeyPress
                    events.append(key_event(t, vk, True))
                    t += 0.01
                    events.append(key_event(t, vk, False))
            elif head == "MOUSE":
                x, y, action = int(parts[1]), int(parts[2]), parts[3].lower()
                extra = int(parts[4]) if len(parts) > 4 and parts[4].lstrip("-").isdigit() else 0
                _jitbit_mouse(events, t, x, y, action, extra, result)
            else:
                result.skipped += 1
        except (IndexError, ValueError):
            result.skipped += 1
    return result


def _jitbit_mouse(events, t, x, y, action, extra, result):
    if action == "move":
        events.append({"t": t, "type": "move", "x": x, "y": y})
        return
    if "wheel" in action:
        notches = round(extra / 120) if abs(extra) >= 120 else (extra or -1)
        events.append({"t": t, "type": "scroll", "x": x, "y": y, "dx": 0, "dy": notches})
        return
    button = next((b for b in ("left", "right", "middle") if b in action), None)
    if button is None:
        result.skipped += 1
        return
    if action.endswith("down"):
        presses = [True]
    elif action.endswith("up"):
        presses = [False]
    elif "double" in action:
        presses = [True, False, True, False]
    else:
        presses = [True, False]
    for i, p in enumerate(presses):
        events.append({"t": round(t + i * 0.01, 4), "type": "click", "x": x, "y": y, "button": button, "pressed": p})


# ---------------------------------------------------------------- AutoHotkey

AHK_STEP = 0.01      # AutoHotkey's default key and mouse delay
MAX_EVENTS = 200000  # stop expanding loops after this many actions


class _AhkConverter:
    def __init__(self):
        self.result = Imported("AutoHotkey", [])
        self.t = 0.0
        self.pos = None
        self.stopped = False
        self.vars = {}  # number variables (x := 100, Random, ...)
        self.key_step = AHK_STEP  # SetKeyDelay
        self.mouse_step = AHK_STEP  # SetMouseDelay

    def note(self, text):
        if text not in self.result.notes:
            self.result.notes.append(text)

    def emit(self, ev):
        ev["t"] = round(self.t, 4)
        self.result.events.append(ev)
        self.t += self.key_step if ev["type"] == "key" else self.mouse_step
        if len(self.result.events) > MAX_EVENTS:
            raise ImportError_("This script makes too many actions to convert (it may loop too often).")

    def key(self, vk, pressed):
        self.emit({"type": "key", "key": {"vk": vk}, "pressed": pressed})

    def click(self, button, pressed, x=None, y=None):
        if x is not None:
            self.pos = (x, y)
        ev = {"type": "click", "button": button, "pressed": pressed}
        if self.pos:
            ev["x"], ev["y"] = self.pos
        self.emit(ev)

    def move(self, x, y, relative=False):
        if relative:
            if self.pos is None:
                self.emit({"type": "move_rel", "dx": x, "dy": y})
                return
            x, y = self.pos[0] + x, self.pos[1] + y
        self.pos = (x, y)
        self.emit({"type": "move", "x": x, "y": y})

    def scroll(self, dx, dy):
        ev = {"type": "scroll", "dx": dx, "dy": dy}
        if self.pos:
            ev["x"], ev["y"] = self.pos
        self.emit(ev)


def import_ahk(text):
    lines = _ahk_clean_lines(text)
    conv = _AhkConverter()
    block, _ = _ahk_parse_block(lines, 0)
    _ahk_run(block, conv)
    if not conv.result.events:
        raise ImportError_("No actions found in this AutoHotkey script. Only simple scripts made of Send, "
                           "Sleep, Click, MouseMove and MouseClick lines can be opened.")
    return conv.result


def _ahk_clean_lines(text):
    out, in_comment = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if in_comment:
            if line.startswith("*/"):
                in_comment = False
            continue
        if line.startswith("/*"):
            in_comment = True
            continue
        line = re.sub(r"(^|\s);.*$", "", line).strip()  # ; comments
        if line:
            out.append(line)
    return out


def _ahk_parse_block(lines, i):
    """Return (statements, next index). A statement is ('line', text) or ('loop', count, body)."""
    stmts = []
    while i < len(lines):
        line = lines[i]
        if line == "}":
            return stmts, i + 1
        m = re.match(r"^loop\b[\s,(]*([%\w\s+*/-]*?)\s*\)?\s*(\{?)\s*$", line, re.I)
        if m and not re.match(r"^loop\s*,?\s*(files|parse|read|reg)\b", line, re.I):
            count = m.group(1).strip() or None
            i += 1
            if not m.group(2):
                if i < len(lines) and lines[i] == "{":
                    i += 1
                else:  # one-line loop body
                    body, _ = ([("line", lines[i])], None) if i < len(lines) else ([], None)
                    stmts.append(("loop", count, body))
                    i += 1
                    continue
            body, i = _ahk_parse_block(lines, i)
            stmts.append(("loop", count, body))
            continue
        if line.endswith("{") and line != "{":
            # if / while / hotkey with a block: keep the block's actions, note the condition is ignored
            stmts.append(("line", line[:-1].strip()))
            body, i = _ahk_parse_block(lines, i + 1)
            stmts.append(("block", body))
            continue
        if line == "{":
            body, i = _ahk_parse_block(lines, i + 1)
            stmts.append(("block", body))
            continue
        stmts.append(("line", line))
        i += 1
    return stmts, i


def _ahk_run(stmts, conv):
    for stmt in stmts:
        if conv.stopped:
            return
        if stmt[0] == "loop":
            count = stmt[1]
            if count is None:
                count = 1
                conv.note("A \"Loop\" without a count was played once. Turn on Repeat continuously to keep "
                          "it going.")
            else:
                value = _ahk_number(count, conv)
                if value is None:
                    count = 1
                    conv.note("A \"Loop\" count couldn't be worked out, so it was played once.")
                else:
                    count = max(0, int(value))
            for _ in range(count):
                _ahk_run(stmt[2], conv)
        elif stmt[0] == "block":
            _ahk_run(stmt[1], conv)
        else:
            _ahk_line(stmt[1], conv)


_IGNORED = {"#noenv", "#singleinstance", "#persistent", "#warn", "#requires", "#maxthreadsperhotkey",
            "#include", "#ifwinactive", "#hotif", "sendmode", "setkeydelay", "setmousedelay",
            "setdefaultmousespeed", "coordmode", "setworkingdir", "setbatchlines", "setwindelay",
            "setcontroldelay", "settitlematchmode", "detecthiddenwindows", "processsetpriority",
            "process", "winactivate", "winwaitactive", "tooltip", "soundbeep", "critical", "keywait",
            "global", "local", "static", "#hotkeyinterval", "#maxhotkeysperinterval", "listlines",
            "setcapslockstate", "setnumlockstate", "setscrolllockstate", "blockinput", "traytip", "menu",
            "a_traymenu", "persistent", "settimer", "pause", "suspend", "reload", "msgbox",
            "winwait", "winmaximize", "winrestore", "winminimize", "run", "fileappend", "outputdebug"}
_CONDITIONS = ("if", "else", "while", "imagesearch", "pixelsearch", "pixelgetcolor", "ifwinactive",
               "ifwinexist", "getkeystate", "until", "for", "try", "catch", "switch", "case")


def _ahk_line(line, conv):
    res = conv.result
    if re.match(r"^[^\s,]+::", line):  # hotkey label, maybe with an action after it
        after = line.split("::", 1)[1].strip()
        if after and after.lower() not in ("return",):
            if conv.result.events:
                conv.stopped = True  # a second hotkey: the first macro is complete
            return
        if conv.result.events:
            conv.stopped = True
        return
    if re.match(r"^\w+:$", line):  # label
        return

    if _ahk_assign(line, conv):
        return
    m = re.match(r"^([#\w]+)\s*\((.*)\)\s*$", line)  # v2 call: Send("x")
    if m:
        cmd, args = m.group(1), m.group(2)
    else:
        m = re.match(r"^([#\w]+)\s*(?:,\s*|\s+|$)(.*)$", line)
        if not m:
            res.skipped += 1
            return
        cmd, args = m.group(1), m.group(2)
    low = cmd.lower()
    args = args.strip()

    if low in ("return", "exitapp"):
        if conv.result.events:
            conv.stopped = True
        return
    if low in ("setkeydelay", "setmousedelay"):
        delay = _ahk_number(_split_args(args)[0] if args else "", conv)
        if delay is not None:
            step = max(0.0, delay / 1000.0) if delay >= 0 else 0.0
            if low == "setkeydelay":
                conv.key_step = step
            else:
                conv.mouse_step = step
        return
    if low == "random":
        a = _split_args(args)
        lo, hi = (_ahk_number(a[1], conv) if len(a) > 1 else 0), (_ahk_number(a[2], conv) if len(a) > 2 else 0)
        if a and a[0]:
            conv.vars[a[0].lower()] = ((lo or 0) + (hi or 0)) / 2
            conv.note("Random numbers were set to the middle of their range.")
        return
    if low == "dllcall" and "mouse_event" in args.lower():
        nums = [v for v in re.findall(r"-?\d+|\w+", args.split("mouse_event", 1)[1])
                if not re.fullmatch(r"(?i)u?int|uptr|ptr|int64|short", v)]
        vals = [_ahk_number(v, conv) for v in nums]
        if len(vals) >= 3 and vals[0] == 1 and vals[1] is not None and vals[2] is not None:
            conv.emit({"type": "move_rel", "dx": int(vals[1]), "dy": int(vals[2])})
        else:
            res.skipped += 1
        return
    if low in _CONDITIONS:
        conv.note("Conditions (if, while, ImageSearch, PixelSearch, ...) can't be converted: the actions "
                  "inside them play every time. Picture watch can do some of what ImageSearch does.")
        return
    if low in _IGNORED or low.startswith("#"):
        if low in ("settimer", "msgbox", "run"):
            conv.note(f"{cmd} lines were left out.")
        return
    if low == "sleep":
        delay = _ahk_number(args, conv)
        if delay is None:
            res.skipped += 1
        else:
            conv.t += max(0.0, delay) / 1000.0
        return
    if low in ("controlsend", "controlclick"):
        conv.note("ControlSend / ControlClick were played as normal keys and clicks (to the window in front).")
        a = _split_args(args)
        if low == "controlsend":
            _ahk_send(a[1] if len(a) > 1 else a[0], conv)
        else:
            _ahk_click(" ".join(x for x in a[1:2] if x) or "", conv)
        return
    args = _ahk_expand(args, conv)
    if low in ("send", "sendinput", "sendevent", "sendplay", "sendraw", "sendtext"):
        _ahk_send(_unquote(args), conv, raw=low in ("sendraw", "sendtext"))
        return
    if low == "click":
        _ahk_click(_unquote(args), conv)
        return
    if low == "mousemove":
        a = _split_args(args)
        try:
            conv.move(int(float(a[0])), int(float(a[1])), relative=len(a) > 3 and a[3].lower() == "r")
        except (IndexError, ValueError):
            res.skipped += 1
        return
    if low == "mouseclick":
        _ahk_mouseclick(_split_args(args), conv)
        return
    if low in ("mouseclickdrag",):
        a = _split_args(args)
        try:
            button = _button_name(a[0] or "left")
            x1, y1, x2, y2 = (int(float(v)) for v in a[1:5])
            conv.move(x1, y1)
            conv.click(button, True, x1, y1)
            conv.move(x2, y2)
            conv.click(button, False, x2, y2)
        except (IndexError, ValueError):
            res.skipped += 1
        return
    res.skipped += 1


def _ahk_number(text, conv):
    """A number from a literal, a variable or a simple sum like (x + 50) * 2; None if it isn't one."""
    t = str(text).strip()
    if t.startswith("% "):
        t = t[2:]
    t = re.sub(r"%(\w+)%", lambda m: str(conv.vars.get(m.group(1).lower(), m.group(0))), t)
    t = _unquote(t)

    def var(m):
        name = m.group(0).lower()
        return str(conv.vars[name]) if name in conv.vars else m.group(0)
    t = re.sub(r"[A-Za-z_]\w*", var, t)
    if not re.fullmatch(r"[\d\s.+\-*/()]+", t) or not re.search(r"\d", t):
        return None
    try:
        return _arith(t)
    except Exception:
        return None


def _arith(text):
    """Works out a sum like (12 + 3) * 2 / 5 (numbers, + - * / and brackets only; no ** powers)."""
    import ast
    import operator
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](ev(node.left), ev(node.right))
        raise ValueError("not a simple sum")
    return ev(ast.parse(text, mode="eval"))


def _ahk_assign(line, conv):
    """x := 100, x = 100 (old style), x += 5, x -= 5, x := Random(1, 9). True if it was one."""
    m = re.match(r"^([A-Za-z_]\w*)\s*(:=|=|\+=|-=|\*=)\s*(.*)$", line)
    if not m or m.group(1).lower() in ("send", "sleep", "click", "loop"):
        return False
    name, op, expr = m.group(1).lower(), m.group(2), m.group(3).strip()
    r = re.match(r"(?i)^random\s*\(\s*([^,]*),\s*([^)]*)\)$", expr)
    if r:
        lo, hi = _ahk_number(r.group(1), conv), _ahk_number(r.group(2), conv)
        value = ((lo or 0) + (hi or 0)) / 2
        conv.note("Random numbers were set to the middle of their range.")
    else:
        value = _ahk_number(expr, conv)
    if value is None:
        conv.vars.pop(name, None)  # text or something else: not a number this converter can use
        return True
    old = conv.vars.get(name, 0)
    conv.vars[name] = {"+=": old + value, "-=": old - value, "*=": old * value}.get(op, value)
    return True


def _ahk_expand(args, conv):
    """Put the values of %variables% (and "% expression" arguments) into a command's arguments."""
    args = re.sub(r"%(\w+)%", lambda m: _num_text(conv.vars.get(m.group(1).lower()), m.group(0)), args)
    parts = []
    for part in args.split(","):
        st = part.strip()
        if st.startswith("% ") or (re.fullmatch(r"[A-Za-z_]\w*(\s*[-+*/]\s*[\w.]+)*", st) and
                                   st.split()[0].lower() in conv.vars):
            value = _ahk_number(st, conv)
            if value is not None:
                part = _num_text(value, part)
        parts.append(part)
    return ",".join(parts)


def _num_text(value, fallback):
    if value is None:
        return fallback
    return str(int(value)) if float(value).is_integer() else str(value)


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def _split_args(args):
    return [_unquote(a) for a in args.split(",")]


def _button_name(word):
    w = word.strip().lower()
    return {"l": "left", "left": "left", "r": "right", "right": "right", "m": "middle", "middle": "middle",
            "x1": "x1", "x2": "x2", "wu": "wheelup", "wheelup": "wheelup", "wd": "wheeldown",
            "wheeldown": "wheeldown", "wl": "wheelleft", "wheelleft": "wheelleft", "wr": "wheelright",
            "wheelright": "wheelright"}.get(w)


def _do_clicks(conv, button, count, down_up, x=None, y=None, relative=False):
    if x is not None:
        conv.move(x, y, relative=relative)
    if button.startswith("wheel"):
        step = {"wheelup": (0, 1), "wheeldown": (0, -1), "wheelleft": (-1, 0), "wheelright": (1, 0)}[button]
        for _ in range(max(count, 1)):
            conv.scroll(*step)
        return
    if count == 0 and down_up is None:
        return
    for _ in range(max(count, 1)):
        if down_up in (None, "down"):
            conv.click(button, True)
        if down_up in (None, "up"):
            conv.click(button, False)


def _ahk_click(args, conv):
    tokens = [t for t in re.split(r"[\s,]+", args) if t]
    numbers, button, down_up, relative = [], "left", None, False
    for tok in tokens:
        low = tok.lower()
        if re.fullmatch(r"-?\d+(\.\d+)?", tok):
            numbers.append(int(float(tok)))
        elif _button_name(low):
            button = _button_name(low)
        elif low in ("down", "d"):
            down_up = "down"
        elif low in ("up", "u"):
            down_up = "up"
        elif low in ("rel", "relative"):
            relative = True
    x = y = None
    count = 1
    if len(numbers) >= 2:
        x, y = numbers[0], numbers[1]
        if len(numbers) >= 3:
            count = numbers[2]
    elif len(numbers) == 1:
        count = numbers[0]
    _do_clicks(conv, button, count, down_up, x, y, relative)


def _ahk_mouseclick(a, conv):
    try:
        button = _button_name(a[0] or "left") if a and a[0] else "left"
        x = int(float(a[1])) if len(a) > 1 and a[1] else None
        y = int(float(a[2])) if len(a) > 2 and a[2] else None
        count = int(a[3]) if len(a) > 3 and a[3] else 1
        flag = a[5].lower() if len(a) > 5 else ""
        relative = len(a) > 6 and a[6].lower() == "r"
    except ValueError:
        conv.result.skipped += 1
        return
    down_up = "down" if flag == "d" else "up" if flag == "u" else None
    _do_clicks(conv, button or "left", count, down_up, x if y is not None else None, y, relative)


_MODIFIERS = {"^": 0xA2, "!": 0xA4, "+": 0xA0, "#": 0x5B}


def _ahk_send(text, conv, raw=False):
    if text.lower().startswith("{blind}"):
        text = text[7:]
    if text.lower().startswith("{raw}") or text.lower().startswith("{text}"):
        raw = True
        text = text.split("}", 1)[1]
    i = 0
    mods = []
    while i < len(text):
        ch = text[i]
        if not raw and ch in _MODIFIERS and i + 1 < len(text):
            mods.append(_MODIFIERS[ch])
            i += 1
            continue
        if not raw and ch == "{":
            end = text.find("}", i + 2)
            if end == -1:
                end = len(text)
            inner = text[i + 1:end]
            i = end + 1
            _ahk_send_braced(inner, conv, mods)
            mods = []
            continue
        i += 1
        _type_char(ch, conv, mods)
        mods = []


def _press_with_mods(conv, vk, mods, shift=False, count=1):
    held = list(mods) + ([SHIFT_VK] if shift and SHIFT_VK not in mods else [])
    for m in held:
        conv.key(m, True)
    for _ in range(count):
        conv.key(vk, True)
        conv.key(vk, False)
    for m in reversed(held):
        conv.key(m, False)


def _type_char(ch, conv, mods):
    if ch in "\r":
        return
    if ch == "\n":
        ch = "\r"
    vk, shift = char_to_vk(ch) if ch != "\r" else (0x0D, False)
    if vk is None:
        conv.result.skipped += 1
        return
    _press_with_mods(conv, vk, mods, shift)


def _ahk_send_braced(inner, conv, mods):
    parts = inner.split()
    if not parts:
        return
    if len(inner) == 1 or inner in ("{", "}"):  # {!}, {{}
        _type_char(inner[0], conv, mods)
        return
    name = parts[0]
    if name.lower() == "click":
        _ahk_click(" ".join(parts[1:]), conv)
        return
    arg = parts[1].lower() if len(parts) > 1 else ""
    button = _MOUSE_NAMES.get(name.lower())
    if button:
        if arg in ("down", "up"):
            conv.click(button, arg == "down")
        else:
            conv.click(button, True)
            conv.click(button, False)
        return
    if name.lower() in ("wheelup", "wheeldown", "wheelleft", "wheelright"):
        _do_clicks(conv, name.lower(), int(arg) if arg.isdigit() else 1, None)
        return
    vk = name_to_vk(name)
    shift = False
    if len(name) == 1:
        vk, shift = char_to_vk(name)
    if vk is None:
        conv.result.skipped += 1
        return
    if arg == "down" or arg == "downtemp":
        conv.key(vk, True)
    elif arg == "up":
        conv.key(vk, False)
    else:
        _press_with_mods(conv, vk, mods, shift, int(arg) if arg.isdigit() else 1)


# ---------------------------------------------------------------- entry point

IMPORT_EXTS = (".luvmacro", ".rec", ".mcr", ".ahk")


def import_file(path):
    """Read a macro saved by another program. Raises ImportError_ with a friendly message."""
    ext = os.path.splitext(path)[1].lower()
    with open(path, "rb") as f:
        raw = f.read()

    if ext == ".exe":
        raise ImportError_("This is a program, not a macro file. Macros that TinyTask or other recorders "
                           "turned into .exe files can't be opened. Ask for the original .rec file instead.")
    if ext == ".pmc":
        raise ImportError_("Pulover's Macro Creator files (.pmc) can't be opened directly. In Pulover's "
                           "Macro Creator, choose File > Export to AHK, then open the .ahk file here.")
    if ext == ".rec":
        return import_tinytask(raw)

    text = _decode(raw)
    if text is None:
        if len(raw) % 20 == 0:
            return import_tinytask(raw)
        raise ImportError_("This file isn't a macro format this app knows.")

    stripped = text.lstrip()
    if ext == ".luvmacro" or (stripped.startswith("{") and '"luvmacro"' in stripped[:200]):
        try:
            return import_luvmacro(text)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ImportError_(f"This .luvmacro file looks damaged ({exc}).")
    if ext in (".ahk", ".ah2"):
        return import_ahk(text)
    if ext == ".mcr" or re.search(r"^\s*(DELAY\s*:\s*\d|Keyboard\s*:|Mouse\s*:)", text, re.M | re.I):
        return import_jitbit(text)
    if ext in (".ahk", ".ah2", ".txt") or re.search(r"^\s*(Send\w*|Sleep|Click|MouseMove|MouseClick)\b", text, re.M | re.I):
        return import_ahk(text)
    raise ImportError_("This file isn't a macro format this app knows.")


def _decode(raw):
    for enc in ("utf-8-sig", "utf-16"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if "\x00" not in text:
            return text
    return None


# ---------------------------------------------------------------- saving as AutoHotkey

def export_ahk(events, name="macro"):
    """An AutoHotkey v2 script that plays the macro once (Esc stops it). Times are kept with Sleep."""
    lines = [
        f"; {name}: made with Macro Recorder. Needs AutoHotkey v2 (autohotkey.com).",
        "; Run it to play the macro once. Esc stops it.",
        "#Requires AutoHotkey v2.0",
        "#SingleInstance Force",
        'SendMode "Event"',
        "SetKeyDelay -1, -1",
        "SetMouseDelay -1",
        'CoordMode "Mouse", "Screen"',
        "",
    ]
    last = 0.0
    names = {"left": "Left", "right": "Right", "middle": "Middle", "x1": "X1", "x2": "X2"}
    for ev in events:
        gap = int(round((ev.get("t", last) - last) * 1000))
        if gap > 0:
            lines.append(f"Sleep {gap}")
        last = ev.get("t", last)
        kind = ev.get("type")
        if kind == "move":
            lines.append(f"MouseMove {ev['x']}, {ev['y']}, 0")
        elif kind == "move_rel":
            lines.append(f'DllCall("mouse_event", "UInt", 1, "Int", {int(ev["dx"])}, "Int", {int(ev["dy"])}, '
                         '"UInt", 0, "UPtr", 0)')
        elif kind == "click":
            where = f"{ev['x']} {ev['y']} " if "x" in ev else ""
            lines.append(f'Click "{where}{names.get(ev["button"], "Left")} {"Down" if ev["pressed"] else "Up"}"')
        elif kind == "scroll":
            where = f"{ev['x']} {ev['y']} " if "x" in ev else ""
            dy, dx = int(ev.get("dy", 0)), int(ev.get("dx", 0))
            if dy:
                lines.append(f'Click "{where}{"WheelUp" if dy > 0 else "WheelDown"} {abs(dy)}"')
            if dx:
                lines.append(f'Click "{where}{"WheelRight" if dx > 0 else "WheelLeft"} {abs(dx)}"')
        elif kind == "key":
            vk = _export_vk(ev.get("key", {}))
            if vk is None:
                lines.append("; (a key that has no Windows key code was left out)")
            else:
                lines.append(f'Send "{{vk{vk:02X} {"down" if ev["pressed"] else "up"}}}"')
        elif kind == "wait_picture":
            lines.append("; (a \"Wait for a picture\" step was left out: AutoHotkey can't do it this way)")
    lines += ["ExitApp", "", "Esc::ExitApp", ""]
    return "\r\n".join(lines)


def _export_vk(key):
    if "vk" in key:
        return int(key["vk"])
    special = key.get("special")
    if special:
        names = {"shift": 0xA0, "shift_l": 0xA0, "shift_r": 0xA1, "ctrl": 0xA2, "ctrl_l": 0xA2, "ctrl_r": 0xA3,
                 "alt": 0xA4, "alt_l": 0xA4, "alt_r": 0xA5, "alt_gr": 0xA5, "cmd": 0x5B, "cmd_l": 0x5B,
                 "cmd_r": 0x5C, "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "backspace": 0x08,
                 "delete": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23, "page_up": 0x21, "page_down": 0x22,
                 "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "caps_lock": 0x14, "menu": 0x5D,
                 "num_lock": 0x90, "print_screen": 0x2C, "scroll_lock": 0x91, "pause": 0x13}
        if special in names:
            return names[special]
        m = re.fullmatch(r"f(\d{1,2})", special)
        if m:
            return 0x6F + int(m.group(1))
    if key.get("char"):
        return char_to_vk(key["char"])[0]
    return None
