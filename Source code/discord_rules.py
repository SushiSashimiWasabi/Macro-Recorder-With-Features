"""Discord message rules: plain functions, no window, no network, no screenshots (sending and the screenshot are in
discord_ui.py). Who is pinged, how a run's result is sent, and the cards for a session's end and a disconnect.
`s` is the settings dict; `values` is stats.Session.values(ping)."""
import stats

PROBLEM_COLOR, END_COLOR, BACK_COLOR, WARN_COLOR = 0xFF4757, 0x4F7CFF, 0x2ECC71, 0xFFB238
RECOVERY_TITLES = {"lost": "Disconnected", "back": "Back in the game", "stuck": "A run seems stuck"}


def ping_for(s, problem, dropped=False):
    """The @ping to put in a message ("" = nobody): always, only for problems, or for a divine fragment drop."""
    when = s.get("discord_ping_when", "problems")
    if when == "always" or (when == "problems" and problem) or (dropped and s.get("discord_ping_fragments")):
        return str(s.get("discord_ping", "")).strip()
    return ""


def run_wanted(s, dropped):
    """Whether a finished run is sent at all."""
    return bool(s.get("discord_enabled") and (s.get("discord_runs", True) or (dropped and s.get("discord_ping_fragments"))))


def run_send(s, status, dropped, content):
    """How a finished run is sent: ("live", False) = the one card that updates, or ("own", screenshot?) = a message of
    its own. An unknown result or a divine fragment always gets its own message with a screenshot (so it can be
    looked at later); a run that pings too (the ping wouldn't reach anyone in an edited message)."""
    keep = status == stats.UNKNOWN or dropped
    if s.get("discord_live") and not content.strip() and not keep:
        return "live", False
    return "own", bool(s.get("discord_screenshot", True) or keep)


def session_card(values, text, problem, has_results):
    """The card when playback stops: how it ended, with the session's results."""
    lines = [text]
    if has_results:
        lines.append(f"Completed {values['completed']} · Failed {values['failed']} · "
                     f"Unknown {values['unknown']} · Win rate {values['winrate']}")
    lines.append(f"Total runtime {values['total']}")
    return {"title": f"{values['macro']} · {'Problem' if problem else 'Session ended'}",
            "description": "\n".join(lines), "color": PROBLEM_COLOR if problem else END_COLOR}


def recovery_card(kind, values, text, reconnects):
    """The card for a disconnect screen ("lost"), the game got back ("back") or a stuck run ("stuck")."""
    return {"title": f"{values['macro']} · {RECOVERY_TITLES[kind]}",
            "description": text + "\nReconnects this session: " + str(reconnects),
            "color": BACK_COLOR if kind == "back" else WARN_COLOR}
