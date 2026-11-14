"""Tests for mission results, the Discord card, video keys and AutoHotkey. No real input, no windows,
a throwaway settings folder."""
import http.server
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, sys.argv[1])
tmp = tempfile.mkdtemp(prefix="mr_res_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402

import image_watch  # noqa: E402
import importers  # noqa: E402
import modern_ui  # noqa: E402
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
check("built-in MISSION COMPLETED and MISSION FAILED pictures added on first start",
      sorted(p["kind"] for p in app.result_pictures) == ["loss", "win"])
sent = []
app._replay_event = lambda e, hk, hb: sent.append(e)
for name in ("showwarning", "showinfo", "showerror"):
    setattr(app.boxes, name, lambda *a, **k: None)
window_tools.foreground = lambda: None
app.settings["pause_when_away"] = False
app.away_var.set(False)
app.watch_var.set(False)
app.settings["watch_enabled"] = False


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def run_play(events, repeats=1, limit=20):
    sent.clear()
    app.events = events
    app.ready_var.set(0)
    app.loop_var.set(False)
    app.repeat_var.set(repeats)
    app.play()
    t0 = time.time()
    while app.playing and time.time() - t0 < limit:
        pump(0.05)
    return time.time() - t0


# fake screen: the result banner appears during run 1 only, the "failed" one during run 2
win_pic = np.zeros((40, 200, 3), np.uint8)
win_pic[8:32, 10:190] = (60, 200, 250)
for x in range(20, 180, 18):
    win_pic[12:28, x:x + 8] = 255
loss_pic = np.zeros((40, 200, 3), np.uint8)
loss_pic[8:32, 10:190] = (40, 40, 220)
for y in range(10, 30, 6):
    loss_pic[y:y + 3, 15:185] = 255
loss_pic[10:30, 95:100] = 255
blank = np.full((app.screen_h, app.screen_w, 3), 25, np.uint8)
with_win = blank.copy()
with_win[400:440, 600:800] = win_pic
with_loss = blank.copy()
with_loss[400:440, 600:800] = loss_pic
app.result_pictures = [{"img": win_pic, "file": "w.png", "screen_h": app.screen_h, "kind": "win"},
                       {"img": loss_pic, "file": "l.png", "screen_h": app.screen_h, "kind": "loss"}]
phase = {"run_starts": []}
orig_finish = app._finish_run


def screen_now(sct=None, region=None):
    if not phase["run_starts"]:
        return blank
    n = len(phase["run_starts"])
    since = time.time() - phase["run_starts"][-1]
    if since < 0.8:
        return blank
    return {1: with_win, 2: with_loss}.get(n, blank)


image_watch.grab_screen = screen_now
orig_set_note = app._set_note


def note(text):
    if text.startswith("Playing run"):
        phase["run_starts"].append(time.time())
    orig_set_note(text)


app._set_note = note
evs = [{"type": "key", "key": {"vk": 65}, "pressed": True, "t": 0.0},
       {"type": "key", "key": {"vk": 65}, "pressed": False, "t": 2.4}]
cards = []
app.settings.update(discord_enabled=True, discord_runs=True, discord_screenshot=False,
                    discord_webhook="https://discord.com/api/webhooks/1/" + "x" * 60, discord_ping="<@42>",
                    discord_ping_when="problems")
app.notifier.send = lambda content, png=None, embed=None, username=None: cards.append((content, embed, username))
app.discord_var.set(True)
app.discord_runs_var.set(True)
app.discord_shot_var.set(False)
app.discord_ping_var.set("<@42>")
app.discord_stop_var.set(True)
took = run_play(evs, repeats=3)
statuses = [st for st, _ in app.session.runs]
check("results: run 1 won, run 2 lost, run 3 unknown", statuses == ["win", "loss", "unknown"], statuses)
v = app.session.values()
check("results: completed/failed counts", (v["completed"], v["failed"]) == ("1/3", "1/3"), v)
check("results: win rate of decided runs", v["winrate"] == "50.00%", v["winrate"])
run_cards = [c for c in cards if "Run #" in (c[1] or {}).get("title", "")]
check("discord: one card per run", len(run_cards) == 3, len(run_cards))
check("discord: card text filled in", run_cards and "Victory" in run_cards[0][1]["description"]
      and "{" not in run_cards[0][1]["description"], run_cards[0][1]["description"][:80] if run_cards else "")
check("discord: ping only on the lost run", [c[0] for c in run_cards] == ["", "<@42>", ""], [c[0] for c in run_cards])
check("discord: win green, loss red", [c[1]["color"] for c in run_cards][:2] == [0x2ECC71, 0xFF4757])
check("discord: summary when it stops", any("Session ended" in (c[1] or {}).get("title", "") for c in cards))
check("all-time results saved", app.settings.get("stats_all", {}).get("runs") == 3, app.settings.get("stats_all"))

# custom message text with placeholders
app.settings["discord_title"] = "{macro} #{run}"
app.settings["discord_message"] = "𝐒𝐭𝐚𝐭𝐮𝐬 {status} {completed}"
content, card = app._run_card("win", app.session.values(""))
check("discord: own text and title", card["title"].endswith("#3") and card["description"].endswith("1/3"), card)

# ping when a divine fragment drops (also when Ping says Never, and with "After each run" off)
app.settings.update(discord_ping_when="never", discord_runs=False, discord_ping_fragments=True)
cards.clear()
app.session.add("win", 100, 0)
app._run_finished(4, "done")
check("fragment ping: no drop, no card (After each run off)", cards == [], cards)
app.session.add("win", 100, 2)
app._run_finished(5, "done")
check("fragment ping: a drop sends the card with the ping", len(cards) == 1 and cards[0][0] == "<@42>",
      [c[0] for c in cards])
app.settings.update(discord_ping_fragments=False, discord_runs=True)
cards.clear()
app.session.add("win", 100, 1)
app._run_finished(6, "done")
check("fragment ping off: card without ping", len(cards) == 1 and cards[0][0] == "", [c[0] for c in cards])
app.settings.update(discord_ping_when="problems")

# a real HTTP post with an embed and a picture
got = []


class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers["Content-Length"])
        got.append((self.headers["Content-Type"], self.rfile.read(n)))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


import discord_notify  # noqa: E402

srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
discord_notify.post(f"http://127.0.0.1:{srv.server_port}/x", "<@42>", b"\x89PNGfake",
                    embed={"title": "T", "description": "D", "color": 5}, username="Bot")
body = got[0][1]
payload = json.loads(body.split(b"\r\n\r\n", 1)[1].split(b"\r\n--", 1)[0])
check("discord post: embed with the picture inside", payload["embeds"][0]["image"]["url"] == "attachment://screen.png")
check("discord post: name and pings allowed", payload["username"] == "Bot" and "users" in payload["allowed_mentions"]["parse"])
srv.shutdown()

# screenshot of a chosen program falls back to the main screen when it isn't open
window_tools.windows_of = lambda exe: []
png = discord_notify.screenshot_png("program:Nope.exe")
check("screenshot: missing program falls back", png and png[:2] == b"\xff\xd8")

# video keys
app.video_live = True
cmds = []
app.video.command = lambda name, value=0: cmds.append((name, value))
app.video.is_open = lambda: True
from pynput import keyboard  # noqa: E402

k = keyboard.KeyCode.from_vk(102)
check("video key: Num 6 is Forward", app._video_key_action(k) == "forward")
app.video_key("forward")
app.video_key("vol_down")
check("video key: commands sent", cmds[:2] == [("seek", 10), ("volume", -10)], cmds)
app.settings["video_history"] = ["https://www.youtube.com/watch?v=aaaaaaaaaaa", "https://youtu.be/bbbbbbbbbbb?t=30"]
app.settings["video_link"] = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
app.video_key("next")
check("video key: next video loads the next link", cmds[-1][0] == "load" and cmds[-1][1]["video"] == "bbbbbbbbbbb"
      and cmds[-1][1]["start"] == 30, cmds[-1])
n = len(app.events)
app.recording, app.paused = True, False
app._on_key_press(k)
check("video key: not recorded", len(app.events) == n)
app.recording = False
app.video_live = False
check("video key: off when the window is closed", app._video_key_action(k) is None)

# AutoHotkey: variables, loops, export and back
src = os.path.join(tmp, "a.ahk")
open(src, "w").write('d := 100\nLoop 3 {\n  Send "{Blind}x"\n  Sleep d * 2\n}\nClick 50, 60\n')
r = importers.import_file(src)
keys = [e for e in r.events if e["type"] == "key"]
check("ahk: loop with variable sleep", len(keys) == 6 and r.events[-1]["type"] == "click", (len(keys), r.skipped))
out = importers.export_ahk(r.events, "t")
open(src, "w", encoding="utf-8").write(out)
r2 = importers.import_file(src)
check("ahk: exported script reads back", [e["type"] for e in r2.events] == [e["type"] for e in r.events]
      or len(r2.events) >= len(r.events), (len(r.events), len(r2.events)))
bad = os.path.join(tmp, "b.ahk")
open(bad, "w").write("x := 9**9**9\nSleep x\nSend a\n")
t0 = time.time()
importers.import_file(bad)
check("ahk: no huge sums", time.time() - t0 < 2)

print()
print(f"{sum(ok for _, ok in results)} of {len(results)} passed")
root.destroy()
