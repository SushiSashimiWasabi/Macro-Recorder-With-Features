"""Trimming a recording: the dead time at its start and end, and long stretches in the middle
where nothing happens.

"Nothing happens" means: no event at all for a while, and no key or mouse button is held down
meanwhile (holding W for ten seconds is not a pause). Mouse wandering before the first and after
the last real action (a key, a click, a scroll, a camera move, a picture step) is dead time too.
Nothing is cut by itself: suggestions() lists what could go, the Edit window lets each one be
ticked, and apply() makes the shorter recording."""

REAL = ("key", "click", "scroll", "move_rel", "wait_picture")
MIN_GAP = 3.0  # a pause in the middle at least this long is suggested
KEEP = 0.5  # how much of a cut pause stays


def _real(ev):
    return ev.get("type") in REAL


def suggestions(events, min_gap=MIN_GAP, keep=KEEP):
    """What could be cut, in order: dicts {"kind": "start" | "end" | "gap", "at": seconds into the
    recording, "seconds": how much time goes, "index": the event the cut is before (gap), "text"}."""
    out = []
    if not events:
        return out
    real = [i for i, ev in enumerate(events) if _real(ev)]
    first = real[0] if real else 0
    last = real[-1] if real else len(events) - 1
    lead = events[first]["t"]
    if lead > 0.05:
        moves = f" (with {first} mouse moves)" if first else ""
        out.append({"kind": "start", "at": 0.0, "seconds": lead, "index": first,
                    "text": f"Start: {lead:.1f} s before the first action{moves}"})
    held = set()
    for i in range(first, last):
        ev = events[i]
        if ev.get("type") == "key":
            key = ("k", repr(sorted(ev.get("key", {}).items())))
            held.add(key) if ev.get("pressed") else held.discard(key)
        elif ev.get("type") == "click":
            key = ("b", ev.get("button"))
            held.add(key) if ev.get("pressed") else held.discard(key)
        gap = events[i + 1]["t"] - ev["t"]
        if gap >= min_gap and not held and gap - keep > 0.05:
            out.append({"kind": "gap", "at": ev["t"], "seconds": gap - keep, "index": i + 1,
                        "text": f"At {clock(ev['t'])}: nothing happens for {gap:.1f} s (it would wait {keep:g} s)"})
    tail = events[-1]["t"] - events[last]["t"]
    if tail > 0.05 and last < len(events) - 1:
        out.append({"kind": "end", "at": events[last]["t"], "seconds": tail, "index": last + 1,
                    "text": f"End: {tail:.1f} s of mouse moves after the last action"})
    return out


def apply(events, chosen):
    """A new list of events with the chosen suggestions cut out (the events themselves are copies)."""
    start = next((c for c in chosen if c["kind"] == "start"), None)
    end = next((c for c in chosen if c["kind"] == "end"), None)
    gaps = {c["index"]: c["seconds"] for c in chosen if c["kind"] == "gap"}
    first = start["index"] if start else 0
    stop = end["index"] if end else len(events)
    shift = events[first]["t"] if start else 0.0
    out = []
    for i in range(first, stop):
        shift += gaps.get(i, 0.0)
        ev = dict(events[i])
        ev["t"] = round(max(0.0, ev["t"] - shift), 4)
        out.append(ev)
    return out


def saved_seconds(chosen):
    return sum(c["seconds"] for c in chosen)


def clock(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02}"
