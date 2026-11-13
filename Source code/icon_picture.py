"""Your own pictures for the app icon and the logo in front of "Macro Recorder" (Settings > General).

Any common picture works: .png, .jpg, .gif (first frame), .bmp, .webp, .tif and Windows .ico files.
Transparent parts stay transparent. The chosen picture is stored as a .png in the settings folder.
"""
import base64
import struct

import cv2
import numpy as np

PICTURE_TYPES = [("Pictures", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tif *.tiff *.ico"),
                 ("All files", "*.*")]
MAX_STORED = 256  # stored pictures are at most this many pixels wide/high


def _to_bgra(img):
    if img is None:
        return None
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    if img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    if img.dtype != np.uint8:
        img = (img / 256).astype(np.uint8)
    return img


def _read_ico(data):
    """The biggest picture in a Windows .ico file, as BGRA (or None)."""
    if len(data) < 6 or struct.unpack_from("<HHH", data, 0)[:2] != (0, 1):
        return None
    count = struct.unpack_from("<H", data, 4)[0]
    best = None
    for i in range(count):
        w, h, _c, _r, _p, bpp, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        w, h = w or 256, h or 256
        if best is None or (w * h, bpp) > (best[0] * best[1], best[2]):
            best = (w, h, bpp, size, offset)
    if best is None:
        return None
    w, h, bpp, size, offset = best
    blob = data[offset:offset + size]
    if blob[:8] == b"\x89PNG\r\n\x1a\n":  # newer icons keep a PNG inside
        return _to_bgra(cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_UNCHANGED))
    # an old-style bitmap: header, then the pixels bottom-up (height counts the mask too)
    hdr_size, bw, bh2, _planes, bits = struct.unpack_from("<IiiHH", blob, 0)
    bh = bh2 // 2
    if bits == 32:
        px = np.frombuffer(blob, np.uint8, count=bw * bh * 4, offset=hdr_size).reshape(bh, bw, 4)
        img = px[::-1].copy()
        if not img[:, :, 3].any():  # no alpha stored: everything visible
            img[:, :, 3] = 255
        return img
    # other bit depths: let OpenCV read it as a .bmp file (no transparency)
    fixed = bytearray(blob)
    struct.pack_into("<i", fixed, 8, bh)
    file_header = b"BM" + struct.pack("<IHHI", 14 + len(fixed), 0, 0, 14 + hdr_size + (
        4 * (1 << bits) if bits <= 8 else 0))
    return _to_bgra(cv2.imdecode(np.frombuffer(file_header + bytes(fixed), np.uint8), cv2.IMREAD_COLOR))


def load(path):
    """Any picture file as BGRA (blue, green, red, see-through), or None if it can't be read."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    raw = data.tobytes()
    if path.lower().endswith(".ico") or raw[:4] == b"\x00\x00\x01\x00":
        try:
            img = _read_ico(raw)
            if img is not None:
                return img
        except (struct.error, ValueError, cv2.error):
            pass
    try:
        return _to_bgra(cv2.imdecode(data, cv2.IMREAD_UNCHANGED))
    except cv2.error:
        return None


def fit(img, size):
    """Shrink (or grow) to fit in size x size, keeping its shape, centred on a see-through square."""
    h, w = img.shape[:2]
    f = size / max(w, h)
    nw, nh = max(1, round(w * f)), max(1, round(h * f))
    small = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)
    out = np.zeros((size, size, 4), np.uint8)
    x, y = (size - nw) // 2, (size - nh) // 2
    out[y:y + nh, x:x + nw] = small
    return out


def store(path, dest):
    """Read the picture at path and save it as a .png at dest (at most MAX_STORED pixels)."""
    img = load(path)
    if img is None or img.shape[0] < 1 or img.shape[1] < 1:
        return False
    h, w = img.shape[:2]
    if max(w, h) > MAX_STORED:
        f = MAX_STORED / max(w, h)
        img = cv2.resize(img, (max(1, round(w * f)), max(1, round(h * f))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        return False
    buf.tofile(dest)
    return True


def photo(tk_module, path, size, master=None):
    """A Tk picture of the stored picture, fitted into size x size (None if it can't be read)."""
    img = load(path)
    if img is None:
        return None
    ok, buf = cv2.imencode(".png", fit(img, size))
    if not ok:
        return None
    return tk_module.PhotoImage(master=master, data=base64.b64encode(buf.tobytes()).decode("ascii"))
