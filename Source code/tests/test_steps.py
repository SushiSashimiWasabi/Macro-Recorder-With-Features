"""Macros made of steps (the Edit window): waits, keys, typing, clicks, Repeat, If, Retry, Start over,
Stop, steps turned off, and saving / opening such a macro. No real input, no windows shown."""
import json
import os
import sys
import tempfile
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_steps_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402

import image_watch  # noqa: E402
import modern_ui  # noqa: E402
import window_tools  # noqa: E402
import macro_steps as workflow  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


root = tk.Tk()
root.withdraw()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
root.withdraw()
for name in ("showwarning", "showinfo", "showerror"):
    setattr(app.boxes, name, lambda *a, **k: None)
window_tools.foreground = lambda: None
app.settings.update(pause_when_away=False, watch_enabled=False, results_enabled=False, drops_enabled=False,
                    fit_to="screen", discord_enabled=False)
app.away_var.set(False)
app.watch_var.set(False)
app.results_var.set(False)
app.drops_var.set(False)
app.fit_var.set(modern_ui.FIT_TO["screen"])
app.macro_screen = None
sent = []
app._replay_event = lambda e, hk, hb: sent.append((round(time.perf_counter(), 3), e))


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def run(steps, limit=20, repeats=1):
    sent.clear()
    app.set_steps(steps)
    app.ready_var.set(0)
    app.loop_var.set(False)
    app.repeat_var.set(repeats)
    t0 = time.time()
    app.play()
    while app.playing and time.time() - t0 < limit:
        pump(0.03)
    return time.time() - t0


def keys(evs):
    return [(e["key"].get("vk") or e["key"].get("char") or e["key"].get("special"), e["pressed"])
            for _t, e in evs if e["type"] == "key"]


def step(kind, **kw):
    a = workflow.new_action(kind)
    a.update(kw)
    return a


A = {"vk": 65}
rec = step("recorded", events=[{"type": "key", "key": A, "pressed": True, "t": 0.0},
                               {"type": "key", "key": A, "pressed": False, "t": 0.1}])

# a recorded step, a wait, a key press: in order, with the wait
took = run([rec, step("wait", seconds=0.5), step("key", key={"vk": 66})])
k = keys(sent)
check("recorded, wait, key: all played in order", k == [(65, True), (65, False), (66, True), (66, False)], k)
gap = sent[2][0] - sent[1][0]
check("the wait waited", 0.45 <= gap <= 0.7, f"{gap:.2f} s")

# Repeat 3 times; a step turned off is skipped
r = step("repeat", times=3, actions=[step("key", key={"vk": 67}), step("key", key={"vk": 68}, off=True)])
run([r])
check("Repeat 3 times, the step turned off skipped", keys(sent) == [(67, True), (67, False)] * 3, keys(sent))

# Type text
run([step("type", text="ab c", delay=0.0)])
typed = [x for x, pressed in keys(sent) if pressed]
check("Type text", typed == ["a", "b", "space", "c"], typed)

# Click: moves there, then down and up
run([step("click", x=40, y=50, button="right", mode="click")])
kinds = [(e["type"], e.get("pressed")) for _t, e in sent]
check("Click", kinds == [("move", None), ("click", True), ("click", False)] and sent[1][1]["button"] == "right",
      kinds)

# a click held for 0.4 s, a key held for 0.3 s
run([step("click", x=5, y=5, button="left", mode="click", hold=0.4)])
downs = [t for t, e in sent if e["type"] == "click" and e["pressed"]]
ups = [t for t, e in sent if e["type"] == "click" and not e["pressed"]]
check("Click held for 0.4 s", downs and ups and 0.35 <= ups[0] - downs[0] <= 0.6, round(ups[0] - downs[0], 2) if ups else None)
run([step("key", key={"vk": 80}, hold=0.3)])
k_down = [t for t, e in sent if e["type"] == "key" and e["pressed"]]
k_up = [t for t, e in sent if e["type"] == "key" and not e["pressed"]]
check("Key held for 0.3 s", k_down and k_up and 0.25 <= k_up[0] - k_down[0] <= 0.5, round(k_up[0] - k_down[0], 2))

# If with a picture: runs only when the picture is on the (fake) screen
pic = np.zeros((30, 60, 3), np.uint8)
pic[5:25, 5:55] = (40, 200, 240)
pic[12:18, 10:50] = 255
blank = np.full((app.screen_h, app.screen_w, 3), 30, np.uint8)
with_pic = blank.copy()
with_pic[500:530, 900:960] = pic
screen = {"img": blank}
image_watch.grab_screen = lambda sct=None, region=None: screen["img"].copy()
cond = {"shows": True, "png": image_watch.png_data(pic), "screen_h": app.screen_h, "match": 85}
if_step = step("if", condition=dict(cond), actions=[step("key", key={"vk": 69})])
run([if_step, step("key", key={"vk": 70})])
check("If: picture not there, its steps skipped", keys(sent) == [(70, True), (70, False)], keys(sent))
screen["img"] = with_pic
run([if_step, step("key", key={"vk": 70})])
check("If: picture there, its steps run", keys(sent) == [(69, True), (69, False), (70, True), (70, False)],
      keys(sent))
not_step = step("if", condition=dict(cond, shows=False), actions=[step("key", key={"vk": 71})])
run([not_step])
check("If doesn't show: skipped while it shows", keys(sent) == [], keys(sent))

# Retry until the picture shows: the picture shows after the 2nd try
screen["img"] = blank
tries = {"n": 0}
orig = app._run_steps


def counting(steps, ctx):
    if steps and steps[0].get("id") == "inner":
        tries["n"] += 1
        if tries["n"] == 2:
            screen["img"] = with_pic
    return orig(steps, ctx)


app._run_steps = counting
inner = step("key", key={"vk": 72})
inner["id"] = "inner"
run([step("retry", condition=dict(cond), tries=5, actions=[inner])], limit=30)
app._run_steps = orig
check("Retry: ran again until the picture showed (2 tries)", tries["n"] == 2, tries)

# Stop ends the macro; the steps after it don't play
run([step("key", key={"vk": 73}), step("stop"), step("key", key={"vk": 74})])
check("Stop: nothing after it", keys(sent) == [(73, True), (73, False)] and app.stop_reason is None, keys(sent))

# Start over: runs from step 1 again, and stops itself if it loops too fast
run([step("key", key={"vk": 75}), step("restart")], limit=20)
check("Start over: stopped by its safety limit", app.stop_reason and "Start over" in app.stop_reason,
      app.stop_reason)
check("Start over: played 11 times", keys(sent).count((75, True)) == 11, keys(sent).count((75, True)))

# save and open a macro with steps
app.set_steps([rec, step("wait", seconds=1.0), step("repeat", times=2, actions=[step("key", key={"vk": 76})])])
path = os.path.join(tmp, "steps.macro")
modern_ui.filedialog.asksaveasfilename = lambda **k: path
app.name_var.set("steps")
app.save()
data = json.load(open(path, encoding="utf-8"))
check("saved: the steps are in the file", [a["kind"] for a in data["actions"]] == ["recorded", "wait", "repeat"])
check("saved: older versions still get the recorded part", len(data["events"]) == 2)
app.set_steps(workflow.from_events([]))
app.load(path, quiet=True)
check("opened: the steps come back", app.actions and [a["kind"] for a in app.actions] == ["recorded", "wait", "repeat"])
simple_path = os.path.join(tmp, "simple.macro")
app.set_steps([rec])
check("one recorded step is a plain macro", app.actions is None and len(app.events) == 2)

print()
print(f"{sum(ok for _, ok in results)} of {len(results)} passed")
root.destroy()
