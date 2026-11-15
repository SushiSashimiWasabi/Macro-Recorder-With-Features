"""The phone remote: start, stop, pause, look at and switch macros from Discord (slash commands
and a message with buttons), plus its window (Settings > Discord > Phone remote…).

The connection itself is discord_remote.py. Only Discord accounts on the "allowed" list are obeyed;
an account gets on it by typing /pair with the code this window shows, so being in the same server
is not enough to control the PC.

Part of the dark window: ModernMacroRecorder (modern_ui.py) inherits this class.
"""

import hmac
import secrets
import threading
import webbrowser

from ui_common import *  # noqa: F401,F403  (colours, fonts, widgets, tk, core, the other modules)

import lazy
discord_remote = lazy.module("discord_remote")  # (loaded when the phone remote is first used)

DEVELOPER_PAGE = "https://discord.com/developers/applications"


def _command(name, description, options=None):
    cmd = {"name": name, "description": description, "type": 1,
           "integration_types": [0], "contexts": [0, 1]}  # in a server, and in a private chat with the bot
    if options:
        cmd["options"] = options
    return cmd


COMMANDS = [
    _command("start", "Start playing the open macro"),
    _command("stop", "Stop the macro"),
    _command("pause", "Pause the macro"),
    _command("resume", "Go on after a pause"),
    _command("status", "What the app is doing, with buttons to control it"),
    _command("screenshot", "A screenshot of the game right now"),
    _command("macro", "Switch to another saved macro", [
        {"type": 3, "name": "name", "description": "The macro's name", "required": True, "autocomplete": True}]),
    _command("stats", "Today's runs, wins, fragments and reconnects"),
    _command("keepgoing", "Cancel \"Stop by itself\" for the macro that's playing"),
    _command("profile", "Switch to another settings profile (no name: list them)", [
        {"type": 3, "name": "name", "description": "The profile's name", "required": False, "autocomplete": True}]),
    _command("pingme", "Ping you when something happens (once)", [
        {"type": 3, "name": "when", "description": "What to wait for", "required": True, "choices": [
            {"name": "a divine fragment drops", "value": "fragment"},
            {"name": "the macro stops", "value": "stop"},
            {"name": "a run fails", "value": "loss"},
            {"name": "it disconnects or the game closes", "value": "lost"},
            {"name": "forget all my pings", "value": "none"}]},
        {"type": 4, "name": "runs", "description": "Or: after this many more runs", "required": False}]),
    _command("pair", "Allow your Discord account to control the app", [
        {"type": 3, "name": "code", "description": "The pairing code shown in the app on the PC",
         "required": True}]),
]

NOT_PAIRED = ("This remote doesn't know your Discord account yet. On the PC, open Settings > Discord > "
              "Phone remote… and type the pairing code shown there here: `/pair` and the code.")
NO_ANSWER = "The app on the PC didn't answer in time. Try again in a moment."
COLORS = {"Playing": 0x4F7CFF, "Paused": 0xFFB020, "Starting": 0xFFB020, "Recording": 0xFF4757, "Ready": 0x2ECC71}

SETUP_STEPS = (
    "1.  Press \"Open Discord's developer page\", sign in, then New Application (any name, like "
    "\"My macro remote\").\n"
    "2.  On that page: Bot (on the left) > Reset Token > Copy. Paste it in the box above and press Connect.\n"
    "3.  Press \"Add the bot to my server…\" and pick your own server.\n"
    "4.  In Discord (also on your phone), type  /pair  and the pairing code shown here.\n\n"
    "After that: /status shows what the app is doing with Start, Pause, Stop and Screenshot buttons. "
    "There are also /start, /stop, /pause, /resume, /screenshot and /macro.")


class RemoteMixin:
    # ------------------------------------------------------------ start and stop of the bot

    def _init_remote(self):
        s = self.settings
        self.remote_win = None
        self.remote_info = {}
        self.remote_lock = threading.Lock()
        self.remote_fails = 0
        self.remote_pairing = False  # /pair works only while the Phone remote window is open
        self.remote_code = self._new_pair_code()
        self.remote_var = tk.BooleanVar(value=bool(s.get("remote_enabled", False)))
        self.remote_token_var = tk.StringVar(value=str(s.get("remote_token", "")))
        self.remote_status_var = tk.StringVar(value="")
        self.remote_code_var = tk.StringVar(value=self._shown_code())
        self.remote = lazy.LazyObject(lambda: discord_remote.Remote(
            get_token=lambda: str(self.settings.get("remote_token", "")) if self.settings.get("remote_enabled") else "",
            handle=self._remote_handle,
            on_status=lambda ok, text, info=None: self._call_ui(lambda: self._remote_status(ok, text, info)),
            commands=COMMANDS, presence=self._remote_presence,
            registered_key=lambda: self.settings.get("remote_commands_key"),
            on_registered=lambda key: self._call_ui(lambda: self._remote_registered(key)),
            log=diag.info), idle={"stop": lambda *a, **k: None, "running": lambda: False})
        self._remote_restart()

    @staticmethod
    def _new_pair_code():
        return f"{secrets.randbelow(10 ** 6):06d}"

    def _shown_code(self):
        return self.remote_code[:3] + " " + self.remote_code[3:]

    def _remote_registered(self, key):
        self.settings["remote_commands_key"] = key
        core.save_settings(self.settings)

    def _remote_status(self, ok, text, info):
        if info:
            self.remote_info = info
        if not self.settings.get("remote_enabled"):
            text = "Off."
        self.remote_ok = ok
        self.remote_status_var.set(text)
        self._remote_refresh_window()

    def _remote_restart(self):
        """Log in again with the token in settings (or log out when it's off or empty)."""
        s = self.settings
        self.remote.stop()
        token = str(s.get("remote_token", "")).strip()
        if not s.get("remote_enabled"):
            self.remote_status_var.set("Off.")
        elif not token:
            self.remote_status_var.set("Paste the bot's token to connect.")
        elif not discord_remote.looks_like_token(token):
            self.remote_status_var.set("That doesn't look like a bot token (it's a long line with two dots in it).")
        else:
            self.remote_status_var.set("Connecting to Discord…")
            self.remote.start()

    def _remote_apply(self):
        """The switch or the token changed in the window."""
        s = self.settings
        before = (bool(s.get("remote_enabled")), str(s.get("remote_token", "")))
        s["remote_enabled"] = bool(self.remote_var.get())
        s["remote_token"] = self.remote_token_var.get().strip()
        core.save_settings(s)
        if before != (s["remote_enabled"], s["remote_token"]) or not self.remote.running():
            self.remote_info = {}
            self._remote_restart()
        self._remote_refresh_window()

    def _remote_users(self):
        users = self.settings.get("remote_users")
        return [u for u in users if isinstance(u, dict) and u.get("id")] if isinstance(users, list) else []

    def _remote_allowed(self, uid):
        return bool(uid) and any(str(u.get("id")) == str(uid) for u in self._remote_users())

    def _remote_add_user(self, uid, name):
        users = [u for u in self._remote_users() if str(u.get("id")) != str(uid)]
        users.append({"id": str(uid), "name": str(name)[:60]})
        self.settings["remote_users"] = users
        core.save_settings(self.settings)
        self.remote_code_var.set(self._shown_code())
        self._remote_refresh_window()

    def _remote_remove_user(self, uid):
        self.settings["remote_users"] = [u for u in self._remote_users() if str(u.get("id")) != str(uid)]
        core.save_settings(self.settings)
        self._remote_refresh_window()

    def _remote_new_code(self):
        with self.remote_lock:
            self.remote_code = self._new_pair_code()
            self.remote_fails = 0
        self.remote_code_var.set(self._shown_code())

    # ------------------------------------------------------------ what Discord shows

    def _remote_name(self):
        """The open macro's name (read without touching the window: also used from helper threads)."""
        if self.playing and getattr(self, "play_name", ""):
            return self.play_name
        if self.current_file:
            return os.path.splitext(os.path.basename(self.current_file))[0]
        return "" if not (self.events or self.actions) else "Unsaved macro"

    def _remote_state(self):
        if self.recording or self.record_countdown_left > 0:
            return "Recording"
        if self.playing and self.countdown_left > 0:
            return "Starting"
        if self.playing and self.play_paused_at is not None:
            return "Paused"
        return "Playing" if self.playing else "Ready"

    def _remote_presence(self):
        """The bot's status line in Discord's member list."""
        state, name = self._remote_state(), short(self._remote_name(), 40)
        if state in ("Playing", "Paused") and name:
            runs = len(self.session.runs)
            return f"{state}: {name}" + (f" · run {runs + 1}" if state == "Playing" and runs else "")
        if state == "Ready":
            return "Ready" + (f": {name}" if name else "")
        return state

    def _remote_macros(self):
        """The saved macros that can be opened: [(name, path)], each name once."""
        out, seen = [], set()
        for path in list(self.settings.get("macro_library") or []):
            if not isinstance(path, str) or not os.path.isfile(path):
                continue
            name = os.path.splitext(os.path.basename(path))[0][:100]
            if name and name.lower() not in seen:
                seen.add(name.lower())
                out.append((name, path))
        return out

    def _remote_panel(self, note=""):
        """The answer to every command: what the app is doing, with the buttons under it."""
        state = self._remote_state()
        name = self._remote_name()
        busy = self.playing or self.recording or self.record_countdown_left > 0
        lines = []
        if state == "Starting":
            lines.append(f"Starts in {self.countdown_left} s")
        elif state == "Paused" and getattr(self, "away_paused", False):
            lines.append("Paused because the game isn't the window in front")
        if self.playing:
            v = self.session.values("")
            lines.append(f"**Running for** {v['total']}")
            lines.append(f"**Runs done** {v['run']}" + (f" (average {v['average']})" if v["run"] else ""))
            note_now = (self.play_note or "").strip()
            if note_now and state == "Playing":
                lines.append(note_now)
        if self.playing and getattr(self, "auto_stop", None) and not self.auto_stop["cancelled"]:
            lines.append(f"**Stops by itself** {self.auto_stop_summary()} (/keepgoing cancels)")
        if self.playing and self.session.reconnects:
            lines.append(f"**Reconnects** {self.session.reconnects}")
        if self.playing and getattr(self, "chain_step", None):
            lines.append(f"**Chain part** {self.chain_step}")
        if self.session.runs and (self.playing or not busy):
            v = self.session.values("")
            if not self.playing:
                lines.append(f"**Last session** {v['run']} run{'s' if v['run'] != 1 else ''}")
            if self.result_matchers:
                lines.append(f"**Completed** {v['completed']} · **Failed** {v['failed']} · "
                             f"**Unknown** {v['unknown']} · **Win rate** {v['winrate']}")
            if v["fragments_session"]:
                lines.append(f"**Divine fragments** +{v['fragments_session']} this session")
        if not name:
            lines.append("No macro is open. Pick one in the list below." if self._remote_macros()
                         else "No macro is open, and none are saved yet.")
        elif state == "Ready" and not lines:
            lines.append("Ready to start.")
        embed = {"title": f"{name or 'Macro Recorder'} · {state}", "description": "\n".join(lines)[:3900],
                 "color": COLORS.get(state, 0x9B9BA6),
                 "footer": {"text": "Updated " + time.strftime("%H:%M:%S")}}
        paused = state == "Paused"
        can_start = not busy and bool(self.events or self.actions)
        buttons = [
            {"type": 2, "style": 3, "label": "Start", "custom_id": "mr:start", "disabled": not can_start},
            {"type": 2, "style": 1 if paused else 2, "label": "Resume" if paused else "Pause",
             "custom_id": "mr:resume" if paused else "mr:pause",
             "disabled": not self.playing or self.countdown_left > 0},
            {"type": 2, "style": 4, "label": "Stop", "custom_id": "mr:stop", "disabled": not self.playing},
            {"type": 2, "style": 2, "label": "Refresh", "custom_id": "mr:refresh"},
            {"type": 2, "style": 2, "label": "Screenshot", "custom_id": "mr:screenshot"},
        ]
        rows = [{"type": 1, "components": buttons}]
        macros = self._remote_macros()[:25]
        if macros:
            current = name.lower()
            rows.append({"type": 1, "components": [{
                "type": 3, "custom_id": "mr:macro", "placeholder": "Switch to another macro…", "disabled": busy,
                "options": [{"label": n, "value": n, "default": n.lower() == current} for n, _ in macros]}]})
        return {"content": str(note or "")[:1900], "embeds": [embed], "components": rows}

    # ------------------------------------------------------------ the actions (on the window's thread)

    def _remote_act(self, name, arg, who):
        diag.info(f"Phone remote: {name}")
        if name == "start":
            return self._remote_start(who)
        if name == "stop":
            if not self.playing:
                return "Nothing is playing."
            self.stop_playback()
            return "Stopped."
        if name in ("pause", "resume"):
            if not self.playing:
                return "Nothing is playing."
            if self.countdown_left > 0:
                return "It's still counting down."
            if getattr(self, "away_paused", False):
                return "It's paused because the game isn't the window in front. It goes on by itself when it is."
            paused = self.play_paused_at is not None
            if paused == (name == "pause"):
                return "It's already paused." if paused else "It isn't paused."
            self.toggle_pause()
            return "Paused." if name == "pause" else "Going on."
        if name == "macro":
            return self._remote_open(arg)
        if name == "stats":
            return self.remote_stats_text()
        if name == "keepgoing":
            return ("\"Stop by itself\" is cancelled: the macro keeps going until you stop it."
                    if self.cancel_auto_stop() else "Nothing to cancel: no stop is planned for a playing macro.")
        if name == "profile":
            return self.remote_profile(arg)
        if name == "pingme":
            return self.remote_pingme(arg, who)
        return ""

    def _remote_start(self, who):
        if self.playing:
            return "It's already playing."
        if self.recording or self.record_countdown_left > 0 or self.capture_callback is not None:
            return "The app is busy recording right now."
        if not (self.events or self.actions):
            return "No macro is open. Pick one first (`/macro`, or the list under this message)."
        self.boxes.close_all()  # (a box left open on the PC would sit over the game)
        # nobody is at the PC to click the game: put its window in front
        front_note = ""
        exe = (self.macro_program or {}).get("exe") or self.settings.get("last_game_exe")
        if IS_WIN and exe and self.target_var.get() == SCREEN_TARGET:
            wins = window_tools.windows_of(exe)
            game = os.path.splitext(exe)[0]
            if not wins:
                front_note = f" {game} doesn't seem to be open, though."
            elif not window_tools.force_to_front(wins[0]):
                front_note = f" Couldn't put {game} in front, though: check with Screenshot."
        notes = self.boxes.quiet = []
        self._check_program = lambda: True  # (no "Switch to the game?" question)
        try:
            self.play()
        finally:
            self.boxes.quiet = None
            del self._check_program
        if not self.playing:
            return "Couldn't start: " + (notes[0] if notes else "the app refused, look at it on the PC.")
        self.sub_note = "Started from Discord by " + short(str(who), 30)
        ready = self.countdown_left
        return f"Started **{self._remote_name()}**" + (f" (begins in {ready} s)." if ready else ".") + front_note

    def _remote_open(self, wanted):
        if self.playing or self.recording or self.record_countdown_left > 0:
            return "Stop the macro first, then switch."
        wanted = str(wanted or "").strip().lower()
        macros = self._remote_macros()
        match = [m for m in macros if m[0].lower() == wanted] or [m for m in macros if wanted and wanted in m[0].lower()]
        if not match:
            return "No saved macro with that name." if macros else "There are no saved macros yet."
        name, path = match[0]
        if self.current_file and os.path.normcase(os.path.abspath(self.current_file)) == os.path.normcase(
                os.path.abspath(path)):
            return f"**{name}** is already open."
        if self._has_unsaved_macro():
            return "The macro open on the PC isn't saved, so it wasn't replaced. Save it on the PC first."
        self.skip_file_pictures = True
        if not self.load(path, quiet=True):
            self.skip_file_pictures = False
            return f"Couldn't open {name}."
        self.sub_note = "Switched macro from Discord"
        self._refresh()
        return f"Opened **{name}**."

    # ------------------------------------------------------------ commands arriving (helper threads)

    def _remote_on_ui(self, fn, timeout=40.0):
        """Run fn on the window's thread and wait for what it returns (None when it took too long)."""
        box = {}
        done = threading.Event()

        def run():
            try:
                box["result"] = fn()
            except Exception as exc:
                diag.error("A phone remote command failed", exc)
                box["result"] = None
            done.set()
        self._call_ui(run)
        done.wait(timeout)
        return box.get("result")

    def _remote_pair(self, uid, who, code):
        if not uid:
            return "Discord didn't say who you are. Try again."
        if self._remote_allowed(uid):
            return "Your account is already allowed. Try `/status`."
        if not self.remote_pairing:  # (so nobody can keep guessing codes while you're away)
            return ("Pairing is only open while the Phone remote window is open. On the PC, open Settings > "
                    "Discord > Phone remote…, then type `/pair` with the code shown there.")
        typed = "".join(c for c in str(code or "") if c.isdigit())
        with self.remote_lock:
            ok = hmac.compare_digest(typed, self.remote_code)
            if ok:
                self.remote_code = self._new_pair_code()  # (each code works once)
                self.remote_fails = 0
            else:
                self.remote_fails += 1
                if self.remote_fails >= 5:  # no guessing: a new code after five wrong ones
                    self.remote_code = self._new_pair_code()
                    self.remote_fails = 0
        if not ok:
            self._call_ui(lambda: self.remote_code_var.set(self._shown_code()))
            return ("That isn't the code. Look at Settings > Discord > Phone remote… on the PC "
                    "(the code changes after a few wrong tries).")
        diag.info("Phone remote: a Discord account was paired")
        self._call_ui(lambda: self._remote_add_user(uid, who))
        return "Paired. This account can now control the app: try `/status`."

    def _remote_handle(self, it):
        """One command, button press or typed-ahead list from Discord."""
        R = discord_remote
        kind = it.get("type")
        data = it.get("data") or {}
        user = (it.get("member") or {}).get("user") or it.get("user") or {}
        uid = str(user.get("id") or "")
        who = user.get("global_name") or user.get("username") or "someone"
        allowed = self._remote_allowed(uid)
        options = data.get("options") or []
        if kind == 4:  # the list of macro names while typing /macro
            typed = str(next((o.get("value") for o in options if o.get("focused")), "") or "").lower()
            if str(data.get("name") or "") == "profile":
                names = sorted(self.profiles(), key=str.lower) if allowed else []
            else:
                names = [n for n, _ in self._remote_macros()] if allowed else []
            R.respond(it, R.CHOICES, {"choices": [{"name": n, "value": n} for n in names
                                                 if typed in n.lower()][:25]})
            return
        if kind == 2:
            name = str(data.get("name") or "")
            arg = options[0].get("value") if options else None
            if name == "pingme":  # (what to wait for, how many runs, who asked)
                arg = (arg, next((o.get("value") for o in options if o.get("name") == "runs"), None), uid)
        elif kind == 3:
            name = str(data.get("custom_id") or "").partition(":")[2]
            arg = (data.get("values") or [None])[0]
        else:
            return
        button = kind == 3
        if name == "pair":
            R.respond(it, R.REPLY, {"content": self._remote_pair(uid, who, arg), "flags": R.ONLY_YOU})
            return
        if not allowed:
            R.respond(it, R.REPLY, {"content": NOT_PAIRED, "flags": R.ONLY_YOU})
            return
        if name == "screenshot":
            R.respond(it, R.DEFER_REPLY)
            diag.info("Phone remote: screenshot")
            picture = discord_notify.encode(self._screenshot(), size=self.settings.get("discord_shot_size", "sharp"))
            if picture:
                R.edit_reply(it, {"content": "Screenshot at " + time.strftime("%H:%M:%S")}, picture)
            else:
                R.edit_reply(it, {"content": "Couldn't take a screenshot."})
            return
        box = {}
        done = threading.Event()

        def work():
            note = self._remote_on_ui(lambda: self._remote_act(name, arg, who))
            if name == "stop":  # (the macro lets go of its keys first: show the state after that)
                end = time.monotonic() + 1.5
                while self.playing and time.monotonic() < end:
                    time.sleep(0.05)
            box["panel"] = self._remote_on_ui(lambda: self._remote_panel(NO_ANSWER if note is None else note))
            done.set()
        threading.Thread(target=work, daemon=True, name="discord-remote-work").start()
        if done.wait(2.2) and box.get("panel"):
            R.respond(it, R.UPDATE if button else R.REPLY, box["panel"])
            return
        R.respond(it, R.DEFER_UPDATE if button else R.DEFER_REPLY)  # (it takes longer: answer afterwards)
        done.wait(45)
        R.edit_reply(it, box.get("panel") or {"content": NO_ANSWER})

    # ------------------------------------------------------------ the window

    def open_remote_window(self):
        old = self.remote_win
        if old is not None and old.winfo_exists():
            old.deiconify()
            old.lift()
            return
        parent = self.settings_win if self.settings_win is not None and self.settings_win.winfo_viewable() \
            else self.root
        win = self.remote_win = tk.Toplevel(parent, bg=BG)
        self.remote_pairing = True
        # closed in any way (also along with the Settings window): pairing closes too
        win.bind("<Destroy>", lambda e: e.widget is win and self._remote_pairing_closed(), add="+")
        win.title("Phone remote - Macro Recorder")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        if getattr(self, "icon_img", None) is not None:
            win.iconphoto(False, self.icon_img)
        f = tk.Frame(win, bg=BG)
        f.pack(fill="both", expand=True, padx=18, pady=14)

        self._section(f, "PHONE REMOTE (YOUR OWN DISCORD BOT)", first=True)
        tk.Label(f, text="Start, stop, pause and check your macro from Discord on your phone. It needs your own "
                 "small bot (free, about five minutes, once): the steps are at the bottom.", bg=BG, fg=MUTED,
                 font=F_SMALL, anchor="w", justify="left", wraplength=520).pack(fill="x", pady=(0, 6))
        self._switch_row(f, "Control this app from Discord", self.remote_var, command=self._remote_apply)
        row = self._row(f, "Bot token", "paste it here")
        ttk.Button(row, text="Connect", width=9, command=self._remote_apply).pack(side="right")
        entry = tk.Entry(row, textvariable=self.remote_token_var, bg=FIELD, fg=TEXT, font=F_SMALL, relief="flat",
                         insertbackground=TEXT, highlightthickness=1, show="•", highlightbackground=BORDER,
                         highlightcolor=ACCENT, width=34)
        entry.pack(side="right", padx=(0, 6), ipady=3)
        entry.bind("<Return>", lambda e: self._remote_apply())
        self.remote_status_label = tk.Label(f, textvariable=self.remote_status_var, bg=BG, fg=MUTED, font=F_SMALL,
                                            anchor="w", wraplength=520, justify="left")
        self.remote_status_label.pack(fill="x")
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Open Discord's developer page",
                   command=lambda: webbrowser.open(DEVELOPER_PAGE)).pack(side="left")
        self.remote_invite_btn = ttk.Button(row, text="Add the bot to my server…", command=self._remote_invite)
        self.remote_invite_btn.pack(side="left", padx=(6, 0))

        self._section(f, "WHO MAY USE IT")
        row = self._row(f, "Pairing code", "in Discord, type /pair and this code")
        link(row, "New code", self._remote_new_code).pack(side="right")
        tk.Label(row, textvariable=self.remote_code_var, bg=BG, fg=TEXT, font=(FAMILY, 13, "bold")).pack(
            side="right", padx=(0, 12))
        self.remote_users_frame = tk.Frame(f, bg=BG)
        self.remote_users_frame.pack(fill="x", pady=(2, 0))

        self._section(f, "HOW TO SET IT UP")
        tk.Label(f, text=SETUP_STEPS, bg=BG, fg=TEXT, font=F_SMALL, anchor="w", justify="left",
                 wraplength=520).pack(fill="x")
        tk.Label(f, text="Don't share the token: whoever has it can be your bot. It's kept only in this PC's "
                 "settings. Friends who use the app make their own bot the same way.", bg=BG, fg=DIM,
                 font=F_SMALL, anchor="w", justify="left", wraplength=520).pack(fill="x", pady=(8, 0))
        bottom = tk.Frame(f, bg=BG)
        bottom.pack(fill="x", pady=(12, 0))
        ttk.Button(bottom, text="Close", style="Accent.TButton", width=8, command=self._remote_close).pack(
            side="right")
        win.protocol("WM_DELETE_WINDOW", self._remote_close)
        dark_title_bar(win)
        self._remote_refresh_window()

    def _remote_pairing_closed(self):
        """The window is gone: /pair stops working, and the code it showed won't work next time."""
        if self.remote_pairing:
            self.remote_pairing = False
            self._remote_new_code()
        if self.remote_win is not None:
            try:
                if not self.remote_win.winfo_exists():
                    self.remote_win = None
            except tk.TclError:
                self.remote_win = None

    def _remote_close(self):
        win, self.remote_win = self.remote_win, None
        if win is not None and win.winfo_exists():
            s = self.settings
            if (bool(self.remote_var.get()), self.remote_token_var.get().strip()) != (
                    bool(s.get("remote_enabled")), str(s.get("remote_token", ""))):
                self._remote_apply()  # (a token pasted without pressing Connect)
            win.destroy()

    def _remote_invite(self):
        app_id = self.remote_info.get("app_id") or discord_remote.app_id_from_token(self.remote_token_var.get())
        if app_id:
            webbrowser.open(discord_remote.invite_link(app_id))

    def _remote_refresh_window(self):
        win = self.remote_win
        if win is None or not win.winfo_exists():
            return
        ok = getattr(self, "remote_ok", None)
        on = bool(self.settings.get("remote_enabled"))
        self.remote_status_label.config(fg=GREEN if ok and on else (RED if ok is False and on else MUTED))
        has_id = bool(self.remote_info.get("app_id")
                      or discord_remote.app_id_from_token(self.remote_token_var.get()))
        self.remote_invite_btn.config(state="normal" if has_id else "disabled")
        box = self.remote_users_frame
        for child in box.winfo_children():
            child.destroy()
        users = self._remote_users()
        if not users:
            tk.Label(box, text="Nobody yet. The first /pair with the code above adds your account.", bg=BG, fg=DIM,
                     font=F_SMALL, anchor="w").pack(fill="x")
        for u in users:
            row = tk.Frame(box, bg=BG)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=short(str(u.get("name") or "?"), 30), bg=BG, fg=TEXT, font=F_BASE).pack(side="left")
            tk.Label(row, text="ID " + str(u.get("id")), bg=BG, fg=DIM, font=F_SMALL).pack(side="left", padx=(8, 0))
            link(row, "Remove", lambda uid=u.get("id"): self._remote_remove_user(uid)).pack(side="right")
