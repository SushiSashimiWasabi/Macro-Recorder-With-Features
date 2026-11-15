"""Macro files: smaller mouse paths (simplify / expand), the compact file layout, AutoHotkey."""
import io
import json
import math
import os
import sys
import tempfile

src = sys.argv[1]
sys.path.insert(0, src)
import importers  # noqa: E402
import macro_recorder as core  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


# a recording: a straight drag, a curve, a pause, clicks and a camera turn in between
ev, t, x, y = [], 0.0, 100, 100
for k in range(200):
    t += 0.01
    x += 3
    ev.append({"type": "move", "x": x, "y": y, "t": round(t, 4)})
ev.append({"type": "click", "x": x, "y": y, "button": "left", "pressed": True, "t": round(t, 4)})
for k in range(150):
    t += 0.01
    ev.append({"type": "move", "x": round(x + 200 * math.sin(k / 30)), "y": round(y + 200 * (1 - math.cos(k / 30))),
               "t": round(t, 4)})
ev.append({"type": "click", "x": ev[-1]["x"], "y": ev[-1]["y"], "button": "left", "pressed": False, "t": round(t, 4)})
ev.append({"type": "move_rel", "dx": 30, "dy": -2, "t": round(t + 0.01, 4)})
t += 2.0
for k in range(100):
    t += 0.01
    ev.append({"type": "move", "x": 500 - k * 2, "y": 500 + k, "t": round(t, 4)})

saved = core.simplify_moves(ev)
opened = core.expand_moves(saved)
moves = [e for e in ev if e["type"] == "move"]
check("smaller paths: far fewer points saved", sum(e["type"] == "move" for e in saved) < len(moves) / 5,
      sum(e["type"] == "move" for e in saved))
check("smaller paths: all points back when opened", sum(e["type"] == "move" for e in opened) == len(moves))


def pos_at(evs, when):
    last = None
    for q in evs:
        if q["t"] > when + 1e-9:
            break
        if q["type"] == "move":
            last = (q["x"], q["y"])
    return last


worst = max(max(abs(a - b) for a, b in zip(pos_at(ev, q["t"]), pos_at(opened, q["t"]))) for q in moves)
check("smaller paths: same movement within 1 px", worst <= 1, f"{worst} px")
check("smaller paths: clicks and camera turns untouched",
      [e for e in ev if e["type"] != "move"] == [e for e in opened if e["type"] != "move"])
check("smaller paths: nothing to do for a macro without moves",
      core.expand_moves(core.simplify_moves([e for e in ev if e["type"] != "move"]))
      == [e for e in ev if e["type"] != "move"])

# compact layout reads back the same
buf = io.StringIO()
core.dump_macro({"app": "macro_recorder", "version": 1, "events": ev}, buf)
check("compact file reads back the same", json.loads(buf.getvalue())["events"] == ev)

# AutoHotkey: variables, loops, export and read back
tmp = tempfile.mkdtemp(prefix="mr_files_")
path = os.path.join(tmp, "a.ahk")
open(path, "w").write('d := 100\nLoop 3 {\n  Send "{Blind}x"\n  Sleep d * 2\n}\nClick 50, 60\n')
r = importers.import_file(path)
check("ahk: loop with a variable sleep", sum(e["type"] == "key" for e in r.events) == 6 and r.events[-1]["type"] == "click")
open(path, "w", encoding="utf-8").write(importers.export_ahk(r.events, "t"))
r2 = importers.import_file(path)
check("ahk: a saved script reads back", len(r2.events) >= len(r.events))
open(path, "w").write("x := 9**9**9\nSleep x\nSend a\n")
check("ahk: no huge sums", importers.import_file(path) is not None)

# a mouse press that was never let go of (like the click on Record) is left out, so it isn't held all run
L = lambda p, t: {"type": "click", "x": 1, "y": 1, "button": "left", "pressed": p, "t": t}
stray = [L(True, 0.0), {"type": "move", "x": 5, "y": 5, "t": 0.1}, L(True, 0.5), L(False, 0.6), L(False, 0.9)]
kept = core.drop_stray_clicks(stray)
check("stray presses left out, the real click kept", [(e["type"], e.get("pressed")) for e in kept] ==
      [("move", None), ("click", True), ("click", False)], kept)

# a macro file made of steps can't add up to more than MAX_EXPANDED actions, or nest groups too deep
glide = [{"type": "move", "x": 0, "y": 0, "t": 0.0}, {"type": "move", "x": 100, "y": 0, "t": 9.0, "s": 1}]
many = [{"kind": "recorded", "events": [dict(e) for e in glide]} for _ in range(3000)]
try:
    core.expand_steps(many)
    check("steps file: one limit for all its parts", False)
except ValueError:
    check("steps file: one limit for all its parts", True)
deep = cur = {"kind": "repeat", "actions": []}
for _ in range(core.MAX_NESTING + 5):
    cur["actions"].append({"kind": "repeat", "actions": []})
    cur = cur["actions"][0]
try:
    core.expand_steps([deep])
    check("steps file: groups nested too deep refused", False)
except ValueError:
    check("steps file: groups nested too deep refused", True)


# ---- (2.9.1) nothing of this PC in a saved .macro: other macros by name / relative path only
tmpd = tempfile.mkdtemp(prefix="mr_files_")
home = os.path.join(tmpd, "Users", "SomeName")
folder = os.path.join(home, "macros")
os.makedirs(os.path.join(folder, "parts"))
inside = os.path.join(folder, "parts", "Part A.macro")
outside = os.path.join(home, "Desktop", "Rejoin.macro")
data = {"app": "macro_recorder", "events": [],
        "actions": [{"kind": "play_macro", "file": inside, "on_fail": outside, "id": 1},
                    {"kind": "repeat", "actions": [{"kind": "play_macro", "file": outside, "id": 3}], "id": 2}],
        "watch_pictures": [{"png": "AAAA", "screen_h": 1440, "name": "Disconnected", "action": "recover",
                            "macro": outside, "also": "picture_1.png", "confirm_file": "picture_2.png",
                            "macros": [outside], "key": {"vk": 13}, "cooldown": 5, "match": 300}]}
path = os.path.join(folder, "Main.macro")
with open(path, "w", encoding="utf-8") as f:
    core.dump_macro(data, f)
text = open(path, encoding="utf-8").read()
back = json.loads(text)
check("saved macro: no whole paths (no user name) inside", "SomeName" not in text and tmpd not in text
      and "Users" not in text, text[:300])
a = back["actions"]
check("saved macro: a chain step in the macro's folder is kept relative to it",
      a[0]["file"].replace("\\", "/") == "parts/Part A.macro", a[0])
check("saved macro: a macro outside its folder: only its file name", a[0]["on_fail"] == "Rejoin.macro"
      and a[1]["actions"][0]["file"] == "Rejoin.macro", a)
pic = back["watch_pictures"][0]
check("saved macro: a picture's rejoin macro by file name only, no other files of this PC",
      pic["macro"] == "Rejoin.macro" and not any(k in pic for k in ("also", "confirm_file", "macros")), pic)
check("saved macro: a picture's values are checked (Match % 300 -> 99)", pic["match"] == 99 and pic["key"] == {"vk": 13})
check("the macros in memory keep their whole paths", data["actions"][0]["file"] == inside
      and data["watch_pictures"][0]["macro"] == outside)

# opening someone's macro: only known actions and sensible values come in
odd = {"action": "format_disk", "macro": r"C:\Windows\..\evil\x.macro", "key": "rm -rf", "cooldown": -5,
       "tries": 10 ** 9, "seconds": float("nan"), "click": "yes", "name": "x" * 500, "confirm_file": r"..\..\a.png"}
got = core.shared_picture_fields(odd, folder=folder)
check("opened picture: unknown action dropped", "action" not in got, got)
check("opened picture: its macro is looked for beside the opened macro, by file name",
      got.get("macro") == os.path.join(folder, "x.macro"), got.get("macro"))
check("opened picture: odd values dropped or kept in range",
      "key" not in got and got.get("cooldown") == 0 and got.get("tries") == 20 and "seconds" not in got
      and "click" not in got and len(got.get("name", "")) == 60 and "confirm_file" not in got, got)
check("opened picture: a macro that isn't a .macro file is dropped",
      "macro" not in core.shared_picture_fields({"macro": r"C:\tools\run.bat", "action": "play"}, folder))
check("shared path: '..' never leaves the folder", core.shared_macro_path(r"..\..\x.macro", None) == "x.macro")

# a chain step saved relative is found again from the open macro
class _App:
    current_file = path
    _find_macro_file = core.MacroRecorder._find_macro_file
open(inside, "w").close()
check("a relative chain step is found from the open macro's folder",
      os.path.normcase(_App()._find_macro_file("parts/Part A.macro")) == os.path.normcase(inside))
check("a chain step with '..' doesn't leave the folder", _App()._find_macro_file(r"..\Desktop\Rejoin.macro") is None)

print()
print(f"{sum(ok for _, ok in results)} of {len(results)} passed")
