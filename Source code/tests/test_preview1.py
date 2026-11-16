"""2.10 preview 1: new sounds and the countdown before rejoining, Check my macro, older versions of a
macro, and exporting the run stats. No real input, no sound, no window shown, no message box, a
throwaway settings folder."""
import csv
import datetime
import json
import os
import sys
import tempfile
import threading
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_p1_")
settings_dir = os.path.join(tmp, "settings")
os.makedirs(settings_dir)
macros_dir = os.path.join(tmp, "macros")
os.makedirs(macros_dir)

import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(settings_dir, "settings.json")
import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402

import check_ui  # noqa: E402
import macro_steps as workflow  # noqa: E402
import macro_versions  # noqa: E402
import modern_ui  # noqa: E402
import run_history  # noqa: E402
import sounds  # noqa: E402
import stats  # noqa: E402
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
root.withdraw()
played = []
app.player = type("P", (), {"beep": lambda s, n, v=50: played.append(n),
                            "play_file": lambda s, p, v=50, fallback=None: played.append(fallback),
                            "stop": lambda s, wait=True: None, "can_play": lambda s, p: True})()
box_calls = []
for name in ("showwarning", "showinfo", "showerror"):
    setattr(app.boxes, name, lambda *a, _n=name, **k: box_calls.append((_n, a)))
app.boxes.askyesno = lambda *a, **k: True
window_tools.foreground = lambda: None
window_tools.windows_of = lambda exe: []


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


# ------------------------------------------------------------ 1. sounds
ids = sounds.EVENT_IDS
new = ["win", "loss", "fragment", "milestone", "timed_warning", "recover_disconnect", "recover_close"]
check("sounds: the new events are in Settings > Sounds", all(e in ids for e in new))
check("sounds: every event has a built-in beep", all(e in sounds.TONES for e in ids))
check("sounds: the beeps can be made (also the silent gap)",
      all(len(sounds.tone_wav(sounds.TONES[e], 0.3)) > 44 for e in new))
on_at_first = {e: on for e, _l, _t, on in sounds.EVENTS}
check("sounds: Win and Loss start off; fragment, warning and countdowns start on",
      not on_at_first["win"] and not on_at_first["loss"]
      and all(on_at_first[e] for e in ("fragment", "milestone", "timed_warning", "recover_disconnect",
                                        "recover_close")))
check("sounds: the settings choice starts like that",
      app.sound_choice("win")["mode"] == "off" and app.sound_choice("recover_close")["mode"] == "default")

# the sound for a finished run
app.session = stats.Session("M")
app.session.add(stats.WIN, 10, 0)
check("run sound: a win", app._run_sound() == "win")
app.session.add(stats.LOSS, 10, 0)
check("run sound: a loss", app._run_sound() == "loss")
app.session.add(stats.WIN, 10, 2)
check("run sound: a fragment beats the win", app._run_sound() == "fragment")
app.sound_choice("fragment")["mode"] = "off"
check("run sound: fragment off: the win sound instead", app._run_sound() == "win")
app.sound_choice("fragment")["mode"] = "default"
app.session.add(stats.UNKNOWN, 10, 0)
check("run sound: unknown: none", app._run_sound() is None)
played.clear()
app.sounds_var.set(True)
app.sound_choice("win")["mode"] = "default"
app.session.add(stats.WIN, 10, 0)
app._run_finished(1, "end")
pump(0.2)
check("run sound: plays when a run ends (Win turned on)", played == ["win"], played)
app.sound_choice("win")["mode"] = "off"
played.clear()
app._run_finished(2, "end")
pump(0.2)
check("run sound: Win off (the default): quiet", played == [], played)

# the countdown before rejoining: one tick (and sound) a second, held by Pause, ended by Stop
app.play_paused_at = None
app.play_pause_total = 0.0
app.stop_play.clear()
app.settings["recovery_countdown"] = 0
ticks = []
real_tick = app._recovery_tick
app._recovery_tick = lambda kind, left: (ticks.append((kind, left)), real_tick(kind, left))
check("countdown: 0 = none", app._recovery_countdown("disconnect") and ticks == [])
app.settings["recovery_countdown"] = 2
played.clear()
out = {}
th = threading.Thread(target=lambda: out.setdefault("r", app._recovery_countdown("disconnect")))
t0 = time.time()
th.start()
seen_overlay = []
while th.is_alive() and time.time() - t0 < 6:
    pump(0.05)
    seen_overlay.append(app.recover_left)
took = time.time() - t0
pump(0.1)
check("countdown: two ticks, a second apart", ticks == [("disconnect", 2), ("disconnect", 1)] and 1.8 < took < 3,
      (ticks, round(took, 2)))
check("countdown: goes on afterwards", out.get("r") is True)
check("countdown: a sound each second", played.count("recover_disconnect") == 2, played)
check("countdown: the timer at the top knows it, and forgets it after",
      ("disconnect", 2) in seen_overlay and app.recover_left is None)
# pause holds it
ticks.clear()
app.settings["recovery_countdown"] = 1
out.clear()
app.play_paused_at = time.perf_counter()  # paused before it starts
th = threading.Thread(target=lambda: out.setdefault("r", app._recovery_countdown("close")))
t0 = time.time()
th.start()
pump(1.5)
check("countdown: Pause holds it", th.is_alive() and ticks == [("close", 1)], ticks)
app.play_pause_total += time.perf_counter() - app.play_paused_at
app.play_paused_at = None
th.join(3)
check("countdown: goes on after Resume", out.get("r") is True and 2.2 < time.time() - t0 < 4,
      round(time.time() - t0, 2))
# stop while paused
out.clear()
app.settings["recovery_countdown"] = 5
app.play_paused_at = time.perf_counter()
th = threading.Thread(target=lambda: out.setdefault("r", app._recovery_countdown("close")))
th.start()
pump(0.3)
t0 = time.time()
app.stop_play.set()
th.join(2)
check("countdown: Stop while paused ends it at once", out.get("r") is False and time.time() - t0 < 0.5
      and app.recover_left is None)
app.play_paused_at = None
app.stop_play.clear()
# also stop while counting
out.clear()
th = threading.Thread(target=lambda: out.setdefault("r", app._recovery_countdown("disconnect")))
th.start()
pump(0.3)
app.stop_play.set()
th.join(2)
check("countdown: Stop ends it", out.get("r") is False)
app.stop_play.clear()
app._recovery_tick = real_tick

# the setting
app.recover_count_var.set(7)
app._save_settings()
check("countdown setting: saved", app.settings.get("recovery_countdown") == 7)
check("countdown setting: Undo/Reset know it", "recovery_countdown" in app.PAGE_SETTINGS)
app.recover_count_var.set(5)
app._save_settings()


# ------------------------------------------------------------ 2. Check my macro
def save_macro(name, actions=None, events=None, folder=macros_dir):
    path = os.path.join(folder, name + ".macro")
    data = {"app": "macro_recorder", "version": 1, "events": events or []}
    if actions:
        data["actions"] = actions
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def key(vk, t, pressed=True):
    return {"type": "key", "key": {"vk": vk}, "pressed": pressed, "t": t}


def chain(path, on_fail=None):
    a = workflow.new_action("play_macro")
    a["file"] = path
    if on_fail:
        a["on_fail"] = on_fail
    return a


rec = workflow.new_action("recorded")
rec["events"] = [key(65, 0.0), key(65, 0.05, False)]
inner_path = save_macro("Inner", actions=[chain(os.path.join(macros_dir, "Deep gone.macro"))])
main_path = save_macro("Main", actions=[rec, chain(inner_path), chain(os.path.join(macros_dir, "Gone.macro"),
                                                                      on_fail=os.path.join(macros_dir, "Fail gone.macro"))])
app.load(main_path, quiet=True)
app.macro_screen = None
app.macro_program = None
problems = app.check_macro((1920, 1080))
pids = [p["id"] for p in problems]
check("check: a missing chained macro is a sure problem",
      any(p["id"] == "chain:gone" and p["level"] == check_ui.SURE for p in problems), pids)
check("check: its macro for when it fails too", "chain:fail gone" in pids, pids)
check("check: also a missing macro inside a chained macro", "chain:deep gone" in pids, pids)
check("check: words for players (no 'None', no paths)",
      all("None" not in p["text"] and macros_dir not in p["text"] for p in problems), [p["text"] for p in problems])
# a picture step without a picture
wp = workflow.new_action("wait_picture")
wp.pop("png", None)
app.set_steps([rec, wp])
app.current_file = main_path
check("check: a picture step without a picture", any(p["id"].startswith("steppic:") for p in app.check_macro()))
# Picture watch: missing picture file and missing rejoin macro, and If the game closes
pic = core.SavedPicture(os.path.join(settings_dir, "watch_pictures", "nope.png"), file="nope.png", screen_h=1080,
                        action="recover", macro=os.path.join(macros_dir, "Rejoin gone.macro"))
app.watch_pictures = [pic]
app._picture_active = lambda p, path=None: True
app.settings["game_closed"] = {"on": True, "action": "reopen", "macro": os.path.join(macros_dir, "Close gone.macro")}
pids = [p["id"] for p in app.check_macro()]
check("check: a Picture watch picture whose file is gone", "watchpic:nope.png" in pids, pids)
check("check: a picture's rejoin macro that's gone", "watchmacro:nope.png:rejoin gone" in pids, pids)
check("check: If the game closes: its rejoin macro is gone", "closedmacro:close gone" in pids, pids)
app.watch_pictures = []
app.settings["game_closed"] = {"on": False, "action": "wait"}
# maybe problems: game not open, screen far off
app.set_steps([rec])
app.current_file = main_path
app.macro_program = {"exe": "RobloxPlayerBeta.exe", "title": "Roblox"}
pids = [p["id"] for p in app.check_macro()]
check("check: the game isn't open (maybe)", ("game" in pids) == window_tools.IS_WIN, pids)
window_tools.windows_of = lambda exe: [123]
check("check: the game is open: no warning", "game" not in [p["id"] for p in app.check_macro()])
window_tools.windows_of = lambda exe: []
app.macro_program = None
app.settings["fit_to"] = "screen"
app.macro_screen = (1920, 1080)
check("check: 16:9 on 16:10 is fine", not [p for p in app.check_macro((1920, 1200)) if p["id"] == "screen"])
check("check: 1080p on 1440p is fine", not [p for p in app.check_macro((2560, 1440)) if p["id"] == "screen"])
check("check: 16:9 on 4:3 is far off", [p for p in app.check_macro((1024, 768)) if p["id"] == "screen"])
check("check: a much smaller screen is far off", check_ui.screen_far_off((3840, 2160), (1280, 720)))
check("check: same size is fine", not check_ui.screen_far_off((1920, 1080), (1920, 1080)))
check("check: nothing to tell for a fine macro", app.check_macro((1920, 1080)) == [])
# don't warn me again, per macro, and back
app.macro_screen = (1920, 1080)
app.set_steps([rec, chain(os.path.join(macros_dir, "Gone.macro"))])
app.current_file = main_path
shown = app.check_on_play((1024, 768))
check("on Play: tells about both", sorted(p["id"] for p in shown) == ["chain:gone", "screen"], shown)
check("on Play: a line in the main window with See…",
      "2 things to check" in app.profile_notice.cget("text") and app.check_notice_see.cget("text") == "See…",
      app.profile_notice.cget("text"))
app.set_check_ignored("screen", True)
shown = app.check_on_play((1024, 768))
check("don't warn again: that one isn't told any more", [p["id"] for p in shown] == ["chain:gone"], shown)
check("don't warn again: kept in the settings for this macro",
      app.settings["check_ignore"] == {"main": ["screen"]}, app.settings.get("check_ignore"))
app.current_file = os.path.join(macros_dir, "Other.macro")
check("don't warn again: only for that macro", "screen" not in app.check_ignored())
app.current_file = main_path
# the Check list (built into a hidden frame: no window shows) has "Warn me again"
holder = tk.Frame(root)
real_play_on = app._read_play_on
app._read_play_on = lambda quiet=False: (1024, 768)
app._fill_check(holder, holder)
app._read_play_on = real_play_on
texts = []


def walk_widgets(w):
    for c in w.winfo_children():
        try:
            texts.append(c.cget("text"))
        except tk.TclError:
            pass
        walk_widgets(c)


def all_widgets(w):
    for c in w.winfo_children():
        yield c
        yield from all_widgets(c)


walk_widgets(holder)
check("Check list: shows the turned-off warning with Warn me again",
      "Warn me again" in texts and "Don't warn me again for this macro" in texts, texts)
app.set_check_ignored("screen", False)
check("warn me again: the setting is gone again", "check_ignore" not in app.settings
      or "main" not in app.settings["check_ignore"])
app.set_check_ignored("screen", True)
app.rename_check_ignored("main", "main 2")
check("rename keeps the turned-off warnings", app.settings["check_ignore"] == {"main 2": ["screen"]})
app.settings.pop("check_ignore")
app.macro_screen = None
app.set_steps([rec])
shown = app.check_on_play((1920, 1080))
check("on Play: nothing wrong clears the line", shown == [] and app.check_notice_see.cget("text") == "")
check("check_ignore isn't part of a profile", "check_ignore" in __import__("profiles_ui").SKIP_KEYS)

# Play itself never stops for these: a missing chained macro and a picture step without a picture
sent = []
app._replay_event = lambda e, hk, hb: sent.append(e)
app.settings.update(pause_when_away=False, results_enabled=False, drops_enabled=False)
app.away_var.set(False)
app.watch_var.set(False)
app.result_pictures = []
app.switch_prog_var.set(False)
wp2 = workflow.new_action("wait_picture")
wp2.pop("png", None)
app.set_steps([chain(os.path.join(macros_dir, "Gone.macro")), wp2, rec])
app.current_file = main_path
app.ready_var.set(0)
app.loop_var.set(False)
app.repeat_var.set(1)
box_calls.clear()
errors = []
core.messagebox.showerror = lambda *a, **k: errors.append(a)
modern_ui.messagebox.showerror = lambda *a, **k: errors.append(a)
app.play()
t0 = time.time()
while app.playing and time.time() - t0 < 10:
    pump(0.03)
check("Play: goes on with a missing macro and an empty picture step", not errors
      and [e["key"]["vk"] for e in sent if e.get("type") == "key" and e.get("pressed")] == [65], (errors, sent))
check("Play: the line says what to check", "to check" in app.profile_notice.cget("text"))

# ------------------------------------------------------------ 3. older versions of a macro
vfile = save_macro("Versioned", actions=[rec])
check("versions: none at first", macro_versions.versions(vfile) == [])
check("versions: a new file has nothing to keep", macro_versions.keep(os.path.join(macros_dir, "New.macro")) is None)
first = open(vfile, encoding="utf-8").read()
kept = macro_versions.keep(vfile)
check("versions: kept in the app's settings folder, not beside the macro",
      kept and kept.startswith(os.path.join(settings_dir, "macro_versions")) and
      sorted(os.listdir(macros_dir)) == sorted(set(os.listdir(macros_dir))) and
      not any("macro_versions" in f for f in os.listdir(macros_dir)), kept)
check("versions: the same again isn't kept twice", macro_versions.keep(vfile) is None
      and len(macro_versions.versions(vfile)) == 1)
base = datetime.datetime(2026, 11, 1, 12, 0, 0)
for n in range(12):
    with open(vfile, "w", encoding="utf-8") as f:
        f.write(first.replace('"version":1', f'"version":1,"n":{n}').replace('"version": 1', f'"version": 1, "n": {n}'))
    macro_versions.keep(vfile, now=base + datetime.timedelta(minutes=n))
vs = macro_versions.versions(vfile)
check("versions: at most 10 kept, newest first", len(vs) == 10 and vs[0][1] > vs[-1][1], len(vs))
# restore: the version now is kept first, so it can be undone
now_text = open(vfile, encoding="utf-8").read()
old_path, old_when = vs[-1]
old_text = open(old_path, encoding="utf-8").read()
macro_versions.restore(old_path, vfile)
check("restore: the older version is back", open(vfile, encoding="utf-8").read() == old_text)
check("restore: the version before the restore was kept (undo)",
      open(macro_versions.versions(vfile)[0][0], encoding="utf-8").read() == now_text)
# rename: the versions follow the name
renamed = os.path.join(macros_dir, "Versioned 2.macro")
count = len(macro_versions.versions(vfile))
macro_versions.renamed(vfile, renamed)
check("rename: the versions go along", len(macro_versions.versions(renamed)) == count
      and macro_versions.versions(vfile) == [])
check("versions: date words", macro_versions.when_text(datetime.datetime(2026, 11, 16, 9, 5, 0),
                                                      now=datetime.datetime(2026, 11, 16, 20, 0)) == "Today 09:05:00")
# Save… in the main window keeps the version it had
app.load(main_path, quiet=True)
modern_ui.filedialog.asksaveasfilename = lambda **k: main_path
before = len(macro_versions.versions(main_path))
app.save()
check("Save…: the version the file had is kept", len(macro_versions.versions(main_path)) == before + 1)

# ------------------------------------------------------------ 4. export stats
run_history.clear()
t_now = time.time()
run_history.add("Bloodawakening", "win", 312.4, 1, t=t_now - 86400)
run_history.add("=HYPERLINK(\"x\")", "loss", 40.0, 0, t=t_now)
run_history.note("reconnects")
out_csv = os.path.join(tmp, "stats.csv")
modern_ui.filedialog.asksaveasfilename = lambda **k: out_csv
box_calls.clear()
path = app.export_stats()
check("export: saved where chosen", path == out_csv and os.path.isfile(out_csv))
raw = open(out_csv, "rb").read()
check("export: starts with the mark Excel needs for UTF-8", raw.startswith(b"\xef\xbb\xbf"))
rows = list(csv.reader(open(out_csv, encoding="utf-8-sig", newline="")))
check("export: runs with date, time, macro, result, seconds, fragments",
      rows[1] == ["Date", "Time", "Macro", "Result", "Seconds", "Divine fragments"]
      and rows[2][2:] == ["Bloodawakening", "Won", "312.4", "1"], rows[:4])
check("export: a name that looks like a formula stays text", rows[3][2].startswith("'="), rows[3])
day_start = rows.index(["DAILY TOTALS"])
check("export: the daily totals", len(rows) - day_start - 2 == 2 and rows[-1][7] == "1", rows[day_start:])
text = raw.decode("utf-8-sig")
check("export: no paths or user names", tmp not in text and os.path.expanduser("~") not in text
      and os.environ.get("USERNAME", "zzz-nobody") not in text)
check("export: a box says it's done (stubbed)", box_calls and box_calls[-1][0] == "showinfo", box_calls)

# ------------------------------------------------------------ 5. open someone's stats file (only to look at)
friend = run_history.read_csv(out_csv)
check("open file: our own export reads back", len(friend.runs()) == 2 and friend.skipped == 0,
      (friend.runs(), friend.skipped))
check("open file: the ' before a formula-like name is taken off again",
      sorted(friend.macros()) == sorted(["Bloodawakening", '=HYPERLINK("x")']), friend.macros())
check("open file: results, seconds, fragments and day totals come back",
      any(r["status"] == "win" and r["s"] == 312.4 and r["f"] == 1 for r in friend.runs())
      and sum(d["reconnects"] for _dt, d in friend.days(14)) == 1)


def write(name, text):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return p


def refused(p):
    try:
        run_history.read_csv(p)
    except ValueError as exc:
        return str(exc)
    return None


check("open file: plain text isn't taken", refused(write("a.csv", "hello, world\n1,2,3\n")) == run_history.NOT_OURS)
check("open file: a macro file isn't taken", refused(write("b.csv", '{"app":"macro_recorder","events":[]}'))
      == run_history.NOT_OURS)
check("open file: an empty file isn't taken", refused(write("c.csv", "")) == run_history.NOT_OURS)
check("open file: a missing file says so", (refused(os.path.join(tmp, "nope.csv")) or "").startswith("The file couldn't"))
big = os.path.join(tmp, "big.csv")
with open(big, "wb") as f:
    f.write(b"RUNS\n")
    f.truncate(run_history.MAX_FILE_BYTES + 1)
check("open file: over 20 MB is refused before it's read", "too big" in (refused(big) or ""), refused(big))
head = "RUNS\nDate,Time,Macro,Result,Seconds,Divine fragments\n"
many = write("many.csv", head + "2026-11-01,10:00:00,M,Won,70,0\n" * (run_history.MAX_FILE_RUNS + 1))
check("open file: more than 50,000 runs is refused", "too many runs" in (refused(many) or ""), refused(many))
bad_lines = [
    "2026-13-40,10:00:00,M,Won,70,0",       # no such date
    "1850-01-01,10:00:00,M,Won,70,0",       # far too old
    "2026-11-01,25:00:00,M,Won,70,0",       # no such time
    "2026-11-01,10:00:00,M,Hacked,70,0",    # unknown result
    "2026-11-01,10:00:00,M,Won,nan,0",      # not a number
    "2026-11-01,10:00:00,M,Won,-5,0",       # below zero
    "2026-11-01,10:00:00,M,Won,1e99,0",     # gigantic
    "2026-11-01,10:00:00,M,Won,70,2.5",     # half a fragment
    "2026-11-01,10:00:00,M,Won,70,99999",   # too many fragments
    "2026-11-01",                            # cut short
]
good = ["2026-11-01,10:00:00,Good,Won,70,1", "2026-11-02,11:30:00,Good,Failed,20,0"]
mixed = write("mixed.csv", head + "\n".join(bad_lines + good) + "\n\nDAILY TOTALS\n"
              "Date,Runs,Won,Failed,Unknown,Seconds played,Divine fragments,Reconnects,Fastest win (s),"
              "Slowest win (s)\n2026-11-01,1,1,0,0,70,1,0,70,70\nnot-a-date,1,1,0,0,70,1,0,,\n"
              "2026-11-02,-1,0,0,0,0,0,0,,\n")
m = run_history.read_csv(mixed)
check("open file: bad lines are left out and counted", len(m.runs()) == 2 and m.skipped == len(bad_lines) + 2,
      (len(m.runs()), m.skipped))
check("open file: only sensible day totals are kept", list(m._days) == ["2026-11-01"], list(m._days))
tricky = write("tricky.csv", "RUNS\nExtra,Seconds,Result,Macro,Time,Date\n"
               + "x,70,won,\"Evil‮noisruc​\nname" + "A" * 500 + "\",10:00:00,2026-11-01\n"
               + "x,70,Won,'@SUM(1),10:00:00,2026-11-01\n")
t = run_history.read_csv(tricky)
names = t.macros()
check("open file: other column order and unknown columns are fine", len(t.runs()) == 2, t.runs())
check("open file: invisible and control characters are taken out, names at most 60 letters",
      all(len(n) <= 60 and "‮" not in n and "​" not in n and "\n" not in n for n in names), names)
check("open file: a formula stays plain text", "@SUM(1)" in names, names)
check("open file: an old file still shows its own last 14 days in the chart",
      t.days(14)[-1][0] == "2026-11-01")

# the Run stats window with the file
run_history.add("My own macro", "win", 65.0, 0)
mine_before = [dict(r) for r in run_history.runs()]
box_calls.clear()
win = app.open_stats_file(out_csv)
pump(0.2)
texts.clear()
walk_widgets(win)
check("viewer: says whose stats these are (file name only) and that anyone can change them",
      "Viewing: stats.csv" in texts and any(isinstance(x, str) and "anyone can change" in x for x in texts)
      and not any(isinstance(x, str) and tmp in x for x in texts), texts[:6])
check("viewer: Export… is off while looking at a file",
      any(isinstance(w, ttk.Button) and w.cget("text") == "Export…" and str(w.cget("state")) == "disabled"
          for w in all_widgets(win)))
check("viewer: shows everything in the file (not just the last 7 days)", win.vars["period"].get() == "Everything kept")
others = None
for w in all_widgets(win):
    if isinstance(w, ttk.Combobox) and str(w.cget("textvariable")) == str(win.vars["other"]):
        others = list(w.cget("values"))
check("viewer: Compare with lists the file's macros and, apart, my own", others and "Bloodawakening" in others
      and "Mine: My own macro" in others and others.index("Mine: My own macro") > others.index("Bloodawakening"),
      others)
win.vars["macro"].set("Bloodawakening")
win.vars["other"].set("Mine: My own macro")
win.show()
pump(0.1)
texts.clear()
walk_widgets(win)
check("viewer: their macro next to my own", "Bloodawakening" in texts and "Mine: My own macro" in texts
      and "5m 12s" in texts and "1m 05s" in texts, [x for x in texts if isinstance(x, str) and "m " in x][:8])
check("viewer: nothing is added to my own stats", [dict(r) for r in run_history.runs()] == mine_before)
win.view(run_history.MINE)
pump(0.1)
texts.clear()
walk_widgets(win)
check("Back to my stats: my own again, Export on", "Viewing: stats.csv" not in texts and any(
    isinstance(w, ttk.Button) and w.cget("text") == "Export…" and str(w.cget("state")) == "normal"
    for w in all_widgets(win)))
win.destroy()
box_calls.clear()
errors.clear()
said = app.open_stats_file(write("d.csv", "nope"))
shown = [str(a) for _n, a in box_calls] + [str(a) for a in errors]
check("viewer: a file that isn't ours gives a plain message (no window)",
      said is None and any(run_history.NOT_OURS in x and "d.csv" in x and tmp not in x for x in shown), shown)
opened = []
real_osf = app.open_stats_file
app.open_stats_file = lambda p, parent=None: opened.append(p)
app.open_path(out_csv)
app.open_stats_file = real_osf
check("dropped on the app: a .csv opens in Run stats", opened == [out_csv])

passed = sum(1 for _n, ok in results if ok)
print(f"\n{passed} of {len(results)} passed")
root.destroy()
sys.exit(0 if passed == len(results) else 1)
