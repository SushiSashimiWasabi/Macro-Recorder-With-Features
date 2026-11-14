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


def hide_own_windows_from_capture(hide):
    """Make this app's own windows (main window, timer at the top, Settings, video...) invisible to
    screenshots (hide=True), or visible again. Screenshots then show what's behind them, like the game.
    Windows 10 (2004) and newer; elsewhere nothing happens. Returns how many windows were changed."""
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
                if user32.SetWindowDisplayAffinity(hwnd, 0x11 if hide else 0):  # WDA_EXCLUDEFROMCAPTURE / NONE
                    changed.append(hwnd)
            return True
        user32.EnumWindows(callback, 0)
    except Exception:
        pass
    return len(changed)
