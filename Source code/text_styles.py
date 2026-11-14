"""Letter styles for Discord messages, made of special Unicode letters (they show the same for
everyone, anywhere: 𝐁𝐨𝐥𝐝, 𝓒𝓾𝓻𝓼𝓲𝓿𝓮, 𝕲𝖔𝖙𝖍𝖎𝖈, ...), and turning them back into plain letters.

Discord's own formatting (**bold**, *italic*, __underline__, ~~strike~~, # heading, `code`) is
added by the editor as marks around the text instead."""

import re
import unicodedata

UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWER = "abcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"


def _run(start, letters, exceptions=None):
    out = {c: chr(start + i) for i, c in enumerate(letters)}
    out.update(exceptions or {})
    return out


def _style(upper=None, lower=None, digits=None, up_ex=None, low_ex=None, extra=None):
    table = {}
    if upper is not None:
        table.update(_run(upper, UPPER, up_ex))
    if lower is not None:
        table.update(_run(lower, LOWER, low_ex))
    if digits is not None:
        table.update(_run(digits, DIGITS))
    table.update(extra or {})
    return table


SMALL_CAPS = dict(zip(LOWER, "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ"))
CIRCLED = _style(0x24B6, 0x24D0, extra={"0": "⓪", **{str(i): chr(0x2460 + i - 1) for i in range(1, 10)}})

# name in the editor -> letter table
STYLES = {
    "Normal": {},
    "𝐁𝐨𝐥𝐝": _style(0x1D400, 0x1D41A, 0x1D7CE),
    "𝐼𝑡𝑎𝑙𝑖𝑐": _style(0x1D434, 0x1D44E, low_ex={"h": "ℎ"}),
    "𝑩𝒐𝒍𝒅 𝒊𝒕𝒂𝒍𝒊𝒄": _style(0x1D468, 0x1D482),
    "𝓒𝓾𝓻𝓼𝓲𝓿𝓮": _style(0x1D4D0, 0x1D4EA),
    "𝒮𝒸𝓇𝒾𝓅𝓉": _style(0x1D49C, 0x1D4B6,
                      up_ex={"B": "ℬ", "E": "ℰ", "F": "ℱ", "H": "ℋ", "I": "ℐ", "L": "ℒ", "M": "ℳ", "R": "ℛ"},
                      low_ex={"e": "ℯ", "g": "ℊ", "o": "ℴ"}),
    "𝕲𝖔𝖙𝖍𝖎𝖈": _style(0x1D56C, 0x1D586),
    "𝔻𝕠𝕦𝕓𝕝𝕖": _style(0x1D538, 0x1D552, 0x1D7D8,
                    up_ex={"C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"}),
    "𝗦𝗮𝗻𝘀 𝗯𝗼𝗹𝗱": _style(0x1D5D4, 0x1D5EE, 0x1D7EC),
    "𝘚𝘢𝘯𝘴 𝘪𝘵𝘢𝘭𝘪𝘤": _style(0x1D608, 0x1D622),
    "𝙼𝚘𝚗𝚘": _style(0x1D670, 0x1D68A, 0x1D7F6),
    "Ｗｉｄｅ": _style(0xFF21, 0xFF41, 0xFF10, extra={" ": "　"}),
    "Sᴍᴀʟʟ ᴄᴀᴘs": SMALL_CAPS,
    "Ⓒⓘⓡⓒⓛⓔⓓ": CIRCLED,
}

_BACK = {}
for _table in STYLES.values():
    for _plain, _fancy in _table.items():
        _BACK.setdefault(_fancy, _plain)


def to_plain(text):
    """Special letters back to normal ones (𝐁𝐨𝐥𝐝 -> Bold), and invisible characters removed."""
    text = "".join(_BACK.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKC", text)
    return re.sub("[​-‏⁠﻿]", "", text)


def is_styled(text):
    """True if the text has special letters (or invisible characters) that to_plain would change."""
    return to_plain(text) != text


def apply(style, text):
    """The text in a letter style. {placeholders} like {run} stay as they are, so they still work."""
    table = STYLES.get(style, {})
    out = []
    for part in re.split(r"(\{\w+\})", to_plain(text) if table else text):
        if re.fullmatch(r"\{\w+\}", part):
            out.append(part)
        else:
            out.append("".join(table.get(ch, ch) for ch in part))
    return "".join(out) if table else to_plain(text)


# Discord's own formatting: name -> (mark before, mark after); a heading goes at the line's start
MARKS = {"Bold": ("**", "**"), "Italic": ("*", "*"), "Underline": ("__", "__"), "Strike": ("~~", "~~"),
         "Code": ("`", "`"), "Spoiler": ("||", "||")}


def preview_spans(text):
    """Split Discord-formatted text into (piece, set of looks) for the editor's preview."""
    spans = []
    for line in text.split("\n"):
        looks_line = set()
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            looks_line.add("h" + str(len(m.group(1))))
            line = m.group(2)
        pos = 0
        pattern = re.compile(r"(\*\*(.+?)\*\*|__(.+?)__|~~(.+?)~~|\|\|(.+?)\|\||`(.+?)`|\*(.+?)\*|_(.+?)_)")
        for mm in pattern.finditer(line):
            if mm.start() > pos:
                spans.append((line[pos:mm.start()], set(looks_line)))
            whole = mm.group(1)
            if whole.startswith("**"):
                inner, look = mm.group(2), "bold"
            elif whole.startswith("__"):
                inner, look = mm.group(3), "underline"
            elif whole.startswith("~~"):
                inner, look = mm.group(4), "strike"
            elif whole.startswith("||"):
                inner, look = mm.group(5), "spoiler"
            elif whole.startswith("`"):
                inner, look = mm.group(6), "code"
            else:
                inner, look = mm.group(7) or mm.group(8), "italic"
            for piece, looks in preview_spans(inner)[:-1] or [(inner, set())]:
                spans.append((piece, looks | {look} | looks_line))
            pos = mm.end()
        if pos < len(line):
            spans.append((line[pos:], set(looks_line)))
        spans.append(("\n", set()))
    return spans
