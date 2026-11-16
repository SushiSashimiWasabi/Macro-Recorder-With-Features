"""Older versions of a macro (2.10): every time a .macro file is saved over, the version it had before
is kept, up to 10 per macro, in the app's own settings folder ("macro_versions", one folder per macro
name). Never beside the macro or in a shared file. "Restore an older version…" (Edit > More, with a
macro chosen on the left) puts one back; the macro as it was is kept as a version first, so a restore
can be undone the same way.

The versions follow the macro's name: a macro renamed in the app takes its versions along."""
import datetime
import filecmp
import os
import shutil

import macro_recorder as core

KEEP = 10
EXT = ".macro"


def root():
    return os.path.join(os.path.dirname(core.settings_path()), "macro_versions")


def _key(name):
    """The folder name for a macro name (or a path): its file name, lower case, safe for a folder."""
    base = os.path.splitext(os.path.basename(name or ""))[0].strip().lower()
    return "".join(c for c in base if c not in '\\/:*?"<>|').strip(". ") or "_"


def folder(name):
    return os.path.join(root(), _key(name))


def versions(name):
    """[(path, datetime)] of a macro's kept versions, newest first."""
    d = folder(name)
    try:
        files = [f for f in os.listdir(d) if f.endswith(EXT)]
    except OSError:
        return []
    out = []
    for f in files:
        try:
            when = datetime.datetime.strptime(f[:-len(EXT)], "%Y%m%d-%H%M%S-%f")
        except ValueError:
            continue
        out.append((os.path.join(d, f), when))
    out.sort(key=lambda v: v[1], reverse=True)
    return out


def keep(path, now=None):
    """Before `path` is saved over: keep the version it has now. Nothing happens when there's no such
    file yet or it's the same as the newest kept version. Returns the kept copy's path or None."""
    if not path or os.path.splitext(path)[1].lower() != EXT or not os.path.isfile(path):
        return None
    try:
        kept = versions(path)
        if kept and filecmp.cmp(path, kept[0][0], shallow=False):
            return None
        d = folder(path)
        os.makedirs(d, exist_ok=True)
        now = now or datetime.datetime.now()
        target = os.path.join(d, now.strftime("%Y%m%d-%H%M%S-%f") + EXT)
        while os.path.exists(target):
            now += datetime.timedelta(microseconds=1)
            target = os.path.join(d, now.strftime("%Y%m%d-%H%M%S-%f") + EXT)
        shutil.copyfile(path, target)
        for old, _when in versions(path)[KEEP:]:
            os.remove(old)
        return target
    except OSError as exc:
        core.diag.error("Couldn't keep the older version of a macro", exc)
        return None


def restore(version_path, path):
    """Put a kept version back as the macro at `path` (the macro as it is now is kept first)."""
    with open(version_path, "rb") as f:
        data = f.read()  # (read first: keeping the version now may clear out the oldest one, this one)
    keep(path)
    with open(path, "wb") as f:
        f.write(data)


def renamed(old, new):
    """A macro renamed in the app: its versions go along to the new name."""
    src, dst = folder(old), folder(new)
    if src == dst or not os.path.isdir(src):
        return
    try:
        os.makedirs(dst, exist_ok=True)
        for f in os.listdir(src):
            if not os.path.exists(os.path.join(dst, f)):
                shutil.move(os.path.join(src, f), os.path.join(dst, f))
        shutil.rmtree(src, ignore_errors=True)
        for extra, _when in versions(new)[KEEP:]:
            os.remove(extra)
    except OSError as exc:
        core.diag.error("Couldn't move a macro's older versions", exc)


def when_text(when, now=None):
    """"Today 14:05", "Yesterday 09:30" or "12 Nov 2026 18:00"."""
    today = (now or datetime.datetime.now()).date()
    if when.date() == today:
        day = "Today"
    elif when.date() == today - datetime.timedelta(days=1):
        day = "Yesterday"
    else:
        day = f"{when.day} {when.strftime('%b %Y')}"
    return f"{day} {when.strftime('%H:%M:%S')}"
