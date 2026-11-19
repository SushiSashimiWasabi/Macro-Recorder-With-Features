"""Colour themes (Preview 4): the accent colour (buttons, switches, blue lines, links) picked in
Settings > Background > LOOK, changed at once in every open window.

The colours are names every part of the app imported from ui_common (ACCENT, ACCENT_DARK, ACCENT_HOVER).
Changing them: those names are set again in every module that has them, the ttk styles are made again,
and every open widget whose colour was the old accent gets the new one (switches and cards redraw)."""
import sys
import tkinter as tk

import ui_common

NAMES = ("ACCENT", "ACCENT_DARK", "ACCENT_HOVER")
OPTIONS = ("bg", "fg", "activebackground", "activeforeground", "highlightcolor", "highlightbackground",
           "selectbackground", "insertbackground", "troughcolor", "disabledforeground")


def theme_of(name):
    return ui_common.THEMES.get(name) or ui_common.THEMES["Blue"]


def set_globals(name):
    """The accent names get the theme's colours in every module that uses them. Returns {old: new}."""
    new = theme_of(name)
    old = tuple(getattr(ui_common, n) for n in NAMES)
    if old == new:
        return {}
    for mod in list(sys.modules.values()):
        d = getattr(mod, "__dict__", None)
        if not isinstance(d, dict):
            continue
        for n, o, v in zip(NAMES, old, new):
            if d.get(n) == o:
                d[n] = v
    return {o.lower(): v for o, v in zip(old, new)}


def recolour(root, changes):
    """Every open window: widgets in an old accent colour get the new one; drawn parts redraw."""
    if not changes:
        return 0
    count = 0
    todo = [root]
    while todo:
        w = todo.pop()
        try:
            todo.extend(w.winfo_children())
        except tk.TclError:
            continue
        if getattr(w, "keep_colour", False):  # (the colour samples to pick from)
            continue
        for opt in OPTIONS:
            try:
                now = str(w.cget(opt)).lower()
            except (tk.TclError, AttributeError):
                continue
            if now in changes:
                try:
                    w.configure(**{opt: changes[now]})
                    count += 1
                except tk.TclError:
                    pass
        if isinstance(w, tk.Canvas):
            for item in w.find_all():
                for opt in ("fill", "outline"):
                    try:
                        now = str(w.itemcget(item, opt)).lower()
                    except tk.TclError:
                        continue
                    if now in changes:
                        w.itemconfigure(item, **{opt: changes[now]})
                        count += 1
        own = getattr(w, "color", None)  # (the big Play card keeps its colour)
        if isinstance(own, str) and own.lower() in changes:
            w.color = changes[own.lower()]
        for fn_name in ("_draw", "draw"):
            redraw = getattr(w, fn_name, None)
            if callable(redraw) and (fn_name == "_draw" or isinstance(w, ui_common.Switch)):
                try:
                    redraw()
                except Exception:
                    pass
    return count


def apply(root, name):
    """Change the accent colour now, everywhere. Returns how many widget colours changed."""
    changes = set_globals(name)
    if not changes:
        return 0
    ui_common.apply_theme(root)
    return recolour(root, changes)
