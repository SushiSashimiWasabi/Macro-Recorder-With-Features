"""Macro counters (stage 2a of the core split): the one place that changes a counter.
A counter is a name -> number in a plain dict; Picture watch counting and counter steps run on different
threads, so every change happens under the same lock and never calls out of here while holding it."""

COUNTER_MAX = 10 ** 9  # a counter never goes beyond +-1,000,000,000


def add(values, lock, name, amount):
    """Add to a counter (it starts at 0), keep it within +-COUNTER_MAX, return the new value."""
    with lock:
        values[name] = max(-COUNTER_MAX, min(COUNTER_MAX, values.get(name, 0) + amount))
        return values[name]


def set_value(values, lock, name, value):
    """Give a counter exactly this value, return it."""
    with lock:
        values[name] = value
        return value
