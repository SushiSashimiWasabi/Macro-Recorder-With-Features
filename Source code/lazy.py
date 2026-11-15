"""Load a big module (OpenCV, numpy) only when it's first used, so the app starts sooner.

    cv2 = lazy.module("cv2")      # nothing is loaded yet
    cv2.resize(...)               # loaded now, the first time something of it is used

available("cv2", "numpy") says whether they could be loaded, without loading them."""

import importlib
import importlib.util


class _LazyModule:
    def __init__(self, name):
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_module", None)

    def _load(self):
        mod = object.__getattribute__(self, "_module")
        if mod is None:
            mod = importlib.import_module(object.__getattribute__(self, "_name"))
            object.__setattr__(self, "_module", mod)
        return mod

    def __getattr__(self, attr):
        return getattr(self._load(), attr)

    def __setattr__(self, attr, value):
        setattr(self._load(), attr, value)

    def __repr__(self):
        return f"<lazy module {object.__getattribute__(self, '_name')}>"


def module(name):
    return _LazyModule(name)


def available(*names):
    try:
        return all(importlib.util.find_spec(n) is not None for n in names)
    except (ImportError, ValueError):
        return False


class LazyObject:
    """An object that's only made (by make()) the first time it's really used, so its module isn't
    loaded at start.

        self.video = lazy.LazyObject(make_video, idle={"is_open": lambda: False})

    idle: what reading an attribute gives while it isn't made yet (so a quick "is it open?" doesn't
    make it). Values set before it's made are kept and handed to it when it's made."""

    def __init__(self, make, idle=None):
        object.__setattr__(self, "_make", make)
        object.__setattr__(self, "_idle", dict(idle or {}))
        object.__setattr__(self, "_pending", {})
        object.__setattr__(self, "_obj", None)

    def lazy_made(self):
        """Whether it was made already."""
        return object.__getattribute__(self, "_obj") is not None

    def _get(self):
        obj = object.__getattribute__(self, "_obj")
        if obj is None:
            obj = object.__getattribute__(self, "_make")()
            for attr, value in object.__getattribute__(self, "_pending").items():
                setattr(obj, attr, value)
            object.__setattr__(self, "_obj", obj)
        return obj

    def __getattr__(self, attr):
        if object.__getattribute__(self, "_obj") is None:
            pending = object.__getattribute__(self, "_pending")
            if attr in pending:
                return pending[attr]
            idle = object.__getattribute__(self, "_idle")
            if attr in idle:
                return idle[attr]
        return getattr(self._get(), attr)

    def __setattr__(self, attr, value):
        if object.__getattribute__(self, "_obj") is None:
            object.__getattribute__(self, "_pending")[attr] = value
        else:
            setattr(object.__getattribute__(self, "_obj"), attr, value)
