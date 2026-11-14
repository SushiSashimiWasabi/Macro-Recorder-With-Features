# Macro Recorder

Records what you do with the mouse and keyboard, then plays it back. You can save a recording to a
file and send it to friends.

It was made mainly to grind **AOT:R** (Attack on Titan Revolution, on Roblox): it starts a mission
over by itself, counts wins, losses and divine fragments, and reports them to Discord. But it works
just as well as an everyday macro recorder for anything else, and every feature can be freely
customized.

## What's in this folder

| Folder or file | What it is |
| --- | --- |
| `Complete build version\MacroRecorder.exe` | The finished app, always the newest build. This is the one to use and send to friends. |
| `Previous version\MacroRecorder.exe` | The build before the newest one, kept by `build.bat` to go back to if needed. |
| `saved macro file\` | Your own macros. |
| `Source code\` | The Python code: `macro_recorder.py` (recording and playback), `modern_ui.py` (the window; its parts are `ui_common.py`, `settings_pages.py`, `settings_window.py`, `discord_ui.py`, `results_ui.py`, `edit_window.py`, `macro_editor.py`, `video_ui.py`), `macro_steps.py` (macros made of steps), `backdrop.py` (background pictures), `sounds.py`, `background.py`, `importers.py` (other programs' macros, saving as .ahk), `image_watch.py` (finding pictures), `stats.py` (results), `discord_notify.py`, `text_styles.py`, `raw_mouse.py` (camera), `window_tools.py`, `diag.py` (log and report), `lazy.py`; `requirements.txt`, and `bg_test.py` for testing background playback. |
| `build.bat` | Builds a new `MacroRecorder.exe` from the source code. |
| `run.bat` | Runs the app straight from the source code, without building. |
| `build_mac.sh`, `run_mac.sh` | The same two for a Mac (they only work on a Mac). |
| `.github\workflows\build.yml` | Lets GitHub build the Windows .exe and the Mac app (see "Mac" below). |

## Start it

**Easiest:** double-click `Complete build version\MacroRecorder.exe`. It's a single file that runs
without installing anything, so you can send it to friends as it is.

**Which Windows PCs it runs on:** Windows 10 and Windows 11, 64-bit. Almost every PC sold in the last
ten years is 64-bit. It does **not** run on 32-bit Windows, on Windows 7 or 8, or on a PC in
"Windows S mode" (which only allows Store apps). Windows 11 laptops with an ARM chip (Snapdragon)
run it through Windows' built-in emulation, a bit slower; that hasn't been tried.

The first time a friend runs it, Windows SmartScreen may say "Windows protected your PC" because the
file isn't signed. They click **More info**, then **Run anyway**. Some antivirus programs also
wrongly flag unsigned single-file Python apps like this one.

**From the source code:** double-click `run.bat`, or in PowerShell:

```powershell
cd "Source code"
py -m pip install -r requirements.txt
py macro_recorder.py
```

**Rebuilding the .exe** after changing the code: double-click `build.bat`. It installs PyInstaller
and puts the new `MacroRecorder.exe` in `Complete build version`, replacing the old one. Close
Macro Recorder first, because Windows won't let a running program be replaced. PyInstaller's
working files go to your Temp folder, so they don't clutter this one.

## Use it

A small dark window stays on top of your other windows (turn that off in Settings). It shows what
the app is doing, big **Record / Pause / Play / Stop** buttons with their keys, a **Repeat
continuously** switch, the speed, and your macro's name with **Edit... / Open... / Save...**.
The hotkeys work even when the window isn't focused. These are the starting keys; change them in
**Settings > General**.

| Key | What it does |
| --- | --- |
| F9  | Start recording, or stop recording |
| F10 | Pause or resume recording (time spent paused is skipped), or pause / go on with playback |
| F11 | Play the recording |
| F12 | Stop playback |

It records mouse movement, clicks (left, right, middle), scrolling and every key, including
shortcuts like Ctrl+C, with the timing between them. The hotkeys above and clicks on the recorder's
own window aren't recorded.

Before playing you can set:
- **Repeat continuously:** keep playing until you press the stop key. Turn it off to type how
  many times to play it.
- **Speed:** pick a preset or type any speed from 0.01 to 100, like `1.3` or `2.5x`.
- **Countdown** (Settings > Playback): how many seconds to wait after you press play before the
  macro starts, so you can switch to the game. The stop key cancels it. 0 starts at once.

**Timer at the top of the screen:** while a macro plays, a small box at the top middle of your main
screen shows the countdown, then "Playing" with how long it's been going, the run number, and the
keys that pause and stop it. It stays there even when the app is minimized, and clicks go straight
through it (on Windows). Turn it off in Settings > Playback.

**Video over the game:** paste a YouTube video link into the **Video** row (under Saved macros)
and click **Show**. Playlists aren't supported, only single videos (the red note under the row). The video plays with sound in a small window that always stays on
top of the game. Move it by its title bar and resize it by dragging its edges; it remembers its size
and place. While a macro records or plays, clicks go straight through it and it never takes the
keyboard, so the macro isn't affected (pause the macro to use the video's own buttons). **Close**
(or the window's X) shuts it. Settings > Playback > Video window: let clicks always go through, and
a See-through slider. It uses YouTube's official embedded player (in Edge on Windows), so YouTube's
ads still play, and videos whose owner blocks outside players, and YouTube Mixes, can't play.
You can't open a video while a macro is running; open it first.
**Video keys** (Settings > Playback > Advanced > Change keys...): while the video window is open, keys
(the number pad at first) skip 10 seconds back or forward, change the volume, mute, pause, change
the speed, and go to the next or previous video you showed before, without touching the mouse. They
aren't recorded. YouTube's player doesn't let apps change the quality; use the gear in the video.

**Pausing playback:** press the pause key while a macro plays. It lets go of any keys and buttons
it's holding and waits; press it again to carry on from the same spot.

**Settings** (top right) has tabs:
- **General:** hotkeys, status bar, keep the window on top, link .macro files.
- **Recording:** record mouse movement or not (clicks keep their position either way), **Record
  game camera movement** (see below), how detailed (Smooth, Normal, Light, under Advanced), and Clear.
- **Playback:** countdown, top-of-screen timer, **Offer to switch to the macro's game**, **Pause if
  the game isn't in front**, Screen size with **Fit clicks to**, and under Advanced: Play into and the
  video window.
- **Discord:** messages in your own Discord channel while a macro runs (see below).
- **Picture watch:** see below.
- **Background:** put your own picture behind the window, also an animated `.gif`. **Add...** saves a picture (up to 5),
  and the **◀ ▶** arrows switch between your saved pictures (or none, the plain dark window).
  **Darkness** keeps text readable, **Fit** fills the window or shows the whole picture, and
  **Show which part** slides the picture (drag it or scroll the mouse wheel over it). The Settings
  window can use the same as the main window, its own picture and options, or a different one for
  each page. Pictures are kept in your settings folder, not inside the app, so the .exe you share
  doesn't include them.
- **Sounds:** switch sounds on or off, set the volume, and choose what each thing sounds like
  (recording starts/stops, playing starts/ends, paused, resumed, countdown, picture seen, button
  click): **Default sound**, **No sound**, or **Choose a file...** for a `.wav` or `.mp3` of your
  own. **Try** plays it. Your sounds are kept in your settings folder, not inside the app.

**Icon and logo** (Settings > General): pick your own picture for the app icon (title bar and
taskbar) and for the logo in front of "Macro Recorder" (.png, .jpg, .gif, .bmp, .webp or .ico).
**Logo the same as the app icon** uses one picture for both, **Default** goes back to the built-in
picture (`Source code\default_logo.png`, also the exe file's icon in File Explorer, from
`app_icon.ico`). Your own picture can't change the exe file's icon in File Explorer.

An animated `.gif` background plays in the main and the Settings window. It stands still while a
macro records or plays (so nothing disturbs the macro's timing), and **Play animated pictures**
on the Background page switches the movement off altogether. To keep it light for the computer:
**Frame rate** (5 to 30 pictures a second, default 15), **Only animate the window you're looking at**
and **Pause while another window is in front** (like the game), both on at first.

**Edit...** opens the Edit window: your saved macros on the left, the chosen macro's actions in
the middle and the chosen action's details on the right. **Add action** adds waits, key presses
(held as long as you choose), typing, clicks (also held), mouse moves, scrolling, **Wait for a
picture**, **If** / **Repeat** / **Retry** groups, **Start over**, **Stop** and notes. **Record keys
and mouse...** records straight into the macro, and **Insert another macro...** copies a saved
macro's actions in; both ask where they go (the start, after the chosen action or the end).
**Duplicate**, **Remove** and **More** (move, copy / paste, group, ungroup, turn off) show once you
pick an action. The macro's name box renames its file. **Undo**, **Redo**, **Reset** and **Apply**
light up once something changed.

A recorded part has **Edit the recorded events...**: every recorded action with its time. Select
rows and **Remove selected** (or press Delete), **Remove all mouse moves**, or **Cut the wait at the
start**. **Add action** (a key press, typing, a click, a mouse move or a scroll) and **Record
here...** put new actions anywhere in the recording, and the actions after them move later to make
room. **Add a wait...** puts a pause before the selected row, **Change the wait...** sets the time
between the selected row and the one before it, and **Wait for a picture...** adds a step that stops
the macro until a picture shows on screen, up to a time limit, and can click it. Then **Apply**.

**Game camera (Shift Lock):** with **Record game camera movement** on (Settings > Recording,
Windows only), the app also reads how far the mouse itself moves while the game hides the pointer
(Shift Lock, or holding the right button), the way the game does, and plays those turns back at
the same pace. Use the same in-game camera sensitivity when playing.

**The game in front:** a recording remembers which program it was made in. Pressing Play in this
app's window offers to switch to that game first (or asks before playing if it isn't open). While a
macro plays, if another window comes in front of the game (a pop-up, Discord), the macro lets go of
every key and pauses; click back into the game and it carries on. **Stop after waiting** ends it if
the game stays away that long (0 = keep waiting).

**Results (wins and losses):** Settings > Results has pictures that mean a run was won (the built-in
gold MISSION COMPLETED title, or your own) or lost (add your own MISSION FAILED picture with **Add from
screen...** while it shows). While a macro plays, each run counts as won, lost or unknown. The timer
at the top shows the count, Settings > Results shows the last session and all-time totals, and the
Discord card has the streak, win rate, completed/runs, failed/runs and run times.

**Discord:** in Settings > Discord, paste a webhook link of a channel on your own server (Channel
settings > Integrations > Webhooks > New Webhook > Copy Webhook URL) and switch it on. After each run
you get a results card, and a short summary when playback stops. Choose the name it posts as, who to
ping (`@everyone`, `<@your user ID>`) and when (every message, only failed runs and stops, or never; **Ping when a divine fragment
drops** pings you on that run's card too),
and what the screenshot shows (main screen, all screens, the game's window or any program's window).
**Edit the message...** opens its own window (resize it by its edges; it remembers its size): the
line above the card, the title and the text, with Discord's formatting buttons (bold, italic,
underline, strike, heading, code, spoiler), letter styles (𝐁𝐨𝐥𝐝, 𝓒𝓾𝓻𝓼𝓲𝓿𝓮, 𝕲𝖔𝖙𝖍𝖎𝖈, Ｗｉｄｅ, ...),
`{placeholders}` like `{run}` and `{winrate}`, and a preview. Pasting text with special letters asks
whether to keep them or make it plain. No bot needed. Don't share the link: anyone who has it can post
in that channel.

**Help:** Settings > About > **Make a report** saves the version, your system, screen sizes, a few
settings and the end of the log (`log.txt` in the settings folder) as a text file in the `reports`
folder of the settings folder, and shows a window with **Show the file** (to drag it into Discord,
for example) and **Copy the text**. **Reports and logs...** shows how much room they take and **Clear reports
and logs** deletes them. They stay small on their own: the log keeps at most about 2 MB and only the
last 20 reports are kept. A report never contains macros, keys or your Discord link. When something goes wrong the app says so with
a sound ("Problem" in Settings > Sounds) instead of failing silently. After an update, a window shows
what's new once (also in Settings > About).

## Screen size (play a macro on a different resolution)

**Some macros were recorded in fullscreen, so those only work in fullscreen** (play the game
fullscreen, on the main screen). The app itself works properly in windowed mode too: a macro
recorded in a window plays back fine in the same window.

The **Screen size** box (Settings > Playback) has two choices:
- **Macro recorded at:** the screen size the macro was recorded on. It's filled in by itself for
  macros recorded in this app and for `.luvmacro` files (which store it). For files that don't say,
  like TinyTask or AutoHotkey ones, it shows "Same as your screen" (nothing is changed); pick the size
  if you know it.
- **Your screen:** the size to play at. **Auto** uses your screen's size, which is right for almost
  everyone. Pick a size (or type one, like `2560x1440`) only if Auto shows the wrong one.

When the two differ, every mouse click and mouse position is moved to fit. For example a click at
(1064, 796) on 1920x1080 lands at (1419, 1061) on 2560x1440. Everything is scaled by the height
around the middle of the screen, which is how Roblox fits its 3D view, so it also works on screens
of a different shape (16:10, ultrawide). Buttons that the game sticks to a screen edge may then be a
bit off on those shapes.

Camera turning (the mouse moves a `.luvmacro` uses to look around) isn't changed: the game turns the
camera by the same amount on every screen size. It does depend on the in-game camera sensitivity,
so friends should use the same sensitivity as the person who recorded it. Timing depends on the
game too: a slower PC or a lower frame rate can make a long macro drift.

The size is saved in the `.macro` file, so a friend with another screen can just open it.

## Watch for a picture (start over when a mission is done)

While a macro plays, the app can keep looking at the screen for one or more pictures, like the
"MISSION COMPLETED" and "MISSION FAILED" banners. When any of them shows up, the current run is over: the app lets go of any held
keys, waits a few seconds, and starts the macro again from the beginning. It only looks at
ordinary screenshots; it doesn't read or change the game.

**Ready for AOT:R out of the box:** the first time someone runs the app it already watches for the
game's RETRY button (a picture built into the .exe), with Repeat continuously on. A friend only has to open
their own macro and press Play. If they remove the picture, **Add built-in RETRY** puts it back.
It was taken on a 1080p screen; on other screen sizes it's resized to match.

These options are in **Settings > Picture watch**. To use your own pictures instead:

1. Get the picture on screen (for example finish a mission so the banner shows).
2. Click **Add from screen...**. The screen freezes; drag a box around the picture. For a banner,
   box just the text and the line under it. Esc cancels. (Or use **Add picture file...** for a saved
   PNG/JPG.) Add as many pictures as you like, for example one for Completed and one for Failed;
   **Remove** takes one off the list.
3. Click **Test now** while a picture is showing, and again while it isn't. It lists a score per
   picture. The one showing should be
   well above the **Match** percentage and the second well below. 80% suits most pictures.
4. Tick **While playing, start the macro over...** and set:
   - **When it shows: click on it:** clicks the middle of the picture as soon as it's seen. Use this
     with a button, like the Retry button at the end of a mission. A small picture of just the
     button (or just its word, "RETRY", so a changing vote count doesn't matter) works best.
   - **wait N s:** time for the game to load before the macro starts again.
   - **If the macro ends before the picture shows, wait up to N s for it:** if the macro finishes
     its steps first, it waits this long for the picture, then starts over anyway.
   - **Ignore the background:** only match the bright parts of the picture (text, lines) and the
     pixels right around them, so a different scene behind the banner doesn't matter. Leave it on.

   - **Safety limit:** if the picture starts the macro over more than this many times in that many
     seconds (10 in 60 at first), something is stuck, so the macro stops and says why. 0 = no limit.
   - **Press Shift if the mouse pointer is hidden:** before clicking, frees the mouse from Roblox's
     Shift Lock so the click lands on the button.
   - **Save these pictures inside the macros you save:** a friend who opens your macro is asked
     whether to add its pictures, so they get your Retry picture too.

Each time the picture shows counts as one finished run for **Repeat**. After it has been seen, it
must go away before it can count again, so a results screen that stays up doesn't restart the macro
twice. The picture must be visible on your main screen, so this doesn't work with "Play into" a
background window that is covered. It still finds the picture if the game shows it a bit bigger or
smaller (about 15% either way, more if the screen size changed).

## Change the hotkeys

Open **Settings > General**, then click **Change** next to an action and press the key you want (Esc cancels).
If that key already belongs to another action, the two swap. **Reset to F9-F12** goes back to the
starting keys. Pick keys you don't use in the game: a hotkey is never recorded or played back.

Your hotkeys, speed, countdown and other settings are remembered for next time in
`%APPDATA%\MacroRecorder\settings.json`. Each person who runs the app has their own.

## Save and share

**Save...** writes the recording to a `.macro` file. Send that file, together with
`MacroRecorder.exe` if they don't have it yet, to a friend. Older `.json` recordings open too.

There are three ways to open a macro:
- Click **Open...** and choose the file.
- Drag the `.macro` file onto `MacroRecorder.exe`.
- Double-click the `.macro` file. This works after you click **Link .macro files** once in the app.
  It only changes settings for your own Windows account. If you move `MacroRecorder.exe` to another
  folder, click the button again.

**Saved macros (quick switch):** every macro you open or save is added to the **Saved macros** row
in the main window (up to 20). Click **◀** or **▶** to switch straight to the previous or next one.
**Remove** takes the open macro off that list and opens the next one (or an empty macro when the list is empty); the file itself is never deleted. Files that
were moved or deleted are skipped, and the app asks first if the open macro has unsaved changes.

## Updates

When the app starts, it checks this project's newest GitHub Release. If there's a newer version,
it asks first, then downloads it, puts it in place of the old `MacroRecorder.exe` (or
`MacroRecorder.app` on a Mac) and restarts. It never updates in the middle of recording or
playing. Turn the check off, or check by hand, in **Settings > About > Updates**. Your settings
and macros are kept. Versions from before 2.1 can't update themselves: download 2.1 once from
the Releases page.

For the developer: raise `APP_VERSION` in `Source code\version.py` and push to `main`. GitHub
then builds Windows and Mac and publishes them as Release `v<version>`.

## Open macros from other programs

**Open...** (or dragging a file onto `MacroRecorder.exe`) also reads macros saved by other recorders.
They're converted when opened; click **Save...** to keep a copy as a `.macro` file.

| Program | File | Notes |
| --- | --- | --- |
| luvmacro | `.luvmacro` | Clicks, keys, scrolling and camera-turning mouse moves. |
| TinyTask | `.rec` | Mouse and keys. TinyTask macros turned into `.exe` files can't be opened. |
| Macro Recorder (Jitbit) | `.mcr` | Mouse, keys and delays. Commands like GOTO or text-typing are left out. |
| AutoHotkey | `.ahk` | v1 and v2 scripts: Send, Sleep, Click, MouseMove, MouseClick(Drag), Loop, number variables and sums, Random (its middle value), SetKeyDelay, mouse_event camera moves. Conditions (`if`, `ImageSearch`) are ignored: their actions always play. **Save...** can also write a macro as an AutoHotkey v2 script. |
| Pulover's Macro Creator | `.pmc` | Not directly. In Pulover's, use File > Export to AHK and open the `.ahk`. |

After opening, a message says how many steps couldn't be converted. Macros that turn the camera
with the mouse only work when played on the whole screen, not into a background window.

If the other PC's screen size is different, mouse positions are scaled to fit it (see
**Screen size** above).

## Mac

The same app runs on a Mac, with every feature except these Windows-only ones: **Play into** a
background window, **Record game camera movement**, **Pause if the game isn't in front**, switching
to the macro's game, and the **Link .macro files** button (on a Mac, double-clicking a `.macro` file
works by itself once the app is in Applications). Macro files work both ways: a macro recorded on
Windows plays on a Mac and the other way round. Keys are translated between the two keyboards
(the Windows key becomes Command, Alt becomes Option).

**This hasn't been tried on a real Mac yet.** Nobody working on it has one.

**Getting the Mac app.** A Mac app can only be built on a Mac. Two ways:
- **GitHub (no Mac needed):** this folder is uploaded to GitHub, and GitHub builds the app on its
  own Macs every time the code changes. On the repository's **Actions** tab, open the newest
  **Build** run and download **MacroRecorder-Mac-AppleSilicon** (M1 or newer Macs) or
  **MacroRecorder-Mac-Intel** (older Macs; Apple menu > About This Mac shows which). It also makes
  **MacroRecorder-Windows**.
- **On the Mac itself:** install Python 3 from python.org, then in Terminal, in this folder,
  `bash run_mac.sh` (runs it) or `bash build_mac.sh` (makes `Mac build version/MacroRecorder.app`).

**First start on the Mac (one time):**
1. Unzip, and drag **MacroRecorder.app** into **Applications**.
2. Open it. Because it isn't signed by Apple, macOS says it can't check it. Click **Done**, then go
   to **System Settings > Privacy & Security**, scroll down and click **Open Anyway** next to
   Macro Recorder. (An app built on the Mac itself doesn't get this warning.)
3. Give it three permissions in **System Settings > Privacy & Security**: **Accessibility**,
   **Input Monitoring** and **Screen Recording**. The app shows which are missing when it starts.
   Then quit it and open it again.
4. If it's rebuilt later, macOS may ask for the permissions again: switch them off and on.

**On a MacBook:** F9-F12 are volume/brightness keys unless you hold **fn**, and F11 shows the desktop.
In **Settings > General**, pick other keys you don't use in the game.

**Unknown until someone tries it:**
- Camera turning (the mouse moves `.luvmacro` files use) in Roblox on a Mac. It's sent the way a real
  mouse moves, but Roblox may react differently than on Windows, and the camera sensitivity may
  need to match the recorder's.
- Screen sizes: a Mac counts positions in "points" (a Retina screen has 2 pixels per point). The
  "Your screen" box shows the size in points, which is what macros use there, so leave it on Auto.
- The video window: on a Mac it's a floating window of the app (Safari's engine) that should stay
  above fullscreen games and let clicks through. That was checked on GitHub's Macs, but not with a
  game or with real playback. macOS may ask once to let the app "find devices on local networks".
- The built-in RETRY picture: Roblox may draw it at a different size on a Mac. If **Test now** doesn't
  find it, use **Add from screen...** to take a new picture on the Mac.

## Good to know

- Press the stop key (F12 unless you changed it) at any time to stop a macro that's doing something you didn't expect.
- If a key or mouse button was held down when playback stopped, it's released automatically.
- To record or control apps that run as administrator, start the recorder as administrator too.
- Some games block simulated input, so macros may not work in them.

## Ideas for later

- A hotkey for each saved macro.

## License

The code is under the [MIT License](LICENSE): you may use, change and share it freely, as long as the
license text and the copyright line stay with it.

The pictures taken from the game (`Source code/retry_default.png`, `Source code/completed_default.png`
and `Source code/tests/data/results_screen_part.png`) and the names "Attack on Titan Revolution"
(AOT:R) and "Roblox" belong to their owners and are not covered by this license. This project is not
affiliated with or endorsed by them.
