"""How late each action is played (ms), with and without the screen checks running. No real input."""
import os
import statistics
import sys
import tempfile
import time

sys.path.insert(0, sys.argv[1])
tmp = tempfile.mkdtemp(prefix="mr_timing_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
if os.environ.get("MR_SPIN"):  # compare: MR_SPIN=0.002 plays like before 2.8 (2 ms of clock-watching)
    core.SPIN_SECONDS = float(os.environ["MR_SPIN"])
import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402

import image_watch  # noqa: E402
import modern_ui  # noqa: E402
import window_tools  # noqa: E402

root = tk.Tk()
root.withdraw()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
root.withdraw()
for name in ("showwarning", "showinfo", "showerror"):
    setattr(app.boxes, name, lambda *a, **k: None)
window_tools.foreground = lambda: None
app.settings["pause_when_away"] = False
app.away_var.set(False)
app.settings["discord_enabled"] = False
fired = []
start_clock = {}


def replay(ev, hk, hb):
    fired.append((ev["t"], app._play_clock()))


app._replay_event = replay
# a quick tap every 37 ms for 6 s
events = []
t = 0.0
while t < 6:
    events.append({"type": "key", "key": {"vk": 65}, "pressed": True, "t": round(t, 4)})
    events.append({"type": "key", "key": {"vk": 65}, "pressed": False, "t": round(t + 0.012, 4)})
    t += 0.037


def run(label, watch):
    fired.clear()
    app.watch_var.set(watch)
    app.settings["watch_enabled"] = watch
    app.settings["results_enabled"] = watch
    app.results_var.set(watch)
    app.watch_end_var.set(0)
    app.events = events
    app.ready_var.set(0)
    app.loop_var.set(False)
    app.repeat_var.set(1)
    app.play()
    cpu0 = time.process_time()
    t0 = time.time()
    while app.playing and time.time() - t0 < 30:
        root.update()
        time.sleep(0.01)
    cpu = 100 * (time.process_time() - cpu0) / max(1e-6, time.time() - t0)
    base = fired[0][1] - fired[0][0]
    late = [(c - base - want) * 1000 for want, c in fired]
    late.sort()
    holds = [(fired[i + 1][1] - fired[i][1]) * 1000 for i in range(0, len(fired) - 1, 2)]
    print(f"{label}: {len(fired)} actions, late ms median {statistics.median(late):.2f}, "
          f"95% {late[int(len(late) * .95)]:.2f}, max {late[-1]:.2f}; tap hold ms (want 12) "
          f"min {min(holds):.1f} median {statistics.median(holds):.1f} max {max(holds):.1f}; "
          f"CPU {cpu:.0f}% of one core")


root.update()
if not app.watch_pictures: app.add_builtin_picture()
print("watch pictures", len(app.watch_pictures), "result pictures", len(app.result_pictures))
run("no screen checks", False)
if image_watch is not None:
    run("picture watch + results", True)
root.destroy()
