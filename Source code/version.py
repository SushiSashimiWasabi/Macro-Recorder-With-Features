# The app's version. Raising it (and pushing to main) makes GitHub publish a new Release,
# which every copy of the app offers to install when it starts.
APP_VERSION = "2.10"

# Every version, newest first: (version, the day it was finalized, changes). The newest is shown once after an update;
# Settings > About > What's new shows them all. Each change is one paragraph (shown as a bullet).
# Version numbers started at 2.1 (the first one that could update itself); the earlier steps have
# names instead.
HISTORY = [
    ("2.10", "16 November 2026", [
        "New sounds (Settings > Sounds): Win, Loss, Divine fragment, Milestone, Timed start warning, Rejoin "
        "countdown (disconnect) and Reopen countdown (game closed). Each can have its own sound file or be "
        "turned off. Win and Loss start off; the others start on.",
        "Before the app gets you back into the game (the rejoin macro after a disconnect, or opening the "
        "game again after it closed) it now counts down with a sound each second, also on the timer at the "
        "top of the screen, so you know it's about to use the mouse. Pause holds the countdown and Stop "
        "ends it. Change its length in Settings > Playback > Countdown before rejoining (5 s; 0 = none).",
        "Check my macro: when you press Play (or Check at the bottom of the main window) the app looks for "
        "things that would make the macro go wrong: a macro a \"Play another macro\" step plays is gone, a "
        "picture or a picture's rejoin macro is missing, the game isn't open, or the screen is very "
        "different from the one it was recorded on. It never stops Play: a line under Saved macros says so "
        "and See… lists them. Each warning can be turned off for one macro, and turned on again in Check.",
        "A missing macro of a \"Play another macro\" step, or a picture step without a picture, no longer "
        "stops Play: that part is skipped (Check my macro tells you).",
        "Older versions of a macro: each time a macro is saved, the version it had before is kept (the last "
        "10, in the app's own folder, never beside the macro). Edit > choose the macro on the left > More > "
        "Restore an older version… puts one back; the macro as it was is kept too, so you can go back.",
        "Run stats > Export… saves every kept run and the daily totals as a file that opens in Excel (dates, "
        "macro names, results, times and fragments only).",
        "Run stats > Open file… shows a stats file someone exported (or drop the file on the app's icon): "
        "the same numbers, chart and latest runs, and Compare with can put one of your own macros next to "
        "one of theirs. It's only looked at: it's never added to your own stats, and Back to my stats "
        "switches back. Lines that don't make sense are left out, and the file can't run anything.",
        "Edit window: More opens again when an action is chosen.",
        "Mac: ⓘ links react to a normal click, message boxes no longer lock up or stick to their window, and "
        "windows are no longer pinned to the window they came from. (Not tried on a real Mac yet.)",
    ]),
    ("2.9.1", "16 November 2026", [
        "Safer sharing: a saved macro no longer carries whole paths of your PC (they could show your Windows "
        "user name). A chain step's macro is saved relative to the macro's own folder, or by its file name, "
        "and a picture's rejoin macro by its file name; both are looked for beside the macro when it's "
        "opened. Re-save macros you shared before to clean them up.",
        "Opening someone's macro that comes with pictures now lists what each picture would do before you "
        "add them, and only known actions and sensible values are taken over.",
        "A picture inside a shared file that claims to be gigantic is refused instead of filling the "
        "memory.",
    ]),
    ("2.9", "15 November 2026", [
        "Picture watch has its own window (Settings > Picture watch > Open Picture watch…, or Picture watch "
        "at the bottom of the main window), made like the Edit window: groups on the left, the group's "
        "pictures in the middle, the chosen picture's options on the right. Rename a group or picture in the "
        "box at the top; Undo, Redo, Reset and Apply work on everything in it, and nothing is used until "
        "Apply.",
        "Groups: General (the options for every picture), AOT:R (the pictures that come with the app: RETRY, "
        "Disconnected, MISSION COMPLETED and MISSION FAILED, each with an ⓘ that says what it's for), My "
        "pictures, and groups you make. A green dot means on, red off, grey: on, but its group is off. "
        "Built-in pictures can be turned off and reset to their built-in settings, and added into your own "
        "groups too.",
        "Each picture can be used for all macros or only for the macros you tick. Macros saved with their "
        "pictures inside now carry only the pictures used for them, and the status line says how many "
        "pictures are watched when you press Play.",
        "The MISSION COMPLETED / FAILED pictures and the Disconnected box's options moved into Picture watch "
        "(AOT:R); Settings > Results keeps the run stats and divine fragments.",
        "Your pictures were sorted into the groups by themselves (the built-in ones into AOT:R, yours into My "
        "pictures). A copy of your settings from before is in the Backups folder beside them.",
        "The red line about fullscreen in Settings > Playback is gone. Instead, a short yellow note shows only "
        "for an opened macro that was recorded before 2.6 (it doesn't know its game window, so in a window "
        "its clicks may miss).",
        "Profiles remember their background too: which picture each window shows, its darkness, fit and "
        "part. Switching a profile (or opening a macro linked to one) swaps the background at once; the "
        "saved pictures stay one list shared by every profile. Removing a picture another profile uses asks "
        "first.",
        "Built-in pictures are on only in AOT:R. A copy in another group (added, moved or duplicated there) "
        "starts off, and its row says \"off: turn on to use here\". Profiles kept from before 2.9 have their "
        "pictures sorted into groups too, so switching to one no longer moves the built-in pictures into My "
        "pictures.",
        "Each picture can have its own Match % and Ignore background (MATCHING > Use its own, off by default; "
        "General has the same for every picture). The list shows the name on the left half and what it does on "
        "the right half; hover a row to see all of it. A note warns when you add a big picture, which can match "
        "game screens by mistake (it can be ticked away).",
        "The log says which picture showed and how well it matched, so a report shows what ended a run. Macros "
        "saved with their pictures inside keep each picture's name and what it does.",
        "No more dark boxes behind the text under Ready when you switch macros, and the Darkness and \"Show "
        "which part\" sliders now follow while you drag.",
        "The Share file can carry the background pictures and GIFs too (it asks; each up to 25 MB). Importing "
        "adds them to your background pictures (none twice) and the shared profile uses them.",
        "A switch on the row of the red \"Playlists aren't supported\" note under Video hides it. Fit clicks to "
        "has one ⓘ with all of its help.",
        "Empty name boxes say what goes there: a grey \"Type a name for this picture\" in Picture watch and "
        "\"Type a name for this macro\" in the Edit window. It goes away as soon as you type.",
        "If / Retry steps that wait for a picture, and the check after a rejoin that the Disconnected box is "
        "gone, use much less CPU: they look where the picture was last seen first, rest between looks, and "
        "look for the Disconnected box only in the middle of the screen.",
        "Settings > Discord > Screenshot size: Sharp (as before) or Smaller, about half the upload for long "
        "nights.",
        "Settings > Playback > Advanced > Saved browser data: shows how much the video window's own Edge "
        "keeps, and Clear… deletes it.",
        "The app opens a little sooner: the Discord, phone remote and video parts load the first time "
        "they're used. The log's health line (every 30 minutes while playing) now also says how long the "
        "picture checks take.",
    ]),
    ("2.8.1", "15 November 2026", [
        "Phone remote: /pair now works only while the Phone remote window is open on the PC, so nobody can "
        "keep guessing the code while you're away. Accounts you already paired keep working as before, and "
        "closing the window gives a new code for next time.",
        "Settings with a background picture: lists that change (Picture watch after adding or changing a "
        "picture, Results pictures, Phone remote accounts) no longer turn partly black.",
        "Long names no longer push buttons off the window: in Picture watch, Change… now sits next to Remove "
        "and a long name or macro name wraps onto the next line; long summaries next to Change… (Stop by "
        "itself, Small random timing, Profile, Daily or weekly summary) are cut short, and the mouse over "
        "them shows all of it.",
    ]),
    ("2.8", "15 November 2026", [
        "Every picture in Picture watch now has its own action (Change… next to it): start the macro over, "
        "play another macro and then start over, switch to another macro, skip to the next step, press a "
        "key, wait, or stop. Each one can have a name, its own \"click on it\", a cooldown, and \"only when "
        "this other picture also shows\".",
        "Chains: the new Edit action \"Play another macro\" plays a saved macro as often as you say. Put a few "
        "under each other (macro A 5 times, then macro B) and turn Repeat on to loop the chain. Each part "
        "counts as a run, and picture watch works inside every part.",
        "Disconnect recovery: give the \"Disconnected\" box's picture the action \"Disconnected: play my rejoin macro\" and "
        "choose your rejoin macro. It plays the macro, checks that the box is gone (and, if you chose one, "
        "that an \"I'm back\" picture shows), then starts the main macro over. Failed tries wait longer each "
        "time; after the last one it stops. Discord is told when it disconnects, gets back or gives up, and "
        "reconnects are counted.",
        "If the game closes completely (Settings > Playback > If the game closes): wait as before, stop, or "
        "open the game again and play a rejoin macro.",
        "Run stats (Settings > Results > Run stats): every run is now kept between sessions. See the win rate, "
        "average and usual run time, best and longest run, fragments an hour and a chart of the last 14 days, "
        "for one macro or all, next to another macro to compare. Unusually slow runs are marked.",
        "Stop by itself (Settings > Playback): after a number of runs, fragments or minutes, or at a time of "
        "day; in the middle of a run or after it. Afterwards it can close the game, put the PC to sleep or "
        "shut it down (with a countdown you can cancel). Discord is told 5 minutes before a timed stop.",
        "Small random timing (Settings > Playback > Advanced, off unless you turn it on): each action a few "
        "milliseconds earlier or later and clicks within a few pixels, for steadier long loops. Each macro can "
        "have its own amounts or never use it.",
        "Discord daily and weekly summary (Settings > Discord): runs, wins and losses, fragments, time and the "
        "best run; the weekly one comes with a chart and your record days.",
        "Trim (Edit > a recorded part > Trim…): finds the wait at the start, mouse wandering at the end and "
        "long pauses in the middle where no key is held, and cuts only the ones you tick.",
        "Profiles (Settings > General > Profile): named sets of all your settings, switched with one click. A "
        "macro can be linked to a profile, so opening it switches; in a chain, each part can use a profile's "
        "speed and random timing.",
        "Phone remote: /stats, /profile and /keepgoing (cancels \"Stop by itself\"); the status card shows a "
        "planned stop, reconnects and the chain part that's playing.",
        "Emergency stop: Ctrl+Alt+End always stops playing and recording, whatever the hotkeys are set to.",
        "Edit keeps unapplied changes safe: if the app closes unexpectedly, it offers them back next time.",
        "Run dashboard (the Dashboard link at the bottom of the main window): the macro, its chain, what it's "
        "doing now, today's results, picture watch, stop by itself, profile, Discord and the phone remote on "
        "one page, with Play, Pause and Stop.",
        "Share in one file (Settings > General > Share): Export writes the open macro with the macros it plays, "
        "the Picture watch pictures and their actions, and its linked profile. Import puts it all in place and "
        "asks before adding pictures or a profile. Your Discord link and the phone remote are never inside.",
        "Chains: \"If a run of it fails, play\" for each part, and a chart of the chain (in Edit, drag a box to "
        "move the step) that also shows what each watched picture does.",
        "Settings has a search box (bottom left), and a first start asks three questions to set the app up.",
        "Discord: \"One card that updates\" changes the same card after each run instead of posting a new one. "
        "Phone remote: /pingme pings you once when a fragment drops, a run fails, it disconnects, it stops, or "
        "after a number of runs.",
        "Lighter during long loops: Picture watch no longer searches the whole screen every second for a "
        "picture that hasn't shown yet (like the Disconnected box), and looks for the Disconnected box only "
        "in the middle of the screen. Results look for MISSION FAILED where MISSION COMPLETED showed, and "
        "Wait for a picture steps rest between looks. Searching the whole screen is also several times quicker.",
        "While a macro plays, the PC doesn't go to sleep or turn the screen off by itself (Stop by itself can "
        "still put it to sleep).",
        "Discord: a message that Discord turned away (too many at once) or that couldn't get through is sent "
        "again a little later instead of being lost.",
        "Run stats are saved after every run, so a crash or power cut loses none.",
        "Windows: the app starts much quicker. It now comes as MacroRecorder.exe with a hidden folder named "
        "_internal beside it (keep the two together if you move it), so it no longer unpacks about 150 MB each "
        "time it starts. Updates unpack the new version beside the app and swap it in only after the app has "
        "closed; if anything goes wrong, the old version is put back. A one-file copy moves over to this by "
        "itself on its next update.",
        "Windows: a \"Starting…\" picture shows at once when you open the app, until its window is ready.",
        "Smaller things: a GIF background lets go of memory while a macro plays, playback uses less CPU "
        "between actions, and the log notes every 30 minutes how much memory and CPU the app uses.",
    ]),
    ("2.7", "15 November 2026", [
        "A phone remote through Discord (Settings > Discord > Phone remote…): start, stop, pause and resume "
        "the macro, see what it's doing, get a screenshot and switch to another saved macro, with slash "
        "commands (/start, /stop, /pause, /resume, /status, /screenshot, /macro) or the buttons under the "
        "status message. It uses your own small Discord bot (free; the window shows the steps).",
        "Only Discord accounts you pair are obeyed: type /pair with the code the window shows. The bot's "
        "token stays in this PC's settings.",
        "Start from the phone puts the game's window in front first, and a problem that would show a box on "
        "the PC is told in Discord instead.",
    ]),
    ("2.6.3", "15 November 2026", [
        "Fixed: the Saved macros row counted a macro whose file had been deleted, so the first macro you "
        "opened showed as number 2. Deleted files are now taken off the list by themselves.",
        "The ◀ ▶ arrows only show when the list has more than one macro. With one saved macro that "
        "isn't open, click its name in the row to open it.",
    ]),
    ("2.6.2", "14 November 2026", [
        "Recorded events: in a long recording, a change redraws only the rows after it (much quicker near "
        "the end of the list).",
        "Undo in Edit uses much less memory with long recordings.",
        "Lighter in the background: the settings file is written once after your last change, the app checks "
        "in half as often while idle, and the timer at the top redraws once a second.",
        "Discord screenshots skip a short wait when none of the app's windows are in the picture.",
    ]),
    ("2.6.1", "14 November 2026", [
        "Fixed: while playing, the game's pointer didn't follow the macro's mouse moves until you moved the "
        "real mouse. Moves are now sent as real mouse input, which games like Roblox notice.",
        "A countdown before recording starts, like before playing (Settings > Recording > Countdown; Record "
        "again cancels it), and the timer at the top of the screen also shows while recording.",
        "Fixed: a mouse button could stay held down for a whole run when the click on Record got into the "
        "recording.",
        "Divine fragments in the first or last slot of a full OBTAINED row are counted too, and the Discord "
        "card says \"+1 this run, +1 this session\".",
        "Discord's \"The game's window\" screenshot shows only the game for macros from other recorders too "
        "(like .luvmacro).",
    ]),
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
