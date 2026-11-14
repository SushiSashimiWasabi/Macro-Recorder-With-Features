# The app's version. Raising it (and pushing to main) makes GitHub publish a new Release,
# which every copy of the app offers to install when it starts.
APP_VERSION = "2.6"

# Every version, newest first: (version, the day it was finalized, changes). The newest is shown once after an update;
# Settings > About > What's new shows them all. Each change is one paragraph (shown as a bullet).
# Version numbers started at 2.1 (the first one that could update itself); the earlier steps have
# names instead.
HISTORY = [
    ("2.6", "14 November 2026", [
        "A new Edit window: your saved macros on the left, the chosen macro's actions in the middle and the "
        "chosen action's details on the right. Add action (waits, key presses, typing, clicks, mouse moves, "
        "scrolling, Wait for a picture, If / Repeat / Retry groups, Start over, Stop, notes), Duplicate, Remove "
        "and More (move up / down, copy / paste, into / out of a group, group, ungroup, turn off), with shortcuts.",
        "Change a macro's name (its file name) in Edit, with Undo, Redo, Reset and Apply that light up once "
        "something changed.",
        "In Edit, record keys and mouse straight into a macro, or copy another saved macro's actions into it "
        "(at the start, after the chosen action or at the end), and hold a click or key press for as long as "
        "you choose.",
        "Recorded events: Add action (key press, typing, click, mouse move, scroll) and Record here put new "
        "actions anywhere in a recording, and the actions after them move later to make room.",
        "Settings has Redo too, next to Undo, Reset and Apply.",
        "Discord: \"Ping when a divine fragment drops\" pings you on the card of a run that dropped one.",
        "MISSION FAILED is built in: failed runs count as losses instead of Unknown.",
        "Fit clicks to the game window is the default, so macros work in fullscreen and in a window.",
    ]),
    ("2.5", "14 November 2026", [
        "Fixed: Results counted every run as Unknown when MISSION COMPLETED showed a little bigger or smaller "
        "on screen than the picture. Every size is now looked for until it's found, and the size it was found "
        "at is remembered for next time.",
        "Divine fragments: the ones in the OBTAINED row (pink-to-blue frame) are counted after each run and "
        "added to the Discord card ({fragments}, {fragments_session}, {fragments_total}) and the Results page.",
        "Results look at the screen about 7 times quicker and, once found, only at the title's spot; a "
        "\"failed\" title is less likely to be mistaken for a \"completed\" one.",
        "\"Save smaller mouse paths\" (Settings > Recording > Advanced, off at first): macros with a lot of "
        "mouse movement get much smaller files, with the same movement.",
        "Lighter while playing: the timer at the top redraws only when it changes, and the \"game in front\" "
        "check asks Windows less often.",
        "Every new version is now checked by about 75 automatic tests before it's published.",
        "The code is now under the MIT License (the game's pictures and names belong to their owners).",
    ]),
    ("2.4", "14 November 2026", [
        "Record game camera movement: turns made with Shift Lock or by holding the right mouse button are "
        "recorded and played back at the same pace (Settings > Recording).",
        "Pause if the game isn't in front: a pop-up or another window pauses the macro and lets go of every "
        "key; click back into the game and it carries on (Settings > Playback).",
        "Macros remember their game. Pressing Play in this window offers to switch to it, and \"Fit clicks to "
        "the game window\" works even when the window moved or changed size.",
        "Results: wins (MISSION COMPLETED, built in) and losses (your own MISSION FAILED picture) are counted "
        "while playing, with streak, win rate and run times (Settings > Results).",
        "Discord: a results card after each run in your own channel, with a screenshot of the screen, the game "
        "or any program. Edit its text in its own window, with letter styles (𝐁𝐨𝐥𝐝, 𝓒𝓾𝓻𝓼𝓲𝓿𝓮…), and add a name "
        "and a @ping (Settings > Discord).",
        "Picture watch: a safety limit stops the macro if it starts over too often, Shift Lock is freed before "
        "clicking Retry, and your pictures are saved inside the macros you share.",
        "Edit: add a wait, change a wait, and \"Wait for a picture\" steps that wait until something shows on "
        "screen (and can click it).",
        "Video window keys: skip 10 s, volume, mute, pause, speed and next / previous video from the keyboard "
        "(the number pad at first).",
        "AutoHotkey: more scripts open (variables, Random, delays), and Save… can make an .ahk script.",
        "Help: a log file, Make a report in Settings > About (saved as a file to send), and a sound when something goes wrong. Message "
        "boxes use the app's own dark look, small ⓘ buttons explain options, and rarely used ones are under "
        "Advanced.",
        "Steadier timing for quick taps, lighter screen checks while playing, a quicker start and macro files "
        "about a third smaller.",
    ]),
    ("2.3.1", "13 November 2026", [
        "The timer at the top of the screen is one dark colour all over (no grey frame or grey sides).",
    ]),
    ("2.3", "13 November 2026", [
        "Your own app icon and logo: choose any picture (.png, .jpg, .gif, .bmp, .webp, .ico) in Settings > "
        "General, or use one picture for both. Default goes back.",
        "A new built-in picture for the icon, the logo and the exe file's icon.",
        "The Settings background picture fills everything under the page names, down to the buttons.",
    ]),
    ("2.2", "13 November 2026", [
        "A tidier Settings window: plain page names with a blue line, no box lines, only the Close button, "
        "and a shorter Screen size section with an ⓘ button.",
        "Undo / Reset / Apply when something changed in Settings (removed pictures can be undone too).",
        "Settings and its message boxes stay in front of the main window.",
        "Remove in the saved macros row also closes that macro; the name box stays empty until a macro is "
        "opened.",
        "Picture watch looks around the spot it found the picture last time first: about 5 times less work.",
        "Animated backgrounds: a frame rate of 5-30, only the window you're looking at moves, and they pause "
        "while another window (like the game) is in front.",
        "A smaller exe (52 MB instead of 66 MB) and a quicker start; build.bat keeps the previous exe.",
    ]),
    ("2.1", "13 November 2026", [
        "Updates by themselves: when the app starts it checks for a new version on GitHub, asks, then "
        "downloads it, swaps it in and restarts (Settings > About > Updates).",
        "A link to the app's GitHub page in Settings > About.",
    ]),
    ("Video over the game", "12 November 2026", [
        "Paste a YouTube video link and click Show: it plays in a small window that stays on top of the game. "
        "While a macro records or plays, clicks go straight through it.",
        "Settings > Playback > Video window: let clicks always go through, and how see-through it is.",
        "A red note says playlists aren't supported, only single videos.",
    ]),
    ("Sounds and animated backgrounds", "12 November 2026", [
        "Background pictures can be animated .gif files; they stand still while a macro records or plays.",
        "Settings > Sounds: each sound (recording, playing, pause, resume, countdown, picture seen, button "
        "click) can be the default beep, silent, or your own .wav / .mp3, with a 0-100 volume slider.",
        "The Screen size note explains that some macros were recorded in fullscreen, and that the app itself "
        "works in windowed mode too.",
    ]),
    ("Saved macros", "12 November 2026", [
        "Every macro you open or save goes in the Saved macros row (up to 20): the ◀ ▶ arrows switch to the "
        "previous or next one.",
        "No more flicker when texts change over a background picture.",
    ]),
    ("Background pictures", "12 November 2026", [
        "Your own picture behind the main window and the Settings window: up to 5 saved pictures, with "
        "darkness, fit and which part shows. The Settings window can use the same one, its own, or one for "
        "each page.",
    ]),
    ("The dark window", "11 November 2026", [
        "A new dark main window with big Record / Pause / Play / Stop buttons and their keys, a Repeat "
        "continuously switch and the macro's name.",
        "A Settings window with pages, an Edit window to remove actions, and small sounds.",
        "A timer at the top of the screen while playing, with the pause and stop keys; the pause key also "
        "pauses playback.",
        "Record mouse movement on or off, and how detailed.",
    ]),
    ("Mac version", "11 November 2026", [
        "The same app runs on a Mac (not tried on a real Mac yet); macros work on both. GitHub builds the "
        "Windows exe and the Mac app.",
    ]),
    ("Ready for AOT:R", "11 November 2026", [
        "Watch for a picture: while playing, the macro starts over when a picture (like the RETRY button) "
        "shows on screen, and can click it. Several pictures can be watched.",
        "The RETRY picture is built in, with the settings that suit AOT:R, so friends only open their macro "
        "and press Play.",
        "Screen size: macros made on another screen size are fitted to yours.",
        "Change the hotkeys, type any speed (0.01-100x), and a countdown before playing.",
        "Opens macros from other recorders: .luvmacro, TinyTask .rec, Jitbit .mcr and AutoHotkey .ahk.",
    ]),
    ("The first version", "11 November 2026", [
        "Records the mouse and keyboard and plays it back, with F9-F12 as keys.",
        "Save a recording as a .macro file to share with friends, and open it again (or double-click it after "
        "Link .macro files).",
        "Repeat a macro or loop it forever, at the speed you choose.",
        "Play into a background window (experimental).",
    ]),
]

WHATS_NEW = {version: "\n\n".join(changes) for version, _date, changes in HISTORY}
