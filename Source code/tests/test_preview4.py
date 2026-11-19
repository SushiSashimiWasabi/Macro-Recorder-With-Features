"""Preview 4, round A: the Settings search list closes, windows keep their size (resize + scroll),
the macro's game window can be changed in Edit, the pause names the window ("Bring it to front"),
files keep no window title, in / out of groups, the new names (old ones still found by search).
Opens windows (off to the side) but sends no input to other programs; throwaway settings."""
import io
import json
import os
import sys
import tempfile
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_preview4_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import tkinter as tk  # noqa: E402

import modern_ui  # noqa: E402
import window_tools  # noqa: E402
import extras_ui  # noqa: E402

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
app.boxes.askyesnocancel = lambda *a, **k: False
app.rec_ask_window_var.set(False)
app._save_settings()


def pump(n=5):
    for _ in range(n):
        root.update()
        time.sleep(0.02)


root.deiconify()
root.geometry("+30+30")
pump(10)

# ---------------------------------------------------------------- files keep no window title (Q3)
buf = io.StringIO()
core.dump_macro({"app": "macro_recorder", "program": {"exe": "RobloxPlayerBeta.exe", "title": "Roblox - secret chat",
                                                       "client": [0, 0, 800, 600]}, "events": []}, buf)
data = json.loads(buf.getvalue())
check("file: program name and size kept, window title left out",
      data["program"] == {"exe": "RobloxPlayerBeta.exe", "client": [0, 0, 800, 600]}, data["program"])
check("friendly name: Roblox for its player, else the file name",
      window_tools.friendly_name("RobloxPlayerBeta.exe") == "Roblox" and window_tools.friendly_name("Game.exe") == "Game"
      and window_tools.friendly_name(None) == "")

# ---------------------------------------------------------------- the main window keeps its size (item 2)
app.loop_var.set(False)
app._loop_changed(save=False)
pump()
size_off = (root.winfo_width(), root.winfo_height())
app.loop_var.set(True)
app._loop_changed(save=False)
pump()
size_on = (root.winfo_width(), root.winfo_height())
check("main window: Repeat continuously on / off doesn't change its size", size_off == size_on, (size_off, size_on))
check("main window: \"or play N times\" hidden while repeating", not app.times_inner.winfo_ismapped())
check("main window: can be resized", root.resizable() == (True, True))
w0, h0 = root.winfo_reqwidth(), root.winfo_reqheight()
root.geometry(f"{w0}x{max(150, h0 // 2)}")
pump(10)
check("main window: smaller than its parts -> a scroll bar", app.main_scroll.vbar.winfo_ismapped())
pump(40)  # (the size is kept half a second after the last change)
check("main window: the size you set is remembered", app.settings.get("main_size") == f"{w0}x{max(150, h0 // 2)}",
      app.settings.get("main_size"))
app.reset_window_sizes()
pump(40)
check("Reset window sizes: usual size again, nothing kept",
      "main_size" not in app.settings and not app.main_scroll.vbar.winfo_ismapped()
      and (root.winfo_width(), root.winfo_height()) == (w0, h0), (root.winfo_width(), root.winfo_height(), w0, h0))
app.settings["main_size"] = "99999x99999"
app._keep_window_size(root, "main_size")
pump(5)
check("main window: a saved size bigger than the screen is cut to the screen",
      root.winfo_width() <= root.winfo_screenwidth() and root.winfo_height() <= root.winfo_screenheight())
app.reset_window_sizes()
pump(10)

# (2.13 Mac fix) a scroll area in a hidden window settles: it doesn't lay itself out again and again
hidden = tk.Toplevel(root)
hidden.withdraw()
area = modern_ui.ScrollArea(hidden, "#000000", natural=True)
area.pack(fill="both", expand=True)
tk.Frame(area.inner, width=900, height=900).pack()
calls = []
real_fit = area._fit
area._fit = lambda: (calls.append(1), real_fit())
hidden.geometry("200x200")
for _ in range(50):
    root.update()
check("scroll area: settles in a hidden window (no endless layout)", len(calls) < 20, len(calls))
hidden.deiconify()
hidden.geometry("200x200+40+40")
pump(10)
check("scroll area: once shown, both bars", area.vbar.winfo_ismapped() and area.hbar.winfo_ismapped())
hidden.destroy()

# ---------------------------------------------------------------- Settings: size, scroll, search (items 1, 2, 4)
app.open_settings()
sw = app.settings_win
sw.geometry("+60+60")
pump(15)
check("Settings: can be resized", sw.resizable() == (True, True))
check("Settings: not taller than the screen", sw.winfo_height() <= sw.winfo_screenheight() - 60, sw.winfo_height())
tall = app.tab_areas["Playback"]
app.tabs.select(tall)
pump(5)
sw.geometry(f"{sw.winfo_width()}x300")
pump(15)
check("Settings: a page taller than the window scrolls", tall.vbar.winfo_ismapped())
app.search_var.set("pause")
pump(5)
check("search: the list shows", app.search_list is not None and app.search_list.winfo_exists())
app.tabs.select(app.tab_areas["General"])
pump(5)
check("search: changing page closes the list", app.search_list is None)
app.search_var.set("game closes")
pump(5)
check("search: the list shows again", app.search_list is not None)
sw.geometry(f"+{sw.winfo_rootx() + 40}+{sw.winfo_rooty() + 30}")
pump(10)
check("search: moving Settings closes the list", app.search_list is None)
app.search_var.set("pause")
pump(5)
app.close_settings()
pump(5)
check("search: closing Settings closes the list", app.search_list is None or not app.search_list.winfo_exists())
app.open_settings()
pump(10)
found = [label for _p, _w, label in app.search_settings("Pause if the game isn't in front")]
check("names: the new name shows, the old name still finds it",
      any("Pause when the macro's window isn't in front" in t for t in found), found)
found = [label for _p, _w, label in app.search_settings("status bar")]
check("names: old \"Status bar\" finds \"Status line at the bottom\"", any("Status line at the bottom" in t for t in found),
      found)
page, widget, label = next(f for f in app.search_settings("Remember YouTube sign-in"))
app.search_found = [(page, widget, label)]
app._search_go(0)
pump(10)
check("search: jumping to a setting deep in a page scrolls it into view",
      app.tab_areas[page].canvas.winfo_rooty() - 5 <= widget.winfo_rooty()
      <= app.tab_areas[page].canvas.winfo_rooty() + app.tab_areas[page].canvas.winfo_height(), page)
app.reset_window_sizes()
app.close_settings()
pump(5)

# ---------------------------------------------------------------- Edit: the game window (item 3), in / out (item 5)
path = os.path.join(tmp, "game.macro")
evs = [{"type": "key", "key": {"vk": 65}, "pressed": True, "t": 0.0},
       {"type": "key", "key": {"vk": 65}, "pressed": False, "t": 0.2}]
with open(path, "w", encoding="utf-8") as f:
    json.dump({"app": "macro_recorder", "version": 1, "events": evs,
               "program": {"exe": "Game.exe", "title": "Game", "client": [0, 0, 1280, 720]}}, f)
app._remember_macro(path)
app.load(path, quiet=True)
pump()
app.open_editor()
ed = app.macro_editor
ed.win.geometry("1220x720+40+40")
pump(10)
check("Edit: shows the macro's game window", "Game" in ed.game_label.cget("text") and "1280×720" in ed.game_label.cget("text"),
      ed.game_label.cget("text"))
ed.forget_game_window()
pump()
check("Edit: Forget lights up Apply", str(ed.btn_apply.cget("state")) == "normal" and "none" in ed.game_label.cget("text"))
ed.reset()
pump()
check("Edit: Reset brings the game window back", (ed.program or {}).get("exe") == "Game.exe")
# Change… with a stand-in window list
window_tools_app_windows = window_tools.app_windows
window_tools.app_windows = lambda: [(111, "Other game", "Other.exe")]
box = ed.change_game_window()
pump()
check("Change…: the box lists the open windows and warns about the size", box.winfo_exists())
box.event_generate("<Return>")
pump()
window_tools.app_windows = window_tools_app_windows
check("Change…: the new program, the recorded size kept", ed.program == {"exe": "Other.exe", "client": [0, 0, 1280, 720]},
      ed.program)
ed.apply()
pump()
with open(path, encoding="utf-8") as f:
    saved = json.load(f)
check("Apply: the file plays in the new window (no title)", saved.get("program") == {"exe": "Other.exe",
                                                                                      "client": [0, 0, 1280, 720]})
check("Apply: the open macro plays in the new window too", (app.macro_program or {}).get("exe") == "Other.exe")

# in / out of a group
ed.add("if")
pump()
ed.add("wait")  # (goes inside the chosen If)
pump()
wait_id = ed._selected_id()
check("buttons: ⇤ Out shown and usable inside a group", ed.btn_out.winfo_ismapped()
      and str(ed.btn_out.cget("state")) == "normal")
ed.btn_out.invoke()
pump()
found = ed._selected()
check("⇤ Out: the action left its group", found and found[3] is None and found[0]["id"] == wait_id)
check("In ⇥: usable right after a group", str(ed.btn_in.cget("state")) == "normal"
      and str(ed.btn_out.cget("state")) == "disabled")
ed.btn_in.invoke()
pump()
found = ed._selected()
check("In ⇥: back inside the group above", found and found[3] is not None)
menu_items = []
real_menu = ed._menu


def spy_menu():
    m = real_menu()
    menu_items.append(m)
    m.tk_popup = lambda *a, **k: None
    return m


ed._menu = spy_menu
row = ed.tree.bbox(wait_id)
ed._right_click(type("E", (), {"y": row[1] + 2, "x_root": 0, "y_root": 0})())
m = menu_items[-1]
labels = {m.entrycget(i, "label"): m.entrycget(i, "state") for i in range(m.index("end") + 1) if m.type(i) == "command"}
check("right-click: the group items are there", all(k in labels for k in (
    "Move out of the group", "Move into the group above", "Put in a new If", "Put in a new Repeat",
    "Put in a new Retry", "Ungroup")), list(labels))
check("right-click: what can't be done now is greyed out", labels.get("Move into the group above") == "disabled"
      and labels.get("Move out of the group") == "normal" and labels.get("Ungroup") == "disabled")
ed._menu = real_menu
ed.win.destroy()
pump()

# ---------------------------------------------------------------- the pause names the window (item 3, Q2)
app.macro_program = {"exe": "RobloxPlayerBeta.exe"}
check("pause: names the window", app._away_name() == "Roblox")
app.macro_program = None
check("pause: unknown program -> the old words", app._away_name() == "")
ov = modern_ui.PlayOverlay(root, root.winfo_screenwidth())
ov.show("Paused", "00:05", "Paused: Roblox isn't in front. Click Roblox to go on", "#f0a020", {"pause": "F10", "stop": "F12"})
pressed = []
ov.front_button(lambda: pressed.append(1), "Bring Roblox to front")
pump()
check("Bring it to front: shows under the timer", ov.front_win.winfo_viewable()
      and ov.front_win.winfo_rooty() >= ov.win.winfo_rooty() + ov.win.winfo_height())
ov.front_label.event_generate("<ButtonRelease-1>")
check("Bring it to front: a click runs it", pressed == [1])
ov.front_button(None)
pump()
check("Bring it to front: hidden again when playing goes on", not ov.front_win.winfo_viewable())
ov.show("Paused", "00:06", "", "#f0a020")
ov.front_button(lambda: None)
ov.hide()
pump()
check("Bring it to front: hidden with the timer", not ov.front_win.winfo_viewable())
gone = []
app.away_games = {12345}
real_front = window_tools.force_to_front
window_tools.is_window = (lambda real: (lambda h: h == 12345 or real(h)))(window_tools.is_window)
window_tools.force_to_front = lambda h: gone.append(h) or True
app._bring_game_front()
window_tools.force_to_front = real_front
check("Bring it to front: puts the macro's window in front", gone == [12345])
app.away_games = None

# ================================================================ round B

# ---------------------------------------------------------------- milestones
import stats  # noqa: E402
import milestones_ui  # noqa: E402

app.settings.pop("milestones", None)
app.settings["stats_all"] = {"runs": 1200, "wins": 900, "fragments": 10, "seconds": 3600}
ms = app.milestones()
check("milestones: the usual four", [(m["kind"], m["at"]) for m in ms] == [("runs", 1000), ("fragments", 50),
                                                                          ("streak", 500), ("hours", 500)])
check("milestones: one already passed counts as reached, without a sound", ms[0].get("reached") and
      not ms[1].get("reached"))
ok, note = app.add_milestone("wins", "1,000", "My 1k wins")
check("milestones: add your own", ok and any(m.get("name") == "My 1k wins" for m in app.milestones()), note)
check("milestones: a wrong number is refused", not app.add_milestone("wins", "lots")[0]
      and not app.add_milestone("wins", "0")[0] and not app.add_milestone("nope", "5")[0])
check("milestones: the same one twice is refused", not app.add_milestone("wins", "1000")[0])
sounds_played = []
app._sound = lambda name: sounds_played.append(name)
app.session = stats.Session("test")
for _ in range(100):
    app.session.add(stats.WIN, 30)
reached = app.check_milestones()
check("milestones: reached during a session (wins 900 + 100)", [m.get("name") for m in reached] == ["My 1k wins"]
      and sounds_played == ["milestone"], reached)
check("milestones: wins in a row are counted over sessions", app.settings["stats_all"]["best_streak"] == 1)
again = app.check_milestones()
check("milestones: told only once", again == [] and sounds_played == ["milestone"])
app.session.added = True
check("milestones: a session added to all-time isn't counted twice",
      app.milestone_totals()["wins"] == 900)
app.remove_milestone(len(app.milestones()) - 1)
check("milestones: remove", len(app.milestones()) == 4)
check("milestones: bad entries from the file are dropped", milestones_ui.clean_milestone(
    {"kind": "runs", "at": 1e400}) is None and milestones_ui.clean_milestone({"kind": "x", "at": 5}) is None)
import profiles_ui  # noqa: E402
check("milestones, folders, tour: not part of profiles", {"milestones", "macro_meta", "macro_folders",
                                                          "tour_done"} <= profiles_ui.SKIP_KEYS)

# ---------------------------------------------------------------- folders and tags
import macro_folders  # noqa: E402

pa, pb = os.path.join(tmp, "farm one.macro"), os.path.join(tmp, "rejoin.macro")
for pth in (pa, pb):
    with open(pth, "w", encoding="utf-8") as f:
        json.dump({"app": "macro_recorder", "version": 1, "events": evs}, f)
    app._remember_macro(pth)
app.set_macro_folder([pa], "AOT:R farming")
app.set_macro_tags(pb, "Rejoin, #aot:r, rejoin")
check("folders: a macro goes in a folder", app.macro_meta(pa)["folder"] == "AOT:R farming"
      and "AOT:R farming" in app.macro_folders())
check("tags: cleaned, no doubles", app.macro_meta(pb)["tags"] == ["rejoin", "aot:r"], app.macro_meta(pb))
check("filter: by name, folder and #tag", app.macro_matches(pa, "farming") and app.macro_matches(pb, "#rejoin")
      and not app.macro_matches(pa, "#rejoin") and app.macro_matches(pa, "farm one"))
app._set_row_folder("AOT:R farming")
check("◀ ▶ row: only the chosen folder", app.row_macros() == [os.path.abspath(pa)], app.row_macros())
check("◀ ▶ row: shows the folder", app.row_folder_link.cget("text").startswith("AOT:R"))
app.rename_folder("AOT:R farming", "Farm")
check("folders: rename keeps its macros and the row's choice", app.macro_meta(pa)["folder"] == "Farm"
      and app.row_folder() == "Farm")
app.open_editor()
ed = app.macro_editor
pump(10)
check("Edit: the folder shows with its macro inside", ed.macros.exists("f:Farm") and
      any(ed.entries[int(i)][1] == pa for i in ed.macros.get_children("f:Farm")))
ed.macro_filter_var.set("#rejoin")
pump()
shown = [ed.entries[int(i)][1] for i in ed.macros.get_children("")] + \
        [ed.entries[int(i)][1] for f in ed.macros.get_children("") if f.startswith("f:") for i in ed.macros.get_children(f)]
check("Edit: the filter shows only matching macros", shown == [pb], shown)
ed.macro_filter_var.set("")
pump()
k = next(i for i, (_l, p) in enumerate(ed.entries) if p == pb)
ed._drop_macros([str(k)], "f:Farm", "into")
check("Edit: a macro dropped on a folder goes into it", app.macro_meta(pb)["folder"] == "Farm")
app.meta_renamed(pb, pb + ".renamed")
check("folders: a renamed macro keeps its folder and tags", app.macro_meta(pb + ".renamed")["folder"] == "Farm")
app.remove_folder("Farm")
check("folders: removing one keeps its macros (no folder)", app.macro_meta(pa)["folder"] == "" and
      app.row_folder() == "" and pa in [p for p in app.macro_list()])
ed.win.destroy()
pump()

# ---------------------------------------------------------------- colour themes
import ui_common  # noqa: E402
import themes  # noqa: E402


def contrast(a, b):
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


check("themes: white text on every accent is readable (3:1)", all(contrast(t[0], "#ffffff") >= 3.0
                                                                  for t in ui_common.THEMES.values()),
      {n: round(contrast(t[0], "#ffffff"), 2) for n, t in ui_common.THEMES.items()})
check("themes: every accent as text on the dark window is readable (4.5:1)",
      all(contrast(t[0], ui_common.BG) >= 4.5 for t in ui_common.THEMES.values()),
      {n: round(contrast(t[0], ui_common.BG), 2) for n, t in ui_common.THEMES.items()})
app.open_settings()
pump(10)
line = app.tab_labels["General"][1]
app.tabs.select(app.tab_areas["General"])
pump(5)
app.apply_accent("Purple")
pump(5)
purple = ui_common.THEMES["Purple"][0]
check("themes: changed at once (the page line, every module's colour)", str(line.cget("bg")).lower() == purple
      and modern_ui.ACCENT == purple and ui_common.ACCENT == purple, line.cget("bg"))
check("themes: saved", app.settings.get("accent") == "Purple")
check("themes: the colour samples keep their own colours",
      app.accent_swatches["Blue"].winfo_children()[0].cget("bg").lower() == ui_common.THEMES["Blue"][0])
app.undo_settings_change()
pump(5)
check("themes: Undo puts the colour back at once", ui_common.ACCENT == ui_common.THEMES["Blue"][0]
      and str(line.cget("bg")).lower() == ui_common.THEMES["Blue"][0], ui_common.ACCENT)
app.close_settings()
pump()

# ---------------------------------------------------------------- keys on screen
import keys_overlay  # noqa: E402
import image_watch  # noqa: E402

held = set()
texts = [keys_overlay.event_text(e, held) for e in (
    {"type": "key", "key": {"special": "shift"}, "pressed": True},
    {"type": "key", "key": {"char": "e", "vk": 69}, "pressed": True},
    {"type": "key", "key": {"char": "e", "vk": 69}, "pressed": False},
    {"type": "key", "key": {"special": "shift"}, "pressed": False},
    {"type": "click", "button": "left", "pressed": True, "x": 1, "y": 1},
    {"type": "move", "x": 5, "y": 5})]
check("keys: what the box says", texts == [None, "Shift + E", None, None, "Left click", None], texts)
app.settings["keys_on_screen"] = True
ov = app._keys_overlay()
app._keys_seen({"type": "key", "key": {"char": "w", "vk": 87}, "pressed": True})
ov.tick()
pump()
check("keys: the box shows in its corner", ov.win.winfo_viewable() and ov.label.cget("text") == "W"
      and ov.win.winfo_rootx() > root.winfo_screenwidth() // 2)
check("keys: Picture watch doesn't look at it", ov.rect in image_watch.IGNORE_RECTS)
img = image_watch.np.full((50, 50, 3), 255, image_watch.np.uint8)
image_watch.IGNORE_RECTS.append((10, 10, 20, 20))
image_watch._blank_ignored(img)
image_watch.IGNORE_RECTS.pop()
check("keys: its place is black in Picture watch's screenshots", img[15, 15].sum() == 0 and img[5, 5].sum() == 765)
ov.hide()
pump()
check("keys: hidden after", not ov.win.winfo_viewable() and ov.rect is None)
app._keys_seen({"type": "key", "key": {"char": "w"}, "pressed": True})
app.settings["keys_on_screen"] = False
app._keys_seen({"type": "key", "key": {"char": "q"}, "pressed": True})
check("keys: off = nothing collected", len(ov.pending) == 1)
ov.pending.clear()

# ---------------------------------------------------------------- guided tour
app.settings["first_start_done"] = True
app.settings.pop("tour_done", None)
check("tour: due once, also for people who already use the app", app.tour_due())
win = app.start_tour()
pump(5)
check("tour: step 1 points at Record", win.winfo_viewable() and app.tour_title.cget("text") == "Record"
      and all(b.winfo_viewable() for b in app.tour_marks))
check("tour: it doesn't take over the app", win.grab_current() is None)
for _ in range(5):
    app._tour_go(1)
pump()
check("tour: the last step says Done", app.tour_next.cget("text") == "Done" and app.tour_title.cget("text") == "Settings")
app._tour_go(1)
pump()
check("tour: Done closes it and it's not shown again", app.tour_win is None and not app.tour_due()
      and app.settings.get("tour_done"))
app.start_tour()
app.end_tour()
check("tour: Replay works any time, Skip closes it", app.tour_win is None)

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
