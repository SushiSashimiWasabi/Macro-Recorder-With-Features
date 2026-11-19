"""The app's own windows that must not count as "seen" by the macro (2.13 review, candidate C).

The timer at the top, the "Bring it to front" button, the keys-on-screen box and the guided tour all sit
on top of the screen the macro looks at. Each one tells this module where it is (set_rect, from the Tk
thread; None when it goes away), and every screenshot Picture watch, Wait for a picture, colour checks and
the results look at has those places blacked out (blank, from any thread): a plain black area never matches.

The main window has its own rectangle in MacroRecorder._hide_own_window. Discord's screenshot uses Windows'
"exclude from capture" instead (window_tools.hide_own_windows_from_capture), which is a different job: that
picture is meant to show the game, with the app taken out of it."""
import threading

_lock = threading.Lock()
_rects = {}  # name -> (x0, y0, x1, y1) on the screen


def set_rect(name, rect):
    """This window is now at rect (x0, y0, x1, y1), or (None) gone."""
    with _lock:
        if rect is None:
            _rects.pop(name, None)
        else:
            _rects[name] = tuple(int(v) for v in rect)


def rects_by_name():
    with _lock:
        return dict(_rects)


def blank(img, ox=0, oy=0):
    """Black out the registered windows on a screenshot whose top-left corner is the screen's (ox, oy)."""
    for x0, y0, x1, y1 in list(rects_by_name().values()):
        x0, y0, x1, y1 = max(0, x0 - ox), max(0, y0 - oy), min(img.shape[1], x1 - ox), min(img.shape[0], y1 - oy)
        if x1 > x0 and y1 > y0:
            img[y0:y1, x0:x1] = 0
    return img
