"""Results of the runs of a macro: wins (mission completed), losses (mission failed) and unknown
results, with the streak, win rate and times. Also fills in the {placeholders} of the Discord
message you can edit in Settings > Discord."""

import time

WIN, LOSS, UNKNOWN = "win", "loss", "unknown"
STATUS_TEXT = {WIN: "Victory", LOSS: "Defeat", UNKNOWN: "Unknown"}

DEFAULT_TITLE = "{macro} · Run #{run}"
DEFAULT_CONTENT = "{ping}"
# the text before divine fragments were counted (a saved copy of it is updated to the new one)
OLD_DEFAULT_MESSAGES = [(
    "**Status**\n{status}\n"
    "**Win streak**\n{streak}\n"
    "**Run duration**\n{duration}\n"
    "**Completed**\n{completed} runs\n"
    "**Failed**\n{failed} runs\n"
    "**Unknown results**\n{unknown}\n"
    "**Win rate**\n{winrate}\n"
    "**Average run**\n{average}\n"
    "**Total runtime**\n{total}\n"
    "**Macro**\n{macro}"), (
    "**Status**\n{status}\n"
    "**Win streak**\n{streak}\n"
    "**Run duration**\n{duration}\n"
    "**Completed**\n{completed} runs\n"
    "**Failed**\n{failed} runs\n"
    "**Unknown results**\n{unknown}\n"
    "**Win rate**\n{winrate}\n"
    "**Average run**\n{average}\n"
    "**Total runtime**\n{total}\n"
    "**Divine fragments**\n{fragments_total} in total (+{fragments} this run, {fragments_session} this session)\n"
    "**Macro**\n{macro}")]

DEFAULT_MESSAGE = (
    "**Status**\n{status}\n"
    "**Win streak**\n{streak}\n"
    "**Run duration**\n{duration}\n"
    "**Completed**\n{completed} runs\n"
    "**Failed**\n{failed} runs\n"
    "**Unknown results**\n{unknown}\n"
    "**Win rate**\n{winrate}\n"
    "**Average run**\n{average}\n"
    "**Total runtime**\n{total}\n"
    "**Divine fragments**\n{fragments_total} in total (+{fragments} this run, +{fragments_session} this session)\n"
    "**Macro**\n{macro}")

PLACEHOLDERS = [
    ("{ping}", "who to ping (Ping box)"),
    ("{macro}", "the macro's name"),
    ("{run}", "the run's number"),
    ("{status}", "Victory, Defeat or Unknown"),
    ("{streak}", "wins in a row"),
    ("{duration}", "how long this run took"),
    ("{wins}", "mission completed, this session"),
    ("{losses}", "mission failed, this session"),
    ("{unknown}", "runs with no result picture seen"),
    ("{completed}", "wins / runs, like 394/414"),
    ("{failed}", "losses / runs, like 2/414"),
    ("{winrate}", "wins out of runs with a result, like 99.49%"),
    ("{average}", "average run time"),
    ("{total}", "time since Play was pressed"),
    ("{fragments}", "divine fragments dropped this run"),
    ("{fragments_session}", "divine fragments this session"),
    ("{fragments_total}", "divine fragments in total (all time)"),
    ("{time}", "the time now"),
]


def duration_text(seconds):
    seconds = int(round(max(0.0, seconds)))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h}h {m:02}m"
    if m:
        return f"{m}m {s:02}s"
    return f"{s}s"


class Session:
    """The runs since Play was pressed."""

    def __init__(self, macro="", fragments_before=0):
        self.macro = macro
        self.started = time.time()
        self.runs = []  # (status, seconds)
        self.streak = 0
        self.fragments = []  # divine fragments dropped in each run
        self.fragments_before = fragments_before  # all-time count when the session started

    def add(self, status, seconds, fragments=0):
        self.runs.append((status, seconds))
        self.fragments.append(int(fragments))
        if status == WIN:
            self.streak += 1
        elif status == LOSS:
            self.streak = 0

    def count(self, status):
        return sum(1 for s, _ in self.runs if s == status)

    def values(self, ping=""):
        n = len(self.runs)
        wins, losses = self.count(WIN), self.count(LOSS)
        decided = wins + losses
        last_status, last_secs = self.runs[-1] if self.runs else (UNKNOWN, 0.0)
        average = sum(s for _, s in self.runs) / n if n else 0.0
        return {
            "ping": ping, "macro": self.macro or "Macro", "run": n, "status": STATUS_TEXT[last_status],
            "streak": self.streak, "duration": duration_text(last_secs), "wins": wins, "losses": losses,
            "unknown": self.count(UNKNOWN), "completed": f"{wins}/{n}", "failed": f"{losses}/{n}",
            "winrate": f"{wins * 100 / decided:.2f}%" if decided else "-",
            "average": duration_text(average), "total": duration_text(time.time() - self.started),
            "time": time.strftime("%H:%M"),
            "fragments": self.fragments[-1] if self.fragments else 0,
            "fragments_session": sum(self.fragments),
            "fragments_total": self.fragments_before + sum(self.fragments),
        }

    def summary(self):
        """Short text for the window and the timer at the top: '3 won · 1 failed · 0 unknown'."""
        text = f"{self.count(WIN)} won · {self.count(LOSS)} failed · {self.count(UNKNOWN)} unknown"
        if sum(self.fragments):
            text += f" · {sum(self.fragments)} fragment{'s' if sum(self.fragments) != 1 else ''}"
        return text


def fill(template, values):
    """The template with each {name} replaced; unknown {words} stay as they are."""
    out = str(template)
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out
