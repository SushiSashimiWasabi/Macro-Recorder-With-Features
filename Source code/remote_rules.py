"""Phone remote rules: plain functions, no window, no settings file, no Discord (the window part, the bot and the
actions are in remote_ui.py). What a typed /speed, /repeat or /schedule means, which name a part of a name picks,
and the /pair code check."""
import hmac

import start_later

SPEED = (0.1, 10.0)  # (2.12) /speed's limits
REPEAT_MAX = 9999
PAIR_TRIES = 5  # a new pairing code after this many wrong ones
LOOP_WORDS = ("loop", "forever", "always", "0")
OFF_WORDS = ("off", "no", "cancel")
ALARM_HELP = "Give the alarm as a time like 21:30 (00:00 to 23:59), or off."


def parse_speed(value):
    """/speed: (speed, None), or (None, what to tell the user)."""
    try:
        speed = round(float(value), 2)
    except (TypeError, ValueError):
        return None, "Give a speed like 1, 1.5 or 0.5."
    if not (SPEED[0] <= speed <= SPEED[1]):
        return None, f"The speed must be between {SPEED[0]:g} and {SPEED[1]:g}."
    return speed, None


def parse_repeat(value):
    """/repeat: (times, None) with 0 = loop until stopped, or (None, what to tell the user)."""
    text = str(value or "").strip().lower()
    if text in LOOP_WORDS:
        return 0, None
    try:
        times = int(float(text))
    except (ValueError, OverflowError):  # (OverflowError: "inf")
        return None, f"Give a number of times (1 to {REPEAT_MAX}), or loop."
    if not 1 <= times <= REPEAT_MAX:
        return None, f"The number of times must be between 1 and {REPEAT_MAX}."
    return times, None


def pick_name(names, wanted):
    """The name that is `wanted` (any case), else the first that holds it; None when none does."""
    wanted = str(wanted).lower()
    return next((n for n in names if n.lower() == wanted), None) \
        or next((n for n in names if wanted and wanted in n.lower()), None)


def schedule_options(value):
    """/schedule's options as a dict ({} = just show what's planned)."""
    if isinstance(value, str) and value.strip().lower() in ("cancel", "off", "stop", "no"):
        return {"cancel": True}
    return value if isinstance(value, dict) else ({"alarm": value} if value else {})


def schedule_changes(opts, now, timer_max=1440):
    """(changes to the schedule, None), or (None, what to tell the user). Checks only what was typed; the app
    checks what needs the PC (something to open, a macro open)."""
    changes = {}
    if opts.get("cancel"):
        changes.update(alarm_on=False, timer_on=False)
    alarm = opts.get("alarm")
    if alarm is not None and not isinstance(alarm, str):
        return None, ALARM_HELP
    if isinstance(alarm, str) and alarm.strip():
        if alarm.strip().lower() in OFF_WORDS:
            changes["alarm_on"] = False
        else:
            hhmm = start_later.clean_hhmm(alarm)
            if hhmm is None:
                return None, ALARM_HELP
            changes.update(alarm_on=True, alarm=hhmm, alarm_last="")
    if isinstance(opts.get("every_day"), bool):
        changes["daily"] = opts["every_day"]
    timer = opts.get("timer")
    if timer is not None:
        try:
            minutes = int(timer)
        except (TypeError, ValueError, OverflowError):
            return None, "Give the timer in minutes (0 = off)."
        if minutes <= 0:
            changes["timer_on"] = False
        else:
            changes.update(timer_on=True, timer_min=min(timer_max, minutes), timer_from=now)
    if isinstance(opts.get("repeat"), bool):
        changes["timer_repeat"] = opts["repeat"]
    if isinstance(opts.get("open_game"), bool):
        changes["when"] = "game" if opts["open_game"] else "play"
    return changes, None


def check_code(typed, code, fails):
    """/pair: (right, wrong tries now, make a new code). Only the digits of what was typed count; each code works
    once, and a new one comes after PAIR_TRIES wrong tries (so nobody can keep guessing)."""
    typed = "".join(c for c in str(typed or "") if c.isdigit())
    if hmac.compare_digest(typed, code):
        return True, 0, True
    fails += 1
    return (False, 0, True) if fails >= PAIR_TRIES else (False, fails, False)
