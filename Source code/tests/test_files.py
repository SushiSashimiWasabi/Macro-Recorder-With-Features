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

print()
print(f"{sum(ok for _, ok in results)} of {len(results)} passed")
