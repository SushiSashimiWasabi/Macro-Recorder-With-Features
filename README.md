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
| `Complete build version\` | The finished app: `MacroRecorder.exe` with its hidden `_internal` folder. Use this one. |
| `Previous version\` | The build before, kept by `build.bat` to go back to. |
| `saved macro file\` | Your own macros. |
| `Source code\` | The Python code, `requirements.txt` and tests. |
| `build.bat` / `run.bat` | Build a new exe / run from the source code (`_mac.sh` versions for a Mac). |
| `.github\workflows\build.yml` | Lets GitHub build the Windows and Mac apps. |

## Start it

Double-click `Complete build version\MacroRecorder.exe`. Nothing to install; keep the exe and
`_internal` together if you move it. To give it to a friend, send `MacroRecorder-Windows.zip` from
the newest GitHub Release.

It runs on 64-bit Windows 10 and 11. If SmartScreen says "Windows protected your PC" (the file
isn't signed), click **More info**, then **Run anyway**.

**From the source code:** double-click `run.bat`, or:

```powershell
cd "Source code"
py -m pip install -r requirements.txt
py macro_recorder.py
```

**Rebuilding:** close Macro Recorder, then double-click `build.bat`. The new build goes into
`Complete build version`.

## Use it

A small dark window stays on top of other windows and shows big **Record / Pause / Play / Stop**
buttons. The hotkeys work even when the window isn't focused; change them in **Settings > General**.

| Key | What it does |
| --- | --- |
| F9  | Start or stop recording |
| F10 | Pause or resume recording or playback |
| F11 | Play |
| F12 | Stop playback |

It records mouse moves, clicks, scrolling and keys with their timing. Before playing, choose
**Repeat continuously** (or a number of times), a **Speed** from 0.01 to 100 and a **Countdown**.
A small timer at the top of the screen shows the run number and win/loss count.

**Main features:**
- **Edit window:** change a macro's actions, add waits, keys, clicks, typing, **Wait for a
  picture** and **If / Repeat / Retry** groups.
- **Picture watch:** watches the screen for pictures such as MISSION COMPLETED, MISSION FAILED,
  RETRY or the Disconnected box, then starts the macro over, clicks, plays another macro or stops.
  The AOT:R pictures are built in, so friends can just open their macro and press Play.
- **Results:** counts wins, losses and divine fragments per session and all-time.
- **Discord:** paste a webhook link of your own channel to get a results card with a screenshot
  after each run. Don't share that link.
- **Phone remote:** control the app from Discord on your phone.
- **Game camera (Shift Lock):** records and plays back camera turns (Windows only).
- **Screen size:** clicks are scaled to fit a different screen size or the game's window.
- **Video over the game:** a YouTube video in a small window on top of the game.
- **Your own look:** background pictures and GIFs, sounds, icon and logo.
- **Safety:** the macro pauses if another window covers the game.

Settings are kept in `%APPDATA%\MacroRecorder\settings.json`, one per person.
**Settings > About > Make a report** saves a text file to send when something goes wrong.

## Save and share

**Save...** writes a `.macro` file; send it to a friend together with the app. Open a macro with
**Open...**, by dragging it onto `MacroRecorder.exe`, or by double-clicking it after clicking
**Link .macro files** once. The **Saved macros** row switches between your last 20 macros with
**◀ ▶**.

Since 2.9.1 a `.macro` file never holds full paths of your PC. Macros it plays are found by name
next to it, so share them together in one folder.

**Open...** also converts macros from luvmacro (`.luvmacro`), TinyTask (`.rec`), Jitbit Macro
Recorder (`.mcr`) and AutoHotkey (`.ahk`); **Save...** can also write an `.ahk` script.

## Updates

At start the app checks the newest GitHub Release and, after asking, updates itself and restarts.
Settings and macros are kept. Turn this off in **Settings > About > Updates**.

For the developer: raise `APP_VERSION` in `Source code\version.py` and push to `main`. GitHub
builds Windows and Mac and publishes Release `v<version>`.

## Mac

The same app runs on a Mac, without a few Windows-only parts (such as the game camera). Macros work
on both. It has only been lightly tested on a real Mac.

Get the Mac app from the newest GitHub Release or Actions run (**Apple Silicon** for M1 or newer,
**Intel** for older Macs). Drag it into **Applications**. Because it isn't signed, open it once via
**System Settings > Privacy & Security > Open Anyway**, then allow **Accessibility**,
**Input Monitoring** and **Screen Recording**, and reopen it. On a MacBook, F9-F12 need **fn**, so
pick other keys in Settings.

## Good to know

- The stop key, or **Ctrl+Alt+End** at any time, stops a macro. Held keys and buttons are released.
- To control apps that run as administrator, run the recorder as administrator too.
- Some games block simulated input.

## License

The code is under the [MIT License](LICENSE): you may use, change and share it freely, as long as the
license text and the copyright line stay with it.

The pictures taken from the game (`Source code/retry_default.png`, `Source code/completed_default.png`
and `Source code/tests/data/results_screen_part.png`) and the names "Attack on Titan Revolution"
(AOT:R) and "Roblox" belong to their owners and are not covered by this license. This project is not
affiliated with or endorsed by them.
