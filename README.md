# Macro Recorder

Records what you do with the mouse and keyboard, then plays it back. You can save a recording to a
file and send it to friends.

## What's in this folder

| Folder or file | What it is |
| --- | --- |
| `Complete build version\MacroRecorder.exe` | The finished app, always the newest build. This is the one to use and send to friends. |
| `saved macro file\` | Your own macros. |
| `Source code\` | The Python code (`macro_recorder.py`, `background.py`, `importers.py`, `image_watch.py`), `requirements.txt`, and `bg_test.py` for testing background playback. |
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

A small window stays on top of your other windows. The hotkeys work even when it isn't focused.
These are the starting keys; click **Hotkeys...** to change any of them.

| Key | What it does |
| --- | --- |
| F9  | Start recording, or stop recording |
| F10 | Pause or resume recording (time spent paused is skipped) |
| F11 | Play the recording |
| F12 | Stop playback |

It records mouse movement, clicks (left, right, middle), scrolling and every key, including
shortcuts like Ctrl+C, with the timing between them. The hotkeys above and clicks on the recorder's
own window aren't recorded.

Before playing you can set:
- **Repeat:** how many times to play it.
- **Loop forever:** keep playing until you press the stop key.
- **Speed:** pick a preset or type any speed from 0.01 to 100, like `1.3` or `2.5x`.
- **Get ready:** how many seconds to wait after you press play before the macro starts, so you can
  switch to the game. The window shows the countdown, and the stop key cancels it. 0 starts at once.

## Screen size (play a macro on a different resolution)

**Only works in fullscreen.** Play the game fullscreen, on the main screen.

The **Screen size** box has two choices:
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
game's RETRY button (a picture built into the .exe), with Loop forever on. A friend only has to open
their own macro and press Play. If they remove the picture, **Add built-in RETRY** puts it back.
It was taken on a 1080p screen; on other screen sizes it's resized to match.

To use your own pictures instead:

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

Each time the picture shows counts as one finished run for **Repeat**. After it has been seen, it
must go away before it can count again, so a results screen that stays up doesn't restart the macro
twice. The picture must be visible on your main screen, so this doesn't work with "Play into" a
background window that is covered. It still finds the picture if the game shows it a bit bigger or
smaller (about 15% either way, more if the screen size changed).

## Change the hotkeys

Click **Hotkeys...**, then **Change** next to an action and press the key you want (Esc cancels).
If that key already belongs to another action, the two swap. **Reset to F9-F12** goes back to the
starting keys. Pick keys you don't use in the game: a hotkey is never recorded or played back.

Your hotkeys, speed and get-ready time are remembered for next time in
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

## Open macros from other programs

**Open...** (or dragging a file onto `MacroRecorder.exe`) also reads macros saved by other recorders.
They're converted when opened; click **Save...** to keep a copy as a `.macro` file.

| Program | File | Notes |
| --- | --- | --- |
| luvmacro | `.luvmacro` | Clicks, keys, scrolling and camera-turning mouse moves. |
| TinyTask | `.rec` | Mouse and keys. TinyTask macros turned into `.exe` files can't be opened. |
| Macro Recorder (Jitbit) | `.mcr` | Mouse, keys and delays. Commands like GOTO or text-typing are left out. |
| AutoHotkey | `.ahk` | Simple scripts: Send, Sleep, Click, MouseMove, MouseClick and Loop with a count. Conditions (`if`, `ImageSearch`, variables) are ignored. |
| Pulover's Macro Creator | `.pmc` | Not directly. In Pulover's, use File > Export to AHK and open the `.ahk`. |

After opening, a message says how many steps couldn't be converted. Macros that turn the camera
with the mouse only work when played on the whole screen, not into a background window.

If the other PC's screen size is different, mouse positions are scaled to fit it (see
**Screen size** above).

## Mac

The same app runs on a Mac, with every feature except two Windows-only ones: **Play into** a
background window, and the **Link .macro files** button (on a Mac, double-clicking a `.macro` file
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
Click **Hotkeys...** and pick other keys you don't use in the game.

**Unknown until someone tries it:**
- Camera turning (the mouse moves `.luvmacro` files use) in Roblox on a Mac. It's sent the way a real
  mouse moves, but Roblox may react differently than on Windows, and the camera sensitivity may
  need to match the recorder's.
- Screen sizes: a Mac counts positions in "points" (a Retina screen has 2 pixels per point). The
  "Your screen" box shows the size in points, which is what macros use there, so leave it on Auto.
- The built-in RETRY picture: Roblox may draw it at a different size on a Mac. If **Test now** doesn't
  find it, use **Add from screen...** to take a new picture on the Mac.

## Good to know

- Press the stop key (F12 unless you changed it) at any time to stop a macro that's doing something you didn't expect.
- If a key or mouse button was held down when playback stopped, it's released automatically.
- To record or control apps that run as administrator, start the recorder as administrator too.
- Some games block simulated input, so macros may not work in them.

## Ideas for later

- Edit a recording (delete or change steps, add waits).
- A list of saved macros, each with its own hotkey.
- Wait for a picture at any step inside a macro (not only to restart it).
