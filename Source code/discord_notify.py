"""Messages to your own Discord channel through a webhook link you paste in Settings.

No bot and no server: Discord gives every channel "webhook" links (Channel settings > Integrations
> Webhooks > New Webhook > Copy Webhook URL). Anything posted to that link shows up in the channel.

Notifier.send(text, png=None) queues a message and returns at once; one helper thread sends them
in order. If Discord is slow, the oldest waiting messages are dropped (never more than 5 wait), so
a macro is never held up."""

import json
import queue
import threading
import time
import urllib.error
import urllib.request
import uuid

WEBHOOK_PREFIXES = ("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/",
                    "https://canary.discord.com/api/webhooks/", "https://ptb.discord.com/api/webhooks/")
MAX_WAITING = 5
RETRIES = 2  # a message that Discord turned away (too many) or that couldn't get through is tried this many more times
RETRY_OFFLINE = 30  # seconds before trying again when Discord couldn't be reached


def is_webhook(url):
    url = (url or "").strip()
    return url.startswith(WEBHOOK_PREFIXES) and len(url) > 60


def _ssl_context():
    try:
        import ssl

        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def post(url, text, png=None, timeout=15, embed=None, username=None, edit_id=None, want_id=False):
    """Send one message now (blocking). Raises an error with a readable message if it fails.
    edit_id: change that earlier message instead of posting a new one (LookupError if it's gone).
    want_id: return the new message's id (for editing it later).

    embed: {"title", "description", "color"} shown as a card (the screenshot goes inside it).
    Mentions written in the text (<@id>, <@&role>, @everyone, @here) do ping."""
    payload = {"content": (text or "")[:1900], "username": (username or "Macro Recorder")[:80],
               "allowed_mentions": {"parse": ["users", "roles", "everyone"]}}
    if embed:
        card = {"title": str(embed.get("title", ""))[:250], "description": str(embed.get("description", ""))[:4000]}
        if embed.get("color") is not None:
            card["color"] = int(embed["color"])
        if png:
            card["image"] = {"url": "attachment://" + _picture_name(png)}
        payload["embeds"] = [card]
    if not payload["content"] and not embed and not png:
        payload["content"] = "(empty message)"
    if png:
        boundary = uuid.uuid4().hex
        body = b"".join([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
            "Content-Type: application/json\r\n\r\n".encode(), json.dumps(payload).encode(), b"\r\n",
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; "
            f"filename=\"{_picture_name(png)}\"\r\n"
            f"Content-Type: {'image/png' if png[:4] == b'\x89PNG' else 'image/jpeg'}\r\n\r\n".encode(), png, b"\r\n",
            f"--{boundary}--\r\n".encode()])
        ctype = f"multipart/form-data; boundary={boundary}"
    else:
        body = json.dumps(payload).encode()
        ctype = "application/json"
    target = url.strip().split("?")[0]
    if edit_id:
        target += f"/messages/{edit_id}"
    elif want_id:
        target += "?wait=true"
    req = urllib.request.Request(target, data=body, method="PATCH" if edit_id else "POST",
                                 headers={"Content-Type": ctype, "User-Agent": "MacroRecorder"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            answer = resp.read()
        if want_id and not edit_id:
            try:
                return str(json.loads(answer.decode("utf-8")).get("id") or "") or None
            except (ValueError, AttributeError):
                return None
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and edit_id:
            raise LookupError("that message is gone") from None
        if exc.code == 404:
            raise RuntimeError("Discord says that webhook link doesn't exist (deleted?). Copy it again.") from None
        if exc.code == 429:
            raise RateLimited(_retry_after(exc)) from None
        if exc.code == 413:
            raise RuntimeError("The screenshot was too big for Discord.") from None
        raise RuntimeError(f"Discord refused the message (error {exc.code}).") from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):  # (it may have arrived: not tried again)
            raise RuntimeError(f"Discord didn't answer in time ({exc.reason}).") from None
        raise Unreachable(f"Couldn't reach Discord ({exc.reason}).") from None
    except (TimeoutError, ConnectionError) as exc:
        # (not tried again: the message may have arrived even though the answer didn't)
        raise RuntimeError(f"Discord didn't answer in time ({exc}).") from None


class RateLimited(RuntimeError):
    """Discord said "too many messages": .wait is how many seconds it asked to wait."""

    def __init__(self, wait):
        super().__init__("Discord says too many messages; some were skipped.")
        self.wait = wait


class Unreachable(RuntimeError):
    """No answer from Discord (the internet dropped for a moment, or Discord is down)."""


def _retry_after(exc):
    """Seconds Discord asks to wait after "too many messages" (its header or its answer), 1 to 60."""
    wait = None
    try:
        wait = float(exc.headers.get("Retry-After"))
    except (TypeError, ValueError, AttributeError):
        pass
    if wait is None:
        try:
            wait = float(json.loads(exc.read().decode("utf-8")).get("retry_after"))
        except Exception:
            wait = 2.0
    return max(1.0, min(60.0, wait))


def _picture_name(data):
    return "screen.png" if data[:4] == b"\x89PNG" else "screen.jpg"


CAPTURE_SCREEN, CAPTURE_ALL, CAPTURE_GAME = "screen", "all", "game"  # or "program:<file name>"


def screenshot_png(target=CAPTURE_SCREEN, game_exe=None, max_w=1600):
    """The screenshot as JPG bytes (the name stays for older callers), or None."""
    return encode(grab(target, game_exe), max_w)


def encode(img, max_w=1600):
    """A screenshot (from grab) as JPG bytes, shrunk to max_w wide: much smaller and quicker to make
    and send than PNG, and looks the same in Discord."""
    if img is None:
        return None
    try:
        import cv2

        h, w = img.shape[:2]
        if w > max_w:
            img = cv2.resize(img, (max_w, int(h * max_w / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
        return buf.tobytes() if ok else None
    except Exception:
        return None


def grab(target=CAPTURE_SCREEN, game_exe=None):
    """The main screen, all screens, the game's window or a chosen program's window, as a picture
    (quick: shrinking and packing it is left for later, off the playback thread). A window that can't
    be found (closed, minimized) falls back to the main screen. None if no screenshot is possible."""
    try:
        import numpy as np

        import image_watch
        import window_tools

        img = None
        target = target or CAPTURE_SCREEN
        exe = game_exe if target == CAPTURE_GAME else (target[8:] if target.startswith("program:") else None)
        if exe:
            wins = window_tools.windows_of(exe)
            rect = window_tools.client_rect(wins[0]) if wins else None
            if rect:
                x, y, w, h = rect
                with image_watch.mss.mss() as sct:
                    shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
                img = np.ascontiguousarray(np.asarray(shot)[:, :, :3])
        elif target == CAPTURE_ALL:
            with image_watch.mss.mss() as sct:
                shot = sct.grab(sct.monitors[0])
            img = np.ascontiguousarray(np.asarray(shot)[:, :, :3])
        if img is None:
            img = image_watch.grab_screen()
        return img
    except Exception:
        return None


def grab_area(target=CAPTURE_SCREEN, game_exe=None):
    """The part of the screen grab() will take, as (x, y, w, h); None = all screens (or unknown)."""
    try:
        import ctypes

        import window_tools

        target = target or CAPTURE_SCREEN
        if target == CAPTURE_ALL or not window_tools.IS_WIN:
            return None
        exe = game_exe if target == CAPTURE_GAME else (target[8:] if target.startswith("program:") else None)
        if exe:
            wins = window_tools.windows_of(exe)
            rect = window_tools.client_rect(wins[0]) if wins else None
            if rect:
                return tuple(rect)
        u = ctypes.windll.user32
        return (0, 0, u.GetSystemMetrics(0), u.GetSystemMetrics(1))  # the main screen
    except Exception:
        return None


class Notifier:
    def __init__(self, get_url, on_result=None):
        """get_url(): the webhook link right now. on_result(ok, text): called (on the helper thread)
        after each try, so Settings can show whether the last message really arrived."""
        self.get_url = get_url
        self.on_result = on_result
        self.jobs = queue.Queue()
        self.thread = None
        self.last_sent = 0.0
        self.live = {}  # live card name -> (webhook link, message id): that message is changed in place

    def send(self, text, png=None, embed=None, username=None, live=None):
        """Queue a message. png: the screenshot, taken by the caller at the right moment: picture
        bytes, or a picture from grab() (packed as JPG here, on the helper thread)."""
        url = self.get_url()
        if not is_webhook(url):
            return False
        while self.jobs.qsize() >= MAX_WAITING:  # Discord is slow: drop the oldest
            try:
                self.jobs.get_nowait()
            except queue.Empty:
                break
        self.jobs.put((url, text, png, embed, username, live))
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True, name="discord")
            self.thread.start()
        return True

    def _run(self):
        while True:
            try:
                url, text, png, embed, username, live = self.jobs.get(timeout=30)
            except queue.Empty:
                return
            wait = 1.0 - (time.monotonic() - self.last_sent)  # at most one message a second
            if wait > 0:
                time.sleep(wait)
            ok, note = self._send_with_retries(url, text, png, embed, username, live)
            self.last_sent = time.monotonic()
            if self.on_result:
                try:
                    self.on_result(ok, note)
                except Exception:
                    pass

    def _send_with_retries(self, url, text, png, embed, username, live):
        """Send one message. When Discord says "too many messages" it's sent again after the wait
        Discord asks for, and when Discord can't be reached (the internet dropped for a moment) it's
        tried again after RETRY_OFFLINE seconds, a few times, so an overnight run loses fewer cards."""
        if png is not None and not isinstance(png, (bytes, bytearray)):
            try:
                png = encode(png)
            except Exception as exc:
                return False, str(exc)
        tries = 0
        while True:
            tries += 1
            try:
                self._send_once(url, text, png, embed, username, live)
                return True, "Last message arrived" + (" (after trying again)" if tries > 1 else "")
            except RateLimited as exc:
                if tries > RETRIES:
                    return False, str(exc)
                time.sleep(exc.wait)
            except Unreachable as exc:
                if tries > RETRIES:
                    return False, str(exc)
                time.sleep(RETRY_OFFLINE)
            except Exception as exc:
                return False, str(exc)

    def _send_once(self, url, text, png, embed, username, live):
        if live:
            # one card that's changed in place (a new one when there's none yet, or it's gone)
            known = self.live.get(live)
            done = False
            if known and known[0] == url:
                try:
                    post(url, text, None, embed=embed, username=username, edit_id=known[1])
                    done = True
                except LookupError:
                    pass
            if not done:
                new_id = post(url, text, None, embed=embed, username=username, want_id=True)
                if new_id:
                    self.live[live] = (url, new_id)
        else:
            post(url, text, png, embed=embed, username=username)
