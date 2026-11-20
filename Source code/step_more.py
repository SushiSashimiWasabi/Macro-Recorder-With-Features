"""(2.12) More actions for the Edit window, and more options for the old ones.

New steps (kind):
  else            after an If: its actions run when the If's condition was NOT true
  wait_random     wait a random time between "seconds" and "max"
  maths           counter = a (+ - x /) b, a and b a number or a counter; whole numbers or 2 decimals
  read_clipboard  the number you copied goes into a counter (the copied text is never logged, saved or sent)
  discord         a Discord message ({Counter} filled in), maybe with a screenshot
  sound           play one of the app's sounds
  set_speed       speed for the rest of this run
  game            bring the game to the front, or wait until it's open
  label / goto    a named spot in the macro, and a jump to it (with limits)
  screenshot      to the reports folder, Discord, or both

New options on old steps: see clean_step() (every field is checked there, for files from someone else).
Older versions of the app skip the new steps (they do nothing there) and ignore the new options.

The playback part (StepMoreMixin) is mixed into the core MacroRecorder."""
import copy
import math
import os
import random
import re
import threading
import time

import counters
import macro_steps as workflow

# ---------------------------------------------------------------- what Edit offers

ADDABLE = [
    ("else", "Else…", "after an If: steps that run when its condition isn't true"),
    ("wait_random", "Wait a random time", "between two numbers of seconds"),
    ("maths", "Do maths", "a counter = a number or counter + − × ÷ another"),
    ("read_clipboard", "Read the copied number", "the number you copied goes into a counter"),
    ("discord", "Send a Discord message", "with counters in it, and a screenshot if you like"),
    ("sound", "Play a sound", "one of the app's sounds"),
    ("set_speed", "Set speed", "how fast the rest of this run plays"),
    ("game", "Bring the game to the front", "or wait until the game is open"),
    ("label", "Label", "a named spot that Go to can jump to"),
    ("goto", "Go to a label", "jump to a Label (with a limit)"),
    ("screenshot", "Take a screenshot", "to the reports folder or Discord"),
]
NAMES = {k: n for k, n, _ in ADDABLE}
KINDS = tuple(NAMES)

DEFAULTS = {
    "else": {"actions": []},
    "wait_random": {"seconds": 1.0, "max": 3.0},
    "maths": {"counter": "Total", "a": {"counter": "Total"}, "op": "+", "b": {"number": 1}, "decimals": 0,
              "show_timer": True, "show_log": True, "show_discord": False, "keep": False, "then_macro": ""},
    "read_clipboard": {"counter": "Copied", "keep": False, "then_macro": ""},
    "discord": {"text": "", "screenshot": False, "to": "default", "channel": ""},
    "sound": {"sound": "picture_seen"},
    "set_speed": {"speed": 1.0},
    "game": {"mode": "front", "wait": 60, "otherwise": "go on"},
    "label": {"name": "Start"},
    "goto": {"label": "Start", "limit": 1000},
    "screenshot": {"to": "folder"},
}

MACRO_KEYS = ("then_macro", "otherwise_macro", "fail_macro")  # other macros a step can play
NUMBER_LIMIT = 10 ** 9
OPS = {"+": "+", "-": "−", "*": "×", "/": "÷"}
COMPARE = {">=": "≥", "==": "=", "<=": "≤", "!=": "≠", ">": ">", "<": "<"}
CONDITION_TYPES = {"picture": "A picture or colour", "counter": "A counter", "window": "A program is open",
                   "time": "The time of day"}
MODS = ("ctrl", "shift", "alt", "cmd")
GOTO_LIMIT = 1000
GOTO_FAST = 50  # jumps in a row with no time passing: an endless loop
TEXT_LETTERS = 2000
DESTINATIONS = {"default": "As set in Settings > Discord", "cards": "Where the run cards go",
                "channel": "A channel the phone remote bot is in", "webhook": "The extra webhook (Settings)"}
SHOT_TO = {"folder": "The reports folder", "discord": "Discord", "both": "Both"}


def new_step(kind):
    return copy.deepcopy(DEFAULTS.get(kind, {}))


# ---------------------------------------------------------------- numbers and text

def clean_number(value, default=0, decimals=True):
    """A number within +-NUMBER_LIMIT (2 decimals at most), or the default."""
    try:
        if isinstance(value, bool):
            raise ValueError
        n = float(value)
        if not math.isfinite(n):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return default
    n = max(-NUMBER_LIMIT, min(NUMBER_LIMIT, n))
    if not decimals or n == int(n):
        return int(round(n))
    return round(n, 2)


def fmt(n):
    """1, 2.5, 1000000 (no "1.0")."""
    if isinstance(n, float) and n == int(n):
        n = int(n)
    return f"{n:.2f}".rstrip("0").rstrip(".") if isinstance(n, float) else str(n)


def parse_copied(text):
    """The number in copied text ("1,234.5", "1.234,5", " -12 "), or None. Only a number on its own
    counts (with spaces around it); anything else is None."""
    if not isinstance(text, str):
        return None
    t = text.strip().replace(" ", "").replace(" ", "").replace("_", "")
    if not t or len(t) > 40 or not re.fullmatch(r"[+-]?[\d.,]+", t):
        return None
    if "," in t and "." in t:
        # the last one of the two is the decimal mark
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", "") if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+", t) else t.replace(",", ".")
    elif t.count(".") > 1:
        t = t.replace(".", "") if re.fullmatch(r"[+-]?\d{1,3}(\.\d{3})+", t) else t
    try:
        n = float(t)
    except ValueError:
        return None
    if not math.isfinite(n) or abs(n) > NUMBER_LIMIT:
        return None
    return clean_number(n)


PLACEHOLDER = re.compile(r"\{([^{}\n]{1,30})\}")


def fill(text, counters):
    """{Name} becomes that counter's value (names the macro doesn't have stay as they are)."""
    def one(m):
        name = m.group(1).strip()
        return fmt(counters[name]) if name in counters else m.group(0)
    return PLACEHOLDER.sub(one, str(text or ""))


def do_maths(a, op, b, decimals):
    """(result, problem): the result, or None and why not."""
    if op == "/" and b == 0:
        return None, "can't divide by 0"
    try:
        if op == "+":
            n = a + b
        elif op == "-":
            n = a - b
        elif op == "*":
            n = a * b
        else:
            n = a / b
            if not decimals:
                n = math.floor(n)
    except (OverflowError, ZeroDivisionError):
        return None, "the number got too big"
    if not math.isfinite(n):
        return None, "the number got too big"
    if abs(n) > NUMBER_LIMIT:
        n = math.copysign(NUMBER_LIMIT, n)
    return (round(n, 2) if decimals else int(round(n))), None


else_has_if = workflow.else_has_if  # (2.13 review: the rule lives in macro_steps, with the moves that keep it)


def in_time(now_hm, start, end):
    """Is HH:MM now between start and end (start included, end not; over midnight works)? A time that
    isn't a whole HH:MM (half typed, from a broken file) counts as not in that time, never an error."""
    def mins(hm):
        h, m = (int(p) for p in str(hm).split(":"))
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError
        return h * 60 + m
    try:
        n, s, e = mins(now_hm), mins(start), mins(end)
    except (ValueError, TypeError):
        import diag

        diag.info(f"If the time is {start} to {end}: that isn't a whole time (HH:MM), so it counts as not now")
        return False
    return s <= n < e if s <= e else (n >= s or n < e)


def compare(x, op, y):
    return {">=": x >= y, "==": x == y, "<=": x <= y, "!=": x != y, ">": x > y, "<": x < y}.get(op, x >= y)


# ---------------------------------------------------------------- checking a step from a file

def _hhmm(value, default):
    try:
        h, m = (int(p) for p in str(value).strip().split(":", 1))
    except (ValueError, AttributeError):
        return default
    return f"{h:02d}:{m:02d}" if 0 <= h < 24 and 0 <= m < 60 else default


def _text(value, letters, default=""):
    import unicodedata

    text = "".join(c for c in str(value if value is not None else default)
                   if c in "\n\t" or unicodedata.category(c)[0] != "C")
    return text[:letters]


def _name(value, default):
    import macro_steps as workflow

    name = workflow.clean_counter_name(value)
    return name if str(value or "").strip() else default


def _seconds(value, default, high=36000.0):
    n = clean_number(value, default)
    return float(max(0.0, min(high, n)))


def _choice(value, options, default):
    return value if isinstance(value, str) and value in options else default


def _macro_file(value):
    """A macro another step plays: a file name or a path inside the macro's folder, never ".."."""
    if not isinstance(value, str) or not value.strip():
        return ""
    v = value.strip()[:260]
    return "" if ".." in v.replace("\\", "/").split("/") else v


def _program(value):
    """A program window: {"exe": file name only, "title": a few words}, or None."""
    if not isinstance(value, dict) or not value.get("exe"):
        return None
    exe = os.path.basename(str(value["exe"]).replace("\\", "/"))[:80]
    return {"exe": exe, "title": _text(value.get("title"), 60)} if exe else None


def _area(h):
    for k in ("x0", "y0", "x1", "y1"):
        if k in h:
            h[k] = int(clean_number(h.get(k), 0, decimals=False))
            h[k] = max(-100000, min(100000, h[k]))
    if all(k in h for k in ("x0", "y0", "x1", "y1")):
        h["x0"], h["x1"] = sorted((h["x0"], h["x1"]))
        h["y0"], h["y1"] = sorted((h["y0"], h["y1"]))


def _operand(o):
    if isinstance(o, dict) and "counter" in o:
        return {"counter": _name(o.get("counter"), "Counter")}
    if isinstance(o, dict):
        return {"number": clean_number(o.get("number"), 0)}
    return {"number": 0}


def clean_condition(c, depth=0):
    """The new parts of an If / Retry / Repeat-until condition."""
    if not isinstance(c, dict):
        return c
    c["type"] = _choice(c.get("type"), CONDITION_TYPES, "picture")
    if "wait" in c:
        c["wait"] = _seconds(c.get("wait"), 0, 3600)
    if c["type"] == "counter":
        c["counter"] = _name(c.get("counter"), "Counter")
        c["op"] = _choice(c.get("op"), COMPARE, ">=")
        c["value"] = clean_number(c.get("value"), 0)
        c["other"] = _name(c.get("other"), "") if c.get("other") else ""
    elif c["type"] == "window":
        c["program"] = _program(c.get("program"))
    elif c["type"] == "time":
        c["from"], c["to"] = _hhmm(c.get("from"), "02:00"), _hhmm(c.get("to"), "06:00")
    more = c.get("more")
    if more is not None:
        if not isinstance(more, list) or depth > 0:
            c.pop("more", None)
        else:
            c["more"] = [clean_condition(m, depth + 1) for m in more[:8] if isinstance(m, dict)]
            for m in c["more"]:
                import color_check

                color_check.clean(m)
                m["shows"] = m.get("shows", True) is not False
                if "match" in m:
                    m["match"] = int(max(50, min(99, clean_number(m.get("match"), 85, decimals=False))))
    c["join"] = _choice(c.get("join"), ("and", "or"), "and")
    return c


def clean_step(a):
    """Every new kind and every new option, checked (a file may be someone else's): known values only,
    numbers in range, names cleaned, other macros as file names only. Returns a."""
    if not isinstance(a, dict):
        return a
    kind = a.get("kind")
    for key in MACRO_KEYS:
        if key in a:
            a[key] = _macro_file(a.get(key))
    a.pop("then_steps", None), a.pop("otherwise_steps", None), a.pop("fail_steps", None)  # (only made at Play)
    if kind == "wait_random":
        a["seconds"], a["max"] = _seconds(a.get("seconds"), 1.0), _seconds(a.get("max"), 3.0)
    elif kind == "maths":
        a["counter"] = _name(a.get("counter"), "Total")
        a["a"], a["b"] = _operand(a.get("a")), _operand(a.get("b"))
        a["op"] = _choice(a.get("op"), OPS, "+")
        a["decimals"] = 2 if a.get("decimals") == 2 else 0
        for k in ("show_timer", "show_log", "show_discord", "keep"):
            a[k] = a.get(k) is True
    elif kind == "read_clipboard":
        a["counter"] = _name(a.get("counter"), "Copied")
        a["keep"] = a.get("keep") is True
    elif kind == "discord":
        a["text"] = _text(a.get("text"), TEXT_LETTERS)
        a["screenshot"] = a.get("screenshot") is True
        a["to"] = _choice(a.get("to"), DESTINATIONS, "default")
        a["channel"] = clean_channel(a.get("channel"))
        a.pop("webhook", None)  # (never a webhook link in a macro: it's a secret, kept in Settings only)
    elif kind == "sound":
        import sounds

        a["sound"] = _choice(a.get("sound"), sounds.EVENT_IDS, "picture_seen")
    elif kind == "set_speed":
        a["speed"] = float(max(0.01, min(100.0, clean_number(a.get("speed"), 1.0))))
    elif kind == "game":
        a["mode"] = _choice(a.get("mode"), ("front", "wait"), "front")
        a["wait"] = _seconds(a.get("wait"), 60, 3600)
        a["otherwise"] = _choice(a.get("otherwise"), ("go on", "stop"), "go on")
    elif kind == "label":
        a["name"] = _name(a.get("name"), "Start")
    elif kind == "goto":
        a["label"] = _name(a.get("label"), "Start")
        a["limit"] = int(max(1, min(1000000, clean_number(a.get("limit"), GOTO_LIMIT, decimals=False))))
    elif kind == "screenshot":
        a["to"] = _choice(a.get("to"), SHOT_TO, "folder")
    elif kind == "key":
        if "mods" in a:
            a["mods"] = [m for m in MODS if isinstance(a.get("mods"), list) and m in a["mods"]]
        if "between" in a:
            a["between"] = _seconds(a.get("between"), 0, 3600)
    elif kind == "type":
        a["text"] = _text(a.get("text"), 100000)
        if "enter" in a:
            a["enter"] = a.get("enter") is True
        if "how" in a:
            a["how"] = _choice(a.get("how"), ("letters", "paste"), "letters")
        if "window" in a:
            a["window"] = _program(a.get("window"))
            if a["window"] is not None:
                import window_tools

                if window_tools.never_type_into(exe=a["window"]["exe"]):
                    a["window"] = None  # (2.12: never a command window, the registry, the Run box...)
    elif kind == "click":
        if "target" in a:
            a["target"] = _choice(a.get("target"), ("spot", "area", "found"), "spot")
        for k in ("dx", "dy"):
            if k in a:
                a[k] = int(max(-5000, min(5000, clean_number(a.get(k), 0, decimals=False))))
        if "jitter" in a:
            a["jitter"] = int(max(0, min(200, clean_number(a.get("jitter"), 0, decimals=False))))
        if "random" in a:
            a["random"] = a.get("random") is True
        _area(a)
    elif kind == "move":
        if "glide" in a:
            a["glide"] = _seconds(a.get("glide"), 0, 60)
        if "relative" in a:
            a["relative"] = a.get("relative") is True
        for k in ("dx", "dy"):
            if k in a:
                a[k] = int(max(-20000, min(20000, clean_number(a.get(k), 0, decimals=False))))
    elif kind == "scroll":
        if "between" in a:
            a["between"] = _seconds(a.get("between"), 0, 60)
    elif kind == "wait":
        if "random" in a:
            a["random"] = a.get("random") is True
        if "max" in a:
            a["max"] = _seconds(a.get("max"), a.get("seconds", 1.0))
    elif kind == "wait_picture":
        if "until" in a:
            a["until"] = _choice(a.get("until"), ("shows", "gone"), "shows")
        if "otherwise" in a:
            a["otherwise"] = _choice(a.get("otherwise"), ("go on", "stop", "macro", "restart", "discord"), "go on")
        if not a.get("color_on"):
            _area(a)
    elif kind in ("if", "retry"):
        clean_condition(a.get("condition"))
        if kind == "retry":
            for k, high in (("check", 3600), ("between", 3600)):
                if k in a:
                    a[k] = _seconds(a.get(k), 2.0 if k == "check" else 0, high)
            if "if_fails" in a:
                a["if_fails"] = _choice(a.get("if_fails"), ("go on", "stop", "macro"), "go on")
    elif kind == "repeat":
        if "mode" in a:
            a["mode"] = _choice(a.get("mode"), ("times", "until", "minutes", "forever"), "times")
        if "minutes" in a:
            a["minutes"] = _seconds(a.get("minutes"), 5, 100000)
        if isinstance(a.get("condition"), dict):
            import color_check

            color_check.clean(a["condition"])
            clean_condition(a["condition"])
    elif kind == "stop":
        if "reason" in a:
            a["reason"] = _text(a.get("reason"), 200).replace("\n", " ")
        if "ping" in a:
            a["ping"] = a.get("ping") is True
    elif kind == "note":
        if "show" in a:
            a["show"] = a.get("show") is True
    elif kind == "play_macro":
        if "speed" in a:
            a["speed"] = float(max(0.0, min(100.0, clean_number(a.get("speed"), 0))))
    elif kind == "if_counter":
        if "op" in a:
            a["op"] = _choice(a.get("op"), COMPARE, ">=")
        if "other" in a:
            a["other"] = _name(a.get("other"), "") if a.get("other") else ""
    return a


PING = re.compile(r"(?<![\w.])@(everyone|here)\b|<@[!&]?\d+>", re.IGNORECASE)


def no_pings(text):
    """(2.12) @everyone, @here, <@user> and <@&role> made harmless (shown, but nobody is pinged)."""
    return PING.sub(lambda m: m.group(0).replace("@", "@\u200b", 1), str(text or ""))


SENSITIVE_CLIPBOARD = "reads the number you copy"
# (security, 20 Nov 2026) the Windows key (or Ctrl+Esc) opens the Start menu / Run box: with it, recorded keys
# can start any program. A screenshot sent to Discord shows your screen to whoever owns that link.
SENSITIVE_WINKEY = "presses the Windows key"
SENSITIVE_SHOT = "sends screenshots to Discord"
WIN_SPECIALS = {"cmd", "cmd_l", "cmd_r"}
WIN_VKS = {91, 92}
CTRL_SPECIALS = {"ctrl", "ctrl_l", "ctrl_r"}
CTRL_VKS = {17, 162, 163}


def vk_of(key):
    """A key's code as Windows reads it: only the low 16 bits count (a bigger number in a file, like 65627,
    is cut down to 91 = the Windows key when the key is sent), so the checks below look at those."""
    vk = key.get("vk") if isinstance(key, dict) else getattr(key, "vk", None)
    return vk & 0xFFFF if isinstance(vk, int) and not isinstance(vk, bool) else vk


def is_win_key(key):
    key = key if isinstance(key, dict) else {}
    return str(key.get("special", "")).lower() in WIN_SPECIALS or vk_of(key) in WIN_VKS


def is_ctrl_key(key):
    key = key if isinstance(key, dict) else {}
    return str(key.get("special", "")).lower() in CTRL_SPECIALS or vk_of(key) in CTRL_VKS


def is_esc_key(key):
    key = key if isinstance(key, dict) else {}
    return str(key.get("special", "")).lower() == "esc" or vk_of(key) == 27


def opens_start(events):
    """True when these recorded events press the Windows key, or Esc while Ctrl is held."""
    ctrl = False
    for ev in events if isinstance(events, list) else []:
        if not isinstance(ev, dict) or ev.get("type") != "key":
            continue
        key, pressed = ev.get("key"), bool(ev.get("pressed"))
        if is_win_key(key) and pressed:
            return True
        if is_ctrl_key(key):
            ctrl = pressed
        elif ctrl and pressed and is_esc_key(key):
            return True
    return False


def sensitive_parts(steps):
    """(2.12) What a macro does outside the game that needs your OK when it comes from someone else:
    {"types into notepad.exe", "reads the number you copy", "presses the Windows key",
    "sends screenshots to Discord"}."""
    import macro_steps as workflow

    out = set()
    for a, _l, _i, _p in workflow.walk(steps or []):
        if a.get("off"):
            continue
        kind = a.get("kind")
        if kind == "type" and isinstance(a.get("window"), dict) and a["window"].get("exe"):
            out.add("types into " + os.path.basename(str(a["window"]["exe"])).lower())
        if kind == "read_clipboard":
            out.add(SENSITIVE_CLIPBOARD)
        if kind == "recorded" and opens_start(a.get("events")):
            out.add(SENSITIVE_WINKEY)
        if kind == "key":
            mods = a.get("mods") if isinstance(a.get("mods"), list) else []
            if is_win_key(a.get("key")) or "cmd" in mods or ("ctrl" in mods and is_esc_key(a.get("key"))):
                out.add(SENSITIVE_WINKEY)
        if (kind == "discord" and a.get("screenshot") is True) or \
                (kind == "screenshot" and a.get("to") in ("discord", "both")):
            out.add(SENSITIVE_SHOT)
    return out


def clean_channel(value):
    v = str(value or "").strip()
    return v if re.fullmatch(r"\d{17,20}", v) else ""


def counter_names(a):
    """Counters a new step uses (for the list of counters in Edit and the timer)."""
    kind = a.get("kind")
    names = []
    if kind in ("maths", "read_clipboard"):
        names.append(a.get("counter"))
    if kind == "maths":
        names += [o.get("counter") for o in (a.get("a"), a.get("b")) if isinstance(o, dict) and o.get("counter")]
    return [n for n in names if n]


# ---------------------------------------------------------------- how Edit lists them

def describe(a):
    """(name, a few words) for a new kind, or None for the old kinds."""
    kind = a.get("kind")
    if kind not in NAMES:
        return None
    name = NAMES[kind]
    if kind == "else":
        return "Else", f"when the If above isn't true  ({len(a.get('actions', []))} steps)"
    if kind == "wait_random":
        return name, f"{fmt(a.get('seconds', 0))} to {fmt(a.get('max', 0))} s"
    if kind == "maths":
        def side(o):
            return o.get("counter") if isinstance(o, dict) and "counter" in o else fmt((o or {}).get("number", 0))
        text = f"{a.get('counter')} = {side(a.get('a'))} {OPS.get(a.get('op'), '+')} {side(a.get('b'))}"
        return name, text + (" (2 decimals)" if a.get("decimals") == 2 else "")
    if kind == "read_clipboard":
        return name, f"into {a.get('counter')}"
    if kind == "discord":
        text = str(a.get("text") or "").replace("\n", " ")
        return name, (text[:40] + "…" if len(text) > 40 else text or "(no text yet)") + (
            " + screenshot" if a.get("screenshot") else "")
    if kind == "sound":
        import sounds

        return name, next((n for ev, n, _t, _o in sounds.EVENTS if ev == a.get("sound")), a.get("sound", ""))
    if kind == "set_speed":
        return name, f"{fmt(a.get('speed', 1))}x for the rest of this run"
    if kind == "game":
        return ("Wait for the game", f"up to {fmt(a.get('wait', 60))} s, then bring it to the front") \
            if a.get("mode") == "wait" else (name, "")
    if kind == "label":
        return name, a.get("name", "")
    if kind == "goto":
        return name, f"{a.get('label', '')} (at most {a.get('limit', GOTO_LIMIT)} times a run)"
    if kind == "screenshot":
        return name, SHOT_TO.get(a.get("to"), "")
    return name, ""


def condition_words(c):
    """The new condition types in words (None: a picture or colour, said by the old code)."""
    t = c.get("type", "picture")
    if t == "counter":
        other = c.get("other")
        return f"{c.get('counter')} {COMPARE.get(c.get('op'), '≥')} {other or fmt(c.get('value', 0))}"
    if t == "window":
        p = c.get("program") or {}
        return f"{p.get('exe') or 'a program'} is open" if c.get("shows", True) else \
            f"{p.get('exe') or 'a program'} isn't open"
    if t == "time":
        return f"the time is {c.get('from')} to {c.get('to')}"
    return None


# ---------------------------------------------------------------- the copied text (Windows)

def read_clipboard_text():
    """The text on the clipboard ("" when there's none). Never logged, saved or sent anywhere."""
    import sys

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
        kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
        for _ in range(10):
            if user32.OpenClipboard(None):
                break
            time.sleep(0.02)
        else:
            return ""
        try:
            handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
            if not handle:
                return ""
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ""
            try:
                return ctypes.wstring_at(ptr)[:10000]
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    try:
        import subprocess

        return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=2).stdout[:10000]
    except Exception:
        return ""


def write_clipboard_text(text):
    """Put text on the clipboard (for typing by pasting). True when it worked."""
    import sys

    if sys.platform != "win32":
        try:
            import subprocess

            subprocess.run(["pbcopy"], input=text, text=True, timeout=2)
            return True
        except Exception:
            return False
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    data = (text + "\0").encode("utf-16-le")
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
        ptr = kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        return bool(user32.SetClipboardData(13, handle))
    finally:
        user32.CloseClipboard()


# ---------------------------------------------------------------- playing them

class StepMoreMixin:
    _more_lock = threading.Lock()

    # -------------------------------------------------------------- counters
    def _counter_value(self, name, why=""):
        counters = self.__dict__.setdefault("counters", {})
        if name not in counters:
            import diag

            diag.info(f"Counter \"{name}\" isn't set yet{why}: it counts as 0")
            return 0
        return counters[name]

    def _set_counter(self, name, value):
        counters.set_value(self.__dict__.setdefault("counters", {}), self._counter_lock, name, value)

    def _operand_value(self, o):
        if isinstance(o, dict) and "counter" in o:
            return self._counter_value(o["counter"], " (Do maths)")
        return (o or {}).get("number", 0) if isinstance(o, dict) else 0

    def _show_text(self, text, timer=True, log=True, discord=False):
        import diag

        if timer:
            self.timer_text = text
        if log:
            diag.info(f"Do maths: {text}")
        if discord:
            self._macro_discord(text)

    # -------------------------------------------------------------- the step runner
    def _run_more_step(self, a, ctx):
        """A new step, or an old one that uses a new option. None: the old code plays it."""
        kind = a.get("kind")
        fn = getattr(self, "_more_" + kind, None) if kind in KINDS else None
        if fn is not None:
            return fn(a, ctx)
        if kind == "key" and (a.get("mods") or a.get("between")):
            return self._more_key(a, ctx)
        if kind == "type" and (a.get("enter") or a.get("how") == "paste" or a.get("window") or a.get("then_macro")
                               or "{" in str(a.get("text", ""))):
            return self._more_type(a, ctx)
        if kind == "click" and (a.get("target", "spot") != "spot" or a.get("dx") or a.get("dy") or a.get("jitter")):
            return self._more_click(a, ctx)
        if kind == "move" and (a.get("glide") or a.get("relative")):
            return self._more_move(a, ctx)
        if kind == "scroll" and a.get("between"):
            return self._more_scroll(a, ctx)
        if kind == "wait" and a.get("random"):
            return self._more_wait_random(dict(a, max=a.get("max", a.get("seconds", 1))), ctx)
        if kind == "wait_picture" and (a.get("until") == "gone" or a.get("otherwise") in ("macro", "restart", "discord")
                                       or (not a.get("color_on") and a.get("where") == "area" and "x0" in a)):
            return self._more_wait_picture(a, ctx)
        if kind == "if" and self._new_condition(a.get("condition")):
            ok = self._condition_all(a.get("condition", {}))
            if ok in ("stop", "gameback"):
                return ok
            self.last_if_true = bool(ok)
            return self._run_steps(a.get("actions", []), ctx) if ok else "ok"
        if kind == "retry" and (self._new_condition(a.get("condition")) or a.get("check") is not None
                                or a.get("between") or a.get("if_fails") not in (None, "go on")):
            return self._more_retry(a, ctx)
        if kind == "repeat" and a.get("mode", "times") != "times":
            return self._more_repeat(a, ctx)
        if kind == "stop" and (a.get("reason") or a.get("ping")):
            return self._more_stop(a, ctx)
        if kind == "note" and a.get("show"):
            self.timer_text = str(a.get("text", ""))[:80]
            return "ok"
        if kind == "if_counter" and (a.get("op", ">=") != ">=" or a.get("other")):
            c = {"type": "counter", "counter": a.get("counter"), "op": a.get("op", ">="),
                 "value": a.get("at_least", 1), "other": a.get("other", "")}
            ok = self._condition_one(c)
            self.last_if_true = bool(ok)
            return self._run_steps(a.get("actions", []), ctx) if ok else "ok"
        return None

    def _then(self, a, ctx, key="then"):
        """A step's "Run another macro afterwards" (its steps were read at Play)."""
        steps = a.get(key + "_steps")
        if steps:
            import diag

            diag.info(f"Playing the macro after a step: \"{os.path.splitext(os.path.basename(a.get(key + '_macro')))[0]}\"")
            return self._run_steps(steps, ctx)
        return "ok"

    # -------------------------------------------------------------- new steps
    def _more_else(self, a, ctx):
        return "ok"  # (_run_steps plays an Else's actions when the If before it wasn't true)

    def _more_wait_random(self, a, ctx):
        low, high = sorted((float(a.get("seconds", 0)), float(a.get("max", a.get("seconds", 0)))))
        seconds = random.uniform(low, high)
        self._set_note(f"Waiting {seconds:.1f} s (random)...")
        return self._pause(seconds / ctx["speed"], ctx)

    def _more_maths(self, a, ctx):
        import diag

        x, y = self._operand_value(a.get("a")), self._operand_value(a.get("b"))
        decimals = a.get("decimals") == 2
        op = a.get("op", "+")
        name = a.get("counter", "Total")
        result, problem = do_maths(x, op, y, decimals)
        if problem:
            diag.info(f"Do maths: {name} = {fmt(x)} {OPS.get(op, op)} {fmt(y)}: {problem}, {name} stays "
                      f"{fmt(self._counter_value(name))}")
        else:
            self._set_counter(name, result)
            text = f"{name}: {fmt(x)}{OPS.get(op, op)}{fmt(y)}={fmt(result)}"
            self._show_text(text, a.get("show_timer", True), a.get("show_log", True), a.get("show_discord", False))
        return self._then(a, ctx)

    def _more_read_clipboard(self, a, ctx):
        import diag

        name = a.get("counter", "Copied")
        if getattr(self, "ghost", False):
            diag.info(f"Watch only: the copied number isn't read (counter \"{name}\" stays)")
            return "ok"
        if not getattr(self, "allow_sensitive", True):
            diag.info(f"Read the copied number: skipped (not allowed for this macro), \"{name}\" stays")
            return self._then(a, ctx)
        n = parse_copied(read_clipboard_text())
        if n is None:
            diag.info(f"Read the copied number: what's copied isn't a number, so \"{name}\" stays as it was")
        else:
            self._set_counter(name, n)
            diag.info(f"Read the copied number into \"{name}\"")  # (never the number or the text itself)
        return self._then(a, ctx)

    def _more_discord(self, a, ctx):
        text = fill(a.get("text", ""), getattr(self, "counters", {}) or {})
        png = None
        if a.get("screenshot") and not getattr(self, "allow_sensitive", True):
            import diag

            diag.info("Discord message: sent without its screenshot (not allowed for this macro)")
        elif a.get("screenshot") and hasattr(self, "_screenshot") and not getattr(self, "ghost", False):
            try:
                png = self._screenshot()
            except Exception:
                png = None
        self._macro_discord(text or "(empty message)", png=png, to=a.get("to", "default"), channel=a.get("channel"))
        return "ok"

    def _more_sound(self, a, ctx):
        name = a.get("sound", "picture_seen")
        if hasattr(self, "_sound"):
            self._call_ui(lambda: self._sound(name, even_if_off=True))
        return "ok"

    def _more_set_speed(self, a, ctx):
        import diag

        ctx.setdefault("base_speed", ctx["speed"])
        ctx["speed"] = max(0.01, min(100.0, float(a.get("speed", 1.0))))
        diag.info(f"Set speed: {fmt(ctx['speed'])}x until this run ends")
        return "ok"

    def _more_game(self, a, ctx):
        import diag
        import window_tools

        exe = getattr(self, "play_game_exe", None) or (self.macro_program or {}).get("exe") \
            or self.settings.get("last_game_exe")
        if getattr(self, "ghost", False) or not exe:
            if not exe:
                diag.info("Bring the game to the front: no game known yet, skipped")
            return "ok"
        deadline = self._play_clock() + (float(a.get("wait", 60)) if a.get("mode") == "wait" else 0)
        while True:
            wins = window_tools.windows_of(exe)
            if wins:
                window_tools.force_to_front(wins[0])
                return "ok"
            if self._play_clock() >= deadline:
                diag.info(f"The game ({exe}) isn't open" + (" after waiting" if a.get("mode") == "wait" else ""))
                if a.get("otherwise") == "stop":
                    self.stop_reason = "Stopped: the game isn't open (Wait for the game)."
                    return "stop"
                return "ok"
            self._set_note(f"Waiting for the game ({int(deadline - self._play_clock()) + 1} s)...")
            if self.stop_play.wait(0.5):
                return "stop"

    def _more_label(self, a, ctx):
        return "ok"

    def _more_goto(self, a, ctx):
        import diag

        jumps = self.__dict__.setdefault("goto_jumps", {})
        key = a.get("id") or a.get("label")
        n = jumps.get(key, 0) + 1
        jumps[key] = n
        now = self._play_clock()
        fast = self.__dict__.setdefault("goto_fast", [0, now])
        fast[0] = fast[0] + 1 if now - fast[1] < 0.01 else 1
        fast[1] = now
        limit = int(a.get("limit", GOTO_LIMIT))
        if n > limit or fast[0] > GOTO_FAST:
            why = (f"\"Go to {a.get('label')}\" jumped {limit} times in one run (its limit)" if n > limit else
                   f"\"Go to {a.get('label')}\" jumped {GOTO_FAST} times with no time passing (an endless loop)")
            self.stop_reason = f"Stopped: {why}."
            diag.info(self.stop_reason)
            return "stop"
        return "goto:" + str(a.get("label", ""))

    def _more_screenshot(self, a, ctx):
        import diag

        if getattr(self, "ghost", False):
            return "ok"
        to = a.get("to", "folder")
        try:
            img = self._screenshot() if hasattr(self, "_screenshot") else None
        except Exception as exc:
            diag.error("Take a screenshot failed", exc)
            return "ok"
        if img is None:
            return "ok"
        if to in ("folder", "both"):
            folder = diag.reports_dir()
            if folder:
                try:
                    import image_watch

                    os.makedirs(folder, exist_ok=True)
                    path = os.path.join(folder, time.strftime("screenshot %Y-%m-%d %H-%M-%S.png"))
                    if isinstance(img, (bytes, bytearray)):
                        with open(path, "wb") as f:
                            f.write(img)
                    else:
                        image_watch.save_image(path, img)
                    diag.info("Take a screenshot: saved in the reports folder")
                except Exception as exc:
                    diag.error("Couldn't save the screenshot", exc)
        if to in ("discord", "both") and not getattr(self, "allow_sensitive", True):
            diag.info("Take a screenshot: not sent to Discord (not allowed for this macro)")
        elif to in ("discord", "both"):
            self._macro_discord(f"Screenshot · {time.strftime('%H:%M:%S')}", png=img)
        return "ok"

    # -------------------------------------------------------------- old steps with new options
    def _play_list(self, events, ctx):
        held_keys, held_buttons = ctx["held"]
        for ev in events:
            if ctx["bg"] is not None:
                self._replay_event_bg(ctx["bg"], ev, held_keys)
            else:
                gone = self._key_guard(ev, ctx.get("away"), held_keys, held_buttons)
                if gone:
                    return gone
                self._replay_event(ev, held_keys, held_buttons)
            if ev.get("pause"):
                result = self._pause(ev["pause"], ctx)
                if result != "ok":
                    return result
        return "ok"

    def _more_key(self, a, ctx):
        mods = [{"special": m} for m in a.get("mods", []) if m in MODS]
        mode = a.get("mode", "press")
        key = a.get("key", {})
        if mode in ("down", "up"):
            evs = [{"type": "key", "key": k, "pressed": mode == "down"} for k in (mods + [key] if mode == "down"
                                                                                  else [key] + mods[::-1])]
            return self._play_list(evs, ctx)
        hold = max(0.03, float(a.get("hold", 0) or 0))
        between = float(a.get("between", 0) or 0)
        times = max(1, int(a.get("times", 1)))
        evs = []
        for n in range(times):
            evs += [{"type": "key", "key": m, "pressed": True, "pause": 0.02} for m in mods]
            evs.append({"type": "key", "key": key, "pressed": True, "pause": hold})
            evs.append({"type": "key", "key": key, "pressed": False, "pause": 0.02})
            evs += [{"type": "key", "key": m, "pressed": False, "pause": 0.02} for m in mods[::-1]]
            if between and n + 1 < times:
                evs[-1] = dict(evs[-1], pause=evs[-1]["pause"] + between)
        return self._play_list(evs, ctx)

    def _type_events(self, text, delay):
        return self._step_events({"kind": "type", "text": text, "delay": delay})

    def _more_type(self, a, ctx):
        import diag
        import window_tools

        text = fill(a.get("text", ""), getattr(self, "counters", {}) or {})
        if a.get("enter"):
            text += "\n"
        target = a.get("window")
        back = None
        if target and not getattr(self, "ghost", False):
            if not getattr(self, "allow_sensitive", True):
                diag.info(f"Type text into {target.get('exe')}: skipped (not allowed for this macro)")
                return self._then(a, ctx)
            wins = [w for w in window_tools.windows_of(target.get("exe")) if not window_tools.never_type_into(w)]
            if target.get("title"):
                titled = [w for w in wins if target["title"].lower() in (window_tools.title_of(w) or "").lower()]
                wins = titled or wins
            if not wins:
                diag.info(f"Type text: the window ({target.get('exe')}) isn't open, nothing was typed")
                return self._then(a, ctx)
            back = window_tools.foreground()
            window_tools.force_to_front(wins[0])
            time.sleep(0.15)
            ctx = dict(ctx, away=None)  # (the game isn't in front while typing there: that's on purpose)
        try:
            if a.get("how") == "paste" and not getattr(self, "ghost", False):
                old = read_clipboard_text()
                if write_clipboard_text(text.rstrip("\n")):
                    paste = [{"type": "key", "key": {"special": "ctrl"}, "pressed": True, "pause": 0.03},
                             {"type": "key", "key": {"char": "v"}, "pressed": True, "pause": 0.03},
                             {"type": "key", "key": {"char": "v"}, "pressed": False, "pause": 0.03},
                             {"type": "key", "key": {"special": "ctrl"}, "pressed": False, "pause": 0.1}]
                    if text.endswith("\n"):
                        paste += self._type_events("\n", 0.02)
                    result = self._play_list(paste, ctx)
                    time.sleep(0.1)
                    write_clipboard_text(old)  # (what you had copied comes back)
                else:
                    result = self._play_list(self._type_events(text, float(a.get("delay", 0.02))), ctx)
            else:
                result = self._play_list(self._type_events(text, float(a.get("delay", 0.02))), ctx)
        finally:
            if back is not None:
                time.sleep(0.1)
                window_tools.force_to_front(back)
                time.sleep(0.1)
        if result != "ok":
            return result
        return self._then(a, ctx)

    def _click_point(self, a):
        """Where a click step clicks now: (x, y), or None when there's nothing to click on."""
        import diag

        target = a.get("target", "spot")
        rect = None
        if target == "found":
            rect = getattr(self, "last_found", None)
            if not rect:
                diag.info("Click where it was found: nothing was found yet, so no click")
                return None
        elif target == "area" and all(k in a for k in ("x0", "y0", "x1", "y1")):
            rect = (a["x0"], a["y0"], a["x1"] - a["x0"], a["y1"] - a["y0"])
        if rect is not None:
            x, y, w, h = rect
            if a.get("random"):
                px, py = x + random.randint(0, max(0, int(w) - 1)), y + random.randint(0, max(0, int(h) - 1))
            else:
                px, py = x + int(w) // 2, y + int(h) // 2
        else:
            px, py = int(a.get("x", 0)), int(a.get("y", 0))
        px, py = px + int(a.get("dx", 0)), py + int(a.get("dy", 0))
        j = int(a.get("jitter", 0) or 0)
        if j:
            px, py = px + random.randint(-j, j), py + random.randint(-j, j)
        return px, py

    def _more_click(self, a, ctx):
        spot = self._click_point(a)
        if spot is None:
            return "ok"
        return self._play_list(self._step_events(dict(a, x=spot[0], y=spot[1])), ctx)

    def _more_move(self, a, ctx):
        if a.get("relative"):
            return self._play_list([{"type": "move_rel", "dx": int(a.get("dx", 0)), "dy": int(a.get("dy", 0))}], ctx)
        x, y = int(a.get("x", 0)), int(a.get("y", 0))
        glide = float(a.get("glide", 0) or 0) / ctx["speed"]
        try:
            sx, sy = self.mouse_ctrl.position
        except Exception:
            sx, sy = x, y
        steps = max(1, min(600, int(glide / 0.01)))
        evs = [{"type": "move", "x": round(sx + (x - sx) * k / steps), "y": round(sy + (y - sy) * k / steps),
                "pause": glide / steps if k < steps else 0} for k in range(1, steps + 1)]
        return self._play_list(evs, ctx)

    def _more_scroll(self, a, ctx):
        n = int(a.get("amount", 0))
        between = float(a.get("between", 0) or 0)
        evs = [{"type": "scroll", "dx": 0, "dy": 1 if n > 0 else -1, "pause": between} for _ in range(abs(n))]
        return self._play_list(evs, ctx)

    def _more_wait_picture(self, a, ctx):
        """Wait for a picture or colour with the new options: until it's gone, only in an area, and
        more choices when it doesn't show in time."""
        import diag

        held_keys, held_buttons = ctx["held"]
        want = a.get("until", "shows") != "gone"
        timeout = float(a.get("timeout", 30))
        label = a.get("name") or "the picture"
        if getattr(self, "ghost", False):
            ok = self.test_play.get("found", True)
        elif a.get("color_on"):
            import color_check

            label = color_check.describe(a)
            self._set_note(f"Waiting until {label} {'shows' if want else 'is gone'}...")
            ok = self._color_until(a, want, timeout if timeout > 0 else 10 ** 9, ctx["away"], ctx["held"])
            if isinstance(ok, tuple):
                return "gameback" if ok[1] == "gameback" else "stop"
            if ok and want and "x" in a:
                self.last_found = (int(a["x"]), int(a["y"]), 1, 1)
        else:
            matcher = self.wait_matchers.get(id(a))
            if matcher is None:
                return "ok"
            self._set_note(f"Waiting until {label} {'shows' if want else 'is gone'}...")
            ok = self._look_area_until(matcher, a, want, timeout if timeout > 0 else 10 ** 9)
        if self.stop_play.is_set():
            return "stop"
        if ok:
            if a.get("click") and want and getattr(self, "last_found", None):
                x, y, w, h = self.last_found
                self._click_at(x + w // 2, y + h // 2)
            return "ok"
        other = a.get("otherwise", "go on")
        why = f"{label} didn't {'show' if want else 'go away'} within {timeout:g} s"
        if other == "stop":
            self.stop_reason = f"Stopped: {why}."
            diag.info(self.stop_reason)
            return "stop"
        diag.info(f"Wait for…: {why}")
        if other == "restart":
            return "restart"
        if other == "discord":
            self._macro_discord(why[0].upper() + why[1:] + ".")
        if other == "macro":
            return self._then(a, ctx, "otherwise")
        return "ok"

    def _look_area_until(self, matcher, h, want, wait):
        """A picture shows (want True) or is gone, looked for only in the step's area when it has one."""
        import image_watch

        need = max(0.5, min(0.99, h.get("match", 85) / 100.0))
        area = (h["x0"], h["y0"], h["x1"], h["y1"]) if h.get("where") == "area" and "x0" in h else None
        if area is not None:
            import color_check

            area = color_check._cut(*area)
        deadline = time.perf_counter() + max(0.0, wait)
        with image_watch.mss.mss() as sct:
            origin = image_watch.screen_origin(sct)
            while True:
                started = time.perf_counter()
                try:
                    screen = self._hide_own_window(image_watch.grab_screen(sct, area), origin)
                    score, rect = matcher.find(screen, good_enough=need, area=area)
                except Exception:
                    score, rect = 0.0, None
                self._note_look("wait for a picture", time.perf_counter() - started)
                seen = score >= need and rect is not None
                if seen:
                    x, y, w, hh = rect
                    self.last_found = (origin[0] + x, origin[1] + y, w, hh)
                if seen == want:
                    return True
                if started >= deadline or self.stop_play.is_set():
                    return False
                self.stop_play.wait(max(0.25, time.perf_counter() - started))

    # -------------------------------------------------------------- conditions
    @staticmethod
    def _new_condition(c):
        return isinstance(c, dict) and (c.get("type", "picture") != "picture" or bool(c.get("more"))
                                        or float(c.get("wait", 0) or 0) > 0)

    def _condition_one(self, c, wait=0.0):
        import window_tools

        t = c.get("type", "picture")
        want = c.get("shows", True) is not False
        if t == "counter":
            x = self._counter_value(c.get("counter", "Counter"), " (If)")
            y = self._counter_value(c["other"], " (If)") if c.get("other") else c.get("value", 0)
            return compare(x, c.get("op", ">="), y)
        if t == "window":
            p = c.get("program") or {}
            open_now = bool(p.get("exe") and window_tools.windows_of(p["exe"]))
            return open_now == want
        if t == "time":
            return in_time(time.strftime("%H:%M"), c.get("from", "00:00"), c.get("to", "00:00"))
        found = self._condition_true(c, wait=wait)
        if found and want and not c.get("color_on"):
            m = self.wait_matchers.get(id(c))
            rect = getattr(m, "last_rect", None)
            if rect is not None:
                self.last_found = tuple(int(v) for v in rect)
        elif found and want and c.get("color_on") and "x" in c:
            self.last_found = (int(c["x"]), int(c["y"]), 1, 1)
        return found

    def _condition_all(self, c, wait=None):
        """The whole condition: the first one and the "more" ones, joined with AND / OR. When it
        should wait ("wait" seconds), it looks again until it's true or the time is up."""
        wait = float(c.get("wait", 0) or 0) if wait is None else wait
        deadline = time.perf_counter() + wait
        while True:
            results = []
            for one in [c] + list(c.get("more") or []):
                results.append(bool(self._condition_one(one)))
                if c.get("join") == "or" and results[-1]:
                    break
                if c.get("join", "and") == "and" and not results[-1]:
                    break
            ok = any(results) if c.get("join") == "or" else all(results)
            if ok or time.perf_counter() >= deadline or self.stop_play.is_set():
                return ok
            if self.stop_play.wait(0.25):
                return False

    def _more_retry(self, a, ctx):
        import diag

        tries = max(1, int(a.get("tries", 3)))
        check = float(a.get("check", 2.0))
        between = float(a.get("between", 0) or 0)
        c = a.get("condition", {})
        for n in range(tries):
            result = self._run_steps(a.get("actions", []), ctx)
            if result != "ok":
                return result
            if self._condition_all(c, wait=check):
                return "ok"
            if n + 1 < tries:
                self._set_note(f"Retry: try {n + 2} of {tries}...")
                if between:
                    result = self._pause(between / ctx["speed"], ctx)
                    if result != "ok":
                        return result
        fails = a.get("if_fails", "go on")
        diag.info(f"Retry: still not true after {tries} tries")
        if fails == "stop":
            self.stop_reason = f"Stopped: a Retry wasn't true after {tries} tries."
            return "stop"
        if fails == "macro":
            return self._then(a, ctx, "fail")
        return "ok"

    def _more_repeat(self, a, ctx):
        import diag

        mode = a.get("mode", "times")
        end = self._play_clock() + float(a.get("minutes", 5)) * 60
        quick = 0
        while True:
            began = self._play_clock()
            result = self._run_steps(a.get("actions", []), ctx)
            if result != "ok":
                return result
            if mode == "until" and self._condition_all(a.get("condition") or {}):
                return "ok"
            if mode == "minutes" and self._play_clock() >= end:
                return "ok"
            quick = quick + 1 if self._play_clock() - began < 0.01 else 0
            if quick > GOTO_FAST * 20:
                self.stop_reason = "Stopped: a Repeat went round 1000 times with no time passing (an endless loop)."
                diag.info(self.stop_reason)
                return "stop"
            if self.stop_play.is_set():
                return "stop"

    def _more_stop(self, a, ctx):
        reason = str(a.get("reason") or "").strip()
        self.stop_reason = f"Stopped by the macro: {reason}" if reason else None
        if a.get("ping"):
            self._macro_discord(("Stopped by the macro" + (f": {reason}" if reason else ".")), ping=True)
        return "stop"

    # -------------------------------------------------------------- macros from someone else
    def _sensitive_by_file(self):
        """{macro file key: what it does outside the game}, for the open macro and the macros it plays."""
        import macro_steps as workflow

        out, seen = {}, set()

        def go(steps, key, depth):
            parts = sensitive_parts(steps)
            if parts:
                out.setdefault(key, set()).update(parts)
            if depth > 6:
                return
            for a, _l, _i, _p in workflow.walk(steps):
                if a.get("off"):
                    continue
                keys = (("file",) if a.get("kind") == "play_macro" else ()) + MACRO_KEYS
                for k in keys:
                    found = a.get(k) and self._find_macro_file(a[k])
                    if not found:
                        continue
                    fk = self._macro_key(found)
                    if fk in seen:
                        continue
                    seen.add(fk)
                    try:
                        inner = self._read_macro_file(found)["steps"]
                    except Exception:
                        continue
                    go(inner, fk, depth + 1)
        # (also a macro that is only a recording: its keys are looked at too)
        go(self.macro_steps() or [], self._macro_key(self.current_file) if self.current_file else "", 0)
        return out

    def _trusted(self):
        saved = self.settings.get("trusted_steps")
        return saved if isinstance(saved, dict) else {}

    def trust_steps(self, key, parts):
        """Remember that you OK'd (or made) these parts of a macro (in this PC's settings, never in the file)."""
        if not parts:
            return
        store = self.settings.setdefault("trusted_steps", {}) if isinstance(self.settings.get("trusted_steps"),
                                                                            dict) else None
        if store is None:
            store = self.settings["trusted_steps"] = {}
        store[key] = sorted(set(store.get(key) or []) | set(parts))

    def check_sensitive(self):
        """(2.12) Before Play: a macro that types into another program or reads what you copied, and you
        haven't OK'd that yet (macros from someone else): ask once. No (or nobody at the PC, like a
        start from Discord): those steps are skipped this time. Returns whether they may run."""
        import diag

        trusted = self._trusted()
        new = {k: parts - set(trusted.get(k) or []) for k, parts in self._sensitive_by_file().items()}
        new = {k: v for k, v in new.items() if v}
        if not new:
            self.allow_sensitive = True
            return True
        words = sorted(set().union(*new.values()))
        ok = bool(self.boxes.askyesno(
            "A macro from someone else?",
            "This macro " + ", ".join(words) + ".\n\nIf you made it yourself, that's fine. If someone sent it to "
            "you, only allow it if you trust them.\n\nAllow it? (No: those steps are skipped this time.)"))
        if ok:
            for k, parts in new.items():
                self.trust_steps(k, parts)
            self._save_settings()
            diag.info("Allowed: this macro " + ", ".join(words))
        else:
            diag.info("Not allowed this time (those steps are skipped): this macro " + ", ".join(words))
        self.allow_sensitive = ok
        return ok

    # -------------------------------------------------------------- Discord
    def _macro_discord(self, text, png=None, to="default", channel=None, ping=False):
        """A message from a macro step. Where it goes: the step's choice, else Settings > Discord. The
        extra webhook link stays in Settings (it's a secret) and is never written to the log."""
        import diag

        s = self.settings
        if to in (None, "", "default"):
            to = s.get("discord_macro_to") if s.get("discord_macro_to") in ("cards", "channel", "webhook") else "cards"
        text = str(text)[:1900]
        pings = s.get("discord_macro_pings") is True
        if not pings:
            text = no_pings(text)  # (2.12: a macro from someone else can't ping your server)
        if ping and hasattr(self, "_ping_for"):
            who = str(s.get("discord_ping", "")).strip()
            text = (who + " " + text).strip() if who else text
        try:
            if to == "channel":
                channel = clean_channel(channel) or clean_channel(s.get("discord_macro_channel"))
                token = str(s.get("remote_token", "")).strip() if s.get("remote_enabled") else ""
                if not channel or not token:
                    diag.info("Discord message from the macro not sent: set the bot channel (Settings > Discord) "
                              "and turn the phone remote on")
                    return False
                threading.Thread(target=self._post_to_channel, args=(channel, token, text, png, pings or ping),
                                 daemon=True).start()
                return True
            if to == "webhook":
                import discord_notify

                url = str(s.get("discord_macro_webhook", "")).strip()
                if not discord_notify.is_webhook(url):
                    diag.info("Discord message from the macro not sent: the extra webhook in Settings > Discord "
                              "isn't a webhook link")
                    return False
                if getattr(self, "macro_notifier", None) is None:
                    self.macro_notifier = discord_notify.Notifier(
                        lambda: str(self.settings.get("discord_macro_webhook", "")).strip())
                return self.macro_notifier.send(text, png=png,
                                                username=str(s.get("discord_name") or "Macro Recorder"))
            if not s.get("discord_enabled") or not hasattr(self, "_send_card"):
                diag.info("Discord message from the macro not sent: Discord messages are off (Settings > Discord)")
                return False
            self._send_card(text, None, png)
            return True
        except Exception as exc:
            diag.error("Discord message from the macro failed", exc)
            return False

    def _post_to_channel(self, channel, token, text, png, pings=False):
        import diag
        import discord_remote

        try:
            picture = None
            if png is not None:
                import discord_notify

                picture = png if isinstance(png, (bytes, bytearray)) else discord_notify.encode(png)
            discord_remote.api("POST", f"https://discord.com/api/v10/channels/{channel}/messages",
                               {"content": text,
                                "allowed_mentions": {"parse": ["users", "roles", "everyone"] if pings else []}},
                               token=token, picture=picture)
        except Exception as exc:
            diag.info(f"Discord message from the macro to the bot channel failed: {exc}")
