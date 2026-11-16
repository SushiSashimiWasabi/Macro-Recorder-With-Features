"""Every finished run, kept between sessions (run_history.json in the settings folder), and the
numbers the Stats window, the Discord summaries and "stop by itself" are made from.

A run is {"t": when it ended (seconds since 1970), "macro": name, "status": win/loss/unknown,
"s": how long it took, "f": divine fragments}. The newest MAX_RUNS runs are kept one by one; older
ones stay inside their day's totals ("days": {"2026-11-15": {...}}), which are kept for good."""
import json
import os
import statistics
import threading
import time

MAX_RUNS = 5000
SLOW_FACTOR = 1.5  # a run this many times longer than the macro's usual run is "unusually slow"
_lock = threading.Lock()
_data = None
_path = None
_dirty = False


def _file():
    import macro_recorder as core

    return os.path.join(os.path.dirname(core.settings_path()), "run_history.json")


def _empty():
    return {"runs": [], "days": {}}


def load():
    """The history (read from the file the first time, or again when the settings folder changed)."""
    global _data, _path
    path = _file()
    if _data is None or _path != path:
        _path = path
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data.get("runs"), list) or not isinstance(data.get("days"), dict):
                raise ValueError
            _data = data
        except (OSError, ValueError, AttributeError):
            _data = _empty()
    return _data


def day_of(t=None):
    return time.strftime("%Y-%m-%d", time.localtime(t))


def _day(data, t=None):
    return data["days"].setdefault(day_of(t), {"runs": 0, "wins": 0, "losses": 0, "unknown": 0, "seconds": 0.0,
                                               "fragments": 0, "reconnects": 0, "best": None, "worst": None})


def add(macro, status, seconds, fragments=0, t=None):
    """A run ended. Returns the run as kept."""
    global _dirty
    with _lock:
        data = load()
        t = time.time() if t is None else t
        run = {"t": round(t, 1), "macro": macro or "Macro", "status": status, "s": round(float(seconds), 1),
               "f": int(fragments)}
        data["runs"].append(run)
        del data["runs"][:-MAX_RUNS]
        d = _day(data, t)
        d["runs"] += 1
        d[{"win": "wins", "loss": "losses"}.get(status, "unknown")] += 1
        d["seconds"] = round(d["seconds"] + run["s"], 1)
        d["fragments"] += run["f"]
        if status == "win":  # the best and worst are won runs: a run that failed early isn't a record
            d["best"] = run["s"] if d["best"] is None else min(d["best"], run["s"])
            d["worst"] = run["s"] if d["worst"] is None else max(d["worst"], run["s"])
        _dirty = True
        return run


def note(what, n=1, t=None):
    """Count something else for today ("reconnects")."""
    global _dirty
    with _lock:
        d = _day(load(), t)
        d[what] = d.get(what, 0) + n
        _dirty = True


def save():
    global _dirty
    with _lock:
        if not _dirty or _data is None:
            return
        try:
            tmp = _path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_data, f, separators=(",", ":"))
            os.replace(tmp, _path)
            _dirty = False
        except OSError:
            pass


def clear():
    global _data, _dirty
    with _lock:
        load()
        _data = _empty()
        _dirty = True
    save()


RESULT_WORDS = {"win": "Won", "loss": "Failed", "unknown": "Unknown"}


def _cell(value):
    """A spreadsheet cell: text that starts like a formula (=, +, -, @) gets a ' so Excel shows it
    as text instead of running it (a macro's name is typed by people)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def export_csv(path):
    """(2.10) Every kept run and every day's totals as a CSV file (opens in Excel). Only dates, macro
    names, results, times and fragments: no paths or user names. Returns (runs, days) written."""
    import csv

    with _lock:
        data = load()
        run_list = [dict(r) for r in data["runs"]]
        day_list = sorted((d, dict(v)) for d, v in data["days"].items())
    with open(path, "w", encoding="utf-8-sig", newline="") as f:  # (the BOM: Excel reads it as UTF-8)
        w = csv.writer(f)
        w.writerow(["RUNS"])
        w.writerow(["Date", "Time", "Macro", "Result", "Seconds", "Divine fragments"])
        for r in run_list:
            t = time.localtime(r.get("t", 0))
            w.writerow([time.strftime("%Y-%m-%d", t), time.strftime("%H:%M:%S", t), _cell(str(r.get("macro", ""))),
                        RESULT_WORDS.get(r.get("status"), "Unknown"), r.get("s", 0), r.get("f", 0)])
        w.writerow([])
        w.writerow(["DAILY TOTALS"])
        w.writerow(["Date", "Runs", "Won", "Failed", "Unknown", "Seconds played", "Divine fragments",
                    "Reconnects", "Fastest win (s)", "Slowest win (s)"])
        for date, d in day_list:
            w.writerow([date, d.get("runs", 0), d.get("wins", 0), d.get("losses", 0), d.get("unknown", 0),
                        d.get("seconds", 0), d.get("fragments", 0), d.get("reconnects", 0),
                        "" if d.get("best") is None else d["best"], "" if d.get("worst") is None else d["worst"]])
    return len(run_list), len(day_list)


def runs(macro=None, since=None):
    return [r for r in load()["runs"] if (macro is None or r["macro"] == macro) and (since is None or r["t"] >= since)]


def macros():
    """Macro names, the one played last first."""
    seen = {}
    for r in load()["runs"]:
        seen[r["macro"]] = r["t"]
    return sorted(seen, key=lambda m: -seen[m])


def summary(rs):
    """Numbers for a list of runs."""
    n = len(rs)
    wins = sum(1 for r in rs if r["status"] == "win")
    losses = sum(1 for r in rs if r["status"] == "loss")
    seconds = sum(r["s"] for r in rs)
    fragments = sum(r["f"] for r in rs)
    won = [r["s"] for r in rs if r["status"] == "win"] or [r["s"] for r in rs]
    usual = statistics.median(won) if won else 0.0
    return {"runs": n, "wins": wins, "losses": losses, "unknown": n - wins - losses,
            "winrate": wins * 100.0 / (wins + losses) if wins + losses else None,
            "seconds": seconds, "average": seconds / n if n else 0.0, "usual": usual,
            "fragments": fragments, "fragments_per_hour": fragments * 3600.0 / seconds if seconds else 0.0,
            "best": min(won) if won else None, "worst": max(won) if won else None,
            "slow": sum(1 for r in rs if usual and r["s"] > usual * SLOW_FACTOR)}


def is_slow(run, usual):
    return bool(usual) and run["s"] > usual * SLOW_FACTOR


def days(count=14, end=None):
    """The last `count` days, oldest first: [(date, that day's totals or an empty one)]."""
    data = load()
    end = time.time() if end is None else end
    out = []
    for back in range(count - 1, -1, -1):
        date = day_of(end - back * 86400)
        out.append((date, data["days"].get(date) or {"runs": 0, "wins": 0, "losses": 0, "unknown": 0,
                                                       "seconds": 0.0, "fragments": 0, "reconnects": 0,
                                                       "best": None, "worst": None}))
    return out


def records():
    """Best days ever: {"runs": (date, n), "fragments": (date, n), "wins": (date, n)} (None when empty)."""
    out = {}
    all_days = load()["days"]
    for key in ("runs", "wins", "fragments"):
        best = max(all_days.items(), key=lambda kv: kv[1].get(key, 0), default=None)
        out[key] = (best[0], best[1].get(key, 0)) if best and best[1].get(key, 0) else None
    return out


def chart_png(day_list, title=""):
    """A bar chart of runs per day (won green, failed red, unknown grey) with fragments as a line of
    numbers, as PNG bytes for a Discord message. None when pictures can't be made here."""
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    w, h, left, bottom, top = 760, 360, 50, 50, 50
    img = np.full((h, w, 3), (28, 24, 24), np.uint8)
    biggest = max([d["runs"] for _date, d in day_list] + [1])
    slot = (w - left - 20) / max(1, len(day_list))
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, title, (left, 30), font, 0.7, (244, 241, 241), 2, cv2.LINE_AA)
    cv2.line(img, (left, h - bottom), (w - 20, h - bottom), (100, 90, 90), 1)
    for i, (date, d) in enumerate(day_list):
        x0 = int(left + i * slot + slot * 0.18)
        x1 = int(left + (i + 1) * slot - slot * 0.18)
        y = h - bottom
        for key, colour in (("wins", (113, 204, 46)), ("losses", (87, 71, 255)), ("unknown", (166, 155, 155))):
            part = int((h - bottom - top) * d.get(key, 0) / biggest)
            if part:
                cv2.rectangle(img, (x0, y - part), (x1, y), colour, -1)
                y -= part
        if d["runs"]:
            cv2.putText(img, str(d["runs"]), (x0, y - 6), font, 0.45, (244, 241, 241), 1, cv2.LINE_AA)
        cv2.putText(img, date[8:] + "/" + date[5:7], (x0 - 4, h - bottom + 18), font, 0.4, (166, 155, 155), 1,
                    cv2.LINE_AA)
        if d.get("fragments"):
            cv2.putText(img, f"+{d['fragments']}", (x0 - 2, h - bottom + 36), font, 0.42, (255, 124, 79), 1,
                        cv2.LINE_AA)
    ok, data = cv2.imencode(".png", img)
    return data.tobytes() if ok else None


# ---------------------------------------------------------------- (2.10) someone's exported stats file

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILE_RUNS = 50000
MAX_FILE_DAYS = 20000
NAME_LETTERS = 60
NOT_OURS = "This isn't a Macro Recorder stats file."
_RESULT_FROM_WORD = {"won": "win", "failed": "loss", "unknown": "unknown"}
_EMPTY_DAY = {"runs": 0, "wins": 0, "losses": 0, "unknown": 0, "seconds": 0.0, "fragments": 0, "reconnects": 0,
              "best": None, "worst": None}


def clean_name(text):
    """A macro name from a file someone sent: the ' that Export puts before formula-like names taken off,
    control and invisible characters (also right-to-left tricks) removed, at most NAME_LETTERS letters."""
    import unicodedata

    text = str(text)
    if text[:1] == "'" and text[1:2] in ("=", "+", "-", "@", "\t", "\r"):
        text = text[1:]
    text = "".join(c for c in text if unicodedata.category(c)[0] != "C")
    text = " ".join(text.split())[:NAME_LETTERS].strip()
    return text or "Macro"


def _number(text, low, high, whole=False):
    """A number within [low, high] or None (also for "nan", "inf" and anything that isn't a number)."""
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    if not (low <= value <= high):  # (also false for nan)
        return None
    if whole:
        if value != int(value):
            return None
        return int(value)
    return round(value, 1)


def _date(text):
    """"2026-11-16" if it's a real date between 2000 and 2100, else None."""
    try:
        d = time.strptime(str(text).strip(), "%Y-%m-%d")
    except (TypeError, ValueError, OverflowError):
        return None
    return time.strftime("%Y-%m-%d", d) if 2000 <= d.tm_year <= 2100 else None


def read_csv(path):
    """Read a stats file made by Export (maybe someone else's: nothing in it is trusted or run). Returns a
    FileHistory; lines that don't make sense are skipped and counted (.skipped). Raises ValueError with
    a plain reason when the file can't be used at all."""
    import csv

    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise ValueError(f"The file couldn't be read ({exc.strerror or exc}).") from None
    if size > MAX_FILE_BYTES:
        raise ValueError(f"The file is too big ({size / 1048576:.0f} MB; stats files are at most "
                         f"{MAX_FILE_BYTES // 1048576} MB).")
    try:
        with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
            rows = list(csv.reader(f))
    except (OSError, csv.Error):
        raise ValueError(NOT_OURS) from None
    rows = [[c.strip() for c in r] for r in rows]
    if len(rows) < 2 or rows[0][:1] != ["RUNS"]:
        raise ValueError(NOT_OURS)
    head = {name: n for n, name in enumerate(rows[1])}
    if not all(k in head for k in ("Date", "Time", "Macro", "Result", "Seconds")):
        raise ValueError(NOT_OURS)
    runs_list, days_dict, skipped = [], {}, 0

    def cell(row, cols, name):
        n = cols.get(name)
        return row[n] if n is not None and n < len(row) else ""

    i = 2
    while i < len(rows) and any(rows[i]) and rows[i][:1] != ["DAILY TOTALS"]:
        row = rows[i]
        i += 1
        date = _date(cell(row, head, "Date"))
        result = _RESULT_FROM_WORD.get(cell(row, head, "Result").lower())
        seconds = _number(cell(row, head, "Seconds"), 0, 7 * 86400)
        frags = _number(cell(row, head, "Divine fragments") or "0", 0, 1000, whole=True)
        try:
            clock = time.strptime(cell(row, head, "Time"), "%H:%M:%S")
        except ValueError:
            clock = None
        if None in (date, result, seconds, frags, clock):
            skipped += 1
            continue
        if len(runs_list) >= MAX_FILE_RUNS:
            raise ValueError(f"The file has too many runs (stats files have at most {MAX_FILE_RUNS:,}).")
        when = time.strptime(f"{date} {clock.tm_hour:02d}:{clock.tm_min:02d}:{clock.tm_sec:02d}",
                             "%Y-%m-%d %H:%M:%S")
        runs_list.append({"t": time.mktime(when), "macro": clean_name(cell(row, head, "Macro")), "status": result,
                          "s": seconds, "f": frags})
    while i < len(rows) and rows[i][:1] != ["DAILY TOTALS"]:
        i += 1
    if i + 1 < len(rows):
        dhead = {name: n for n, name in enumerate(rows[i + 1])}
        for row in rows[i + 2:]:
            if not any(row):
                continue
            date = _date(cell(row, dhead, "Date"))
            values = {key: _number(cell(row, dhead, col) or "0", 0, 1000000, whole=True)
                      for key, col in (("runs", "Runs"), ("wins", "Won"), ("losses", "Failed"),
                                       ("unknown", "Unknown"), ("fragments", "Divine fragments"),
                                       ("reconnects", "Reconnects"))}
            values["seconds"] = _number(cell(row, dhead, "Seconds played") or "0", 0, 1e9)
            best, worst = cell(row, dhead, "Fastest win (s)"), cell(row, dhead, "Slowest win (s)")
            values["best"] = _number(best, 0, 7 * 86400) if best else None
            values["worst"] = _number(worst, 0, 7 * 86400) if worst else None
            if date is None or None in [values[k] for k in ("runs", "wins", "losses", "unknown", "fragments",
                                                             "reconnects", "seconds")] \
                    or (best and values["best"] is None) or (worst and values["worst"] is None) \
                    or len(days_dict) >= MAX_FILE_DAYS:
                skipped += 1
                continue
            days_dict[date] = values
    if not runs_list and not days_dict and skipped:
        raise ValueError(NOT_OURS)  # (only lines that don't make sense)
    runs_list.sort(key=lambda r: r["t"])
    return FileHistory(os.path.basename(path), runs_list, days_dict, skipped)


class FileHistory:
    """Someone's exported stats, only to look at: the same questions as this module answers about your
    own runs (runs, macros, days), but never added to your stats, summaries or Discord."""

    def __init__(self, name, runs_list, days_dict, skipped=0):
        self.name = name
        self._runs = runs_list
        self._days = days_dict
        self.skipped = skipped

    def runs(self, macro=None, since=None):
        return [r for r in self._runs if (macro is None or r["macro"] == macro) and (since is None or r["t"] >= since)]

    def macros(self):
        seen = {}
        for r in self._runs:
            seen[r["macro"]] = r["t"]
        return sorted(seen, key=lambda m: -seen[m])

    def days(self, count=14, end=None):
        """The file's last `count` days, ending on its newest day (so an older file still shows a chart)."""
        if end is None:
            newest = max(list(self._days) + [day_of(r["t"]) for r in self._runs[-1:]], default=None)
            end = time.mktime(time.strptime(newest, "%Y-%m-%d")) + 43200 if newest else time.time()
        out = []
        for back in range(count - 1, -1, -1):
            date = day_of(end - back * 86400)
            out.append((date, self._days.get(date) or dict(_EMPTY_DAY)))
        return out


class _Mine:
    """Your own kept runs, asked the same way as a FileHistory."""
    name = None
    skipped = 0

    @staticmethod
    def runs(macro=None, since=None):
        return runs(macro, since)

    @staticmethod
    def macros():
        return macros()

    @staticmethod
    def days(count=14, end=None):
        return days(count, end)


MINE = _Mine()
