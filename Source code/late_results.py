"""Late results (stage 2b of the core split): the rules that decide which run a late MISSION COMPLETED /
FAILED belongs to. A run that ended Unknown may get its result a few seconds later (the results screen
shows after the next run has already started). Plain functions on numbers, a "late" dict and a stats.Session;
what happens around them (history file, Discord, the timer, the lock) stays in core_results."""
import stats


def window(times, limit):
    """How long after an Unknown run its result may still show: `limit` seconds, or half the usual run when runs
    are short (so a real short run isn't taken for the results screen). `times` = seconds of the last won / lost runs."""
    times = times[-10:]
    if not times:
        return limit
    usual = sorted(times)[len(times) // 2]
    return max(1.0, min(limit, usual / 2))


def due(late, kind, now, limit):
    """True when a result `kind` that shows at `now` belongs to the waiting Unknown run `late`."""
    return kind in (stats.WIN, stats.LOSS) and bool(late) and not late.get("given") \
        and now - late["ended"] <= late.get("window", limit)


def apply(session, late, kind):
    """Give the result to the Unknown run in the session (a run that already has a result is left alone)."""
    i = late["index"]
    if 0 <= i < len(session.runs) and session.runs[i][0] == stats.UNKNOWN:
        session.runs[i] = (kind, session.runs[i][1])
        session.streak = session.streak + 1 if kind == stats.WIN else 0


def is_leftover(late, seconds, limit):
    """True when the run that just ended (`seconds` long) came so soon after `late` that it can only be that run's
    results screen."""
    return bool(late) and seconds < late.get("window", limit)


def add_fragments(session, late, fragments):
    """The leftover run's fragments belong to the run before. True when some were handed over."""
    i = late["index"]
    if fragments and 0 <= i < len(session.fragments):
        session.fragments[i] += int(fragments)
        return True
    return False
