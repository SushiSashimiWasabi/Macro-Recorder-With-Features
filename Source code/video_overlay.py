"""A YouTube video (or playlist) in a small always-on-top window over the game.

The video plays in YouTube's own embedded player (the official one, so ads and "embedding turned
off" work the same way as on any website). It runs in an Edge (or Chrome) "app" window: a plain
window with only a title bar, which you can move by its title bar and resize by its edges.
While a macro records or plays, the window lets every click go straight through it and never
takes the keyboard, so the macro and the game don't notice it.

Edge comes with Windows 10 and 11. On a Mac it uses Google Chrome or Microsoft Edge if one is
installed (the click-through part is Windows only).
"""

import html
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

TITLE = "Macro Recorder video"

# ---------------------------------------------------------------- links

_ID = r"[A-Za-z0-9_-]{11}"


def parse_link(text):
    """A YouTube link -> {"video": id or None, "list": playlist id or None, "start": seconds}.
    None if it isn't a YouTube video or playlist link. A bare 11-letter video id works too."""
    text = (text or "").strip()
    if not text:
        return None
    if re.fullmatch(_ID, text):
        return {"video": text, "list": None, "start": 0}
    if "://" not in text:
        text = "https://" + text
    try:
        u = urllib.parse.urlparse(text)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]
    q = urllib.parse.parse_qs(u.query)
    video = None
    if host == "youtu.be":
        part = u.path.strip("/").split("/")[0]
        video = part if re.fullmatch(_ID, part) else None
    elif host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        parts = [p for p in u.path.split("/") if p]
        if parts[:1] == ["watch"] or not parts:
            v = (q.get("v") or [""])[0]
            video = v if re.fullmatch(_ID, v) else None
        elif len(parts) >= 2 and parts[0] in ("shorts", "live", "embed", "v", "e"):
            video = parts[1] if re.fullmatch(_ID, parts[1]) else None
        elif parts[:1] != ["playlist"]:
            return None
    else:
        return None
    lst = (q.get("list") or [""])[0]
    lst = lst if re.fullmatch(r"[A-Za-z0-9_-]{2,64}", lst) else None
    if not video and not lst:
        return None
    start = 0
    t = (q.get("t") or q.get("start") or [""])[0]
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?", t or "")
    if t and m:
        h, mi, s = (int(x) if x else 0 for x in m.groups())
        start = h * 3600 + mi * 60 + s
    return {"video": video, "list": lst, "start": start}


def page_html(link, port):
    """The page with YouTube's embedded player filling the whole window."""
    info = json.dumps(link)
    origin = json.dumps(f"http://127.0.0.1:{port}")
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>{html.escape(TITLE)}</title>
<style>
 html, body {{ margin: 0; height: 100%; background: #000; overflow: hidden; }}
 #player {{ position: fixed; inset: 0; width: 100%; height: 100%; border: 0; }}
 #msg {{ position: fixed; inset: 0; display: none; align-items: center; justify-content: center;
        padding: 20px; color: #ddd; font: 15px "Segoe UI", sans-serif; text-align: center; }}
 #osd {{ position: fixed; left: 50%; top: 14px; transform: translateX(-50%); padding: 6px 14px;
        background: rgba(17, 17, 20, .85); color: #f1f1f4; font: bold 14px "Segoe UI", sans-serif;
        border-radius: 8px; display: none; pointer-events: none; z-index: 10; }}
</style></head>
<body><div id="player"></div><div id="msg"></div><div id="osd"></div>
<script>
 var link = {info};
 var player;
 // tell the app how tall the page is, so it can tuck the browser's own title bar out of sight
 function report() {{ fetch("/size?h=" + Math.round(innerHeight * devicePixelRatio)).catch(function () {{}}); }}
 addEventListener("resize", report); report(); setInterval(report, 700);
 function say(text) {{ var m = document.getElementById("msg"); m.textContent = text; m.style.display = "flex"; }}
 // the app's video keys: skip, volume, speed, play / pause, another video (shown for a moment at the top)
 var osdTimer = null;
 function osd(text) {{
   var o = document.getElementById("osd"); o.textContent = text; o.style.display = "block";
   clearTimeout(osdTimer); osdTimer = setTimeout(function () {{ o.style.display = "none"; }}, 1200);
 }}
 function clock(t) {{ t = Math.max(0, Math.floor(t)); var m = Math.floor(t / 60), s = t % 60;
   return m + ":" + (s < 10 ? "0" : "") + s; }}
 function doCommand(c, v) {{
   if (!player || !player.getPlayerState) return;
   try {{
     if (c === "seek") {{ var t = Math.max(0, player.getCurrentTime() + v); player.seekTo(t, true);
       osd((v > 0 ? "+" : "") + v + " s   " + clock(t)); }}
     else if (c === "volume") {{ var n = Math.max(0, Math.min(100, Math.round(player.getVolume() + v)));
       player.setVolume(n); if (n > 0 && player.isMuted()) player.unMute(); osd("Volume " + n + "%"); }}
     else if (c === "mute") {{ if (player.isMuted()) {{ player.unMute(); osd("Sound on"); }}
       else {{ player.mute(); osd("Muted"); }} }}
     else if (c === "pause") {{ if (player.getPlayerState() === 1) {{ player.pauseVideo(); osd("Paused"); }}
       else {{ player.playVideo(); osd("Playing"); }} }}
     else if (c === "speed") {{ var rates = player.getAvailablePlaybackRates() || [1];
       var i = rates.indexOf(player.getPlaybackRate()); i = Math.max(0, Math.min(rates.length - 1, i + v));
       player.setPlaybackRate(rates[i]); osd("Speed " + rates[i] + "x"); }}
     else if (c === "load") {{ document.getElementById("msg").style.display = "none";
       player.loadVideoById({{ videoId: v.video, startSeconds: v.start || 0 }}); osd(v.label || "Next video"); }}
   }} catch (e) {{}}
 }}
 function pollCommands() {{
   fetch("/cmd").then(function (r) {{ return r.json(); }}).then(function (list) {{
     list.forEach(function (c) {{ doCommand(c[0], c[1]); }});
   }}).catch(function () {{}});
 }}
 setInterval(pollCommands, 200);
 function onYouTubeIframeAPIReady() {{
   var vars = {{ autoplay: 1, playsinline: 1, rel: 0, origin: {origin} }};
   if (link.start) vars.start = link.start;
   var opts = {{ width: "100%", height: "100%", playerVars: vars,
     events: {{ onReady: function (e) {{ e.target.playVideo(); }}, onError: failed }} }};
   if (link.list) {{ vars.list = link.list; if (!link.video) vars.listType = "playlist"; }}
   if (link.video) opts.videoId = link.video;
   player = new YT.Player("player", opts);
 }}
 function failed(e) {{
   var blocked = (e.data === 101 || e.data === 150 || e.data === 153);
   if (link.list && player && player.getPlaylist && player.getPlaylist() &&
       player.getPlaylistIndex() < player.getPlaylist().length - 1) {{
     player.nextVideo();  // skip a video that can't play here and go on with the playlist
     return;
   }}
   say(blocked ? "The owner of this video doesn't allow it to play outside YouTube. Try another video."
       : (e.data === 100 ? "This video was removed or is private."
       : "YouTube couldn't play this video (error " + e.data + ")."));
 }}
</script>
<script src="https://www.youtube.com/iframe_api"></script>
</body></html>"""


class _Server:
    """A tiny web server on this computer only (127.0.0.1) that hands the browser the player page.
    YouTube's player needs to sit on a real web page, not a file, or it refuses to play."""

    def __init__(self):
        self.page = b""
        self.commands = []  # the video keys pressed, waiting for the page to fetch them
        self.inner_height = 0  # the page's height in screen pixels, as the page reports it
        self.reported_at = 0.0
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                path, _, query = self.path.partition("?")
                if path == "/size":
                    h = urllib.parse.parse_qs(query).get("h", ["0"])[0]
                    outer.inner_height = int(h) if h.isdigit() else 0
                    outer.reported_at = time.time()
                    self.send_response(204)
                    self.end_headers()
                    return
                if path == "/cmd":
                    body = json.dumps(outer.commands).encode("utf-8")
                    outer.commands = []
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if path not in ("/", "/index.html"):
                    self.send_error(404)
                    return
                body = outer.page
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass


# ---------------------------------------------------------------- the browser

def find_browser():
    """Path of Edge or Chrome, or None."""
    if IS_WIN:
        places = []
        for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                places += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                           os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    elif IS_MAC:
        places = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    else:
        places = ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/microsoft-edge"]
    for p in places:
        if os.path.isfile(p):
            return p
    return None


if IS_WIN:
    import ctypes
    from ctypes import wintypes

    _u = ctypes.WinDLL("user32", use_last_error=True)  # own copy: argtypes here don't change other modules' calls
    _u.GetWindowLongW.restype = ctypes.c_long
    _u.SetWindowLongW.restype = ctypes.c_long
    _u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    _u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_uint]
    _u.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte, wintypes.DWORD]
    _u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    _u.FindWindowW.restype = wintypes.HWND
    _u.IsWindow.argtypes = [wintypes.HWND]
    _u.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    _u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x20, 0x80000, 0x8000000
    HWND_TOPMOST = wintypes.HWND(-1)
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_FRAMECHANGED, SWP_NOZORDER = 0x1, 0x2, 0x10, 0x20, 0x4

    def _window_pid(hwnd):
        pid = wintypes.DWORD()
        _u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def _find_window(title_start):
        found = []

        def cb(hwnd, _):
            if not _u.IsWindowVisible(hwnd):
                return True
            n = _u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                _u.GetWindowTextW(hwnd, buf, n + 1)
                cls = ctypes.create_unicode_buffer(64)
                _u.GetClassNameW(hwnd, cls, 64)
                if buf.value.startswith(title_start) and cls.value.startswith("Chrome_WidgetWin"):
                    found.append(hwnd)
                    return False
            return True
        _u.EnumWindows(_ENUM(cb), 0)
        return found[0] if found else None

    _u.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    _u.SetParent.restype = wintypes.HWND
    _u.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL]
    _u.GetParent.argtypes = [wintypes.HWND]
    _u.GetParent.restype = wintypes.HWND
    GWL_STYLE = -16
    WS_CHILD, WS_POPUP, WS_CAPTION, WS_THICKFRAME = 0x40000000, 0x80000000, 0x00C00000, 0x00040000
    WS_SYSMENU, WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00080000, 0x00020000, 0x00010000


class VideoOverlay:
    """One video window. All methods are for the Tk thread; poll() should run about twice a second
    while it's open.

    On Windows the video sits inside a window of this app (a normal window you can move by its
    title bar and resize by its edges): the browser's window is put inside it. Windows doesn't let
    one program keep another program's window above a fullscreen game, but the app can keep its
    own window there, the same way as the timer at the top of the screen.
    """

    def __init__(self, profile_dir, root=None, on_closed=None, setup_window=None):
        self.profile_dir = profile_dir  # the browser's own settings for this window (cookies etc.)
        self.root = root                # Tk root (Windows: the video's window is a Tk Toplevel)
        self.on_closed = on_closed      # called when the window gets closed with its X
        self.setup_window = setup_window  # called with the new Toplevel (dark title bar, icon)
        self.proc = None
        self.server = None
        self.host = None      # the app's window around the video (Windows)
        self.holder = None
        self.hwnd = None      # the browser's window (inside self.host on Windows)
        self.click_through = False
        self.opacity = 100
        self.rect = None  # x, y, width, height (screen pixels) of the video area
        self.error = ""
        self.extra_args = []
        self.opened_at = 0.0
        self.tuck = 0          # how far the browser's own title bar is pushed up out of sight
        self.last_size = (0, 0)
        self.moved_at = 0.0

    def command(self, name, value=0):
        """A video key: "seek" (seconds), "volume" (+/- percent), "mute", "pause", "speed" (+1 / -1),
        "load" ({"video", "start", "label"}). The page picks it up within a fifth of a second."""
        if self.server is not None:
            self.server.commands.append([name, value])
            del self.server.commands[:-20]

    # ------------------------------------------------------------ open / close

    def is_open(self):
        if self.server is None:
            return False
        if IS_WIN:
            if self.hwnd is not None:
                return bool(_u.IsWindow(self.hwnd))
            return time.time() - self.opened_at < 30  # still opening
        return self.proc is not None and self.proc.poll() is None

    def _browser_pid(self):
        """The Edge/Chrome still running with this window's profile (even with no window left), or None."""
        if not IS_WIN:
            return None
        h = _u.FindWindowW("Chrome_MessageWindow", os.path.normpath(self.profile_dir))
        return _window_pid(h) if h else None

    def _kill_browser(self, wait=3.0):
        pid = self._browser_pid()
        if not pid:
            return
        subprocess.call(["taskkill", "/T", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, creationflags=0x08000000)
        end = time.time() + wait
        while self._browser_pid() and time.time() < end:
            time.sleep(0.1)

    def open(self, link, rect=None):
        """Show the video. link = parse_link(...) result. Returns True, or False with self.error set."""
        self.close()
        self._kill_browser()  # one left over from before would show an old, dead page
        browser = find_browser()
        if not browser:
            self.error = ("Couldn't find Microsoft Edge or Google Chrome, which the video window uses."
                          if IS_WIN else "The video window needs Google Chrome or Microsoft Edge.")
            return False
        self.server = _Server()
        self.server.page = page_html(link, self.server.port).encode("utf-8")
        self.rect = rect or self.rect or (60, 120, 640, 360)
        x, y, w, h = self.rect
        if IS_WIN:
            bx, by = -32000, -32000  # the browser's own window opens out of sight, then moves into ours
        else:
            bx, by = x, y
        os.makedirs(self.profile_dir, exist_ok=True)
        args = [browser, f"--app=http://127.0.0.1:{self.server.port}/",
                f"--user-data-dir={self.profile_dir}",
                "--no-first-run", "--no-default-browser-check", "--disable-session-crashed-bubble",
                "--autoplay-policy=no-user-gesture-required", "--disable-features=Translate,msEdgeTranslate",
                f"--window-position={bx},{by}", f"--window-size={w},{h}"] + self.extra_args
        try:
            kw = {"creationflags": 0x08000000} if IS_WIN else {}  # no console window
            self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, **kw)
        except OSError as e:
            self.error = f"Couldn't start the browser for the video: {e}"
            self.server.close()
            self.server = None
            return False
        self.hwnd = None
        self.tuck = 0
        self.last_size = (0, 0)
        self.moved_at = 0.0
        self.opened_at = time.time()
        if IS_WIN and self.root is not None:
            self._make_host()
        return True

    def _make_host(self):
        import tkinter as tk
        x, y, w, h = self.rect
        host = self.host = tk.Toplevel(self.root, bg="black")
        host.title("Video - Macro Recorder")
        host.geometry(f"{w}x{h}+{x}+{y}")
        host.minsize(160, 90)
        host.attributes("-topmost", True)
        host.protocol("WM_DELETE_WINDOW", self._user_closed)
        self.holder = tk.Frame(host, bg="black")
        self.holder.pack(fill="both", expand=True)
        self.loading = tk.Label(self.holder, text="Loading the video…", bg="black", fg="#9b9ba6",
                                font=("Segoe UI", 10))
        self.loading.place(relx=0.5, rely=0.5, anchor="center")
        self.holder.bind("<Configure>", lambda e: self._fit())
        if self.setup_window:
            try:
                self.setup_window(host)
            except Exception:
                pass
        host.update_idletasks()
        self._apply_style()

    def _host_hwnd(self):
        if self.host is None:
            return None
        try:
            wid = self.host.winfo_id()
        except Exception:
            return None
        return _u.GetParent(wid) or wid

    def _user_closed(self):
        self.close()
        if self.on_closed:
            self.on_closed()

    def close(self, wait=False):
        """wait=True (when the app quits): make sure the browser is gone before returning."""
        if self.server is None and self.host is None:
            return
        self._remember_rect()
        if IS_WIN and self.hwnd and _u.IsWindow(self.hwnd):
            _u.PostMessageW(self.hwnd, 0x10, 0, 0)  # WM_CLOSE: a normal close, no "restore pages?" next time
        elif not IS_WIN and self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass
        self._ended(wait)

    def _ended(self, wait=False):
        self.proc = None
        self.hwnd = None
        if self.host is not None:
            try:
                self.host.destroy()
            except Exception:
                pass
            self.host = self.holder = None
        if self.server is not None:
            self.server.close()
            self.server = None
        pid = self._browser_pid()
        if pid:
            # Edge sometimes keeps running in the background after its window closes; end it
            def finish():
                end = time.time() + 3
                while self._browser_pid() == pid and time.time() < end:
                    time.sleep(0.2)
                if self._browser_pid() == pid:
                    subprocess.call(["taskkill", "/T", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, creationflags=0x08000000)
            if wait:
                finish()
            else:
                threading.Thread(target=finish, daemon=True).start()

    # ------------------------------------------------------------ while open

    def poll(self):
        """Returns False once the window has been closed."""
        if self.server is None:
            return False
        if not self.is_open():
            self._ended()
            return False
        if not IS_WIN:
            return True
        if self.hwnd is None:
            hwnd = _find_window(TITLE)
            if hwnd is None:
                return True  # still opening
            self.hwnd = hwnd
            if self.host is not None:
                self._adopt()
        else:
            self._remember_rect()
            self._fit(check_tuck=True)
        top = self._host_hwnd() or self.hwnd
        # stay above the game (it can push itself to the front when it gets fullscreen)
        _u.SetWindowPos(top, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        return True

    def _adopt(self):
        """Put the browser's window inside ours, without its frame."""
        style = _u.GetWindowLongW(self.hwnd, GWL_STYLE)
        style &= ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
        _u.SetWindowLongW(self.hwnd, GWL_STYLE, style | WS_CHILD)
        _u.SetParent(self.hwnd, self.holder.winfo_id())
        try:
            self.loading.place_forget()
        except Exception:
            pass
        self._fit()
        self._apply_style()

    def _fit(self, check_tuck=False):
        if self.hwnd is None or self.holder is None:
            return
        try:
            w, h = self.holder.winfo_width(), self.holder.winfo_height()
        except Exception:
            return
        srv = self.server
        # the page says how tall it is (after our last move): the rest is the browser's title bar
        if check_tuck and srv is not None and srv.inner_height and srv.reported_at > self.moved_at + 0.3:
            bar = self.last_size[1] - srv.inner_height
            if 0 <= bar <= 120:
                self.tuck = bar
        size = (w, h + self.tuck)
        if size == self.last_size:
            return
        self.last_size = size
        self.moved_at = time.time()
        _u.MoveWindow(self.hwnd, 0, -self.tuck, size[0], size[1], True)

    def _remember_rect(self):
        if self.host is not None:
            try:
                if self.host.state() == "normal":
                    self.rect = (self.host.winfo_x(), self.host.winfo_y(),
                                 self.holder.winfo_width(), self.holder.winfo_height())
            except Exception:
                pass

    def set_click_through(self, on):
        self.click_through = bool(on)
        self._apply_style()

    def set_opacity(self, percent):
        self.opacity = max(20, min(100, int(percent)))
        self._apply_style()

    def _apply_style(self):
        top = self._host_hwnd() if IS_WIN else None
        if not top:
            return
        ex = _u.GetWindowLongW(top, GWL_EXSTYLE)
        want = ex & ~(WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
        if self.click_through:
            want |= WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_LAYERED
        if self.click_through or self.opacity < 100:
            want |= WS_EX_LAYERED
        else:
            want &= ~WS_EX_LAYERED
        if want != ex:
            _u.SetWindowLongW(top, GWL_EXSTYLE, want)
        if want & WS_EX_LAYERED:
            _u.SetLayeredWindowAttributes(top, 0, int(round(self.opacity * 2.55)), 2)  # LWA_ALPHA
        _u.SetWindowPos(top, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED)


# ---------------------------------------------------------------- Mac

class MacVideoOverlay:
    """The Mac video window: a floating panel of this app with Apple's own web view (the same
    engine as Safari) showing the same embedded-player page as on Windows. It floats above other
    apps and fullscreen games, lets clicks go through while a macro runs, and is moved and
    resized like any window. Needs PyObjC's WebKit part (pyobjc-framework-WebKit)."""

    # "direct": the page is handed straight to the web view (no web server, so less for macOS to
    # ask about); "server": from the same tiny 127.0.0.1 server as on Windows. Both loaded the
    # player and playlists the same on GitHub's Mac.
    PAGE_FROM = "direct"

    def __init__(self, profile_dir=None, root=None, on_closed=None, setup_window=None):
        import AppKit  # noqa: F401  (fails here, not later, if PyObjC isn't there)
        import WebKit  # noqa: F401
        self.root = root
        self.on_closed = on_closed
        self.panel = None
        self.web = None
        self.server = None
        self.click_through = False
        self.opacity = 100
        self.rect = None  # x, y, width, height of the video area, from the top left of the main screen
        self.error = ""
        self.extra_args = []

    def _screen_h(self):
        import AppKit
        return AppKit.NSScreen.screens()[0].frame().size.height

    def command(self, name, value=0):
        if self.web is not None:
            try:
                self.web.evaluateJavaScript_completionHandler_(
                    f"doCommand({json.dumps(name)}, {json.dumps(value)})", None)
            except Exception:
                pass

    def is_open(self):
        return self.panel is not None and bool(self.panel.isVisible())

    def open(self, link, rect=None):
        import AppKit
        import Foundation
        import WebKit
        self.close()
        self.rect = rect or self.rect or (60, 120, 640, 360)
        x, y, w, h = self.rect
        style = (AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable |
                 AppKit.NSWindowStyleMaskResizable | AppKit.NSWindowStyleMaskUtilityWindow |
                 AppKit.NSWindowStyleMaskNonactivatingPanel)
        frame = Foundation.NSMakeRect(x, self._screen_h() - y - h, w, h)
        panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False)
        panel.setTitle_("Video - Macro Recorder")
        panel.setReleasedWhenClosed_(False)
        panel.setHidesOnDeactivate_(False)   # panels hide when their app isn't in front; this one mustn't
        panel.setFloatingPanel_(True)
        panel.setLevel_(AppKit.NSStatusWindowLevel)  # above normal windows and fullscreen games
        panel.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
                                     AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary)
        panel.setMinSize_(Foundation.NSMakeSize(160, 120))
        panel.setBackgroundColor_(AppKit.NSColor.blackColor())
        config = WebKit.WKWebViewConfiguration.alloc().init()
        try:
            config.setMediaTypesRequiringUserActionForPlayback_(0)  # play with sound without a click
        except Exception:
            pass
        web = WebKit.WKWebView.alloc().initWithFrame_configuration_(panel.contentView().bounds(), config)
        web.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        panel.contentView().addSubview_(web)
        if self.PAGE_FROM == "server":
            # the same player page as on Windows, from the same tiny web server on 127.0.0.1
            self.server = _Server()
            self.server.page = page_html(link, self.server.port).encode("utf-8")
            url = Foundation.NSURL.URLWithString_(f"http://127.0.0.1:{self.server.port}/")
            web.loadRequest_(Foundation.NSURLRequest.requestWithURL_(url))
        else:
            # the page handed straight to the web view, as if it came from http://localhost
            page = (page_html(link, 0).replace('"http://127.0.0.1:0"', '"http://localhost"')
                    .replace("function report() {", "function report() { return;"))
            web.loadHTMLString_baseURL_(page, Foundation.NSURL.URLWithString_("http://localhost/"))
        self.panel, self.web = panel, web
        self._apply_style()
        panel.orderFrontRegardless()  # show it without taking the keyboard from the game
        return True

    def poll(self):
        if self.panel is None:
            return False
        if not self.is_open():  # closed with its red button
            self._ended()
            return False
        self._remember_rect()
        self.panel.orderFrontRegardless()
        return True

    def _remember_rect(self):
        if self.panel is None or self.panel.isMiniaturized():
            return
        c = self.panel.contentRectForFrameRect_(self.panel.frame())
        w, h = int(c.size.width), int(c.size.height)
        self.rect = (int(c.origin.x), int(self._screen_h() - c.origin.y - h), w, h)

    def set_click_through(self, on):
        self.click_through = bool(on)
        self._apply_style()

    def set_opacity(self, percent):
        self.opacity = max(20, min(100, int(percent)))
        self._apply_style()

    def _apply_style(self):
        if self.panel is not None:
            self.panel.setIgnoresMouseEvents_(self.click_through)
            self.panel.setAlphaValue_(self.opacity / 100.0)

    def close(self, wait=False):
        if self.panel is None:
            return
        self._remember_rect()
        self.panel.orderOut_(None)
        self._ended()

    def _ended(self):
        web, panel = self.web, self.panel
        self.web = self.panel = None
        if web is not None:
            try:
                web.pauseAllMediaPlaybackWithCompletionHandler_(None)
            except Exception:
                pass
            try:
                web.stopLoading()
                web.loadHTMLString_baseURL_("", None)  # stops the sound for sure
                web.removeFromSuperview()
            except Exception:
                pass
        if panel is not None:
            try:
                panel.close()
            except Exception:
                pass
        if self.server is not None:
            self.server.close()
            self.server = None


def make_overlay(profile_dir, root=None, on_closed=None, setup_window=None):
    """The right video window for this computer (Windows: VideoOverlay, unchanged)."""
    if IS_MAC:
        try:
            return MacVideoOverlay(profile_dir, root, on_closed, setup_window)
        except ImportError:
            pass  # no PyObjC WebKit (running from source without it): the browser's own window
    return VideoOverlay(profile_dir, root, on_closed, setup_window)
