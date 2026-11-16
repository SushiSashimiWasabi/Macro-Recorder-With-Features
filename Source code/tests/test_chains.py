"""Picture actions, macros that play other macros (chains) and disconnect recovery.
No real input is sent, no window is shown, throwaway settings folder."""
import json
import os
import sys
import tempfile
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_test_")

import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402

import macro_steps as workflow  # noqa: E402
import modern_ui  # noqa: E402
import window_tools  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


root = tk.Tk()
root.withdraw()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
app.recover_count_var.set(0)  # (2.10: no countdown before rejoining here; tested in test_preview1)
root.withdraw()
sent = []
app._replay_event = lambda e, hk, hb: sent.append(e)
app._click_at = lambda x, y: sent.append({"type": "clicked_at", "x": x, "y": y})
app._free_shift_lock = lambda: True
app.root.after = (lambda real: (lambda ms, fn=None, *a: real(ms, fn, *a) if fn else real(ms)))(app.root.after)
modern_ui.messagebox.showwarning = lambda *a, **k: None
errors = []
modern_ui.messagebox.showerror = lambda *a, **k: errors.append(a)
core.messagebox.showerror = lambda *a, **k: errors.append(a)
window_tools.foreground = lambda: None
app.settings.update(pause_when_away=False, results_enabled=False, drops_enabled=False)
app.away_var.set(False)
app.result_pictures = []  # (no result pictures: nothing looks at the real screen)
runs = []
app._run_finished = lambda c, how: runs.append((c, how))
recovery = []
app._recovery_event = lambda kind, text: recovery.append(kind)


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def key(vk, t, pressed=True):
    return {"type": "key", "key": {"vk": vk}, "pressed": pressed, "t": t}


def tap(vk, length=0.05):
    return [key(vk, 0.0), key(vk, length, False)]


def save_macro(name, events=None, actions=None):
    path = os.path.join(tmp, name + ".macro")
    data = {"app": "macro_recorder", "version": 1, "events": events or []}
    if actions:
        data["actions"] = actions
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def run_play(steps=None, events=None, **kw):
    sent.clear()
    runs.clear()
    errors.clear()
    recovery.clear()
    app.current_file = kw.get("file")
    if steps is not None:
        app.set_steps(steps)
    else:
        app.actions = None
        app.events = events
    app.ready_var.set(0)
    app.loop_var.set(kw.get("loop", False))
    app.repeat_var.set(kw.get("repeats", 1))
    app.play()
    t0 = time.time()
    while app.playing and time.time() - t0 < kw.get("limit", 15):
        pump(0.03)
        if kw.get("stop_when") and kw["stop_when"]():
            app.stop_playback()
    pump(0.1)
    return time.time() - t0


def pressed_vks():
    return [e["key"]["vk"] for e in sent if e.get("type") == "key" and e.get("pressed")]


def play_macro_step(path, times=1, counts=True):
    a = workflow.new_action("play_macro")
    a.update(file=path, times=times, counts=counts)
    return a


# ---- chains: "Play another macro" steps
app.watch_var.set(False)
app.settings["watch_enabled"] = False
a_path = save_macro("A", tap(65))
b_path = save_macro("B", tap(66))
took = run_play([play_macro_step(a_path, 3), play_macro_step(b_path, 1)])
check("chain: A three times, then B", pressed_vks() == [65, 65, 65, 66], pressed_vks())
check("chain: each part counted as a run", [c for c, _ in runs] == [1, 2, 3, 4], runs)
check("chain: no error", not errors and app.stop_reason is None, (errors, app.stop_reason))

took = run_play([play_macro_step(a_path, 2, counts=False), play_macro_step(b_path, 1, counts=False)], repeats=2)
check("chain: uncounted parts make the whole chain one run", [c for c, _ in runs] == [1, 2], runs)
check("chain: whole chain played twice", pressed_vks() == [65, 65, 66, 65, 65, 66], pressed_vks())

# a macro with steps inside another one, and a recorded part of its own around it
inner = [workflow.new_action("recorded"), workflow.new_action("wait")]
inner[0]["events"] = tap(67)
inner[1]["seconds"] = 0.05
c_path = save_macro("C", tap(67), actions=inner)
own = workflow.new_action("recorded")
own["events"] = tap(68)
run_play([own, play_macro_step(c_path, 2, counts=False)])
check("chain: own keys, then a macro with steps twice", pressed_vks() == [68, 67, 67], pressed_vks())

# a circle: X plays Y, Y plays X
x_path = os.path.join(tmp, "X.macro")
y_path = save_macro("Y", actions=[play_macro_step(x_path)])
save_macro("X", actions=[play_macro_step(y_path)])
app.load(x_path, quiet=True)
run_play(steps=app.macro_steps(), file=x_path)
check("chain: a circle is refused with a message", errors and "circle" in str(errors[0]), errors)
# (2.10) a missing macro no longer stops Play: that step is skipped and Check my macro tells about it
gone_own = workflow.new_action("recorded")
gone_own["events"] = tap(69)
run_play([play_macro_step(os.path.join(tmp, "gone.macro")), gone_own])
check("chain: a missing macro doesn't stop Play (the step is skipped)", not errors and pressed_vks() == [69],
      (errors, pressed_vks()))
check("chain: Check my macro names the missing macro",
      any(p["id"] == "chain:gone" and p["level"] == "sure" for p in app.check_macro()), app.check_macro())

# save and open keeps the step
app.set_steps([play_macro_step(a_path, 4)])
check("chain: describe", workflow.describe(app.actions[0]) == ("Play another macro", "A × 4"),
      workflow.describe(app.actions[0]))

# ---- picture actions
pic_img = np.zeros((20, 40, 3), np.uint8)


def watch_pic(file, **fields):
    return dict({"img": pic_img, "file": file, "screen_h": 1080}, **fields)


def set_pictures(*pics):
    app.watch_pictures = list(pics)
    app.watch_var.set(True)
    app.settings.update(watch_enabled=True, watch_wait=0, watch_click=False, watch_end_wait=0,
                        watch_limit_count=50, watch_limit_seconds=60)
    app.watch_wait_var.set(0)
    app.watch_click_var.set(False)
    app.watch_end_var.set(0)
    app.watch_limit_var.set(50)
    app._save_settings()


plan = {"fire": []}  # [(seconds after start, index of the picture)]


def fake_watch(watch, seen, done):
    began = time.time()
    todo = list(plan["fire"])
    while not done.is_set():
        if todo and time.time() - began >= todo[0][0] and not seen.is_set():
            _, i = todo.pop(0)
            watch["seen_at"] = (5 + i, 5)
            watch["seen_pic"] = watch["matchers"][i].picture_entry
            seen.set()
        time.sleep(0.01)


app._watch_worker = fake_watch
long_tap = [key(65, 0.0), key(65, 0.6, False)]

# press a key and go on
set_pictures(watch_pic("k.png", action="key", key={"vk": 70}, click=True))
plan["fire"] = [(0.2, 0)]
took = run_play(events=long_tap)
check("picture key: pressed its key in the middle, macro went on", pressed_vks() == [65, 70] and len(runs) == 1,
      (pressed_vks(), runs))
check("picture key: its own click on it", any(e.get("type") == "clicked_at" for e in sent))
check("picture key: the macro's own key was let go at its end",
      sent[-1].get("pressed") is False and sent[-1]["key"]["vk"] == 65, sent[-1])

# wait: the macro stands still, nothing is rushed
set_pictures(watch_pic("w.png", action="wait", seconds=1.0))
plan["fire"] = [(0.2, 0)]
took = run_play(events=long_tap)
check("picture wait: the macro took about a second longer", 1.5 < took < 2.6, f"{took:.2f}")

# skip the step
first, second = workflow.new_action("recorded"), workflow.new_action("recorded")
first["events"] = [key(65, 0.0), key(65, 3.0, False)]
second["events"] = tap(66)
set_pictures(watch_pic("s.png", action="skip"))
plan["fire"] = [(0.2, 0)]
took = run_play([first, second])
check("picture skip: the long step ended early, the next one played", pressed_vks() == [65, 66] and took < 2,
      (pressed_vks(), f"{took:.2f}"))

# stop
set_pictures(watch_pic("x.png", action="stop", name="Kicked"))
plan["fire"] = [(0.2, 0)]
run_play(events=long_tap, loop=True)
check("picture stop: stopped with the picture's name", app.stop_reason and "Kicked" in app.stop_reason,
      app.stop_reason)
check("picture stop: not counted as a run", runs == [], runs)

# play another macro, then start over
set_pictures(watch_pic("p.png", action="play", macro=b_path))
plan["fire"] = [(0.2, 0)]
run_play(events=long_tap, repeats=1)
check("picture play: other macro played, then the macro started over",
      pressed_vks() == [65, 66, 65], pressed_vks())
check("picture play: only the full run counted", [c for c, _ in runs] == [1], runs)

# restart (as before) counts the run
set_pictures(watch_pic("r.png"))
plan["fire"] = [(0.2, 0)]
run_play(events=long_tap, repeats=2)
check("picture restart: run 1 ended by the picture, run 2 to its end", runs == [(1, "picture"), (2, "end")], runs)

# switch to another macro
set_pictures(watch_pic("sw.png", action="switch", macro=b_path))
plan["fire"] = [(0.2, 0)]
run_play(events=long_tap, repeats=2)
check("picture switch: B plays from then on", pressed_vks() == [65, 66, 66], pressed_vks())

# a picture with no macro chosen
set_pictures(watch_pic("n.png", action="play"))
run_play(events=long_tap)
check("picture play without a macro: refused with a message", errors and "no macro" in str(errors[0]), errors)

# inside a chain: the picture ends that part's run, the chain goes on with the next pass
set_pictures(watch_pic("r.png"))
plan["fire"] = [(0.2, 0)]
long_path = save_macro("Long", long_tap)
run_play([play_macro_step(long_path, 2), play_macro_step(b_path, 1)])
check("picture in a chain: next pass of the same part, then the next part",
      pressed_vks() == [65, 65, 66] and [c for c, _ in runs] == [1, 2, 3], (pressed_vks(), runs))

# ---- disconnect recovery
shows = {"disconnect": [True, False]}  # what each look at the disconnect screen finds


def fake_shows(matcher, need, wait=0.0):
    return shows["disconnect"].pop(0) if shows["disconnect"] else False


app._shows = fake_shows
core_wait = app.stop_play.wait
set_pictures(watch_pic("d.png", action="recover", macro=b_path, tries=3, name="Disconnected"))
plan["fire"] = [(0.2, 0)]
# (the growing waits between tries are skipped here: 15 s, 30 s...)
real_wait = app.stop_play.wait
app.stop_play.wait = lambda t=None: real_wait(min(t or 0, 0.01))
run_play(events=long_tap, repeats=1)
check("recovery: rejoin macro played twice (first try didn't work), then the macro",
      pressed_vks() == [65, 66, 66, 65], pressed_vks())
check("recovery: lost, then back", recovery == ["lost", "back"], recovery)
check("recovery: counted one reconnect, one full run", app.session.reconnects == 1 and len(runs) == 1,
      (app.session.reconnects, runs))

shows["disconnect"] = [True, True, True]
plan["fire"] = [(0.2, 0)]
run_play(events=long_tap, loop=True)
check("recovery: gives up after its tries and stops", recovery == ["lost", "failed"]
      and app.stop_reason and "couldn't get back" in app.stop_reason, (recovery, app.stop_reason))
check("recovery: rejoin macro played three times", pressed_vks() == [65, 66, 66, 66], pressed_vks())
app.stop_play.wait = real_wait

# ---- settings keep a picture's action
entry = core.watch_entry({"file": "a.png", "screen_h": 1080, "action": "play", "macro": "m.macro", "click": False,
                          "cooldown": 5, "img": 1, "seen_rect": (1, 2, 3, 4)})
check("settings: a picture's action is kept, not its image",
      entry == {"file": "a.png", "screen_h": 1080, "action": "play", "macro": "m.macro", "click": False,
                "cooldown": 5}, entry)

# ---- if the game closes: open it again, play the rejoin macro, start the run over
app.watch_var.set(False)
app.settings["watch_enabled"] = False
app.watch_pictures = []
game = {"open": True, "opened": []}
window_tools.IS_WIN = True
window_tools.windows_of = lambda exe: [111] if exe == "Game.exe" and game["open"] else []
window_tools.force_to_front = lambda hwnd: True
window_tools.foreground = lambda: 111 if game["open"] else 222
window_tools.pid_of = lambda h: 1
window_tools.exe_of = lambda h: {111: "Game.exe"}.get(h, "Other.exe")
core.GAME_GONE_SECONDS = 0.5


def fake_open(target):
    game["opened"].append(target)
    game["open"] = True


app._open_target = fake_open
app.macro_program = {"exe": "Game.exe"}
app.settings["game_closed"] = {"action": "reopen", "open": "roblox://test", "macro": b_path, "tries": 2,
                               "settle": 0}
import threading  # noqa: E402


def close_game_later():
    time.sleep(0.3)
    game["open"] = False


threading.Thread(target=close_game_later, daemon=True).start()
slow = [key(65, 0.0), key(65, 2.5, False)]
keep_program = app.macro_program
run_play(events=slow, limit=30)
check("game closed: it was opened again", game["opened"] == ["roblox://test"], game["opened"])
check("game closed: rejoin macro played, then the run started over", pressed_vks() == [65, 66, 65],
      pressed_vks())
check("game closed: lost, then back; one reconnect, one run", recovery == ["lost", "back"]
      and app.session.reconnects == 1 and len(runs) == 1, (recovery, app.session.reconnects, runs))

# the same with "Pause if the game isn't in front" on (as Kong has it): the game closing is noticed
# while playback is paused, and the rejoin macro must still play (its clock was frozen)
app.settings["pause_when_away"] = True
app.away_var.set(True)
app.macro_program = keep_program
game.update(open=True, opened=[])
threading.Thread(target=close_game_later, daemon=True).start()
began = time.perf_counter()
run_play(events=slow, limit=30)
took = time.perf_counter() - began
check("game closed while paused: rejoin macro played, then the run started over",
      game["opened"] == ["roblox://test"] and pressed_vks() == [65, 66, 65], (game["opened"], pressed_vks()))
check("game closed while paused: the timer never went below zero",
      0 <= app.play_pause_total <= took and app._play_clock() <= time.perf_counter(), (app.play_pause_total, took))
app.settings["pause_when_away"] = False
app.away_var.set(False)

app.settings["game_closed"] = {"action": "stop"}
app.macro_program = keep_program
game["open"] = True
threading.Thread(target=close_game_later, daemon=True).start()
run_play(events=slow, limit=30)
check("game closed: 'stop' stops with the reason", app.stop_reason and "game closed" in app.stop_reason,
      app.stop_reason)
# turned off with its switch: the game closing is only waited for, the choices stay
app.settings["game_closed"] = {"action": "stop", "on": False}
app.macro_program = keep_program
game["open"] = True
threading.Thread(target=close_game_later, daemon=True).start()
sent.clear()
app.ready_var.set(0)
app.loop_var.set(False)
app.repeat_var.set(1)
app.events, app.actions = [key(65, 0.0), key(65, 8.0, False)], None
app.play()
t0 = time.time()
while time.time() - t0 < 4:
    pump(0.05)
still = app.playing
app.stop_playback()
pump(0.3)
check("game closed switched off: the macro isn't stopped by it", still and not (app.stop_reason or ""),
      (still, app.stop_reason))
check("game closed switched off: the row says Off, the choice is kept",
      app.closed_summary() == "Off" and app._closed_settings()["chosen"] == "stop", app.closed_summary())
app.settings.pop("game_closed")
app.macro_program = None
game["open"] = True
window_tools.foreground = lambda: None

# ---- the windows (opened, changed and saved without anyone clicking)
app.settings["macro_library"] = [a_path, b_path]
set_pictures(watch_pic("ui.png"))
app.open_settings() if hasattr(app, "open_settings") else None
pump(0.3)
win = app.edit_picture_action(0)
pump(0.2)
win.vars["action"].set(core.WATCH_ACTION_NAMES["play"])
win.vars["layout"](set_counts=True)
win.vars["macro"].set("B")
win.vars["name"].set("Lobby")
win.vars["cooldown"].set("30")
pump(0.1)
win.save()
pump(0.2)
pic = app.watch_pictures[0]
check("picture window: saved the action, macro, name and cooldown",
      (pic.get("action"), pic.get("macro"), pic.get("name"), pic.get("cooldown")) == ("play", b_path, "Lobby", 30.0),
      {k: v for k, v in pic.items() if k != "img"})
check("picture window: settings keep it", app.settings["watch_pictures"][0].get("action") == "play",
      app.settings["watch_pictures"])
import picture_actions_ui  # noqa: E402

check("picture window: the list says what it does",
      picture_actions_ui.action_summary(pic) == "Play \"B\", then start over  (cooldown 30 s)",
      picture_actions_ui.action_summary(pic))
win = app.open_game_closed()
pump(0.2)
win.vars["action"].set(app.CLOSED_CHOICES["reopen"])
win.vars["open"].set("roblox://experiences/start?placeId=1")
win.vars["macro"].set("A")
win.save()
pump(0.2)
check("game closed window: saved", app._closed_settings()["action"] == "reopen"
      and app._closed_settings()["macro"] == a_path and "placeId" in app._closed_settings()["open"],
      app.settings.get("game_closed"))
check("game closed window: the row says it", "rejoin" in app.closed_summary() and "\"A\"" in app.closed_summary(),
      app.closed_summary())
app.close_settings() if hasattr(app, "close_settings") else None

# ---- fixes after Kong's test (15 Nov)
# the open macro can be chosen for a picture (a rejoin macro that was just recorded and saved)
app.current_file = b_path
win = app.edit_picture_action(0)
check("picture window: the open macro is in the list too", "B" in win.vars["macros"], list(win.vars["macros"]))
win.destroy()
check("picture actions: the disconnect action comes right after 'start over'",
      [k for k, _n, _w in core.WATCH_ACTIONS][:2] == ["restart", "recover"])
# "Play another macro" is in the Edit window's Add action menu
app.open_editor()
pump(0.4)
ed = app.macro_editor
ed._add_menu()
pump(0.2)
texts = []


def collect(w):
    for c in w.winfo_children():
        try:
            texts.append(str(c.cget("text")))
        except tk.TclError:
            pass
        collect(c)


collect(ed.add_popup)
check("Edit: Add action shows 'Play another macro' (chains)",
      any("Play another macro" in t for t in texts) and any("CHAIN" in t for t in texts), texts[:12])
ed.add_popup.destroy()
ed.win.destroy()
# a disconnect box already on screen when Play is pressed is dealt with at once (a results screen isn't)
import image_watch  # noqa: E402

fired = {}
for action in ("recover", "restart"):
    app.watch_pictures = [watch_pic("x.png", action=action, macro=b_path)]
    watch = {"matchers": app._make_matchers(), "need": 0.85}
    for m in watch["matchers"]:
        mid = (app.screen_w // 2 - 20, app.screen_h // 2 - 10, 40, 20)  # (a disconnect box is in the middle)
        m.find_near_last = lambda screen, good_enough=0, mid=mid: (0.99, mid)
        m.find = lambda screen, good_enough=0, quick=False, mid=mid, **kw: (0.99, mid)
        m.near_last_area = lambda: (0, 0, 100, 100)
    seen, done = threading.Event(), threading.Event()
    real_grab = image_watch.grab_screen
    image_watch.grab_screen = lambda sct=None, region=None: np.zeros((100, 100, 3), np.uint8)
    t = threading.Thread(target=core.MacroRecorder._watch_worker, args=(app, watch, seen, done), daemon=True)
    t.start()
    fired[action] = seen.wait(2.5)
    done.set()
    t.join(3)
    image_watch.grab_screen = real_grab
check("picture watch: a disconnect box showing at the start fires, a Retry button doesn't",
      fired == {"recover": True, "restart": False}, fired)

# a disconnect picture only counts in the middle of the screen and when it matches well
# (scores measured on Kong's 2560x1440 screen: the real box 0.985 in the middle; game screens 0.79-0.86
# elsewhere; the check is done as if the screen were that size)
app.screen_w, app.screen_h = 2560, 1440
dc = {"action": "recover"}
check("disconnect picture: the real box in the middle counts", app._watch_match_ok(dc, 0.985, (1072, 586, 416, 246), 0.8))
check("disconnect picture: a game screen scoring 0.86 off-centre doesn't",
      not app._watch_match_ok(dc, 0.861, (579, 79, 350, 208), 0.8))
check("disconnect picture: 0.86 even in the middle isn't enough",
      not app._watch_match_ok(dc, 0.86, (1072, 586, 416, 246), 0.8))
check("disconnect picture: 0.95 at the bottom of the screen doesn't count",
      not app._watch_match_ok(dc, 0.95, (704, 1100, 465, 277), 0.8))
check("other pictures (Retry) count anywhere, as before", app._watch_match_ok({}, 0.81, (5, 5, 50, 20), 0.8))

# the built-in "Disconnected" word: added with the disconnect action, found on the real box
app.watch_pictures = []
app.add_builtin_disconnect()
pic = app.watch_pictures[-1] if app.watch_pictures else {}
check("built-in Disconnected: added with the disconnect action",
      pic.get("action") == "recover" and pic.get("name") == "Disconnected" and pic.get("screen_h") == 1440,
      {k: v for k, v in pic.items() if k != "img"})
box = os.path.join(src, "tests", "data", "disconnected_screen_part.png")
if os.path.isfile(box):
    part = image_watch.load_image(box)  # Kong's real box, pasted where Roblox puts it on a 2560x1440 screen
    screen = np.full((1440, 2560, 3), 60, np.uint8)
    y, x = 720 - part.shape[0] // 2, 1280 - part.shape[1] // 2
    screen[y:y + part.shape[0], x:x + part.shape[1]] = part
    m = image_watch.Matcher(pic["img"], picked_screen_h=1440, ignore_background=True, screen_h=1440)
    score, rect = m.find(screen, good_enough=0.99)
    check("built-in Disconnected: found on the real box, in the middle",
          score > 0.95 and app._watch_match_ok(pic, score, rect, 0.8), (round(score, 3), rect))

    # the recovery's "is the box still there / gone?" checks (and If/Retry) are light: the middle only for
    # a disconnect picture, a rest between looks, and only a whole look can say it's gone
    app.screen_w, app.screen_h = 2560, 1440
    blank = np.full((1440, 2560, 3), 60, np.uint8)
    shown = {"img": screen}
    regions = []

    def fake_grab(sct=None, region=None):
        regions.append(region)
        return shown["img"].copy()
    real_grab = image_watch.grab_screen
    image_watch.grab_screen = fake_grab
    app.stop_play.clear()
    m = image_watch.Matcher(pic["img"], picked_screen_h=1440, ignore_background=True, screen_h=1440)
    m.picture_entry = pic
    app._look_summary()
    real_shows = lambda *a, **k: core.MacroRecorder._shows(app, *a, **k)
    seen_now = real_shows(m, 0.8, wait=0)
    check("recovery check: the box is seen (one look)", seen_now and len(regions) == 1)
    r = regions[0]
    check("recovery check: a disconnect picture is only looked for in the middle",
          r is not None and r[0] > 500 and r[2] < 2060 and r[1] > 200 and r[3] < 1240, r)
    shown["img"] = blank
    regions.clear()
    check("recovery check: the box gone is noticed", not real_shows(m, 0.8, wait=0))
    check("gone check: wanting it gone says yes on a screen without it",
          app._look_until(m, 0.8, False, 0, 0.5, "recovery"))
    shown["img"] = screen
    began = time.perf_counter()
    gone = app._look_until(m, 0.8, False, 1.0, 0.25, "if/retry")
    took = time.perf_counter() - began
    check("gone check: a box still there is never called gone (only seen ones, up to the time limit)",
          not gone and 0.9 < took < 3.0, round(took, 2))
    shown["img"] = blank
    regions.clear()
    began = time.perf_counter()
    app._look_until(m, 0.8, True, 1.2, 0.5, "recovery")
    check("waiting check: rests between looks (about 2 a second, not as fast as it can)",
          2 <= len(regions) <= 5, len(regions))
    summary = app._look_summary()
    check("health line: picture-check times are counted", "recovery" in summary and "if/retry" in summary, summary)
    check("health line: counts start again after each line", app._look_summary() == "")
    image_watch.grab_screen = real_grab

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} passed")
app.flush_settings() if hasattr(app, "flush_settings") else None
root.destroy()
sys.exit(1 if failed else 0)
