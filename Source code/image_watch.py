"""Watch the screen for a picture (like a "MISSION COMPLETED" banner).

Only ordinary screenshots are used: nothing reads or touches the game itself.
The picture is matched on its bright parts (text, lines) and the pixels right around them, so a
background that changes from one time to the next doesn't stop it from being found.
"""

import base64
import os

import cv2
import mss
import numpy as np

cv2.setNumThreads(1)  # use one CPU core only, so the game keeps the rest

WORK_MAX_HEIGHT = 70  # the picture is shrunk to about this height for matching (fast, still precise)
# also try slightly smaller/bigger sizes, in case the game shows it at another size
SIZE_STEPS = tuple(round(0.86 + 0.02 * i, 2) for i in range(15))  # 0.86 .. 1.14


def _soften(gray):
    return cv2.GaussianBlur(gray, (3, 3), 0)


def _patch_std(gray, w, h):
    """Standard deviation of every w x h patch, laid out like matchTemplate's result."""
    s1, s2 = cv2.integral2(gray, sdepth=cv2.CV_64F)
    n = float(w * h)
    a = s1[h:, w:] - s1[:-h, w:] - s1[h:, :-w] + s1[:-h, :-w]
    b = s2[h:, w:] - s2[:-h, w:] - s2[h:, :-w] + s2[:-h, :-w]
    var = b / n - (a / n) ** 2
    return np.sqrt(np.maximum(var, 0.0))


def primary_monitor(sct):
    return sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]


def screen_origin(sct=None):
    """Top-left corner of the main screen, to turn positions on a screenshot into mouse positions."""
    own = sct is None
    if own:
        sct = mss.mss()
    try:
        mon = primary_monitor(sct)
        return mon["left"], mon["top"]
    finally:
        if own:
            sct.close()


def grab_screen(sct=None):
    """Screenshot of the main screen as a BGR image, one pixel per mouse position.

    On Windows (the app is DPI aware) that's the real pixels. A Mac Retina screen has two pixels per
    mouse position each way, so its screenshot is shrunk to match the mouse and window positions."""
    own = sct is None
    if own:
        sct = mss.mss()
    try:
        mon = primary_monitor(sct)
        shot = sct.grab(mon)
        img = np.ascontiguousarray(np.asarray(shot)[:, :, :3])
        if img.shape[1] != mon["width"] or img.shape[0] != mon["height"]:
            img = cv2.resize(img, (mon["width"], mon["height"]), interpolation=cv2.INTER_AREA)
        return img
    finally:
        if own:
            sct.close()


def load_image(path):
    """Read a picture file (works with any characters in the path)."""
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("that isn't a picture this app can read (use PNG, JPG or BMP)")
    return img


def save_image(path, img):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("couldn't save the picture")
    buf.tofile(path)


def png_data(img, max_w=None, max_h=None):
    """PNG of the image as base64 text, for tk.PhotoImage(data=...). Shrunk to fit max_w x max_h."""
    h, w = img.shape[:2]
    f = 1.0
    if max_w:
        f = min(f, max_w / w)
    if max_h:
        f = min(f, max_h / h)
    if f < 1.0:
        img = cv2.resize(img, (max(1, int(w * f)), max(1, int(h * f))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", img)
    return base64.b64encode(buf.tobytes()).decode("ascii")


def feature_mask(gray):
    """Pixels that make up the picture's text/lines, plus a small border around them.

    Returns None when the picture has no clear bright parts (then the whole picture is matched)."""
    _, core = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    share = np.count_nonzero(core) / core.size
    if share > 0.5:  # light picture with dark text: the text is the dark part
        core = 255 - core
        share = 1 - share
    if share < 0.01:
        return None
    mask = cv2.dilate(core, np.ones((3, 3), np.uint8), iterations=2)
    if np.count_nonzero(mask) / mask.size > 0.85:
        return None
    return mask


class Matcher:
    """Finds one picture on screenshots."""

    def __init__(self, picture, picked_screen_h=None, ignore_background=True, screen_h=None):
        h, w = picture.shape[:2]
        if h < 8 or w < 8:
            raise ValueError("the picture is too small; pick a bigger area")
        # the picture was taken on a screen picked_screen_h tall; on another screen size it's
        # probably scaled the same way (game interfaces usually are)
        base = 1.0
        if picked_screen_h and screen_h:
            base = screen_h / picked_screen_h
        # how much screenshots are shrunk (smaller is faster): big pictures to about WORK_MAX_HEIGHT
        # tall, small ones (like a button's word) to 3/4, but never below 20 pixels so text stays readable
        hb = h * base
        self.work = min(1.0, max(20.0, min(hb * 0.75, WORK_MAX_HEIGHT)) / hb)
        gray = cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)
        self.templates = []  # (template, mask or None, size factor)
        for step in SIZE_STEPS:
            f = base * step * self.work
            tw, th = max(4, round(w * f)), max(4, round(h * f))
            t = cv2.resize(gray, (tw, th), interpolation=cv2.INTER_AREA)
            mask = feature_mask(t) if ignore_background else None
            self.templates.append((_soften(t), mask, base * step))
        self.last_best = SIZE_STEPS.index(1.0)
        # how much the picture varies (contrast); a matching spot on screen must vary about as much
        self.detail = max(4.0, float(_soften(self.templates[self.last_best][0]).std()))

    def find(self, screen, good_enough=None, quick=False):
        """Best match on a BGR screenshot: (score 0..1, (x, y, w, h) on the screen).

        With good_enough, stops as soon as a size scores at least that much (tries the size that
        matched best last time first, so a normal check takes one pass). quick only tries that size
        and the ones right next to it."""
        gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        if self.work < 1.0:
            gray = cv2.resize(gray, None, fx=self.work, fy=self.work, interpolation=cv2.INTER_AREA)
        gray = _soften(gray)
        best = (0.0, None)
        order = sorted(range(len(self.templates)), key=lambda i: abs(i - self.last_best))
        if quick:
            order = order[:3]
        for i in order:
            t, mask, _ = self.templates[i]
            th, tw = t.shape
            if th > gray.shape[0] or tw > gray.shape[1]:
                continue
            if mask is not None:
                res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED, mask=mask)
            else:
                res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
            res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
            np.clip(res, -1.0, 1.0, out=res)
            # On a plain area (like a black loading screen) the score is meaningless: OpenCV
            # reports a perfect 100% there. Only count spots with about as much detail as the picture.
            res[_patch_std(gray, tw, th) < 0.35 * self.detail] = 0.0
            _, score, _, (x, y) = cv2.minMaxLoc(res)
            if score > best[0]:
                inv = 1.0 / self.work
                best = (float(score), (int(x * inv), int(y * inv), int(tw * inv), int(th * inv)))
                best_i = i
                if good_enough is not None and score >= good_enough:
                    break
        if best[1] is not None and (good_enough is None or best[0] >= good_enough):
            self.last_best = best_i
        return best
