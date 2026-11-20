# The app's version. Raising it (and pushing to main) makes GitHub publish a new Release,
# which every copy of the app offers to install when it starts.
APP_VERSION = "2.14.6"

# Every version, newest first: (version, the day it was finalized, changes). The newest is shown once after an update;
# Settings > About > What's new shows them all. Each change is one paragraph (shown as a bullet).
# Version numbers started at 2.1 (the first one that could update itself); the earlier steps have
# names instead.
HISTORY = [
    ("2.14.6", "Finalized 20 November 2026", [
        "Safer play: when another window comes in front, the macro now pauses right before its next key, every time. "
        "Before, on a PC that had been on for a while, it often still waited the usual moment first.",
        "Safer macros from someone else: a file that lets go of Ctrl with a different spelling can no longer slip past "
        "the \"presses the Windows key\" question. (2.14.5 was never released; its change is in this version.)",
    ]),
    ("2.14.5", "Finalized 20 November 2026", [
        "Safer macros from someone else: a macro that holds Ctrl in one action and presses Esc in a later one (Ctrl+Esc "
        "opens the Start menu) now asks first, like one that presses the Windows key. Say No and it plays without "
        "that Esc. A macro of yours that holds Ctrl may ask once too: say Yes and it won't ask again.",
    ]),
    ("2.14.4", "Finalized 20 November 2026", [
        "Macro folders: renaming a folder to a name that's already there no longer saves that name twice (each copy "
        "counted toward the 50-folder limit).",
        "Behind the scenes: the rules of Picture watch groups, the Discord messages and macro folders moved into their "
        "own parts of the app, so they can be checked on their own. Nothing looks different.",
    ]),
    ("2.14.3", "Finalized 20 November 2026", [
        "Phone remote: /repeat inf no longer breaks the command (Discord got no answer). It now says how to write it.",
        "Stop by itself: a broken or endless \"minutes\" number in your saved options no longer becomes \"stop after "
        "100000 min\" (it counts as not used), and a broken \"Then\" value no longer stops Play from starting (it "
        "counts as \"Nothing more\").",
        "Behind the scenes: the rules of the phone remote, Stop by itself, the Discord summary and profiles moved into "
        "their own parts of the app, so they can be checked on their own. Nothing looks different.",
    ]),
    ("2.14.2", "Finalized 20 November 2026", [
        "A broken number in your saved all-time results no longer stops a session from being added to them (and saved). "
        "That number now counts as 0.",
        "Behind the scenes: the rules of Start playing later (the alarm and the timer), Check my macro and the all-time "
        "results moved into their own parts of the app, so they can be checked on their own. Nothing looks different.",
    ]),
    ("2.14.1", "Finalized 20 November 2026", [
        "A broken number in your saved results (for example after a crash or a hand-edited settings file) no longer "
        "stops the milestone check after every run, and can no longer stop Play from starting. That number now counts "
        "as 0.",
        "A setting saved as \"Infinity\" (countdowns, repeat count, match %, waits) no longer stops the app from "
        "opening: it goes back to its usual value.",
        "Behind the scenes: the milestone rules moved into their own part of the app, so they can be checked on their "
        "own. Nothing looks different.",
    ]),
    ("2.14.0", "Finalized 20 November 2026", [
        "Safer sharing. A shared profile (.macropack) now carries only play and look options. It can no longer bring a "
        "start-playing-later alarm, start with Windows, Discord links, hotkeys or trusted macros into your app. "
        "Opening a shared macro no longer switches your profile by itself.",
        "A shared macro that sends a Discord screenshot, or presses the Windows key (or Ctrl+Esc), now asks once "
        "before it runs. Say No and it plays without them. Your own macros with a Discord screenshot step ask once too; "
        "starts you are not there for (Discord, timed) send without the screenshot until you say Yes once.",
        "Playing now pauses at once when another window comes in front, even before the next key press. "
        "Recording keeps keys typed into one program only (the window you chose, or the first one you clicked or typed "
        "into) and says in the log how many it left out.",
        "A macro link to a network share (\\\\server\\share) uses only the file name, and an AutoHotkey file with an "
        "endless loop no longer freezes the app. Shared packs only write macro file types.",
        "Not done yet: profiles you imported before this version may still hold risky keys (they no longer switch on "
        "by themselves), and the Mac app is still untested on a real Mac.",
    ]),
    ("2.13.1", "Finalized 20 November 2026", [
        "Keys on screen no longer hides the game from Picture watch. Before, the box could sit on top of the MISSION "
        "COMPLETED title and the run counted as Unknown. The box is still shown in screen recordings.",
        "If the game's file you saved in Settings > Playback > If the game closes is gone after a Roblox update, the "
        "app now opens the newest copy in the same Versions folder (a new switch there, on at first). It says so in "
        "an orange note, in Check my macro and in the log. Links and program names are never treated as a missing file.",
        "Check my macro now tells you when a macro has no game window saved (so Play can't switch to the game), with a "
        "link to Edit > Game window > Change…. Play also writes in the log which way it went.",
        "Each window's tour (Settings, Edit, Picture watch and the recorded events window) starts by itself the first "
        "time you open it, once. The tour box stays in front when you switch a Settings page, and it closes when a "
        "macro starts playing.",
        "The Discord / phone remote screenshot says when the game's window wasn't found and the whole screen was taken "
        "instead, and the log says why. Two Discord screenshots never run at the same moment now.",
        "When a run ends Unknown, the log now says why: the best match of each result picture and which of the app's own "
        "windows were hidden from the screenshot.",
        "Settings are saved safely: a crash or power cut while saving can no longer leave a cut-off settings file, and a "
        "failed save is written to the log.",
        "Fixes: moving an action out of or into a group no longer splits an If from its Else; an If inside an If could "
        "let the Else after it run by mistake; the win streak is right again after a late result; a folder that can't be "
        "made no longer wipes a macro's folder; a made-up milestone date no longer crashes the Milestones window; one odd "
        "event no longer stops the keys box; a failed screenshot is no longer taken for the picture being gone; a saved "
        "window size that no longer fits is dropped.",
        "Behind the scenes: the app's core was split into smaller files and the counter and late-result rules were "
        "moved into their own parts, each with its own tests (1,287 checks pass on Windows). The Mac version has not "
        "been tested on a real Mac.",
    ]),
    ("2.13", "Finalized 19 November 2026", [
        "Windows keep their size: the main window no longer changes size when you switch Repeat continuously, "
        "and Settings has one size for every page, never taller than your screen. Drag a window's corner to make "
        "it bigger or smaller: scroll bars show when it's smaller than its parts, and the size is kept. "
        "Settings > General > Reset window sizes puts both back.",
        "The Settings search list closes when you close or move Settings, change page or click somewhere else. "
        "Search also finds the old names of options that were renamed, and jumping to an option scrolls to it.",
        "Change the window a macro plays in without recording it again: Edit > Game window > Change… (or Forget). "
        "Check my macro links there when the macro's game isn't open. When the game isn't in front, the pause "
        "message names it (\"Paused: Roblox isn't in front\") and a Bring Roblox to front button shows under the "
        "timer. Saved .macro files no longer keep the window's full title, only the program's name.",
        "Moving actions in and out of an If or a group: ⇤ Out and In ⇥ buttons next to Duplicate / Remove / More, "
        "and Move out of the group, Move into the group above, Put in a new If / Repeat / Retry and Ungroup in the "
        "right-click menu. Picture watch's right-click menu has Move to group.",
        "Clearer names for many options, like Pause when the macro's window isn't in front, If the game closes or "
        "disconnects, Stats dashboard and Check my macro. Your settings stay as they were.",
        "Milestones (Settings > Results): goals for your all-time results (1,000 runs, 50 divine fragments, 500 "
        "wins in a row, 500 hours played) and your own ones. Reaching one plays the Milestone sound, says so in "
        "the main window and can send a Discord message.",
        "Macro folders and tags: in Edit, right-click a macro to put it in a folder or give it tags, and filter the "
        "list by name, folder or #tag. The main window's Saved macros row can go through one folder only (All ▾). "
        "Your .macro files never move.",
        "Colour themes: pick the accent colour (blue, purple, green, orange, pink or red) in Settings > Background. "
        "It changes at once in every window.",
        "Keys on screen (Settings > Playback): a small box in a corner shows the keys and clicks being played or "
        "recorded, for videos. It shows in screen recordings, and Picture watch never sees it.",
        "A short guided tour of the main window, shown once. Replay it any time from Settings > About.",
    ]),
    ("2.12", "Finalized 18 November 2026", [
        "If a run gets stuck (Settings > Playback, off at first): when neither MISSION COMPLETED nor MISSION "
        "FAILED shows for some minutes (about 3 runs is suggested, from Run stats), it starts the run over, "
        "plays a macro of yours first (to get unstuck or rejoin), or only tells you on Discord. If it stays "
        "stuck it tries again after a longer wait each time, and after the last try it stops and tells Discord. "
        "The minutes don't count while paused, while the game isn't in front, while getting back into the game "
        "or in test plays. RETRY showing counts as a result too. Under its switch it says what it looks for "
        "(MISSION COMPLETED, MISSION FAILED and RETRY, the built-in pictures in Picture watch > AOT:R, and your "
        "own result pictures), in orange when one of them is off or missing, with Open Picture watch.",
        "Edit: new actions. Do maths (a counter = a number or counter + − × ÷ another, whole numbers or 2 "
        "decimals, shown like \"Total: 1+4=5\" on the timer, in the log or on Discord), Read the copied number "
        "(into a counter; the copied text is never logged or sent), Send a Discord message ({Counter} filled "
        "in, with a screenshot if you like), Take a screenshot, Play a sound, Set speed (until the run ends), "
        "Bring the game to the front / wait for it, Label + Go to a label (with a limit you set, and a guard "
        "against endless loops), Wait a random time, and Else after an If. Do maths, Type text and Read the "
        "copied number can play another macro afterwards.",
        "Edit: more options. Keys: combos like Ctrl+E and time between presses. Type text: {Counter} numbers, "
        "Enter at the end, type into another program's window (it comes to the front, then the game does), "
        "letter by letter or paste. Click: where a picture or colour was found, in an area you draw, a random "
        "spot inside, an offset with \"Show where it clicks\", a small random offset; picked spots are kept in "
        "the macro's size. Move: slowly over some seconds, or a camera turn. Scroll: time between notches. "
        "Wait: random. Wait for…: until it's gone, only in an area, and if it doesn't happen: play a macro, "
        "start over or tell Discord. If: check a counter (= ≥ ≤ ≠ > < a number or another counter), a "
        "program being open or the time of day, look for some seconds, and more conditions with AND / OR. "
        "Repeat: until something is true, for some minutes, or until stopped. Retry: how long to check, a wait "
        "between tries, and what to do if every try fails. Stop: a reason and a Discord ping. Note: on the "
        "timer. Play another macro: its own speed. Pictures and colours both say \"How close (%)\".",
        "Times are typed in HH : MM boxes (the \":\" is always there; after two hour digits it jumps to the "
        "minutes, Backspace in empty minutes jumps back, pasting 21:30 fills both): If the time of day, Start "
        "playing later's alarm and Stop by itself. A half-typed time never stops a macro. Else: Add action puts "
        "it right after the If (also when something inside the If is chosen), an Else in the wrong place says "
        "so in orange, and testing an Else plays its If first. Round option buttons stay dark under the mouse.",
        "Macros from someone else: one that types into another program or reads the number you copied asks "
        "once (\"This macro types into notepad.exe. Allow?\"; No skips those steps, and so does a start from "
        "Discord or a timed start nobody answers). What you add in Edit yourself never asks. A macro can never "
        "type into a command window (cmd, PowerShell, Terminal), the registry or the Run box, also not when the "
        "program was renamed. Messages from macros don't ping (@everyone, @here, people, roles) unless you turn "
        "on \"Allow pings in macro messages\" in Settings > Discord.",
        "Settings > Discord > Messages from macros: where those messages go (the run cards' webhook, a channel "
        "the phone remote bot is in, or another webhook), with a test button. The extra webhook stays on this "
        "PC (never in macros, shared profiles or reports, never in the log).",
        "Fixes from a bug hunt: Cancel / Stop now also cancel a timed start that waits for the run's end; a "
        "broken colour in a shared macro no longer stops it from opening; a drawn area can't ask for a giant "
        "screenshot; counting from Picture watch and from steps at the same moment can't lose a count; with "
        "short runs a real run isn't taken for the results screen; /log hides whole paths; a timer after the "
        "PC clock went back no longer waits longer; /schedule answers a bad alarm with a hint. Colour picking: "
        "with several screens, pick on the main one (said in the window and its ⓘ).",
        "Fewer Unknown runs: when a run ends with no result, the app looks once more over the whole screen. "
        "If MISSION COMPLETED or FAILED still shows within 30 seconds, that run gets it (Run stats and "
        "Discord too), and the short bit after it (only the results screen) isn't counted as a run. The log "
        "says each time.",
        "Colour check: If, Retry and Wait for… can check a colour instead of a picture (switch it on in the "
        "step). Pick the spot and its colour on a frozen screenshot (with a live preview), how different it "
        "may be, one pixel or a small square, how long it must stay, and where to look: only the spot (best) "
        "or the whole screen (slower, and other things with that colour can count too). The spot follows "
        "\"Fit clicks to: The game window\".",
        "Start playing later (Settings > Playback): an alarm at HH:MM (once, or every day) and / or a timer of N "
        "minutes (once, or again and again, at least 5 min), both remembered also after the app is closed. When "
        "it starts it can play the open macro, or open the game first (what to open and the rejoin macro, like "
        "\"If the game closes\"). First the \"Timed start warning\" sound, then a countdown you can cancel (also "
        "with Ctrl+Alt+End). If a macro is playing then, it waits for that run to end and starts again. It waits "
        "for the game's window and gives up after the minutes you set. New sound line: \"Timed start countdown\".",
        "Settings > General > When Windows starts (off at first): open Macro Recorder when Windows starts, and "
        "then do nothing, play the open macro, or open the game first (like \"If the game closes\") and then "
        "play a macro you choose. Only one copy opens. The PC isn't woken from sleep for it. (Mac: not made, "
        "untested there.)",
        "Phone remote: /speed (0.1 to 10), /repeat (a number, or loop), /log (the last lines, without paths or "
        "your Windows name) and /schedule (the alarm, every day, the timer, repeat, open the game first, cancel; "
        "empty shows what's planned). The /status message also shows the speed, repeat, profile, the alarm and "
        "timer, the guards and the counters. Every change from the remote is written to the log.",
        "Picture watch: choose many pictures (Ctrl+click, Shift+click or drag), drag them to another place or "
        "onto a group, Copy / Paste / Duplicate (each copy gets its own picture file), turn them on / off or "
        "remove them all at once (more than 5 asks first); one Undo puts it back. The built-in AOT:R group can "
        "only be copied from.",
        "Picture watch: a new \"When it shows\": Add to a counter (name, amount, keep between plays). It watches "
        "all the time while playing and counts once each time the picture shows (it must be gone, and 5 s must "
        "pass, before it counts again); the run goes on. Also for a colour: Picture watch > Colour…",
        "Colour check: \"Where to look\" can be an area you draw (like taking a picture of an area), and Look "
        "now says whether the colour is seen right now, how close the best match is, and where. A spot or area "
        "picked in Edit is kept in the size the macro was made for.",
        "Fixed: in Edit, changing an If / Retry condition's drop-down (shows / doesn't show) or typing its "
        "name gave an error and wasn't kept.",
    ]),
    ("2.11", "17 November 2026", [
        "Edit window: choose many actions (or macros) at once: Ctrl+click adds or takes away one, Shift+click "
        "chooses everything in between, or drag over them. Duplicate, Remove, Copy, Cut (Ctrl+X), Paste, Move "
        "up / down, Turn off / on and Group into then work on all of them, and one Undo puts them back. Drag "
        "chosen actions to move them (a blue line shows where they go). Removing more than 5 asks first.",
        "Test from an action: right-click it > Play from here, or Play only this action. The usual countdown "
        "comes first, Stop and Ctrl+Alt+End work, the timer says TEST, and a test never counts: no results, "
        "run stats, Discord or Stop by itself, and picture watch and rejoining stay off.",
        "Show without playing: the same, but nothing is pressed or clicked. A dot shows where the mouse "
        "would go and the timer shows the keys. Picture steps aren't looked for: they count as found (or as "
        "not found, if you tick that in the menu).",
        "Show my clicks (right-click or More): a picture of your screen with the macro's clicks as numbered "
        "dots and its mouse moves as lines, all at once or one part at a time. Click a dot to choose its "
        "action. The picture is only shown, never saved or sent.",
        "Counters: new actions Add to a counter, Set a counter and If a counter reaches… (whole numbers). "
        "They show in the timer at the top while playing and start at 0 on each Play, unless Keep between "
        "plays is on. Older versions of the app skip these actions and still play the rest.",
        "Record in which window?: pressing Record in the app lists the open windows (and the desktop); the "
        "one you pick comes to the front and the countdown starts. The Record key from a game skips it, and "
        "Settings > Recording can turn it off. It can also link the new macro to a profile (an existing one "
        "or a new one), which only happens when you save it. The record countdown is now 5 s for new users.",
        "Edit the recorded events…: choose many (also by dragging over rows), drag them to move them, "
        "Duplicate, Copy, Cut, Paste, Up / Down, and Undo / Redo. A key's or button's press and let-go always "
        "go together, so nothing stays held down. Removing more than 5 asks first.",
        "Edit the recorded events…: try the chosen rows (right-click or Preview): Play the chosen rows (test, "
        "never counted), Show without playing (nothing is pressed) or Show my clicks. The matching let-go "
        "comes along, and the time between rows that are far apart is skipped.",
        "Record keys and mouse… and Insert another macro… can put the actions inside the chosen group (also "
        "an empty one), and dropping actions on the middle of a group's row puts them inside it.",
        "Show without playing: \"Pretend pictures are NOT found\" is a green (on) / red (off) switch, with "
        "\"What does that mean?\" next to it.",
        "Fixed: a test from Edit did nothing when no macro was open in the main window (it now always starts, "
        "or says why).",
        "Fixed: mouse movement recorded with camera recording on could play back off to the side (up to "
        "hundreds of pixels with a fast mouse). Each camera step now keeps where the pointer was. Record "
        "again to get this in an older macro.",
        "Fixed: camera recording sometimes didn't start (\"Camera recording couldn't start\" in the log), "
        "so a recording had no camera turns.",
        "Short dark message boxes are as wide as the others.",
        "A recording made in Edit (Record keys and mouse…, Record here…) is fitted to the size the macro was "
        "made for, so a macro made on another screen still clicks the right spots everywhere.",
    ]),
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
