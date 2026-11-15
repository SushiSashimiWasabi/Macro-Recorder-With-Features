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


def grab_screen(sct=None, region=None):
    """Screenshot of the main screen as a BGR image, one pixel per mouse position.

    On Windows (the app is DPI aware) that's the real pixels. A Mac Retina screen has two pixels per
    mouse position each way, so its screenshot is shrunk to match the mouse and window positions.

    region (x0, y0, x1, y1 on the screen): only that part is taken (much faster); the rest of the
    image stays black, so positions on it are the same as on a full screenshot."""
    own = sct is None
    if own:
        sct = mss.mss()
    try:
        mon = primary_monitor(sct)
        if region is not None:
            x0, y0, x1, y1 = (int(v) for v in region)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(mon["width"], x1), min(mon["height"], y1)
            img = np.zeros((mon["height"], mon["width"], 3), np.uint8)
            if x1 - x0 < 1 or y1 - y0 < 1:
                return img
            shot = sct.grab({"left": mon["left"] + x0, "top": mon["top"] + y0,
                             "width": x1 - x0, "height": y1 - y0})
            part = np.asarray(shot)[:, :, :3]
            if part.shape[1] != x1 - x0 or part.shape[0] != y1 - y0:
                part = cv2.resize(part, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
            img[y0:y1, x0:x1] = part
            return img
        shot = sct.grab(mon)
        img = np.ascontiguousarray(np.asarray(shot)[:, :, :3])
        if img.shape[1] != mon["width"] or img.shape[0] != mon["height"]:
            img = cv2.resize(img, (mon["width"], mon["height"]), interpolation=cv2.INTER_AREA)
        return img
    finally:
        if own:
            sct.close()


def grab_part(x0, y0, x1, y1):
    """Only that part of the main screen, as its own small picture: (picture, the screen position
    of its top-left corner). Quicker than grab_screen(region=...), which makes a screen-sized one."""
    with mss.mss() as sct:
        mon = primary_monitor(sct)
        shot = sct.grab({"left": mon["left"] + x0, "top": mon["top"] + y0, "width": x1 - x0, "height": y1 - y0})
        img = np.ascontiguousarray(np.asarray(shot)[:, :, :3])
        if img.shape[1] != x1 - x0 or img.shape[0] != y1 - y0:  # (a Mac Retina screen)
            img = cv2.resize(img, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
        return img, (mon["left"] + x0, mon["top"] + y0)


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


# the quick rough look (see Matcher._look)
ROUGH_MIN_AREA = 40   # only when the area looked at is at least this many times the picture
ROUGH_MIN_SIDE = 8    # and the picture is still at least this big at half size
ROUGH_SPOTS = 6       # how many of the rough look's best spots get the exact look
ROUGH_TRUST = 0.0     # below this, the exact look goes over the whole area after all (0: never;
# checked on the real AOT:R screenshots in tests/data: the rough look never missed a picture that was there)
PLAIN_TRIES = 12      # best spots checked one by one for being plain, before checking every spot


def _rough_spots(gray, t, count):
    """The best few spots of a quick look (no mask), not right next to each other: [(x, y)]."""
    th, tw = t.shape
    if th > gray.shape[0] or tw > gray.shape[1]:
        return []
    res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
    res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0, copy=False)
    spots = []
    for _ in range(count):
        _, score, _, (x, y) = cv2.minMaxLoc(res)
        if score <= 0.1:
            break
        spots.append((x, y))
        res[max(0, y - th // 2):y + th // 2 + 1, max(0, x - tw // 2):x + tw // 2 + 1] = -1.0
    return spots


_half_cache = []  # [(prepared screenshot, at half size)], the last few


def _half(gray):
    with _prepared_lock:
        for g, h in _half_cache:
            if g is gray:
                return h
    half = cv2.resize(gray, (gray.shape[1] // 2, gray.shape[0] // 2), interpolation=cv2.INTER_AREA)
    with _prepared_lock:
        _half_cache.append((gray, half))
        del _half_cache[:-6]
    return half


_prepared_cache = []  # [(screenshot, work, prepared picture)], the last few
_prepared_lock = __import__("threading").Lock()


def _prepared(screen, work):
    """The screenshot in grey, shrunk by work and softened, as every Matcher compares it. Several
    pictures looked for on the same screenshot share this work (it's the slow part of a look)."""
    with _prepared_lock:
        for shot, w, gray in _prepared_cache:
            if shot is screen and w == work:
                return gray
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    if work < 1.0:
        gray = cv2.resize(gray, None, fx=work, fy=work, interpolation=cv2.INTER_AREA)
    gray = _soften(gray)
    with _prepared_lock:
        _prepared_cache.append((screen, work, gray))
        del _prepared_cache[:-6]
    return gray


class Matcher:
    """Finds one picture on screenshots."""

    def __init__(self, picture, picked_screen_h=None, ignore_background=True, screen_h=None, work_height=None):
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
        # (work_height: shrink more, for big pictures like a title that's looked for often)
        self.work = min(1.0, max(20.0, min(hb * 0.75, work_height or WORK_MAX_HEIGHT)) / hb)
        gray = cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)
        self.templates = []  # (template, mask or None, size factor)
        for step in SIZE_STEPS:
            f = base * step * self.work
            tw, th = max(4, round(w * f)), max(4, round(h * f))
            t = cv2.resize(gray, (tw, th), interpolation=cv2.INTER_AREA)
            mask = feature_mask(t) if ignore_background else None
            self.templates.append((_soften(t), mask, base * step))
        # the same sizes at half size without the mask, for the quick rough look (None: too small for it)
        self.rough = []
        for t, mask, _ in self.templates:
            th, tw = t.shape
            if mask is None or min(th, tw) < 2 * ROUGH_MIN_SIDE:
                self.rough.append(None)
            else:
                self.rough.append(cv2.resize(t, (tw // 2, th // 2), interpolation=cv2.INTER_AREA))
        self.last_best = SIZE_STEPS.index(1.0)
        self.last_rect = None  # where it was last found on the screen (x, y, w, h)
        # how much the picture varies (contrast); a matching spot on screen must vary about as much
        self.detail = max(4.0, float(_soften(self.templates[self.last_best][0]).std()))

    def near_last_area(self):
        """(x0, y0, x1, y1): the part of the screen around where it was found last time, or None."""
        if self.last_rect is None:
            return None
        x, y, w, h = self.last_rect
        pad_x, pad_y = w // 2 + 40, h // 2 + 40  # room for a slightly bigger size or a small shift
        return x - pad_x, y - pad_y, x + w + pad_x, y + h + pad_y

    def find_near_last(self, screen, good_enough=None):
        """Like find(), but only looks around the spot where the picture was found last time
        (a small part of the screen: many times faster). (0.0, None) if it was never found yet."""
        area = self.near_last_area()
        if area is None:
            return 0.0, None
        return self.find(screen, good_enough, quick=True, area=area)

    def find(self, screen, good_enough=None, quick=False, remember=True, area=None):
        """Best match on a BGR screenshot: (score 0..1, (x, y, w, h) on the screen).

        With good_enough, stops as soon as a size scores at least that much (tries the size that
        matched best last time first, so a normal check takes one pass). quick only tries that size
        and the ones right next to it. area (x0, y0, x1, y1 on the screenshot): only look there."""
        if area is None:
            result = self._find(screen, good_enough, quick)
        else:
            H, W = screen.shape[:2]
            x0, y0 = max(0, int(area[0])), max(0, int(area[1]))
            x1, y1 = min(W, int(area[2])), min(H, int(area[3]))
            if x1 - x0 < 8 or y1 - y0 < 8:
                return 0.0, None
            # cut the part out of the whole prepared (shrunk) screenshot, not out of the screenshot
            # itself: shrinking a cut-out lines its pixels up differently, which can cost a few % of the score
            gray = _prepared(screen, self.work)
            sx0, sy0 = int(x0 * self.work), int(y0 * self.work)
            sx1, sy1 = int(np.ceil(x1 * self.work)), int(np.ceil(y1 * self.work))
            result = self._find(None, good_enough, quick, gray=gray[sy0:sy1, sx0:sx1], offset=(sx0, sy0))
        if remember and result[1] is not None and (good_enough is None or result[0] >= good_enough):
            self.last_rect = result[1]
        return result

    def _find(self, screen, good_enough, quick, gray=None, offset=(0, 0)):
        if gray is None:
            gray = _prepared(screen, self.work)
        best = (0.0, None)
        best_i = None
        order = sorted(range(len(self.templates)), key=lambda i: abs(i - self.last_best))
        if quick:
            order = order[:3]
        for i in order:
            t, mask, _ = self.templates[i]
            th, tw = t.shape
            if th > gray.shape[0] or tw > gray.shape[1]:
                continue
            score, (x, y) = self._look(gray, i, good_enough)
            if score > best[0]:
                inv = 1.0 / self.work
                ox, oy = offset
                best = (float(score), (int((x + ox) * inv), int((y + oy) * inv), int(tw * inv), int(th * inv)))
                best_i = i
                if good_enough is not None and score >= good_enough:
                    break
        if best[1] is not None and (good_enough is None or best[0] >= good_enough):
            self.last_best = best_i
        return best

    def _look(self, gray, i, good_enough=None):
        """The best score of template size i on the prepared screenshot, and where: (score, (x, y)).

        On a big area a quick rough look (half size, without the mask) comes first and the exact look
        only goes over the few spots it liked best, which is several times quicker. The exact look
        alone is used when the area is small, or when the rough look found nothing clear."""
        t, mask, _ = self.templates[i]
        th, tw = t.shape
        rough = self.rough[i]
        if rough is not None and gray.size >= ROUGH_MIN_AREA * t.size:
            spots = _rough_spots(_half(gray), rough, ROUGH_SPOTS)
            if spots:
                best = (0.0, (0, 0))
                H, W = gray.shape
                pad = max(4, min(tw, th) // 2)
                for rx, ry in spots:
                    x0, y0 = max(0, 2 * rx - pad), max(0, 2 * ry - pad)
                    x1, y1 = min(W, 2 * rx + tw + pad), min(H, 2 * ry + th + pad)
                    score, (x, y) = self._exact(gray[y0:y1, x0:x1], t, mask)
                    if score > best[0]:
                        best = (score, (x + x0, y + y0))
                        if good_enough is not None and score >= good_enough:
                            break
                if best[0] >= ROUGH_TRUST:
                    return best
        return self._exact(gray, t, mask)

    def _exact(self, gray, t, mask):
        th, tw = t.shape
        if th > gray.shape[0] or tw > gray.shape[1]:
            return 0.0, (0, 0)
        if mask is not None:
            res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED, mask=mask)
        else:
            res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
        res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0, copy=False)
        np.clip(res, -1.0, 1.0, out=res)
        # On a plain area (like a black loading screen) the score is meaningless: OpenCV reports a
        # perfect 100% there. Only spots with about as much detail as the picture count. That's
        # checked at the best spots one by one (quick); when many of them are plain (a loading
        # screen), the detail of every spot is worked out at once instead.
        floor = 0.35 * self.detail
        for _ in range(PLAIN_TRIES):
            _, score, _, (x, y) = cv2.minMaxLoc(res)
            if score <= 0.0:
                return 0.0, (x, y)
            if gray[y:y + th, x:x + tw].std() >= floor:
                return float(score), (x, y)
            # a plain spot: rule it and the spots right next to it out, then look at the next best
            res[max(0, y - 2):y + 3, max(0, x - 2):x + 3] = 0.0
        res[_patch_std(gray, tw, th) < floor] = 0.0
        _, score, _, (x, y) = cv2.minMaxLoc(res)
        return float(score), (x, y)
