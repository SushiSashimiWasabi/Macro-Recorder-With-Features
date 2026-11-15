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
