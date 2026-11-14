"""Reads the mouse's own movement (Windows Raw Input), the way games read it to turn the camera.

While a game like Roblox turns its camera (Shift Lock, or holding the right button), it hides the
pointer and keeps putting it back in the middle, so the pointer's position says nothing about how
far the mouse moved. Raw Input reports how far the mouse itself moved, every time it reports.

RawMouse(callback).start() runs a hidden window on its own thread and calls callback(dx, dy) for
every movement (on that thread). Only on Windows; elsewhere start() returns False."""

import sys
import threading

IS_WIN = sys.platform == "win32"

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    class RAWINPUTDEVICE(ctypes.Structure):
        _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                    ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]

    class RAWINPUTHEADER(ctypes.Structure):
        _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD), ("hDevice", wintypes.HANDLE),
                    ("wParam", wintypes.WPARAM)]

    class RAWMOUSE(ctypes.Structure):
        # usFlags is followed by a 4-byte-aligned union of ulButtons / {usButtonFlags, usButtonData}
        _fields_ = [("usFlags", wintypes.USHORT), ("_pad", wintypes.USHORT), ("usButtonFlags", wintypes.USHORT),
                    ("usButtonData", wintypes.USHORT), ("ulRawButtons", wintypes.ULONG),
                    ("lLastX", wintypes.LONG), ("lLastY", wintypes.LONG), ("ulExtraInformation", wintypes.ULONG)]

    class RAWINPUT(ctypes.Structure):
        _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]

    WM_INPUT, WM_CLOSE, WM_DESTROY = 0x00FF, 0x0010, 0x0002
    RID_INPUT, RIM_TYPEMOUSE = 0x10000003, 0
    RIDEV_INPUTSINK, RIDEV_REMOVE = 0x00000100, 0x00000001
    MOUSE_MOVE_ABSOLUTE = 0x01
    HWND_MESSAGE = wintypes.HWND(-3)

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
                                       ctypes.POINTER(wintypes.UINT), wintypes.UINT]
    user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class RawMouse:
    _class_registered = False

    def __init__(self, callback):
        self.callback = callback
        self.hwnd = None
        self.thread = None
        self.ready = threading.Event()
        self.ok = False

    def start(self):
        if not IS_WIN:
            return False
        self.thread = threading.Thread(target=self._run, daemon=True, name="raw-mouse")
        self.thread.start()
        self.ready.wait(3)
        return self.ok

    def stop(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self.thread is not None:
            self.thread.join(2)
        self.thread = None
        self.hwnd = None

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_INPUT:
            try:
                raw = RAWINPUT()
                size = wintypes.UINT(ctypes.sizeof(raw))
                got = user32.GetRawInputData(lparam, RID_INPUT, ctypes.byref(raw), ctypes.byref(size),
                                             ctypes.sizeof(RAWINPUTHEADER))
                if got != 0xFFFFFFFF and raw.header.dwType == RIM_TYPEMOUSE \
                        and not raw.mouse.usFlags & MOUSE_MOVE_ABSOLUTE:
                    dx, dy = raw.mouse.lLastX, raw.mouse.lLastY
                    if dx or dy:
                        self.callback(dx, dy)
            except Exception:
                pass
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run(self):
        try:
            hinst = kernel32.GetModuleHandleW(None)
            self._wndproc = WNDPROC(self._proc)  # kept, so it isn't freed while Windows uses it
            name = "MacroRecorderRawMouse%d" % id(self)
            wc = WNDCLASSW()
            wc.lpfnWndProc = self._wndproc
            wc.hInstance = hinst
            wc.lpszClassName = name
            if not user32.RegisterClassW(ctypes.byref(wc)):
                raise OSError("RegisterClass failed")
            self.hwnd = user32.CreateWindowExW(0, name, "raw mouse", 0, 0, 0, 0, 0, HWND_MESSAGE, None,
                                               hinst, None)
            if not self.hwnd:
                raise OSError("CreateWindow failed")
            dev = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, self.hwnd)  # generic desktop, mouse
            if not user32.RegisterRawInputDevices(ctypes.byref(dev), 1, ctypes.sizeof(dev)):
                raise OSError("RegisterRawInputDevices failed")
            self.ok = True
        except Exception:
            self.ok = False
            self.ready.set()
            return
        self.ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        try:
            dev = RAWINPUTDEVICE(0x01, 0x02, RIDEV_REMOVE, None)
            user32.RegisterRawInputDevices(ctypes.byref(dev), 1, ctypes.sizeof(dev))
        except Exception:
            pass
