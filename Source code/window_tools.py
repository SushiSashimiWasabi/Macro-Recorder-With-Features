"""Small Windows helpers about windows and the mouse: which window is in front, which program it
belongs to, where its inside (client area) is on the screen, whether the mouse pointer is hidden
(a game turning its camera, like Roblox's Shift Lock), and which mouse buttons are held.

On other systems every function answers "don't know" (None / False / empty), so callers simply
skip the feature there."""

import os
import sys

IS_WIN = sys.platform == "win32"

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    class CURSORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hCursor", wintypes.HANDLE),
                    ("ptScreenPos", wintypes.POINT)]

    GA_ROOT = 2
    CURSOR_SHOWING = 0x1
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def foreground():
    """The window in front (its top-level window), or None."""
    if not IS_WIN:
        return None
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        return user32.GetAncestor(hwnd, GA_ROOT) or hwnd
    except Exception:
        return None


def pid_of(hwnd):
    if not IS_WIN or not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value or None


def exe_of(hwnd):
    """The program file name of a window, like 'RobloxPlayerBeta.exe' (None if unknown)."""
    pid = pid_of(hwnd)
    if not pid:
        return None
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
    finally:
        kernel32.CloseHandle(handle)
    return None


def exe_path_of(hwnd):
    """The whole path of a window's program file (None if unknown)."""
    pid = pid_of(hwnd)
    if not pid:
        return None
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
    finally:
        kernel32.CloseHandle(handle)
    return None


def original_name(path):
    """(2.12) The name a program file was built with (its "OriginalFilename"), like 'PowerShell.EXE' for a
    copy of PowerShell renamed to notepad2.exe. "" when it has none."""
    if not IS_WIN or not path:
        return ""
    try:
        version = ctypes.WinDLL("version")
        size = version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return ""
        data = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(path, 0, size, data):
            return ""
        ptr, length = ctypes.c_void_p(), wintypes.UINT()
        if not version.VerQueryValueW(data, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(length)) \
                or length.value < 4:
            langs = [(0x0409, 0x04B0)]
        else:
            raw = ctypes.cast(ptr, ctypes.POINTER(wintypes.WORD * 2)).contents
            langs = [(raw[0], raw[1]), (0x0409, 0x04B0), (0x0409, 0x04E4)]
        for lang, cp in langs:
            key = f"\\StringFileInfo\\{lang:04x}{cp:04x}\\OriginalFilename"
            if version.VerQueryValueW(data, key, ctypes.byref(ptr), ctypes.byref(length)) and length.value:
                name = ctypes.wstring_at(ptr.value, length.value).rstrip("\0").strip()
                return name[:-4] if name.lower().endswith(".mui") else name  # ("Cmd.Exe.MUI")
    except Exception:
        return ""
    return ""


def class_of(hwnd):
    if not IS_WIN or not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256)
    return buf.value


# (2.12) programs a macro may never type into: command windows, the registry, the Run box (explorer), ...
NEVER_TYPE_INTO = {"cmd.exe", "powershell.exe", "pwsh.exe", "powershell_ise.exe", "windowsterminal.exe", "wt.exe",
                   "openconsole.exe", "conhost.exe", "regedit.exe", "regedt32.exe", "mmc.exe", "explorer.exe",
                   "wscript.exe", "cscript.exe", "bash.exe", "wsl.exe", "wslhost.exe", "mshta.exe", "rundll32.exe",
                   "taskmgr.exe", "msiexec.exe", "control.exe", "ssh.exe"}
CONSOLE_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "PseudoConsoleWindow"}


def moved_game_file(path):
    """A saved game file that is gone (Roblox puts every update in a new ...\\Versions\\version-xxx folder):
    the same file name in the newest sibling folder, or None when there is none. A link (roblox://...) or a file
    that is still there comes back as it was."""
    if not path or "://" in path or os.path.exists(path):
        return path
    versions = os.path.dirname(os.path.dirname(path))
    try:
        found = [os.path.join(versions, d, os.path.basename(path)) for d in os.listdir(versions)]
        found = [p for p in found if os.path.isfile(p)]
        return max(found, key=os.path.getmtime) if found else None
    except OSError:
        return None


def never_type_into(hwnd=None, exe=None):
    """(2.12) Is this a window (or program name) a macro must never type into? Checked by the program's
    file name, the name it was built with (a renamed copy) and the kind of window (any console), never
    by its title."""
    if exe and os.path.basename(str(exe)).lower() in NEVER_TYPE_INTO:
        return True
    if not hwnd or not IS_WIN:
        return False
    if class_of(hwnd) in CONSOLE_CLASSES:
        return True
    path = exe_path_of(hwnd)
    if path and os.path.basename(path).lower() in NEVER_TYPE_INTO:
        return True
    return bool(path) and original_name(path).lower() in NEVER_TYPE_INTO


def title_of(hwnd):
    if not IS_WIN or not hwnd:
        return ""
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def client_rect(hwnd):
    """The inside of a window (no title bar or borders) on the screen: (x, y, w, h), or None."""
    if not IS_WIN or not hwnd:
        return None
    try:
        r = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(r)):
            return None
        p = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(p))
        w, h = r.right - r.left, r.bottom - r.top
        if w < 50 or h < 50:
            return None
        return (p.x, p.y, w, h)
    except Exception:
        return None


def is_window(hwnd):
    return bool(IS_WIN and hwnd and user32.IsWindow(hwnd))


FRIENDLY_NAMES = {"robloxplayerbeta.exe": "Roblox", "windows10universal.exe": "Roblox"}


def friendly_name(exe):
    """(Preview 4) A short name for a program file to show people: 'Roblox' for RobloxPlayerBeta.exe,
    else the file name without .exe ('' when unknown)."""
    if not exe:
        return ""
    base = str(exe).replace("\\", "/").rsplit("/", 1)[-1]
    return FRIENDLY_NAMES.get(base.lower()) or os.path.splitext(base)[0]


def program_info(hwnd):
    """What a recording remembers about the window it was made in."""
    exe = exe_of(hwnd)
    if not exe:
        return None
    info = {"exe": exe, "title": title_of(hwnd)}
    rect = client_rect(hwnd)
    if rect:
        info["client"] = list(rect)
    return info


def app_windows():
    """(2.11) The windows a person would switch to: visible, with a title, not a tool window or hidden
    by Windows (cloaked), minimized ones too. [(hwnd, title, program file name)], in Alt+Tab order."""
    if not IS_WIN:
        return []
    found = []
    try:
        dwm = ctypes.windll.dwmapi
    except Exception:
        dwm = None

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        try:
            title = title_of(hwnd)
            if not user32.IsWindowVisible(hwnd) or not title or title == "Program Manager":
                return True
            if user32.GetWindowLongW(hwnd, -20) & 0x80:  # (WS_EX_TOOLWINDOW)
                return True
            if dwm is not None:
                cloaked = wintypes.DWORD()
                if dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 \
                        and cloaked.value:
                    return True
            found.append((hwnd, title, exe_of(hwnd) or ""))
        except Exception:
            pass
        return True

    user32.EnumWindows(callback, 0)
    return found


def windows_of(exe):
    """Visible top-level windows of a program (by its file name), biggest first."""
    if not IS_WIN or not exe:
        return []
    found = []
    want = exe.lower()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        try:
            if user32.IsWindowVisible(hwnd) and title_of(hwnd):
                name = exe_of(hwnd)
                if name and name.lower() == want:
                    rect = client_rect(hwnd)
                    found.append((rect[2] * rect[3] if rect else 0, hwnd))
        except Exception:
            pass
        return True

    user32.EnumWindows(callback, 0)
    found.sort(key=lambda t: -t[0])
    return [hwnd for _, hwnd in found]


def bring_to_front(hwnd):
    """Put a window in front (works when this app is the one in front, as after pressing Play)."""
    if not is_window(hwnd):
        return False
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        return False


def force_to_front(hwnd):
    """Put a window in front even when another program is in front (Windows normally only lets
    the program in front do that). Used when Play comes from the phone remote: nobody is at the
    PC to click the game. True when the window ended up in front."""
    if not is_window(hwnd):
        return False
    try:
        import time

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        if user32.GetForegroundWindow() == hwnd:
            return True
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.05)
        if user32.GetForegroundWindow() == hwnd:
            return True
        # as if this thread belonged to the program in front: then Windows allows it
        fg = user32.GetForegroundWindow()
        me = kernel32.GetCurrentThreadId()
        other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        attached = bool(other and other != me and user32.AttachThreadInput(me, other, True))
        try:
            user32.BringWindowToTop(wintypes.HWND(hwnd))
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(me, other, False)
        time.sleep(0.05)
        if user32.GetForegroundWindow() == hwnd:
            return True
        # last try: after a tap of Alt, Windows lets any program choose the window in front
        user32.keybd_event(0x12, 0, 0, 0)
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.05)
        return user32.GetForegroundWindow() == hwnd
    except Exception:
        return False


def close_window(hwnd):
    """Ask a window to close, as its X button would."""
    if IS_WIN and hwnd:
        user32.PostMessageW(wintypes.HWND(hwnd), 0x0010, 0, 0)  # WM_CLOSE


def cursor_hidden():
    """True while the mouse pointer is hidden (a game turning its camera). None = can't tell."""
    if not IS_WIN:
        return None
    try:
        ci = CURSORINFO()
        ci.cbSize = ctypes.sizeof(CURSORINFO)
        if not user32.GetCursorInfo(ctypes.byref(ci)):
            return None
        return not (ci.flags & CURSOR_SHOWING)
    except Exception:
        return None


def held_mouse_buttons():
    """Mouse buttons held down right now: names like 'left' (as pynput names them)."""
    if not IS_WIN:
        return []
    held = []
    swapped = bool(user32.GetSystemMetrics(23))  # SM_SWAPBUTTON: GetAsyncKeyState reads the real button
    for vk, name in ((0x01, "left"), (0x02, "right"), (0x04, "middle")):
        if user32.GetAsyncKeyState(vk) & 0x8000:
            if swapped and name in ("left", "right"):
                name = "right" if name == "left" else "left"
            held.append(name)
    return held


ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x00000001, 0x00000002


def keep_awake(on):
    """While on: Windows doesn't go to sleep or turn the screen off by itself (a long wait in a macro
    has no key presses to keep it awake). Call it on/off from the same thread. Sleep or shut down
    chosen by the user (or by "Stop by itself") still works."""
    if not IS_WIN:
        return
    try:
        kernel32.SetThreadExecutionState.restype = ctypes.c_uint
        kernel32.SetThreadExecutionState.argtypes = [ctypes.c_uint]
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED if on else 0)
        kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass


def process_health():
    """How heavy this app is right now, for the log: {"memory_mb", "gdi", "user"} (what can be read
    here). Memory is the app's own (private) memory; gdi / user are Windows drawing and window handles
    (a number that keeps growing over a long run means a leak)."""
    info = {}
    try:
        if IS_WIN:
            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + \
                           [(n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize",
                                                           "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                                                           "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                                                           "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            proc = kernel32.GetCurrentProcess()
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            psapi = ctypes.WinDLL("psapi")
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
            if psapi.GetProcessMemoryInfo(proc, ctypes.byref(pmc), pmc.cb):
                info["memory_mb"] = round(pmc.PrivateUsage / 1048576)
            user32.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            info["gdi"] = user32.GetGuiResources(proc, 0)
            info["user"] = user32.GetGuiResources(proc, 1)
        else:
            import resource

            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            info["memory_mb"] = round(peak / (1048576 if sys.platform == "darwin" else 1024))  # (the peak)
    except Exception:
        pass
    return info


def set_thread_priority(level):
    """The calling thread's priority: 1 = above normal (playback), -1 = below normal (screen checks)."""
    if not IS_WIN:
        return
    try:
        kernel32.GetCurrentThread.restype = wintypes.HANDLE
        kernel32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
        kernel32.SetThreadPriority(kernel32.GetCurrentThread(), int(level))
    except Exception:
        pass


def hide_own_windows_from_capture(hide, area=None):
    """Make this app's own windows (main window, timer at the top, Settings, video...) invisible to
    screenshots (hide=True), or visible again. Screenshots then show what's behind them, like the game.
    Windows 10 (2004) and newer; elsewhere nothing happens. Returns how many windows were changed.
    area (x, y, w, h): when hiding, only windows that show in that part of the screen are counted and
    hidden (a minimized one, or one on another screen, isn't in the picture anyway)."""
    if not IS_WIN:
        return 0
    import os as _os
    own = _os.getpid()
    changed = []
    try:
        user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _):
            if pid_of(hwnd) == own and user32.IsWindowVisible(hwnd):
                if hide and area is not None:
                    if user32.IsIconic(hwnd):
                        return True
                    r = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(r))
                    ax, ay, aw, ah = area
                    if r.right <= ax or r.left >= ax + aw or r.bottom <= ay or r.top >= ay + ah:
                        return True
                if user32.SetWindowDisplayAffinity(hwnd, 0x11 if hide else 0):  # WDA_EXCLUDEFROMCAPTURE / NONE
                    changed.append(hwnd)
            return True
        user32.EnumWindows(callback, 0)
    except Exception:
        pass
    return len(changed)
