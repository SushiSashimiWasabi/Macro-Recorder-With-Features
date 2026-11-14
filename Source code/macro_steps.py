"""A macro as a list of steps ("actions"), the way the Edit window shows it.

The simplest macro is one step: the recorded keys and mouse. In Edit, steps can be added around it
(waits, key presses, clicks, typing text, waiting for a picture...) and grouped:

  If          the steps inside run only when a condition is true (a picture shows, or doesn't)
  Repeat      the steps inside run a number of times
  Retry       the steps inside run again until a condition is true (at most a number of tries)

and Stop / Start over end the macro or start it again from step 1. A step can be turned off
(it's kept, but skipped). Every step is a dict with "kind"; groups have "actions".

Files keep the steps under "actions", and also every recorded action in "events" (played one after
another, waits included), so older versions of the app can still play the recorded parts."""

import copy
import uuid

GROUPS = ("if", "repeat", "retry")

# what "Add action" offers: kind, name, a few words
ADDABLE = [
    ("wait", "Wait", "pause for some seconds"),
    ("key", "Press a key", "a key press, or holding / letting go of a key"),
    ("type", "Type text", "types the text, letter by letter"),
    ("click", "Click", "a mouse click somewhere on the screen"),
    ("move", "Move the mouse", "to a spot on the screen"),
    ("scroll", "Scroll", "the mouse wheel up or down"),
    ("wait_picture", "Wait for a picture", "until something shows on screen (and click it)"),
    ("if", "If…", "steps that only run when a picture shows (or doesn't)"),
    ("repeat", "Repeat…", "steps that run a number of times"),
    ("retry", "Retry…", "steps that run again until a picture shows"),
    ("restart", "Start over", "start the macro again from step 1"),
    ("stop", "Stop", "end the macro here"),
    ("note", "Note", "a comment for yourself; does nothing"),
    ("record_here", "Record keys and mouse…", "record now; it goes where you choose"),
    ("insert_macro", "Insert another macro…", "copy a saved macro's actions in here, to change"),
]
NAMES = {k: n for k, n, _ in ADDABLE}
NAMES["recorded"] = "Play recorded keys and mouse"


def new_id():
    return uuid.uuid4().hex[:12]


def new_action(kind):
    a = {"id": new_id(), "kind": kind}
    defaults = {
        "wait": {"seconds": 1.0},
        "key": {"key": {"vk": 0x20}, "mode": "press", "times": 1, "hold": 0.0},
        "type": {"text": "", "delay": 0.02},
        "click": {"x": 0, "y": 0, "button": "left", "mode": "click", "hold": 0.0},
        "move": {"x": 0, "y": 0},
        "scroll": {"amount": -3},
        "wait_picture": {"png": None, "screen_h": None, "timeout": 30, "match": 85, "click": False,
                         "otherwise": "go on", "name": ""},
        "if": {"condition": {"shows": True, "png": None, "screen_h": None, "match": 85}, "actions": []},
        "repeat": {"times": 2, "actions": []},
        "retry": {"condition": {"shows": True, "png": None, "screen_h": None, "match": 85}, "tries": 3,
                  "actions": []},
        "note": {"text": ""},
        "recorded": {"events": []},
    }
    a.update(copy.deepcopy(defaults.get(kind, {})))
    return a


def from_events(events):
    """The steps of a macro that has only recorded actions (every macro before steps existed)."""
    a = new_action("recorded")
    a["events"] = events
    return [a]


def ensure_ids(actions):
    for a in actions:
        if not isinstance(a, dict):
            continue
        a.setdefault("id", new_id())
        if a.get("kind") in GROUPS:
            ensure_ids(a.setdefault("actions", []))
    return actions


def is_simple(actions):
    """Only one recorded step and nothing else (so the file needs no "actions")."""
    return len(actions) == 1 and actions[0].get("kind") == "recorded" and not actions[0].get("off")


def walk(actions, parent=None):
    """Every step (also inside groups): (step, the list it's in, its index there, the group or None)."""
    for i, a in enumerate(actions):
        yield a, actions, i, parent
        if a.get("kind") in GROUPS:
            yield from walk(a.get("actions", []), a)


def find(actions, action_id):
    for a, lst, i, parent in walk(actions):
        if a.get("id") == action_id:
            return a, lst, i, parent
    return None


def all_events(actions):
    """Every recorded action, one step after another, for older versions of the app (and for the
    things that look at all of a macro's actions, like the action count)."""
    out = []
    offset = 0.0
    for a, _lst, _i, _p in walk(actions):
        if a.get("off"):
            continue
        if a.get("kind") == "recorded" and a.get("events"):
            evs = a["events"]
            for ev in evs:
                e = dict(ev)
                e["t"] = round(offset + ev.get("t", 0.0), 4)
                out.append(e)
            offset += evs[-1].get("t", 0.0) + 0.05
        elif a.get("kind") == "wait":
            offset += float(a.get("seconds", 0))
    return out


def length(actions):
    """About how long the macro takes (seconds), groups counted once."""
    evs = all_events(actions)
    return evs[-1]["t"] if evs else 0.0


def count_events(actions):
    return sum(len(a.get("events", [])) for a, _l, _i, _p in walk(actions) if a.get("kind") == "recorded")


def map_points(actions, fn):
    """A copy of the steps with fn(list of events) applied to every recorded action's events and to
    the spots of clicks and mouse moves (used to fit a macro to another screen or window)."""
    def go(steps):
        out = []
        for a in steps:
            kind = a.get("kind")
            if kind == "recorded":
                # (fn gives new events back, so they aren't copied a second time here)
                b = {k: v for k, v in a.items() if k != "events"}
                b["events"] = fn(a.get("events", []))
            else:
                b = copy.deepcopy({k: v for k, v in a.items() if k != "actions"})
                if "actions" in a:
                    b["actions"] = go(a["actions"]) if isinstance(a["actions"], list) else a["actions"]
                if kind in ("click", "move") and "x" in a:
                    moved = fn([{"type": "move", "x": a["x"], "y": a["y"], "t": 0.0}])[0]
                    b["x"], b["y"] = moved["x"], moved["y"]
            out.append(b)
        return out
    return go(actions)


def describe(a):
    """(name, a few words) for the list in the Edit window."""
    kind = a.get("kind")
    name = NAMES.get(kind, kind or "?")
    if kind == "recorded":
        evs = a.get("events", [])
        secs = evs[-1].get("t", 0) if evs else 0
        return name, f"{len(evs):,} recorded events, {secs:.1f} s"
    if kind == "wait":
        return name, f"{float(a.get('seconds', 0)):g} s"
    if kind == "key":
        mode = {"press": "press", "down": "hold down", "up": "let go"}.get(a.get("mode"), "press")
        times = int(a.get("times", 1))
        hold = float(a.get("hold", 0) or 0)
        return name, (f"{mode} {key_text(a.get('key', {}))}" + (f" × {times}" if times > 1 and mode == "press" else "")
                      + (f", held {hold:g} s" if hold > 0 and mode == "press" else ""))
    if kind == "type":
        text = a.get("text", "")
        return name, (text[:40] + "…") if len(text) > 40 else (text or "(no text yet)")
    if kind == "click":
        mode = {"click": "", "double": "double ", "down": "hold ", "up": "let go of "}.get(a.get("mode"), "")
        hold = float(a.get("hold", 0) or 0)
        return name, (f"{mode}{a.get('button', 'left')} at {a.get('x')}, {a.get('y')}"
                      + (f", held {hold:g} s" if hold > 0 and a.get("mode", "click") == "click" else ""))
    if kind == "move":
        return name, f"to {a.get('x')}, {a.get('y')}"
    if kind == "scroll":
        n = int(a.get("amount", 0))
        return name, f"{'up' if n > 0 else 'down'} {abs(n)}"
    if kind == "wait_picture":
        limit = a.get("timeout", 30)
        what = a.get("name") or ("picture" if a.get("png") else "no picture yet")
        return name, f"{what}, up to {limit:g} s" if limit else f"{what}, no time limit"
    if kind == "if":
        return "If", condition_text(a.get("condition", {})) + f"  ({len(a.get('actions', []))} steps)"
    if kind == "repeat":
        return "Repeat", f"{int(a.get('times', 1))} times  ({len(a.get('actions', []))} steps)"
    if kind == "retry":
        return "Retry", (f"until {condition_text(a.get('condition', {}))}, at most {int(a.get('tries', 3))} "
                         f"tries  ({len(a.get('actions', []))} steps)")
    if kind == "restart":
        return name, "from step 1"
    if kind == "stop":
        return name, "the macro ends here"
    if kind == "note":
        return name, a.get("text", "")[:50]
    return name, ""


def condition_text(c):
    what = c.get("name") or ("the picture" if c.get("png") else "a picture (none chosen yet)")
    return f"{what} shows" if c.get("shows", True) else f"{what} doesn't show"


def key_text(key):
    try:
        import platform_keys

        if "special" in key:
            return key["special"].replace("_", " ").title()
        if "vk" in key:
            return platform_keys.win_vk_name(key["vk"]) or key.get("char") or f"key {key['vk']}"
    except Exception:
        pass
    return (key.get("char") or "?").upper()
