"""Milestone rules: plain functions, no window, no settings file, no sound (the window part is milestones_ui.py).

A milestone is {"kind", "at", "name"?, "reached"? ("YYYY-MM-DD")}; totals are {kind: number}."""
import datetime

import stats

KINDS = {"runs": "Runs", "wins": "Wins", "fragments": "Divine fragments", "streak": "Wins in a row",
         "hours": "Hours played"}
DEFAULT_MILESTONES = [{"kind": "runs", "at": 1000}, {"kind": "fragments", "at": 50}, {"kind": "streak", "at": 500},
                      {"kind": "hours", "at": 500}]
MAX_MILESTONES = 30
MAX_AT = 1_000_000_000


def clean_milestone(m):
    """One milestone from the settings file, checked (None when it makes no sense)."""
    if not isinstance(m, dict) or m.get("kind") not in KINDS:
        return None
    try:
        at = int(m.get("at"))
    except (TypeError, ValueError, OverflowError):
        return None
    if not 1 <= at <= MAX_AT:
        return None
    out = {"kind": m["kind"], "at": at}
    name = " ".join(str(m.get("name") or "").split())[:40]
    if name:
        out["name"] = name
    reached = m.get("reached")
    try:
        out["reached"] = datetime.date.fromisoformat(reached).isoformat()  # (a made-up date would crash the window)
    except (TypeError, ValueError):
        pass
    return out


def milestone_name(m):
    if m.get("name"):
        return m["name"]
    n = f"{m['at']:,}"
    return {"runs": f"{n} runs", "wins": f"{n} wins", "fragments": f"{n} divine fragments",
            "streak": f"{n} wins in a row", "hours": f"{n} hours played"}[m["kind"]]


_number = stats.saved_number  # (a broken or endless saved count is 0: it used to stop every check)


def totals(stats_all, session, now):
    """All-time totals: the saved all-time results plus the session that's playing (if not added yet)."""
    a = stats_all if isinstance(stats_all, dict) else {}
    out = {"runs": int(_number(a.get("runs", 0))), "wins": int(_number(a.get("wins", 0))),
           "fragments": int(_number(a.get("fragments", 0))), "streak": int(_number(a.get("best_streak", 0))),
           "hours": _number(a.get("seconds", 0)) / 3600}
    if session is not None and session.runs and not getattr(session, "added", False):
        out["runs"] += len(session.runs)
        out["wins"] += session.count(stats.WIN)
        out["fragments"] += sum(session.fragments)
        out["hours"] += max(0.0, now - session.started) / 3600
    return out


def streak(runs, before, best_before):
    """Wins in a row (now, best) after these runs: a loss ends it, an unknown run doesn't."""
    now, best = int(before), int(best_before)
    for status, _seconds in runs:
        if status == stats.WIN:
            now += 1
        elif status == stats.LOSS:
            now = 0
        best = max(best, now)
    return now, best


def mark_reached(milestones, totals_now, today):
    """Gives `today` to every milestone not reached yet whose total is there; returns those (odd entries skipped)."""
    out = []
    for m in milestones:
        if not isinstance(m, dict) or m.get("kind") not in KINDS or m.get("reached"):
            continue
        try:
            at = int(m.get("at", 0))
        except (TypeError, ValueError, OverflowError):
            continue
        if totals_now.get(m["kind"], 0) >= at:
            m["reached"] = today
            out.append(m)
    return out


def check_new(kind, at, existing):
    """Your own milestone, checked: (the number, "") or (None, the note to show)."""
    if kind not in KINDS:
        return None, "Choose what it counts."
    try:
        at = int(str(at).replace(",", "").strip())
    except ValueError:
        return None, "Type a whole number, like 250."
    if not 1 <= at <= MAX_AT:
        return None, "Type a number from 1 to 1,000,000,000."
    if len(existing) >= MAX_MILESTONES:
        return None, f"There can be {MAX_MILESTONES} milestones at most. Remove one first."
    if any(m["kind"] == kind and m["at"] == at for m in existing):
        return None, "That milestone is already in the list."
    return at, ""
