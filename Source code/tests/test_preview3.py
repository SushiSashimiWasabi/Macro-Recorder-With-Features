"""2.12 preview 3: the stuck run guard, colour checks, timed start / start-up and the phone remote's
/speed /repeat /log /schedule. No real input is sent to any game, no real Discord, no real message box,
a throwaway settings folder. (The start-up test adds and removes a test entry in Windows' start-up list.)"""
import json
import os
import sys
import tempfile
import threading
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_p3_")
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
import sounds  # noqa: E402
import timed_start_ui  # noqa: E402
import window_tools  # noqa: E402

def core_text(folder):
    """macro_recorder.py and the core_*.py files the core class is built from (it was split in 2.13)."""
    import glob

    parts = [os.path.join(folder, "macro_recorder.py")] + sorted(glob.glob(os.path.join(folder, "core_*.py")))
    return "".join(open(p, encoding="utf-8").read() for p in parts)


results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


def windows_only(name):
    """(2.12) A check for a feature that only exists on Windows: on other systems it's skipped (printed as
    "SKIP (Windows only)" and counted in the summary), never run."""
    if sys.platform == "win32":
        return False
    print("SKIP (Windows only) " + name)
    return True


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
app.switch_prog_var.set(False)
app.ready_var.set(0)
app.recover_count_var.set(0)
app._save_settings()
played_sounds = []
app._sound = lambda name, *a, **k: played_sounds.append(name)
sent = []
app._replay_event = lambda e, hk, hb: sent.append(e)


def pump(seconds=0.1):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def key(vk, t, pressed=True):
    return {"type": "key", "key": {"vk": vk}, "pressed": pressed, "t": t}


def rec(vk):
    a = workflow.new_action("recorded")
    a["events"] = [key(vk, 0.0), key(vk, 0.03, False)]
    return a


def wait_play(limit=15):
    t0 = time.time()
    while app.playing and time.time() - t0 < limit:
        pump(0.03)
    pump(0.1)


# ------------------------------------------------------------ 1. the stuck run guard
check("stuck guard: off at first", not app._stuck_settings()["on"])
for i in range(5):
    run_history.add("Farm", "win", 80, 0, t=time.time() - 100 * i)
check("stuck guard: suggests about 3 runs (at least 3 min)", app.stuck_minutes_suggested("Farm") == 4,
      app.stuck_minutes_suggested("Farm"))
check("stuck guard: 10 min when there are no runs yet", app.stuck_minutes_suggested("Nothing yet") == 10)
clock = {"t": 1000.0}
app._play_clock = lambda: clock["t"]
recovery = []
real_event = app._recovery_event
app._recovery_event = lambda kind, text: recovery.append((kind, text))
app.settings["stuck_guard"] = {"on": True, "minutes": 1, "action": "restart", "tries": 2}
app.last_result_clock = 0.0
app.recovery_end_clock = 0.0
chk = app._stuck_watcher()


def ask(advance):
    clock["t"] += advance
    chk.__closure__  # (keep the reference)
    time.sleep(0.0)
    for c in chk.__closure__ or ():
        pass
    # (the check looks at most once a second: make it look now)
    st = next(c.cell_contents for c in chk.__closure__ if isinstance(c.cell_contents, dict)
              and "since" in c.cell_contents)
    st["last"] = 0.0
    return chk(set(), set())


check("stuck guard: fine before the minutes are up", ask(50) is False)
check("stuck guard: starts the run over after 1 min without a result", ask(15) == "gameback"
      and recovery[-1][0] == "stuck", recovery)
check("stuck guard: a result showing puts it back to normal", (app.__setattr__("last_result_clock", clock["t"] + 1)
                                                               or ask(10)) is False)
check("stuck guard: then it waits the minutes again", ask(45) is False and ask(20) == "gameback")
check("stuck guard: the next try waits longer (1.5x)", ask(65) is False and ask(30) == "gameback")
check("stuck guard: after the last try it stops and tells Discord", ask(200) is True
      and recovery[-1][0] == "failed" and "stuck" in app.stop_reason.lower(), app.stop_reason)
app.stop_reason = None
# paused / away / recovery: the clock stands still (play clock) and recovery starts it again
app.settings["stuck_guard"] = {"on": True, "minutes": 1, "action": "ping", "tries": 3}
chk = app._stuck_watcher()
ask(0)
recovery.clear()
app.recovery_end_clock = clock["t"] + 50
check("stuck guard: time spent getting back into the game doesn't count", ask(55) is False and ask(40) is False
      and not recovery)
recovery.clear()
check("stuck guard: \"Only tell me on Discord\" keeps going", ask(25) is False and recovery
      and recovery[-1][0] == "stuck", recovery)
# play a macro first, then start over
played = []
app.settings["stuck_guard"] = {"on": True, "minutes": 1, "action": "macro", "macro": "x", "tries": 3}
app.stuck_steps = [rec(70)]
real_passes = app._run_passes
app._run_passes = lambda steps, ctx, times, top=False, counts=True: (played.append((steps, counts)), "ok")[1]
app.play_ctx = {"held": (set(), set())}
chk = app._stuck_watcher()
check("stuck guard: plays the chosen macro (not counted), then starts over", ask(61) == "gameback"
      and played and played[0][1] is False)
app._run_passes = real_passes
del app._play_clock
app._recovery_event = real_event
check("stuck guard: never in test plays", "None if test else self._stuck_watcher()" in
      core_text(src))
check("stuck guard: Discord gets its own card", "A run seems stuck" in open(os.path.join(src, "discord_rules.py"),
                                                                           encoding="utf-8").read())  # (batch 3: moved)
win = app.open_stuck()
win.vars["minutes"].set("7")
win.vars["action"].set("Only tell me on Discord")
win.save()
check("stuck guard: its window saves the choice", app._stuck_settings()["minutes"] == 7
      and app._stuck_settings()["action"] == "ping")
check("stuck guard: findable in Settings search", bool(app.search_settings("stuck")))
app.settings["stuck_guard"] = {"on": False}

# ------------------------------------------------------------ 2. colour check
dirty = {"color_on": "yes", "rgb": [300, -5, "a"], "tolerance": 1e9, "area": 77, "hold": "nan", "where": "moon",
         "x": 1e12, "y": "5"}
color_check.clean(dirty)
check("colour: values from a shared file are checked", dirty["color_on"] is False and dirty["rgb"] is None
      and dirty["tolerance"] == 100 and dirty["area"] == 1 and dirty["hold"] == 0.0 and dirty["where"] == "spot"
      and dirty["x"] == 100000 and dirty["y"] == 5, dirty)
good = {"color_on": True, "rgb": [255, 0, 0], "tolerance": 10, "area": 5, "hold": 0, "where": "spot", "x": 10, "y": 10}
red = np.zeros((5, 5, 3), np.uint8)
red[:, :] = (0, 0, 250)  # (blue, green, red)
blue = np.zeros((5, 5, 3), np.uint8)
blue[:, :] = (250, 0, 0)
shown = {"img": red}
image_watch.grab_part = lambda x0, y0, x1, y1: (shown["img"], (x0, y0))
check("colour: seen at the spot", color_check.seen(good))
shown["img"] = blue
check("colour: not seen when it's another colour", not color_check.seen(good))
whole = dict(good, where="screen")
screen = np.zeros((200, 300, 3), np.uint8)
image_watch.grab_screen = lambda *a, **k: screen
check("colour: whole screen: nothing there", not color_check.seen(whole))
screen[50:51, 50:51] = (0, 0, 250)
check("colour: whole screen: a single stray pixel doesn't count", not color_check.seen(whole))
screen[100:120, 100:120] = (0, 0, 250)
check("colour: whole screen: a patch counts", color_check.seen(whole))
# If / Retry / Wait with a colour
shown["img"] = red
cond = dict(good, shows=True)
check("colour If: true when it shows", app._condition_true(cond) is True)
check("colour If: \"doesn't show\" is false then", app._condition_true(dict(cond, shows=False)) is False)
flick = {"n": 0}


def flicker(*a):
    flick["n"] += 1
    return (red if flick["n"] % 2 else blue), (0, 0)


image_watch.grab_part = flicker
t0 = time.time()
check("colour: \"must stay for\" ignores flickers", app._condition_true(dict(cond, hold=0.3), wait=0.6) is False
      and time.time() - t0 >= 0.6)
image_watch.grab_part = lambda x0, y0, x1, y1: (shown["img"], (x0, y0))
clicks = []
real_click = app._click_at
app._click_at = lambda x, y: clicks.append((x, y))
wait_step = dict(workflow.new_action("wait_picture"), **good, click=True, timeout=1)
check("colour Wait: goes on and clicks the spot when it shows",
      app._wait_for_picture(wait_step, None, set(), set(), None) == "go on" and clicks == [(10, 10)])
shown["img"] = blue
check("colour Wait: \"stop\" when it doesn't show in time",
      app._wait_for_picture(dict(wait_step, timeout=0.3, otherwise="stop"), None, set(), set(), None) == "stop")
app._click_at = real_click
app.stop_reason = None
check("colour: needs no picture (no \"no picture\" warning, no matcher)",
      app._make_wait_matchers([dict(workflow.new_action("if"), condition=cond)]) == {})
ifc = dict(workflow.new_action("if"), condition=dict(cond))
check("colour: Check my macro doesn't call it a problem",
      not any(p["id"].startswith("steppic") for p in (app.set_steps([ifc]) or app.check_macro())))
fitted = workflow.map_points([ifc], lambda evs: [dict(e, x=e["x"] * 2, y=e["y"] * 2) for e in evs])
check("colour: the spot is fitted like a click", (fitted[0]["condition"]["x"], fitted[0]["condition"]["y"]) == (20, 20))
check("colour: described in plain words", "colour #ff0000 at 10, 10" in workflow.describe(ifc)[1],
      workflow.describe(ifc))
loaded = core.expand_steps([{"kind": "wait_picture", "color_on": True, "rgb": [1, 2, 3, 4], "tolerance": -5}])
check("colour: opening a file checks the colour fields", loaded[0]["rgb"] is None and loaded[0]["tolerance"] == 0)

# the Edit window: the colour switch and its rows
from tkinter import ttk as ttk_mod  # noqa: E402

if_step = workflow.new_action("if")
app.set_steps([if_step])
app.open_editor()
ed = app.macro_editor
pump(0.3)
ed.tree.selection_set(if_step["id"])
ed._step_clicked()
pump(0.1)


def widgets(w):
    for c in w.winfo_children():
        yield c
        yield from widgets(c)


def texts():
    return [w.cget("text") for w in widgets(ed.detail) if isinstance(w, (tk.Label, ttk_mod.Button))]


check("colour Edit: the switch is there and off at first", "Check a colour instead of a picture" in texts()
      and not ed.steps[0]["condition"].get("color_on"))
sw = next(w for w in widgets(ed.detail) if w.__class__.__name__ == "Switch")
sw._click(None)
pump(0.2)
cond_now = ed.steps[0]["condition"]
check("colour Edit: switched on, the colour rows show", cond_now.get("color_on") and "Pick spot and colour…" in texts()
      and "Where to look" in texts(), (cond_now, texts()))
errors_before = len(asked)
box = [w for w in widgets(ed.detail) if isinstance(w, ttk_mod.Combobox)][-1]
box.set("The whole screen")
box.event_generate("<<ComboboxSelected>>")
pump(0.2)
check("colour Edit: Where to look can be changed (one Undo point)", ed.steps[0]["condition"].get("where") == "screen",
      ed.steps[0]["condition"])
ed.win.destroy()

# ------------------------------------------------------------ 3. timed start and start-up
now = time.mktime((2026, 11, 17, 20, 0, 0, 0, 0, -1))
check("timed: \"21:30\" is today at 21:30", timed_start_ui.parse_when("21:30", now) == now + 5400)
check("timed: a time that's past is tomorrow", timed_start_ui.parse_when("19:00", now) == now + 23 * 3600)
check("timed: \"15\" and \"in 15 min\" are minutes", timed_start_ui.parse_when("15", now) == now + 900
      and timed_start_ui.parse_when("in 15 min", now) == now + 900)
check("timed: nonsense isn't taken", timed_start_ui.parse_when("25:99", now) is None
      and timed_start_ui.parse_when("soon", now) is None and timed_start_ui.parse_when("-5", now) is None)
check("timed: its own sound lines", "timed_warning" in sounds.EVENT_IDS and "timed_countdown" in sounds.EVENT_IDS
      and "recover_disconnect" in sounds.EVENT_IDS and "recover_close" in sounds.EVENT_IDS)
app.set_steps([rec(71)])
app.current_file = None
app._set_startup_setting(countdown=3, give_up=1)
started = []
app._remote_start = lambda who: (started.append(who), "ok")[1]
window_tools.windows_of = lambda exe: [1]
app.macro_program = {"exe": "RobloxPlayerBeta.exe"}
played_sounds.clear()
app.plan_timed_start(time.time() + 0.5, "timed")
check("timed: planned (shown in Settings)", app.timed_summary().startswith("Plays at"))
pump(1.8)
check("timed: the warning sound, then the countdown window with Cancel",
      "timed_warning" in played_sounds and app.timed_box is not None and app.timed_box.winfo_exists())
pump(3.5)
check("timed: after the countdown it plays (game window found)", started == ["a timed start"]
      and played_sounds.count("timed_countdown") >= 2, (started, played_sounds))
started.clear()
app.plan_timed_start(time.time(), "timed")
pump(1.3)
app.cancel_timed_start()
pump(3.5)
check("timed: Cancel in the countdown stops it", started == [] and app.timed_box is None)
app.plan_timed_start(time.time(), "timed")
pump(1.3)
app.emergency_stop()
pump(3.5)
check("timed: Ctrl+Alt+End cancels it too", started == [] and getattr(app, "timed_plan", None) is None)
window_tools.windows_of = lambda exe: []
plan = app.plan_timed_start(time.time(), "timed")
plan["phase"] = "waiting"
plan["give_up_at"] = time.time() - 1
app._timed_go(plan)
windows_only("timed: gives up when the game doesn't open in time (and says so)") or check("timed: gives up when the game doesn't open in time (and says so)", started == []
      and "gave up" in app.sub_note, app.sub_note)
plan = app.plan_timed_start(time.time(), "timed")
plan["phase"] = "waiting"
plan["give_up_at"] = time.time() + 60
app._timed_go(plan)
windows_only("timed: waits for the game's window before playing") or check("timed: waits for the game's window before playing", started == [] and app.timed_plan is plan)
app.cancel_timed_start()
# start-up
one = f"MacroRecorderTest{os.getpid()}"
windows_only("start-up: only one copy (a second one sees the first)") or check("start-up: only one copy (a second one sees the first)", timed_start_ui.single_copy(True, one)
      and not timed_start_ui.single_copy(True, one))
app._run_value_name = lambda: "Macro Recorder test (delete me)"
# (a test key of its own, not Windows' real start-up list: nothing is ever added to what starts with Windows,
# and security software can't block a "program added to start-up" here; that made this check flaky on GitHub)
real_run_key = timed_start_ui.RUN_KEY
test_key = rf"Software\MacroRecorderTests\Run{os.getpid()}"
winreg = None
if timed_start_ui.IS_WIN:
    import winreg

    winreg.CreateKey(winreg.HKEY_CURRENT_USER, test_key).Close()
    timed_start_ui.RUN_KEY = test_key
try:
    check("start-up: off at first", not app.startup_enabled())
    ok_on = app.set_startup(True)
    on_now = app.startup_enabled()
    ok_off = app.set_startup(False)
    windows_only("start-up: the switch adds and removes the Windows start-up entry") or check("start-up: the switch adds and removes the Windows start-up entry", ok_on and on_now and ok_off
          and not app.startup_enabled(), dict(added=ok_on, there=on_now, removed=ok_off))
finally:
    app.set_startup(False)
    timed_start_ui.RUN_KEY = real_run_key
    if winreg is not None:
        for k in (test_key, r"Software\MacroRecorderTests"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, k)
            except OSError:
                pass  # (the parent stays if another test run is using it)
check("start-up: started with the start-up flag", timed_start_ui.STARTUP_FLAG in app._startup_command())
app._set_startup_setting(when="play")
app.startup_action()
check("start-up: \"Play the open macro\" plans a start now (warning + countdown first)",
      app.timed_plan and app.timed_plan["why"] == "startup")
app.cancel_timed_start()
farm = os.path.join(tmp, "Farm.macro")
with open(farm, "w", encoding="utf-8") as f:
    json.dump({"app": "macro_recorder", "version": 1, "events": [key(72, 0.0), key(72, 0.03, False)]}, f)
app._set_startup_setting(when="game", macro=farm)
app.startup_action()
check("start-up: \"Open the game, then play\" opens that macro and plans with the game first",
      app.timed_plan and app.timed_plan.get("open_game") and os.path.basename(app.current_file) == "Farm.macro")
app.cancel_timed_start()
# opening the game first, inside playback (like "If the game closes")
calls = []
real_closed = app._game_closed
app._game_closed = lambda opts, exe, steps, startup=False: (calls.append((opts["action"], startup)), "gameback")[1]
app.settings["game_closed"] = {"on": True, "action": "wait", "open": "x.exe", "macro": ""}
app.start_rejoin_first = True
app.loop_var.set(False)
app.repeat_var.set(1)
sent.clear()
app.play()
wait_play()
app._game_closed = real_closed
windows_only("start-up: the game is opened first (reopen, not counted as a reconnect), then the macro plays") or check("start-up: the game is opened first (reopen, not counted as a reconnect), then the macro plays",
      calls == [("reopen", True)] and [e["key"]["vk"] for e in sent if e.get("pressed")] == [72],
      (calls, [e["key"]["vk"] for e in sent if e.get("pressed")]))
windows_only("start-up: findable in Settings search") or check("start-up: findable in Settings search", bool(app.search_settings("windows starts")))
app._set_startup_setting(when="nothing")

# ------------------------------------------------------------ 4. phone remote extras
names = [c["name"] for c in remote_ui.COMMANDS]
check("remote: /speed /repeat /log /schedule are there (no /milestones yet)",
      all(n in names for n in ("speed", "repeat", "log", "schedule")) and "milestones" not in names)
check("remote: /speed with limits", "between" in app.remote_speed(50, "me") and "between" in app.remote_speed(0.01, "me")
      and "1.5x" in app.remote_speed(1.5, "me") and app._check_speed(quiet=True) == 1.5)
check("remote: /repeat a number", "3 times" in app.remote_repeat("3", "me") and not app.loop_var.get()
      and int(app.repeat_var.get()) == 3)
check("remote: /repeat loop", "loop" in app.remote_repeat("loop", "me") and app.loop_var.get())
check("remote: /repeat nonsense", "1 and 9999" in app.remote_repeat("100000", "me")
      and "number" in app.remote_repeat("lots", "me"))
user = os.environ.get("USERNAME") or os.environ.get("USER") or "Somebody"  # (Mac: $USER)
sample = (f"2026-11-17 INFO Opened C:\\Users\\{user}\\Desktop\\Farm.macro\n"
          f"2026-11-17 INFO user {user} did it /Users/{user}/x.macro\n")
clean = remote_ui.remote_log_text(sample)
check("remote: /log has no paths or Windows user name", "C:\\" not in clean and user.lower() not in clean.lower()
      and "/Users/" not in clean, clean)
check("remote: /log gives the last lines", app.remote_log().startswith("```"))
app.set_steps([rec(73)])
check("remote: /schedule alarm:21:30 sets the alarm", "Alarm 21:30" in app.remote_schedule({"alarm": "21:30"}, "me")
      and app._schedule()["alarm_on"])
check("remote: /schedule shows what's planned", "21:30" in app.remote_schedule({}, "me"))
check("remote: /schedule every_day and timer with repeat", "every day" in app.remote_schedule(
    {"every_day": True, "timer": 2, "repeat": True}, "me") and app._schedule()["timer_min"] == 5)
check("remote: /schedule cancel turns both off", "Nothing is planned" in app.remote_schedule({"cancel": True}, "me")
      and not app._schedule()["alarm_on"] and not app._schedule()["timer_on"])
check("remote: /schedule nonsense", "Give the alarm" in app.remote_schedule({"alarm": "25:99"}, "me"))
log_text = open(core.diag.log_path(), encoding="utf-8").read() if core.diag.log_path() else ""
check("remote: every change is in the log", "Phone remote: speed set to 1.5" in log_text
      and "Phone remote: repeat set to loop" in log_text and "start playing later changed by" in log_text)

# ------------------------------------------------------------ round 2: Picture watch choose many / copy / count
app.boxes.askyesno = lambda *a, **k: (asked.append(("askyesno", a)), True)[1]
pw = app.open_picture_watch(core.GROUP_MINE) or app.picture_win
pump(0.3)
os.makedirs(core.watch_dir(), exist_ok=True)


def new_pic(name):
    file = f"{name}.png"
    image_watch.save_image(os.path.join(core.watch_dir(), file), np.full((20, 40, 3), 90, np.uint8))
    e = {"file": file, "screen_h": 1080, "kind": None, "name": name, "group": core.GROUP_MINE}
    pw.pics.append(pw._with_uid(e))
    return e


made = [new_pic(f"p{i}") for i in range(7)]
pw.new_files |= {e["file"] for e in made}
pw.select_group(core.GROUP_MINE)
pump(0.1)
n_undo = len(pw.undo_stack)
pw.pics_tree.selection_set([str(made[0]["_uid"]), str(made[1]["_uid"])])
pw._picture_clicked()
pw.copy_pictures()
other = {"id": "g_other", "name": "Other"}
pw.groups.append(other)
pw.paste_pictures("g_other")
copies = [e for e in pw.pics if e["group"] == "g_other"]
check("Picture watch: Paste into another group (each copy its own file)", len(copies) == 2
      and all(e["file"] not in ("p0.png", "p1.png") and os.path.isfile(os.path.join(core.watch_dir(), e["file"]))
              for e in copies), [e["file"] for e in copies])
check("Picture watch: one Undo per change", len(pw.undo_stack) == n_undo + 1)
pw.undo()
check("Picture watch: Undo takes the copies back", not [e for e in pw.pics if e["group"] == "g_other"])
pw.select_group(core.GROUP_MINE)
uids = [e["_uid"] for e in made]
pw.pics_tree.selection_set([str(u) for u in uids[:3]])
pw.toggle_pictures()
check("Picture watch: turn many off at once", not any(core.picture_on(pw._pic(u)) for u in uids[:3]))
pw.pics_tree.selection_set([str(u) for u in uids[:3]])
pw._drop_on_group([], "g_other")
check("Picture watch: dragged onto a group, they go into it", all(pw._pic(u)["group"] == "g_other" for u in uids[:3]))
pw.undo()
pw.select_group(core.GROUP_MINE)
asked.clear()
pw.pics_tree.selection_set([str(u) for u in uids])
pw.remove_picture()
check("Picture watch: removing more than 5 asks first", any(n == "askyesno" and "7 pictures" in str(a)
                                                            for n, a in asked) and not any(pw._pic(u) for u in uids))
pw.undo()
pw.select_group(core.GROUP_AOTR)
builtin = [e for e in pw.pics if e["group"] == core.GROUP_AOTR]
pw.clipboard = [dict(made[0])]
asked.clear()
pw.paste_pictures(core.GROUP_AOTR)
check("Picture watch: the built-in AOT:R group can't be pasted into", any("can't be changed" in str(a)
                                                                          for _n, a in asked))
if builtin:
    pw.pics_tree.selection_set([str(builtin[0]["_uid"])])
    pw._drop_on_group([], core.GROUP_MINE)
    check("Picture watch: a built-in picture can't be dragged out of AOT:R", builtin[0]["group"] == core.GROUP_AOTR)
# a colour that counts
pw.select_group(core.GROUP_MINE)
real_pick = app._pick_point
app._pick_point = lambda parent, on_pick, hidden=(), with_color=False: on_pick(10, 10, (255, 0, 0))
pw.add_colour()
app._pick_point = real_pick
col = pw._pic(pw.sel_pic)
check("Picture watch: Colour… adds a colour that counts (with a swatch picture)",
      col and col.get("color_on") and col.get("action") == "count" and os.path.isfile(
          os.path.join(core.watch_dir(), col["file"])), col)
pw.apply()
pw.win.destroy()
app.watch_var.set(True)
counting = app._count_pictures()
check("Picture watch: counting pictures are watched alongside, not as restarts",
      counting and not any(getattr(m, "picture_entry", {}).get("color_on") for m in app._make_matchers()))
app.watch_var.set(False)
shared = core.shared_picture_fields({"action": "count", "counter": "Evil\u202e" + "x" * 99, "amount": 1e99,
                                     "keep": "yes", "color_on": True, "rgb": [1, 2, 3], "where": "moon"})
check("Picture watch: counting / colour fields from a shared file are checked",
      shared["counter"] == ("Evil" + "x" * 99)[:30] and shared["amount"] == 1000000 and "keep" not in shared
      and shared["where"] == "spot", shared)
# the counting watcher: once per appearance, cooldown, never while paused
looks = iter([True, True, True, False, True, True, False] + [False] * 50)
real_seen = color_check.seen
color_check.seen = lambda h: next(looks, False)
app.counters = {}
done = threading.Event()
pic = {"color_on": True, "rgb": [255, 0, 0], "x": 1, "y": 1, "action": "count", "counter": "Drops", "amount": 1,
       "cooldown": 0.1, "name": "Blue drop"}
app.COUNT_EVERY = 0.05
app.play_paused_at = None
app.away_started = None
th = threading.Thread(target=app._count_worker, args=([pic], done))
th.start()
time.sleep(0.8)
done.set()
th.join(2)
check("counting: once each time it shows (it must be gone before it counts again)", app.counters.get("Drops") == 2,
      app.counters)
looks = iter([True] * 40)
app.counters = {}
app.play_paused_at = time.perf_counter()
done = threading.Event()
th = threading.Thread(target=app._count_worker, args=([pic], done))
th.start()
time.sleep(0.5)
done.set()
th.join(2)
app.play_paused_at = None
color_check.seen = real_seen
check("counting: never while paused", app.counters.get("Drops") is None, app.counters)
check("counting: never in test or watch-only plays", "self.count_list = [] if test else self._count_pictures()" in
      core_text(src))
log_text = open(core.diag.log_path(), encoding="utf-8").read() if core.diag.log_path() else ""
check("counting: each count is in the log", "counter \"Drops\" +1" in log_text)

# colour: an area I draw, and Look now
area = {"color_on": True, "rgb": [255, 0, 0], "tolerance": 10, "where": "area", "x0": 0, "y0": 0, "x1": 50, "y1": 50}
pic_area = np.zeros((50, 50, 3), np.uint8)
pic_area[20:30, 20:30] = (0, 0, 250)
image_watch.grab_part = lambda x0, y0, x1, y1: (pic_area, (x0, y0))
check("colour area: a patch inside the area counts", color_check.seen(area))
seen_now, best, where_now = color_check.look(area)
check("colour Look now: seen, the best match and where", seen_now and best >= 95 and where_now == (20, 20),
      (seen_now, best, where_now))
pic_area[:, :] = (250, 0, 0)
seen_now, best, _w = color_check.look(area)
check("colour Look now: not seen, with how close it was", not seen_now and best < 50, (seen_now, best))
fitted = workflow.map_points([dict(workflow.new_action("if"), condition=dict(area))],
                             lambda evs: [dict(e, x=e["x"] * 2, y=e["y"] * 2) for e in evs])
check("colour area: fitted like clicks", (fitted[0]["condition"]["x1"], fitted[0]["condition"]["y1"]) == (100, 100))
app.macro_screen = (app.screen_w // 2, app.screen_h // 2)
app.settings["fit_to"] = "screen"
app.open_editor()
ed = app.macro_editor
pump(0.2)
check("colour: a spot picked in Edit is kept in the macro's size",
      ed._spot_to_macro(app.screen_w // 2, app.screen_h // 2) == (app.screen_w // 4, app.screen_h // 4))
ed.win.destroy()
app.macro_screen = None

# ------------------------------------------------------------ round 2: the alarm and the timer
app.set_steps([rec(74)])
app._set_schedule(alarm_on=True, alarm="10:00", daily=False, timer_on=False, alarm_last="", when="play")
base = time.mktime((2026, 11, 17, 10, 0, 30, 0, 0, -1))
fired = []
real_plan = app.plan_timed_start
app.plan_timed_start = lambda at, why="timed", **kw: fired.append((why, kw))
check("alarm: fires at its time", app._schedule_check(base) == "alarm" and fired[-1][0] == "alarm")
check("alarm: once (off afterwards, the time stays)", not app._schedule()["alarm_on"]
      and app._schedule()["alarm"] == "10:00")
app._set_schedule(alarm_on=True, daily=True, alarm_last="")
app._schedule_check(base)
check("alarm: every day stays on, and not twice the same day", app._schedule()["alarm_on"]
      and app._schedule_check(base + 30) is None)
check("alarm: missed by more than 10 minutes isn't played late", app._schedule_due(base + 3600)[0] is False)
app._set_schedule(alarm_on=False, timer_on=True, timer_min=5, timer_repeat=True, timer_from=base - 301)
check("timer: fires after its minutes", app._schedule_check(base) == "timer")
check("timer: again and again counts again from now", app._schedule()["timer_on"]
      and app._schedule()["timer_from"] == base)
app._set_schedule(timer_repeat=False, timer_from=base - 301)
app._schedule_check(base)
check("timer: once is off afterwards", not app._schedule()["timer_on"])
fired.clear()
app._set_schedule(alarm_on=True, alarm="10:00", daily=False, alarm_last="", timer_on=True, timer_min=5,
                  timer_repeat=False, timer_from=base - 270)
app._schedule_check(base)
check("alarm + timer within a minute: only one start", len(fired) == 1 and not app._schedule()["timer_on"], fired)
app._set_schedule(timer_on=True, timer_min=1, timer_repeat=True)
check("timer: again and again is at least 5 minutes", app._schedule()["timer_min"] == 5)
app._set_schedule(timer_on=True, timer_repeat=False, timer_from=time.time() - 9999, alarm_on=False)
app.schedule_start()
check("timer: ran out while the app was closed: not played late", not app._schedule()["timer_on"])
app._set_schedule(when="game", open="C:\\Games\\Roblox.exe", macro="")
fired.clear()
app._set_schedule(alarm_on=True, alarm="10:00", alarm_last="")
app._schedule_check(base)
check("open the game first: what to open goes with the start", fired and fired[-1][1].get("open_game")
      and fired[-1][1].get("open") == "C:\\Games\\Roblox.exe", fired)
app.plan_timed_start = real_plan
# while a macro plays: wait for the run's end, then start again
app.playing = True
plan = {"at": time.time(), "why": "timer"}
app.timed_plan = plan
app._timed_countdown(plan)
check("playing: it waits for the run to end (never cuts a run)", app.restart_after_run is plan
      and getattr(app, "timed_box", None) is None)
app.playing = False
app.stop_play.clear()
app.session = __import__("stats").Session("x")
app._run_finished(1, "end")
check("playing: at the run's end the macro stops, to start again", app.stop_play.is_set())
app.stop_play.clear()
app.restart_after_run = None
app.timed_plan = None
win = app.open_timed_start()
win.vars["alarm_on"].set(True)
win.vars["hour"].set("7")
win.vars["minute"].set("5")
win.vars["timer_on"].set(True)
win.vars["timer"].set("2")
win.vars["repeat"].set(True)
win.vars["when"].set("play")
win.save()
sc = app._schedule()
check("window: alarm 07:05 and a repeating timer (at least 5) are saved",
      sc["alarm"] == "07:05" and sc["alarm_on"] and sc["timer_on"] and sc["timer_min"] == 5 and sc["timer_repeat"])
check("window: remembered in the settings (after a restart too)", app.settings["schedule"]["alarm"] == "07:05")
win.destroy()
lines = "\\n".join(app._remote_settings_lines())
check("Discord status: speed, repeat, start later and the guards", "**Speed**" in lines and "**Start later** Alarm 07:05"
      in lines and "**Stuck run guard**" in lines and "Game closes" in lines, lines)
check("Discord status: no paths in it", ":\\\\" not in lines and "/Users/" not in lines)
app._set_schedule(alarm_on=False, timer_on=False)

# ------------------------------------------------------------ the stuck run guard: RETRY, and what it looks for
real_results, real_watch = app.result_pictures, app.watch_pictures
app.result_pictures = [{"file": "c.png", "builtin": "completed", "kind": "win", "name": "MISSION COMPLETED"},
                       {"file": "f.png", "builtin": "failed", "kind": "loss", "name": "MISSION FAILED"},
                       {"file": "mine.png", "kind": "win", "name": "My win banner"}]
app.watch_pictures = [{"file": "r.png", "builtin": "retry", "name": "RETRY"}]
app.settings["results_enabled"] = True
app.watch_var.set(True)
text, ok = app.stuck_looks_for()
check("guard: says what it looks for (built-in pictures in Picture watch > AOT:R)", ok
      and "MISSION COMPLETED ✓" in text and "MISSION FAILED ✓" in text and "RETRY ✓" in text
      and "Picture watch > AOT:R" in text, text)
check("guard: names your own result pictures too", "My win banner" in text, text)
app.watch_pictures = [dict(app.watch_pictures[0], on=False)]
text, ok = app.stuck_looks_for()
check("guard: a picture that's off shows in orange and says so", not ok and "RETRY ✗" in text
      and "RETRY is off" in text, text)
app.watch_pictures = []
text, ok = app.stuck_looks_for()
check("guard: a missing picture says so", not ok and "RETRY is missing" in text, text)
app.result_pictures, app.watch_pictures = real_results, real_watch
app.watch_var.set(False)
check("guard: RETRY showing resets the guard (like a result)", 'if pic.get("builtin") == "retry":' in
      core_text(src))
clock = {"t": 5000.0}
app._play_clock = lambda: clock["t"]
app.settings["stuck_guard"] = {"on": True, "minutes": 1, "action": "restart", "tries": 3}
app.last_result_clock = 0.0
app.recovery_end_clock = 0.0
chk = app._stuck_watcher()
ask(50)
app.last_result_clock = clock["t"]  # (what RETRY appearing does)
check("guard: after RETRY the minutes start again", ask(50) is False and ask(15) == "gameback")
del app._play_clock
app.settings["stuck_guard"] = {"on": False}

# ------------------------------------------------------------ a late result goes to the Unknown run before
import stats as stats_mod  # noqa: E402

real = {k: getattr(app, k) for k in ("_run_result", "_count_drops", "_kinds_found", "_run_finished")}
app.result_matchers = ["stand-in"]
app._count_drops = lambda: 0
app._kinds_found = lambda: {"win": True, "loss": False}
finished = []
app._run_finished = lambda count, how: finished.append((count, how))
looks = []


def results_seq(*answers):
    it = iter(answers)

    def look(began, whole_screen=False):
        looks.append(whole_screen)
        return next(it, stats_mod.UNKNOWN)
    return look


def run_ends(seconds, *answers):
    app._run_result = results_seq(*answers)
    began = time.perf_counter() - seconds
    app.run_began = (began, app._play_clock() - seconds)
    return app._finish_run(len(app.session.runs) + 1, "picture")


app.session = stats_mod.Session("Late")
app.late_result = None
n_hist = len(run_history.runs())
looks.clear()
run_ends(200)
check("late result: an Unknown run takes one more look, over the whole screen", looks == [False, True], looks)
check("late result: the run is Unknown for now", app.session.runs[-1][0] == "unknown" and app.late_result)
# the next run is only the results screen (12 s): its result goes to the run before, and it isn't counted
out = run_ends(12, "win")
check("late result: a result in the next 30 s goes to the Unknown run", app.session.runs == [("win", 200)]
      or [r[0] for r in app.session.runs] == ["win"], app.session.runs)
check("late result: the short leftover isn't counted (not a run)", out is False and len(app.session.runs) == 1)
check("late result: Run stats changed too (won, not unknown)", run_history.runs()[-1]["status"] == "win"
      and len(run_history.runs()) == n_hist + 1, run_history.runs()[-1])
check("late result: Discord and the sound hear about the corrected run", finished and finished[-1] == (1, "late"),
      finished)
log_text = open(core.diag.log_path(), encoding="utf-8").read() if core.diag.log_path() else ""
check("late result: the log says so", "Late result: MISSION COMPLETED showed" in log_text
      and "isn't counted" in log_text)
# seen by the watcher while the next run plays
run_ends(200)
check("late result (watcher): gives it to the Unknown run", app._give_late_result("loss")
      and app.session.runs[-1][0] == "loss")
check("late result (watcher): only once", not app._give_late_result("win"))
out = run_ends(10)
check("late result (watcher): the short leftover isn't counted", out is False and len(app.session.runs) == 2)
# a long next run is a real run
run_ends(200)
app._give_late_result("win")
out = run_ends(90)
check("late result: a next run of 30 s or more is a real run", out is not False and len(app.session.runs) == 4)
# too late
run_ends(200)
app.late_result["ended"] -= 31
check("late result: after 30 s it isn't given to the run before", not app._give_late_result("win")
      and app.session.runs[-1][0] == "unknown")
# a won run doesn't wait for anything
app.late_result = None
run_ends(200, "win")
check("late result: a run with its result isn't waiting", app.late_result is None)
out = run_ends(12, "win")
check("late result: a short won run after a won run still counts", out is not False
      and app.session.runs[-1] == ("win", app.session.runs[-1][1]) and len(app.session.runs) == 7)
for k, v in real.items():
    setattr(app, k, v)
app.result_matchers = []
app.late_result = None

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
root.destroy()
sys.exit(0 if passed == len(results) else 1)
