"""Start playing later rules: plain functions, no window, no settings file, no clock of their own (the window part,
the countdown and the start-up entry are in timed_start_ui.py). Times are seconds since 1970, as time.time() gives."""
import time

SCHEDULE_DEFAULTS = {"alarm_on": False, "alarm": "07:00", "daily": False, "timer_on": False, "timer_min": 30,
                     "timer_repeat": False, "timer_from": 0.0, "when": "play", "open": "", "macro": "",
                     "alarm_last": ""}
TIMER_REPEAT_MIN = 5


def clean_hhmm(text):
    """"07:30" from "7:30" / "07:30"; None when it isn't a time (00-23 : 00-59)."""
    try:
        h, m = (int(p) for p in str(text).strip().split(":", 1))
    except (ValueError, AttributeError):
        return None
    return f"{h:02d}:{m:02d}" if 0 <= h < 24 and 0 <= m < 60 else None


def parse_when(text, now=None):
    """"21:30" (today, or tomorrow if that's past), "in 15" / "+15" / "15" minutes: the time (seconds
    since 1970), or None when it isn't one of those."""
    now = now or time.time()
    text = str(text or "").strip().lower().replace("in ", "").replace("min", "").strip()
    if ":" in text:
        try:
            h, m = (int(p) for p in text.split(":", 1))
        except ValueError:
            return None
        if not (0 <= h < 24 and 0 <= m < 60):
            return None
        t = time.localtime(now)
        at = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, h, m, 0, 0, 0, -1))
        return at if at > now + 5 else at + 86400
    try:
        minutes = float(text.lstrip("+"))
    except ValueError:
        return None
    return now + minutes * 60 if 0 < minutes <= 24 * 60 else None


def _whole(value, default, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def clean_schedule(saved):
    """The saved schedule (Settings > Playback > Start playing later), checked: the alarm (HH:MM, every day or once),
    the timer (N minutes, again and again or once) and what happens when one goes off."""
    saved = saved if isinstance(saved, dict) else {}
    out = dict(SCHEDULE_DEFAULTS)
    for k in ("alarm_on", "daily", "timer_on", "timer_repeat"):
        out[k] = saved.get(k) is True
    out["alarm"] = clean_hhmm(saved.get("alarm")) or out["alarm"]
    out["timer_min"] = _whole(saved.get("timer_min", 30), 30, 1, 24 * 60)
    if out["timer_repeat"]:
        out["timer_min"] = max(TIMER_REPEAT_MIN, out["timer_min"])
    try:
        out["timer_from"] = float(saved.get("timer_from") or 0)
    except (TypeError, ValueError):
        out["timer_from"] = 0.0
    out["when"] = saved.get("when") if saved.get("when") in ("play", "game") else "play"
    out["open"] = str(saved.get("open") or "")
    out["macro"] = str(saved.get("macro") or "")
    out["alarm_last"] = str(saved.get("alarm_last") or "")
    return out


def alarm_today(alarm, now):
    """(the alarm's time today, today as YYYY-MM-DD)."""
    h, m = (int(p) for p in alarm.split(":"))
    t = time.localtime(now)
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, h, m, 0, 0, 0, -1)), time.strftime("%Y-%m-%d", t)


def due(sc, now):
    """(alarm due, timer due, the clock went back). The alarm counts up to 10 minutes late, once a day. When the
    timer's start lies more than a minute ahead (the PC clock went back) it isn't due: count it from now."""
    alarm = False
    if sc["alarm_on"]:
        at, today = alarm_today(sc["alarm"], now)
        alarm = sc["alarm_last"] != today and 0 <= now - at < 600
    if sc["timer_on"] and sc["timer_from"] > now + 60:
        return alarm, False, True
    timer = bool(sc["timer_on"] and sc["timer_from"]) and now >= sc["timer_from"] + sc["timer_min"] * 60
    return alarm, timer, False


def one_start(sc, alarm, timer, now):
    """The alarm and the timer within a minute of each other are one start. Returns (alarm, timer, the schedule
    changes): a once-alarm turns off, a once-timer turns off, a repeating timer counts again from now."""
    if alarm and not timer and sc["timer_on"] and sc["timer_from"]:
        timer = sc["timer_from"] + sc["timer_min"] * 60 - now < 60
    if timer and not alarm and sc["alarm_on"]:
        at, today = alarm_today(sc["alarm"], now)
        alarm = sc["alarm_last"] != today and abs(at - now) < 60
    changes = {}
    if alarm:
        changes["alarm_last"] = alarm_today(sc["alarm"], now)[1]
        if not sc["daily"]:
            changes["alarm_on"] = False  # (once: the time stays filled in)
    if timer:
        if sc["timer_repeat"]:
            changes["timer_from"] = now
        else:
            changes["timer_on"] = False
    return alarm, timer, changes


def on_open(sc, now):
    """When the app opens: (the schedule changes, the timer ran out while the app was closed). A timer with no start
    time, or one that ran out (repeating), counts from now; a once-timer that ran out turns off."""
    if not (sc["timer_on"] and (not sc["timer_from"] or sc["timer_from"] + sc["timer_min"] * 60 < now - 60)):
        return {}, False
    if sc["timer_repeat"] or not sc["timer_from"]:
        return {"timer_from": now}, bool(sc["timer_from"])
    return {"timer_on": False}, True
