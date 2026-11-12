"""A picture of your choice behind a window (the main window and the Settings window).

Tk can't make a frame or label see-through, so each plain part of the window gets its own piece
of the picture: frames get a picture label laid underneath their contents, text labels show their
text on top of their piece, small drawings (switches, the status dot) draw over theirs, and
checkboxes and text boxes take the piece's average colour. The picture is darkened so text stays
readable, and one area (the main panel, the settings page) is darkened a bit more, like tinted
glass. Buttons, boxes and the big cards stay solid.

Needs numpy and opencv (already used by picture watch). Works on Windows and Mac.
"""

import base64
import os
import tkinter as tk
from tkinter import ttk

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = np = None

AVAILABLE = cv2 is not None

PICTURE_TYPES = [("Pictures", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"), ("All files", "*.*")]
FITS = {"Fill the window": "cover", "Show the whole picture": "contain"}
POSITIONS = {"Top": 0, "Middle": 50, "Bottom": 100}  # older settings; now a 0-100 slider
STORED_NAME = "background.png"
MAX_SIDE = 2000  # pictures are stored at most this big (enough for the window, quick to load)

FRAME_CLASSES = {"Frame", "TFrame", "Tk", "Toplevel", "Labelframe", "TLabelframe"}
LABEL_CLASSES = {"Label", "TLabel"}


def hex_to_bgr(color):
    color = color.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return np.array([b, g, r], dtype=np.float32)


def read_picture(path):
    """Read any picture file (also with non-English letters in its path). Returns BGR, or None."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    except Exception:
        return None
    if img is None:
        return None
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:  # see-through parts become dark
        alpha = img[:, :, 3:4].astype(np.float32) / 255
        img = (img[:, :, :3].astype(np.float32) * alpha).astype(np.uint8)
    if img.dtype != np.uint8:
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return img


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


def photo(img):
    ok, data = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    return tk.PhotoImage(data=base64.b64encode(data.tobytes()))


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
                 skip=(), lift_colors=None, border_color="#33333d", area=None):
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
        self.source = None      # the picture (BGR)
        self.source_key = None
        self.darkness = 0.5
        self.fit = "cover"
        self.position = 0.0
        self.composite = None   # the finished picture for the whole window
        self.composite_size = None
        self.composite_key = None
        self.items = {}         # widget -> what we changed (to undo it)
        self.pending = None
        self._new_widgets = False
        root.bind("<Configure>", self._root_changed, add="+")

    # ------------------------------------------------------------ public

    @property
    def active(self):
        return self.source is not None

    def set_picture(self, path, darkness=50, fit="cover", position=0.0):
        """Show the picture at path (None or "" = no picture, the plain window)."""
        if not AVAILABLE or not path or not os.path.isfile(path):
            self.source, self.source_key = None, None
            self.clear()
            return path is None or path == ""
        key = (path, os.path.getmtime(path))
        if key != self.source_key:
            img = read_picture(path)
            if img is None:
                self.source, self.source_key = None, None
                self.clear()
                return False
            self.source, self.source_key = img, key
        self.darkness = max(0.0, min(0.95, darkness / 100))
        self.fit = fit
        self.position = position
        self.composite = None
        self.repaint()
        return True

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
        for w in changed:
            self._undo(w, forget=False)
        new_labels = self._decorate(self.root, dry=True)
        if not changed and not new_labels and not self._new_widgets:
            return
        if changed:  # let them measure their new text, then give them their picture again
            self.root.update_idletasks()
            for w in changed:
                if w.winfo_exists():
                    self._size_label(w)
        self.repaint()

    text_changed = refresh

    def clear(self):
        """Back to the plain window."""
        for w in list(self.items):
            self._undo(w)
        self.items.clear()
        self.composite = None

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
        img = cv2.resize(src, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        base = hex_to_bgr(self.base)
        out = np.empty((height, width, 3), np.float32)
        out[:] = base
        # the slider position moves the picture along the side that's cut off ("cover");
        # a picture that fits whole stays in the middle
        p = self.position if self.fit == "cover" else 0.5
        ox = ax + round((aw - nw) * p)
        oy = ay + round((ah - nh) * p)
        x0, y0 = max(ox, ax, 0), max(oy, ay, 0)
        x1, y1 = min(ox + nw, ax + aw, width), min(oy + nh, ay + ah, height)
        if x1 > x0 and y1 > y0:
            out[y0:y1, x0:x1] = img[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
        out = out * (1 - self.darkness) + base * self.darkness
        g = self._glass_rect(width, height)
        if g:
            gx0, gy0, gx1, gy1 = g
            blurred = cv2.GaussianBlur(out, (0, 0), self.GLASS_BLUR) if self.GLASS_BLUR else out
            glass = hex_to_bgr(self.glass_color)
            out[gy0:gy1, gx0:gx1] = blurred[gy0:gy1, gx0:gx1] * (1 - self.glass_mix) + glass * self.glass_mix
        return np.clip(out, 0, 255).astype(np.uint8)

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

    def _crop(self, w):
        """The piece of the picture behind widget w."""
        x, y = self._pos(w)
        cw, ch = max(1, w.winfo_width()), max(1, w.winfo_height())
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
            self.composite = self._compose(*size)
            self.composite_size, self.composite_key = size, key
        for w, it in list(self.items.items()):
            if not w.winfo_exists():
                self.items.pop(w, None)
                continue
            target = it.get("under", w)
            if not target.winfo_ismapped() or not w.winfo_ismapped():
                continue
            piece = self._crop(target)
            kind = it["kind"]
            if kind in ("entry", "check"):
                color = hex_of(piece.reshape(-1, 3).mean(axis=0))
                if kind == "entry":
                    w.config(bg=color, disabledbackground=color)
                else:
                    self.style.configure(it["style"], background=color)
                    self.style.map(it["style"], background=[("active", color)])
                continue
            if kind == "frame" and it.get("box"):
                # a box with a title (Labelframe): draw its outline again, the piece covers it
                lw = w.nametowidget(str(w.cget("labelwidget"))) if str(w.cget("labelwidget")) else None
                top = (lw.winfo_height() // 2) if lw is not None else 0
                h, wd = piece.shape[:2]
                cv2.rectangle(piece, (0, top), (wd - 1, h - 1), tuple(int(v) for v in hex_to_bgr(self.border)), 1)
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
        # a titled box: cover its outline too (it is drawn again on the piece)
        under.place(x=0, y=0, relwidth=1, relheight=1, bordermode="outside" if box else "inside")
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
