"""2.12 preview 3, the bug hunt: edge cases that try to break the new features (timed start, the stuck run
guard, colour checks, counting, Picture watch copy/drag, the late result fix, the phone remote).

Known bugs found by this hunt are checked with known_bug(): it passes while the bug is still there (so the
suite stays green until the owner OKs the fix) and prints "KNOWN BUG". When a fix lands it prints "FIXED" and
fails, so the check can then be turned into a normal one.

No real input is sent to any game, no real Discord, no real message box, a throwaway settings folder.
The only real screen use is a 1x1 screenshot (never a window, never input)."""
import json
import os
import sys
import tempfile
import threading
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_p3e_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402

import color_check  # noqa: E402
import image_watch  # noqa: E402
import macro_steps as workflow  # noqa: E402
import modern_ui  # noqa: E402
import remote_ui  # noqa: E402
import run_history  # noqa: E402
import stats  # noqa: E402
import timed_start_ui  # noqa: E402
import window_tools  # noqa: E402

results = []
known = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


def known_bug(name, bug_shows, info=""):
    """A bug found by the hunt, not fixed yet (waiting for the owner's OK)."""
    known.append(name)
    results.append((name, bool(bug_shows)))
    print(("PASS KNOWN BUG " if bug_shows else "FAIL FIXED (make it a normal check) ") + name
          + (f"  [{info}]" if info else ""))


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
        return None
    except Exception as exc:  # noqa: BLE001
        return exc


root = tk.Tk()
root.withdraw()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
root.withdraw()
asked = []
for name in ("showwarning", "showinfo", "showerror"):
    setattr(app.boxes, name, lambda *a, _n=name, **k: asked.append((_n, a)))
app.boxes.askyesno = lambda *a, **k: True
app.boxes.askyesnocancel = lambda *a, **k: False
modern_ui.messagebox.showwarning = lambda *a, **k: asked.append(("warning", a))
window_tools.foreground = lambda: None
app.settings.update(pause_when_away=False, drops_enabled=False, discord_enabled=False)
app.away_var.set(False)
app.watch_var.set(False)
app.result_pictures = []
app._save_settings()
app._sound = lambda name, *a, **k: None


def pump(seconds=0.1):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


# ------------------------------------------------------------ timed start: odd times
pw = timed_start_ui.parse_when
check("parse_when: 24:00 / 12:60 / -5 / nan / inf / text are refused",
      all(pw(t) is None for t in ("24:00", "12:60", "-5", "nan", "inf", "soon", "", None, "1e9")))
check("parse_when: 00:00 just before midnight is in a few seconds' time",
      0 < pw("00:00", now=time.mktime((2026, 11, 18, 23, 59, 50, 0, 0, -1)))
      - time.mktime((2026, 11, 18, 23, 59, 50, 0, 0, -1)) <= 10)
ch = timed_start_ui.clean_hhmm
check("clean_hhmm: 7:5 -> 07:05, bad ones refused", ch("7:5") == "07:05" and ch("25:61") is None
      and ch("07:30:00") is None and ch(None) is None and ch(["7", "5"]) is None and ch("-1:30") is None)
# alarm at midnight
app._set_schedule(alarm_on=True, alarm="00:00", daily=True, alarm_last="", timer_on=False, when="play")
midnight = time.mktime((2026, 11, 19, 0, 0, 20, 0, 0, -1))
check("alarm 00:00: fires just after midnight", app._schedule_due(midnight)[0])
check("alarm 00:00: not just before midnight", not app._schedule_due(midnight - 40)[0])
# DST: Europe-style spring forward is not in this PC's zone, but a time that doesn't exist must not crash
check("alarm: a 02:30 alarm on any day never crashes",
      raises(app._schedule_due, time.mktime((2026, 3, 29, 2, 40, 0, 0, 0, -1))) is None)
# settings someone edited by hand
app.settings["schedule"] = {"alarm_on": "yes", "alarm": "99:99", "timer_on": 1, "timer_min": "1e400",
                            "timer_from": "soon", "when": "moon", "daily": None}
sc = app._schedule()
check("schedule from broken settings: cleaned (nothing on, sane values)", not sc["alarm_on"] and not sc["timer_on"]
      and sc["alarm"] != "99:99" and sc["when"] == "play" and sc["timer_from"] == 0.0, sc)
# the PC clock goes back an hour: the timer's start is in the future
app._set_schedule(alarm_on=False, timer_on=True, timer_min=5, timer_repeat=False, timer_from=time.time() + 3600)
app._schedule_due(time.time())
due = app._schedule_due(time.time() + 6 * 60)[1]
check("timer: after the PC clock goes back, it counts from now (not an extra hour)", due)
app._set_schedule(timer_on=False)

# cancel while it waits for a run's end
app.playing = True
plan = app.plan_timed_start(time.time() - 1, "timer")
app._timed_countdown(plan)
waiting = app.restart_after_run is plan
app.cancel_timed_start("cancelled from Discord")
check("timed start: was waiting for the run's end", waiting)
check("timed start: Cancel while it waits for the run's end clears the wait too",
      getattr(app, "restart_after_run", None) is None)
plan = app.plan_timed_start(time.time() - 1, "timer")
app._timed_countdown(plan)
app.stop_playback()
check("timed start: Stop (F12) while it waits for the run's end cancels it", getattr(app, "restart_after_run", None)
      is None and app.timed_plan is None)
app.stop_play.clear()
app.restart_after_run = None
app.playing = False
app.timed_plan = None

# ------------------------------------------------------------ colour checks: odd values
bad = {"color_on": True, "rgb": [float("inf"), 0, 0], "where": "spot", "x": 1, "y": 1}
err = raises(color_check.clean, dict(bad))
check("colour from a shared file: rgb 1e400 (inf) becomes no colour", err is None
      and color_check.clean(dict(bad))["rgb"] is None, repr(err))
err = raises(workflow.clean_color_step, {"kind": "wait_picture", **bad})
check("colour: a macro with rgb 1e400 opens", err is None, repr(err))
h = color_check.clean({"color_on": True, "rgb": [float("nan"), 2, 3], "tolerance": float("nan"), "hold": "inf",
                       "where": ["area"], "area": [5], "x": 1e400, "y": "x"})
check("colour: nan / text / lists in a shared file are cleaned", h["rgb"] is None and h["tolerance"] == 10
      and h["hold"] == 60.0 and h["where"] == "spot" and h["area"] == 1 and h["x"] == 0 and h["y"] == 0, h)
check("colour: rgb with 2 or 4 numbers is refused", color_check.clean({"color_on": True, "rgb": [1, 2]})["rgb"]
      is None and color_check.clean({"color_on": True, "rgb": [1, 2, 3, 4]})["rgb"] is None)
asked_size = []
real_grab = image_watch.grab_part
image_watch.grab_part = lambda x0, y0, x1, y1: (asked_size.append((x1 - x0, y1 - y0)),
                                                (np.zeros((2, 2, 3), np.uint8), (x0, y0)))[1]
zero = color_check.clean({"color_on": True, "rgb": [1, 2, 3], "where": "area", "x0": 50, "y0": 50, "x1": 50,
                          "y1": 50})
check("colour: a zero-size drawn area doesn't crash (looks at 1 pixel)", raises(color_check.seen, zero) is None
      and asked_size[-1] == (1, 1), asked_size[-1:])
huge = color_check.clean({"color_on": True, "rgb": [1, 2, 3], "where": "area", "x0": -999999, "y0": -999999,
                          "x1": 999999, "y1": 999999})
color_check.look(huge)
w, hh = asked_size[-1]
box = color_check.screens_box()
check("colour: a huge area is cut to the real screens", w <= box[2] - box[0] and hh <= box[3] - box[1],
      f"{w} x {hh}, screens {box}")
image_watch.grab_part = real_grab
# the owner's second screen is at -1920, 0: a spot there is read from that screen
if os.environ.get("CI"):
    print("SKIP (PC only) colour: a spot on the left screen (negative x) can be read (needs a second screen)")
else:
    err = raises(image_watch.grab_part, -1900, 10, -1899, 11)
    check("colour: a spot on the left screen (negative x) can be read", err is None, repr(err))
check("colour: describe() never crashes on half-filled entries",
      all(raises(color_check.describe, d) is None for d in ({}, {"where": "area"}, {"rgb": "x"}, {"where": "screen"})))

# ------------------------------------------------------------ counters
check("counter values: 1e400, nan, True, '5', 2.5 are cleaned", workflow.clean_whole("1e400") == 0
      and workflow.clean_whole(float("nan")) == 0 and workflow.clean_whole(True) == 0
      and workflow.clean_whole("5") == 5 and workflow.clean_whole(2.5) == 0 and workflow.clean_whole(10**12)
      == workflow.COUNTER_LIMIT)
check("counter names: invisible / right-to-left / empty / Thai", workflow.clean_counter_name("\u202eevil") == "evil"
      and workflow.clean_counter_name("   ") == "Counter" and workflow.clean_counter_name("ไอเทม") == "ไอเทม")
app.settings["counter_values"] = {app._counters_key(): {"Drops": "1e400", "Bad": [1], "Huge": 10**30}}
steps = [dict(workflow.new_action("counter_add"), counter="Drops", keep=True),
         dict(workflow.new_action("counter_add"), counter="Huge", keep=True)]
err = raises(app._start_counters, steps)
check("kept counters: broken saved values start at 0 or the limit, no crash", err is None
      and app.counters.get("Drops") == 0 and app.counters.get("Huge") == 10 ** 9,
      (err, getattr(app, "counters", None)))
# two threads adding at once (Picture watch counting + a counter step)
app.counters = {"Drops": 0}
step = dict(workflow.new_action("counter_add"), counter="Drops", amount=1)


def add_many():
    for _ in range(20000):
        app._counter_step(step, {})


def count_many():
    for _ in range(20000):
        app._count_now({"counter": "Drops", "amount": 1}, "x")


real_info = core.diag.info
core.diag.info = lambda *a, **k: None
t1, t2 = threading.Thread(target=add_many), threading.Thread(target=count_many)
t1.start(), t2.start()
t1.join(), t2.join()
core.diag.info = real_info
total = app.counters.get("Drops")
check("counters: a counting picture and a counter step at the same moment don't lose a count", total == 40000,
      f"{total} of 40000")

# ------------------------------------------------------------ the late result fix: more cases
real = {k: getattr(app, k) for k in ("_run_result", "_count_drops", "_kinds_found", "_run_finished")}
app.result_matchers = ["stand-in"]
app._count_drops = lambda: 0
app._kinds_found = lambda: {"win": True, "loss": True}
app._run_finished = lambda count, how: None


def run_ends(seconds, status=stats.UNKNOWN):
    app._run_result = lambda began, whole_screen=False: status
    app.run_began = (time.perf_counter() - seconds, app._play_clock() - seconds)
    return app._finish_run(len(app.session.runs) + 1, "picture")


app.session = stats.Session("Edge")
app.late_result = None
run_ends(200)
check("late: two results in a row: the first goes to the Unknown run", app._give_late_result("win"))
check("late: the second is the current run's own (not given again)", not app._give_late_result("loss")
      and app.session.runs[-1][0] == "win")
run_ends(10, "loss")  # the leftover
app.late_result = None
# Stop during the 30 s: a new Play starts clean
run_ends(200)
app.late_result = None  # (what Play does)
check("late: after Stop and Play again, an old Unknown run doesn't get the new session's result",
      not app._give_late_result("win"))
# short runs: every run is under 30 s
app.session = stats.Session("Short runs")
for _ in range(3):
    run_ends(20, stats.WIN)      # the usual run here: 20 s
run_ends(20)                     # really unknown (the result was missed)
out = run_ends(20, stats.WIN)    # a real won run of 20 s
check("late: with 20 s runs, a real won run after an Unknown one is its own run (window 10 s)",
      out is not False and len(app.session.runs) == 5 and app.session.runs[3][0] == "unknown", app.session.runs)
app.session = stats.Session("Short runs 2")
for _ in range(3):
    run_ends(20, stats.WIN)
run_ends(20)
out = run_ends(4, stats.WIN)     # only the results screen (4 s)
check("late: with 20 s runs, a 4 s leftover still goes to the Unknown run", out is False
      and app.session.runs[-1][0] == "win" and len(app.session.runs) == 4, app.session.runs)
for k, v in real.items():
    setattr(app, k, v)
app.result_matchers = []
app.late_result = None

# ------------------------------------------------------------ phone remote: odd /schedule input
app.events, app.actions = [], [workflow.new_action("wait")]
answers = {}
for v in ("25:61", "-5", "abc", "７:３０", "12:30:45", "", {"timer": "abc"}, {"timer": -5}, {"timer": 10**20},
          {"timer": "1e9"}, {"alarm": "off"}, {"alarm": 5}):
    try:
        answers[str(v)] = app.remote_schedule(v, "ทดสอบ")
    except Exception as exc:  # noqa: BLE001
        answers[str(v)] = exc
check("/schedule: bad input never crashes", not any(isinstance(a, Exception) for a in answers.values()), answers)
check("/schedule: 25:61 and -5 are refused with a hint", "00:00 to 23:59" in answers["25:61"]
      and "00:00 to 23:59" in answers["-5"])
check("/schedule: a huge timer is held at 24 h", app._schedule()["timer_min"] <= 1440)
check("/schedule: an alarm that isn't a time (5) gets the hint", "00:00 to 23:59" in answers["{'alarm': 5}"])
app.remote_schedule("cancel", "x")
app.cancel_timed_start()
long_name = "ไอเทม" * 400
app.name_var.set(long_name)
app.counters = {("ตัวนับ" * 50 + str(i)): i for i in range(40)}
lines = "\n".join(app._remote_settings_lines())
check("/status lines: very long Thai names stay short (Discord's 2000 letter limit)", len(lines) < 1500, len(lines))
app.counters = {}
leak = remote_ui.remote_log_text(r"Saved C:\Games\Macro Recorder\saved macro file\Farm.macro")
check("/log: a path with spaces is hidden whole", "Macro Recorder" not in leak and "Farm" not in leak
      and leak.startswith("Saved [a file]"), leak)
check("/log: links and words around paths stay", remote_ui.remote_log_text("see https://x.com/a and C:/a b/c.txt ok")
      == "see https://x.com/a and [a file] ok")
for _p in ("Opened /Users/someone/My Macros/Farm.macro now", "Opened ~/My Stuff/a b/Farm.macro now",
           "Opened /home/bob/Data dir/Farm.macro now", "Opened ~\\My Macros\\Farm.macro now"):
    _clean = remote_ui.remote_log_text(_p)
    if _clean != "Opened [a file] now":
        check("/log: Mac / Linux paths (and ~\\...) with spaces are hidden whole", False, (_p, _clean))
        break
else:
    check("/log: Mac / Linux paths (and ~\\...) with spaces are hidden whole", True)
check("/log: no Windows user name in it", (os.environ.get("USERNAME") or "zzzz").lower()
      not in remote_ui.remote_log_text(os.path.expanduser("~") + r"\x.txt").lower())

# ------------------------------------------------------------ start-up entry with spaces / Thai in the path
real_exe, real_frozen = sys.executable, getattr(sys, "frozen", False)
sys.executable, sys.frozen = r"D:\เกม ทดสอบ\Macro Recorder\MacroRecorder.exe", True
cmd = app._startup_command()
sys.executable = real_exe
if real_frozen:
    sys.frozen = real_frozen
else:
    del sys.frozen
check("start-up: an exe path with spaces and Thai letters is quoted", cmd.startswith('"D:\\เกม ทดสอบ\\Macro Recorder'
                                                                                  '\\MacroRecorder.exe" '), cmd)

# ------------------------------------------------------------ Picture watch: copy / drag edge cases
app.boxes.askyesno = lambda *a, **k: True
win = app.open_picture_watch(core.GROUP_MINE) or app.picture_win
pump(0.3)
os.makedirs(core.watch_dir(), exist_ok=True)


def new_pic(name, write=True):
    file = f"{name}.png"
    if write:
        image_watch.save_image(os.path.join(core.watch_dir(), file), np.full((20, 40, 3), 90, np.uint8))
    e = {"file": file, "screen_h": 1080, "kind": None, "name": name, "group": core.GROUP_MINE}
    win.pics.append(win._with_uid(e))
    return e


a, b = new_pic("same"), new_pic("same2")
b["name"] = "same"
gone = new_pic("gone", write=False)
win.select_group(core.GROUP_MINE)
pump(0.1)
n_undo = len(win.undo_stack)
win.pics_tree.selection_set([str(a["_uid"])])
win._drop_on_group([], core.GROUP_MINE)
check("Picture watch: dropped on its own group: nothing changes, no Undo step", len(win.undo_stack) == n_undo
      and a["group"] == core.GROUP_MINE)
win.pics_tree.selection_set([str(a["_uid"]), str(b["_uid"])])
win.duplicate_pictures()
copies = [e for e in win.pics if e.get("name") == "same" and e not in (a, b)]
check("Picture watch: two pictures with the same name duplicate fine (own files)", len(copies) == 2
      and len({e["file"] for e in copies}) == 2, [e["file"] for e in copies])
win.pics_tree.selection_set([str(gone["_uid"])])
err = raises(win.duplicate_pictures)
check("Picture watch: duplicating a picture whose file is missing doesn't crash", err is None, repr(err))
win.pics_tree.selection_set([str(e["_uid"]) for e in win.pics if e["group"] == core.GROUP_MINE])
n = len([e for e in win.pics if e["group"] == core.GROUP_MINE])
win.remove_picture()
win.undo()
check("Picture watch: Undo after removing more than 5 brings all of them back",
      len([e for e in win.pics if e["group"] == core.GROUP_MINE]) == n)
win.win.destroy()

# ------------------------------------------------------------ the new actions: trying to break them
import step_more  # noqa: E402

app.result_matchers = []
app.ready_var.set(0)
app.loop_var.set(False)
app.repeat_var.set(1)
sent_new = []
real_replay = app._replay_event
app._replay_event = lambda e, hk, hb: sent_new.append(e)
real_windows, real_front = window_tools.windows_of, window_tools.force_to_front
window_tools.windows_of = lambda exe: []
window_tools.force_to_front = lambda hwnd: True


def play_steps(steps):
    sent_new.clear()
    app.stop_reason = None
    app.set_steps(steps)
    app.play()
    t0 = time.time()
    while app.playing and time.time() - t0 < 20:
        pump(0.03)
    pump(0.1)


def new(kind, **kw):
    a = workflow.new_action(kind)
    a.update(kw)
    return a


play_steps([new("type", text="hello", window={"exe": "gone.exe", "title": ""})])
check("new: Type into a program that isn't open types nothing (and says so)", not sent_new
      and "isn't open, nothing was typed" in open(core.diag.log_path(), encoding="utf-8").read())
real_write = step_more.write_clipboard_text
step_more.write_clipboard_text = lambda t: False
window_tools.windows_of = lambda exe: [1]
play_steps([new("type", text="ab", how="paste", window={"exe": "x.exe", "title": ""})])
check("new: when pasting fails, it types letter by letter instead", [e["key"].get("char") for e in sent_new
                                                                     if e.get("pressed")] == ["a", "b"])
step_more.write_clipboard_text = real_write
window_tools.windows_of = lambda exe: []
app.counters = {"T": 10 ** 9}
app._more_maths(new("maths", counter="T", a={"counter": "T"}, op="+", b={"number": 1}), {"speed": 1})
check("new: a counter at 1,000,000,000 + 1 stays at the limit", app.counters["T"] == 10 ** 9)
app._more_maths(new("maths", counter="T", a={"number": -10 ** 9}, op="*", b={"number": 10 ** 9}), {"speed": 1})
check("new: a huge negative result stops at -1,000,000,000", app.counters["T"] == -10 ** 9)
# a kept counter with decimals survives a restart of Play
steps = [new("maths", counter="Avg", a={"number": 7}, op="/", b={"number": 2}, decimals=2, keep=True)]
play_steps(steps)
app._start_counters(steps)
check("new: a kept counter with decimals comes back as 3.5", app.counters.get("Avg") == 3.5, app.counters)
# an Else after an If that's turned off
play_steps([new("if_counter", counter="Z", at_least=99, off=True, actions=[]),
            new("else", actions=[new("key", key={"vk": 70})])])
check("new: an Else after a turned-off If doesn't run", not sent_new)
# labels: two with the same name: the first one
app.counters = {}
play_steps([new("label", name="L"), new("counter_add", counter="C"), new("label", name="L"),
            new("if_counter", counter="C", at_least=3, actions=[new("stop")]), new("goto", label="L", limit=10)])
check("new: two Labels with the same name: Go to jumps to the first", app.counters.get("C") == 3, app.counters)
# speed 0 or less from a file
s0 = step_more.clean_step({"kind": "set_speed", "speed": 0})
check("new: Set speed 0 from a file becomes 0.01 (never stands still or divides by 0)", s0["speed"] == 0.01)
# deep nesting of conditions from a file
deep = {"kind": "if", "condition": {"type": "counter", "more": [{"type": "counter", "more": [{"type": "x"}]}]}}
step_more.clean_step(deep)
check("new: AND / OR conditions can't be nested inside each other (from a file)",
      "more" not in deep["condition"]["more"][0])
window_tools.windows_of, window_tools.force_to_front = real_windows, real_front
app._replay_event = real_replay

passed = sum(1 for _n, ok in results if ok)
print(f"\nKnown bugs still there: {len(known)}")
print(f"\n{passed} of {len(results)} passed")
root.destroy()
sys.exit(0 if passed == len(results) else 1)
