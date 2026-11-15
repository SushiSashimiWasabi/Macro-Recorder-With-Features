"""A phone remote through Discord: your own small bot that the app logs in as.

A webhook link (discord_notify.py) can only send. To *receive* "start" or "stop" from Discord the
app has to be a bot: you make one on Discord's developer page, paste its token in Settings >
Discord > Phone remote, and add it to your server. The app then keeps one connection open to
Discord (outgoing only: nothing on your PC is opened to the internet) and Discord hands it the
slash commands and button presses.

This file is only the connection, with Python's own modules (no extra packages):
  WebSocket   a small secure websocket client
  Remote      logs in, keeps the connection alive, registers the slash commands, and calls
              handle(interaction) on a helper thread for every command / button press
  respond(), edit_reply()   answer an interaction (they need no token: Discord gives each
              interaction its own one-time address)

What the commands do lives in remote_ui.py. The token is never logged."""

import base64
import hashlib
import json
import os
import random
import socket
import ssl
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = "https://discord.com/api/v10"
GATEWAY = "wss://gateway.discord.gg"
USER_AGENT = "DiscordBot (MacroRecorder, 1.0)"
MAX_MESSAGE = 8 * 1024 * 1024

# what Discord can say when it closes the connection for good
FATAL_CLOSES = {
    4004: "Discord says the bot token is wrong. Copy it again (Bot > Reset Token).",
    4010: "Discord refused the connection (shard).",
    4011: "Discord refused the connection (too many servers).",
    4012: "Discord refused the connection (old version).",
    4013: "Discord refused the connection (intents).",
    4014: "Discord refused the connection (intents not allowed).",
}
NEW_SESSION_CLOSES = (4007, 4009)


class Fatal(Exception):
    """Trying again won't help (wrong token)."""


class Closed(Exception):
    def __init__(self, code=1006, reason=""):
        super().__init__(f"closed ({code}) {reason}".strip())
        self.code = code


def _ssl_context():
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def looks_like_token(token):
    """A bot token is three parts with dots between (no spaces)."""
    token = (token or "").strip()
    parts = token.split(".")
    return len(token) >= 50 and len(parts) == 3 and all(parts) and not any(c.isspace() for c in token)


def app_id_from_token(token):
    """The bot's application ID (the first part of its token), or None."""
    try:
        first = (token or "").strip().split(".")[0]
        text = base64.urlsafe_b64decode(first + "=" * (-len(first) % 4)).decode("ascii")
        return text if text.isdigit() and 15 <= len(text) <= 22 else None
    except Exception:
        return None


def invite_link(app_id):
    """The page that adds the bot to a server (it asks for no permissions: answering commands
    needs none)."""
    return ("https://discord.com/oauth2/authorize?client_id=" + str(app_id)
            + "&scope=bot+applications.commands&permissions=0")


# ---------------------------------------------------------------- websocket

class WebSocket:
    def __init__(self, url, timeout=20):
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname
        port = parts.port or (443 if parts.scheme == "wss" else 80)
        path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        raw = socket.create_connection((host, port), timeout=timeout)
        try:
            self.sock = _ssl_context().wrap_socket(raw, server_hostname=host) if parts.scheme == "wss" else raw
        except Exception:
            raw.close()
            raise
        self.closed = False
        self.send_lock = threading.Lock()
        self.buf = b""
        try:
            key = base64.b64encode(os.urandom(16)).decode()
            self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
                               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                               f"Sec-WebSocket-Version: 13\r\nUser-Agent: {USER_AGENT}\r\n\r\n").encode())
            while b"\r\n\r\n" not in self.buf:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise Closed(1006, "no answer")
                self.buf += chunk
                if len(self.buf) > 65536:
                    raise Closed(1006, "bad answer")
            head, self.buf = self.buf.split(b"\r\n\r\n", 1)
            lines = head.decode("latin-1").split("\r\n")
            if " 101" not in lines[0]:
                raise Closed(1006, lines[0][:80])
            headers = {k.strip().lower(): v.strip() for k, v in (ln.split(":", 1) for ln in lines[1:] if ":" in ln)}
            want = base64.b64encode(hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            if headers.get("sec-websocket-accept") != want:
                raise Closed(1006, "bad handshake")
            self.sock.settimeout(2.0)  # (short, so close() from another thread is noticed)
        except Exception:
            self.close()
            raise

    def _exact(self, n):
        while len(self.buf) < n:
            if self.closed:
                raise Closed(1006, "closed here")
            try:
                chunk = self.sock.recv(65536)
            except (socket.timeout, ssl.SSLWantReadError):
                continue
            except OSError as exc:
                raise Closed(1006, str(exc)) from None
            if not chunk:
                raise Closed(1006, "connection lost")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        """The next whole text message (pings are answered on the way). Raises Closed."""
        parts = []
        size = 0
        while True:
            b1, b2 = self._exact(2)
            op = b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._exact(8))[0]
            if n > MAX_MESSAGE:
                raise Closed(1009, "message too big")
            mask = self._exact(4) if b2 & 0x80 else None
            data = self._exact(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 8:
                code = struct.unpack(">H", data[:2])[0] if len(data) >= 2 else 1005
                raise Closed(code, data[2:].decode("utf-8", "replace"))
            if op == 9:
                self._send(10, data)
                continue
            if op == 10:
                continue
            parts.append(data)
            size += n
            if size > MAX_MESSAGE:
                raise Closed(1009, "message too big")
            if b1 & 0x80:
                return b"".join(parts).decode("utf-8", "replace")

    def _send(self, op, payload):
        n = len(payload)
        if n < 126:
            head = bytes([0x80 | op, 0x80 | n])
        elif n < 65536:
            head = bytes([0x80 | op, 0x80 | 126]) + struct.pack(">H", n)
        else:
            head = bytes([0x80 | op, 0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self.send_lock:
            if self.closed:
                raise Closed(1006, "closed here")
            try:
                self.sock.settimeout(10.0)
                self.sock.sendall(head + mask + body)
            except OSError as exc:
                raise Closed(1006, str(exc)) from None
            finally:
                try:
                    self.sock.settimeout(2.0)
                except OSError:
                    pass

    def send_json(self, data):
        self._send(1, json.dumps(data).encode("utf-8"))

    def close(self):
        self.closed = True
        try:
            self.sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------- Discord's web API

def api(method, url, payload=None, token=None, picture=None, timeout=15):
    """One call to Discord. picture: JPG / PNG bytes sent along as the message's file.
    Returns the answer (dict / list) or None; raises RuntimeError with a readable message."""
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = "Bot " + token.strip()
    if picture:
        boundary = uuid.uuid4().hex
        name = "screen.png" if picture[:4] == b"\x89PNG" else "screen.jpg"
        kind = "image/png" if name.endswith("png") else "image/jpeg"
        body = b"".join([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
            "Content-Type: application/json\r\n\r\n".encode(), json.dumps(payload or {}).encode(), b"\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{name}\"\r\n"
            f"Content-Type: {kind}\r\n\r\n".encode(), picture, b"\r\n", f"--{boundary}--\r\n".encode()])
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    else:
        body = None
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise RuntimeError("Discord says the bot token is wrong.") from None
        if exc.code == 429:
            raise RuntimeError("Discord says: too many requests, wait a little.") from None
        detail = ""
        try:
            detail = str(json.loads(exc.read()).get("message", ""))[:120]
        except Exception:
            pass
        raise RuntimeError(f"Discord refused it (error {exc.code}{': ' + detail if detail else ''}).") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Couldn't reach Discord ({exc.reason}).") from None
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Couldn't reach Discord ({exc}).") from None


# kinds of answer to an interaction
REPLY, DEFER_REPLY, DEFER_UPDATE, UPDATE, CHOICES = 4, 5, 6, 7, 8
ONLY_YOU = 64  # message flag: only the person who used the command sees the answer


def respond(interaction, kind, data=None):
    """The first answer to a command or button press (must arrive within 3 seconds)."""
    body = {"type": kind}
    if data is not None:
        body["data"] = data
    api("POST", f"{API}/interactions/{interaction['id']}/{interaction['token']}/callback", body, timeout=8)


def edit_reply(interaction, data, picture=None):
    """Change the answer afterwards (after DEFER_REPLY / DEFER_UPDATE, for up to 15 minutes)."""
    if picture:
        data = dict(data)
        data["attachments"] = [{"id": 0, "filename": "screen.png" if picture[:4] == b"\x89PNG" else "screen.jpg"}]
    api("PATCH", f"{API}/webhooks/{interaction['application_id']}/{interaction['token']}/messages/@original",
        data, picture=picture, timeout=30)


def commands_key(app_id, commands):
    return hashlib.sha1((str(app_id) + json.dumps(commands, sort_keys=True)).encode()).hexdigest()


# ---------------------------------------------------------------- the bot

class Remote:
    def __init__(self, get_token, handle, on_status=None, commands=None, presence=None,
                 registered_key=None, on_registered=None, log=None):
        """get_token(): the bot token right now ("" = off).
        handle(interaction): called on a helper thread for every command, button and typed-ahead list.
        on_status(ok, text, info): ok True = connected, False = a problem, None = busy / off.
        commands: the slash commands to register; registered_key() / on_registered(key) remember
        that it was done, so they're sent to Discord only when they change.
        presence(): a short line shown as the bot's status in Discord (or None)."""
        self.get_token = get_token
        self.handle = handle
        self.on_status = on_status or (lambda ok, text, info=None: None)
        self.commands = commands or []
        self.presence = presence
        self.registered_key = registered_key or (lambda: None)
        self.on_registered = on_registered or (lambda key: None)
        self.log = log or (lambda text: None)
        self.thread = None
        self.stop_flag = threading.Event()
        self.ws = None
        self.session_id = None
        self.resume_url = None
        self.seq = None
        self.acked = True
        self.app_id = None
        self.bot_name = None
        self.connected = False
        self.shown_presence = None
        self.presence_sent = 0.0
        self.gateway = GATEWAY

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        if self.running():
            return
        self.stop_flag = threading.Event()
        self.session_id = self.seq = self.resume_url = None
        self.thread = threading.Thread(target=self._run, args=(self.stop_flag,), daemon=True, name="discord-remote")
        self.thread.start()

    def stop(self):
        self.stop_flag.set()
        self.connected = False
        ws = self.ws
        if ws is not None:
            ws.close()
        self.thread = None

    # ---- the connection

    def _run(self, stop):
        wait = 1.0
        while not stop.is_set():
            token = (self.get_token() or "").strip()
            if not token:
                return
            self.on_status(None, "Connecting to Discord…", None)
            try:
                self._session(token, stop)
                wait = 1.0  # (it was connected: try again straight away)
            except Fatal as exc:
                self.connected = False
                if not stop.is_set():
                    self.log(f"Discord remote stopped: {exc}")
                    self.on_status(False, str(exc), None)
                return
            except Closed as exc:
                if exc.code in FATAL_CLOSES:
                    self.connected = False
                    if not stop.is_set():
                        self.log(f"Discord remote stopped: close code {exc.code}")
                        self.on_status(False, FATAL_CLOSES[exc.code], None)
                    return
                if exc.code in NEW_SESSION_CLOSES:
                    self.session_id = self.seq = None
                was, self.connected = self.connected, False
                if was:
                    wait = 1.0
            except Exception as exc:
                was, self.connected = self.connected, False
                if was:
                    wait = 1.0
                elif not stop.is_set():
                    self.on_status(False, f"Couldn't reach Discord ({short_error(exc)}). Trying again…", None)
            if stop.wait(wait + random.random()):
                return
            wait = min(wait * 2, 60.0)

    def _session(self, token, stop):
        ws = WebSocket((self.resume_url if self.session_id and self.resume_url else self.gateway)
                       + "/?v=10&encoding=json")
        self.ws = ws
        try:
            if stop.is_set():
                return
            hello = json.loads(ws.recv())
            interval = float(hello["d"]["heartbeat_interval"]) / 1000.0
            self.acked = True
            threading.Thread(target=self._beat, args=(ws, interval, stop), daemon=True,
                             name="discord-remote-beat").start()
            if self.session_id and self.seq is not None:
                ws.send_json({"op": 6, "d": {"token": token, "session_id": self.session_id, "seq": self.seq}})
            else:
                ws.send_json({"op": 2, "d": {
                    "token": token, "intents": 0,  # (commands and buttons arrive without any intent)
                    "properties": {"os": "windows", "browser": "MacroRecorder", "device": "MacroRecorder"}}})
            while not stop.is_set():
                msg = json.loads(ws.recv())
                op = msg.get("op")
                if msg.get("s") is not None:
                    self.seq = msg["s"]
                if op == 0:
                    self._event(msg.get("t"), msg.get("d") or {}, token, ws)
                elif op == 1:
                    ws.send_json({"op": 1, "d": self.seq})
                elif op == 7:  # Discord asks to connect again (it goes on where it was)
                    return
                elif op == 9:  # the session is no good: log in afresh
                    if not msg.get("d"):
                        self.session_id = self.seq = None
                    stop.wait(1 + random.random() * 4)
                    return
                elif op == 11:
                    self.acked = True
        finally:
            ws.close()

    def _beat(self, ws, interval, stop):
        """Tells Discord every ~40 s that the app is still there; a missing answer = connect again."""
        if stop.wait(interval * random.random()):
            return
        while not ws.closed and not stop.is_set():
            if not self.acked:
                ws.close()
                return
            self.acked = False
            try:
                ws.send_json({"op": 1, "d": self.seq})
            except Exception:
                ws.close()
                return
            end = time.monotonic() + interval
            while True:
                left = end - time.monotonic()
                if left <= 0:
                    break
                if stop.wait(min(5.0, left)) or ws.closed:
                    return
                self._show_presence(ws)

    def _show_presence(self, ws, force=False):
        if self.presence is None or not self.connected:
            return
        try:
            text = self.presence()
        except Exception:
            return
        now = time.monotonic()
        if not text or (text == self.shown_presence and not force) or now - self.presence_sent < 15:
            return
        try:
            ws.send_json({"op": 3, "d": {"since": None, "status": "online", "afk": False, "activities": [
                {"name": "Custom Status", "type": 4, "state": str(text)[:120]}]}})
            self.shown_presence = text
            self.presence_sent = now
        except Exception:
            pass

    def _event(self, kind, d, token, ws):
        if kind == "READY":
            self.session_id = d.get("session_id")
            self.resume_url = d.get("resume_gateway_url")
            self.app_id = str((d.get("application") or {}).get("id") or "") or app_id_from_token(token)
            user = d.get("user") or {}
            self.bot_name = user.get("global_name") or user.get("username") or "the bot"
            servers = len(d.get("guilds") or [])
            self.connected = True
            self.shown_presence = None
            self.presence_sent = 0.0
            note = ""
            try:
                self._register(token)
            except Exception as exc:
                note = f" The commands couldn't be set up: {exc}"
                self.log(f"Discord remote: commands not registered: {exc}")
            self.log(f"Discord remote connected ({servers} server(s))")
            self.on_status(True, f"Connected as {self.bot_name}." + note,
                           {"app_id": self.app_id, "name": self.bot_name, "servers": servers})
            self._show_presence(ws, force=True)
        elif kind == "RESUMED":
            self.connected = True
            self.on_status(True, f"Connected as {self.bot_name}.", None)
        elif kind == "INTERACTION_CREATE":
            threading.Thread(target=self._handle, args=(d,), daemon=True, name="discord-remote-command").start()

    def _handle(self, interaction):
        try:
            self.handle(interaction)
        except Exception as exc:
            self.log(f"Discord remote: a command failed: {type(exc).__name__}: {exc}")

    def _register(self, token):
        if not self.commands or not self.app_id:
            return
        key = commands_key(self.app_id, self.commands)
        if self.registered_key() == key:
            return
        api("PUT", f"{API}/applications/{self.app_id}/commands", self.commands, token=token)
        self.on_registered(key)


def short_error(exc):
    text = str(getattr(exc, "reason", None) or exc) or type(exc).__name__
    return text if len(text) <= 80 else text[:79] + "…"
