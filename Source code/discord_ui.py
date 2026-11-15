"""Settings > Discord: the run cards, the summary when playback stops, the test message and the
message editor window.

Part of the dark window: ModernMacroRecorder (modern_ui.py) inherits this class.
"""

import time

from ui_common import *  # noqa: F401,F403  (colours, fonts, widgets, tk, core, the other modules)


class DiscordMixin:
    DISCORD_HELP = (
        "Get messages in your own Discord channel while a macro runs, for example on your phone while "
        "you're away.\n\n"
        "1. In Discord, open the settings of a channel on your own server (the gear next to its name).\n"
        "2. Integrations > Webhooks > New Webhook, then Copy Webhook URL.\n"
        "3. Paste it in the box here and press Send a test message.\n\n"
        "No bot and no account is needed. The link works like a password for that channel: anyone "
        "who has it can post there, so don't share it. The screenshot shows your whole main screen.")

    def _build_discord_tab(self, f):
        self._section(f, "DISCORD MESSAGES", first=True)
        self._switch_row(f, "Send messages to my Discord channel", self.discord_var, info=self.DISCORD_HELP)
        row = self._row(f, "Webhook link", "paste it here")
        self.discord_entry = tk.Entry(row, textvariable=self.discord_url_var, bg=FIELD, fg=TEXT, font=F_SMALL,
                                      relief="flat", insertbackground=TEXT, highlightthickness=1, show="•",
                                      highlightbackground=BORDER, highlightcolor=ACCENT, width=34)
        self.discord_entry.pack(side="right", ipady=3)
        self.discord_entry.bind("<FocusOut>", lambda e: self._save_settings(), add="+")
        row = self._row(f, "Name it posts as")
        self._entry(row, self.discord_name_var, 22).pack(side="right", ipady=2)
        row = self._row(f, "Ping", info=self.PING_HELP)
        box = ttk.Combobox(row, width=22, state="readonly", textvariable=self.discord_ping_when_var,
                           values=list(PING_WHEN.values()))
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda e: (box.selection_clear(), self._save_settings()))
        self._entry(row, self.discord_ping_var, 16).pack(side="right", padx=(0, 6), ipady=2)
        self._switch_row(f, "Ping when a divine fragment drops", self.discord_ping_drop_var,
                         "also when Ping says Never", info=self.PING_DROP_HELP)
        self._section(f, "WHEN")
        self._switch_row(f, "After each run", self.discord_runs_var, "a card with the run's results")
        self._switch_row(f, "When playback stops", self.discord_stop_var, "finished, stopped or a problem")
        self._switch_row(f, "With a screenshot", self.discord_shot_var)
        self._choice_row(f, "One card that updates", self.live_summary, self.toggle_live_card,
                         tip="instead of a new card each run (no screenshot)")
        self._choice_row(f, "Daily or weekly summary", self.summary_summary, self.open_summary_options)
        row = self._row(f, "Screenshot of")
        self.discord_program_box = ttk.Combobox(row, width=20, textvariable=self.discord_program_var,
                                                postcommand=self._list_programs)
        self.discord_program_box.pack(side="right")
        self.discord_program_box.bind("<<ComboboxSelected>>", lambda e: self._capture_changed())
        self.discord_program_box.bind("<FocusOut>", lambda e: self._capture_changed())
        box = ttk.Combobox(row, width=17, state="readonly", textvariable=self.discord_capture_var,
                           values=list(CAPTURE_CHOICES.values()))
        box.pack(side="right", padx=(0, 6))
        box.bind("<<ComboboxSelected>>", lambda e: (box.selection_clear(), self._capture_changed()))
        self._capture_changed(save=False)
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", pady=(10, 4))
        ttk.Button(row, text="Edit the message…", command=self.edit_discord_message).pack(side="left")
        ttk.Button(row, text="Send a test message", command=self._discord_test).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Phone remote…", command=self.open_remote_window).pack(side="right")
        tk.Label(f, textvariable=self.discord_status_var, bg=BG, fg=MUTED, font=F_SMALL, anchor="w",
                 wraplength=460, justify="left").pack(fill="x")
        tk.Label(f, text="Don't share the link: anyone who has it can post in that channel.",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x", pady=(4, 0))

    PING_HELP = (
        "Who gets pinged, put where {ping} is in the message (at its top, at first).\n\n"
        "Type @everyone or @here, or a person as <@their user ID> (like <@123456789012345678>), or a role "
        "as <@&role ID>. To get an ID: Discord > Settings > Advanced > Developer Mode on, then right-click "
        "the person or role > Copy ID. Several are fine, separated by spaces.\n\n"
        "Every message: each run and each stop. Only failed runs and stops: when a run is lost or the "
        "macro stops. Never: no ping.")

    PING_DROP_HELP = (
        "After a run where divine fragments were counted (Settings > Results > Count divine fragments), "
        "its card is sent with the ping, whatever the Ping box says about when to ping.\n\n"
        "The card is sent even if \"After each run\" is off.")

    def _entry(self, parent, var, width):
        e = tk.Entry(parent, textvariable=var, bg=FIELD, fg=TEXT, font=F_SMALL, relief="flat", width=width,
                     insertbackground=TEXT, highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT)
        e.bind("<FocusOut>", lambda ev: self._save_settings(), add="+")
        return e

    def _list_programs(self):
        """Programs with a window open right now, for "A program's window"."""
        names = []
        if background is not None:
            for hwnd, _title in background.list_windows():
                exe = window_tools.exe_of(hwnd)
                if exe and exe not in names and window_tools.pid_of(hwnd) != os.getpid():
                    names.append(exe)
        self.discord_program_box.config(values=sorted(names, key=str.lower))

    def _capture_setting(self):
        choice = next((k for k, v in CAPTURE_CHOICES.items() if v == self.discord_capture_var.get()), "screen")
        if choice == "program":
            exe = self.discord_program_var.get().strip()
            return "program:" + exe if exe else "screen"
        return choice

    def _capture_changed(self, save=True):
        program = self.discord_capture_var.get() == CAPTURE_CHOICES["program"]
        if program:
            self.discord_program_box.pack(side="right")
        else:
            self.discord_program_box.pack_forget()
        if save:
            self._save_settings()
            if getattr(self, "settings_backdrop", None) is not None:
                self.root.after_idle(self.settings_backdrop.refresh)

    def _screenshot(self):
        """The screenshot for Discord, taken right now as chosen in Settings > Discord (a picture; the
        sending thread packs it as JPG, so the macro isn't held up). This app's own windows (the main
        window, the timer at the top, the video) are left out of it, so it shows only the game."""
        target = self.settings.get("discord_capture", "screen")
        exe = ((self.macro_program or {}).get("exe") or getattr(self, "play_game_exe", None)
               or self.settings.get("last_game_exe"))
        # (only our windows that are in the picture: none there, no wait)
        hidden = window_tools.hide_own_windows_from_capture(True, discord_notify.grab_area(target, exe))
        try:
            if hidden:
                time.sleep(0.06)  # (Windows needs a moment to take them out of the picture)
            return discord_notify.grab(target, exe)
        finally:
            if hidden:
                window_tools.hide_own_windows_from_capture(False)

    def _ping_for(self, problem, dropped=False):
        s = self.settings
        when = s.get("discord_ping_when", "problems")
        if when == "always" or (when == "problems" and problem) or (dropped and s.get("discord_ping_fragments")):
            return str(s.get("discord_ping", "")).strip()
        return ""

    def _run_card(self, status, values):
        s = self.settings
        title = stats.fill(s.get("discord_title") or stats.DEFAULT_TITLE, values)
        text = stats.fill(s.get("discord_message") or stats.DEFAULT_MESSAGE, values)
        content = stats.fill(s.get("discord_content", stats.DEFAULT_CONTENT), values).strip()
        return content, {"title": title, "description": text, "color": RESULT_COLORS.get(status)}

    def _send_card(self, content, card, png, live=None):
        if self.settings.get("discord_enabled"):
            more = {"live": live} if live else {}
            self.notifier.send(content, png=png, embed=card,
                               username=str(self.settings.get("discord_name") or "Macro Recorder"), **more)

    def _run_finished(self, count, how):
        """After each run (on the playback thread): the run's results to Discord."""
        s = self.settings
        dropped = bool(self.session.fragments and self.session.fragments[-1] > 0)
        if not (s.get("discord_enabled") and (s.get("discord_runs", True)
                                              or (dropped and s.get("discord_ping_fragments")))):
            return
        status = self.session.runs[-1][0] if self.session.runs else stats.UNKNOWN
        values = self.session.values(self._ping_for(status == stats.LOSS, dropped))
        content, card = self._run_card(status, values)
        # an unknown result or a divine fragment: always a message of its own with a screenshot, so it
        # can be looked at afterwards (only won and failed runs go into the card that updates)
        keep = status == stats.UNKNOWN or dropped
        if s.get("discord_live") and not content.strip() and not keep:
            # "One card that updates": the same message is changed after each run (a run that pings
            # still gets a message of its own, or the ping wouldn't reach anyone)
            card = dict(card, description=card.get("description", "") + "\n*Updated " + time.strftime("%H:%M:%S")
                        + "*")
            self._send_card("", card, None, live=f"runs:{self.session.started}")
            return
        # taken now, before the macro goes on (clicks Retry, starts over)
        png = self._screenshot() if (s.get("discord_screenshot", True) or keep) else None
        self._send_card(content, card, png)

    def _discord_summary(self, text, problem=False):
        """When playback stops: how it ended, with the session's results."""
        s = self.settings
        if not s.get("discord_enabled"):
            return
        values = self.session.values(self._ping_for(problem))
        lines = [text]
        if self.session.runs and self.result_matchers:
            lines.append(f"Completed {values['completed']} · Failed {values['failed']} · "
                         f"Unknown {values['unknown']} · Win rate {values['winrate']}")
        lines.append(f"Total runtime {values['total']}")
        card = {"title": f"{values['macro']} · {'Problem' if problem else 'Session ended'}",
                "description": "\n".join(lines), "color": 0xFF4757 if problem else 0x4F7CFF}
        png = self._screenshot() if problem and s.get("discord_screenshot", True) else None
        self._send_card(values["ping"], card, png)

    def _discord_recovery(self, kind, text):
        """A disconnect screen showed ("lost") or the rejoin macro got the game back ("back").
        (When it couldn't, playback stops and the usual "Problem" message says why.)"""
        s = self.settings
        if not s.get("discord_enabled") or kind not in ("lost", "back"):
            return
        values = self.session.values(self._ping_for(kind == "lost"))
        card = {"title": f"{values['macro']} · {'Disconnected' if kind == 'lost' else 'Back in the game'}",
                "description": text + "\nReconnects this session: " + str(self.session.reconnects),
                "color": 0xFFB238 if kind == "lost" else 0x2ECC71}
        png = self._screenshot() if kind == "lost" and s.get("discord_screenshot", True) else None
        self._send_card(values["ping"], card, png)

    def _discord_test(self):
        self._save_settings()
        url = self.discord_url_var.get().strip()
        if not discord_notify.is_webhook(url):
            self.discord_status_var.set("That isn't a Discord webhook link (it starts with "
                                        "https://discord.com/api/webhooks/).")
            return
        self.discord_status_var.set("Sending…")
        sample = stats.Session(self.name_var.get().strip() or "Test macro")
        sample.started -= 600
        for st, secs in ((stats.WIN, 118), (stats.WIN, 121), (stats.LOSS, 95), (stats.WIN, 117)):
            sample.add(st, secs)
        content, card = self._run_card(stats.WIN, sample.values(self._ping_for(True)))
        card["title"] = "Test · " + card["title"]
        shot = self.discord_shot_var.get()
        name = str(self.settings.get("discord_name") or "Macro Recorder")

        def work():
            discord_notify.post(url, content, discord_notify.encode(self._screenshot()) if shot else None,
                                embed=card, username=name)

        def done(_r, error):
            self.discord_status_var.set(str(error) if error else "Sent. Check your Discord channel.")
        self._in_background(work, done)

    def edit_discord_message(self):
        """The Discord message editor, in its own window (resizable; it remembers its size): the line
        above the card, the card's title and text, letter styles and Discord's own formatting, the
        {placeholders}, and a preview filled with example results."""
        s = self.settings
        old = getattr(self, "discord_editor", None)
        if old is not None and old.winfo_exists():
            old.deiconify()
            old.lift()
            return
        win = self.discord_editor = tk.Toplevel(self.root, bg=BG)
        win.title("Discord message - Macro Recorder")
        win.attributes("-topmost", True)
        win.minsize(680, 440)
        geo = s.get("discord_editor_geometry")
        win.geometry(geo if isinstance(geo, str) and geo[:1].isdigit() else "980x660")
        if getattr(self, "icon_img", None) is not None:
            win.iconphoto(False, self.icon_img)

        top = tk.Frame(win, bg=BG)
        top.pack(fill="x", padx=16, pady=(12, 0))

        def field(label, value, row):
            tk.Label(top, text=label, bg=BG, fg=MUTED, font=F_SECTION, anchor="w").grid(row=row, column=0,
                                                                                       sticky="w", pady=3)
            var = tk.StringVar(value=value)
            e = tk.Entry(top, textvariable=var, bg=FIELD, fg=TEXT, font=F_BASE, relief="flat", insertbackground=TEXT,
                         highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT)
            e.grid(row=row, column=1, sticky="ew", padx=(10, 0), ipady=3, pady=3)
            return var, e
        top.columnconfigure(1, weight=1)
        content_var, content_entry = field("ABOVE THE CARD", s.get("discord_content", stats.DEFAULT_CONTENT), 0)
        title_var, title_entry = field("CARD TITLE", s.get("discord_title") or stats.DEFAULT_TITLE, 1)
        tk.Label(top, text="Pings only work above the card. Put {ping} there (the Ping box in Settings says who).",
                 bg=BG, fg=DIM, font=F_SMALL, anchor="w").grid(row=2, column=1, sticky="w", padx=(10, 0))

        # toolbar: Discord's formatting and letter styles
        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=16, pady=(10, 4))
        main = tk.Frame(win, bg=BG)
        main.pack(fill="both", expand=True, padx=16)
        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        side = tk.Frame(main, bg=BG, width=300)
        side.pack(side="left", fill="y", padx=(14, 0))
        side.pack_propagate(False)
        # the placeholders, as clickable words under the text (each one is put in where the cursor is)
        chips_row = tk.Frame(left, bg=BG)
        chips_row.pack(side="bottom", fill="x", pady=(6, 0))
        head = tk.Frame(chips_row, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="PLACEHOLDERS (click one to put it in)", bg=BG, fg=MUTED, font=F_SECTION,
                 anchor="w").pack(side="left")
        meanings = "\n".join(f"{k}   {what}" for k, what in stats.PLACEHOLDERS)
        link(head, "ⓘ", lambda: self.boxes.showinfo("Placeholders", "Each one is replaced by its value when "
                                                  "the message is sent:\n\n" + meanings, parent=win),
             fg=MUTED, font=(FAMILY, 10)).pack(side="left", padx=(5, 0))
        chips = tk.Text(chips_row, bg=BG, fg=TEXT, relief="flat", font=(FAMILY, 9, "bold"), wrap="word",
                        height=3, highlightthickness=0, cursor="hand2", padx=0, pady=2)
        chips.pack(fill="x")
        for key, what in stats.PLACEHOLDERS:
            tag = "ph_" + key.strip("{}")
            chips.insert("end", key, (tag,))
            chips.insert("end", "    ")
            chips.tag_configure(tag, foreground=TEXT)
            chips.tag_bind(tag, "<Button-1>", lambda e, key=key: insert_placeholder(key))
            chips.tag_bind(tag, "<Enter>", lambda e, tag=tag: chips.tag_configure(tag, foreground=ACCENT))
            chips.tag_bind(tag, "<Leave>", lambda e, tag=tag: chips.tag_configure(tag, foreground=TEXT))
        chips.config(state="disabled")
        text = tk.Text(left, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", font=(FAMILY, 10),
                       highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT, wrap="word",
                       undo=True, padx=8, pady=6, selectbackground=ACCENT)
        scroll = ttk.Scrollbar(left, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.insert("1.0", s.get("discord_message") or stats.DEFAULT_MESSAGE)
        state = {"last": text}  # the box the toolbar works on (the text, or the title / top line)
        for w in (text, content_entry, title_entry):
            w.bind("<FocusIn>", lambda e, w=w: state.update(last=w), add="+")

        def selection(w):
            """(start, end, selected text) in the box, or None when nothing is selected."""
            try:
                if isinstance(w, tk.Text):
                    return w.index("sel.first"), w.index("sel.last"), w.get("sel.first", "sel.last")
                if w.selection_present():
                    a, b = w.index("sel.first"), w.index("sel.last")
                    return a, b, w.get()[a:b]
            except tk.TclError:
                pass
            return None

        def replace_selection(w, new):
            sel = selection(w)
            if sel is None:
                return False
            a, b, _old = sel
            if isinstance(w, tk.Text):
                w.edit_separator()
                w.delete(a, b)
                w.insert(a, new)
                w.tag_add("sel", a, f"{a}+{len(new)}c")
            else:
                w.delete(a, b)
                w.insert(a, new)
                w.select_range(a, a + len(new))
            return True

        def need_selection():
            hint.set("Select some text first, then pick the style.")

        def mark(name):
            w = state["last"]
            before, after = text_styles.MARKS[name]
            sel = selection(w)
            if sel is None:
                need_selection()
                return
            old = sel[2]
            if old.startswith(before) and old.endswith(after) and len(old) >= len(before) + len(after):
                new = old[len(before):len(old) - len(after)]  # pressing it again takes the marks off
            else:
                new = before + old + after
            replace_selection(w, new)
            changed()

        def heading():
            w = state["last"]
            if not isinstance(w, tk.Text):
                return
            line = w.index("insert linestart")
            if w.get(line, f"{line}+2c") == "# ":
                w.delete(line, f"{line}+2c")
            else:
                w.insert(line, "# ")
            changed()

        def letter_style(_e=None):
            name = style_var.get()
            style_box.selection_clear()
            w = state["last"]
            sel = selection(w)
            if sel is None:
                need_selection()
                return
            replace_selection(w, text_styles.apply(name, sel[2]))
            changed()

        for label, cmd in (("B", lambda: mark("Bold")), ("I", lambda: mark("Italic")),
                           ("U", lambda: mark("Underline")), ("S", lambda: mark("Strike")),
                           ("H", heading), ("</>", lambda: mark("Code")), ("Spoiler", lambda: mark("Spoiler"))):
            font = {"B": (FAMILY, 10, "bold"), "I": (FAMILY, 10, "italic"), "U": (FAMILY, 10, "underline"),
                    "S": (FAMILY, 10, "overstrike")}.get(label, (FAMILY, 10))
            b = tk.Label(bar, text=label, bg=CARD, fg=TEXT, font=font, padx=9, pady=3, cursor="hand2")
            b.pack(side="left", padx=(0, 4))
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, b=b: b.config(bg=CARD_HOVER))
            b.bind("<Leave>", lambda e, b=b: b.config(bg=CARD))
        tk.Label(bar, text="   Letters", bg=BG, fg=MUTED, font=F_SMALL).pack(side="left")
        style_var = tk.StringVar(value="Normal")
        style_box = ttk.Combobox(bar, width=16, state="readonly", textvariable=style_var,
                                 values=list(text_styles.STYLES), font=(FAMILY, 10))
        style_box.pack(side="left", padx=(6, 0))
        style_box.bind("<<ComboboxSelected>>", letter_style)
        hint = tk.StringVar(value="Select text, then press a button or pick Letters. {placeholders} stay working.")
        tk.Label(bar, textvariable=hint, bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(side="left", padx=(12, 0))

        # right side: preview with example results, and the placeholders (click one to put it in)
        tk.Label(side, text="PREVIEW (example results)", bg=BG, fg=MUTED, font=F_SECTION, anchor="w").pack(fill="x")
        card = tk.Frame(side, bg="#2b2d31")
        card.pack(fill="both", expand=True, pady=(4, 8))
        tk.Frame(card, bg=GREEN, width=4).pack(side="left", fill="y")
        preview = tk.Text(card, bg="#2b2d31", fg="#dbdee1", relief="flat", font=(FAMILY, 9), wrap="word",
                          padx=10, pady=8, highlightthickness=0, cursor="arrow", height=12)
        preview.pack(side="left", fill="both", expand=True)
        for tag, font in (("bold", (FAMILY, 9, "bold")), ("italic", (FAMILY, 9, "italic")),
                          ("underline", (FAMILY, 9, "underline")), ("strike", (FAMILY, 9, "overstrike")),
                          ("code", ("Consolas", 9)), ("h1", (FAMILY, 13, "bold")), ("h2", (FAMILY, 11, "bold")),
                          ("h3", (FAMILY, 10, "bold")), ("title", (FAMILY, 10, "bold"))):
            preview.tag_configure(tag, font=font)
        preview.tag_configure("code", background="#1e1f22")
        preview.tag_configure("spoiler", background="#1e1f22", foreground="#1e1f22")

        def insert_placeholder(key):
            w = state["last"]
            w.insert("insert", key)
            w.focus_set()
            changed()

        sample = stats.Session(self.name_var.get().strip() or "OUTSKIRTS")
        sample.started -= 3 * 3600
        for st, secs in [(stats.WIN, 117)] * 9 + [(stats.LOSS, 95), (stats.UNKNOWN, 140)] + [(stats.WIN, 117)] * 9:
            sample.add(st, secs)

        def render():
            state["job"] = None
            values = sample.values(str(self.settings.get("discord_ping", "")).strip() or "@you")
            preview.config(state="normal")
            preview.delete("1.0", "end")
            top_line = stats.fill(content_var.get(), values).strip()
            if top_line:
                preview.insert("end", top_line + "\n\n")
            preview.insert("end", stats.fill(title_var.get(), values) + "\n", ("title",))
            for piece, looks in text_styles.preview_spans(stats.fill(text.get("1.0", "end-1c"), values)):
                preview.insert("end", piece, tuple(looks))
            preview.config(state="disabled")

        def changed(_e=None):
            if state.get("job") is not None:
                win.after_cancel(state["job"])
            state["job"] = win.after(200, render)
        text.bind("<KeyRelease>", changed, add="+")
        for var in (content_var, title_var):
            var.trace_add("write", lambda *a: changed())

        # pasting text from somewhere else: keep its special letters, or make it plain?
        def paste(event):
            w = event.widget
            try:
                clip = w.clipboard_get()
            except tk.TclError:
                return "break"
            if text_styles.is_styled(clip):
                answer = self.boxes.askchoice(
                    "Paste", "The text you're pasting has special letters (a fancy font or style).\n\n"
                    "Paste it as it is, or as plain text in the normal font?",
                    [("As it is", "keep"), ("Plain text", "plain"), ("Cancel", None)], default="keep", parent=win)
                if answer is None:
                    return "break"
                if answer == "plain":
                    clip = text_styles.to_plain(clip)
            try:
                if isinstance(w, tk.Text):
                    if w.tag_ranges("sel"):
                        w.delete("sel.first", "sel.last")
                elif w.selection_present():
                    w.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
            w.insert("insert", clip)
            changed()
            return "break"
        for w in (text, content_entry, title_entry):
            w.bind("<<Paste>>", paste)

        def default():
            content_var.set(stats.DEFAULT_CONTENT)
            title_var.set(stats.DEFAULT_TITLE)
            text.delete("1.0", "end")
            text.insert("1.0", stats.DEFAULT_MESSAGE)
            changed()

        def remember_size():
            try:
                s["discord_editor_geometry"] = win.geometry()
            except tk.TclError:
                pass

        def save():
            s["discord_content"] = content_var.get()
            s["discord_title"] = title_var.get().strip() or stats.DEFAULT_TITLE
            s["discord_message"] = text.get("1.0", "end").rstrip() or stats.DEFAULT_MESSAGE
            remember_size()
            self._save_settings()
            win.destroy()

        def close():
            remember_size()
            core.save_settings(s)
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", close)
        bottom = tk.Frame(win, bg=BG)
        bottom.pack(side="bottom", fill="x", padx=16, pady=12, before=main)  # (always shown, even when small)
        link(bottom, "Back to the default text", default).pack(side="left")
        ttk.Button(bottom, text="Save", style="Accent.TButton", width=8, command=save).pack(side="right")
        ttk.Button(bottom, text="Cancel", width=8, command=close).pack(side="right", padx=6)
        dark_title_bar(win)
        render()
        text.focus_set()
