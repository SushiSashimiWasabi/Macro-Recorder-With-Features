"""Stop by itself and the Discord daily / weekly summary: plain functions, no window, no settings file, no clock of
their own (the windows, the timer thread, sleep / shut down and sending are in core_guards.py and automation_ui.py).
Times are seconds since 1970, as time.time() gives."""
import math
import time

import stats

THEN = ("nothing", "close", "sleep", "shutdown")  # (core.AUTO_STOP_THEN has their names)
THEN_TEXT = {"nothing": "", "close": ", then close the game", "sleep": ", then sleep", "shutdown": ", then shut down"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MINUTES_MAX = 100000.0
COUNT_MAX = 1000000


def wrap_hhmm(text):
    """"HH:MM" from "h:m" with the hours wrapped at 24 and the minutes at 60 ("25:70" = "01:10"); None when it isn't
    two numbers with a ":" between them."""
    try:
        hh, mm = str(text).split(":")
        return f"{int(hh) % 24:02}:{int(mm) % 60:02}"
    except ValueError:
        return None


def _whole(value, default, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def clean_settings(saved):
    """Settings > Playback > "Stop by itself", checked: {"on", "runs", "fragments", "minutes", "at" ("HH:MM" or ""),
    "finish_run", "then" (one of THEN), "warn"}; 0 / "" = not used."""
    saved = saved if isinstance(saved, dict) else {}
    try:
        minutes = float(saved.get("minutes") or 0)
    except (TypeError, ValueError):
        minutes = 0.0
    if not math.isfinite(minutes):  # (a broken or endless number in the file is "not used", never 100000 min)
        minutes = 0.0
    then = saved.get("then") if saved.get("then") in THEN else "nothing"
    return {"on": bool(saved.get("on", False)), "runs": _whole(saved.get("runs", 0), 0, 0, COUNT_MAX),
            "fragments": _whole(saved.get("fragments", 0), 0, 0, COUNT_MAX),
            "minutes": max(0.0, min(MINUTES_MAX, minutes)), "at": wrap_hhmm(str(saved.get("at") or "").strip()) or "",
            "finish_run": bool(saved.get("finish_run", True)), "then": then, "warn": bool(saved.get("warn", True))}


def plan(auto, now):
    """What "Stop by itself" means for a playback that starts at `now`: the settings plus "deadline" (when to stop,
    or None), "cancelled" and "due"; None when it's off or nothing is set."""
    if not auto["on"] or not (auto["runs"] or auto["fragments"] or auto["minutes"] or auto["at"]):
        return None
    deadlines = []
    if auto["minutes"]:
        deadlines.append(now + auto["minutes"] * 60)
    if auto["at"]:
        hh, mm = (int(v) for v in auto["at"].split(":"))
        lt = time.localtime(now)
        at = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mm, 0, 0, 0, -1))
        deadlines.append(at if at > now + 1 else at + 86400)
    return dict(auto, deadline=min(deadlines) if deadlines else None, cancelled=False, due=None)


def stop_reason(auto, runs, fragments):
    """After a run: why this was the last one (text), or None to go on. `runs` played so far, `fragments` this
    session. A deadline already reached (auto["due"]) counts too."""
    if not auto or auto["cancelled"]:
        return None
    if auto["runs"] and runs >= auto["runs"]:
        return f"{auto['runs']} runs were played"
    if auto["fragments"] and fragments >= auto["fragments"]:
        return f"{fragments} divine fragment{'s' if fragments != 1 else ''} dropped"
    return auto["due"] or None


def settings_text(a):
    """The line in Settings: "After 3 runs or 30 min, then sleep", "At 03:30", "Off"."""
    parts = []
    if a["runs"]:
        parts.append(f"{a['runs']} runs")
    if a["fragments"]:
        parts.append(f"{a['fragments']} fragments")
    if a["minutes"]:
        parts.append(f"{a['minutes']:g} min")
    if a["at"]:
        parts.append(f"at {a['at']}")
    if not a["on"] or not parts:
        return "Off"
    return ("After " + " or ".join(parts)).replace("After at", "At") + THEN_TEXT[a["then"]]


# ---------------------------------------------------------------- the Discord daily / weekly summary

def clean_summary(saved):
    """The saved summary options, checked: {"daily", "at" ("HH:MM"), "weekly", "weekday", "last_daily",
    "last_weekly"} (the last two: the day each was last sent, "YYYY-MM-DD" or None)."""
    saved = saved if isinstance(saved, dict) else {}
    weekday = saved.get("weekday") if saved.get("weekday") in WEEKDAYS else "Sunday"
    return {"daily": bool(saved.get("daily", False)), "at": wrap_hhmm(saved.get("at") or "22:00") or "22:00",
            "weekly": bool(saved.get("weekly", False)), "weekday": weekday, "last_daily": saved.get("last_daily"),
            "last_weekly": saved.get("last_weekly")}


def summary_text(s):
    """The line in Settings: "Every day and every Sunday at 22:00", "Off"."""
    parts = (["every day"] if s["daily"] else []) + ([f"every {s['weekday']}"] if s["weekly"] else [])
    text = " and ".join(parts) + f" at {s['at']}"
    return text[0].upper() + text[1:] if parts else "Off"


def first_sent(old, new, today, hhmm):
    """(last_daily, last_weekly) to save with new options: a summary turned on after today's time has passed
    sends its first one tomorrow; one that was on already keeps its day."""
    passed = hhmm >= new["at"]
    return (old["last_daily"] if old["daily"] else (today if passed else None),
            old["last_weekly"] if old["weekly"] else (today if passed else None))


def due(s, today, hhmm, weekday):
    """The summaries to send now: [] or ["daily"] / ["weekly"] / both. `today` "YYYY-MM-DD", `hhmm` "HH:MM",
    `weekday` 0 = Monday."""
    if not (s["daily"] or s["weekly"]) or hhmm < s["at"]:
        return []
    out = []
    if s["daily"] and s["last_daily"] != today:
        out.append("daily")
    if s["weekly"] and s["last_weekly"] != today and WEEKDAYS[weekday] == s["weekday"]:
        out.append("weekly")
    return out


def clock_text(seconds):
    return "-" if seconds is None else stats.duration_text(seconds)


def card_lines(s, runs, reconnects, day_list=None, records=None):
    """The summary card's lines. `s`: run_history.summary of the runs (None when none are kept), `runs` the day
    totals' runs; for the weekly one `day_list` [(date, totals)] and `records` (run_history.records())."""
    lines = []
    if s:
        rate = f"{s['winrate']:.1f}%" if s["winrate"] is not None else "-"
        lines += [f"**Runs** {s['runs']}  ·  **Won** {s['wins']}  ·  **Failed** {s['losses']}  ·  "
                  f"**Unknown** {s['unknown']}",
                  f"**Win rate** {rate}  ·  **Average run** {clock_text(s['average'])}",
                  f"**Best run** {clock_text(s['best'])}  ·  **Longest** {clock_text(s['worst'])}",
                  f"**Divine fragments** {s['fragments']}  ({s['fragments_per_hour']:.2f} an hour)",
                  f"**Time in runs** {clock_text(s['seconds'])}"]
        if s["slow"]:
            lines.append(f"**Unusually slow runs** {s['slow']}")
    else:
        lines.append(f"**Runs** {runs}")
    if reconnects:
        lines.append(f"**Reconnects** {reconnects}")
    if day_list is not None:
        best = max(day_list, key=lambda kv: kv[1]["runs"])
        lines.append(f"**Best day this week** {best[0]} with {best[1]['runs']} runs")
        rec = records or {}
        if rec.get("runs"):
            lines.append(f"**Record day** {rec['runs'][0]}: {rec['runs'][1]} runs"
                         + (f"  ·  most fragments {rec['fragments'][0]}: {rec['fragments'][1]}"
                            if rec.get("fragments") else ""))
    return lines
