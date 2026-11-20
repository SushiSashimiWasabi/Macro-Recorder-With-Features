"""2.13 review fixes: moving actions in / out of groups never splits an If from its Else, the tour closes when
playing starts, a folder that can't be made leaves a macro's folder alone, a bad milestone date is dropped,
one odd event doesn't stop the keys-on-screen box.
Opens windows (off to the side) but sends no input to other programs; throwaway settings."""
import json
import os
import sys
import tempfile
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_review213_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import tkinter as tk  # noqa: E402

import macro_steps as workflow  # noqa: E402
import milestones_ui  # noqa: E402
import modern_ui  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


root = tk.Tk()
root.withdraw()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
for name in ("showwarning", "showinfo", "showerror"):
    setattr(app.boxes, name, lambda *a, **k: None)
app.boxes.askyesno = lambda *a, **k: True
app.rec_ask_window_var.set(False)
app._save_settings()


def pump(n=5):
    for _ in range(n):
        root.update()
        time.sleep(0.02)


root.deiconify()
root.geometry("+30+30")
pump(10)

# ---------------------------------------------------------------- 1: If and Else stay together in Edit
path = os.path.join(tmp, "ifelse.macro")
with open(path, "w", encoding="utf-8") as f:
    json.dump({"app": "macro_recorder", "version": 1, "events": [
        {"type": "key", "key": {"vk": 65}, "pressed": True, "t": 0.0},
        {"type": "key", "key": {"vk": 65}, "pressed": False, "t": 0.2}]}, f)
app._remember_macro(path)
app.load(path, quiet=True)
pump()
app.open_editor()
ed = app.macro_editor
ed.win.geometry("1220x720+40+40")
pump(10)


def build():
    """[If [wait a], Else [wait b], wait c]; returns the ids."""
    a, b, c = (workflow.new_action("wait") for _ in range(3))
    i, e = workflow.new_action("if"), workflow.new_action("else")
    i["actions"], e["actions"] = [a], [b]
    ed.steps = [i, e, c]
    ed._fill_steps()
    pump()
    return {"if": i["id"], "else": e["id"], "a": a["id"], "b": b["id"], "c": c["id"]}


def pick(step_id):
    ed.tree.selection_set(step_id)
    pump(2)


def kinds():
    return [s["kind"] for s in ed.steps]


ids = build()
pick(ids["a"])
ed.out_of_group()
pump()
check("Out: the last action leaves an If that has an Else: the Else still follows the If",
      kinds() == ["if", "else", "wait", "wait"], kinds())

ids = build()
pick(ids["if"])
ed.ungroup()
pump()
check("Ungroup: an If with an Else after it is not ungrouped (the Else would lose its If)",
      kinds() == ["if", "else", "wait"], kinds())

ids = build()
pick(ids["else"])
ed.into_group_above()
pump()
check("In: an Else can't be pushed inside its If", kinds() == ["if", "else", "wait"]
      and not ed.steps[0]["actions"][0]["kind"] == "else", kinds())

ids = build()
pick(ids["b"])
ed.out_of_group()
pump()
check("Out: an action leaving the Else goes after it (it was the last one in the list)",
      kinds() == ["if", "else", "wait", "wait"], kinds())

ids = build()
pick(ids["if"])
in_g, above_g, is_g = ed._group_moves()
check("buttons: an If with an Else after it can't be ungrouped, moved in or moved out", not is_g and not above_g)

# ---------------------------------------------------------------- 2: the tour closes when playing starts
app.settings["first_start_done"] = True
app.settings.pop("tour_done", None)
app.start_tour()
pump(3)
app.playing = True
app.tour_stop_if_busy()
pump(2)
app.playing = False
check("tour: closes when a macro starts playing, and isn't marked as done", app.tour_win is None
      and not app.settings.get("tour_done"))

# ---------------------------------------------------------------- 3: a folder that can't be made changes nothing
pa = os.path.join(tmp, "a.macro")
with open(pa, "w", encoding="utf-8") as f:
    json.dump({"app": "macro_recorder", "version": 1, "events": []}, f)
app._remember_macro(pa)
app.set_macro_folder([pa], "Farm")
app.settings["macro_folders"] = [f"F{i}" for i in range(50)]
ok = app.set_macro_folder([pa], "One too many")
check("folders: the 51st folder isn't made and the macro keeps its folder", app.macro_meta(pa)["folder"] == "Farm"
      and ok is False, app.macro_meta(pa))
ok = app.set_macro_folder([pa], "​​")
check("folders: a name with nothing printable changes nothing", app.macro_meta(pa)["folder"] == "Farm" and ok is False)
check("folders: 'No folder' still works", app.set_macro_folder([pa], "") is not False and app.macro_meta(pa)["folder"] == "")

# ---------------------------------------------------------------- 4: a bad milestone date is dropped
bad = milestones_ui.clean_milestone({"kind": "runs", "at": 5, "reached": "abcdefghij"})
good = milestones_ui.clean_milestone({"kind": "runs", "at": 5, "reached": "2026-11-19"})
check("milestones: a made-up date is dropped, a real one kept", "reached" not in bad and good.get("reached") == "2026-11-19",
      (bad, good))
app.settings["milestones"] = [{"kind": "runs", "at": 5, "reached": "abcdefghij"}]
win = app.open_milestones()
pump(3)
check("milestones: the window opens with a bad date in the file", win.winfo_exists())
win.destroy()

# ---------------------------------------------------------------- 5: one odd event doesn't stop the keys box
ov = app._keys_overlay()
ov.pending.clear()
ov.add({"type": "scroll", "dy": None})
ov.add({"type": "key", "key": "abc", "pressed": True})
ov.add({"type": "key", "key": {"char": "w"}, "pressed": True})
err = None
try:
    ov.tick()
except Exception as exc:  # noqa: BLE001
    err = exc
check("keys box: odd events are skipped, the good one still shows", err is None and
      [t for t, _ in ov.lines] == ["W"], (err, list(ov.lines)))
ov.hide()

# ---------------------------------------------------------------- window sizes (stand-in window, no real one moves)
class FakeWin:
    def __init__(self, req=(400, 300), size=(900, 700)):
        self.req, self.size, self.geo, self.jobs, self.binds = req, size, [], [], []

    def winfo_screenwidth(self): return 1000
    def winfo_screenheight(self): return 800
    def winfo_vrootwidth(self): return 4000  # (two screens side by side)
    def winfo_vrootheight(self): return 800
    def winfo_reqwidth(self): return self.req[0]
    def winfo_reqheight(self): return self.req[1]
    def winfo_width(self): return self.size[0]
    def winfo_height(self): return self.size[1]
    def winfo_viewable(self): return True
    def state(self): return "normal"
    def update_idletasks(self): pass
    def geometry(self, g=None): self.geo.append(g)
    def bind(self, seq, fn, add=None): self.binds.append(fn)
    def after(self, ms, fn): self.jobs.append(fn); return len(self.jobs)
    def after_cancel(self, job): pass


w = FakeWin()
app.settings["t1_size"] = "3000x500"
app._keep_window_size(w, "t1_size")
check("window size: a size on the second screen is kept (limit is both screens, not the main one)",
      w.geo == ["3000x500"], w.geo)

w = FakeWin(req=(600, 300))
app.settings.update({"t2_size": "1500x700", "t2_size_base": "400x300"})
app._keep_window_size(w, "t2_size")
check("window size: a size saved before the contents grew is not used", w.geo == [], w.geo)
w = FakeWin(req=(404, 300))
app._keep_window_size(w, "t2_size")
check("window size: a tiny change in the contents doesn't lose the saved size", w.geo == ["1500x700"], w.geo)
w = FakeWin(req=(400, 300))
app.settings["t3_size"] = "1500x700"
app._keep_window_size(w, "t3_size")  # (saved by an older version: no base known: used)
check("window size: a saved size with no base (older version) is still used", w.geo == ["1500x700"], w.geo)

w = FakeWin(req=(400, 300), size=(900, 700))
app._keep_window_size(w, "t4_size")
w.binds[-1](type("E", (), {"widget": w})())
w.jobs[-1]()
check("window size: the size and the contents' size it was made for are saved",
      app.settings.get("t4_size") == "900x700" and app.settings.get("t4_size_base") == "400x300",
      (app.settings.get("t4_size"), app.settings.get("t4_size_base")))
w.size = (400, 300)
w.binds[-1](type("E", (), {"widget": w})())
w.jobs[-1]()
check("window size: back to the usual size forgets both", "t4_size" not in app.settings
      and "t4_size_base" not in app.settings)

# ---------------------------------------------------------------- folders: entries of macros that are gone
gone = os.path.join(tmp, "gone.macro")
app.settings["macro_folders"] = []  # (the 50 made above)
app.set_macro_folder([pa], "Keep")
app.settings.setdefault("macro_meta", {})[app._meta_key(gone)] = {"folder": "Old", "tags": ["x"]}
app._show_macro_list()
store = app.settings["macro_meta"]
check("folders: the folder and tags of a macro that no longer exists are cleaned out",
      app._meta_key(gone) not in store, list(store))
check("folders: a macro still in the list keeps its folder", app.macro_meta(pa)["folder"] == "Keep")

# ---------------------------------------------------------------- playback: an If inside an If's body doesn't change its Else
import threading  # noqa: E402


class PlayStub(core.MacroRecorder):
    """The real step runner, with no window: conditions are given in the step, marks are recorded."""

    def __init__(self):
        self.stop_play = threading.Event()
        self.ran = []

    def _condition_one(self, c, wait=0.0):
        return c["val"]

    def _new_condition(self, c):
        return False

    def _run_step(self, a, ctx):
        if a.get("kind") == "mark":
            self.ran.append(a["name"])
            return "ok"
        return super()._run_step(a, ctx)


def played(steps):
    s = PlayStub()
    s._run_steps(steps, {"seen": threading.Event(), "held": (set(), set()), "bg": None, "speed": 1.0, "away": None})
    return s.ran


def If(val, *body):
    return {"kind": "if", "condition": {"val": val}, "actions": list(body)}


def Else(*body):
    return {"kind": "else", "actions": list(body)}


def mark(name):
    return {"kind": "mark", "name": name}


check("playback: If true -> its body only", played([If(True, mark("a")), Else(mark("b"))]) == ["a"])
check("playback: If false -> the Else only", played([If(False, mark("a")), Else(mark("b"))]) == ["b"])
got = played([If(True, If(False, mark("inner")), mark("after")), Else(mark("else"))])
check("playback: a false If inside a TRUE If's body: the Else after the outer If does not run", got == ["after"], got)
got = played([If(False, mark("a")), Else(If(True, mark("x")), mark("y")), Else(mark("z"))])
check("playback: a second Else after an Else never runs", got == ["x", "y"], got)
got = played([If(True, mark("a")), Else(mark("b")), If(False, mark("c")), Else(mark("d"))])
check("playback: two If / Else pairs in a row each follow their own If", got == ["a", "d"], got)

# ---------------------------------------------------------------- win streak: worked out from the session's runs
import stats  # noqa: E402

app.settings["stats_all"] = {"streak_now": 3, "best_streak": 4}
app.session = stats.Session("t", streak_before=3, best_streak_before=4)
for st in (stats.WIN, stats.UNKNOWN, stats.WIN):
    app.session.add(st, 10)
app._note_streak()
check("streak: wins carry on from the streak before the session (an Unknown run doesn't end it)",
      app.settings["stats_all"]["streak_now"] == 5 and app.settings["stats_all"]["best_streak"] == 5,
      app.settings["stats_all"])
app._note_streak()
check("streak: noting the same runs twice counts nothing twice", app.settings["stats_all"]["streak_now"] == 5,
      app.settings["stats_all"])
app.session.runs[1] = (stats.LOSS, 10)  # (the Unknown run's result showed late: it was lost)
app._note_streak()
check("streak: a late loss ends the streak where it happened (and the best is worked out again)",
      app.settings["stats_all"]["streak_now"] == 1 and app.settings["stats_all"]["best_streak"] == 4,
      app.settings["stats_all"])

app.session = stats.Session("t")
app.session.add(stats.WIN, 10)
app.session.add(stats.UNKNOWN, 10)
app.late_result = {"ended": time.perf_counter(), "index": 1, "run": None, "count": 2, "window": 30}
told = []
app._results_changed = lambda: told.append(1)
given = app._give_late_result(stats.WIN)
check("streak: a late result tells the window, so the streak and milestones are looked at again",
      given is True and told == [1], (given, told))
del app._results_changed

# ---------------------------------------------------------------- a screenshot that fails never means "the picture is gone"
import types  # noqa: E402


class _Mss:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _broken_grab(*a, **k):
    raise OSError("no screenshot")


real_image_watch = core.image_watch
core.image_watch = types.SimpleNamespace(mss=types.SimpleNamespace(mss=_Mss), screen_origin=lambda sct=None: (0, 0),
                                         grab_screen=_broken_grab)
try:
    looker = PlayStub()
    looker.win_rect = (0, 0, 0, 0)
    pic = types.SimpleNamespace(last_rect=None, need=0.8, picture_entry={})
    gone = looker._look_until(pic, 0.8, False, 0, 0.01, "test")
    shown = looker._look_until(pic, 0.8, True, 0, 0.01, "test")
finally:
    core.image_watch = real_image_watch
check("screenshot fails: 'wait until it's gone' does not say it's gone", gone is False, gone)
check("screenshot fails: 'wait until it shows' does not say it shows", shown is False, shown)

# ---------------------------------------------------------------- B: one call for "renamed" / "gone" (macro records)
import macro_versions  # noqa: E402

old_p = os.path.join(tmp, "rec_old.macro")
new_p = os.path.join(tmp, "rec_new.macro")
with open(old_p, "w", encoding="utf-8") as f:
    json.dump({"app": "macro_recorder", "version": 1, "events": []}, f)
app._remember_macro(old_p)
app.settings["macro_folders"] = []
app.set_macro_folder([old_p], "RecFolder")
app.set_macro_tags(old_p, "farm, x")
app.set_check_ignored("pid1", True, key=macro_versions._key(old_p))
macro_versions.keep(old_p)
app.watch_pictures.append({"file": "rec.png", "macros": [os.path.abspath(old_p)], "macro": os.path.abspath(old_p)})
app.trust_steps(app._macro_key(old_p), ["type"])
os.replace(old_p, new_p)
app.macro_renamed(old_p, new_p)
pic = app.watch_pictures[-1]
check("records: a renamed macro keeps its folder and tags", app.macro_meta(new_p)["folder"] == "RecFolder"
      and app.macro_meta(new_p)["tags"] == ["farm", "x"] and app._meta_key(old_p) not in app.settings["macro_meta"])
check("records: ... its turned-off warnings", "pid1" in app.check_ignored(macro_versions._key(new_p))
      and not app.check_ignored(macro_versions._key(old_p)))
check("records: ... its older versions", len(macro_versions.versions(new_p)) >= 1 and not macro_versions.versions(old_p))
check("records: ... the pictures that use or play it", pic["macros"] == [os.path.abspath(new_p)]
      and pic["macro"] == os.path.abspath(new_p), pic)
check("records: ... what you OK'd for it", app._macro_key(new_p) in app._trusted())
app.watch_pictures.remove(pic)
app.macro_gone(new_p)
check("records: when its file is gone, what's kept for that path goes too", app._meta_key(new_p) not in
      app.settings["macro_meta"] and app._macro_key(new_p) not in app._trusted())

# ---------------------------------------------------------------- A: the If / Else pairing and the group moves, no window
def tree():
    """[If [wait a], Else [wait b], wait c] and its ids."""
    a, b, c = (workflow.new_action("wait") for _ in range(3))
    i, e = workflow.new_action("if"), workflow.new_action("else")
    i["actions"], e["actions"] = [a], [b]
    return [i, e, c], {"if": i["id"], "else": e["id"], "a": a["id"], "b": b["id"], "c": c["id"]}


def shape(steps):
    return [(s["kind"], [x["kind"] for x in s.get("actions", [])]) for s in steps]


steps, ids = tree()
check("steps: pairs_with_else knows an If with its Else, and that Else",
      workflow.pairs_with_else(steps, 0) and workflow.pairs_with_else(steps, 1) and not workflow.pairs_with_else(steps, 2))
check("steps: else_has_if is the one shared rule", workflow.else_has_if(steps, 1) and not workflow.else_has_if(steps, 0))
steps[0]["off"] = True
check("steps: an Else after a turned-off If has no If", not workflow.else_has_if(steps, 1))
steps, ids = tree()
check("steps: can_move_out is on for the child of an If, off for an If with an Else and for the Else",
      workflow.can_move_out(steps, ids["a"]) and not workflow.can_move_out(steps, ids["if"])
      and not workflow.can_move_out(steps, ids["else"]))
check("steps: move_out puts the child after the Else", workflow.move_out(steps, ids["a"])
      and shape(steps) == [("if", []), ("else", ["wait"]), ("wait", []), ("wait", [])], shape(steps))
steps, ids = tree()
check("steps: can_ungroup is off for an If with an Else, on for the Else",
      not workflow.can_ungroup(steps, ids["if"]) and workflow.can_ungroup(steps, ids["else"]))
check("steps: ungroup of the If does nothing", not workflow.ungroup(steps, ids["if"])
      and shape(steps) == [("if", ["wait"]), ("else", ["wait"]), ("wait", [])])
steps, ids = tree()
check("steps: can_move_into_above is off for the Else, on for the step after the Else",
      not workflow.can_move_into_above(steps, ids["else"]) and workflow.can_move_into_above(steps, ids["c"]))
check("steps: move_into_above puts the step inside the group above", workflow.move_into_above(steps, ids["c"])
      and shape(steps) == [("if", ["wait"]), ("else", ["wait", "wait"])], shape(steps))
steps, ids = tree()
slot = workflow.else_slot(steps, ids["a"])
check("steps: a new Else goes after the If the chosen step is in", slot is not None and slot[0] is steps and slot[1] == 1)
check("steps: ... and after a chosen If, and nowhere special for another step", workflow.else_slot(steps, ids["if"])[1] == 1
      and workflow.else_slot(steps, ids["c"]) is None)

# ---------------------------------------------------------------- C: the app's own windows are not on the screen the macro looks at
import numpy as np  # noqa: E402

import own_windows  # noqa: E402
import ui_common  # noqa: E402

own_windows.set_rect("t", (10, 10, 20, 20))
pic_img = np.ones((40, 40, 3), np.uint8)
own_windows.blank(pic_img)
check("own windows: a registered rectangle is blacked out of a screenshot, the rest is left",
      int(pic_img[15, 15].sum()) == 0 and int(pic_img[30, 30].sum()) == 3)
shifted = np.ones((40, 40, 3), np.uint8)
own_windows.blank(shifted, 5, 5)  # (a part of the screen that starts at 5, 5)
check("own windows: ... also in a part of the screen", int(shifted[6, 6].sum()) == 0 and int(shifted[20, 20].sum()) == 3)
own_windows.set_rect("t", None)
check("own windows: a window that went away is forgotten", "t" not in own_windows.rects_by_name())

box = ui_common.PlayOverlay(root, root.winfo_screenwidth())
box.show("Playing", "0:01", "", ui_common.ACCENT)
pump(3)
timer = own_windows.rects_by_name().get("timer")
check("own windows: the timer at the top is registered where it is", timer is not None
      and timer[0] == box.win.winfo_rootx() and timer[1] == box.win.winfo_rooty()
      and timer[2] - timer[0] == box.win.winfo_width(), (timer, box.win.winfo_geometry()))
box.front_button(lambda: None)
pump(3)
check("own windows: the Bring it to front button is registered", "front" in own_windows.rects_by_name())
box.front_button(None)
check("own windows: ... and forgotten when it hides", "front" not in own_windows.rects_by_name())
box.hide()
check("own windows: ... and so is the timer", "timer" not in own_windows.rects_by_name())
box.win.destroy()

app.settings["first_start_done"] = True
app.start_tour()
pump(3)
names = own_windows.rects_by_name()
check("own windows: the tour box and its bars are registered", "tour" in names and any(n.startswith("tour_bar") for n in names),
      list(names))
app.end_tour(done=False)
check("own windows: ... and forgotten when the tour ends", not any(n.startswith("tour") for n in own_windows.rects_by_name()))

# ---------------------------------------------------------------- tours: minimize, follow, and the new ones
import tour_ui  # noqa: E402


def has_text(widget, text):
    try:
        if widget.cget("text") == text:
            return True
    except tk.TclError:
        pass
    return any(has_text(c, text) for c in widget.winfo_children())


def walk_tour(name, expect_steps):
    """Every step of a tour: it shows, and (when the part is on screen) the 4 bars frame it."""
    problems = []
    for n in range(expect_steps):
        app._tour_show()
        pump(2)
        if not app.tour_win.winfo_viewable() or not app.tour_title.cget("text"):
            problems.append(f"step {n + 1}: no box")
        if not all(b.winfo_viewable() for b in app.tour_marks):
            problems.append(f"step {n + 1}: no frame around {app.tour_title.cget('text')}")
        if n < expect_steps - 1:
            app._tour_go(1)
    return problems


app.settings["first_start_done"] = True
app.start_tour()
pump(3)
root.iconify()
pump(3)
app._tour_watch()
check("tour: hides while its window is minimized", not app.tour_win.winfo_viewable()
      and not any(n.startswith("tour") for n in own_windows.rects_by_name()))
root.deiconify()
pump(3)
app._tour_watch()
pump(3)
check("tour: comes back when the window is restored", app.tour_win.winfo_viewable())
root.geometry("+60+70")
pump(3)
app._tour_watch()
pump(3)
check("tour: follows its window when it moves", app.tour_at == app._tour_host_at(), (app.tour_at, app._tour_host_at()))
app.end_tour(done=False)

app.open_settings()
pump(10)
check("tour: Settings has a Take a tour link", has_text(app.settings_win, "Take a tour"))
app.start_tour("settings")
pump(3)
check("tour: Settings tour starts", app.tour_win is not None and len(app.tour_steps) == 9, app.tour_steps and len(app.tour_steps))
problems = walk_tour("settings", 9)
check("tour: every Settings step shows and frames its part", not problems, problems)
check("tour: a Settings step opens its page", app.tabs.tab(app.tabs.select(), "text") == "About")
app.close_settings()
pump(3)
app._tour_watch()
check("tour: the Settings tour ends when Settings is closed", app.tour_win is None)


def z_above(a, b):
    """True when window a is in front of window b (Windows only: walks the real window order)."""
    import ctypes
    u = ctypes.windll.user32
    u.GetAncestor.restype = ctypes.c_void_p
    u.GetTopWindow.restype = ctypes.c_void_p
    u.GetWindow.restype = ctypes.c_void_p
    ha, hb = (u.GetAncestor(ctypes.c_void_p(w.winfo_id()), 2) for w in (a, b))
    h, seen = u.GetTopWindow(None), 0
    while h and seen < 5000:
        if h == ha:
            return True
        if h == hb:
            return False
        h, seen = u.GetWindow(ctypes.c_void_p(h), 2), seen + 1
    return None


if sys.platform == "win32":
    # A user report: switching a Settings page by hand while the tour runs lost the tour box (Settings came over it)
    app.open_settings()
    pump(10)
    app.start_tour("settings")
    pump(3)
    app.tabs.select(app.tab_areas["Sounds"])
    pump(30)
    check("tour: the tour box stays in front when a Settings page is switched by hand",
          z_above(app.tour_win, app.settings_win), "tour box behind Settings")
    app.end_tour(done=False)
    app.close_settings()
    pump(3)

app.open_editor()
ed = app.macro_editor
ed.win.geometry("1220x720+40+40")
pump(10)
check("tour: Edit has a Tour link", has_text(ed.win, "Tour"))
app.start_tour("edit")
pump(3)
check("tour: Edit tour starts", app.tour_win is not None and len(app.tour_steps) == 7)
problems = walk_tour("edit", 7)
check("tour: every Edit step shows and frames its part", not problems, problems)
app.end_tour(done=False)
ed.win.destroy()
pump(3)
app.start_tour("edit")
check("tour: no Edit window, no Edit tour", app.tour_win is None)

pw = app.open_picture_watch()
pump(10)
check("tour: Picture watch has a Tour link", has_text(app.picture_win.win, "Tour"))
app.start_tour("picture")
pump(3)
check("tour: Picture watch tour starts", app.tour_win is not None and len(app.tour_steps) == 5)
problems = walk_tour("picture", 5)
check("tour: every Picture watch step shows and frames its part", not problems, problems)
app.end_tour(done=False)
app.picture_win.close()
pump(3)

events = [{"type": "key", "key": {"vk": 65}, "pressed": True, "t": 0.0},
          {"type": "key", "key": {"vk": 65}, "pressed": False, "t": 0.2}]
evwin = app._events_window(root, events, lambda e: None)
evwin.geometry("+80+80")
pump(10)
check("tour: the recorded events window has a Tour link", has_text(evwin, "Tour"))
app.start_tour("events")
pump(3)
check("tour: recorded events tour starts", app.tour_win is not None and len(app.tour_steps) == 6)
problems = walk_tour("events", 6)
check("tour: every recorded events step shows and frames its part", not problems, problems)
app.end_tour(done=False)
evwin.destroy()
pump(3)
app.settings.pop("tour_done", None)
app.start_tour("edit")
check("tour: other tours never mark the main tour as done", not app.settings.get("tour_done"))

# ---------------------------------------------------------------- Play: which path _check_program took is logged
import window_tools  # noqa: E402

logged = []
real_info, real_fg, real_pid, real_of = core.diag.info, window_tools.foreground, window_tools.pid_of, window_tools.windows_of
core.diag.info = lambda msg, *a, **k: logged.append(str(msg))
real_win = modern_ui.IS_WIN
modern_ui.IS_WIN = True
app.macro_program = {"exe": "RobloxPlayerBeta.exe"}
app.switch_prog_var.set(True)
app.target_var.set(modern_ui.SCREEN_TARGET)
try:
    window_tools.foreground = lambda: 111
    window_tools.pid_of = lambda h: os.getpid() + 1  # another program is in front (Play from a hotkey)
    ok = app._check_program()
    check("Play from another window: plays there", ok is True)
    check("Play from another window: the log says so", any("Switch to game" in m and "another window" in m for m in logged), logged)
    logged.clear()
    window_tools.pid_of = lambda h: os.getpid()  # this app is in front, the game is not open
    window_tools.windows_of = lambda exe: []
    app.boxes.askyesno = lambda *a, **k: False
    ok = app._check_program()
    check("Play with the game not open: asks, and the log says so", ok is False
          and any("Switch to game" in m and "not open" in m for m in logged), logged)
finally:
    core.diag.info, window_tools.foreground, window_tools.pid_of, window_tools.windows_of = real_info, real_fg, real_pid, real_of
    modern_ui.IS_WIN = real_win
    app.macro_program = None

# ---------------------------------------------------------------- Check my macro: a macro with no game window saved
real_ev, real_prog, real_sw, real_away = app.events, app.macro_program, app.switch_prog_var.get(), app.settings.get("pause_when_away")


def nogame():
    return [p for p in app.check_macro() if p["id"] == "nogame"]


app.events = [{"type": "key", "key": {"vk": 65}, "pressed": True, "t": 0.0},
              {"type": "key", "key": {"vk": 65}, "pressed": False, "t": 0.2}]
app.macro_program = None
app.switch_prog_var.set(True)
found = nogame()
check("Check my macro: a macro with no game window says so (and where to fix it)",
      len(found) == 1 and found[0]["level"] == "maybe" and "Game window" in found[0]["text"], found)
app.macro_program = {"exe": "RobloxPlayerBeta.exe"}
check("Check my macro: no note when the macro knows its game", not nogame())
app.macro_program = None
app.events = []
check("Check my macro: no note for a macro with no recorded actions", not nogame())
app.events = [{"type": "key", "key": {"vk": 65}, "pressed": True, "t": 0.0}]
app.switch_prog_var.set(False)
app.settings["pause_when_away"] = False
check("Check my macro: no note when switching and pausing are both off (a missing game costs nothing)", not nogame())
app.settings["pause_when_away"] = True
check("Check my macro: the note is back when only 'Pause when the macro's window isn't in front' is on", len(nogame()) == 1)
app.events, app.macro_program = real_ev, real_prog
app.switch_prog_var.set(real_sw)
app.settings["pause_when_away"] = real_away

# ---------------------------------------------------------------- "If the game closes": the saved game file moved
# (Roblox puts every update in a new Versions\version-... folder, so a saved path goes stale)
vers = os.path.join(tmp, "Roblox", "Versions")
for n, (folder, age) in enumerate((("version-old", 300), ("version-new", 100), ("version-nogame", 50))):
    os.makedirs(os.path.join(vers, folder), exist_ok=True)
    if folder != "version-nogame":
        gp = os.path.join(vers, folder, "Player.exe")
        open(gp, "w").close()
        os.utime(gp, (time.time() - age, time.time() - age))
gone = os.path.join(vers, "version-gone", "Player.exe")
newest = os.path.join(vers, "version-new", "Player.exe")
check("game file: an existing file stays as it is", window_tools.moved_game_file(newest) == newest)
check("game file: a link stays as it is", window_tools.moved_game_file("roblox://x") == "roblox://x")
check("game file: a missing file is found again in the newest sibling folder",
      window_tools.moved_game_file(gone) == newest, window_tools.moved_game_file(gone))
check("game file: nothing like it nearby gives None",
      window_tools.moved_game_file(os.path.join(tmp, "Nowhere", "v1", "Player.exe")) is None)
check("game file: a folder without the file is skipped",
      window_tools.moved_game_file(os.path.join(vers, "version-gone", "Other.exe")) is None)

# a missing file in an ordinary folder must never be swapped for another program that has the same file name
os.makedirs(os.path.join(tmp, "Games"), exist_ok=True)
os.makedirs(os.path.join(tmp, "OtherApp"), exist_ok=True)
open(os.path.join(tmp, "OtherApp", "Game.exe"), "w").close()
check("game file: a gone file in a folder that isn't a Versions folder is never swapped for another program",
      window_tools.moved_game_file(os.path.join(tmp, "Games", "Game.exe")) is None,
      window_tools.moved_game_file(os.path.join(tmp, "Games", "Game.exe")))
# links and program names are not files: no "it's gone" note for them
for link in ("roblox-player:1+launchmode:play", "notepad.exe", "roblox://x"):
    check(f"game open: '{link}' is a link or a program name, not a gone file",
          app._game_open_target({"open": link, "follow": True}) == (link, ""), app._game_open_target({"open": link, "follow": True}))

app.settings["game_closed"] = {"action": "reopen", "open": gone, "macro": "", "tries": 1, "settle": 0}
check("game closed: 'use the newest' is on unless turned off", app._closed_settings()["follow"] is True)
target, note = app._game_open_target(app._closed_settings())
check("game closed: the gone file is replaced by the newest one", target == newest and "version-new" in note, (target, note))
app.settings["game_closed"]["follow"] = False
target, note = app._game_open_target(app._closed_settings())
check("game closed: with the switch off the saved file is kept, and the note says it's gone",
      target == gone and "isn't there" in note, (target, note))
app.settings["game_closed"]["follow"] = True
app.settings["game_closed"]["open"] = newest
check("game closed: a file that is there gives no note", app._game_open_target(app._closed_settings()) == (newest, ""))
check("Check my macro: no note while the saved file is there",
      not any(p["id"] == "closedopen" for p in app.check_macro()))
app.settings["game_closed"]["open"] = gone
notes = [p for p in app.check_macro() if p["id"] == "closedopen"]
check("Check my macro: tells when the saved game file is gone", len(notes) == 1 and "version-new" in notes[0]["text"], notes)

# the whole recovery opens the NEW file (stand-ins for the game and the countdown)
opened = []
open_now = {"v": False}
real_fns = (window_tools.windows_of, window_tools.force_to_front, window_tools.IS_WIN, app._open_target,
            app._recovery_countdown, app._recovery_event)
window_tools.windows_of = lambda exe: [111] if open_now["v"] else []
window_tools.force_to_front = lambda h: True
window_tools.IS_WIN = True
app._recovery_countdown = lambda kind: True
app._recovery_event = lambda *a, **k: None
app._open_target = lambda t: (opened.append(t), open_now.update(v=True))
try:
    app.stop_play.clear()
    res = app._game_closed(app._closed_settings(), "Player.exe", [])
    check("game closed: the new game file is opened, not the gone one", opened == [newest] and res == "gameback", (opened, res))
finally:
    (window_tools.windows_of, window_tools.force_to_front, window_tools.IS_WIN, app._open_target,
     app._recovery_countdown, app._recovery_event) = real_fns
app.settings.pop("game_closed", None)

# the "If the game closes" window: the switch, the orange note, and saving the switch
import profiles_ui  # noqa: E402

check("profiles: the tours already shown never switch with a profile", "tours_seen" in profiles_ui.SKIP_KEYS)
app.settings["game_closed"] = {"action": "reopen", "open": gone, "macro": "", "tries": 1, "settle": 0}
cw = app.open_game_closed()
pump(5)
check("game closed window: a gone game file shows an orange note", "version-new" in cw.vars["missing"].cget("text"),
      cw.vars["missing"].cget("text"))
cw.vars["follow"].set(False)
check("game closed window: the note changes with the switch", "no newer one" in cw.vars["missing"].cget("text"))
cw.save()
pump(3)
check("game closed window: the switch is saved", app.settings["game_closed"].get("follow") is False
      and app._closed_settings()["follow"] is False, app.settings.get("game_closed"))
app.settings["game_closed"] = {"action": "reopen", "open": newest, "macro": "", "tries": 1, "settle": 0, "open_wait": 300}
cw = app.open_game_closed()
pump(3)
cw.save()
pump(3)
check("game closed window: Save keeps a hand-set 'open_wait'", app.settings["game_closed"].get("open_wait") == 300,
      app.settings.get("game_closed"))
app.settings.pop("game_closed", None)

# ---------------------------------------------------------------- every tour starts by itself the first time
app.tours_auto = True
app.settings["tour_done"] = True  # (an old user: the main tour is long done)
app.settings.pop("tours_seen", None)
app.open_settings()
pump(10)
app.tour_first_scan()
check("tours: not on the very first sighting (the window gets a moment to appear)", app.tour_win is None)
app.tour_first_scan()
check("tours: Settings' tour starts by itself the first time, for an old user too",
      app.tour_win is not None and app.tour_name == "settings", getattr(app, "tour_name", None))
check("tours: it is remembered", app.settings.get("tours_seen") == ["settings"], app.settings.get("tours_seen"))
app.end_tour(done=False)
app.close_settings()
pump(3)
app.open_settings()
pump(10)
app.tour_first_scan()
app.tour_first_scan()
check("tours: the second time Settings opens, no tour", app.tour_win is None)
app.close_settings()
pump(3)
app.settings.pop("tours_seen", None)
app.playing = True
app.open_settings()
pump(10)
app.tour_first_scan()
app.tour_first_scan()
check("tours: never while a macro plays, and not remembered either",
      app.tour_win is None and not app.settings.get("tours_seen"), app.settings.get("tours_seen"))
app.playing = False
app.close_settings()
pump(3)
app.tours_auto = False
app.tour_first_scan()
check("tours: switched off outside the real app (tests stay quiet)", app.tour_win is None)
ticks = []
real_after = app.root.after
app.root.after = lambda ms, fn=None, *a: ticks.append(ms) or "id"
try:
    app.settings["tours_seen"] = [n for n in tour_ui.TOURS if n != "main"]
    app.tour_first_tick()
    check("tours: once every tour was shown the scanner stops (no timer left running)", ticks == [], ticks)
    app.settings["tours_seen"] = []
    app.tour_first_tick()
    check("tours: while one is still to show the scanner keeps looking", len(ticks) == 1, ticks)
finally:
    app.root.after = real_after
    app.tours_auto = False
    app.settings.pop("tours_seen", None)

# ---------------------------------------------------------------- Discord screenshots say when the game window wasn't found
import discord_notify  # noqa: E402

logged = []
real_info, real_how, real_hide = core.diag.info, discord_notify.grab_how, window_tools.hide_own_windows_from_capture
core.diag.info = lambda msg, *a, **k: logged.append(str(msg))
window_tools.hide_own_windows_from_capture = lambda *a, **k: False
try:
    discord_notify.grab_how = lambda target, exe: ("PIC", "game window not found, main screen taken", True)
    pic, how, fell = app._screenshot_with_note()
    check("screenshot: the app gives the picture, how it was taken, and that it fell back",
          (pic, fell) == ("PIC", True) and "not found" in how, (pic, how, fell))
    check("screenshot: a fallback is logged (so a report shows it)", any("Screenshot:" in m and "not found" in m for m in logged), logged)
    check("screenshot: _screenshot() still gives only the picture", app._screenshot() == "PIC")
    logged.clear()
    discord_notify.grab_how = lambda target, exe: ("PIC2", "game window (RobloxPlayerBeta.exe, 2560x1369)", False)
    pic, how, fell = app._screenshot_with_note()
    check("screenshot: a normal one is not logged here (the remote logs its own)", not fell and not any("Screenshot:" in m for m in logged), logged)
finally:
    core.diag.info, discord_notify.grab_how, window_tools.hide_own_windows_from_capture = real_info, real_how, real_hide

# ---------------------------------------------------------------- small things
import tour_ui  # noqa: E402

before = len(root.bind("<Escape>").split("\n")) if root.bind("<Escape>") else 0
app.start_tour()
app.end_tour(done=False)
app.start_tour()
app.end_tour(done=False)
after = len(root.bind("<Escape>").split("\n")) if root.bind("<Escape>") else 0
check("tour: Replay doesn't pile up Escape bindings", after - before <= 0, (before, after))
check("milestones: check_milestones returns the list of what was reached", app.check_milestones() == [])

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
