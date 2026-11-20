"""Check my macro rules: plain functions, no window (the Check window, the Picture watch / game / screen checks and
the notice line are in check_ui.py). Files and open programs are reached only through the functions passed in:
the real disk and windows in the app, a dict of made-up macros in the tests."""
import os

import macro_steps as workflow
import step_more

SURE, MAYBE = "sure", "maybe"


def macro_name(path):
    return os.path.splitext(os.path.basename(path or ""))[0] or "?"


def screen_far_off(made_for, play_on):
    """True when the screen a macro was recorded on is so different from this one that scaling can't
    make up for it: another shape (16:9 against 4:3), or less than half / more than 2.5 times as big.
    16:9 against 16:10, or 1080p against 1440p, is fine."""
    try:
        (w1, h1), (w2, h2) = made_for, play_on
        if min(w1, h1, w2, h2) <= 0:
            return False
        shape = (w1 / h1) / (w2 / h2)
        size = h2 / h1
    except (TypeError, ValueError, ZeroDivisionError):
        return False
    return not (0.83 <= shape <= 1.2) or not (0.5 <= size <= 2.5)


def step_problems(steps, find, read, program_open=None, max_depth=6):
    """[(id, level, text)] of the steps, also inside the macros their "Play another macro" steps play.
    find(path): where that macro's file is now, or None. read(found): its steps (an error = skipped, it's told
    when it plays). program_open(exe): is that program open; None = can't look (not Windows)."""
    out = []
    _walk(steps, find, read, program_open, max_depth, out, set(), 0)
    return out


def _walk(steps, find, read, program_open, max_depth, out, visited, depth):
    if depth > max_depth:
        return
    for a, lst, i, _parent in workflow.walk(steps):
        if a.get("off"):
            continue
        kind = a.get("kind")
        holder = a.get("condition", {}) if kind in ("if", "retry") else a if kind == "wait_picture" else None
        if holder is not None and not holder.get("png") and not holder.get("color_on"):
            what = {"if": "An \"If\"", "retry": "A \"Retry\""}.get(kind, "A \"Wait for a picture\"")
            out.append((f"steppic:{a.get('id')}", SURE, f"{what} step has no picture, so it never sees one. "
                                                        "Choose one in Edit."))
        _more_step(a, lst, i, steps, find, program_open, out)
        if kind != "play_macro":
            continue
        for key, what in (("file", "a \"Play another macro\" step plays"),
                          ("on_fail", "a \"Play another macro\" step plays when it fails")):
            path = a.get(key)
            if not path:
                continue
            found = find(path)
            if not found:
                out.append((f"chain:{macro_name(path).lower()}", SURE,
                            f"The macro \"{macro_name(path)}\" that {what} isn't there any more. That part is skipped."))
                continue
            fkey = os.path.normcase(os.path.abspath(found))
            if fkey in visited:
                continue
            visited.add(fkey)
            try:
                inner = read(found)
            except Exception:
                continue  # (a broken file is told when it plays)
            _walk(inner, find, read, program_open, max_depth, out, visited, depth + 1)


def _more_step(a, lst, i, steps, find, program_open, out):
    """(2.12) A Go to without its Label, a macro a step plays that isn't there, an Else that doesn't come right
    after an If, a program window that isn't open now."""
    kind = a.get("kind")
    if kind == "goto":
        labels = {b.get("name") for b, _l, _i, _p in workflow.walk(steps) if b.get("kind") == "label"
                  and not b.get("off")}
        if a.get("label") not in labels:
            out.append((f"goto:{a.get('id')}", SURE, f"\"Go to {a.get('label')}\" has no Label \"{a.get('label')}\" "
                                                     "to jump to: the macro would stop there. Add the Label in Edit."))
    if kind == "else" and not step_more.else_has_if(lst, i):
        out.append((f"else:{a.get('id')}", SURE, "An Else doesn't come right after an If, so it never runs. "
                                                 "Move it under an If in Edit."))
    for key in step_more.MACRO_KEYS:
        path = a.get(key)
        if path and not find(path):
            out.append((f"then:{macro_name(path).lower()}", SURE, f"The macro \"{macro_name(path)}\" that a step "
                                                                  "plays isn't there any more. That part is skipped."))
    window = a.get("window") if kind == "type" else None
    if window and window.get("exe") and program_open is not None and not program_open(window["exe"]):
        out.append((f"window:{window['exe'].lower()}", MAYBE, f"\"Type text\" types into {window['exe']}, which isn't "
                                                              "open now. Open it before playing (else nothing is typed)."))


def ignored(store, key):
    """The warnings turned off for one macro (its key: macro_versions._key of its name)."""
    ids = store.get(key) if isinstance(store, dict) else None
    return set(i for i in ids if isinstance(i, str)) if isinstance(ids, list) else set()


def set_ignored(store, key, pid, ignore):
    """Turns one warning off (ignore) or on again for one macro, in the store (a dict)."""
    ids = ignored(store, key)
    (ids.add if ignore else ids.discard)(pid)
    if ids:
        store[key] = sorted(ids)
    else:
        store.pop(key, None)


def rename_ignored(store, old_key, new_key):
    """A macro renamed in the app keeps its turned-off warnings."""
    if isinstance(store, dict) and old_key in store and old_key != new_key:
        store[new_key] = store.pop(old_key)
