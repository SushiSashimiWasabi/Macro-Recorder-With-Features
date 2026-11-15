"""Trimming, profiles, the emergency stop, the phone remote's new commands and the Edit window's
autosave. No real input is sent, throwaway settings folder."""
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
import tkinter as tk  # noqa: E402
from pynput import keyboard  # noqa: E402

import macro_editor  # noqa: E402
import macro_steps as workflow  # noqa: E402
import modern_ui  # noqa: E402
import trim  # noqa: E402
import window_tools  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


def key(vk, t, pressed=True):
    return {"type": "key", "key": {"vk": vk}, "pressed": pressed, "t": t}


# ---- trimming (pure)
move = {"type": "move", "x": 1, "y": 1, "t": 0.5}
events = [move, key(65, 2.0), key(65, 2.1, False), key(87, 3.0), key(87, 13.0, False), key(66, 20.0),
          key(66, 20.1, False), {"type": "move", "x": 5, "y": 5, "t": 22.0}]
found = trim.suggestions(events)
check("trim: finds the start, one pause and the end", [c["kind"] for c in found] == ["start", "gap", "end"], found)
check("trim: holding a key for 10 s isn't a pause", all(c["at"] != 3.0 for c in found))
check("trim: the pause is the 7 s after the key was let go", abs(found[1]["seconds"] - 6.5) < 0.01, found[1])
out = trim.apply(events, found)
check("trim: all three cut", [(e["type"], e["t"]) for e in out] == [
    ("key", 0.0), ("key", 0.1), ("key", 1.0), ("key", 11.0), ("key", 11.5), ("key", 11.6)], out)
check("trim: the recording itself isn't changed", events[1]["t"] == 2.0 and len(events) == 8)
only_gap = trim.apply(events, [found[1]])
check("trim: one suggestion alone", len(only_gap) == 8 and abs(only_gap[5]["t"] - 13.5) < 0.01, only_gap)
check("trim: seconds saved", abs(trim.saved_seconds(found) - (2.0 + 6.5 + 1.9)) < 0.01, trim.saved_seconds(found))
check("trim: nothing to cut in a tight recording", trim.suggestions([key(65, 0.0), key(65, 0.2, False)]) == [])
check("trim: a higher limit suggests fewer pauses", len(trim.suggestions(events, min_gap=8)) == 2)

# ---- the app
root = tk.Tk()
root.withdraw()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
root.withdraw()
sent = []
app._replay_event = lambda e, hk, hb: sent.append(e)
app.root.after = (lambda real: (lambda ms, fn=None, *a: real(ms, fn, *a) if fn else real(ms)))(app.root.after)
modern_ui.messagebox.showwarning = lambda *a, **k: None
window_tools.foreground = lambda: None
app.settings.update(pause_when_away=False, watch_enabled=False)
app.away_var.set(False)
app.watch_var.set(False)
app.result_pictures = []
app._save_settings()


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


# ---- profiles
app.speed_var.set("1x")
app.ready_var.set(3)
app._save_settings()
check("profiles: none at first", app.profile_active() is None and app.profile_summary() == "None yet")
check("profiles: a new one from the settings now", app.save_profile("  Farming  ") == "Farming"
      and app.profile_active() == "Farming")
app.speed_var.set("2x")
app.ready_var.set(7)
app.settings["auto_stop"] = {"on": True, "runs": 50}
app._save_settings()
app.save_profile("Testing")
check("profiles: the second one holds the changed settings",
      app.profiles()["Testing"]["speed"] == 2.0 and app.profiles()["Farming"]["speed"] == 1.0,
      (app.profiles()["Testing"].get("speed"), app.profiles()["Farming"].get("speed")))
check("profiles: nothing that belongs to the PC is inside",
      not any(k.startswith("remote_") or k in ("profiles", "macro_library", "stats_all")
              for k in app.profiles()["Testing"]))
check("profiles: switch back", app.switch_profile("Farming") and app.profile_active() == "Farming")
check("profiles: the controls show the other profile's settings",
      app.speed_var.get() == "1x" and app.ready_var.get() == 3 and "auto_stop" not in app.settings,
      (app.speed_var.get(), app.ready_var.get(), app.settings.get("auto_stop")))
app.ready_var.set(5)  # a change while Farming is in use belongs to Farming
app._save_settings()
app.switch_profile("Testing")
check("profiles: and forth again", app.speed_var.get() == "2x" and app.ready_var.get() == 7
      and app._auto_stop_settings()["runs"] == 50, (app.speed_var.get(), app.ready_var.get()))
check("profiles: the profile in use kept the change made meanwhile",
      app.profiles()["Farming"]["ready_seconds"] == 5, app.profiles()["Farming"].get("ready_seconds"))
check("profiles: rename", app.rename_profile("Testing", "Quick test") and app.profile_active() == "Quick test"
      and "Testing" not in app.profiles())
check("profiles: a name in use is refused", not app.rename_profile("Quick test", "Farming"))

# backgrounds belong to a profile (2.9): which picture each window shows, darkness and so on
import shutil  # noqa: E402
import backdrop  # noqa: E402
import extras_ui  # noqa: E402
import profiles_ui  # noqa: E402
data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
pngs = sorted(f for f in os.listdir(data) if f.lower().endswith(".png"))[:2]
for i, f in enumerate(pngs, 1):
    shutil.copy(os.path.join(data, f), os.path.join(tmp, f"bg{i}.png"))
app.settings["background_library"] = [{"file": "bg1.png", "name": "one"}, {"file": "bg2.png", "name": "two"}]
app.settings["background_picture"] = "bg1.png"
app.bg_main.dark_var.set(30)
app._save_settings()
app.switch_profile("Farming")
app.settings["background_picture"] = "bg2.png"
app.bg_main.dark_var.set(60)
app._save_settings()
app.switch_profile("Quick test")
check("backgrounds: switching a profile brings its own picture and darkness",
      app.bg_main.picture() == "bg1.png" and int(app.bg_main.dark_var.get()) == 30,
      (app.bg_main.picture(), app.bg_main.dark_var.get()))
if backdrop.AVAILABLE:
    check("backgrounds: the window shows it at once", app.backdrop.source_key is not None
          and app.backdrop.source_key[0].endswith("bg1.png"), app.backdrop.source_key)
app.switch_profile("Farming")
check("backgrounds: and back", app.bg_main.picture() == "bg2.png" and int(app.bg_main.dark_var.get()) == 60,
      (app.bg_main.picture(), app.bg_main.dark_var.get()))
check("backgrounds: the saved pictures stay one shared list",
      len(app.bg_library()) == 2 and not any("background_library" in p for p in app.profiles().values()))
check("backgrounds: how animated pictures play isn't part of a profile",
      not profiles_ui.in_profile("background_fps") and profiles_ui.in_profile("settings_background_general_picture"))
check("backgrounds: a shared profile never carries them",
      not any(profiles_ui.is_background_key(k) for k in extras_ui.shareable(app.profiles()["Quick test"])))
check("backgrounds: another profile using a picture is found",
      app.profiles_using_background("bg1.png") == ["Quick test"], app.profiles_using_background("bg1.png"))
app.profiles()["Old"] = {"speed": 1.0}
app._profiles_take_background()
check("backgrounds: a profile from before 2.9 takes the one showing now",
      app.profiles()["Old"].get("background_picture") == "bg2.png", app.profiles()["Old"])
app.forget_background_everywhere("bg2.png")
check("backgrounds: a removed picture is gone from every profile",
      app.profiles()["Old"]["background_picture"] == "" and app.profiles()["Quick test"]["background_picture"] == "bg1.png")
# the note about playlists under Video: a switch on its row hides it (the row stays)
check("playlist note: shown at first", app.playlist_note.cget("text") == app.PLAYLIST_NOTE)
app.playlist_note_var.set(False)
app._playlist_note_switched()
check("playlist note: switched off, hidden and remembered (not per profile)",
      app.playlist_note.cget("text") == "" and app.settings.get("video_playlist_note") is False
      and not profiles_ui.in_profile("video_playlist_note") and app.playlist_note.winfo_manager() == "pack")
app.playlist_note_var.set(True)
app._playlist_note_switched()
if backdrop.AVAILABLE:
    # a label whose text changes gets its piece of picture at once; its own colour is the piece's
    # colour, so whatever Tk shows of it for a moment is never a dark box
    root.deiconify()
    pump(0.3)
    app.backdrop.refresh()
    lab = app.playlist_note
    app.playlist_note_var.set(False)
    app._playlist_note_switched()
    app.playlist_note_var.set(True)
    app._playlist_note_switched()
    it = app.backdrop.items.get(lab)
    check("background: a changed label keeps a piece and the piece's colour",
          it is not None and it["text"] == app.PLAYLIST_NOTE and str(lab.cget("bg")).lower() != modern_ui.PANEL.lower(),
          (it and it["text"], lab.cget("bg")))
del app.profiles()["Old"]
app.settings["background_picture"] = ""
app.bg_main.dark_var.set(40)
app._save_settings()
app.switch_profile("Quick test")

# a macro linked to a profile switches to it when opened
path = os.path.join(tmp, "linked.macro")
with open(path, "w", encoding="utf-8") as f:
    json.dump({"app": "macro_recorder", "version": 1, "events": [key(65, 0.0), key(65, 0.1, False)],
               "profile": "Farming", "vary": {"mode": "own", "ms": 9, "px": 1}}, f)
app.load(path, quiet=True)
check("profiles: opening a linked macro switches to its profile", app.profile_active() == "Farming"
      and app.speed_var.get() == "1x", (app.profile_active(), app.speed_var.get()))
check("macro file: its own random timing is read", app._vary_now() == {"ms": 9, "px": 1}, app._vary_now())
save_to = os.path.join(tmp, "resaved.macro")
modern_ui.filedialog.asksaveasfilename = lambda **k: save_to
app.save()
with open(save_to, encoding="utf-8") as f:
    data = json.load(f)
check("macro file: saving keeps the profile link and the random timing",
      data.get("profile") == "Farming" and data.get("vary") == {"mode": "own", "ms": 9, "px": 1},
      {k: data.get(k) for k in ("profile", "vary")})

# the phone remote's new commands
check("remote: /profile lists them", "Farming" in app.remote_profile(None) and "Quick test" in app.remote_profile(None),
      app.remote_profile(None))
check("remote: /profile switches (part of a name is enough)", "Quick test" in app.remote_profile("quick")
      and app.profile_active() == "Quick test", app.profile_active())
check("remote: /profile with an unknown name says so", "no profile" in app.remote_profile("nope"))
check("remote: /stats answers", "Today" in app._remote_act("stats", None, "me"), app._remote_act("stats", None, "me"))
check("remote: /keepgoing with nothing planned says so", "Nothing to cancel" in app._remote_act("keepgoing", None, "me"))
import remote_ui  # noqa: E402

names = [c["name"] for c in remote_ui.COMMANDS]
check("remote: the new commands are registered", {"stats", "keepgoing", "profile"} <= set(names), names)
app.delete_profile("Quick test")
check("profiles: delete", "Quick test" not in app.profiles() and app.profile_active() is None)

# a chain part with its own profile plays at that profile's speed
app.switch_profile("Farming")
app.profiles()["Fast"] = dict(app.profiles()["Farming"], speed=4.0)
part_path = os.path.join(tmp, "part.macro")
with open(part_path, "w", encoding="utf-8") as f:
    json.dump({"app": "macro_recorder", "version": 1, "events": [key(66, 0.0), key(66, 2.0, False)]}, f)
step = workflow.new_action("play_macro")
step.update(file=part_path, times=1, profile="Fast")
app.current_file = None
app.set_steps([step])
app.result_pictures = []  # (switching profiles loaded them again: nothing may look at the real screen)
app.ready_var.set(0)
app.loop_var.set(False)
app.repeat_var.set(1)
t0 = time.time()
app.play()
while app.playing and time.time() - t0 < 10:
    pump(0.03)
took = time.time() - t0
check("chain: a part with a profile uses that profile's speed (2 s at 4x)", 0.4 < took < 1.5, f"{took:.2f}")

# ---- the emergency stop: Ctrl+Alt+End
app.actions = None
app.events = [key(65, 0.0), key(65, 30.0, False)]
app.loop_var.set(True)
app.play()
pump(0.3)
check("emergency stop: a macro is playing", app.playing)
app._on_key_press(keyboard.Key.ctrl_l)
app._on_key_press(keyboard.Key.end)
pump(0.2)
check("emergency stop: End with only Ctrl does nothing", app.playing)
app._on_key_press(keyboard.Key.alt_l)
app._on_key_press(keyboard.Key.end)
t0 = time.time()
while app.playing and time.time() - t0 < 3:
    pump(0.03)
check("emergency stop: Ctrl+Alt+End stops playback", not app.playing)
app._on_key_release(keyboard.Key.alt_l)
app._on_key_release(keyboard.Key.ctrl_l)
app.loop_var.set(False)
app.capture_callback = lambda key_id: None  # (as if a "press a key" box was waiting)
app.play_was = app.playing
app._on_key_press(keyboard.Key.ctrl_r)
app._on_key_press(keyboard.Key.alt_gr)
app._on_key_press(keyboard.Key.end)
pump(0.1)
check("emergency stop: works while a 'press a key' box is waiting", app.capture_callback is None)
app._on_key_release(keyboard.Key.ctrl_r)
app._on_key_release(keyboard.Key.alt_gr)

# ---- Edit: Trim window and the autosave
app.current_file = None
app.actions = None
app.events = [dict(e) for e in events]
app.name_var.set("To trim")
app.open_editor()
pump(0.5)
ed = app.macro_editor
ed._open_entry(ed.current if ed.current is not None else 0, ask=False)
recorded = ed.steps[0]
win = ed.trim_window(recorded)
pump(0.2)
check("trim window: lists the three suggestions, pauses unticked",
      [v.get() for v in win.state["vars"]] == [True, False, True], [v.get() for v in win.state["vars"]])
win.every(True)
win.cut()
pump(0.2)
check("trim window: Cut shortened the recorded part (one Undo point)",
      len(ed.steps[0]["events"]) == 6 and ed.steps[0]["events"][-1]["t"] == 11.6 and len(ed.undo_stack) == 1,
      (len(ed.steps[0]["events"]), len(ed.undo_stack)))
ed.autosave_now()
auto = macro_editor.MacroEditor.autosave_path()
check("autosave: unapplied changes are written to a file", os.path.isfile(auto))
ed.undo()
ed.autosave_now()
check("autosave: nothing unapplied, no file", not os.path.isfile(auto))
ed.redo()
ed.autosave_now()
# the app "crashes": the window goes without Apply or the question
ed.win.destroy()
app.macro_editor = None
check("autosave: the file is still there after a crash", os.path.isfile(auto))
asked = []
app.boxes.askyesno = lambda *a, **k: (asked.append(a), True)[1]
app.open_editor()
pump(0.8)
ed = app.macro_editor
check("autosave: Edit offers the changes back and restores them", asked and len(ed.steps[0]["events"]) == 6
      and ed._changed(), (len(asked), len(ed.steps[0]["events"])))
ed.apply()
ed.autosave_now()
check("autosave: applied, so the file is gone", not os.path.isfile(auto) and len(app.events) == 6, len(app.events))
ed.win.destroy()

# switching with no profile in use keeps the settings as a profile first (they used to be lost)
app.settings.pop("profile_active", None)
app.ready_var.set(9)
app._save_settings()
app.switch_profile("Farming")
check("profiles: switching from no profile keeps the old settings as \"My settings\"",
      any(n.startswith("My settings") and p.get("ready_seconds") == 9 for n, p in app.profiles().items()),
      list(app.profiles()))

# the notice under Saved macros when a linked macro switched the profile
app.switch_profile("Fast")
root.deiconify()
pump(0.3)
size_before = (root.winfo_width(), root.winfo_height())
app.load(path, quiet=True)  # (linked.macro is linked to Farming)
pump(0.3)
check("notice: shown under Saved macros after the linked macro switched the profile",
      "Farming" in app.profile_notice.cget("text"), app.profile_notice.cget("text"))
check("notice: the window keeps its size when it shows", (root.winfo_width(), root.winfo_height()) == size_before,
      (size_before, (root.winfo_width(), root.winfo_height())))
unlinked = os.path.join(tmp, "plain.macro")
with open(unlinked, "w", encoding="utf-8") as f:
    json.dump({"app": "macro_recorder", "version": 1, "events": [key(65, 0.0), key(65, 0.1, False)]}, f)
app.load(unlinked, quiet=True)
pump(0.1)
check("notice: gone after opening a macro that isn't linked, the window still the same size",
      app.profile_notice.cget("text") == "" and (root.winfo_width(), root.winfo_height()) == size_before)
root.withdraw()

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} passed")
root.destroy()
sys.exit(1 if failed else 0)
