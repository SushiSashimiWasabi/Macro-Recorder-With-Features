"""2.11 preview 2 (Edit window): choosing many, tests from an action, watch-only tests (that must send
nothing), Show my clicks and counters. Opens windows but sends no input to other programs; throwaway
settings, no real message boxes, no real Discord."""
import json
import os
import sys
import tempfile
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_p2_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402

import clicks_view  # noqa: E402
import image_watch  # noqa: E402
import macro_steps as workflow  # noqa: E402
import modern_ui  # noqa: E402
import run_history  # noqa: E402
import window_tools  # noqa: E402

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
app.boxes.askyesno = lambda *a, **k: (asked.append(("askyesno", a)), True)[1]
app.boxes.askyesnocancel = lambda *a, **k: False
modern_ui.messagebox.showwarning = lambda *a, **k: asked.append(("warning", a))
core.messagebox.showerror = lambda *a, **k: asked.append(("error", a))
window_tools.foreground = lambda: None
app.settings.update(pause_when_away=False, results_enabled=False, drops_enabled=False, discord_enabled=False)
app.away_var.set(False)
app.watch_var.set(False)
app.result_pictures = []
app.switch_prog_var.set(False)
app.ready_var.set(0)
app.recover_count_var.set(0)
app._save_settings()
sent = []
app._replay_event = (lambda real: (lambda e, hk, hb: (sent.append(e), None) if not app.ghost
                                   else real(e, hk, hb)))(app._replay_event)


def pump(seconds=0.1):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def key(vk, t, pressed=True):
    return {"type": "key", "key": {"vk": vk}, "pressed": pressed, "t": t}


def tap(vk):
    return [key(vk, 0.0), key(vk, 0.03, False)]


def rec(vk):
    a = workflow.new_action("recorded")
    a["events"] = tap(vk)
    return a


def write(name, actions):
    path = os.path.join(tmp, name + ".macro")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"app": "macro_recorder", "version": 1, "events": workflow.all_events(actions),
                   "actions": actions}, f)
    app._remember_macro(path)
    return path


def wait_play(limit=15):
    t0 = time.time()
    while app.playing and time.time() - t0 < limit:
        pump(0.03)
    pump(0.15)


def pressed():
    return [e["key"]["vk"] for e in sent if e.get("type") == "key" and e.get("pressed")]


# ------------------------------------------------------------ 5. counters
c_add = workflow.new_action("counter_add")
c_add["counter"] = "Wins"
c_if = workflow.new_action("if_counter")
c_if.update(counter="Wins", at_least=2, actions=[rec(71)])
check("counters: in Add action", all(k in workflow.NAMES for k in workflow.COUNTER_KINDS))
check("counters: described in plain words", workflow.describe(c_add) == ("Add to a counter", "Wins +1")
      and workflow.describe(c_if)[1].startswith("Wins is 2 or more"), (workflow.describe(c_add), workflow.describe(c_if)))
dirty = {"kind": "counter_add", "counter": "Evil‮​name" + "x" * 80, "amount": 1e30, "keep": "yes",
         "extra": 1}
workflow.clean_counter_step(dirty)
check("counters from a file are checked: name cleaned and cut, number in range, keep only if true",
      len(dirty["counter"]) <= 30 and "‮" not in dirty["counter"] and dirty["amount"] == 1000000
      and dirty["keep"] is False, dirty)
bad = {"kind": "counter_set", "counter": None, "value": "nan"}
workflow.clean_counter_step(bad)
check("counters: nonsense values become safe ones", bad["counter"] == "Counter" and bad["value"] == 0, bad)
loaded = core.expand_steps([{"kind": "if_counter", "counter": 5, "at_least": "2.5", "actions": [
    {"kind": "counter_add", "counter": "A", "amount": -3000000}]}])
check("counters: opening a file cleans them, also inside groups",
      loaded[0]["counter"] == "5" and loaded[0]["at_least"] == 1 and loaded[0]["actions"][0]["amount"] == -1000000,
      loaded)
# playing: 3 runs of "add 1; if Wins >= 2: press G"
path_c = write("Counting", [c_add, c_if])
app.load(path_c, quiet=True)
app.repeat_var.set(3)
app.loop_var.set(False)
sent.clear()
app.play()
wait_play()
check("counters: count while playing; If a counter reaches runs from the 2nd run on",
      pressed() == [71, 71] and app.counters.get("Wins") == 3, (pressed(), getattr(app, "counters", None)))
sent.clear()
app.play()
wait_play()
check("counters: start at 0 on each Play", app.counters.get("Wins") == 3 and pressed() == [71, 71])
c_add["keep"] = True
write("Counting", [c_add, c_if])
app.load(path_c, quiet=True)
app.play()
wait_play()
app.play()
wait_play()
check("counters: Keep between plays goes on counting (kept in this PC's settings)",
      app.counters.get("Wins") == 6 and app.settings["counter_values"]["counting"]["Wins"] == 6,
      (app.counters, app.settings.get("counter_values")))
check("counters: never written into the macro file",
      "counter_values" not in open(path_c, encoding="utf-8").read())
check("counters: not part of a profile", "counter_values" in __import__("profiles_ui").SKIP_KEYS)
old_kind = {"kind": "if_counter", "actions": [rec(72)]}
check("an older app skips actions it doesn't know (and still plays the recorded part in events)",
      workflow.all_events([rec(70), old_kind]) and core.MacroRecorder._step_events({"kind": "counter_add"}) == [])

# ------------------------------------------------------------ 2. tests from an action
a1, a2, grp, a4 = rec(65), rec(66), workflow.new_action("repeat"), rec(68)
grp.update(times=3, actions=[rec(67), rec(69)])
steps = [a1, a2, grp, a4]
from_inner = workflow.steps_from(steps, grp["actions"][1]["id"])
check("Play from here inside a group: the rest of the group once, then what follows",
      [s.get("events", [{}])[0].get("key", {}).get("vk") for s in from_inner] == [69, 68])
path_t = write("Testing", steps)
app.load(path_t, quiet=True)
app.repeat_var.set(1)
app.open_editor()
ed = app.macro_editor
pump(0.3)
runs_before = len(run_history.runs())
app.loop_var.set(True)  # (a test plays once even when the main window says loop)
ed.tree.selection_set(a2["id"])
ed._step_clicked()
sent.clear()
check("test: starts", ed.test_play("from") and app.playing and app.test_play["mode"] == "test")
check("test: the Edit window is only hidden while it plays", ed.win.winfo_exists() and ed.win.state() == "withdrawn")
seen_word = []
while app.playing:
    pump(0.03)
    if app.overlay is not None:
        seen_word.append(app.overlay.state.cget("text"))
pump(0.2)
check("test: plays from that action to the end, once", pressed() == [66, 67, 69, 67, 69, 67, 69, 68], pressed())
check("test: the timer says TEST", "TEST" in seen_word, set(seen_word))
check("test: not counted in run stats", len(run_history.runs()) == runs_before)
check("test: the Edit window comes back, and the test is over", ed.win.state() != "withdrawn"
      and app.test_play is None and "not counted" in app.sub_note, app.sub_note)
app.loop_var.set(False)
sent.clear()
ed.tree.selection_set([a1["id"], a4["id"]])
ed._step_clicked()
a4["off"] = True
ed.test_play("only")
wait_play()
check("Play only these actions (also when turned off)", pressed() == [65, 68], pressed())
a4.pop("off")
# a test never counts, also not the parts of a chain
inner_path = write("Part", [rec(73)])
chain = workflow.new_action("play_macro")
chain.update(file=inner_path, times=2, counts=True)
calls = []
real_finish = app._finish_run
app._finish_run = lambda c, how: calls.append(c)
app.play_test([chain], "test")
wait_play()
app._finish_run = real_finish
check("test: the parts of a chain aren't counted either", calls == [] and pressed()[-2:] == [73, 73], calls)
# Stop during a test (and Ctrl+Alt+End is the same stop)
w = workflow.new_action("wait")
w["seconds"] = 5
app.play_test([w, rec(74)], "test")
pump(0.3)
app.emergency_stop()
wait_play()
check("test: Ctrl+Alt+End stops it", not app.playing and 74 not in pressed() and app.test_play is None)

# ------------------------------------------------------------ 3. watch only: nothing may be pressed
low = []
real_move_to, real_move_rel = core.move_to, core.move_relative
core.move_to = lambda *a, **k: low.append(("move_to", a))
core.move_relative = lambda *a, **k: low.append(("move_relative", a))


class Spy:
    def __getattr__(self, name):
        return lambda *a, **k: low.append((name, a))
    position = (0, 0)


app.kb_ctrl, app.mouse_ctrl = Spy(), Spy()
fronted = []
real_front = window_tools.force_to_front
window_tools.force_to_front = lambda *a: fronted.append(a)
click = workflow.new_action("click")
click.update(x=300, y=200)
typed = workflow.new_action("type")
typed["text"] = "hi"
pic_if = workflow.new_action("if")
pic_if["actions"] = [rec(75)]
waitp = workflow.new_action("wait_picture")
waitp.update(png="x", click=True, otherwise="stop")
move_rec = workflow.new_action("recorded")
move_rec["events"] = [{"type": "move", "x": 10, "y": 10, "t": 0.0}, {"type": "click", "x": 10, "y": 10,
                      "button": "left", "pressed": True, "t": 0.02},
                      {"type": "click", "x": 10, "y": 10, "button": "left", "pressed": False, "t": 0.05},
                      {"type": "move_rel", "dx": 30, "dy": 0, "t": 0.06}, key(76, 0.07), key(76, 0.09, False)]
ghost_steps = [click, typed, pic_if, waitp, move_rec]
sent.clear()
app.play_test(ghost_steps, "ghost", found=True)
check("watch only: starts with nothing pressing", app.ghost and isinstance(app.kb_ctrl, modern_ui.NoInput))
ghost_words = []
while app.playing:
    pump(0.03)
    if app.overlay is not None:
        ghost_words.append((app.overlay.state.cget("text"), app.overlay.note.cget("text")))
pump(0.2)
check("watch only: NOTHING was pressed, clicked or moved", low == [] and sent == [] and fronted == [],
      (low[:5], sent[:5], fronted))
check("watch only: the banner says nothing is pressed", any(w == "WATCH ONLY" and "Nothing is pressed" in n
                                                            for w, n in ghost_words), set(ghost_words))
check("watch only: the keys are shown", any("Pressing" in n for _w, n in ghost_words))
check("watch only: the dot was shown where the mouse would be", getattr(app, "ghost_dot", None) is not None
      and getattr(app, "ghost_at", None) is not None, getattr(app, "ghost_at", None))
check("watch only: the real controllers are back afterwards", isinstance(app.kb_ctrl, Spy) and not app.ghost)
# picture steps take the chosen way: found (above) played the If; not found skips it and stops at the wait
notes = []
real_note = app._set_note
app._set_note = lambda t: (notes.append(t), real_note(t))
app.play_test([pic_if], "ghost", found=True)
wait_play()
found_keys = [n for n in notes if "counts as found" in n]
notes.clear()
app.play_test([pic_if, waitp, rec(77)], "ghost", found=False)
wait_play()
app._set_note = real_note
check("watch only: a picture counts as found (a note says so)", found_keys)
check("watch only: or as not found when ticked (the If is skipped, the wait stops the test)",
      any("counts as not found" in n for n in notes) and low == [], notes)
core.move_to, core.move_relative = real_move_to, real_move_rel
window_tools.force_to_front = real_front

# ------------------------------------------------------------ 1. choosing many in the Edit window
app.load(path_t, quiet=True)
ed.win.destroy()
app.open_editor()
ed = app.macro_editor
pump(0.3)
ids = [a["id"] for a in ed.steps]
ed.tree.selection_set([ids[0], ids[1]])
ed._step_clicked()
check("many: the details say how many are chosen", any("2 actions chosen" == getattr(w, "cget", lambda k: "")("text")
                                                       for w in ed.detail.winfo_children()[0].winfo_children()))
n_undo = len(ed.undo_stack)
ed.duplicate()
check("many: Duplicate copies all of them (after each), one Undo point",
      len(ed.steps) == 6 and len(ed.undo_stack) == n_undo + 1 and len(ed.tree.selection()) == 2)
ed.undo()
check("many: one Undo puts it all back", [a["id"] for a in ed.steps] == ids)
ed.tree.selection_set([ids[1], ids[3]])
ed.move(-1)
check("many: Move up moves each one place up", [a["id"] for a in ed.steps] == [ids[1], ids[0], ids[3], ids[2]],
      [ids.index(a["id"]) for a in ed.steps])
ed.undo()
ed.tree.selection_set([ids[0], ids[1]])
ed.copy()
ed.tree.selection_set(ids[3])
ed.paste()
check("many: Copy and Paste several", len(ed.steps) == 6 and ed.steps[4]["events"] == ed.steps[0]["events"])
ed.undo()
ed.tree.selection_set([ids[0], ids[1]])
ed.cut()
check("many: Cut takes them out and can be pasted", len(ed.steps) == 2 and len(ed.clipboard) == 2)
ed.undo()
ed.tree.selection_set([ids[0], ids[3]])
ed.toggle_off()
check("many: Turn off all chosen", ed.steps[0].get("off") and ed.steps[3].get("off") and not ed.steps[1].get("off"))
ed.toggle_off()
check("many: and on again", not ed.steps[0].get("off") and not ed.steps[3].get("off"))
ed.tree.selection_set([ids[0], ids[1]])
ed.group_into("repeat")
check("many: Group into puts them in one group", ed.steps[0]["kind"] == "repeat"
      and [a["id"] for a in ed.steps[0]["actions"]] == ids[:2])
ed.undo()
inner_id = grp["actions"][0]["id"]
ed.tree.selection_set([ids[0], inner_id])
ed.group_into("if")
check("many: grouping actions from different lists says why not", asked and "same list" in str(asked[-1]))
# remove: more than 5 asks first
ed.tree.selection_set(ids)
asked.clear()
ed.remove()
check("many: removing 4 doesn't ask", not any(n == "askyesno" for n, _a in asked) and ed.steps == [])
ed.undo()
for _ in range(2):
    ed.tree.selection_set([a["id"] for a in ed.steps])
    ed.duplicate()
asked.clear()
ed.tree.selection_set([a["id"] for a in ed.steps])
ed.remove()
check("many: removing more than 5 asks first", any(n == "askyesno" and "16 actions" in str(a) for n, a in asked),
      asked)
ed.undo()
ed.reset()
# dragging chosen actions onto another place
ed.tree.selection_set([ids[0], ids[1]])
ed._drop_steps(list(ed.tree.selection()), ids[3], "after")
check("drag: chosen actions go after the one they're dropped on", [a["id"] for a in ed.steps] == [ids[2], ids[3],
                                                                                                    ids[0], ids[1]])
ed.undo()
ed.tree.selection_set([ids[2]])
ed._drop_steps([ids[2]], inner_id, "before")
check("drag: a group can't be dropped inside itself", [a["id"] for a in ed.steps] == ids)
ed.tree.selection_set([ids[0]])
ed._drop_steps([ids[0]], inner_id, "before")
check("drag: an action can be dropped into a group", ed.steps[1]["actions"][0]["id"] == ids[0])
ed.undo()
# the drag itself (mouse events on the list)
ed.tree.update_idletasks()
pump(0.2)
b0, b3 = ed.tree.bbox(ids[0]), ed.tree.bbox(ids[3])
if b0 and b3:
    ed.tree.selection_set([])
    drag = [d for d in ed.tree.bind("<ButtonPress-1>").split("\n") if d]
    ed.tree.event_generate("<ButtonPress-1>", x=20, y=b0[1] + 3)
    ed.tree.event_generate("<B1-Motion>", x=20, y=b0[1] + b0[3] + 3)
    pump(0.05)
    ed.tree.event_generate("<ButtonRelease-1>", x=20, y=b0[1] + b0[3] + 3)
    pump(0.05)
    check("drag over actions chooses them", set(ed.tree.selection()) >= {ids[0], ids[1]}, ed.tree.selection())
# the macro list: several at once
paths_before = list(app.macro_list())
ed.macros.selection_set([str(i) for i, (_l, p) in enumerate(ed.entries) if p in (path_c, inner_path)])
ed.focus = "macros"
asked.clear()
ed.remove()
check("macros: Remove takes several off the list (asks once, files kept)",
      sum(1 for n, _a in asked if n == "askyesno") == 1 and path_c not in app.macro_list()
      and os.path.isfile(path_c) and len(app.macro_list()) == len(paths_before) - 2)

# ------------------------------------------------------------ 4. Show my clicks
cl = workflow.new_action("click")
cl.update(x=100, y=100)
rec_c = workflow.new_action("recorded")
rec_c["events"] = [{"type": "move", "x": 5 * i, "y": 5 * i, "t": i * 0.01} for i in range(2000)] + [
    {"type": "click", "x": 50, "y": 60, "button": "left", "pressed": True, "t": 21.0},
    {"type": "click", "x": 50, "y": 60, "button": "left", "pressed": False, "t": 21.1}]
found = clicks_view.parts([rec_c, cl])
check("clicks: numbered in playing order", [m[3] for _i, _n, ms in found for m in ms if m[0] == "click"] == [1, 2])
check("clicks: a long mouse path is drawn simplified",
      len(next(m for m in found[0][2] if m[0] == "path")[1]) <= clicks_view.MAX_PATH_POINTS + 2)
real_grab = image_watch.grab_screen
shots = []
image_watch.grab_screen = lambda *a, **k: (shots.append(1), np.zeros((app.screen_h, app.screen_w, 3), np.uint8))[1]
ed.steps = [rec_c, cl]
ed._fill_steps()
ed.file_data = {}
app.macro_screen = None
files_before = sorted(os.path.join(d, f) for d, _s, fs in os.walk(tmp) for f in fs)
cw = ed.show_clicks()
pump(0.3)
image_watch.grab_screen = real_grab
check("clicks: the window opens with the screenshot taken once", cw is not None and shots == [1])
dots = cw.canvas.find_withtag("dot")
check("clicks: a dot for each click", len(dots) == 4, len(dots))  # (a circle and its number each)
x0, y0, x1, y1 = cw.canvas.coords(dots[-2])
cw.canvas.event_generate("<Button-1>", x=int((x0 + x1) / 2), y=int((y0 + y1) / 2))
pump(0.2)
check("clicks: clicking a dot chooses its action in Edit", ed.tree.selection() == (cl["id"],), ed.tree.selection())
cw.step(1)
check("clicks: one part at a time", "Part 1 of 2" in str([w.cget("text") for w in cw.winfo_children()[1].winfo_children()
                                                           if isinstance(w, tk.Label)]))
check("clicks: the screenshot isn't saved anywhere",
      sorted(os.path.join(d, f) for d, _s, fs in os.walk(tmp) for f in fs) == files_before)
cw.destroy()
ed.win.destroy()

# ------------------------------------------------------------ round 2 (Kong's test of preview 2)
import raw_mouse  # noqa: E402

# 1. a test from Edit starts even when the main window has no macro, and is never silent
app.events, app.actions, app.current_file = [], None, None
sent.clear()
started = app.play_test([rec(78)], "test")
wait_play()
check("test starts with no macro open in the main window", started and pressed() == [78], pressed())
app.events, app.actions = [], None
app.play()
check("normal Play with no macro still does nothing", not app.playing)
asked.clear()
w2 = workflow.new_action("wait")
w2["seconds"] = 3
app.play_test([w2], "test")
pump(0.2)
again = app.play_test([rec(79)], "test")
check("a test that can't start says why", again is False and any("can't start" in str(a) for _n, a in asked), asked)
app.stop_playback()
wait_play()

# 6. camera recording starts every time (the hidden window's name is never used twice)
if raw_mouse.IS_WIN:
    oks = []
    for _ in range(20):
        rm = raw_mouse.RawMouse(lambda dx, dy: None)
        oks.append(rm.start())
        rm.stop()
        del rm
    check("camera recording starts 20 times in a row", all(oks), oks)

# B. camera steps keep where the pointer was, and playback puts it back there
app.events = []
app.recording = True
app.paused = False
app.start_time = time.perf_counter()
app.paused_total = 0.0


class Here:
    position = (321, 654)


real_ctrl = app.mouse_ctrl
app.mouse_ctrl = Here()
app.camera_dx, app.camera_dy = 5, -2
app._flush_camera()
app.recording = False
check("camera step keeps the pointer's spot", app.events and app.events[-1].get("x") == 321
      and app.events[-1].get("y") == 654 and app.events[-1]["dx"] == 5, app.events[-1:])
moves = []
real_rel = core.move_relative
core.move_relative = lambda ctrl, dx, dy, held=(): moves.append(("rel", dx, dy))


class Spot:
    def __init__(self):
        self.where = None

    @property
    def position(self):
        return self.where

    @position.setter
    def position(self, xy):
        self.where = xy
        moves.append(("put", xy))


app.mouse_ctrl = Spot()
core.MacroRecorder._replay_event(app, {"type": "move_rel", "dx": 5, "dy": -2, "x": 321, "y": 654}, set(), set())
core.MacroRecorder._replay_event(app, {"type": "move_rel", "dx": 1, "dy": 1}, set(), set())
core.move_relative = real_rel
app.mouse_ctrl = real_ctrl
check("playback: the camera turn is sent, then the pointer is put on the recorded spot",
      moves == [("rel", 5, -2), ("put", (321, 654)), ("rel", 1, 1)], moves)
check("fitting to another screen moves that spot too",
      core.scale_events([{"type": "move_rel", "dx": 5, "dy": 0, "x": 960, "y": 540}], (1920, 1080),
                        (2560, 1440))[0]["x"] == 1280)

# 2. inside an empty group: record / insert, and dropping on the group's row
app.load(path_t, quiet=True)
app.open_editor()
ed = app.macro_editor
pump(0.3)
empty = workflow.new_action("if_counter")
ed.change(lambda: ed.steps.append(empty), select=empty["id"])
ed.tree.selection_set(empty["id"])
ed._step_clicked()
check("record/insert offer \"Inside the chosen group\" when a group is chosen",
      ("Inside the chosen group", "inside") in ed._where_choices())
ed._insert_steps([rec(80)], "inside", empty["id"])
check("inserted inside the empty group", len(empty["actions"]) == 1)
ed.undo()
ed.tree.selection_set(ed.steps[0]["id"])
ed._step_clicked()
check("no \"inside\" choice for a normal action", not any(v == "inside" for _t, v in ed._where_choices()))
first = ed.steps[0]["id"]
ed.tree.selection_set(first)
group = next(a for a in ed.steps if a["id"] == empty["id"])
ed._drop_steps([first], empty["id"], "into")
group = next(a for a in ed.steps if a["id"] == empty["id"])
check("dropping on a group's row puts it inside (also when the group is empty)",
      [a["id"] for a in group["actions"]] == [first] and all(a["id"] != first for a in ed.steps))
ed.undo()
pump(0.1)
drag = ed.tree.bind  # (the drag helper decides "into" from where on the row the mouse is)
helpers = [w for w in ed.tree.winfo_children()]
box = ed.tree.bbox(empty["id"])
if box:
    import ui_common

    td = ui_common.TreeDrag.__new__(ui_common.TreeDrag)
    td.tree, td.is_group = ed.tree, (lambda iid: "group" in ed.tree.item(iid, "tags"))
    ed.tree.selection_set(first)
    mid = box[1] + box[3] // 2
    check("drag: the middle of a group's row means inside, its edges above / below",
          td.where(empty["id"], mid) == "into" and td.where(empty["id"], box[1] + 1) == "before"
          and td.where(empty["id"], box[1] + box[3] - 1) == "after")

# 4. the watch-only picture switch: a green / red dot, and an explanation
m = ed._menu()
ed._test_items(m)
labels = [m.entrycget(i, "label") for i in range(m.index("end") + 1) if m.type(i) == "command"]
check("menu: \"Pretend pictures are NOT found: off\" with a dot", any("NOT found: off" in t for t in labels)
      and any(m.entrycget(i, "image") for i in range(m.index("end") + 1) if m.type(i) == "command"
              and "NOT found" in m.entrycget(i, "label")), labels)
k = next(i for i in range(m.index("end") + 1) if m.type(i) == "command" and "NOT found" in m.entrycget(i, "label"))
m.invoke(k)
m2 = ed._menu()
ed._test_items(m2)
check("menu: one click turns it on (green)", ed.ghost_not_found.get() and any(
    "NOT found: on" in m2.entrycget(i, "label") for i in range(m2.index("end") + 1) if m2.type(i) == "command"))
ed.ghost_not_found.set(False)
asked.clear()
ed._ghost_help()
check("menu: What does that mean? explains both ways", asked and "FOUND" in str(asked[-1]) and "Retry" in str(asked[-1]))
ed.win.destroy()

# 3. a short dark box is as wide as the others
real_boxes = modern_ui.ThemedBoxes(app)
sizes = []
root.after(400, lambda: (sizes.append(real_boxes.open_boxes[-1].winfo_width()), real_boxes.close_all()))
real_boxes.askyesno("Edit", "Remove these 16 actions?\n\nUndo puts them back.", parent=root)
check("a short question box is as wide as the others (about 520 px)", sizes and sizes[0] >= 480, sizes)

# 5. choose many in "Edit the recorded events…"
evs = [key(65, 0.0), key(65, 0.1, False), {"type": "move", "x": 1, "y": 1, "t": 0.2}, key(66, 0.3),
       key(66, 0.4, False), {"type": "move", "x": 2, "y": 2, "t": 0.5}, key(67, 1.0), key(67, 1.1, False)]
got = []
ew = app._events_window(root, [dict(e) for e in evs], lambda e: got.append(e))
pump(0.3)
ops, tree = ew.ops, ew.tree


def kinds():
    return [(e.get("key", {}).get("vk"), e.get("pressed")) if e["type"] == "key" else e["type"] for e in
            [ew_events() [i] for i in range(len(ew_events()))]]


def ew_events():
    return [tree.item(i, "values") for i in tree.get_children()]


n0 = len(tree.get_children())
tree.selection_set(["3"])  # B pressed: its let-go goes along
ops["duplicate"]()
check("events: Duplicate takes the matching let-go along (nothing stays held)", len(tree.get_children()) == n0 + 2
      and "taken along" in ops["note"].get(), ops["note"].get())
ops["undo"]()
check("events: Undo", len(tree.get_children()) == n0)
ops["redo"]()
ops["undo"]()
tree.selection_set(["0"])
ops["move"]([0], 6, "after")
vals = [tree.item(i, "values")[2] for i in tree.get_children()]
check("events: drag-move puts A (press and let-go) after C, keeping times in order",
      len(vals) == n0 and [float(tree.item(i, "values")[0].split()[0]) for i in tree.get_children()] ==
      sorted(float(tree.item(i, "values")[0].split()[0]) for i in tree.get_children()))
ops["undo"]()
tree.selection_set([str(i) for i in range(n0)])
ops["copy"]()
asked.clear()
ops["remove"]()
check("events: removing more than 5 asks first", any("Remove these 8" in str(a) for _n, a in asked), asked)
ops["undo"]()
tree.selection_set(["7"])
ops["paste"]()
check("events: Paste puts copies after the chosen row", len(tree.get_children()) == 2 * n0)
ops["undo"]()
ew.apply()
check("events: Apply hands back the list", got and len(got[0]) == n0)

# the "Record in which window?" box
wins = window_tools.app_windows()
check("the window list has titles and program names (only shown, never saved)",
      all(isinstance(t, str) and t for _h, t, _e in wins))


def answer(choose, profile=None, new_name=None):
    def go():
        box = getattr(app, "record_window_box", None)
        if box is None:
            root.after(100, go)
            return
        tr = next(w for w in box.winfo_children()[0].winfo_children() if isinstance(w, ttk_mod.Treeview))
        if choose is None:
            box.destroy()
            return
        tr.selection_set(choose)
        if profile:
            combo = [w for w in all_children(box) if isinstance(w, ttk_mod.Combobox)][0]
            combo.set(profile)
        for b in all_children(box):
            if isinstance(b, ttk_mod.Button) and b.cget("text") == "Start":
                b.invoke()
                return
    root.after(200, go)


def all_children(w):
    for c in w.winfo_children():
        yield c
        yield from all_children(c)


from tkinter import ttk as ttk_mod  # noqa: E402

answer("desktop")
picked = app.ask_record_window()
check("the box gives back the chosen window (here: the desktop)", picked and picked[0] == "desktop", picked)
answer(None)
check("closing the box cancels recording", app.ask_record_window() is None)
app.save_profile("Farm")
answer("desktop", profile="Farm")
picked = app.ask_record_window()
check("More…: link to an existing profile", picked and picked[1] == ("existing", "Farm"), picked)
app.pending_profile = ("new", "Night farm")
app.events = [key(65, 0.0), key(65, 0.1, False)]
app.actions = None
out_path = os.path.join(tmp, "Fresh.macro")
modern_ui.filedialog.asksaveasfilename = lambda **k: out_path
app.save()
check("the new profile is only made when the macro is saved, and the macro is linked to it",
      "Night farm" in app.profiles() and json.load(open(out_path, encoding="utf-8")).get("profile") == "Night farm")
app.pending_profile = ("new", "Never made")
app.record_countdown_left = 1
app.record_countdown_job = None
app.toggle_record()  # (Record again during the countdown: cancelled)
check("a cancelled recording makes no profile", "Never made" not in app.profiles() and app.pending_profile is None)
check("the record countdown is 5 s unless set", core.int_setting({}, "record_ready_seconds", 5, 0, 600) == 5
      and app._record_ready_seconds() in (0, 5) or "record_ready_seconds" in app.settings)
check("Record from a game (another window in front) never asks", not app._ask_record_window_now())
# a recording made in Edit is fitted to the macro's own size
app.load(path_t, quiet=True)
app.open_editor()
ed = app.macro_editor
pump(0.2)
app.macro_screen, app.macro_program = (app.screen_w // 2, app.screen_h // 2), None
app.settings["fit_to"] = "screen"
fitted = ed.to_macro_size([{"type": "click", "x": app.screen_w // 2, "y": app.screen_h // 2, "button": "left",
                            "pressed": True, "t": 0.0}])
check("Edit recording: fitted to the macro's own screen size",
      (fitted[0]["x"], fitted[0]["y"]) == (app.screen_w // 4, app.screen_h // 4), fitted)
app.macro_screen = (app.screen_w, app.screen_h)
same = ed.to_macro_size([{"type": "click", "x": 10, "y": 20, "button": "left", "pressed": True, "t": 0.0}])
check("Edit recording: same size stays as it is", (same[0]["x"], same[0]["y"]) == (10, 20))
ed.win.destroy()

# ------------------------------------------------------------ the freeze (Kong 16 Nov): the box is always on screen
real_fg, real_pid = window_tools.foreground, window_tools.pid_of
window_tools.foreground = lambda: 12345  # (this app is in front: the box is asked)
window_tools.pid_of = lambda h: os.getpid()
app.rec_ask_window_var.set(True)
app.settings["record_ask_window"] = True
app.events, app.actions = [], None


def box_then_cancel(action):
    seen = {}

    def look():
        box = getattr(app, "record_window_box", None)
        if box is None or not box.winfo_exists():
            root.after(50, look)
            return
        seen["on_screen"] = bool(box.winfo_viewable())
        box.destroy()
    root.after(200, look)
    action()
    pump(0.3)
    return seen.get("on_screen")


root.deiconify()
pump(0.2)
windows_only("box: Record in the main window shows it on screen") or check("box: Record in the main window shows it on screen", box_then_cancel(app.toggle_record)
      and not app.recording and app.record_countdown_left == 0)
app.load(path_t, quiet=True)
app.open_editor()
ed = app.macro_editor
pump(0.3)
app.boxes.askchoice = lambda *a, **k: "end"
windows_only("box: Record keys and mouse… in Edit shows it on screen (the freeze)") or check("box: Record keys and mouse… in Edit shows it on screen (the freeze)", box_then_cancel(ed.record_here))
windows_only("box: cancelling it brings the Edit window back, nothing records") or check("box: cancelling it brings the Edit window back, nothing records",
      ed.win.state() != "withdrawn" and app.record_into is None and not app.recording)
empty2 = workflow.new_action("repeat")
ed.change(lambda: ed.steps.append(empty2), select=empty2["id"])
ed.tree.selection_set(empty2["id"])
app.boxes.askchoice = lambda *a, **k: "inside"
windows_only("box: also for recording inside the chosen group") or check("box: also for recording inside the chosen group", box_then_cancel(ed.record_here)
      and ed.win.state() != "withdrawn")
root.withdraw()
pump(0.1)
app.boxes.askchoice = lambda *a, **k: "end"
windows_only("box: on screen even when no window of the app is showing") or check("box: on screen even when no window of the app is showing", box_then_cancel(ed.record_here))
root.deiconify()
ew2 = app._events_window(ed.win, [key(65, 0.0), key(65, 0.1, False)], lambda e: None)
pump(0.2)
windows_only("box: Record here… in the recorded events shows it on screen") or check("box: Record here… in the recorded events shows it on screen", box_then_cancel(ew2.record_here))
windows_only("box: and both windows come back") or check("box: and both windows come back", ew2.winfo_exists() and ew2.state() != "withdrawn"
      and ed.win.state() != "withdrawn")
ew2.destroy()
ed.win.destroy()
window_tools.foreground, window_tools.pid_of = real_fg, real_pid
check("box: the Record key from a game never shows it", not app._ask_record_window_now())

# ------------------------------------------------------------ preview the chosen rows of the recorded events
app.load(path_t, quiet=True)
app.open_editor()
ed = app.macro_editor
pump(0.3)
rows_evs = [key(81, 0.0), key(81, 0.05, False), {"type": "move", "x": 5, "y": 5, "t": 0.1}, key(82, 5.0),
            key(82, 5.05, False), key(83, 30.0), key(83, 30.05, False)]
ew3 = app._events_window(ed.win, [dict(e) for e in rows_evs], lambda e: None)
pump(0.2)
ew3.tree.selection_set(["0", "5"])  # Q pressed and S pressed, far apart: their let-gos come along
step, added = ew3.ops["rows_step"]()
times = [e["t"] for e in step["events"]]
check("preview rows: the matching let-gos are taken along", len(step["events"]) == 4 and len(added) == 2,
      step["events"])
check("preview rows: the time between far-apart rows is skipped", times[-1] < 1.0, times)
sent.clear()
runs_before = len(run_history.runs())
ew3.ops["preview"]("test")
check("preview rows: the window hides while they play", ew3.state() == "withdrawn")
wait_play()
check("preview rows: plays only the chosen rows (with their let-gos), never counted",
      pressed() == [81, 83] and len(run_history.runs()) == runs_before, pressed())
check("preview rows: the window comes back afterwards", ew3.winfo_exists() and ew3.state() != "withdrawn")
check("preview rows: nothing stays held down", not any(app.held_lists))
low.clear()
real_move_to, real_move_rel = core.move_to, core.move_relative
core.move_to = lambda *a, **k: low.append(("move_to", a))
core.move_relative = lambda *a, **k: low.append(("move_relative", a))
app.kb_ctrl, app.mouse_ctrl = Spy(), Spy()
sent.clear()
ew3.tree.selection_set(["2", "3"])
ew3.ops["preview"]("ghost")
wait_play()
core.move_to, core.move_relative = real_move_to, real_move_rel
check("preview rows: Show without playing presses nothing", low == [] and sent == [], (low[:3], sent[:3]))
real_grab = image_watch.grab_screen
image_watch.grab_screen = lambda *a, **k: np.zeros((app.screen_h, app.screen_w, 3), np.uint8)
ew3.tree.selection_set(["2"])
cw2 = ew3.ops["preview"]("clicks")
pump(0.3)
image_watch.grab_screen = real_grab
check("preview rows: Show my clicks for the chosen rows", cw2 is not None and len(cw2.found) == 1)
if cw2 is not None:
    cw2.destroy()
ew3.destroy()
ed.win.destroy()

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
root.destroy()
sys.exit(0 if passed == len(results) else 1)
