"""Run history and stats, stop by itself, small random timing, Discord summaries.
No real input is sent, throwaway settings folder."""
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

import modern_ui  # noqa: E402
import run_history  # noqa: E402
import window_tools  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


# ---- run history (pure)
day1 = time.mktime((2026, 11, 14, 12, 0, 0, 0, 0, -1))
day2 = day1 + 86400
for i, (status, secs, frags) in enumerate([("win", 100, 0), ("win", 110, 1), ("loss", 40, 0), ("win", 300, 0)]):
    run_history.add("Farm", status, secs, frags, t=day1 + i * 400)
run_history.add("Other", "unknown", 50, 0, t=day2)
run_history.note("reconnects", t=day2)
s = run_history.summary(run_history.runs("Farm"))
check("history: counts", (s["runs"], s["wins"], s["losses"], s["unknown"]) == (4, 3, 1, 0), s)
check("history: win rate 75%", abs(s["winrate"] - 75.0) < 0.01, s["winrate"])
check("history: best and longest won run", (s["best"], s["worst"]) == (100, 300), s)
check("history: one unusually slow run (300 s against a usual 110)", s["slow"] == 1 and s["usual"] == 110, s)
check("history: fragments an hour", abs(s["fragments_per_hour"] - 3600 / 550) < 0.01, s["fragments_per_hour"])
check("history: macros, newest first", run_history.macros() == ["Other", "Farm"], run_history.macros())
days = run_history.days(2, end=day2)
check("history: days", [d["runs"] for _date, d in days] == [4, 1] and days[1][1]["reconnects"] == 1, days)
check("history: record day", run_history.records()["runs"] == ("2026-11-14", 4), run_history.records())
run_history.save()
with open(os.path.join(tmp, "run_history.json"), encoding="utf-8") as f:
    check("history: saved to its file", len(json.load(f)["runs"]) == 5)
png = run_history.chart_png(days, "test")
check("history: chart picture is a PNG", png and png[:4] == b"\x89PNG", type(png))

# ---- the app
root = tk.Tk()
root.withdraw()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
root.withdraw()
sent = []
app._replay_event = lambda e, hk, hb: sent.append((time.perf_counter(), e))
app.root.after = (lambda real: (lambda ms, fn=None, *a: real(ms, fn, *a) if fn else real(ms)))(app.root.after)
modern_ui.messagebox.showwarning = lambda *a, **k: None
boxes = []  # (a real box would wait for a click that never comes)
app.boxes.showinfo = lambda *a, **k: boxes.append(a)
window_tools.foreground = lambda: None
app.settings.update(pause_when_away=False, watch_enabled=False)
app.away_var.set(False)
app.watch_var.set(False)
app.result_pictures = []
power = []
app._power_action = lambda then: power.append(then)
cards = []
app._send_card = lambda content, card, png: cards.append((card, png))


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def key(vk, t, pressed=True):
    return {"type": "key", "key": {"vk": vk}, "pressed": pressed, "t": t}


def run_play(events, **kw):
    sent.clear()
    app.actions = None
    app.events = events
    app.ready_var.set(0)
    app.loop_var.set(kw.get("loop", False))
    app.repeat_var.set(kw.get("repeats", 1))
    app.play()
    t0 = time.time()
    while app.playing and time.time() - t0 < kw.get("limit", 15):
        pump(0.03)
    pump(0.1)
    return time.time() - t0


tap = [key(65, 0.0), key(65, 0.05, False)]

# stop by itself after 3 runs, then close the game
app.settings["auto_stop"] = {"on": True, "runs": 3, "then": "close"}
before = len(run_history.runs())
run_play(tap, loop=True)
check("auto stop: stopped after 3 runs", app.runs_done == 3 and app.auto_stopped == "3 runs were played",
      (app.runs_done, app.auto_stopped))
check("auto stop: no problem reported", app.stop_reason is None, app.stop_reason)
check("auto stop: then closed the game", power == ["close"], power)
check("history: the 3 runs were kept", len(run_history.runs()) == before + 3, len(run_history.runs()))
check("auto stop: summary text", app.auto_stop_summary() == "After 3 runs, then close the game",
      app.auto_stop_summary())

# after some minutes, in the middle of a run
power.clear()
app.settings["auto_stop"] = {"on": True, "minutes": 0.01, "finish_run": False, "then": "nothing"}
took = run_play([key(65, 0.0), key(65, 5.0, False)], loop=True)
check("auto stop: timed stop in the middle of a run", took < 3 and app.auto_stopped and "time" in app.auto_stopped,
      (took, app.auto_stopped))
# ... or after the run that's playing
app.settings["auto_stop"] = {"on": True, "minutes": 0.005, "finish_run": True}
took = run_play([key(65, 0.0), key(65, 1.2, False)], loop=True)
check("auto stop: timed stop waits for the run to finish", app.runs_done == 1 and took > 1.2, (app.runs_done, took))
# cancelled (as /keepgoing does)
app.settings["auto_stop"] = {"on": True, "runs": 1}
app.root.after(100, app.cancel_auto_stop)
run_play([key(65, 0.0), key(65, 0.4, False)], repeats=3)
check("auto stop: cancelled, so all 3 runs played", app.runs_done == 3 and not app.auto_stopped,
      (app.runs_done, app.auto_stopped))
# off
app.settings["auto_stop"] = {"on": False, "runs": 1}
run_play(tap, repeats=2)
check("auto stop: off does nothing", app.runs_done == 2, app.runs_done)
app.settings.pop("auto_stop")
check("auto stop: at a time of day gives a deadline within a day",
      (lambda a: a and 0 < a["deadline"] - time.time() <= 86400)(
          (app.settings.__setitem__("auto_stop", {"on": True, "at": "03:30"}), app._prepare_auto_stop())[1]))
app.settings.pop("auto_stop")

# ---- small random timing
clicks = [{"type": "click", "x": 500, "y": 500, "button": "left", "pressed": p, "t": 0.1 * i}
          for i, p in enumerate([True, False] * 10)]
run_play(clicks)
exact = [(e["x"], e["y"]) for _t, e in sent]
check("random timing: off by default, clicks land exactly", set(exact) == {(500, 500)}, set(exact))
app.settings["vary"] = {"on": True, "ms": 30, "px": 4}
run_play(clicks)
spots = [(e["x"], e["y"]) for _t, e in sent]
times = [t for t, _e in sent]
check("random timing: clicks land near, not always on, the spot",
      len(set(spots)) > 1 and all(abs(x - 500) <= 4 and abs(y - 500) <= 4 for x, y in spots), set(spots))
check("random timing: a release lands where its press did",
      all(spots[i] == spots[i + 1] for i in range(0, len(spots), 2)), spots)
check("random timing: still in order, and all 20 played",
      len(sent) == 20 and times == sorted(times) and [e["pressed"] for _t, e in sent] == [True, False] * 10)
gaps = [round((times[i + 1] - times[i]) * 1000) for i in range(len(times) - 1)]
check("random timing: the waits differ a little (100 ms each when exact)", len(set(gaps)) > 3
      and all(30 <= g <= 175 for g in gaps), gaps)
app.macro_vary = {"mode": "off"}
check("random timing: a macro can turn it off for itself", app._vary_now() is None)
app.macro_vary = {"mode": "own", "ms": 5, "px": 0}
check("random timing: or have its own amounts", app._vary_now() == {"ms": 5, "px": 0}, app._vary_now())
app.macro_vary = None
app.settings.pop("vary")
check("random timing: summary", app.vary_summary() == "Off", app.vary_summary())

# ---- Discord summaries
app.settings["discord_enabled"] = True
made = app.summary_card("daily", now=day1 + 3600)
check("summary: daily card has the day's numbers", made and "**Runs** 4" in made[0]["description"]
      and "75.0%" in made[0]["description"] and made[1] is None, made and made[0]["description"])
made = app.summary_card("weekly", now=day2 + 3600)
check("summary: weekly card has a chart and the record day",
      made and made[1] and made[1][:4] == b"\x89PNG" and "Record day" in made[0]["description"],
      made and made[0]["description"])
check("summary: a day with no runs sends nothing", app.summary_card("daily", now=day1 - 5 * 86400) is None)
cards.clear()
app.settings["discord_summary"] = {"daily": True, "at": "00:00", "weekly": False}
app.root.after = lambda *a, **k: None  # (the next tick isn't wanted here)
app._summary_tick()
app._summary_tick()
check("summary: sent once when its time has come, not again the same day",
      len(cards) == 1 and "Today's summary" in cards[0][0]["title"], [c[0]["title"] for c in cards])

# ---- the Stats numbers (as the window shows them)
lines = dict(app.stats_lines(app.stats_numbers("Farm", "all")))
check("stats: lines for one macro", lines["Runs"] == "4" and lines["Win rate"] == "75.0%"
      and lines["Best run"] == "1m 40s" and lines["Unusually slow runs"] == "1", lines)

# ---- the windows open, and Save keeps what was chosen
app.root.after = root.after
app.open_settings()
pump(0.3)
win = app.open_auto_stop()
win.variables["on"].set(True)
win.variables["runs"].set("25")
win.variables["at"].set("soon")
win.save()
pump(0.1)
check("windows: a wrong time is refused, the window stays", win.winfo_exists() and "auto_stop" not in app.settings
      and len(boxes) == 1, boxes)
win.variables["at"].set("3:30")
win.save()
pump(0.1)
check("windows: stop by itself saved", app._auto_stop_settings()["runs"] == 25
      and app._auto_stop_settings()["at"] == "03:30" and app.auto_stop_summary() == "After 25 runs or at 03:30",
      (app.settings.get("auto_stop"), app.auto_stop_summary()))
win = app.open_vary()
win.variables["on"].set(True)
win.variables["ms"].set("15")
win.variables["mode"].set("Never for this macro")
win.save()
pump(0.1)
check("windows: random timing saved, with the macro's own choice",
      app.settings["vary"] == {"on": True, "ms": 15, "px": 3} and app.macro_vary == {"mode": "off"},
      (app.settings.get("vary"), app.macro_vary))
win = app.open_summary_options()
win.variables["weekly"].set(True)
win.variables["weekday"].set("Friday")
win.save()
pump(0.1)
check("windows: summary options saved", app._summary_settings()["weekly"]
      and app._summary_settings()["weekday"] == "Friday" and "Friday" in app.summary_summary(), app.summary_summary())
win = app.open_stats()
pump(0.2)
win.vars["macro"].set("Farm")
win.vars["other"].set("Other")
win.vars["period"].set("Everything kept")
win.show()
pump(0.1)
check("windows: the Stats window shows a macro next to another", win.winfo_exists())
win.destroy()
app.close_settings()

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} passed")
root.destroy()
sys.exit(1 if failed else 0)
