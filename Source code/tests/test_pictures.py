"""Tests for Picture watch 2.9: groups, the built-in pictures, moving older settings over (with a
backup), pictures for some macros only, and the Picture watch window (its Undo / Redo / Reset /
Apply). No real input, a throwaway settings folder; no message box waits for a click."""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, sys.argv[1])
tmp = tempfile.mkdtemp(prefix="mr_pics_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402

import image_watch  # noqa: E402
import modern_ui  # noqa: E402
import stats  # noqa: E402

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
boxes = []
for name in ("showwarning", "showinfo", "showerror"):
    setattr(app.boxes, name, lambda *a, **k: boxes.append(a))
app.boxes.askyesno = lambda *a, **k: True
answers = []
app.boxes.askchoice = lambda *a, **k: answers.pop(0) if answers else None


def pump(seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def all_pics():
    return app.watch_pictures + app.result_pictures


# ---- a new copy of the app: every built-in picture, on, in AOT:R
pump(0.3)
builtins = sorted(p.get("builtin") for p in all_pics())
check("first start: the 4 built-in pictures", builtins == ["completed", "disconnect", "failed", "retry"], builtins)
check("first start: all in AOT:R and on",
      all(core.picture_group(p) == "aotr" and p.get("on") is not False for p in all_pics()))
check("first start: groups AOT:R and My pictures",
      [g["id"] for g in app.settings.get("picture_groups", [])] == ["aotr", "mine"], app.settings.get("picture_groups"))
check("first start: RETRY and Disconnected are watched, the titles count results",
      sorted(p["builtin"] for p in app.watch_pictures) == ["disconnect", "retry"]
      and sorted(p["kind"] for p in app.result_pictures) == ["loss", "win"])
dc = next(p for p in app.watch_pictures if p["builtin"] == "disconnect")
check("first start: Disconnected plays the rejoin macro", dc.get("action") == "recover" and dc.get("name") == "Disconnected")
check("first start: no backup (nothing to back up)", not os.path.isdir(os.path.join(tmp, "Backups")))
check("summary on the Settings page", app.picture_summary() == "AOT:R: 4 of 4 on", app.picture_summary())

# ---- moving older settings over (2.8 had no groups): a copy of the settings is kept first
pic = np.zeros((20, 40, 3), np.uint8)
pic[5:15, 5:35] = (40, 200, 240)
image_watch.save_image(os.path.join(core.watch_dir(), "own.png"), pic)
retry_img = image_watch.load_image(core.resource_path(core.BUILTIN_PICTURE))
image_watch.save_image(os.path.join(core.watch_dir(), "old_retry.png"), retry_img)
win_img = image_watch.load_image(core.resource_path(core.BUILTIN_WIN_PICTURE))
image_watch.save_image(os.path.join(core.watch_dir(), "old_win.png"), win_img)
app.settings.pop("picture_groups")
app.settings["watch_pictures"] = [{"file": "old_retry.png", "screen_h": 1080, "click": True},
                                  {"file": "own.png", "screen_h": 1440, "name": "Lobby"}]
app.settings["result_pictures"] = [{"file": "old_win.png", "screen_h": 1440, "kind": "win"}]
with open(core.settings_path(), "w", encoding="utf-8") as f:
    json.dump(app.settings, f)
core._settings_write["written"].clear()
app.watch_pictures = [core.watch_picture_from(e) for e in app.settings["watch_pictures"]]
app._load_result_pictures()
app.pictures_fresh = False
app._setup_picture_groups()
backup = os.path.join(tmp, "Backups", "settings before 2.9 picture groups.json")
check("2.9 first start: the settings were backed up first", os.path.isfile(backup)
      and "old_retry.png" in open(backup, encoding="utf-8").read())
by_file = {p["file"]: p for p in all_pics()}
check("2.9 first start: the old RETRY copy is found to be the built-in one, in AOT:R, keeps its options",
      by_file["old_retry.png"].get("builtin") == "retry" and core.picture_group(by_file["old_retry.png"]) == "aotr"
      and by_file["old_retry.png"].get("click") is True, {k: v for k, v in by_file["old_retry.png"].items() if k != "img"})
check("2.9 first start: your own picture goes to My pictures",
      core.picture_group(by_file["own.png"]) == "mine" and not by_file["own.png"].get("builtin"))
check("2.9 first start: the old MISSION COMPLETED copy is found too",
      by_file["old_win.png"].get("builtin") == "completed" and core.picture_group(by_file["old_win.png"]) == "aotr")
added = [p for p in all_pics() if p["file"] not in ("old_retry.png", "own.png", "old_win.png")]
check("2.9 first start: the missing built-ins are added, off (you didn't have them)",
      sorted(p["builtin"] for p in added) == ["disconnect", "failed"] and all(p.get("on") is False for p in added),
      [(p.get("builtin"), p.get("on")) for p in added])
saved = json.load(open(core.settings_path(), encoding="utf-8"))
check("2.9 first start: written to the settings at once", saved.get("picture_groups")
      and any(e.get("builtin") == "retry" for e in saved.get("watch_pictures", [])))
check("summary: on counts", app.picture_summary() == "AOT:R: 2 of 4 on · My pictures: 1 of 1 on", app.picture_summary())

# ---- which pictures are used: on, group on, every macro or this one
app.current_file = os.path.join(tmp, "Farm.macro")
own = by_file["own.png"]
active = {p["file"] for p in app._active_watch_pictures()}
check("used: the pictures that are on", active == {"old_retry.png", "own.png"}, active)
own["macros"] = [os.path.join(tmp, "Other.macro")]
check("used: a picture for another macro isn't", "own.png" not in {p["file"] for p in app._active_watch_pictures()})
check("used: ...but is for that macro", "own.png" in {p["file"] for p in app._active_watch_pictures(
    os.path.join(tmp, "Other.macro"))})
own.pop("macros")
app.settings["picture_groups"][0]["on"] = False
active = {p["file"] for p in app._active_watch_pictures()}
check("used: a group that's off turns its pictures off", active == {"own.png"}, active)
check("used: result pictures follow their group too", not app._active_result_pictures())
app.settings["picture_groups"][0].pop("on")
check("saved inside a macro: only the pictures used for it",
      len(app._pictures_for_file(os.path.join(tmp, "Farm.macro"))) == 2)
own["macros"] = [os.path.join(tmp, "Other.macro")]
check("saved inside a macro: a picture for another macro stays out",
      len(app._pictures_for_file(os.path.join(tmp, "Farm.macro"))) == 1)
app._pictures_macro_renamed(os.path.join(tmp, "Other.macro"), os.path.join(tmp, "Renamed.macro"))
check("a renamed macro: the picture follows it", own["macros"] == [os.path.abspath(os.path.join(tmp, "Renamed.macro"))],
      own.get("macros"))
own.pop("macros")

# ---- the window
w = app.open_picture_watch()
pump(0.4)
check("window: opens on AOT:R with its 4 pictures", len(w.pics_tree.get_children()) == 4,
      len(w.pics_tree.get_children()))
check("window: General, AOT:R and My pictures on the left",
      list(w.groups_tree.get_children()) == ["general", "aotr", "mine"], w.groups_tree.get_children())
check("window: nothing changed yet: Apply is off", str(w.btn_apply.cget("state")) == "disabled")
check("window: built-ins can't be removed from AOT:R",
      w.pics_tree.selection_set(w.pics_tree.get_children()[0]) or (pump(0.1), True)[1]
      and str(w.btn_remove_pic.cget("state")) == "disabled")
first = w._pic(w.sel_pic)
w.remove_picture()
check("window: Remove says why for a built-in in AOT:R", first in w.pics and boxes, boxes[-1:])

# turning a picture off, Undo, Redo
w.change(lambda: first.update(on=False))
check("window: a change lights Apply", str(w.btn_apply.cget("state")) == "normal")
w.undo()
check("window: Undo puts it back", w._pic(first["_uid"]).get("on") is not False and not w.changed())
w.redo()
check("window: Redo does it again", w._pic(first["_uid"]).get("on") is False and w.changed())
w.reset()
check("window: Reset: as when it opened", not w.changed())

# a new group, named in the box at the top
w.new_group()
pump(0.1)
w.name_var.set("Night farm")
pump(0.1)
g = w._group(w.sel_group)
check("window: New group, renamed with the name box", g and g["name"] == "Night farm" and "Night farm" in
      w.groups_tree.item(g["id"], "text"), g)
# a built-in added into it keeps its built-in settings
w.add_builtin("disconnect")
pump(0.1)
e = w._pic(w.sel_pic)
check("window: Add built-in into another group: built-in settings, in that group",
      e["group"] == g["id"] and e.get("builtin") == "disconnect" and e.get("action") == "recover"
      and os.path.isfile(os.path.join(core.watch_dir(), e["file"])), {k: v for k, v in e.items()})
# its options change from the form on the right
w.form.vars["action"].set(core.WATCH_ACTION_NAMES["restart"])
w.form.vars["layout"](set_counts=True)
pump(0.1)
check("window: the options on the right change the picture", e.get("action") is None, e.get("action"))
w.reset_builtin(e)
check("window: Reset to built-in", w._pic(e["_uid"]).get("action") == "recover")
e = w._pic(e["_uid"])
w.change(lambda: e.update(macros=[app.current_file]))
check("window: the row says how many macros", "1 macro" in w.pics_tree.item(str(e["_uid"]), "text"),
      w.pics_tree.item(str(e["_uid"]), "text"))
# Apply: everything is used
assert w.apply()
pump(0.1)
check("window: Apply writes the groups", any(x.get("name") == "Night farm" for x in app.settings["picture_groups"]))
new_pic = next((p for p in app.watch_pictures if p["file"] == e["file"]), None)
check("window: Apply: the app uses the new picture, for that macro, in that group",
      new_pic is not None and new_pic.get("group") == g["id"] and new_pic.get("macros") == [app.current_file])
check("window: after Apply nothing is waiting", not w.changed() and str(w.btn_apply.cget("state")) == "disabled")

# removing a picture deletes its file only on Apply
w.select_group(g["id"])
w.sel_pic = e["_uid"]
w.remove_picture()
path = os.path.join(core.watch_dir(), e["file"])
check("window: removed, but the file stays until Apply (Undo can bring it back)", os.path.isfile(path))
w.apply()
check("window: Apply removes its file", not os.path.isfile(path))

# General: the options for every picture
w.select_group("general")
pump(0.1)
w.general["watch_match"] = 90
w._show_buttons()
w.apply()
check("window: General options are applied to the app", app.settings.get("watch_match") == 90
      and app.watch_match_var.get() == 90)

# a group that's off: its pictures show grey, with the reason
w.select_group("mine")
w.change(lambda: w._group("mine").update(on=False))
row = w.pics_tree.get_children()[0]
check("window: a picture in a group that's off says why", "group \"My pictures\" is off" in
      w._picture_tip(w._pic(int(row))))
# closing with changes asks: Discard throws them away, and a picture added then thrown away goes
w.add_builtin("retry")
added_file = w._pic(w.sel_pic)["file"]
answers.append("discard")
w.close()
pump(0.1)
check("window: closing with changes asks; Discard keeps the settings as they were",
      all(x.get("on") is not False for x in app.settings["picture_groups"] if x["id"] == "mine")
      and not w.alive())
check("window: a picture added and discarded is deleted", not os.path.isfile(os.path.join(core.watch_dir(), added_file)))

# ---- Results page: the pictures moved out, a button leads to them
app.open_settings("Results")
pump(0.5)
check("Results page: no picture lists any more, a button opens Picture watch",
      not hasattr(app, "result_lists") and any(str(b.cget("text")).startswith("Open Picture watch")
                                               for b in app.result_buttons))
app.close_settings()

# ---- the yellow note for macros recorded before 2.6
app.events = [{"type": "key", "key": {"vk": 65}, "pressed": True, "t": 0.0}]
app.macro_program = None
app._refresh()
check("old macro: the yellow note instead of the line under the name",
      app.info_var.get() == app.OLD_MACRO_NOTE and app.old_macro_var.get() == app.OLD_MACRO_NOTE)
app.macro_program = {"exe": "Game.exe", "client": [0, 0, 800, 600]}
app._refresh()
check("a macro that knows its window: no note", app.info_var.get() != app.OLD_MACRO_NOTE
      and not app.old_macro_var.get(), app.info_var.get())
check("no red fullscreen line in Settings > Playback any more",
      "Some macros were recorded in fullscreen" not in open(os.path.join(sys.argv[1], "settings_pages.py"),
                                                          encoding="utf-8").read().split("SCREEN_SIZE_HELP")[2])

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} passed")
core.flush_settings()
root.destroy()
sys.exit(1 if failed else 0)
