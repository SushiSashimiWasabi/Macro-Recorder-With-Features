"""Logic tests for the new features. No real mouse/keyboard input is sent, no window is shown,
and the app uses a throwaway settings folder."""
import base64
import http.server
import json
import os
import sys
import tempfile
import threading
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_test_")

import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402

import diag  # noqa: E402
import discord_notify  # noqa: E402
import image_watch  # noqa: E402
import modern_ui  # noqa: E402
import window_tools  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


# ---- pure functions
ev = [{"type": "click", "x": 960, "y": 540, "t": 0}, {"type": "move_rel", "dx": 5, "dy": 0, "t": 0.1}]
out = core.scale_events_rect(ev, (0, 0, 1920, 1080), (100, 50, 1280, 720))
check("fit to window: centre stays centre", (out[0]["x"], out[0]["y"]) == (740, 410), out[0])
check("fit to window: camera untouched", out[1] == ev[1])
out = core.scale_events_rect([{"type": "click", "x": 0, "y": 0, "t": 0}], (0, 0, 1920, 1080), (0, 0, 2560, 1440))
check("fit to window: corner scales", (out[0]["x"], out[0]["y"]) == (0, 0), out[0])

# ---- the app, with its input listeners stopped at once (so nothing real is recorded)
root = tk.Tk()
root.withdraw()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
root.withdraw()
sent = []
app._replay_event = lambda e, hk, hb: sent.append(e)
app._click_at = lambda x, y: sent.append({"type": "clicked_at", "x": x, "y": y})
app._free_shift_lock = lambda: True
app.root.after = (lambda real: (lambda ms, fn=None, *a: real(ms, fn, *a) if fn else real(ms)))(app.root.after)


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def run_play(events, **kw):
    sent.clear()
    app.events = events
    app.ready_var.set(0)
    app.loop_var.set(kw.get("loop", False))
    app.repeat_var.set(kw.get("repeats", 1))
    app.play()
    t0 = time.time()
    while app.playing and time.time() - t0 < kw.get("limit", 15):
        pump(0.05)
    return time.time() - t0


# away pause: the game (window 111) leaves the front for 1 s in the middle of a 1.2 s macro
app.settings["watch_enabled"] = False
app.watch_var.set(False)
app.settings["pause_when_away"] = True
app.macro_program = None
fg = {"now": 111}
window_tools.foreground = lambda: fg["now"]
window_tools.pid_of = lambda h: 1 if h in (111, 222) else os.getpid()
window_tools.exe_of = lambda h: {111: "Game.exe", 222: "Other.exe"}.get(h)
window_tools.windows_of = lambda exe: [111] if exe == "Game.exe" else []
events = [{"type": "key", "key": {"vk": 65}, "pressed": True, "t": 0.0},
          {"type": "key", "key": {"vk": 65}, "pressed": False, "t": 1.2}]


def away_later():
    time.sleep(0.3)
    fg["now"] = 222
    time.sleep(1.5)
    fg["now"] = 111


threading.Thread(target=away_later, daemon=True).start()
took = run_play(events)
check("away pause: playback waited for the game", took > 2.4, f"{took:.2f} s")
check("away pause: both key events still sent", len(sent) == 2, sent)
check("away pause: no stop reason", app.stop_reason is None, app.stop_reason)

# away limit: game never comes back -> stops after 1 s
app.settings["away_stop_seconds"] = 1
app.away_stop_var.set(1)
fg["now"] = 111


def away_forever():
    time.sleep(0.2)
    fg["now"] = 222


threading.Thread(target=away_forever, daemon=True).start()
modern_ui.messagebox.showwarning = lambda *a, **k: None
took = run_play(events)
check("away limit: stopped with a reason", app.stop_reason and "wasn't in front" in app.stop_reason,
      app.stop_reason)
check("away limit: key released (only press sent)", len(sent) == 1, sent)
app.settings["away_stop_seconds"] = 0
app.away_stop_var.set(0)
fg["now"] = 111

# runaway limit: a picture "seen" every run
app.settings["pause_when_away"] = False
app.away_var.set(False)
app.watch_pictures = [{"img": np.zeros((20, 40, 3), np.uint8), "file": "x.png", "screen_h": 1080}]
app.watch_var.set(True)
app.settings.update(watch_enabled=True, watch_wait=0, watch_click=True, watch_end_wait=0,
                    watch_limit_count=3, watch_limit_seconds=60)
app.watch_wait_var.set(0)
app.watch_click_var.set(True)
app.watch_end_var.set(0)
app.watch_limit_var.set(3)
app._save_settings()


def fake_watch(watch, seen, done):
    while not done.is_set():
        if not seen.is_set():
            watch["seen_at"] = (5, 5)
            seen.set()
        time.sleep(0.05)


app._watch_worker = fake_watch
long_events = [{"type": "key", "key": {"vk": 65}, "pressed": True, "t": 0.0},
               {"type": "key", "key": {"vk": 65}, "pressed": False, "t": 0.3}]
runs = []
app._run_finished = lambda c, how: runs.append((c, how))
took = run_play(long_events, loop=True, limit=20)
check("runaway limit: stopped by the safety limit", app.stop_reason and "times" in app.stop_reason,
      app.stop_reason)
check("runaway limit: 4 runs reported", len(runs) == 4, runs)
check("runaway limit: clicked the picture", any(e.get("type") == "clicked_at" for e in sent))

# wait for a picture step: the picture appears on the (fake) screen after 0.6 s
app.watch_var.set(False)
app.settings["watch_enabled"] = False
pic = np.zeros((30, 60, 3), np.uint8)
pic[5:25, 5:55] = (40, 200, 240)
pic[12:18, 10:50] = (255, 255, 255)
screen_blank = np.full((1080, 1920, 3), 30, np.uint8)
screen_with = screen_blank.copy()
screen_with[500:530, 900:960] = pic
shown = {"at": time.time() + 0.6}
image_watch.grab_screen = lambda sct=None, region=None: screen_with if time.time() > shown["at"] else screen_blank
step = {"type": "wait_picture", "png": image_watch.png_data(pic), "screen_h": app.screen_h, "timeout": 5, "match": 85,
        "click": True, "name": "test", "otherwise": "go on", "t": 0.1}
evs = [{"type": "key", "key": {"vk": 65}, "pressed": True, "t": 0.0}, step,
       {"type": "key", "key": {"vk": 65}, "pressed": False, "t": 0.2}]
shown["at"] = time.time() + 0.8
took = run_play(evs)
clicked = [e for e in sent if e.get("type") == "clicked_at"]
check("wait step: waited for the picture", took > 0.8, f"{took:.2f}")
check("wait step: clicked its middle", clicked and abs(clicked[0]["x"] - 930) <= 3 and abs(clicked[0]["y"] - 515) <= 3,
      clicked)
check("wait step: the rest played after", sent and sent[-1].get("pressed") is False)
shown["at"] = time.time() + 100
step2 = dict(step, timeout=0.5, otherwise="stop")
took = run_play([evs[0], step2, evs[2]])
check("wait step: stop when it doesn't show", app.stop_reason and "didn't show" in app.stop_reason, app.stop_reason)

# save / open: program and pictures inside the macro
app.events = [{"type": "click", "x": 10, "y": 10, "button": "left", "pressed": True, "t": 0.0}]
app.macro_program = {"exe": "Game.exe", "title": "Game", "client": [0, 0, 1920, 1080]}
app.watch_pictures = [{"img": pic.copy(), "file": "p.png", "screen_h": 1080}]
app.settings["watch_save_with_macro"] = True
path = os.path.join(tmp, "t.macro")
modern_ui.filedialog.asksaveasfilename = lambda **k: path
app.save()
data = json.load(open(path, encoding="utf-8"))
check("save: program kept", data.get("program", {}).get("exe") == "Game.exe")
check("save: watch picture inside", len(data.get("watch_pictures", [])) == 1)
app.watch_pictures = []
app.macro_program = None
asked = []
modern_ui.messagebox.askyesno = lambda *a, **k: asked.append(a) or True
modern_ui.messagebox.showinfo = lambda *a, **k: None
core.messagebox.showinfo = lambda *a, **k: None
app._add_watch_picture = lambda img, screen_h=None: app.watch_pictures.append(
    {"img": img, "file": "n.png", "screen_h": screen_h})
app.load(path, quiet=True)
pump(0.3)
check("open: program read back", (app.macro_program or {}).get("exe") == "Game.exe")
check("open: offered and added the picture", len(app.watch_pictures) == 1 and len(asked) == 1)
app.load(path, quiet=True)
pump(0.3)
check("open again: not offered twice", len(asked) == 1)

# fit to window during play
app.settings["fit_to"] = "window"
app.fit_var.set(modern_ui.FIT_TO["window"])
window_tools.client_rect = lambda h: (100, 50, 1280, 720) if h == 111 else None
evs = app._events_for_play((1920, 1080))[0]["events"]  # (the macro's one recorded step)
check("fit to window: used the game's window", evs[0]["x"] == round(100 + 640 + (10 - 960) * (720 / 1080)), evs[0])
app.settings["fit_to"] = "screen"

# camera: raw moves become move_rel only while the pointer is hidden
app.events = []
app.recording, app.paused = True, False
app.start_time = time.perf_counter()
app.raw_mouse = object()
hidden = {"v": True}
app.hidden_cache = (0.0, True)
window_tools.cursor_hidden = lambda: hidden["v"]
for _ in range(20):
    app._on_raw_move(2, -1)
    time.sleep(0.001)
app._flush_camera()
rel = [e for e in app.events if e["type"] == "move_rel"]
check("camera: movement recorded", sum(e["dx"] for e in rel) == 40 and sum(e["dy"] for e in rel) == -20,
      (len(rel), sum(e["dx"] for e in rel)))
check("camera: grouped into few steps", 1 <= len(rel) <= 12, len(rel))
app.settings["record_mouse_moves"] = True
n = len(app.events)
app._on_move(5, 5)
check("camera: no position recorded while hidden", len(app.events) == n)
hidden["v"] = False
app.hidden_cache = (0.0, False)
app.last_move = 0
app._on_move(5, 5)
check("camera: positions recorded when the pointer shows", len(app.events) == n + 1)
app._on_raw_move(9, 9)
app._flush_camera()
check("camera: no camera step while the pointer shows", app.events[-1]["type"] == "move")
app.raw_mouse = None
app.recording = False

# report has no webhook link and no home folder
app.settings["discord_webhook"] = "https://discord.com/api/webhooks/123/SECRETSECRETSECRETSECRETSECRETSECRETSECRET"
diag.info("a line with " + os.path.expanduser("~"))
text = diag.report("t", app.settings, (1920, 1080))
check("report: no webhook", "SECRET" not in text)
check("report: no user folder", os.path.expanduser("~") not in text)

# Discord: messages and a screenshot reach a (local, fake) webhook
got = []


class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers["Content-Length"])
        got.append((self.headers["Content-Type"], self.rfile.read(n)))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_port}/api/webhooks/1/x"
discord_notify.post(url, "hello")
image_watch.grab_screen = lambda sct=None, region=None: screen_blank
discord_notify.post(url, "with picture", discord_notify.screenshot_png())
check("discord: plain message", got and got[0][0] == "application/json" and b"hello" in got[0][1])
check("discord: screenshot attached", len(got) > 1 and got[1][0].startswith("multipart/") and b"\xff\xd8" in got[1][1])
srv.shutdown()

print()
print(f"{sum(ok for _, ok in results)} of {len(results)} passed")
root.destroy()
