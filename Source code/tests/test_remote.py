"""The phone remote (Discord bot): the connection against a pretend Discord on this PC, and the
commands against the real window (kept hidden). Nothing is sent to Discord and no input is sent
to other programs: playing is replaced by a stand-in."""
import base64
import hashlib
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time

src = sys.argv[1]
sys.path.insert(0, src)
tmp = tempfile.mkdtemp(prefix="mr_remote_")
import macro_recorder as core  # noqa: E402

core.settings_path = lambda: os.path.join(tmp, "settings.json")
import tkinter as tk  # noqa: E402

import discord_remote as R  # noqa: E402
import modern_ui  # noqa: E402

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))


# ---------------------------------------------------------------- small things

TOKEN = base64.urlsafe_b64encode(b"123456789012345678").decode().rstrip("=") + ".Gabcde." + "x" * 38
check("a token's shape is recognised", R.looks_like_token(TOKEN) and not R.looks_like_token("hello")
      and not R.looks_like_token("https://discord.com/api/webhooks/1/abc"))
check("the bot's ID is read from its token", R.app_id_from_token(TOKEN) == "123456789012345678")
check("the invite link asks for commands and no permissions",
      "client_id=123456789012345678" in R.invite_link("123456789012345678")
      and "applications.commands" in R.invite_link(1) and "permissions=0" in R.invite_link(1))


# ---------------------------------------------------------------- a pretend Discord gateway

class FakeGateway:
    """Speaks just enough websocket: says hello, notes what the app sends, sends what the test asks."""

    def __init__(self):
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(5)
        self.port = self.server.getsockname()[1]
        self.got = []       # every message from the app, in order
        self.conns = []
        self.plan = []      # per connection: function(conn, self) run after hello
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        try:
            head = b""
            while b"\r\n\r\n" not in head:
                head += conn.recv(4096)
            key = [ln.split(":", 1)[1].strip() for ln in head.decode().split("\r\n")
                   if ln.lower().startswith("sec-websocket-key")][0]
            accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
            conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                         b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n")
            self.conns.append(conn)
            self.send(conn, {"op": 10, "d": {"heartbeat_interval": 300}})
            while True:
                msg = self.read(conn)
                if msg is None:
                    return
                self.got.append(msg)
                if msg["op"] == 1:
                    self.send(conn, {"op": 11})
                elif msg["op"] in (2, 6) and self.plan:
                    threading.Thread(target=self.plan.pop(0), args=(conn, msg), daemon=True).start()
        except OSError:
            pass

    @staticmethod
    def _exact(conn, n):
        data = b""
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                raise OSError("gone")
            data += chunk
        return data

    def read(self, conn):
        b1, b2 = self._exact(conn, 2)
        n = b2 & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._exact(conn, 2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._exact(conn, 8))[0]
        mask = self._exact(conn, 4)
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(self._exact(conn, n)))
        if b1 & 0x0F == 8:
            return None
        return json.loads(data)

    @staticmethod
    def send(conn, data, split=False):
        raw = json.dumps(data).encode()
        frames = [(1, raw, True)] if not split else [(1, raw[:5], False), (0, raw[5:], True)]
        for op, part, fin in frames:
            n = len(part)
            head = bytes([(0x80 if fin else 0) | op])
            head += bytes([n]) if n < 126 else (bytes([126]) + struct.pack(">H", n) if n < 65536
                                                 else bytes([127]) + struct.pack(">Q", n))
            conn.sendall(head + part)

    @staticmethod
    def close(conn, code):
        conn.sendall(bytes([0x88, 2]) + struct.pack(">H", code))


def wait_for(cond, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


gw = FakeGateway()
status = []
handled = []
registered = []
api_calls = []
real_api = R.api
R.api = lambda method, url, payload=None, token=None, picture=None, timeout=15: api_calls.append(
    (method, url, payload, token, picture))

READY = {"op": 0, "t": "READY", "s": 1, "d": {
    "session_id": "sess1", "resume_gateway_url": f"ws://127.0.0.1:{gw.port}",
    "application": {"id": "42"}, "user": {"username": "MacroBot"}, "guilds": [{"id": "1"}]}}


def first_login(conn, msg):
    gw.send(conn, READY)
    gw.send(conn, {"op": 0, "t": "INTERACTION_CREATE", "s": 2, "d": {"id": "i1", "token": "t1", "type": 2,
                                                                        "data": {"name": "status"}}}, split=True)
    big = {"op": 0, "t": "INTERACTION_CREATE", "s": 3, "d": {"id": "i2", "token": "t2", "type": 2,
                                                              "data": {"name": "x" * 70000}}}
    gw.send(conn, big)
    wait_for(lambda: len(handled) == 2 and any(m["op"] == 3 for m in gw.got))
    conn.close()  # the connection drops: the app must come back and go on (resume)


def second_login(conn, msg):
    gw.send(conn, {"op": 0, "t": "RESUMED", "s": 4, "d": {}})
    gw.send(conn, {"op": 0, "t": "INTERACTION_CREATE", "s": 5, "d": {"id": "i3", "token": "t3", "type": 3,
                                                                        "data": {"custom_id": "mr:stop"}}})
    wait_for(lambda: len(handled) == 3 and sum(1 for m in gw.got if m["op"] == 1) >= 2)
    gw.close(conn, 4004)  # then Discord says the token is no good


gw.plan = [first_login, second_login]
remote = R.Remote(get_token=lambda: TOKEN, handle=handled.append,
                  on_status=lambda ok, text, info=None: status.append((ok, text, info)),
                  commands=[{"name": "status", "description": "x"}], presence=lambda: "Ready",
                  registered_key=lambda: (registered or [None])[-1], on_registered=registered.append)
remote.gateway = f"ws://127.0.0.1:{gw.port}"
remote.start()
check("logs in and says it's connected", wait_for(lambda: any(ok for ok, _, _ in status)),
      [t for _, t, _ in status])
login = next((m for m in gw.got if m["op"] == 2), None)
check("the login asks for no intents and carries the token", login is not None and login["d"]["intents"] == 0
      and login["d"]["token"] == TOKEN)
info = next((i for ok, _, i in status if ok and i), {})
check("it knows the bot's name, ID and servers", info.get("name") == "MacroBot" and info.get("app_id") == "42"
      and info.get("servers") == 1, info)
check("the slash commands are registered once", wait_for(lambda: len(registered) == 1) and any(
    c[0] == "PUT" and c[1].endswith("/applications/42/commands") and c[3] == TOKEN for c in api_calls))
check("commands arrive (also split and very long messages)", wait_for(lambda: len(handled) >= 2)
      and handled[0]["id"] == "i1" and len(handled[1]["data"]["name"]) == 70000)
check("after a dropped connection it goes on where it was", wait_for(lambda: len(handled) == 3, 8)
      and any(m["op"] == 6 and m["d"]["session_id"] == "sess1" and m["d"]["seq"] == 3 for m in gw.got),
      [m["op"] for m in gw.got])
check("heartbeats are sent", wait_for(lambda: sum(1 for m in gw.got if m["op"] == 1) >= 2))
check("the status line is shown in Discord", wait_for(lambda: any(
    m["op"] == 3 and m["d"]["activities"][0]["state"] == "Ready" for m in gw.got)))
check("a wrong token stops it with a clear message", wait_for(lambda: status and status[-1][0] is False, 8)
      and "token is wrong" in status[-1][1] and wait_for(lambda: not remote.running()), status[-1:])
check("the token is never in a status text", not any(TOKEN in str(t) for _, t, _ in status))
n = len(api_calls)
R.respond({"id": "9", "token": "tok"}, R.REPLY, {"content": "hi"})
R.edit_reply({"application_id": "42", "token": "tok"}, {"content": "pic"}, b"\xff\xd8jpg")
check("answers go to the interaction's own address", api_calls[n][1].endswith("/interactions/9/tok/callback")
      and api_calls[n][2] == {"type": 4, "data": {"content": "hi"}}
      and api_calls[n + 1][1].endswith("/webhooks/42/tok/messages/@original")
      and api_calls[n + 1][2]["attachments"][0]["filename"] == "screen.jpg" and api_calls[n + 1][4])
remote.stop()

# ---------------------------------------------------------------- the commands, in the real window

root = tk.Tk()
root.withdraw()
app = modern_ui.ModernMacroRecorder(root)
app.kb_listener.stop()
app.mouse_listener.stop()
root.withdraw()
check("the remote is off until it's turned on", not app.remote.running() and app.remote_status_var.get() == "Off.")

sent = []   # (kind, data) answers and ("edit", data, picture)
R.respond = lambda it, kind, data=None: sent.append((kind, data))
R.edit_reply = lambda it, data, picture=None: sent.append(("edit", data, picture))

for name in ("Alpha", "Beta"):
    with open(os.path.join(tmp, name + ".macro"), "w", encoding="utf-8") as f:
        json.dump({"app": "macro_recorder", "version": 1, "name": name, "events": [
            {"type": "key_down", "key": {"char": "a"}, "t": 0.1}, {"type": "key_up", "key": {"char": "a"}, "t": 0.2}]}, f)
app.settings["macro_library"] = [os.path.join(tmp, "Alpha.macro"), os.path.join(tmp, "Beta.macro"),
                                 os.path.join(tmp, "Gone.macro")]


def run(interaction, seconds=6.0):
    """Send one interaction the way the bot's helper thread does; pump the window meanwhile."""
    before = len(sent)
    t = threading.Thread(target=app._remote_handle, args=(interaction,), daemon=True)
    t.start()
    end = time.time() + seconds
    while t.is_alive() and time.time() < end:
        root.update()
        time.sleep(0.01)
    return sent[before:]


def cmd(name, value=None, user="111", kind=2):
    data = {"name": name} if kind == 2 else {"custom_id": "mr:" + name}
    if value is not None and kind == 2:
        data["options"] = [{"name": "x", "value": value}]
    elif value is not None:
        data["values"] = [value]
    return {"id": "1", "token": "tok", "application_id": "42", "type": kind, "data": data,
            "member": {"user": {"id": user, "username": "player", "global_name": "Player"}}}


out = run(cmd("start"))
check("a stranger is refused, privately", len(out) == 1 and out[0][0] == R.REPLY
      and out[0][1]["flags"] == R.ONLY_YOU and "pairing code" in out[0][1]["content"], out)
code = app.remote_code
out = run(cmd("pair", code))
check("pairing is closed while the Phone remote window isn't open, even with the right code",
      "only open while the Phone remote window is open" in out[0][1]["content"] and not app._remote_users()
      and app.remote_fails == 0, out)
app.open_remote_window()
app.remote_win.geometry("+5000+5000")
root.update()
check("opening the window opens pairing", app.remote_pairing)
out = run(cmd("pair", "000000" if app.remote_code != "000000" else "111111"))
check("a wrong pairing code is refused", "isn't the code" in out[0][1]["content"] and not app._remote_users())
code = app.remote_code
for _ in range(4):
    run(cmd("pair", "999999" if code != "999999" else "888888"))
check("five wrong codes: a new code", app.remote_code != code)
code = app.remote_code
out = run(cmd("pair", code[:3] + " " + code[3:]))
for _ in range(30):
    root.update()
    time.sleep(0.01)
check("the right code pairs the account", "Paired" in out[0][1]["content"]
      and app._remote_users() == [{"id": "111", "name": "Player"}] and out[0][1]["flags"] == R.ONLY_YOU, out)
check("each code works once", app.remote_code != code and run(cmd("pair", code, user="222"))[0][1]["content"]
      .startswith("That isn't") and not app._remote_allowed("222"))

out = run(cmd("status"))
panel = out[0][1]
check("status: a card with the five buttons and the macro list", out[0][0] == R.REPLY
      and "Ready" in panel["embeds"][0]["title"]
      and [b["label"] for b in panel["components"][0]["components"]] == ["Start", "Pause", "Stop", "Refresh",
                                                                         "Screenshot"]
      and [o["label"] for o in panel["components"][1]["components"][0]["options"]] == ["Alpha", "Beta"], panel)
check("with no macro open, Start is off", panel["components"][0]["components"][0]["disabled"]
      and "No macro is open" in panel["embeds"][0]["description"])
out = run(cmd("start"))
check("start without a macro explains", "No macro is open" in out[0][1]["content"] and not app.playing)

out = run({**cmd("macro"), "type": 4, "data": {"name": "macro", "options": [{"name": "name", "value": "be",
                                                                              "focused": True}]}})
check("typing /macro lists the matching names", out == [(R.CHOICES, {"choices": [{"name": "Beta", "value": "Beta"}]})])
out = run(cmd("macro", "Beta"))
check("a macro is opened by name", "Opened **Beta**" in out[0][1]["content"] and app.name_var.get() == "Beta"
      and "Beta" in out[0][1]["embeds"][0]["title"], out[0][1]["content"])
out = run(cmd("macro", "Alpha", kind=3))
check("the list under the message switches (and updates that message)", out[0][0] == R.UPDATE
      and app.name_var.get() == "Alpha" and not out[0][1]["components"][0]["components"][0]["disabled"])
check("no question box is left waiting after a remote open", not getattr(app.boxes, "open_boxes", []))

# playing: a stand-in for the real playback (no keys are pressed)
played = []


def fake_play_worker(events, repeats, loop, speed, bg=None, ready=0, watch=None):
    played.append(len(events))
    app.stop_play.wait(30)
    app._call_ui(app._playback_done)


app._play_worker = fake_play_worker
app.settings["discord_enabled"] = False
app.ready_var.set(0)
asked = []
app.boxes._real_box = app.boxes._box
out = run(cmd("start", kind=3))
check("Start plays the macro without asking anything", app.playing and played == [1]
      and out[0][0] == R.UPDATE and "Started **Alpha**" in out[0][1]["content"], out[0][1]["content"])
panel = out[0][1]
labels = {b["label"]: b.get("disabled", False) for b in panel["components"][0]["components"]}
check("while playing: Start off, Pause and Stop on, the list off", "Playing" in panel["embeds"][0]["title"]
      and labels == {"Start": True, "Pause": False, "Stop": False, "Refresh": False, "Screenshot": False}
      and panel["components"][1]["components"][0]["disabled"], labels)
check("the bot's status line says what plays", app._remote_presence() == "Playing: Alpha")
out = run(cmd("start"))
check("start twice: already playing", "already playing" in out[0][1]["content"])
out = run(cmd("macro", "Beta"))
check("no switching while it plays", "Stop the macro first" in out[0][1]["content"] and app.name_var.get() == "Alpha")
out = run(cmd("pause"))
check("pause", app.play_paused_at is not None and out[0][1]["content"] == "Paused."
      and [b["label"] for b in out[0][1]["components"][0]["components"]][1] == "Resume")
out = run(cmd("pause"))
check("pause twice changes nothing", app.play_paused_at is not None and "already paused" in out[0][1]["content"])
out = run(cmd("resume", kind=3))
check("resume", app.play_paused_at is None and out[0][1]["content"] == "Going on.")
out = run(cmd("stop"))
check("stop: the answer already shows it stopped", not app.playing and out[0][1]["content"] == "Stopped."
      and "Ready" in out[0][1]["embeds"][0]["title"], out[0][1]["embeds"][0]["title"])
out = run(cmd("stop"))
check("stop when nothing plays", "Nothing is playing" in out[0][1]["content"])

# a problem that would normally show a box on the PC comes back as text
app.watch_var.set(True)
import numpy as np  # noqa: E402

# (2.9: with no picture on it plays without watching, so the problem is a picture without its macro)
old_pictures, app.watch_pictures = app.watch_pictures, [{"img": np.full((20, 20, 3), 90, np.uint8), "file": "x.png",
                                                         "screen_h": None, "action": "play"}]
out = run(cmd("start"))
check("a problem at start is told in Discord, with no box on the PC", not app.playing
      and out[0][1]["content"].startswith("Couldn't start:") and "picture" in out[0][1]["content"]
      and not getattr(app.boxes, "open_boxes", []), out[0][1]["content"])
app.watch_pictures = old_pictures
app.watch_var.set(False)

# an unsaved recording on the PC is never thrown away from the phone
app.unsaved = True
out = run(cmd("macro", "Beta"))
check("an unsaved macro isn't replaced", "isn't saved" in out[0][1]["content"] and app.name_var.get() == "Alpha")
app.unsaved = False

# the screenshot
import numpy as np  # noqa: E402

app._screenshot_with_note = lambda: (np.zeros((40, 60, 3), np.uint8), "main screen", False)
out = run(cmd("screenshot", kind=3))
check("screenshot: first 'working on it', then the picture", out[0] == (R.DEFER_REPLY, None)
      and out[1][0] == "edit" and out[1][2][:2] == b"\xff\xd8", [o[0] for o in out])
check("screenshot: a normal one says only the time", out[1][1]["content"].startswith("Screenshot at ")
      and "whole screen" not in out[1][1]["content"], out[1][1])
app._screenshot_with_note = lambda: (np.zeros((40, 60, 3), np.uint8), "game window not found, main screen taken", True)
out = run(cmd("screenshot", kind=3))
check("screenshot: when the game window wasn't found the reply says it is the whole screen",
      "whole screen" in out[1][1]["content"] and out[1][2][:2] == b"\xff\xd8", out[1][1])

# a window's thread that's busy: Discord still gets an answer in time, the result follows
slow = app._remote_act
app._remote_act = lambda *a: (time.sleep(2.6), slow(*a))[1]
out = run(cmd("status"), seconds=10)
check("a slow answer: 'working on it' in time, the card afterwards", out[0] == (R.DEFER_REPLY, None)
      and out[1][0] == "edit" and out[1][1]["embeds"], [o[0] for o in out])
app._remote_act = slow

# the window
app.open_remote_window()
app.remote_win.geometry("+5000+5000")
root.update()
texts = []


def walk(w):
    for c in w.winfo_children():
        try:
            texts.append(str(c.cget("text")))
        except tk.TclError:
            pass
        walk(c)


walk(app.remote_win)
check("the window lists the allowed account and the setup steps", "Player" in texts and "ID 111" in texts
      and any("Reset Token" in t for t in texts) and any("Connect" == t for t in texts))
app.remote_var.set(True)
app.remote_token_var.set("not a token")
app._remote_apply()
check("a pasted line that isn't a token is noticed (and nothing connects)", not app.remote.running()
      and "doesn't look like a bot token" in app.remote_status_var.get())
app._remote_remove_user("111")
check("Remove takes the account off the list", not app._remote_allowed("111"))
app.flush = getattr(core, "flush_settings", lambda: None)
app.flush()
with open(os.path.join(tmp, "settings.json"), encoding="utf-8") as f:
    saved = json.load(f)
check("the settings are saved on this PC", saved.get("remote_enabled") is True and saved.get("remote_token") == "not a token")
import diag  # noqa: E402

check("the token never goes into a support report",
      "not a token" not in diag.report("x", dict(saved, remote_token="SECRET.TOKEN.VALUE"))
      and "SECRET" not in diag.report("x", dict(saved, remote_token="SECRET.TOKEN.VALUE")))
app.remote_var.set(False)
code = app.remote_code
app._remote_close()
check("closing the window keeps what was set", app.settings.get("remote_enabled") is False and app.remote_win is None)
root.update()
check("closing the window closes pairing, with a new code for next time", not app.remote_pairing
      and app.remote_code != code and "only open" in run(cmd("pair", app.remote_code, user="333"))[0][1]["content"]
      and not app._remote_allowed("333"))
app.open_remote_window()
root.update()
app.remote_win.destroy()
root.update()
check("pairing also closes when the window goes some other way (with the Settings window)",
      not app.remote_pairing and app.remote_win is None)
app._on_close()

ok = sum(1 for _, good in results if good)
print(f"\n{ok} of {len(results)} passed")
sys.exit(0 if ok == len(results) else 1)
