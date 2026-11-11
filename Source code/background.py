"""Experimental background playback: send recorded input to one window with
ordinary Windows messages (PostMessage), without moving the real cursor or
taking keyboard focus.

Many apps accept this. Many games, Roblox included, read the mouse and keyboard
in other ways and may ignore it, especially when they aren't focused.
"""

import ctypes
import sys
from ctypes import wintypes

if sys.platform != "win32":  # pragma: no cover
    raise ImportError("background playback only works on Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)

WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_MOUSEWHEEL, WM_MOUSEHWHEEL = 0x020A, 0x020E
MK_LBUTTON, MK_RBUTTON, MK_SHIFT, MK_CONTROL, MK_MBUTTON = 0x1, 0x2, 0x4, 0x8, 0x10
MAPVK_VK_TO_VSC = 0
CWP_SKIPINVISIBLE = 0x1

VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
SHIFT_VKS = {0x10, 0xA0, 0xA1}
CTRL_VKS = {0x11, 0xA2, 0xA3}
ALT_VKS = {0x12, 0xA4, 0xA5}
# keys whose scan code needs the "extended" flag
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E,
                0x5B, 0x5C, 0x5D, 0x6F, 0x90, 0xA3, 0xA5}

BUTTON_MSGS = {
    "left": (WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON),
    "right": (WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON),
    "middle": (WM_MBUTTONDOWN, WM_MBUTTONUP, MK_MBUTTON),
}

user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ChildWindowFromPointEx.argtypes = [wintypes.HWND, wintypes.POINT, wintypes.UINT]
user32.ChildWindowFromPointEx.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.IsChild.argtypes = [wintypes.HWND, wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def list_windows():
    """Visible top-level windows with a title, as [(hwnd, title)]."""
    found = []

    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found


def is_usable(hwnd):
    return bool(user32.IsWindow(hwnd))


def is_minimized(hwnd):
    return bool(user32.IsIconic(hwnd))


def _make_lparam(lo, hi):
    return ((hi & 0xFFFF) << 16) | (lo & 0xFFFF)


class BackgroundPlayer:
    """Replays events into one window. Positions in the recording are screen
    positions; they're turned into positions inside the window, so the window
    should be where it was when the macro was recorded."""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.buttons = 0  # MK_* flags currently "held"
        self.mods = set()  # "shift", "ctrl", "alt"
        self.last_point = (0, 0)

    # -------------------------------------------------------------- targets

    def _key_target(self):
        """The control inside the target window that has keyboard focus, if any."""
        thread = user32.GetWindowThreadProcessId(self.hwnd, None)
        info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
        if user32.GetGUIThreadInfo(thread, ctypes.byref(info)) and info.hwndFocus:
            focus = info.hwndFocus
            if focus == self.hwnd or user32.IsChild(self.hwnd, focus):
                return focus
        return self.hwnd

    def _mouse_target(self, sx, sy):
        """(window, client x, client y) for a screen position."""
        pt = wintypes.POINT(sx, sy)
        user32.ScreenToClient(self.hwnd, ctypes.byref(pt))
        target = self.hwnd
        child = user32.ChildWindowFromPointEx(self.hwnd, wintypes.POINT(pt.x, pt.y), CWP_SKIPINVISIBLE)
        if child and child != self.hwnd:
            cpt = wintypes.POINT(sx, sy)
            user32.ScreenToClient(child, ctypes.byref(cpt))
            return child, cpt.x, cpt.y
        return target, pt.x, pt.y

    def _wparam_flags(self):
        flags = self.buttons
        if "shift" in self.mods:
            flags |= MK_SHIFT
        if "ctrl" in self.mods:
            flags |= MK_CONTROL
        return flags

    # -------------------------------------------------------------- input

    def mouse_move(self, sx, sy):
        self.last_point = (sx, sy)
        target, x, y = self._mouse_target(sx, sy)
        user32.PostMessageW(target, WM_MOUSEMOVE, self._wparam_flags(), _make_lparam(x, y))

    def mouse_button(self, sx, sy, button, pressed):
        if button not in BUTTON_MSGS:
            return
        down, up, flag = BUTTON_MSGS[button]
        if pressed:
            self.buttons |= flag
        else:
            self.buttons &= ~flag
        target, x, y = self._mouse_target(sx, sy)
        user32.PostMessageW(target, down if pressed else up, self._wparam_flags(), _make_lparam(x, y))

    def scroll(self, sx, sy, dx, dy):
        target, _, _ = self._mouse_target(sx, sy)
        lparam = _make_lparam(sx, sy)  # wheel messages use screen positions
        if dy:
            user32.PostMessageW(target, WM_MOUSEWHEEL, _make_lparam(self._wparam_flags(), int(dy * 120)), lparam)
        if dx:
            user32.PostMessageW(target, WM_MOUSEHWHEEL, _make_lparam(self._wparam_flags(), int(dx * 120)), lparam)

    def key(self, vk, pressed):
        if vk in SHIFT_VKS:
            (self.mods.add if pressed else self.mods.discard)("shift")
        elif vk in CTRL_VKS:
            (self.mods.add if pressed else self.mods.discard)("ctrl")
        elif vk in ALT_VKS:
            (self.mods.add if pressed else self.mods.discard)("alt")

        scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
        lparam = 1 | (scan << 16)
        if vk in EXTENDED_VKS:
            lparam |= 1 << 24
        alt = "alt" in self.mods
        if alt:
            lparam |= 1 << 29
        if not pressed:
            lparam |= (1 << 30) | (1 << 31)
        if alt or vk in ALT_VKS:
            msg = WM_SYSKEYDOWN if pressed else WM_SYSKEYUP
        else:
            msg = WM_KEYDOWN if pressed else WM_KEYUP
        user32.PostMessageW(self._key_target(), msg, vk, ctypes.c_ssize_t(lparam & 0xFFFFFFFF).value)

    def release_all(self, held_vks):
        for vk in list(held_vks):
            self.key(vk, False)
        for name, (_, _, flag) in BUTTON_MSGS.items():
            if self.buttons & flag:
                self.mouse_button(*self.last_point, name, False)
