"""A small log file and a support report you can copy and paste to whoever helps you.

The log (log.txt in the settings folder, at most about 1 MB with one older copy) gets a line for
starting, recording, playing and every error, with the error's details. The report has the app
version, the system, screen sizes, a few settings and the end of the log. It never includes your
macros, your keys, picture files or the Discord link, and your user folder name is replaced
with "~". Nothing is sent anywhere: you copy it yourself."""

import logging
import logging.handlers
import os
import platform
import sys
import traceback

log = logging.getLogger("macro_recorder")
_log_path = None


def setup(folder):
    """Start writing the log into folder/log.txt (safe to call more than once)."""
    global _log_path
    if _log_path:
        return
    try:
        os.makedirs(folder, exist_ok=True)
        _log_path = os.path.join(folder, "log.txt")
        handler = logging.handlers.RotatingFileHandler(_log_path, maxBytes=1_000_000, backupCount=1,
                                                       encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    except Exception:
        _log_path = None


def info(text):
    try:
        log.info(_private(text))
    except Exception:
        pass


def error(text, exc=None):
    """Log an error (with its traceback when exc is given). Returns a one-line description."""
    try:
        if exc is not None:
            details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            log.error(_private(f"{text}\n{details}"))
        else:
            log.error(_private(text))
    except Exception:
        pass
    return f"{text}: {exc}" if exc is not None else text


def log_path():
    return _log_path


def _private(text):
    """Your user folder becomes "~" (it often holds your name)."""
    home = os.path.expanduser("~")
    text = str(text)
    if home and len(home) > 3:
        text = text.replace(home, "~").replace(home.replace("\\", "/"), "~")
    return text


def _log_tail(lines=80):
    if not _log_path or not os.path.exists(_log_path):
        return "(no log yet)"
    try:
        with open(_log_path, encoding="utf-8", errors="replace") as f:
            tail = f.readlines()[-lines:]
        return "".join(tail).rstrip() or "(log is empty)"
    except OSError as exc:
        return f"(couldn't read the log: {exc})"


SAFE_SETTINGS = ("speed", "loop", "repeat_count", "ready_seconds", "record_mouse_moves", "mouse_detail",
                 "record_camera", "watch_enabled", "watch_click", "watch_wait", "watch_match", "watch_end_wait",
                 "watch_ignore_bg", "watch_limit_count", "watch_limit_seconds", "watch_shift_lock",
                 "pause_when_away", "away_stop_seconds", "switch_to_program", "fit_to", "play_resolution",
                 "play_overlay", "sounds", "check_updates", "discord_enabled")


def report(app_version, settings, screen=None, extra=None):
    """The support report as text (to copy to the clipboard)."""
    lines = [
        "Macro Recorder support report",
        f"Version: {app_version}" + (" (from source)" if not getattr(sys, "frozen", False) else ""),
        f"System: {platform.platform()} ({platform.machine()})",
        f"Python: {platform.python_version()}",
    ]
    if screen:
        lines.append(f"Main screen: {screen[0]}x{screen[1]}")
    try:
        import mss

        with mss.mss() as sct:
            mons = [f"{m['width']}x{m['height']} at {m['left']},{m['top']}" for m in sct.monitors[1:]]
        lines.append("Screens: " + "; ".join(mons))
    except Exception:
        pass
    shown = {k: settings.get(k) for k in SAFE_SETTINGS if k in settings}
    if isinstance(settings.get("watch_pictures"), list):
        shown["watch_pictures"] = f"{len(settings['watch_pictures'])} picture(s)"
    if isinstance(settings.get("hotkeys"), dict):
        shown["hotkeys"] = "changed" if settings["hotkeys"] != {"record": "f9", "pause": "f10", "play": "f11",
                                                                "stop": "f12"} else "F9-F12"
    lines.append("Settings: " + ", ".join(f"{k}={v}" for k, v in shown.items()))
    for line in extra or []:
        lines.append(line)
    lines.append("")
    lines.append("Last lines of the log:")
    lines.append(_log_tail())
    return _private("\n".join(lines))


# ---------------------------------------------------------------- report files

MAX_REPORTS = 20  # older report files are deleted by themselves


def reports_dir():
    return os.path.join(os.path.dirname(_log_path), "reports") if _log_path else None


def save_report(text):
    """Keep a report as a text file in the reports folder (newest MAX_REPORTS kept). Returns its path."""
    import time

    folder = reports_dir()
    if not folder:
        raise OSError("the settings folder isn't known")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, time.strftime("Macro Recorder report %Y-%m-%d %H-%M-%S.txt"))
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text + "\n")
    old = sorted((p for p in os.listdir(folder) if p.startswith("Macro Recorder report")), reverse=True)
    for name in old[MAX_REPORTS:]:
        try:
            os.remove(os.path.join(folder, name))
        except OSError:
            pass
    return path


def _files():
    """(the log files, the report files) that exist now."""
    logs = [p for p in (_log_path, (_log_path or "") + ".1") if p and os.path.isfile(p)]
    folder = reports_dir()
    reports = [os.path.join(folder, n) for n in os.listdir(folder)
               if n.startswith("Macro Recorder report")] if folder and os.path.isdir(folder) else []
    return logs, reports


def storage():
    """(number of report files, bytes used by reports and logs together)."""
    logs, reports = _files()
    size = 0
    for p in logs + reports:
        try:
            size += os.path.getsize(p)
        except OSError:
            pass
    return len(reports), size


def clear():
    """Delete every report file and empty the log. Returns how many bytes were freed."""
    _count, before = storage()
    logs, reports = _files()
    for p in reports:
        try:
            os.remove(p)
        except OSError:
            pass
    for handler in list(log.handlers):  # the log file is open: empty it through its handler
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            try:
                handler.acquire()
                handler.stream.seek(0)
                handler.stream.truncate()
            except Exception:
                pass
            finally:
                handler.release()
    old = (_log_path or "") + ".1"
    if os.path.isfile(old):
        try:
            os.remove(old)
        except OSError:
            pass
    _count, after = storage()
    info("Reports and logs cleared")
    return max(0, before - after)


def size_text(n):
    if n < 1024:
        return f"{n} bytes"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.1f} MB"
