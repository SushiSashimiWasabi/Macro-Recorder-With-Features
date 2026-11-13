"""A picture of your choice behind a window (the main window and the Settings window).

Tk can't make a frame or label see-through, so each plain part of the window gets its own piece
of the picture: frames get a picture label laid underneath their contents, text labels show their
text on top of their piece, small drawings (switches, the status dot) draw over theirs, and
checkboxes and text boxes take the piece's average colour. The picture is darkened so text stays
readable, and one area (the main panel, the settings page) is darkened a bit more, like tinted
glass. Buttons, boxes and the big cards stay solid.

An animated .gif plays: the finished picture of each frame is kept as one Tk picture, and every
part copies its piece out of it (a quick copy inside Tk), so the window doesn't flicker.

Needs numpy and opencv (already used by picture watch). Works on Windows and Mac.
"""

import base64
import bisect
import os
import shutil
import time
import tkinter as tk
from tkinter import ttk

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = np = None

AVAILABLE = cv2 is not None

PICTURE_TYPES = [("Pictures", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.gif"),
                 ("Animated pictures", "*.gif"), ("All files", "*.*")]
FITS = {"Fill the window": "cover", "Show the whole picture": "contain"}
POSITIONS = {"Top": 0, "Middle": 50, "Bottom": 100}  # older settings; now a 0-100 slider
STORED_NAME = "background.png"
MAX_SIDE = 2000  # pictures are stored at most this big (enough for the window, quick to load)

# animated pictures (.gif): how much memory their frames may take, and how fast they may play
ANIM_BYTES = 64 * 1024 * 1024        # the frames of one animation, shrunk to fit this
ANIM_DECODE_BYTES = 200 * 1024 * 1024  # read this much at a time (very long ones are cut short)
ANIM_MAX_FRAMES = 600
ANIM_WORK_SIDE = 1280                # frames are never kept bigger than this (plenty for the window)
ANIM_MIN_SIDE = 320                  # frames aren't shrunk below this; frames are dropped instead
ANIM_MIN_MS = 40                     # quickest frame (25 a second)
ANIM_CACHE_BYTES = 96 * 1024 * 1024  # finished frames kept ready per window (else made each time)

FRAME_CLASSES = {"Frame", "TFrame", "Tk", "Toplevel", "Labelframe", "TLabelframe", "TNotebook"}
LABEL_CLASSES = {"Label", "TLabel"}


def hex_to_bgr(color):
    color = color.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return np.array([b, g, r], dtype=np.float32)


def _to_bgr(img):
    """Any decoded picture as plain 8-bit BGR (see-through parts become dark)."""
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:  # see-through parts become dark
        alpha = img[:, :, 3:4].astype(np.float32) / 255
        img = (img[:, :, :3].astype(np.float32) * alpha).astype(np.uint8)
    if img.dtype != np.uint8:
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return img


def read_picture(path):
    """Read any picture file (also with non-English letters in its path). Returns BGR, or None.
    An animated picture gives its first frame."""
    if is_gif(path):
        anim = load_animation(path)
        return anim[0][0] if anim else None
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    except Exception:
        return None
    if img is None:
        return None
    return _to_bgr(img)


def is_gif(path):
    try:
        with open(path, "rb") as f:
            return f.read(6) in (b"GIF87a", b"GIF89a")
    except OSError:
        return False


_ANIMS = {}  # (path, mtime) -> (frames, durations in ms); the last few, as reading takes a moment


def load_animation(path):
    """The frames of a .gif: ([BGR pictures], [milliseconds each is shown]), or None.
    A .gif with one picture gives one frame. Big or long animations are shrunk to stay light."""
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None
    if key in _ANIMS:
        _ANIMS[key] = _ANIMS.pop(key)  # most recently used last
        return _ANIMS[key]
    result = None
    try:
        data = np.fromfile(path, dtype=np.uint8)
        w, h = int(data[6]) | int(data[7]) << 8, int(data[8]) | int(data[9]) << 8
        if hasattr(cv2, "imdecodeanimation") and w > 0 and h > 0:
            # read a batch of frames at a time and shrink them straight away, so a big animation
            # never needs all its frames at full size at once
            batch = int(max(1, min(ANIM_MAX_FRAMES, ANIM_DECODE_BYTES // (w * h * 4))))
            scale = min(1.0, ANIM_WORK_SIDE / max(w, h))
            size = (max(1, round(w * scale)), max(1, round(h * scale)))
            frames, durations = [], []
            while len(frames) < ANIM_MAX_FRAMES and sum(f.nbytes for f in frames[:1]) * len(frames) < 2 * ANIM_BYTES:
                try:
                    ok, anim = cv2.imdecodeanimation(data, start=len(frames), count=batch)
                except TypeError:  # an opencv that only reads it all at once
                    ok, anim = cv2.imdecodeanimation(data) if not frames else (False, None)
                if not ok or not len(anim.frames):
                    break
                got = [_to_bgr(f) for f in anim.frames]
                if scale < 1:
                    got = [cv2.resize(f, size, interpolation=cv2.INTER_AREA) for f in got]
                d = [int(v) for v in anim.durations] or [100]
                durations += (d + [d[-1]] * len(got))[:len(got)]
                frames += got
                if len(got) < batch:
                    break
            if frames:
                # like browsers: a frame that says "no time at all" gets a tenth of a second
                durations = [100 if d <= 10 else max(ANIM_MIN_MS, d) for d in durations]
                result = _lighten(frames, durations)
        if result is None:  # older opencv: the first frame, as a still picture
            img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
            if img is not None:
                result = ([_to_bgr(img)], [100])
    except Exception:
        result = None
    if result is not None:
        _ANIMS[key] = result
        for old in list(_ANIMS)[:-3]:
            del _ANIMS[old]
    return result


def _lighten(frames, durations):
    """Shrink the frames (and, for very long animations, drop some) to fit ANIM_BYTES."""
    h, w = frames[0].shape[:2]
    scale = min(1.0, MAX_SIDE / max(h, w))
    per_frame = ANIM_BYTES / (3 * len(frames))
    if w * h * scale * scale > per_frame:
        scale = max((per_frame / (w * h)) ** 0.5 * 0.98, min(1.0, ANIM_MIN_SIDE / min(h, w)))
    if scale < 1:
        size = (max(1, round(w * scale)), max(1, round(h * scale)))
        frames = [cv2.resize(f, size, interpolation=cv2.INTER_AREA) for f in frames]
    while len(frames) > 2 and sum(f.nbytes for f in frames) > ANIM_BYTES:
        durations = [sum(durations[i:i + 2]) for i in range(0, len(durations), 2)]
        frames = frames[::2]
    return frames, durations


def store_any(src_path, folder, stem):
    """Copy the chosen picture into the settings folder as <stem>.png, or, for an animated .gif,
    as it is, as <stem>.gif. Returns the stored file's name, or None if it can't be read."""
    if is_gif(src_path):
        anim = load_animation(src_path)
        if anim is None:
            return None
        if len(anim[0]) > 1:
            os.makedirs(folder, exist_ok=True)
            try:
                shutil.copyfile(src_path, os.path.join(folder, stem + ".gif"))
            except OSError:
                return None
            return stem + ".gif"
    return store_picture(src_path, folder, stem + ".png")


def store_picture(src_path, folder, name=STORED_NAME):
    """Copy the chosen picture into the settings folder (so it still works if the original is moved
    or deleted). Returns the stored file's name, or None if it isn't a picture we can read."""
    img = read_picture(src_path)
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    ok, data = cv2.imencode(".png", img)
    if not ok:
        return None
    os.makedirs(folder, exist_ok=True)
    data.tofile(os.path.join(folder, name))
    return name


_SIZES = {}


def picture_size(path):
    """(width, height) of a picture file, or None (remembered, so it's quick to ask again)."""
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None
    if key not in _SIZES:
        img = read_picture(path) if AVAILABLE else None
        _SIZES[key] = (img.shape[1], img.shape[0]) if img is not None else None
    return _SIZES[key]


def cut_axis_for(path, fit, width, height):
    """Which side of the picture is cut to fit a window of this size: "y", "x" or None."""
    size = picture_size(path) if path and fit == "cover" else None
    if not size or width < 2 or height < 2:
        return None
    w, h = size
    if abs(w / h - width / height) < 0.01:
        return None
    return "y" if w / h < width / height else "x"


_PPM = [True]  # Tk reads plain PPM data much quicker than PNG (if this Tk can)


def picture_data(img):
    """A BGR picture as data for a Tk picture: (data, format)."""
    if _PPM[0]:
        return b"P6\n%d %d\n255\n" % (img.shape[1], img.shape[0]) + img[:, :, ::-1].tobytes(), "ppm"
    ok, data = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    return base64.b64encode(data.tobytes()), "png"


def photo(img, into=None):
    """A Tk picture of a BGR picture (into: put it in this Tk picture instead of a new one)."""
    data, fmt = picture_data(img)
    try:
        if into is not None:
            into.tk.call(into, "put", data, "-format", fmt)
            return into
        return tk.PhotoImage(data=data, format=fmt)
    except tk.TclError:
        if not _PPM[0]:
            raise
        _PPM[0] = False
        return photo(img, into)


def hex_of(bgr):
    return "#%02x%02x%02x" % (int(bgr[2]), int(bgr[1]), int(bgr[0]))


class Backdrop:
    """Paints a picture behind the plain parts of one Tk window.

    see_through: the background colours that count as "plain" (they get the picture).
    glass: the widget whose area is drawn as tinted glass (a bit darker), e.g. the main panel.
    skip: widgets (and everything inside them) that stay as they are, e.g. the big buttons.
    lift_colors: text colours to make brighter while a picture is shown, {old: new}.
    """

    GLASS_BLUR = 0    # how blurry the picture is behind the glass area

    def __init__(self, root, see_through, base_color, glass=None, glass_color=None, glass_mix=0.2,
                 skip=(), lift_colors=None, border_color=None, area=None):
        """area: a function giving the widget the picture fills (None = the whole window); the rest
        stays plain."""
        self.root = root
        self.area = area
        self.see_through = {c.lower() for c in see_through}
        self.base = base_color
        self.glass = glass
        self.glass_color = glass_color or base_color
        self.glass_mix = glass_mix
        self.skip = set(skip)
        self.lift_colors = {k.lower(): v for k, v in (lift_colors or {}).items()}
        self.border = border_color
        self.style = ttk.Style(root)
        self.source = None      # the picture (BGR); of an animation, the frame that's showing
        self.source_key = None
        self.frames = None      # an animated picture's frames, else None
        self.frame_ends = []    # when each frame ends, in ms from the start of a round
        self.frame_i = 0
        self.animate = True     # play animated pictures (False: they stand still)
        self.paused = False     # stand still for now (while a macro records or plays)
        self.fps = 15           # at most this many pictures a second
        self.may_animate = None  # a function: False = stand still for now (e.g. another window in front)
        self.anim_job = None
        self.anim_start = 0.0
        self.masters = {}       # frame number -> the finished picture of the whole window, in Tk
        self.master = None      # ... or just the one that's showing, when they'd take too much room
        self.composite_frame = None  # which frame self.composite shows
        self.last_tick_ms = 0.0
        self.darkness = 0.5
        self.fit = "cover"
        self.position = 0.0
        self.composite = None   # the finished picture for the whole window
        self.composite_size = None
        self.composite_key = None
        self.items = {}         # widget -> what we changed (to undo it)
        self.pending = None
        self.pending_fix = None
        self._probe = self._probe_ttk = None
        self._new_widgets = False
        root.bind("<Configure>", self._root_changed, add="+")

    # ------------------------------------------------------------ public

    @property
    def active(self):
        return self.source is not None

    def set_picture(self, path, darkness=50, fit="cover", position=0.0):
        """Show the picture at path (None or "" = no picture, the plain window)."""
        if not AVAILABLE or not path or not os.path.isfile(path):
            self._no_picture()
            return path is None or path == ""
        key = (path, os.path.getmtime(path))
        darkness_now = max(0.0, min(0.95, darkness / 100))
        if key == self.source_key and self.composite is not None and \
                (self.darkness, self.fit, self.position) == (darkness_now, fit, position):
            return True  # nothing changed: repainting would only make the window flicker
        if key != self.source_key:
            anim = load_animation(path) if is_gif(path) else None
            img = anim[0][0] if anim else read_picture(path)
            if img is None:
                self._no_picture()
                return False
            self._stop_animation()
            self.source, self.source_key = img, key
            self.frames, self.frame_i, self.frame_ends = None, 0, []
            if anim and len(anim[0]) > 1:
                self.frames = anim[0]
                total = 0
                for d in anim[1]:
                    total += d
                    self.frame_ends.append(total)
        self.darkness = max(0.0, min(0.95, darkness / 100))
        self.fit = fit
        self.position = position
        self._forget_composite()
        self.repaint()
        self._start_animation()
        return True

    def _no_picture(self):
        self._stop_animation()
        self.source, self.source_key, self.frames = None, None, None
        self.clear()

    def _forget_composite(self):
        self.composite = None
        self.composite_frame = None
        self.masters = {}
        self.master = None

    # ------------------------------------------------------------ animated pictures

    @property
    def animated(self):
        return self.frames is not None

    def set_animate(self, on):
        """Play animated pictures, or let them stand still (the Settings switch)."""
        if bool(on) != self.animate:
            self.animate = bool(on)
            self._start_animation()

    def set_fps(self, fps):
        """Show at most this many pictures a second (Settings > Background, 5 to 30)."""
        self.fps = max(1, min(60, int(fps)))

    def set_paused(self, paused):
        """Stand still for now, e.g. while a macro records or plays (keeps its timing exact)."""
        if bool(paused) != self.paused:
            self.paused = bool(paused)
            self._start_animation()

    def _playing(self):
        return self.frames is not None and self.animate and not self.paused

    def _stop_animation(self):
        if self.anim_job is not None:
            try:
                self.root.after_cancel(self.anim_job)
            except tk.TclError:
                pass
            self.anim_job = None

    def _start_animation(self):
        self._stop_animation()
        if not self._playing():
            return
        # go on from the frame that's showing
        begun = self.frame_ends[self.frame_i - 1] if self.frame_i else 0
        self.anim_start = time.perf_counter() - begun / 1000
        self.anim_job = self.root.after(ANIM_MIN_MS, self._tick)

    def _tick(self):
        self.anim_job = None
        if not self._playing():
            return
        delay = 200  # hidden, minimized or not wanted right now: just look again a little later
        try:
            allowed = self.may_animate is None or self.may_animate()
            if allowed and self._shown():
                t0 = time.perf_counter()
                total = self.frame_ends[-1]
                pos = ((t0 - self.anim_start) * 1000) % total
                i = min(bisect.bisect_right(self.frame_ends, pos), len(self.frames) - 1)
                if i != self.frame_i:
                    self._show_frame(i)
                spent = (time.perf_counter() - t0) * 1000
                self.last_tick_ms = spent
                # the rest of this frame's time, but always leave the window as much time for
                # everything else as the frame took (a slow PC shows fewer frames instead of lagging)
                # no more than self.fps pictures a second (fewer = less work for the computer)
                delay = max(self.frame_ends[i] - pos - spent, spent, 10, 1000 / self.fps - spent)
        except tk.TclError:
            return  # the window is gone
        self.anim_job = self.root.after(int(delay), self._tick)

    def _show_frame(self, i):
        """Show frame i: every part copies its piece out of the frame's finished picture."""
        self.frame_i = i
        self.source = self.frames[i]
        root = self.root
        size = (root.winfo_width(), root.winfo_height())
        if size[0] < 2 or size[1] < 2:
            return
        if self.area is not None:
            a = self.area()
            if a is None or not a.winfo_ismapped():
                return
        if self.composite_key != (size, self._area_rect(*size)) or not self.items:
            self._crop_all()  # the window changed: everything is laid out again anyway
            return
        master = self._master(i)
        W, H = size
        call = root.tk.call
        for w, it in self.items.items():
            rect, img = it.get("rect"), it.get("img")
            if rect is None or img is None or it.get("covered"):
                continue
            x, y, cw, ch = rect
            if it.get("box") or x < 0 or y < 0 or x + cw > W or y + ch > H:
                photo(self._piece(it, rect), into=img)  # needs drawing on, or sticks out
            else:
                call(img, "copy", master, "-from", x, y, x + cw, y + ch)

    def _master(self, i):
        """The finished picture of the whole window for frame i, as a Tk picture."""
        m = self.masters.get(i)
        if m is not None:
            return m
        self.composite = self._compose(*self.composite_size)
        self.composite_frame = i
        h, w = self.composite.shape[:2]
        if w * h * 4 * len(self.frames) <= ANIM_CACHE_BYTES:
            m = self.masters[i] = photo(self.composite)  # kept: the next rounds only copy
        else:
            m = self.master = photo(self.composite, into=self.master)
        return m

    def _fresh_composite(self):
        """Make sure self.composite shows the frame that's on screen."""
        if self.frames is not None and self.composite is not None and self.composite_frame != self.frame_i:
            self.composite = self._compose(*self.composite_size)
            self.composite_frame = self.frame_i

    def repaint(self):
        """Lay the picture under every plain part of the window again (after layout changes)."""
        self.pending = None
        if not self.active or not self._shown():
            return
        root = self.root
        root.update_idletasks()
        new_labels = self._decorate(root)
        root.update_idletasks()  # labels let go of their stretching first, then are measured
        for w in new_labels:
            self._size_label(w)
        root.update_idletasks()
        self._crop_all()

    def refresh(self):
        """Call after texts may have changed or parts of the window were shown, hidden or added.
        A label that got a picture keeps its old size until it may measure its new text."""
        if not self.active or not self._shown():
            return
        changed = [w for w, it in self.items.items()
                   if it["kind"] == "label" and w.winfo_exists() and str(w.cget("text")) != it["text"]]
        new_labels = self._decorate(self.root, dry=True)
        if not changed and not new_labels and not self._new_widgets:
            return
        if not new_labels and not self._new_widgets and self.composite is not None:
            # only texts changed: each label gets its new piece in one go, so nothing flashes
            for w in changed:
                self._retext(w)
            if self.pending_fix is None:  # parts that moved because of it get their piece right after
                self.pending_fix = self.root.after(1, self._fix_moved)
            return
        for w in changed:
            self._undo(w, forget=False)
        if changed:  # let them measure their new text, then give them their picture again
            self.root.update_idletasks()
            for w in changed:
                if w.winfo_exists():
                    self._size_label(w)
        self.repaint()

    text_changed = refresh

    def _fix_moved(self):
        self.pending_fix = None
        if self.active and self._shown():
            # labels that just got a longer text may not have their new size yet (Tk sizes them
            # when idle, and this timer can run first); measuring them now would give them a
            # piece of their OLD size, leaving the rest of the label as a dark box
            self.root.update_idletasks()
            self._crop_all()

    def _natural_size(self, w, it):
        """The size a label wants for its text right now (measured on a spare label that's never
        shown, so the real one doesn't have to drop its picture first)."""
        pad = it["pad"]
        try:
            if w.winfo_class() == "TLabel":
                if self._probe_ttk is None:
                    self._probe_ttk = ttk.Label(self.root, style="Bd.TLabel")
                probe = self._probe_ttk
                probe.config(text=w.cget("text"), font=w.cget("font"), padding=pad["padding"],
                             width=w.cget("width"), wraplength=w.cget("wraplength"))
            else:
                if self._probe is None:
                    self._probe = tk.Label(self.root)
                probe = self._probe
                probe.config(text=w.cget("text"), font=w.cget("font"), wraplength=w.cget("wraplength"),
                             justify=w.cget("justify"),
                             **{k: pad[k] for k in ("padx", "pady", "bd", "highlightthickness", "width", "height")})
            return probe.winfo_reqwidth(), probe.winfo_reqheight()
        except (tk.TclError, KeyError):
            return w.winfo_width(), w.winfo_height()

    def _retext(self, w):
        """A label with a picture got a new text: give it its piece at its new size straight away."""
        it = self.items[w]
        self._fresh_composite()
        width, height = self._natural_size(w, it)
        stretch = it.get("stretch", (False, False))
        if stretch[0]:  # stretched by its row: keeps that width
            width = w.winfo_width()
        if stretch[1]:
            height = w.winfo_height()
        width, height = max(1, width), max(1, height)
        x, y = self._pos(w)
        img = photo(self._crop(w, (width, height)))
        it["img"], it["text"], it["rect"] = img, str(w.cget("text")), (x, y, width, height)
        w.config(image=img)

    def clear(self):
        """Back to the plain window."""
        for w in list(self.items):
            self._undo(w)
        self.items.clear()
        self._forget_composite()

    def cut_axis(self):
        """Which side of the picture gets cut to fit the window: "y" (top/bottom), "x" (left/right),
        or None (nothing is cut)."""
        if self.source is None or self.fit != "cover":
            return None
        h, w = self.source.shape[:2]
        W, H = max(1, self.root.winfo_width()), max(1, self.root.winfo_height())
        if abs(w / h - W / H) < 0.01:
            return None
        return "y" if w / h < W / H else "x"

    # ------------------------------------------------------------ the picture

    def _shown(self):
        try:
            return bool(self.root.winfo_ismapped())
        except tk.TclError:
            return False

    def _area_rect(self, width, height):
        """Where the picture goes: the whole window, or only the area widget (e.g. the settings page)."""
        a = self.area() if self.area else None
        if a is None or not a.winfo_ismapped():
            return 0, 0, width, height
        x, y = self._pos(a)
        return x, y, max(1, a.winfo_width()), max(1, a.winfo_height())

    def _compose(self, width, height):
        src = self.source
        h, w = src.shape[:2]
        ax, ay, aw, ah = self._area_rect(width, height)
        s = max(aw / w, ah / h) if self.fit == "cover" else min(aw / w, ah / h)
        nw, nh = max(1, round(w * s)), max(1, round(h * s))
        if self.frames is not None:  # quick, it's done for every frame
            how = cv2.INTER_AREA if s < 0.5 else cv2.INTER_LINEAR
        else:
            how = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
        img = cv2.resize(src, (nw, nh), interpolation=how)
        base = self._flat(self.base, width, height)
        out = base.copy()
        # the slider position moves the picture along the side that's cut off ("cover");
        # a picture that fits whole stays in the middle
        p = self.position if self.fit == "cover" else 0.5
        ox = ax + round((aw - nw) * p)
        oy = ay + round((ah - nh) * p)
        x0, y0 = max(ox, ax, 0), max(oy, ay, 0)
        x1, y1 = min(ox + nw, ax + aw, width), min(oy + nh, ay + ah, height)
        if x1 > x0 and y1 > y0:
            out[y0:y1, x0:x1] = img[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
        out = cv2.addWeighted(out, 1 - self.darkness, base, self.darkness, 0)
        g = self._glass_rect(width, height)
        if g and g[2] > g[0] and g[3] > g[1]:
            gx0, gy0, gx1, gy1 = g
            part = out[gy0:gy1, gx0:gx1]
            if self.GLASS_BLUR:
                part = cv2.GaussianBlur(part, (0, 0), self.GLASS_BLUR)
            glass = self._flat(self.glass_color, width, height)[gy0:gy1, gx0:gx1]
            out[gy0:gy1, gx0:gx1] = cv2.addWeighted(part, 1 - self.glass_mix, glass, self.glass_mix, 0)
        return out

    def _flat(self, color, width, height):
        """A picture of one colour, the size of the window (remembered)."""
        flats = getattr(self, "_flats", None)
        if flats is None or flats[0] != (width, height):
            flats = self._flats = ((width, height), {})
        if color not in flats[1]:
            img = np.empty((height, width, 3), np.uint8)
            img[:] = np.round(hex_to_bgr(color)).astype(np.uint8)
            flats[1][color] = img
        return flats[1][color]

    def _glass_rect(self, width, height):
        g = self.glass
        if g is None or not g.winfo_ismapped():
            return None
        x, y = self._pos(g)
        return (max(x, 0), max(y, 0), min(x + g.winfo_width(), width), min(y + g.winfo_height(), height))

    def _pos(self, w):
        if w is self.root:
            return 0, 0
        return w.winfo_rootx() - self.root.winfo_rootx(), w.winfo_rooty() - self.root.winfo_rooty()

    def _crop(self, w, size=None):
        """The piece of the picture behind widget w (size: if it's about to get another size)."""
        x, y = self._pos(w)
        cw, ch = size or (max(1, w.winfo_width()), max(1, w.winfo_height()))
        return self._crop_rect(x, y, cw, ch)

    def _piece(self, it, rect):
        """The piece for an item at rect, with a titled box's outline drawn on."""
        piece = self._crop_rect(*rect)
        if it.get("box") and self.border:  # no line unless a border colour is given
            h, wd = piece.shape[:2]
            cv2.rectangle(piece, (0, it.get("box_top", 0)), (wd - 1, h - 1),
                          tuple(int(v) for v in hex_to_bgr(self.border)), 1)
        return piece

    def _crop_rect(self, x, y, cw, ch):
        self._fresh_composite()
        H, W = self.composite.shape[:2]
        piece = np.empty((ch, cw, 3), np.uint8)
        piece[:] = hex_to_bgr(self.base).astype(np.uint8)
        sx0, sy0 = max(x, 0), max(y, 0)
        sx1, sy1 = min(x + cw, W), min(y + ch, H)
        if sx1 > sx0 and sy1 > sy0:
            piece[sy0 - y:sy1 - y, sx0 - x:sx1 - x] = self.composite[sy0:sy1, sx0:sx1]
        return piece

    def _crop_all(self):
        root = self.root
        size = (root.winfo_width(), root.winfo_height())
        if size[0] < 2 or size[1] < 2:
            return
        if self.area is not None:
            a = self.area()
            if a is None or not a.winfo_ismapped():
                return  # the page isn't shown yet; painted again once it is
        key = (size, self._area_rect(*size))
        if self.composite is None or self.composite_key != key:
            self._forget_composite()
            self.composite = self._compose(*size)
            self.composite_frame = self.frame_i
            self.composite_size, self.composite_key = size, key
            for it in self.items.values():
                it.pop("rect", None)
        for w, it in list(self.items.items()):
            if not w.winfo_exists():
                self.items.pop(w, None)
                continue
            target = it.get("under", w)
            if not target.winfo_exists():
                # the picture behind a frame was destroyed with the frame's children (a list that
                # was rebuilt); forget the frame, so the next refresh gives it a new one
                self.items.pop(w, None)
                continue
            if not target.winfo_ismapped() or not w.winfo_ismapped():
                continue
            rect = self._pos(target) + (target.winfo_width(), target.winfo_height())
            if it.get("rect") == rect:
                continue  # still where it was: its piece is still right
            it["rect"] = rect
            kind = it["kind"]
            if kind == "frame":
                # (an animation doesn't need to keep up a part that's completely covered)
                it["covered"] = self._covered(w, it["under"])
                if it.get("box"):
                    lw = w.nametowidget(str(w.cget("labelwidget"))) if str(w.cget("labelwidget")) else None
                    it["box_top"] = (lw.winfo_height() // 2) if lw is not None else 0
            piece = self._piece(it, rect) if kind == "frame" else self._crop_rect(*rect)
            if kind in ("entry", "check"):
                color = hex_of(piece.reshape(-1, 3).mean(axis=0))
                if kind == "entry":
                    w.config(bg=color, disabledbackground=color)
                else:
                    self.style.configure(it["style"], background=color)
                    self.style.map(it["style"], background=[("active", color)])
                continue
            img = photo(piece)
            it["img"] = img  # Tk forgets pictures nobody keeps
            if kind == "frame":
                it["under"].config(image=img)
            elif kind == "label":
                w.config(image=img)
            elif kind == "canvas":
                w.delete("bdimg")
                w.create_image(0, 0, anchor="nw", image=img, tags="bdimg")
                w.tag_lower("bdimg")

    def _covered(self, w, under):
        """Is this frame hidden completely behind one of its own parts?"""
        try:
            width, height = w.winfo_width(), w.winfo_height()
            for c in w.winfo_children():
                if c is not under and c.winfo_manager() and c.winfo_ismapped() \
                        and not isinstance(c, tk.Toplevel) and c.winfo_x() <= 0 and c.winfo_y() <= 0 \
                        and c.winfo_x() + c.winfo_width() >= width and c.winfo_y() + c.winfo_height() >= height:
                    return True
        except tk.TclError:
            pass
        return False

    # ------------------------------------------------------------ giving widgets their piece

    def _background_of(self, w):
        cls = w.winfo_class()
        try:
            if cls.startswith("T") and cls not in ("Tk", "Toplevel"):
                style = str(w.cget("style")) or cls
                return str(self.style.lookup(style, "background"))
            return str(w.cget("bg"))
        except tk.TclError:
            return ""

    def _plain(self, w):
        return self._background_of(w).lower() in self.see_through

    def _decorate(self, parent, dry=False):
        """Give every plain, visible part its piece. Returns the labels that still need measuring.
        dry: only look whether anything new would get a piece."""
        if not dry:
            self._new_widgets = False
        found = []
        widgets = [parent] if parent is self.root else []
        widgets += [w for w in parent.winfo_children()]
        for w in widgets:
            if w in self.skip or getattr(w, "_bd_under", False):
                continue
            if w is not parent and isinstance(w, tk.Toplevel):
                continue
            try:
                if not w.winfo_ismapped():
                    continue
            except tk.TclError:
                continue
            cls = w.winfo_class()
            if w not in self.items and self._plain(w):
                if cls in FRAME_CLASSES:
                    if dry:
                        self._new_widgets = True
                    else:
                        self._decorate_frame(w, cls)
                elif cls in LABEL_CLASSES and not str(w.cget("image")):
                    if not dry:
                        self._loosen_label(w)
                    found.append(w)
                elif cls == "Canvas":
                    if dry:
                        self._new_widgets = True
                    else:
                        self.items[w] = {"kind": "canvas"}
                elif cls == "Entry":
                    if dry:
                        self._new_widgets = True
                    else:
                        self.items[w] = {"kind": "entry", "bg": w.cget("bg"),
                                         "disabledbackground": w.cget("disabledbackground")}
                elif cls == "TCheckbutton":
                    if dry:
                        self._new_widgets = True
                    else:
                        old = str(w.cget("style"))
                        name = f"Bd{abs(hash(str(w)))}.TCheckbutton"
                        w.config(style=name)
                        self.items[w] = {"kind": "check", "style": name, "old_style": old}
            if w is not parent:
                found += self._decorate(w, dry)
        return found

    def _decorate_frame(self, w, cls):
        under = tk.Label(w, bd=0, highlightthickness=0, padx=0, pady=0, bg=self.base)
        under._bd_under = True
        box = cls in ("Labelframe", "TLabelframe")
        # a titled box: cover its outline too (it is drawn again on the piece); a ttk frame's
        # padding counts as its border, so cover that as well (else it stays a plain dark band)
        outside = box or cls.startswith("T") and cls not in ("Tk", "Toplevel")
        under.place(x=0, y=0, relwidth=1, relheight=1, bordermode="outside" if outside else "inside")
        under.lower()
        self.items[w] = {"kind": "frame", "under": under, "box": box}

    def _loosen_label(self, w):
        """A label stretched across its row (to keep its text on the left) shrinks to its text,
        still on the left: its piece of picture is exactly its size, and text sits in the middle."""
        ttk_label = w.winfo_class() == "TLabel"
        it = {"kind": "label", "text": None, "foreground": str(w.cget("foreground")),
              "compound": str(w.cget("compound")), "geom": None}
        if ttk_label:
            # a ttk label draws a thin border around itself; this style has none, so its piece
            # of picture can be exactly its size
            if "Bd.TLabel" not in getattr(self, "_styles", set()):
                self.style.layout("Bd.TLabel", [("Label.label", {"sticky": "nswe"})])
                self._styles = {"Bd.TLabel"}
            it["pad"] = {"padding": w.cget("padding"), "style": str(w.cget("style"))}
            w.config(style="Bd.TLabel")
        else:
            # (with a picture, a label's width and height count pixels instead of letters)
            it["pad"] = {k: w.cget(k) for k in ("padx", "pady", "bd", "highlightthickness", "width", "height")}
        anchor = str(w.cget("anchor") or "center")
        manager = w.winfo_manager()
        if manager == "pack":
            info = w.pack_info()
            if info.get("fill") in ("x", "both") and "w" in anchor:
                it["geom"] = ("pack", {"fill": info["fill"], "anchor": info.get("anchor", "center")})
                w.pack_configure(fill="y" if info["fill"] == "both" else "none", anchor="w")
        elif manager == "grid":
            sticky = str(w.grid_info().get("sticky", ""))
            if "e" in sticky and "w" in sticky:
                it["geom"] = ("grid", {"sticky": sticky})
                w.grid_configure(sticky=sticky.replace("e", ""))
        self.items[w] = it
        lift = self.lift_colors.get(it["foreground"].lower())
        if lift:
            w.config(foreground=lift)

    def _size_label(self, w):
        """Give a label a blank picture of its own size (the real piece comes in _crop_all)."""
        it = self.items.get(w)
        if it is None:
            return
        width, height = w.winfo_width(), w.winfo_height()
        it["text"] = str(w.cget("text"))
        it["stretch"] = (width > w.winfo_reqwidth(), height > w.winfo_reqheight())
        it.pop("rect", None)
        blank = tk.PhotoImage(width=max(1, width), height=max(1, height))
        it["img"] = blank
        if w.winfo_class() == "TLabel":
            w.config(image=blank, compound="center", padding=0)
        else:
            w.config(image=blank, compound="center", padx=0, pady=0, bd=0, highlightthickness=0, width=0, height=0)

    def _undo(self, w, forget=True):
        it = self.items.get(w)
        if it is None:
            return
        try:
            kind = it["kind"]
            if kind == "frame":
                if forget:
                    it["under"].destroy()
            elif kind == "label":
                pad = dict(it["pad"])
                if not forget:
                    pad.pop("style", None)  # keep the border-less look while it measures its text
                w.config(image="", compound=it["compound"] or "none", **pad)
                if forget:
                    w.config(foreground=it["foreground"])
                    if it["geom"]:
                        how, opts = it["geom"]
                        (w.pack_configure if how == "pack" else w.grid_configure)(**opts)
            elif kind == "canvas":
                w.delete("bdimg")
            elif kind == "entry":
                w.config(bg=it["bg"], disabledbackground=it["disabledbackground"])
            elif kind == "check":
                w.config(style=it["old_style"])
        except tk.TclError:
            pass
        if forget:
            self.items.pop(w, None)

    def _root_changed(self, event):
        if event.widget is not self.root or not self.active:
            return
        if (event.width, event.height) != self.composite_size and self.pending is None:
            self.pending = self.root.after(60, self.repaint)
