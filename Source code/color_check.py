"""Colour check (2.12): a picture-free condition for If, Retry and Wait: "this colour shows (or doesn't)
at the spot I picked" or "anywhere on the screen". It only looks at screenshots.

A step or condition that checks a colour has "color_on": True and
  rgb [r, g, b], tolerance (0-100 %: how far each of red / green / blue may be off),
  x, y (the spot, in screen pixels, fitted like clicks), area (1 = one pixel, 5 = a 5x5 square),
  hold (seconds it must stay before it counts), where ("spot" or "screen").
"The whole screen" needs a patch of at least MIN_PATCH x MIN_PATCH pixels of the colour (so single
stray pixels don't count) and is looked at less often."""
AREAS = (1, 5)
WHERE = ("spot", "area", "screen")
MIN_PATCH = 6
SPOT_EVERY = 0.1     # seconds between looks at a spot
SCREEN_EVERY = 0.5   # and at the whole screen (heavier)


def hex_of(rgb):
    try:
        r, g, b = (max(0, min(255, int(v))) for v in rgb)
    except (TypeError, ValueError):
        return "#000000"
    return f"#{r:02x}{g:02x}{b:02x}"


def clean(h):
    """The colour fields of a step or condition from a file (maybe someone else's), checked."""
    if not isinstance(h, dict):
        return h
    h["color_on"] = h.get("color_on") is True
    if not h["color_on"] and not any(k in h for k in ("rgb", "tolerance", "area", "hold", "where")):
        return h
    rgb = h.get("rgb")
    try:
        h["rgb"] = [max(0, min(255, int(v))) for v in rgb][:3] if isinstance(rgb, list) and len(rgb) == 3 else None
    except (TypeError, ValueError, OverflowError):
        h["rgb"] = None
    h["tolerance"] = _whole(h.get("tolerance"), 10, 0, 100)
    h["area"] = h.get("area") if h.get("area") in AREAS else 1
    try:
        hold = float(h.get("hold", 0) or 0)
        h["hold"] = round(max(0.0, min(60.0, hold)), 2) if hold == hold else 0.0
    except (TypeError, ValueError):
        h["hold"] = 0.0
    h["where"] = h.get("where") if h.get("where") in WHERE else "spot"
    for k in ("x", "y", "x0", "y0", "x1", "y1"):
        if k in h:
            h[k] = _whole(h.get(k), 0, -100000, 100000)
    if h["where"] == "area" and all(k in h for k in ("x0", "y0", "x1", "y1")):
        h["x0"], h["x1"] = sorted((h["x0"], h["x1"]))
        h["y0"], h["y1"] = sorted((h["y0"], h["y1"]))
    return h


def _whole(value, default, low, high):
    try:
        if isinstance(value, bool):
            raise ValueError
        v = float(value)
        if v != v:
            raise ValueError
        return max(low, min(high, int(v)))
    except (TypeError, ValueError, OverflowError):
        return default


def describe(h):
    if h.get("where") == "area":
        where = "in the area I drew" if "x0" in h else "(no area drawn yet)"
    else:
        where = "anywhere on the screen" if h.get("where") == "screen" else (
            f"at {h.get('x')}, {h.get('y')}" if "x" in h else "(no spot picked yet)")
    return f"the colour {hex_of(h.get('rgb') or [0, 0, 0])} {where}"


def ready(h):
    """Can it be checked? (a colour picked, and a spot unless it looks at the whole screen)"""
    if h.get("where") == "area":
        return bool(h.get("rgb")) and all(k in h for k in ("x0", "y0", "x1", "y1"))
    return bool(h.get("rgb")) and (h.get("where") == "screen" or ("x" in h and "y" in h))


def every(h):
    """How often to look: a spot often, a big area or the whole screen less often (they cost more)."""
    if h.get("where") == "screen":
        return SCREEN_EVERY
    if h.get("where") == "area":
        w, hh = abs(h.get("x1", 0) - h.get("x0", 0)), abs(h.get("y1", 0) - h.get("y0", 0))
        return SCREEN_EVERY if w * hh > 400 * 400 else SPOT_EVERY * 2
    return SPOT_EVERY


_screens = None


def screens_box():
    """(left, top, right, bottom) of all screens together, in main-screen pixels (Kong's left screen
    is at -1920). Areas are cut to this, so a file can't ask for a giant screenshot."""
    global _screens
    if _screens is None:
        try:
            import image_watch

            with image_watch.mss.mss() as sct:
                every, main = sct.monitors[0], image_watch.primary_monitor(sct)
                left, top = every["left"] - main["left"], every["top"] - main["top"]
                _screens = (left, top, left + every["width"], top + every["height"])
        except Exception:
            _screens = (-16384, -16384, 16384, 16384)
    return _screens


def _cut(x0, y0, x1, y1):
    left, top, right, bottom = screens_box()
    x0, x1 = max(left, min(right - 1, x0)), max(left + 1, min(right, x1))
    y0, y1 = max(top, min(bottom - 1, y0)), max(top + 1, min(bottom, y1))
    return x0, y0, max(x0 + 1, x1), max(y0 + 1, y1)


def _region(h):
    """(picture, its top-left on the screen, how much it was shrunk) of where this check looks."""
    import image_watch

    where = h.get("where")
    if where == "screen":
        shot = image_watch.grab_screen()
        return shot[::2, ::2], (0, 0), 2
    if where == "area":
        x0, y0, x1, y1 = _cut(*(int(h[k]) for k in ("x0", "y0", "x1", "y1")))
        img, origin = image_watch.grab_part(x0, y0, x1, y1)
        return img, origin, 1
    area = h.get("area", 1) if h.get("area") in AREAS else 1
    half = area // 2
    x, y = int(h.get("x", 0)), int(h.get("y", 0))
    img, origin = image_watch.grab_part(x - half, y - half, x + half + 1, y + half + 1)
    return img, origin, 1


def look(h):
    """Look now: (seen, the best match in %, where on the screen the best match was)."""
    import numpy as np

    rgb = h.get("rgb")
    if not ready(h):
        return False, 0, None
    img, origin, shrink = _region(h)
    if img is None or not img.size:
        return False, 0, None
    want = np.array([rgb[2], rgb[1], rgb[0]], np.int16)
    off = np.abs(img[:, :, :3].astype(np.int16) - want).max(axis=2)
    y, x = np.unravel_index(int(off.argmin()), off.shape)
    best = int(round(100 - off[y, x] * 100 / 255))
    return seen(h), best, (origin[0] + int(x) * shrink, origin[1] + int(y) * shrink)


def _mask(img, rgb, tolerance):
    import numpy as np

    want = np.array([rgb[2], rgb[1], rgb[0]], np.int16)  # (screenshots are blue, green, red)
    off = tolerance * 255 / 100.0
    return (np.abs(img[:, :, :3].astype(np.int16) - want) <= off).all(axis=2)


def seen(h):
    """Does the colour show right now? (one look)"""
    import image_watch

    rgb, tol = h.get("rgb"), h.get("tolerance", 10)
    if not rgb:
        return False
    if h.get("where") in ("screen", "area"):
        import cv2
        import numpy as np

        img, _origin, shrink = _region(h)  # (the whole screen at half size: lighter, a patch still shows)
        if img is None or not img.size:
            return False
        mask = _mask(img, rgb, tol).astype(np.uint8)
        k = max(1, (MIN_PATCH if h.get("where") == "screen" else 3) // shrink)  # (an area: 3 x 3)
        return bool(cv2.erode(mask, np.ones((k, k), np.uint8)).any())
    area = h.get("area", 1) if h.get("area") in AREAS else 1
    half = area // 2
    x, y = int(h.get("x", 0)), int(h.get("y", 0))
    img, _origin = image_watch.grab_part(x - half, y - half, x + half + 1, y + half + 1)
    if img is None or not img.size:
        return False
    return bool(_mask(img, rgb, tol).mean() >= 0.5)  # (most of the square has the colour)
