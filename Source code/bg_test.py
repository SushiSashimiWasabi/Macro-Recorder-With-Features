"""Test background playback against one window, without focusing it.

    py bg_test.py notepad      # sanity check: types into Notepad, reads the text back
    py bg_test.py roblox       # probes a Roblox window and measures what changes on screen

For Roblox, each probe takes a picture of the window before and after (PrintWindow,
which works even if the window is behind others) and reports how much changed,
compared with how much it changes on its own when nothing is sent.
"""

import ctypes
import sys
import time
from ctypes import wintypes

import background as bg

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.GetForegroundWindow.restype = wintypes.HWND


def find_window(word):
    word = word.lower()
    hits = [(h, t) for h, t in bg.list_windows() if word in t.lower()]
    # prefer an exact app title
    hits.sort(key=lambda ht: len(ht[1]))
    return hits[0] if hits else (None, None)


def window_rect(hwnd):
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, r.right, r.bottom  # screen left, top, width, height


def capture(hwnd, tries=20):
    """Like _capture_once, but skips the blank all-white frames PrintWindow
    sometimes returns for game windows (they made every probe look like ~133)."""
    for _ in range(tries):
        frame = _capture_once(hwnd)
        if frame and min(frame) < 250:
            return frame
        time.sleep(0.05)
    return frame


def _capture_once(hwnd):
    """Grayscale pixels of the window's client area as bytes (PrintWindow)."""
    _, _, w, h = window_rect(hwnd)
    hdc = user32.GetDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 0x1 | 0x2)  # client only, full content
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]
    bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bih), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    raw = buf.raw
    step = 16  # sample every 16th pixel, enough to see change
    return bytes(raw[i + 1] for i in range(0, len(raw), 4 * step))


def diff(a, b):
    n = min(len(a), len(b))
    if not n:
        return 0.0
    return sum(abs(a[i] - b[i]) for i in range(n)) / n


def report_focus(hwnd):
    fg = user32.GetForegroundWindow()
    print(f"  target focused? {'YES (test not valid for background)' if fg == hwnd else 'no'}")


def notepad_test():
    hwnd, title = find_window("notepad")
    if not hwnd:
        print("Open Notepad first.")
        return
    print(f"Notepad window: {title!r}")
    report_focus(hwnd)
    p = bg.BackgroundPlayer(hwnd)
    for ch in "hello bg":
        vk = user32.VkKeyScanW(ord(ch)) & 0xFF
        p.key(vk, True)
        p.key(vk, False)
        time.sleep(0.03)
    time.sleep(0.5)
    target = p._key_target()
    n = user32.GetWindowTextLengthW(target)
    text = ctypes.create_unicode_buffer(n + 1)
    user32.SendMessageW(target, 0x000D, n + 1, text)  # WM_GETTEXT
    print(f"  text in Notepad now: {text.value[-40:]!r}")


def roblox_test():
    hwnd, title = find_window("roblox")
    if not hwnd:
        print("Open Roblox first.")
        return
    left, top, w, h = window_rect(hwnd)
    print(f"Roblox window: {title!r}, {w}x{h} at ({left},{top})")
    report_focus(hwnd)
    cx, cy = left + w // 2, top + h // 2
    p = bg.BackgroundPlayer(hwnd)
    W, A, SPACE = 0x57, 0x41, 0x20

    def hold_key(vk, secs):
        p.key(vk, True)
        end = time.time() + secs
        while time.time() < end:  # repeat like a held key
            time.sleep(0.05)
        p.key(vk, False)

    def drag(button, dx):
        p.mouse_move(cx, cy)
        p.mouse_button(cx, cy, button, True)
        for i in range(1, 21):
            p.mouse_move(cx + dx * i // 20, cy)
            time.sleep(0.03)
        p.mouse_button(cx + dx, cy, button, False)

    def move_only(dx):
        for i in range(1, 21):
            p.mouse_move(cx + dx * i // 20, cy)
            time.sleep(0.03)

    probes = [
        ("nothing (baseline)", lambda: time.sleep(2)),
        ("hold W 2 s (walk forward)", lambda: hold_key(W, 2)),
        ("hold A 2 s (walk left)", lambda: hold_key(A, 2)),
        ("Space (jump)", lambda: (hold_key(SPACE, 0.2), time.sleep(1.5))),
        ("move mouse only (camera in shift-lock)", lambda: (move_only(300), time.sleep(1))),
        ("right-drag (rotate camera)", lambda: (drag("right", 300), time.sleep(1))),
        ("left click", lambda: (p.mouse_button(cx, cy, "left", True), time.sleep(0.1),
                                p.mouse_button(cx, cy, "left", False), time.sleep(1.5))),
        ("scroll (zoom)", lambda: (p.scroll(cx, cy, 0, -3), time.sleep(1.5))),
    ]
    results = []
    for name, action in probes:
        before = capture(hwnd)
        action()
        after = capture(hwnd)
        d = diff(before, after)
        results.append((name, d))
        print(f"  {name:42s} change {d:6.2f}")
        time.sleep(1)
    base = results[0][1]
    print(f"\nBaseline change with no input: {base:.2f}. Probes far above it probably worked.")
    report_focus(hwnd)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "notepad"
    notepad_test() if which == "notepad" else roblox_test()
