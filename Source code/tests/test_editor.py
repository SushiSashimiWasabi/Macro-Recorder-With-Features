"""The Edit window: open macros, add / move / group / copy / turn off steps, Undo / Redo / Reset /
Apply (and renaming the file). Opens the window (off to the side) but sends no input to other
programs. With a folder as 2nd argument, it also saves screenshots there."""
import json
import os
import sys
import tempfile
import time

src = sys.argv[1]
shots = sys.argv[2] if len(sys.argv) > 2 else None
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_editor_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import tkinter as tk  # noqa: E402

import modern_ui  # noqa: E402
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
app.boxes.askyesno = lambda *a, **k: True
app.boxes.askyesnocancel = lambda *a, **k: False
app.rec_ready_var.set(0)  # (recording starts at once; the countdown is tested at the end)
app._save_settings()


def pump(n=5):
    for _ in range(n):
        root.update()
        time.sleep(0.02)


# two saved macros
def write(name, events, actions=None):
    path = os.path.join(tmp, name + ".macro")
    data = {"app": "macro_recorder", "version": 1, "events": events}
    if actions:
        data["actions"] = actions
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    app._remember_macro(path)
    return path


evs = [{"type": "key", "key": {"vk": 65}, "pressed": True, "t": 0.0},
       {"type": "key", "key": {"vk": 65}, "pressed": False, "t": 0.2}]
p1 = write("first", evs)
p2 = write("second", evs * 1)
app.load(p1, quiet=True)
pump()
app.open_editor()
ed = app.macro_editor
ed.win.geometry("1220x720+40+40")
pump(10)
check("opens the open macro", ed.entries[ed.current][1] == p1 and len(ed.steps) == 1)
check("nothing changed: Apply, Reset, Undo, Redo off",
      all(str(b.cget("state")) == "disabled" for b in (ed.btn_apply, ed.btn_reset, ed.btn_undo, ed.btn_redo)))
check("no Duplicate / Remove / More before something is chosen", not ed.btn_dup.winfo_ismapped())
name_hint = ed.name_entry.winfo_children()[0]
check("name hint: not shown while the macro has a name", not name_hint.winfo_ismapped())
before_name = ed.name_var.get()
ed.name_var.set("")
pump()
check("name hint: shown in the empty name box", name_hint.winfo_ismapped()
      and name_hint.cget("text") == "Type a name for this macro" and ed.name_var.get() == "")
ed.name_var.set("x")
pump()
check("name hint: gone with the first letter typed", not name_hint.winfo_ismapped())
ed.name_var.set(before_name)
pump()

ed.tree.selection_set(ed.steps[0]["id"])
pump()
check("choosing a step shows Duplicate / Remove / More", ed.btn_dup.winfo_ismapped() and ed.btn_more.winfo_ismapped())
ed.add("wait")
ed.add("key")
pump()
check("Add action: added after the chosen step", [a["kind"] for a in ed.steps] == ["recorded", "wait", "key"])
check("a change lights up Apply, Reset, Undo", all(str(b.cget("state")) == "normal"
                                                    for b in (ed.btn_apply, ed.btn_reset, ed.btn_undo)))
ed.move(-1)
check("Move up", [a["kind"] for a in ed.steps] == ["recorded", "key", "wait"])
ed.group_into("repeat")
check("Group into a Repeat", ed.steps[1]["kind"] == "repeat" and ed.steps[1]["actions"][0]["kind"] == "key")
ed.tree.selection_set(ed.steps[2]["id"])  # the wait
pump()
ed.into_group_above()
check("Move into the group above", [a["kind"] for a in ed.steps[1]["actions"]] == ["key", "wait"])
ed.out_of_group()
check("Move out of its group", [a["kind"] for a in ed.steps] == ["recorded", "repeat", "wait"])
ed.copy()
ed.paste()
check("Copy / Paste", [a["kind"] for a in ed.steps] == ["recorded", "repeat", "wait", "wait"]
      and ed.steps[2]["id"] != ed.steps[3]["id"])
ed.toggle_off()
check("Turn this action off", ed.steps[3].get("off") is True)
ed.undo()
check("Undo", not ed.steps[3].get("off"))
ed.redo()
check("Redo", ed.steps[3].get("off") is True)
ed.duplicate()
check("Duplicate", len(ed.steps) == 5)
ed.remove()
check("Remove", len(ed.steps) == 4)
ed.tree.selection_set(ed.steps[1]["id"])
pump()
ed.ungroup()
check("Ungroup", [a["kind"] for a in ed.steps] == ["recorded", "key", "wait", "wait"])
if shots:
    ed.tree.selection_set(ed.steps[1]["id"])
    pump(10)
    import mss
    import mss.tools

    def grab(w, name):
        w.update()
        with mss.mss() as sct:
            img = sct.grab({"left": w.winfo_rootx() - 8, "top": w.winfo_rooty() - 32,
                            "width": w.winfo_width() + 16, "height": w.winfo_height() + 40})
            mss.tools.to_png(img.rgb, img.size, output=os.path.join(shots, name))
    grab(ed.win, "40_editor_key.png")
    ed.tree.selection_set(ed.steps[0]["id"])
    pump(10)
    grab(ed.win, "41_editor_recorded.png")

# Record keys and mouse straight into the macro (at the start)
before_events = list(app.events)
app.boxes.askchoice = lambda *a, **k: "start"
n_before = len(ed.steps)
ed.record_here()
pump()
check("record here: recording started, Edit window hidden", app.recording and not ed.win.winfo_viewable())
app._add({"type": "key", "key": {"vk": 90}, "pressed": True})
app._add({"type": "key", "key": {"vk": 90}, "pressed": False})
app.toggle_record()
pump(10)
check("record here: the recording is the first step", len(ed.steps) == n_before + 1 and
      ed.steps[0]["kind"] == "recorded" and
      [e["key"]["vk"] for e in ed.steps[0]["events"] if e["type"] == "key"] == [90, 90])
check("record here: the open macro is unchanged", app.events == before_events and not app.recording)
check("record here: the Edit window is back", ed.win.winfo_viewable())
ed.undo()
check("record here: Undo takes it out again", len(ed.steps) == n_before)

# Insert another macro (a copy of its actions) at the end
import macro_editor  # noqa: E402
other_steps, _d = macro_editor.read_macro(p2)
n_before = len(ed.steps)
ed._insert_steps(other_steps, "end")
check("insert another macro: its actions copied in", len(ed.steps) == n_before + len(other_steps)
      and ed.steps[-1]["kind"] == "recorded" and ed.steps[-1]["id"] != other_steps[0]["id"])
check("insert another macro: the other macro's file unchanged", json.load(open(p2, encoding="utf-8"))["events"] == evs)
ed.undo()
check("insert another macro: Undo takes it out", len(ed.steps) == n_before)

# The Recorded events window: add a key press and a click by hand, and record more, in the list
K = {"vk": 65}
rec_evs = [{"type": "key", "key": K, "pressed": True, "t": 0.0}, {"type": "key", "key": K, "pressed": False, "t": 0.1},
           {"type": "key", "key": {"vk": 66}, "pressed": True, "t": 2.0},
           {"type": "key", "key": {"vk": 66}, "pressed": False, "t": 2.1}]
got = {}
ev_win = app._events_window(ed.win, [dict(e) for e in rec_evs], lambda evs: got.setdefault("evs", evs))
pump()
ev_win.tree.selection_set("1")  # after A up
orig_dialog = app._manual_event_dialog


def fake_dialog(action_kw, where):
    def dialog(events_win, editor_win, kind, choices, on_done):
        check(f"add {kind}: where choices offered", [c[1] for c in choices][:2] == ["after", "before"], choices)
        a = workflow.new_action(kind)
        a.update(action_kw)
        on_done(a, where)
    return dialog


app._manual_event_dialog = fake_dialog({"key": {"vk": 67}, "hold": 0.5}, "after")
ev_win.add_action("key")
pump()
rows = [ev_win.tree.item(i, "values") for i in ev_win.tree.get_children()]
check("add key: 2 new rows after the selected one", len(rows) == 6 and "C" in rows[2][2] and "C" in rows[3][2], rows)
check("add key: the new rows are selected", ev_win.tree.selection() == ("2", "3"), ev_win.tree.selection())
app._manual_event_dialog = fake_dialog({"x": 10, "y": 20, "button": "right"}, "end")
ev_win.add_action("click")
pump()
app._manual_event_dialog = orig_dialog
ev_win.tree.selection_set("0")
app.boxes.askchoice = lambda *a, **k: "before"
ev_win.record_here()
pump()
check("record here (events): recording, windows hidden", app.recording and not ev_win.winfo_viewable()
      and not ed.win.winfo_viewable())
app._add({"type": "key", "key": {"vk": 90}, "pressed": True})
app._add({"type": "key", "key": {"vk": 90}, "pressed": False})
app.toggle_record()
pump(10)
check("record here (events): windows back", ev_win.winfo_viewable() and ed.win.winfo_viewable())
ev_win.apply()
pump()
evs = got.get("evs") or []
order = [(e.get("key") or {}).get("vk") or e["type"] for e in evs if e["type"] in ("key", "click", "move")]
check("events: recorded Z first, then A, the held C, B, the right click",
      order == [90, 90, 65, 65, 67, 67, 66, 66, "move", "click", "click"], order)
times = [e["t"] for e in evs]
check("events: times only go up", times == sorted(times), times)
c_down, c_up = evs[4]["t"], evs[5]["t"]
check("events: C held about 0.5 s", 0.45 <= c_up - c_down <= 0.55, round(c_up - c_down, 2))
check("events: B moved later to make room", evs[6]["t"] - evs[5]["t"] > 1.0, round(evs[6]["t"] - evs[5]["t"], 2))
check("events: click is right, at 10, 20", evs[-1]["button"] == "right" and evs[-1]["x"] == 10 and
      not any("pause" in e for e in evs))

# Reset, then a change + Apply with a new name
ed.reset()
check("Reset", len(ed.steps) == 1)
ed.tree.selection_set(ed.steps[0]["id"])
ed.add("wait")
ed.name_var.set("renamed")
pump()
check("Apply works", ed.apply())
new_path = os.path.join(tmp, "renamed.macro")
check("Apply: renamed the file", os.path.exists(new_path) and not os.path.exists(p1))
data = json.load(open(new_path, encoding="utf-8"))
check("Apply: steps saved in the file", [a["kind"] for a in data["actions"]] == ["recorded", "wait"])
check("Apply: the open macro has the steps", app.actions and len(app.actions) == 2 and
      app.current_file == new_path)
check("after Apply: buttons off again", str(ed.btn_apply.cget("state")) == "disabled")

# open the other macro from the list
i2 = next(i for i, (_l, p) in enumerate(ed.entries) if p == p2)
ed._open_entry(i2)
check("another macro opens on the right", ed.entries[ed.current][1] == p2 and ed.name_var.get() == "second")

ed.close()
pump()
check("closes", not ed.win.winfo_exists())

# the Saved macros row: a deleted file is forgotten, arrows only with more than one macro
def row():
    app.macros_checked = -10.0
    app._refresh()
    return app.mac_label.cget("text"), app.mac_prev.cget("text"), app.mac_next.cget("text")


gone = os.path.join(tmp, "deleted.macro")
app.settings["macro_library"] = [gone]  # (its file doesn't exist)
app.events, app.actions, app.current_file = [], None, None
text, prev, nxt = row()
check("saved macros: a deleted file isn't counted", app.macro_list() == [] and prev == "" and nxt == ""
      and "show up here" in text, (text, prev, nxt))
app.settings["macro_library"] = [gone]
app.load(p2, quiet=True)
text, prev, nxt = row()
check("saved macros: the first opened macro is 1 of 1, no arrows", text.startswith("1 of 1") and prev == ""
      and nxt == "", (text, prev, nxt))
app.load(new_path, quiet=True)
text, prev, nxt = row()
check("saved macros: with two, arrows show", text.startswith("2 of 2") and prev == "◀" and nxt == "▶",
      (text, prev, nxt))
app.settings["macro_library"] = [p2]
app.events, app.actions, app.current_file = [], None, None
text, prev, nxt = row()
check("saved macros: one saved, none open: click its name, no arrows", text.startswith("Click to open")
      and prev == "" and nxt == "", (text, prev, nxt))
app._mac_label_clicked()
check("saved macros: clicking the name opens it", app.current_file == p2 and row()[0].startswith("1 of 1"))

# the countdown before recording, with the timer at the top of the screen
app.rec_ready_var.set(1)
app._save_settings()
app.overlay_var.set(True)
app.events = [{"type": "key", "key": {"vk": 65}, "pressed": True, "t": 0.0}]
app.toggle_record()
pump()
check("countdown: not recording yet", not app.recording and app.record_countdown_left == 1)
check("countdown: shown at the top of the screen", app.overlay is not None and
      app.overlay.state.cget("text") == "Recording in" and app.overlay.win.state() != "withdrawn")
app.toggle_record()  # Record again: cancelled
pump()
check("countdown: Record again cancels it", not app.recording and app.record_countdown_left == 0
      and len(app.events) == 1)
app.toggle_record()
end = time.time() + 1.6
while time.time() < end and not app.recording:
    pump(1)
check("countdown: recording starts after it", app.recording and app.events == [])
pump(15)
check("recording: the timer says Recording", app.overlay.state.cget("text") == "Recording"
      and app.overlay.key_labels["stop"][1].cget("text") == "Stop rec.", app.overlay.state.cget("text"))
app._add({"type": "key", "key": {"vk": 66}, "pressed": True})
app.toggle_record()
pump()
check("recording stopped: the timer says Recorded", not app.recording and app.overlay.state.cget("text") == "Recorded")
print()
print(f"{sum(ok for _, ok in results)} of {len(results)} passed")
root.destroy()
