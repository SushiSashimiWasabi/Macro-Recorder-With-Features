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
