"""The dark Macro Recorder window (started from macro_recorder.py).

It reuses everything from macro_recorder.py (recording, playback, hotkeys, speed, countdown,
picture watch, screen size scaling, imports) and only changes the window around it. The window is
made of parts, each in its own file:

  ui_common.py        colours, fonts, the dark theme, small widgets, dark message boxes
  settings_pages.py   the Settings window and its pages (General, Recording, Playback, Background,
                      Sounds)
  discord_ui.py       Settings > Discord, the run cards and the message editor
  results_ui.py       Settings > Results (won / lost pictures and the results)
  settings_window.py  About, opening / closing Settings, Undo / Reset / Apply, shortcut keys
  edit_window.py      the Edit window
  video_ui.py         the video window over the game and its keys
  modern_ui.py        (this file) the main window, playback, files, saved macros, and main()
"""

from ui_common import *  # noqa: F401,F403
from automation_ui import AutomationMixin
from check_ui import CheckMixin
from record_window_ui import RecordWindowMixin
from stuck_ui import StuckMixin
from milestones_ui import MilestonesMixin
from macro_folders import MacroFoldersMixin
from keys_overlay import KeysOverlayMixin
from tour_ui import TourMixin
from timed_start_ui import TimedStartMixin
import timed_start_ui
import step_more
import themes
import macro_versions
from discord_ui import DiscordMixin
from extras_ui import ExtrasMixin
from edit_window import EditWindowMixin
from macro_editor import MacroEditorMixin
from picture_actions_ui import PictureActionsMixin
from picture_window import PictureWatchMixin
from profiles_ui import ProfilesMixin
from remote_ui import RemoteMixin
from results_ui import ResultsMixin
from settings_pages import SettingsPagesMixin
from settings_window import SettingsWindowMixin
from video_ui import VideoMixin


class ModernMacroRecorder(TourMixin, KeysOverlayMixin, MacroFoldersMixin, MilestonesMixin, TimedStartMixin, CheckMixin, RecordWindowMixin, StuckMixin, ExtrasMixin, ProfilesMixin, PictureWatchMixin, SettingsPagesMixin, PictureActionsMixin, AutomationMixin, DiscordMixin, RemoteMixin, ResultsMixin, SettingsWindowMixin, MacroEditorMixin, EditWindowMixin, VideoMixin, core.MacroRecorder):
    def __init__(self, root, preview=False):
        self.preview = preview
        self.sub_note = "Record something, or open a macro"
        self.settings_win = None
        self.edit_win = None
        self.unsaved = False  # the open macro was edited and not saved since
        self.boxes = ThemedBoxes(self)
        messagebox.use(self.boxes)  # every part of the window now shows the dark message boxes
        core.messagebox = self.boxes
        super().__init__(root)
        self._init_remote()  # the phone remote (Settings > Discord > Phone remote), if it's on

    # ------------------------------------------------------------ main window

    def _build_ui(self):
        root = self.root
        s = self.settings
        root.title("Macro Recorder (preview)" if self.preview else "Macro Recorder")
        root.resizable(True, True)  # (Preview 4: drag the corner; scroll bars when it's smaller)
        root.attributes("-topmost", bool(s.get("always_on_top", True)))
        themes.set_globals(s.get("accent", "Blue"))  # (Preview 4: the chosen accent colour, before anything is made)
        apply_theme(root)
        self.window_stack = WindowStack(root)  # (a window opened from another stays in front of it)
        # ready-made sizes of the icon and logo (read by Tk directly next time: a quicker start)
        icon_picture.CACHE_DIR = os.path.join(os.path.dirname(core.settings_path()), "icon_cache")
        self.logo_same_var = tk.BooleanVar(value=bool(s.get("app_logo_same", False)))
        self.icon_img = None
        self._apply_app_icon()
        dark_title_bar(root)

        # settings that the old window kept on its main screen (used by playback)
        self.repeat_var = tk.IntVar(value=core.int_setting(s, "repeat_count", 1, 1, 9999))
        self.loop_var = tk.BooleanVar(value=bool(s.get("loop", True)))
        self.speed_var = tk.StringVar(value=format_speed(parse_speed(s.get("speed", 1)) or 1.0))
        self.ready_var = tk.IntVar(value=core.int_setting(s, "ready_seconds", 3, 0, 600))
        self.rec_ready_var = tk.IntVar(value=core.int_setting(s, "record_ready_seconds", 5, 0, 600))
        self.rec_ask_window_var = tk.BooleanVar(value=s.get("record_ask_window", True) is not False)
        self.target_windows = []
        self.target_var = tk.StringVar(value=SCREEN_TARGET)
        self.name_var = tk.StringVar(value="")  # empty until a macro is opened or saved
        self.old_macro_var = tk.StringVar(value="")  # the yellow note for macros recorded before 2.6
        self.sounds_var = tk.BooleanVar(value=bool(s.get("sounds", True)))
        # (these are made the first time they're used, so their parts aren't loaded at start)
        self.player = lazy.LazyObject(lambda: sounds.Player(), idle={"stop": lambda *a, **k: None})
        self.last_sound = 0.0
        root.bind_all("<Button-1>", self._click_sound, add="+")
        self.volume_var = tk.IntVar(value=sounds.volume_number(s.get("sound_volume", sounds.DEFAULT_VOLUME)))
        self.statusbar_var = tk.BooleanVar(value=bool(s.get("status_bar", True)))
        self.ontop_var = tk.BooleanVar(value=bool(s.get("always_on_top", True)))
        self.overlay_var = tk.BooleanVar(value=bool(s.get("play_overlay", True)))
        self.update_check_var = tk.BooleanVar(value=bool(s.get("check_updates", True)))
        self.update_status_var = tk.StringVar(value="")
        # the status text sits on the Settings picture: give it its piece again whenever it changes
        self.update_status_var.trace_add("write", lambda *a: self.root.after_idle(self._settings_text_changed))
        self.update_busy = False
        self.overlay = None
        self.overlay_job = None
        self.play_began = None
        self.play_paused_at = None  # when playback was paused (None = not paused)
        self.play_pause_total = 0.0
        self.held_now = None  # the keys and buttons the macro is holding down right now
        self.rec_moves_var = tk.BooleanVar(value=bool(s.get("record_mouse_moves", True)))
        self.detail_var = tk.StringVar(value=s.get("mouse_detail", "Smooth")
                                       if s.get("mouse_detail") in MOUSE_DETAIL else "Smooth")
        self.camera_var = tk.BooleanVar(value=bool(s.get("record_camera", False)))
        self.simplify_var = tk.BooleanVar(value=bool(s.get("simplify_moves", False)))
        # playing: pause when the game leaves the front, offer to switch to it, fit to its window
        self.away_var = tk.BooleanVar(value=bool(s.get("pause_when_away", True)))
        self.away_stop_var = tk.IntVar(value=core.int_setting(s, "away_stop_seconds", 0, 0, 3600))
        self.recover_count_var = tk.IntVar(value=core.int_setting(s, "recovery_countdown", 5, 0, 60))
        self.switch_prog_var = tk.BooleanVar(value=bool(s.get("switch_to_program", True)))
        self.fit_var = tk.StringVar(value=FIT_TO.get(s.get("fit_to"), FIT_TO["window"]))
        # messages to your own Discord channel (a webhook link)
        self.discord_var = tk.BooleanVar(value=bool(s.get("discord_enabled", False)))
        self.discord_url_var = tk.StringVar(value=str(s.get("discord_webhook", "")))
        self.discord_runs_var = tk.BooleanVar(value=bool(s.get("discord_runs", True)))
        self.discord_ping_drop_var = tk.BooleanVar(value=bool(s.get("discord_ping_fragments", False)))
        self.discord_shot_var = tk.BooleanVar(value=bool(s.get("discord_screenshot", True)))
        self.discord_size_var = tk.StringVar(value=SHOT_SIZE.get(s.get("discord_shot_size"), SHOT_SIZE["sharp"]))
        self.discord_stop_var = tk.BooleanVar(value=bool(s.get("discord_stops", True)))
        self.discord_name_var = tk.StringVar(value=str(s.get("discord_name", "Macro Recorder")))
        self.discord_ping_var = tk.StringVar(value=str(s.get("discord_ping", "")))
        self.discord_ping_when_var = tk.StringVar(value=PING_WHEN.get(s.get("discord_ping_when"),
                                                                      PING_WHEN["problems"]))
        cap = str(s.get("discord_capture", "screen"))
        self.discord_capture_var = tk.StringVar(
            value=CAPTURE_CHOICES["program"] if cap.startswith("program:") else CAPTURE_CHOICES.get(cap, "Main screen"))
        self.discord_program_var = tk.StringVar(value=cap[8:] if cap.startswith("program:") else "")
        # mission results (wins and losses)
        self.results_var = tk.BooleanVar(value=bool(s.get("results_enabled", True)))
        self.drops_var = tk.BooleanVar(value=bool(s.get("drops_enabled", True)))
        if s.get("discord_message") in stats.OLD_DEFAULT_MESSAGES:
            s["discord_message"] = stats.DEFAULT_MESSAGE  # (the default text, now with divine fragments)
        self.results_match_var = tk.IntVar(value=core.int_setting(s, "results_match", core.RESULTS_MATCH_DEFAULT, 50, 99))
        self.session_var = tk.StringVar(value="Nothing played yet.")
        self.alltime_var = tk.StringVar(value="")
        self.discord_status_var = tk.StringVar(value="")
        self.discord_status_var.trace_add("write", lambda *a: self.root.after_idle(self._settings_text_changed))
        # (reads the saved settings, not the boxes: it's also used from the playback thread)
        self.notifier = lazy.LazyObject(lambda: discord_notify.Notifier(
            lambda: str(self.settings.get("discord_webhook", "")) if self.settings.get("discord_enabled") else "",
            on_result=lambda ok, text: self._call_ui(lambda: self.discord_status_var.set(text)),
            shot_size=lambda: self.settings.get("discord_shot_size", "sharp")))
        # the YouTube video window over the game
        self.video_var = tk.StringVar(value=str(s.get("video_link", "")))
        self.video_through_var = tk.StringVar(
            value=s.get("video_click_through") if s.get("video_click_through") in VIDEO_THROUGH
            else VIDEO_THROUGH[0])
        self.video_opacity_var = tk.IntVar(value=core.int_setting(s, "video_opacity", 100, 20, 100))
        def setup_video_window(win):
            dark_title_bar(win)
            if getattr(self, "icon_img", None) is not None:
                win.iconphoto(False, self.icon_img)
        video_dir = os.path.join(os.path.dirname(core.settings_path()), "video_browser")
        self.video = lazy.LazyObject(
            lambda: video_overlay.make_overlay(video_dir, root=root, on_closed=lambda: self._video_closed(),
                                               setup_window=setup_video_window),
            idle={"is_open": lambda: False, "close": lambda *a, **k: None, "rect": None, "click_through": False,
                  "error": ""})
        r = s.get("video_rect")
        if isinstance(r, list) and len(r) == 4 and all(isinstance(v, int) for v in r):
            self.video.rect = tuple(r)
        self.video.opacity = self.video_opacity_var.get()
        self.video_job = None

        # (Preview 4) everything sits in a scroll area: the window keeps its size by itself, can be made
        # bigger or smaller by dragging its corner, and gets scroll bars when it's smaller than its parts
        self.main_scroll = ScrollArea(root, BG, natural=True, on_scroll=lambda: self._scrolled(self.backdrop))
        self.main_scroll.pack(fill="both", expand=True)
        wheel_scrolls(root, lambda: self.main_scroll)
        outer = self.main_scroll.inner

        # header: name of the app + settings
        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x", padx=18, pady=(14, 10))
        mark = self.logo_canvas = tk.Canvas(head, width=30, height=30, bg=BG, highlightthickness=0)
        self._draw_logo()
        mark.pack(side="left")
        tk.Label(head, text="Macro Recorder", bg=BG, fg=TEXT, font=F_TITLE).pack(side="left", padx=(10, 0))
        if self.preview:
            tk.Label(head, text="PREVIEW", bg=AMBER, fg="#111", font=(FAMILY, 7, "bold"),
                     padx=4).pack(side="left", padx=(8, 0), pady=(4, 0))
        gear = self.gear_link = link(head, "⚙  Settings", self.open_settings, fg=MUTED, font=(FAMILY, 10))
        gear.pack(side="right")

        panel = tk.Frame(outer, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        panel.pack(fill="both", expand=True, padx=12)
        body = tk.Frame(panel, bg=PANEL)
        body.pack(fill="both", expand=True, padx=16, pady=14)

        # status
        st = tk.Frame(body, bg=PANEL)
        st.pack(fill="x")
        self.status_dot = tk.Canvas(st, width=16, height=16, bg=PANEL, highlightthickness=0)
        self.status_dot.pack(side="left")
        self.status_var = tk.StringVar()
        tk.Label(st, textvariable=self.status_var, bg=PANEL, fg=TEXT, font=F_STATUS).pack(side="left", padx=(8, 0))
        self.sub_var = tk.StringVar()
        tk.Label(body, textvariable=self.sub_var, bg=PANEL, fg=MUTED, font=F_BASE, anchor="w").pack(
            anchor="w", pady=(4, 14))

        # the four big buttons
        cards = tk.Frame(body, bg=PANEL)
        cards.pack(fill="x")
        self.card_record = Card(cards, "record", "Record", RED, self.toggle_record)
        self.card_pause = Card(cards, "pause", "Pause", AMBER, self.toggle_pause)
        self.card_play = Card(cards, "play", "Play", ACCENT, self.play)
        self.card_stop = Card(cards, "stop", "Stop", MUTED, self.stop_playback)
        for i, c in enumerate((self.card_record, self.card_pause, self.card_play, self.card_stop)):
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            cards.columnconfigure(i, weight=1, uniform="cards", minsize=118)

        # repeat + speed
        rep = tk.Frame(body, bg=PANEL)
        rep.pack(fill="x", pady=(14, 0))
        self.loop_switch = Switch(rep, self.loop_var, command=self._loop_changed, bg=PANEL)
        self.loop_switch.pack(side="left")
        tk.Label(rep, text="Repeat continuously", bg=PANEL, fg=TEXT, font=F_BASE).pack(side="left", padx=(10, 0))
        # (Preview 4) "or play N times" hides while Repeat continuously is on, but its place stays, so the
        # window never changes size
        self.times_frame = tk.Frame(rep, bg=PANEL)
        self.times_frame.pack(side="left")
        self.times_inner = tk.Frame(self.times_frame, bg=PANEL)
        self.times_inner.pack(side="left")
        tk.Label(self.times_inner, text="   or play", bg=PANEL, fg=MUTED, font=F_BASE).pack(side="left")
        self.repeat_box = ttk.Spinbox(self.times_inner, from_=1, to=9999, width=5, textvariable=self.repeat_var,
                                      command=self._save_settings)
        self.repeat_box.pack(side="left", padx=4)
        tk.Label(self.times_inner, text="times", bg=PANEL, fg=MUTED, font=F_BASE).pack(side="left")
        self.times_frame.update_idletasks()
        self.times_frame.config(width=self.times_inner.winfo_reqwidth(), height=self.times_inner.winfo_reqheight())
        self.times_frame.pack_propagate(False)
        self.speed_box = ttk.Combobox(rep, width=6, textvariable=self.speed_var, values=SPEED_PRESETS)
        self.speed_box.pack(side="right")
        tk.Label(rep, text="Speed", bg=PANEL, fg=MUTED, font=F_BASE).pack(side="right", padx=(0, 6))
        for ev in ("<FocusOut>", "<Return>", "<<ComboboxSelected>>"):
            self.speed_box.bind(ev, lambda e: self._check_speed(quiet=True))
        self._loop_changed(save=False)

        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=14)

        # quick switch: ◀ ▶ go through the saved macros (every macro opened or saved goes in the list)
        sw = tk.Frame(body, bg=PANEL)
        sw.pack(fill="x", pady=(0, 8))
        tk.Label(sw, text="Saved macros", bg=PANEL, fg=MUTED, font=F_SMALL).pack(side="left")
        # (Preview 4) ◀ ▶ can go through one folder only
        self.row_folder_link = link(sw, "All ▾", self._row_folder_menu, bg=PANEL, fg=MUTED, font=F_SMALL)
        self.row_folder_link.pack(side="left", padx=(6, 0))
        self.mac_prev = link(sw, "◀", lambda: self.step_macro(-1), bg=PANEL, fg=TEXT, font=(FAMILY, 11))
        self.mac_prev.pack(side="left", padx=(10, 0))
        self.mac_label = tk.Label(sw, bg=PANEL, fg=MUTED, font=F_SMALL, width=34)
        self.mac_label.pack(side="left", padx=4)
        self.mac_label.bind("<Button-1>", self._mac_label_clicked)
        self.mac_next = link(sw, "▶", lambda: self.step_macro(1), bg=PANEL, fg=TEXT, font=(FAMILY, 11))
        self.mac_next.pack(side="left")
        self.mac_remove = link(sw, "Remove", self.remove_macro_from_list, bg=PANEL)
        self.mac_remove.pack(side="right")
        # one line that's always there (empty most of the time), so a message about the profile appears in
        # place: the window never changes size and the background picture isn't cut again for it
        self.profile_notice_row = tk.Frame(body, bg=PANEL)
        self.profile_notice_row.pack(fill="x", pady=(0, 8))
        self.profile_notice = tk.Label(self.profile_notice_row, text="", bg=PANEL, fg=AMBER, font=F_SMALL, anchor="w")
        self.profile_notice.pack(side="left", fill="x", expand=True)
        self.profile_notice_ok = link(self.profile_notice_row, "", lambda: self.show_profile_notice(None), bg=PANEL)
        self.profile_notice_ok.pack(side="right")
        # (2.10) Check my macro uses the same line: "See…" opens the list
        self.check_notice_see = link(self.profile_notice_row, "", self.open_check, bg=PANEL)
        self.check_notice_see.pack(side="right", padx=(0, 8))

        # a YouTube video or playlist in a window over the game
        vid = tk.Frame(body, bg=PANEL)
        vid.pack(fill="x", pady=(0, 2))
        tk.Label(vid, text="Video overlay", bg=PANEL, fg=MUTED, font=F_SMALL).pack(side="left")
        self.video_entry = tk.Entry(vid, textvariable=self.video_var, bg=FIELD, fg=TEXT, font=F_SMALL,
                                    relief="flat", insertbackground=TEXT, highlightthickness=1,
                                    highlightbackground=BORDER, highlightcolor=ACCENT)
        self.video_entry.pack(side="left", fill="x", expand=True, padx=(10, 6), ipady=3)
        self.video_entry.bind("<Return>", lambda e: self.show_video())
        self.btn_video = ttk.Button(vid, text="Show", width=7, command=self.toggle_video)
        self.btn_video.pack(side="right")
        self._video_hint()
        # the note about playlists, with a switch on the same row to hide it (2.9). Hidden, the row
        # stays (only the switch shows), so the window keeps its size
        note = tk.Frame(body, bg=PANEL)
        note.pack(fill="x", pady=(0, 8))
        self.playlist_note_var = tk.BooleanVar(value=self.settings.get("video_playlist_note", True) is not False)
        self.playlist_note = tk.Label(note, text="", bg=PANEL, fg=RED, font=F_SMALL, anchor="w")
        self.playlist_note.pack(side="left", fill="x", expand=True)
        Switch(note, self.playlist_note_var, command=self._playlist_note_switched, bg=PANEL).pack(side="right")
        self.playlist_note_label = tk.Label(note, text="", bg=PANEL, fg=DIM, font=F_SMALL)
        self.playlist_note_label.pack(side="right", padx=(0, 6))
        self._show_playlist_note()

        # the macro: its name, size and file buttons
        mac = tk.Frame(body, bg=PANEL)
        mac.pack(fill="x")
        self.name_entry = tk.Entry(mac, textvariable=self.name_var, bg=PANEL, fg=TEXT, font=(FAMILY, 11, "bold"),
                                   relief="flat", insertbackground=TEXT, highlightthickness=0, width=22)
        self.name_entry.pack(side="left", fill="x", expand=True)
        self.name_entry.bind("<Return>", lambda e: self.root.focus_set())
        self.btn_save = ttk.Button(mac, text="Save…", command=self.save)
        self.btn_load = ttk.Button(mac, text="Open…", command=self.load)
        self.btn_edit = ttk.Button(mac, text="Edit…", command=self.open_editor)
        for b in (self.btn_save, self.btn_load, self.btn_edit):
            b.pack(side="right", padx=(6, 0))
        self.info_var = tk.StringVar()
        # (width=1: a long line is cut at the window's edge instead of making the window wider; the
        # whole line shows when the mouse is over it)
        self.info_label = tk.Label(body, textvariable=self.info_var, bg=PANEL, fg=MUTED, font=F_SMALL, anchor="w",
                                   width=1)
        self.info_label.pack(fill="x", pady=(2, 0))
        self.info_full = ""
        hover_text(self.info_label, lambda: self.info_full)

        # footer: status bar + version
        foot = tk.Frame(outer, bg=BG)
        foot.pack(fill="x", padx=18, pady=(8, 10))
        self.statusbar_label = tk.Label(foot, bg=BG, fg=DIM, font=F_SMALL, anchor="w")
        self.statusbar_label.pack(side="left")
        link(foot, "About", lambda: self.open_settings("About"), fg=MUTED).pack(side="right")
        link(foot, "Stats dashboard", self.open_dashboard, fg=MUTED).pack(side="right", padx=(0, 10))
        link(foot, "Check my macro", self.open_check, fg=MUTED).pack(side="right", padx=(0, 10))
        self.picture_link = link(foot, "Picture watch", lambda: self.open_picture_watch(), fg=MUTED)
        self.picture_link.pack(side="right", padx=(0, 10))
        tk.Label(foot, text=f"v{APP_VERSION}", bg=BG, fg=DIM, font=F_SMALL).pack(side="right", padx=(0, 8))

        # an optional picture behind the window (Settings > Background)
        self.backdrop = backdrop.Backdrop(
            root, see_through=(BG, PANEL), base_color=BG, glass=panel, glass_color=PANEL,
            skip=(self.card_record, self.card_pause, self.card_play, self.card_stop),
            lift_colors={DIM: MUTED, MUTED: "#c2c2cc"})
        self._bg_library_upgrade()
        self._profiles_take_background()
        self.bg_main = BackgroundControls(self, "background", lambda: self.backdrop, lambda: self.root)
        # the settings window: one background for every page, or one for each page
        self.bg_per_page_var = tk.BooleanVar(value=bool(s.get("settings_background_per_page", False)))
        self.bg_page_var = tk.StringVar(value=SETTINGS_PAGES[0])
        self.bg_animate_var = tk.BooleanVar(value=bool(s.get("background_animate", True)))
        self.bg_fps_var = tk.IntVar(value=core.int_setting(s, "background_fps", 15, 5, 30))
        self.bg_focused_var = tk.BooleanVar(value=bool(s.get("background_animate_focused", True)))
        self.bg_pause_others_var = tk.BooleanVar(value=bool(s.get("background_pause_others", True)))

        def settings_controls(prefix):
            c = BackgroundControls(self, prefix, None, self._settings_page, same_as=self.bg_main)
            c.get_backdrop = lambda: (getattr(self, "settings_backdrop", None)
                                      if self._settings_bg_controls() is c else None)
            return c
        self.bg_settings = settings_controls("settings_background")
        self.bg_pages = {page: settings_controls("settings_background_" + page.lower().replace(" ", "_"))
                         for page in SETTINGS_PAGES}
        root.after(80, self._apply_background)

        self._build_settings_window()
        self._keep_window_size(root, "main_size")

    def _loop_changed(self, save=True):
        if self.loop_var.get():
            self.times_inner.pack_forget()
        else:
            self.times_inner.pack(side="left")
        if getattr(self, "backdrop", None) is not None:
            self.root.after_idle(self.backdrop.refresh)
        if save:
            self._save_settings()

    # ------------------------------------------------------------ (Preview 4) window sizes

    @staticmethod
    def _scrolled(bd):
        """A scroll area moved: the background picture's pieces follow the parts that moved."""
        if bd is not None and bd.active:
            bd._crop_all()

    def _keep_window_size(self, win, key, default=None):
        """Remember the size you drag a window to (settings[key] = "WxH"); it opens at that size next time
        (made smaller when it doesn't fit the screen). Its usual size is the size of its parts."""
        saved = self.settings.get(key)
        try:
            w, h = (int(v) for v in str(saved).split("x"))
        except (TypeError, ValueError):
            w = h = 0
        if w > 0 and h > 0:
            w = max(200, min(w, win.winfo_screenwidth() - 20))
            h = max(150, min(h, win.winfo_screenheight() - 60))
            win.geometry(f"{w}x{h}")
        state = {"job": None}

        def store():
            state["job"] = None
            try:
                if win.state() != "normal" or not win.winfo_viewable():
                    return
                size = f"{win.winfo_width()}x{win.winfo_height()}"
            except tk.TclError:
                return
            usual = default() if default else f"{win.winfo_reqwidth()}x{win.winfo_reqheight()}"
            want = None if size == usual else size  # (its usual size isn't kept: it may change with a version)
            if self.settings.get(key) != want:
                if want is None:
                    self.settings.pop(key, None)
                else:
                    self.settings[key] = want
                core.save_settings(self.settings)

        def changed(event):
            if event.widget is not win:
                return
            if state["job"] is not None:
                win.after_cancel(state["job"])
            state["job"] = win.after(500, store)
        win.bind("<Configure>", changed, add="+")

    def reset_window_sizes(self):
        """Settings > General > "Reset window sizes": the main window and Settings get their usual size."""
        for key, win in (("main_size", self.root), ("settings_size", self.settings_win)):
            self.settings.pop(key, None)
            if win is not None:
                win.geometry("")
        if self.settings_win is not None and getattr(self, "settings_default_size", None):
            self.settings_win.geometry(self.settings_default_size)
        core.save_settings(self.settings)
        core.diag.info("Window sizes reset to the usual ones")

    # ------------------------------------------------------------ settings window



    # ------------------------------------------------------------ mission results (Results page)



    # ------------------------------------------------------------ Edit window


    # ------------------------------------------------------------ state shown on screen

    def _refresh(self):
        if not hasattr(self, "card_play") or not hasattr(self, "key_badges"):
            return  # still building the window
        if self.record_countdown_left > 0:
            state, color = f"Recording in {self.record_countdown_left}…", AMBER
            sub = "Switch to the game window now (press Record again to cancel)"
        elif self.recording:
            state, color = ("Recording paused", AMBER) if self.paused else ("Recording", RED)
            sub = "Press Record again when you're done" if not self.paused else "Press Pause again to go on"
        elif self.playing and self.countdown_left > 0:
            state, color = f"Starting in {self.countdown_left}…", AMBER
            sub = "Switch to the game window now"
        elif self.playing and self.play_paused_at is not None:
            state, color = "Paused", AMBER
            sub = "Press " + hotkey_name(self.hotkeys["pause"]) + " or Resume to go on"
        elif self.playing:
            state, color = "Playing", ACCENT
            sub = self.play_note or "Playing the macro"
        else:
            state, color = "Ready", GREEN if self.events else MUTED
            sub = self.sub_note
        self.status_var.set(state)
        self.sub_var.set(sub)
        d = self.status_dot
        d.delete("!bdimg")
        d.create_oval(1, 1, 15, 15, outline=color, width=2)
        d.create_oval(5, 5, 11, 11, fill=color, outline="")

        k = {action: hotkey_name(self.hotkeys[action]) for action in HOTKEY_ACTIONS}
        busy = self.recording or self.playing
        self.card_record.update_card("Stop rec." if self.recording else (
            "Cancel" if self.record_countdown_left > 0 else "Record"), k["record"],
            enabled=not self.playing, active=self.recording or self.record_countdown_left > 0)
        play_paused = self.playing and self.play_paused_at is not None
        self.card_pause.update_card("Resume" if self.paused or play_paused else "Pause", k["pause"],
                                    enabled=self.recording or (self.playing and self.countdown_left == 0),
                                    active=self.paused or play_paused)
        self.card_play.update_card("Play", k["play"], enabled=not busy and bool(self.events or self.actions),
                                   active=self.playing)
        self.card_stop.update_card("Stop", k["stop"], enabled=self.playing)

        length = self.events[-1]["t"] if self.events else 0.0
        parts = [f"{len(self.events)} actions", f"{length:.1f} s"]
        if self.macro_screen:
            parts.append(f"made for {core.format_resolution(self.macro_screen)}")
        if self.current_file and os.path.splitext(os.path.basename(self.current_file))[0] != self.name_var.get():
            parts.append(os.path.basename(self.current_file))
        self._show_old_macro_note("  ·  ".join(parts))
        self._show_macro_list(busy)

        for b in (self.btn_save, self.btn_load, self.btn_edit, getattr(self, "btn_clear", None)):
            if b is not None:
                b.config(state="disabled" if busy else "normal")
        self.speed_box.config(state="disabled" if busy else "normal")
        # opening the video takes the keyboard for a moment, so not while a macro runs (closing is fine)
        self.btn_video.config(state="disabled" if busy and not self.video.is_open() else "normal")
        self.repeat_box.config(state="disabled" if busy else "normal")
        self.loop_switch.set_enabled(not busy)
        self.name_entry.config(state="disabled" if busy else "normal", disabledbackground=self.name_entry.cget("bg"),
                               disabledforeground=MUTED)
        for b in (self.made_for_box, self.play_on_box):
            b.config(state="disabled" if busy else "normal")
        for b in self.watch_widgets + self.watch_remove_buttons:
            b.config(state="disabled" if busy or image_watch is None else "normal")

        for action, badge in self.key_badges.items():
            if self.capture_callback is None or badge.cget("text") != "Press a key…":
                badge.config(text=k[action], fg=TEXT)

        if self.statusbar_var.get():
            bits = [f"{k['record']} record", f"{k['play']} play", f"{k['stop']} stop",
                    f"speed {self.speed_var.get()}"]
            if image_watch is not None and self.watch_var.get():
                n = len(self._active_watch_pictures())
                bits.append(f"watching {n} picture{'s' if n != 1 else ''}")
            self.statusbar_label.config(text="   ·   ".join(bits))
        else:
            self.statusbar_label.config(text="")
        if hasattr(self, "bg_animate_var"):
            self._apply_animation()
        self._video_mode()
        for b in (getattr(self, "backdrop", None), getattr(self, "settings_backdrop", None)):
            if b is not None:
                b.refresh()

    # ------------------------------------------------------------ settings

    def _save_settings(self):
        if hasattr(self, "sounds_var"):
            s = self.settings
            s["sounds"] = bool(self.sounds_var.get())
            s["sound_volume"] = int(self.volume_var.get())
            s["status_bar"] = bool(self.statusbar_var.get())
            s["always_on_top"] = bool(self.ontop_var.get())
            s["record_mouse_moves"] = bool(self.rec_moves_var.get())
            s["mouse_detail"] = self.detail_var.get()
            s["record_camera"] = bool(self.camera_var.get())
            s["simplify_moves"] = bool(self.simplify_var.get())
            try:
                s["record_ready_seconds"] = max(0, min(600, int(self.rec_ready_var.get())))
            except (tk.TclError, ValueError):
                pass
            s["record_ask_window"] = bool(self.rec_ask_window_var.get())
            s["pause_when_away"] = bool(self.away_var.get())
            try:
                s["away_stop_seconds"] = max(0, min(3600, int(self.away_stop_var.get())))
            except (tk.TclError, ValueError):
                pass
            try:
                s["recovery_countdown"] = max(0, min(60, int(self.recover_count_var.get())))
            except (tk.TclError, ValueError):
                pass
            s["switch_to_program"] = bool(self.switch_prog_var.get())
            s["fit_to"] = next((k for k, v in FIT_TO.items() if v == self.fit_var.get()), "screen")
            s["discord_enabled"] = bool(self.discord_var.get())
            s["discord_webhook"] = self.discord_url_var.get().strip()
            s["discord_runs"] = bool(self.discord_runs_var.get())
            s["discord_ping_fragments"] = bool(self.discord_ping_drop_var.get())
            s["discord_screenshot"] = bool(self.discord_shot_var.get())
            s["discord_shot_size"] = next((k for k, v in SHOT_SIZE.items() if v == self.discord_size_var.get()),
                                          "sharp")
            s["discord_stops"] = bool(self.discord_stop_var.get())
            s["discord_name"] = self.discord_name_var.get().strip()[:80]
            s["discord_ping"] = self.discord_ping_var.get().strip()
            s["discord_ping_when"] = next((k for k, v in PING_WHEN.items() if v == self.discord_ping_when_var.get()),
                                          "problems")
            s["discord_capture"] = self._capture_setting()
            s["results_enabled"] = bool(self.results_var.get())
            s["drops_enabled"] = bool(self.drops_var.get())
            try:
                s["results_match"] = max(50, min(99, int(self.results_match_var.get())))
            except (tk.TclError, ValueError):
                pass
            s["play_overlay"] = bool(self.overlay_var.get())
            s["check_updates"] = bool(self.update_check_var.get())
            s["app_logo_same"] = bool(self.logo_same_var.get())
            try:
                s["background_fps"] = max(5, min(30, int(self.bg_fps_var.get())))
            except (tk.TclError, ValueError):
                pass
            s["background_animate_focused"] = bool(self.bg_focused_var.get())
            s["background_pause_others"] = bool(self.bg_pause_others_var.get())
            if hasattr(self, "video_entry"):
                s["video_link"] = self.video_link_text()
                s["video_click_through"] = self.video_through_var.get()
                s["video_opacity"] = int(self.video_opacity_var.get())
                if self.video.rect:
                    s["video_rect"] = [int(v) for v in self.video.rect]
            if hasattr(self, "bg_settings"):
                for c in [self.bg_main, self.bg_settings] + list(self.bg_pages.values()):
                    c.save(s)
                s["settings_background_per_page"] = bool(self.bg_per_page_var.get())
                s["background_animate"] = bool(self.bg_animate_var.get())
            try:
                s["repeat_count"] = max(1, min(9999, int(self.repeat_var.get())))
            except (tk.TclError, ValueError):
                pass
        super()._save_settings()
        if getattr(self, "settings_win", None) is not None and getattr(self, "settings_history", None) is not None:
            self._settings_maybe_changed()

    # ------------------------------------------------------------ actions with sounds and notes

    def toggle_record(self):
        was = self.recording
        counting = self.record_countdown_left > 0
        into_editor = self.record_into is not None
        super().toggle_record()
        if self.record_countdown_left > 0 and not counting:  # the countdown before recording started
            self._tick_overlay()
            return
        if counting and not self.recording and self.record_countdown_left == 0:  # cancelled
            self.pending_profile = None
            self._record_stopped_here()
            self.sub_note = "Recording cancelled"
            if self.overlay is not None:
                self.overlay.hide()
            self._refresh()
            return
        if was and not self.recording:
            self._record_stopped_here()
            self._sound("record_stop")
            self.sub_note = "The recording was put in the Edit window" if into_editor \
                else f"Recorded {len(self.events)} actions"
            self._finish_overlay(recording=True)
            self._refresh()

    def _record_countdown_tick(self, seconds_left):
        if self._record_window_gone():
            return
        self._sound("countdown")

    def _recording_began(self):
        """After the countdown: the start sound, the name, and the timer at the top of the screen."""
        self._sound("record_start")
        if self.record_into is not None:  # (recording for the Edit window: the open macro's name stays)
            self.sub_note = "Recording for the Edit window: press Record again to stop"
        else:
            self.name_var.set("Recording " + datetime.datetime.now().strftime("%Y-%m-%d %H.%M"))
        if self.overlay_job is None:
            self._tick_overlay()

    def _on_move(self, x, y):
        if not self._capturing() or not self.settings.get("record_mouse_moves", True) or self._camera_turning():
            return
        now = time.perf_counter()
        if now - self.last_move < MOUSE_DETAIL.get(self.settings.get("mouse_detail"), 0.01):
            return
        self.last_move = now
        self._add({"type": "move", "x": x, "y": y})

    def _macro_name(self):
        return getattr(self, "play_name", "") or "Macro"

    def _program_name(self):
        p = self.macro_program or {}
        title = (p.get("title") or "").strip()
        exe = p.get("exe") or ""
        return title if title and len(title) <= 40 else (os.path.splitext(exe)[0] or "the game")

    def _check_program(self):
        """"Offer to switch to the macro's game": when Play is pressed in this window and the macro
        knows its game, switch to it first (or ask whether to play anyway when it isn't open).
        Returns False when the user cancels."""
        exe = (self.macro_program or {}).get("exe")
        if not exe or not IS_WIN or not self.switch_prog_var.get() or self.target_var.get() != SCREEN_TARGET:
            return True
        fg = window_tools.foreground()
        if fg is None or window_tools.pid_of(fg) != os.getpid():
            return True  # Play was pressed from the game (or another window): play there
        wins = window_tools.windows_of(exe)
        name = self._program_name()
        if not wins:
            self.game_asked = True  # (Check my macro doesn't tell it again)
            return messagebox.askyesno(
                "Macro Recorder", f"This macro was recorded in {name} ({exe}), which isn't open.\n\n"
                "Play it anyway?", parent=self.root)
        answer = messagebox.askyesnocancel(
            "Macro Recorder", f"Switch to {name} and play the macro there?\n\n"
            "Yes = switch to it, No = play without switching.", parent=self.root)
        if answer is None:
            return False
        if answer:
            self.root.after(0, lambda: window_tools.bring_to_front(wins[0]))
        return True

    def open_path(self, path):
        """A file dropped on the app's icon or opened with it: a stats file (.csv, 2.10) opens in Run stats
        to look at, anything else as a macro."""
        if path.lower().endswith(".csv"):
            self.open_stats_file(path)
        else:
            self.load(path)

    def play(self):
        if self.recording or self.playing or self.capture_callback is not None \
                or not (self.events or self.actions or getattr(self, "test_play", None)):
            return
        self.game_asked = False
        if not self._check_program():
            return
        if not (getattr(self, "test_play", None) or {}).get("mode") == "ghost":
            self.check_sensitive()  # (2.12: a macro from someone else that types elsewhere or reads the clipboard)
        self.play_name = self.name_var.get().strip()
        # (reset before the playback thread starts: it reads the clock straight away)
        self.play_paused_at = None
        self.play_pause_total = 0.0
        self.away_paused = False
        self.held_now = None
        super().play()
        if self.playing and not getattr(self, "test_play", None):
            # Check my macro (2.10): only tells, never stops Play
            self.check_on_play(self._read_play_on(quiet=True), skip=("game",) if self.game_asked else ())
        if self.playing and getattr(self, "fit_note", ""):
            self.sub_note = "Clicks " + self.fit_note
            if self.old_macro_var.get():  # (the note shows for a moment when Play is pressed)
                self.sub_note = self.old_macro_var.get()
        if self.playing:
            if self.settings_win is not None:
                self.close_settings()  # its picture list must not be seen as the picture on screen
            pictures = getattr(self, "picture_win", None)
            if pictures is not None and pictures.alive():
                pictures.win.withdraw()  # (the same; its changes stay: Picture watch shows it again)
            if self.edit_win is not None and self.edit_win.winfo_exists():
                if getattr(self, "test_play", None):
                    self.edit_win.withdraw()  # (a test from Edit: it comes back afterwards, changes and all)
                else:
                    self.edit_win.destroy()
            self.stopped_by_user = False
            self.play_began = None
            self._tick_overlay()
            self._sound("play_start")

    def stop_playback(self):
        if self.playing:
            self.stopped_by_user = True
            if getattr(self, "restart_after_run", None):  # (2.12: Stop also cancels a timed start that waits)
                self.cancel_timed_start("cancelled: playback was stopped")
        super().stop_playback()

    def _play_clock(self):
        """Playback's clock: it stands still while playback is paused."""
        now = self.play_paused_at if self.play_paused_at is not None else time.perf_counter()
        return now - self.play_pause_total

    def _clock_back(self, seconds):
        if self.play_paused_at is None:  # (while paused the clock isn't running anyway)
            self.play_pause_total += seconds

    def _user_paused(self):
        return self.play_paused_at is not None and not getattr(self, "away_paused", False)

    def _away_pause(self, on):
        """Paused because the game isn't in front (runs on the playback thread)."""
        if on and self.play_paused_at is None:
            self.away_paused = True
            self.play_paused_at = time.perf_counter()
            self._call_ui(lambda: (self._sound("pause"), self._refresh()))
        elif not on and getattr(self, "away_paused", False):
            self.play_pause_total += time.perf_counter() - self.play_paused_at
            self.play_paused_at = None
            self.away_paused = False
            self._call_ui(lambda: (self._sound("resume"), self._refresh()))

    def _replay_event(self, ev, held_keys, held_buttons):
        self.held_now = (held_keys, held_buttons)
        super()._replay_event(ev, held_keys, held_buttons)
        self._keys_seen(ev)  # (Preview 4: keys on screen)

    def _add(self, event):
        super()._add(event)
        self._keys_seen(event)  # (Preview 4: keys on screen, while recording)

    def toggle_pause(self):
        """While recording: pause the recording. While playing: pause playback, or go on."""
        if not self.playing:
            was = self.paused
            super().toggle_pause()
            if self.recording and self.paused != was:
                self._sound("pause" if self.paused else "resume")
            return
        if self.countdown_left > 0 or getattr(self, "away_paused", False):
            return  # (paused because the game isn't in front: clicking into the game goes on)
        if self.play_paused_at is None:
            self.play_paused_at = time.perf_counter()
            if self.held_now is not None:
                # let go of everything, so the character doesn't keep walking while paused
                self._release_held(None, *self.held_now)
            self._sound("pause")
        else:
            self.play_pause_total += time.perf_counter() - self.play_paused_at
            self.play_paused_at = None
            self._sound("resume")
        self._refresh()

    def _set_countdown(self, seconds):
        def tick():  # (not for the first second: "Playing starts" is sounding then)
            if 0 < seconds != self.countdown_left:
                self._sound("countdown")
        self._call_ui(tick)
        super()._set_countdown(seconds)

    def _picture_seen(self):
        self._sound("picture_seen")

    def _recovery_tick(self, kind, seconds_left):
        self._call_ui(lambda: self._sound("recover_disconnect" if kind == "disconnect" else "recover_close"))

    def _run_finished(self, count, how):
        super()._run_finished(count, how)
        if not getattr(self, "test_play", None):  # (Preview 4: a milestone may have been reached)
            self._call_ui(self.check_milestones)
        if getattr(self, "restart_after_run", None):  # (2.12: a timed start waits for this run's end)
            core.diag.info("Timed start: the run ended, the macro stops and starts again")
            self.stop_play.set()
        sound = self._run_sound()
        if sound:
            self._call_ui(lambda: self._sound(sound))

    def _run_sound(self):
        """The sound for the run that just ended: a divine fragment (it matters most, and only one
        sound plays at a time), else a win or a loss; None for an unknown result."""
        s = self.session
        if s.fragments and s.fragments[-1] > 0 and self.sound_choice("fragment")["mode"] != "off":
            return "fragment"
        status = s.runs[-1][0] if s.runs else None
        return {"win": "win", "loss": "loss"}.get(status)

    def _recording_clock(self):
        """How long it has been recording (the time paused not counted)."""
        now = self.pause_started if self.paused else time.perf_counter()
        return max(0.0, now - self.start_time - self.paused_total)

    def _tick_overlay(self):
        """Keep the top-of-screen timer up to date while playing or recording (every quarter second)."""
        self.overlay_job = None
        if self.playing or self.recording:
            self._keys_start()  # (Preview 4: keys on screen)
        if not (self.playing or self.recording or self.record_countdown_left > 0):
            return
        if not self.overlay_var.get():
            if self.overlay is not None:
                self.overlay.hide()
        else:
            if self.overlay is None:
                self.overlay = PlayOverlay(self.root, self.screen_w)
            name = self.name_var.get()
            keys = {a: hotkey_name(self.hotkeys[a]) for a in ("pause", "stop")}
            rec_keys = {"pause": hotkey_name(self.hotkeys["pause"]), "stop": hotkey_name(self.hotkeys["record"])}
            what = "Recording for the Edit window" if self.record_into is not None else "Recording a new macro"
            if self.record_countdown_left > 0:
                self.overlay.show("Recording in", str(self.record_countdown_left),
                                  what + self.record_window_text(), AMBER)
            elif self.recording:
                clock = format_clock(self._recording_clock())
                note = f"{what}  ·  {len(self.events)} actions"
                if self.paused:
                    self.overlay.show("Rec. paused", clock, note, AMBER, rec_keys, stop_word="Stop rec.")
                else:
                    self.overlay.show("Recording", clock, note, RED, rec_keys, stop_word="Stop rec.")
            elif self.countdown_left > 0:
                self.overlay.show("Starting in", str(self.countdown_left), name, AMBER, keys)
            elif getattr(self, "recover_left", None) and self.play_paused_at is None:
                kind, left = self.recover_left
                self.overlay.show("Rejoining in" if kind == "disconnect" else "Reopening in", str(left),
                                  name, AMBER, keys)
            else:
                if self.play_began is None:
                    self.play_began = self._play_clock()
                note = self.play_note.rstrip(".").replace("…", "").replace("Playing run", "Run") or name
                extra = []
                if self.result_matchers and self.session.runs:
                    extra.append(self.session.summary())
                counters = getattr(self, "counters", None)
                shown = getattr(self, "timer_text", None)  # (2.12) Do maths "Total: 1+4=5", or a Note
                if shown:
                    extra.append(short(shown, 40))
                if counters:  # (2.11) "Wins 3 · Tries 1"
                    extra += [f"{short(n, 14)} {step_more.fmt(v)}" for n, v in list(counters.items())[:4]
                              if not (shown and shown.startswith(n + ":"))]
                if extra:
                    note = "  ·  ".join([short(note, 34)] + extra)
                clock = format_clock(self._play_clock() - self.play_began)
                test = getattr(self, "test_play", None)
                word = ("WATCH ONLY" if getattr(self, "ghost", False) else "TEST") if test else "Playing"
                if test and getattr(self, "ghost", False):
                    also = getattr(self, "ghost_keys", "") or ("" if "nothing is pressed" in note.lower()
                                                              else short(note, 40))
                    note = "Nothing is pressed" + (f"  ·  {also}" if also else "")
                if self.play_paused_at is not None:
                    self.overlay.show("Paused", clock, note, AMBER, keys)
                    away = getattr(self, "away_games", None) if getattr(self, "away_paused", False) else None
                    self.overlay.front_button(self._bring_game_front if away and IS_WIN else None,
                                              f"Bring {self._away_name(away) or 'it'} to front")
                else:
                    self.overlay.front_button(None)
                    self.overlay.show(word, clock, note, AMBER if test else ACCENT, keys)
                    # the next look is when the shown second changes (at most half a second away, so
                    # a pause or a new note still shows quickly)
                    left = 1.0 - (self._play_clock() - self.play_began) % 1.0
                    self.overlay_job = self.root.after(int(min(0.5, left) * 1000) + 15, self._tick_overlay)
                    return
        self.overlay_job = self.root.after(250, self._tick_overlay)

    def _bring_game_front(self):
        """(Preview 4) "Bring it to front" under the timer: the paused macro's window comes to the front
        (playback then goes on by itself, as when you click into it)."""
        try:  # (the playback thread may add a window to the set right now)
            wins = [h for h in list(getattr(self, "away_games", None) or ()) if window_tools.is_window(h)]
        except RuntimeError:
            return
        if not wins:
            return
        core.diag.info("Bring it to front: the macro's window was put in front")
        window_tools.force_to_front(wins[0])

    def _finish_overlay(self, recording=False):
        if self.overlay is not None:
            self.overlay.front_button(None)
        if recording:
            if self.overlay_job is not None:
                self.root.after_cancel(self.overlay_job)
                self.overlay_job = None
            if self.overlay is None or not self.overlay_var.get():
                return
            took = format_clock(self.events[-1]["t"] if self.events else 0.0)
            self.overlay.show("Recorded", took, f"{len(self.events)} actions", GREEN)
            self.root.after(4000, lambda: None if (self.playing or self.recording or self.record_countdown_left)
                            else self.overlay.hide())
            return
        if self.overlay is None or not self.overlay_var.get() or self.play_began is None:
            if self.overlay is not None:
                self.overlay.hide()
            return
        took = format_clock(self._play_clock() - self.play_began)
        word = "Stopped" if getattr(self, "stopped_by_user", False) else "Finished"
        self.overlay.show(word, took, self.name_var.get(), MUTED if word == "Stopped" else GREEN)
        self.root.after(4000, lambda: None if self.playing else self.overlay.hide())

    def _playback_done(self):
        if self.play_paused_at is not None:  # stopped while paused
            self.play_pause_total += time.perf_counter() - self.play_paused_at
            self.play_paused_at = None
        super()._playback_done()
        if self.overlay_job is not None:
            self.root.after_cancel(self.overlay_job)
            self.overlay_job = None
        self._finish_overlay()
        self.away_paused = False
        runs = getattr(self, "runs_done", 0)
        runs_text = f"{runs} run{'s' if runs != 1 else ''}"
        reason = self.stop_reason
        if reason:
            self.sub_note = short(reason, 60)
            self._sound("error")
            text = f"Stopped after {runs_text}. {reason}"
        elif getattr(self, "auto_stopped", None):
            self.sub_note = "Stopped by itself"
            self._sound("play_end")
            text = f"Stopped by itself after {runs_text}: {self.auto_stopped}."
        elif getattr(self, "stopped_by_user", False):
            self.sub_note = "Stopped"
            self._sound("play_end")
            text = f"Stopped by you after {runs_text}."
        else:
            self.sub_note = "Finished playing"
            self._sound("play_end")
            text = f"Finished ({runs_text})."
        if getattr(self, "test_play", None):
            self._test_done(reason)
            return
        plan, self.restart_after_run = getattr(self, "restart_after_run", None), None
        if plan is not None:  # (2.12: the timed start that waited: now, with its warning and countdown)
            plan.pop("phase", None)
            self.root.after(800, lambda: self.plan_timed_start(time.time(), plan.get("why", "timed"),
                                                               **{k: v for k, v in plan.items()
                                                                  if k not in ("at", "why")}))
        self._add_to_all_time()
        self._remember_found_sizes()
        self._show_session()
        if self.discord_stop_var.get():
            self._discord_summary(text, problem=bool(reason))
        self._refresh()
        self._pings_on_stop(text)
        if getattr(self, "auto_stopped", None) and not reason:
            self._auto_stop_then()
        if reason:
            extra = ("\n\nSettings > About > Make a report saves the details in a file, to send to whoever helps you."
                     if "error" in reason else "")
            messagebox.showwarning("Macro Recorder", reason + extra, parent=self.root)

    # ------------------------------------------------------------ (2.11) test plays from the Edit window

    def play_test(self, steps, mode="test", screen=None, program=None, found=True):
        """Play some steps as a test (mode "test") or only show them (mode "ghost": nothing is pressed).
        A test never counts: no results, run stats, Discord, Stop by itself, picture watch or rejoining.
        screen / program: those of the macro the steps come from. found: in a ghost test, picture steps
        take the "found" way (else "not found")."""
        why = ("recording is going on" if self.recording or self.record_countdown_left > 0 else
               "a macro is playing" if self.playing else "nothing is chosen to play" if not steps else None)
        if why:
            core.diag.info(f"Test from Edit didn't start: {why}")
            self.boxes.showinfo("Test", f"The test can't start now: {why}.",
                                parent=getattr(self, "edit_win", None) or self.root)
            return False
        core.diag.info(f"Test from Edit ({'watch only' if mode == 'ghost' else 'test'}): {len(steps)} action(s)")
        self.test_play = {"mode": mode, "steps": steps, "screen": screen, "program": program, "found": found}
        self.ghost_keys = ""
        if mode == "ghost":
            # belt and braces: even if something asked them, these controllers press nothing
            self.real_controllers = (self.kb_ctrl, self.mouse_ctrl)
            self.kb_ctrl = self.mouse_ctrl = NoInput()
        try:
            self.play()
        finally:
            if not self.playing:
                self._end_test()
                core.diag.info("Test from Edit didn't start (not played)")
        return self.playing

    def _end_test(self):
        if getattr(self, "real_controllers", None):
            self.kb_ctrl, self.mouse_ctrl = self.real_controllers
            self.real_controllers = None
        self.test_play = None
        self.ghost = False
        self.ghost_keys = ""
        dot = getattr(self, "ghost_dot", None)
        if dot is not None:
            dot.hide()

    def _test_done(self, reason):
        ghost = getattr(self, "ghost", False)
        back, self.test_restore = getattr(self, "test_restore", None) or [], []
        self._end_test()
        for w in back:  # (e.g. "Edit the recorded events…", hidden while its rows played)
            try:
                if w.winfo_exists():
                    w.deiconify()
                    w.lift()
            except tk.TclError:
                pass
        what = "Watch-only test" if ghost else "Test"
        self.sub_note = (f"{what} stopped" if getattr(self, "stopped_by_user", False) else f"{what} done") \
            + " (not counted)"
        self._refresh()
        ed = getattr(self, "edit_win", None)
        if ed is not None and ed.winfo_exists():
            ed.deiconify()
            ed.lift()
        if reason:
            messagebox.showwarning("Macro Recorder", reason, parent=self.root)

    def _ghost_event(self, ev):
        """Watch only: show where the mouse would be and which key would be pressed (sends nothing)."""
        kind = ev.get("type")
        if kind in ("move", "click", "scroll") and "x" in ev:
            self.ghost_at = (int(ev["x"]), int(ev["y"]), kind == "click" and ev.get("pressed"))
        elif kind == "key":
            if ev.get("pressed"):
                self.ghost_keys = "Pressing " + workflow.key_text(ev.get("key") or {})
        if not getattr(self, "ghost_job", False):
            self.ghost_job = True
            self._call_ui(self._ghost_show)

    def _ghost_show(self):
        self.ghost_job = False
        if not getattr(self, "ghost", False):
            return
        at = getattr(self, "ghost_at", None)
        if at is None:
            return
        if getattr(self, "ghost_dot", None) is None:
            self.ghost_dot = GhostDot(self.root)
        self.ghost_dot.show(*at)

    def load(self, path=None, quiet=False):
        ok = super().load(path, quiet=quiet)
        if ok:
            self.pending_profile = None  # (another macro: a profile chosen for a new recording is dropped)
            self.name_var.set(os.path.splitext(os.path.basename(self.current_file))[0])
            self.sub_note = "Macro opened"
            self.unsaved = False
            self._remember_macro(self.current_file)
            self._refresh()
            self.root.after(50, self._offer_file_pictures)
        return ok

    OLD_MACRO_NOTE = "Recorded before 2.6: in a window its clicks may miss. Record it again or play in fullscreen."

    def _show_old_macro_note(self, info):
        """The line under the macro's name: its length and size, or, for an opened macro that doesn't
        know its game window (recorded before 2.6, so it has no window size in it), a short yellow note
        in its place (the line keeps its height, so the window doesn't change size). The note shows in
        Settings > Playback too."""
        old = bool(self.current_file and (self.events or self.actions)
                   and not (self.macro_program or {}).get("client"))
        text = self.OLD_MACRO_NOTE if old else ""
        if self.old_macro_var.get() != text:
            self.old_macro_var.set(text)
        self.info_full = f"{text}\n{info}" if old else info
        self.info_var.set(text or info)
        color = AMBER if old else MUTED
        if self.info_label.cget("fg") != color:
            self.info_label.config(fg=color)

    # ------------------------------------------------------------ pictures to watch for, inside .macro files

    def _pictures_for_file(self, path=None):
        """The pictures to watch for, to save inside a macro (Picture watch > "Save these pictures
        inside the macros you save"): [{"png": base64 PNG, "screen_h": …}]. Only the ones used for that
        macro (path): those that are on and are for every macro or for this one."""
        if image_watch is None or not self.settings.get("watch_save_with_macro", True):
            return []
        out = []
        for pic in self._active_watch_pictures(path):
            try:
                entry = {"png": image_watch.png_data(pic["img"]), "screen_h": pic.get("screen_h")}
            except Exception:
                continue
            # (2.9) its name and what it does go with it, so it doesn't arrive as a nameless picture
            # that only starts the macro over. Not the files of this PC: the rejoin check picture, or
            # which macros it's used for
            # (2.9.1) checked, and the rejoin macro by its file name only: it was the whole path, with
            # the Windows user name in it
            entry.update(core.shared_picture_fields(pic))
            if entry.get("macro"):
                entry["macro"] = os.path.basename(entry["macro"])
            if pic.get("builtin"):
                entry["builtin"] = pic["builtin"]
            out.append(entry)
        return out

    def _offer_file_pictures(self):
        """A macro that comes with pictures to watch for: offer to add the ones that aren't in the list."""
        import base64
        import hashlib

        if getattr(self, "skip_file_pictures", False):  # (opened from the phone remote: nobody to ask)
            self.skip_file_pictures = False
            return
        pics = (getattr(self, "file_data", None) or {}).get("watch_pictures")
        if image_watch is None or not isinstance(pics, list) or not pics:
            return

        def digest(img):
            return hashlib.sha1(img.tobytes() + bytes(str(img.shape), "ascii")).hexdigest()
        have = {digest(p["img"]) for p in self.watch_pictures}
        new = []
        for entry in pics:
            try:
                import numpy as np
                data = np.frombuffer(base64.b64decode(entry["png"]), np.uint8)
                img = image_watch.cv2.imdecode(data, image_watch.cv2.IMREAD_COLOR)
                if img is not None and digest(img) not in have:
                    # (2.9.1) only known actions and sensible values; its macro is looked for beside
                    # the macro it came with (never a path written in the file)
                    folder = os.path.dirname(self.current_file) if self.current_file else None
                    fields = core.shared_picture_fields(entry, folder)
                    if entry.get("builtin") in core.BUILTINS:
                        fields["builtin"] = entry["builtin"]
                        fields["group"] = core.GROUP_AOTR
                    screen_h = entry.get("screen_h")
                    if not isinstance(screen_h, int) or isinstance(screen_h, bool) or not 200 <= screen_h <= 10000:
                        screen_h = None
                    new.append((img, screen_h, fields))
                    have.add(digest(img))
            except Exception:
                continue
        if not new:
            return
        n = len(new)
        from picture_actions_ui import action_summary
        # (2.9.1) says what each one would do, so nothing is added unseen
        lines = "\n".join(f"  \u2022 {f.get('name') or 'picture'}: {action_summary(f)}" for _i, _h, f in new[:8])
        more = f"\n  \u2026 and {n - 8} more" if n > 8 else ""
        if not messagebox.askyesno(
                "Macro Recorder", f"This macro comes with {n} picture{'s' if n != 1 else ''} to watch for "
                f"that you don't have yet:\n\n{lines}{more}\n\nAdd "
                f"{'them' if n != 1 else 'it'} to Picture watch?", parent=self.root):
            return
        for img, screen_h, fields in new:
            self._add_watch_picture(img, screen_h=screen_h, fields=fields)
        self.sub_note = f"Added {n} picture{'s' if n != 1 else ''} to Picture watch"
        self._refresh()

    # ------------------------------------------------------------ the video window

    # ------------------------------------------------------------ keys for the video window

    # action, name, what the page does, how much

    PLAYLIST_NOTE = "Playlists aren't supported, only single videos."

    def _show_playlist_note(self):
        on = bool(self.playlist_note_var.get())
        self.playlist_note.config(text=self.PLAYLIST_NOTE if on else "")
        self.playlist_note_label.config(text="" if on else "Playlist note")

    def _playlist_note_switched(self):
        self.settings["video_playlist_note"] = bool(self.playlist_note_var.get())
        core.save_settings(self.settings)
        self._show_playlist_note()
        if getattr(self, "backdrop", None) is not None:
            self.backdrop.refresh()

    def _on_close(self):
        try:
            self.remote.stop()
        except Exception:
            pass
        try:
            self.video.close(wait=True)
        except Exception:
            pass
        super()._on_close()

    # ------------------------------------------------------------ saved macros (◀ ▶ quick switch)

    def macro_list(self):
        """The saved macros: file paths, in the order they were added (up to MAX_MACROS)."""
        lib = self.settings.get("macro_library")
        if not isinstance(lib, list):
            lib = self.settings["macro_library"] = []
        lib[:] = [p for p in lib if isinstance(p, str) and p]
        return lib

    def _forget_deleted_macros(self):
        """Take macros whose file was deleted off the list (so the row doesn't count a macro that
        isn't there any more). A file whose folder can't be reached right now (an unplugged drive)
        stays. Looked at most every 3 seconds."""
        now = time.monotonic()
        if now - getattr(self, "macros_checked", -10.0) < 3.0:
            return
        self.macros_checked = now
        lib = self.macro_list()
        kept = [p for p in lib if os.path.isfile(p) or not os.path.isdir(os.path.dirname(p))]
        if len(kept) != len(lib):
            diag.info(f"Took {len(lib) - len(kept)} deleted macro file(s) off the saved macros list")
            lib[:] = kept
            core.save_settings(self.settings)

    def _list_index(self, path):
        key = os.path.normcase(os.path.abspath(path)) if path else None
        for i, p in enumerate(self.macro_list()):
            if os.path.normcase(os.path.abspath(p)) == key:
                return i
        return None

    def _remember_macro(self, path):
        """Put an opened or saved macro in the list (the oldest one goes when it's full)."""
        if not path or self._list_index(path) is not None:
            return
        self.macros_checked = -10.0
        self._forget_deleted_macros()
        lib = self.macro_list()
        lib.append(os.path.abspath(path))
        del lib[:-MAX_MACROS]
        self._save_settings()

    def _show_macro_list(self, busy=False):
        self._forget_deleted_macros()
        lib = self.row_macros()  # (Preview 4: only one folder's, when one is chosen)
        i = self._row_index(lib, self.current_file)
        folder = self.row_folder()
        if getattr(self, "row_folder_link", None) is not None:
            self.row_folder_link.config(text=(short(folder, 14) if folder else "All") + " ▾")
        only = i is None and len(lib) == 1 and not busy  # one saved macro, not open: click its name
        if i is not None:
            name = os.path.splitext(os.path.basename(lib[i]))[0]
            text = f"{i + 1} of {len(lib)}:  {short(name, 28)}"
        elif only:
            text = "Click to open:  " + short(os.path.splitext(os.path.basename(lib[0]))[0], 18)
        elif lib:
            text = f"{len(lib)} saved  ·  this one isn't in " + ("this folder" if folder else "the list")
        elif folder:
            text = "no macros in this folder"
        else:
            text = "macros you open or save show up here"
        self.mac_label.config(text=text, cursor="hand2" if only else "arrow")
        self.mac_label_opens = only
        arrows = len(lib) > 1 and not busy  # (nothing to switch to with one macro or none)
        for a, sym in ((self.mac_prev, "◀"), (self.mac_next, "▶")):
            a.config(text=sym if arrows else "", cursor="hand2" if arrows else "arrow")
        rem = self._list_index(self.current_file) is not None and not busy
        self.mac_remove.config(text="Remove" if rem else "", cursor="hand2" if rem else "arrow")

    @staticmethod
    def _row_index(lib, path):
        key = os.path.normcase(os.path.abspath(path)) if path else None
        return next((i for i, p in enumerate(lib) if os.path.normcase(os.path.abspath(p)) == key), None)

    def _has_unsaved_macro(self):
        return bool(self.events) and (self.current_file is None or getattr(self, "unsaved", False))

    def _mac_label_clicked(self, _e=None):
        if getattr(self, "mac_label_opens", False):
            self.step_macro(1)

    def step_macro(self, d):
        """◀ / ▶: open the previous or next saved macro (Preview 4: of the chosen folder only)."""
        lib = self.row_macros()
        if self.recording or self.playing or not lib:
            return
        i = self._row_index(lib, self.current_file)
        if i is not None and len(lib) < 2:
            return
        if self._has_unsaved_macro() and not messagebox.askyesno(
                "Macro Recorder", "This macro isn't saved. Switch to another one anyway?\n\n"
                "(Click No, then Save…, to keep it.)", parent=self.root):
            return
        if i is None:  # not in the list: ▶ starts at the first one, ◀ at the last
            order = lib[:] if d > 0 else lib[::-1]
        else:
            order = [lib[(i + d * n) % len(lib)] for n in range(1, len(lib))]
        missing = []
        for path in order:  # skip files that were moved or deleted
            if not os.path.isfile(path):
                missing.append(path)
                continue
            if self.load(path, quiet=True):
                self.sub_note = "Switched macro" + (f" (skipped {len(missing)} missing file"
                                                    f"{'s' if len(missing) != 1 else ''})" if missing else "")
            else:
                self.sub_note = "Couldn't open " + os.path.basename(path)
            self._refresh()
            return
        self.sub_note = "None of the other saved macros could be found"
        self._refresh()

    def remove_macro_from_list(self):
        """Take the open macro out of the list and close it (the file itself stays where it is).
        The next macro in the list opens instead, or an empty one when the list is empty."""
        i = self._list_index(self.current_file)
        if i is None or self.recording or self.playing:
            return
        if getattr(self, "unsaved", False) and not messagebox.askyesno(
                "Macro Recorder", "This macro has changes that aren't saved. Remove it anyway?\n\n"
                "(Click No, then Save…, to keep them.)", parent=self.root):
            return
        lib = self.macro_list()
        gone = os.path.splitext(os.path.basename(lib[i]))[0]
        del lib[i]
        self._save_settings()
        for n in range(len(lib)):  # open the one that moved into its place (skip missing files)
            path = lib[(i + n) % len(lib)]
            if os.path.isfile(path) and self.load(path, quiet=True):
                self.sub_note = f"Removed {short(gone, 24)} from the list (the file wasn't deleted)"
                self._refresh()
                return
        self.events = []
        self.actions = None
        self.current_file = None
        self.macro_screen = None
        self.unsaved = False
        self._show_made_for()
        self.name_var.set("")
        self.sub_note = f"Removed {short(gone, 24)} from the list (the file wasn't deleted)"
        self._refresh()

    def clear(self):
        had = bool(self.events)
        super().clear()
        if had and not self.events:
            self.unsaved = False
            self.name_var.set("")
            self.sub_note = "Record something, or open a macro"
            self._refresh()

    def _save_ahk(self, path):
        """Save a copy as an AutoHotkey v2 script (the .macro file, if any, stays the one that's open)."""
        events = core.scale_events(self.events, self.macro_screen, (self.screen_w, self.screen_h)) \
            if self.macro_screen else self.events
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(importers.export_ahk(events, self.name_var.get().strip() or "macro"))
        except OSError as exc:
            messagebox.showerror("Macro Recorder", f"Couldn't save the script:\n{exc}", parent=self.root)
            return
        steps = sum(1 for ev in self.events if ev.get("type") == "wait_picture")
        self.sub_note = "Saved as an AutoHotkey script" + (" (picture steps left out)" if steps else "")
        self._refresh()

    def save(self):
        if not (self.events or self.actions):
            messagebox.showinfo("Macro Recorder", "Nothing to save yet. Record something first.")
            return
        name = "".join(c for c in self.name_var.get().strip() if c not in '\\/:*?"<>|') or "my_macro"
        path = filedialog.asksaveasfilename(defaultextension=core.FILE_EXT,
                                            filetypes=[core.FILE_TYPES[0], ("AutoHotkey v2 script", "*.ahk")]
                                            + core.FILE_TYPES[1:], initialfile=name + core.FILE_EXT)
        if not path:
            return
        if path.lower().endswith((".ahk", ".ah2")):
            self._save_ahk(path)
            return
        self._read_made_for(quiet=True)
        events = self.events
        if self.settings.get("simplify_moves", False):
            events = core.simplify_moves(events)  # (put back in full when the file is opened)
        data = {"app": "macro_recorder", "version": core.FILE_VERSION, "name": self.name_var.get().strip(),
                "events": events}
        if self.actions:
            # the steps made in Edit; "events" above keeps every recorded part for older versions
            steps = self.actions
            if self.settings.get("simplify_moves", False):
                steps = workflow.map_points(steps, core.simplify_moves)
            data["actions"] = steps
        if self.macro_screen:
            data["screen"] = {"width": self.macro_screen[0], "height": self.macro_screen[1]}
        if self.macro_program:
            data["program"] = self.macro_program
        if getattr(self, "macro_vary", None):
            data["vary"] = self.macro_vary
        self.apply_pending_profile()  # (2.11: a profile chosen in "Record in which window?")
        if getattr(self, "macro_profile", None):
            data["profile"] = self.macro_profile
        pictures = self._pictures_for_file(path)
        if pictures:
            data["watch_pictures"] = pictures
        macro_versions.keep(path)  # (2.10: the version it had stays in Restore an older version…)
        try:
            with open(path, "w", encoding="utf-8") as f:
                core.dump_macro(data, f)
        except OSError as exc:
            diag.error("Couldn't save a macro", exc)
            messagebox.showerror("Macro Recorder", f"Couldn't save the macro:\n{exc}", parent=self.root)
            return
        self.current_file = path
        self.unsaved = False
        self.name_var.set(os.path.splitext(os.path.basename(path))[0])
        self.sub_note = "Saved"
        self._remember_macro(path)
        self._refresh()


# ---------------------------------------------------------------- start

class NoInput:
    """Stands in for the keyboard and mouse controllers during a watch-only test: presses nothing."""
    position = (0, 0)

    def __getattr__(self, name):
        return lambda *a, **k: None


class GhostDot:
    """Watch only (2.11): a dot where the mouse would be (bigger and red on a click). Clicks go through
    it and it never takes the focus."""
    SIZE = 26

    def __init__(self, root):
        self.win = win = tk.Toplevel(root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        key = "#010203"
        win.config(bg=key)
        try:
            win.attributes("-transparentcolor", key)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(win, width=self.SIZE, height=self.SIZE, bg=key, highlightthickness=0)
        self.canvas.pack()
        self.made_through = False

    def show(self, x, y, click=False):
        c = self.canvas
        c.delete("all")
        r = 12 if click else 7
        mid = self.SIZE // 2
        c.create_oval(mid - r, mid - r, mid + r, mid + r, fill=RED if click else ACCENT, outline="white", width=2)
        self.win.geometry(f"+{x - mid}+{y - mid}")
        if self.win.state() == "withdrawn":
            self.win.deiconify()
        if not self.made_through and IS_WIN:
            # (only once it's on screen: before that the outer window doesn't exist yet, and the setting
            # would land on the inner one and hide the dot)
            self.win.update_idletasks()
            try:
                import ctypes

                u = ctypes.windll.user32
                hwnd = u.GetParent(self.win.winfo_id())
                if hwnd:
                    u.SetWindowLongW(hwnd, -20, u.GetWindowLongW(hwnd, -20) | 0x80000 | 0x20 | 0x80 | 0x8000000)
                    self.made_through = True
            except Exception:
                pass

    def hide(self):
        try:
            self.win.withdraw()
        except tk.TclError:
            pass


def use_preview_settings():
    """The preview keeps its own settings folder (a copy of the real one on first start), so trying
    it never changes the real app's hotkeys or pictures."""
    real_dir = os.path.dirname(core.settings_path())
    preview_dir = real_dir + " Preview"
    if not os.path.exists(os.path.join(preview_dir, "settings.json")) and os.path.isdir(real_dir):
        try:
            shutil.copytree(real_dir, preview_dir, dirs_exist_ok=True)
        except Exception:
            pass
    core.settings_path = lambda: os.path.join(preview_dir, "settings.json")


def _close_splash():
    """Close the "Starting..." picture the exe shows while it unpacks (only in a built exe)."""
    try:
        import pyi_splash

        pyi_splash.close()
    except Exception:
        pass


def main(preview=False):
    if preview:
        use_preview_settings()
    core.make_dpi_aware()
    if IS_MAC:
        try:
            core.mac_prepare_pynput()
        except Exception:
            pass
    import threading
    threading.Thread(target=updater.cleanup_old, daemon=True).start()  # leftover from an update
    if IS_WIN:  # unpacked copies left in Temp by copies that were force-closed
        threading.Thread(target=updater.cleanup_leftover_unpacks, daemon=True).start()
    startup = timed_start_ui.STARTUP_FLAG in sys.argv  # (2.12: opened by Windows at start-up)
    if not timed_start_ui.single_copy(preview) and startup:
        return  # (already open: start-up never opens a second copy)
    root = tk.Tk()
    app = ModernMacroRecorder(root, preview=preview)
    diag.info(f"Started version {APP_VERSION}" + (" (preview)" if preview else ""))
    root.report_callback_exception = app.report_error
    threading.excepthook = lambda a: diag.error(f"Error on a helper thread ({a.thread.name if a.thread else '?'})",
                                                a.exc_value)
    app._whats_new_on_start()
    root.after_idle(_close_splash)
    root.after(20000, app._summary_tick)  # the Discord daily / weekly summary
    if app.first_start_due() and not preview:
        root.after(800, app.open_first_start)
    if app.update_check_var.get():
        root.after(4000, app.check_for_update)
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        root.after(100, lambda: app.open_path(sys.argv[1]))
    if startup:
        root.after(4000, app.startup_action)
    root.after(3000, app.schedule_start)  # (2.12: the remembered alarm and timer)
    root.after(5000, app.tour_when_ready)  # (Preview 4: the guided tour, once)
    if IS_MAC:
        def open_documents(*paths):
            if paths:
                app.open_path(paths[0])
        root.createcommand("::tk::mac::OpenDocument", open_documents)
        missing = core.mac_missing_permissions()
        if missing:
            root.after(300, lambda: messagebox.showwarning(
                "Macro Recorder", core.MAC_PERMISSION_HELP.format(missing=", ".join(missing))))
    root.mainloop()


if __name__ == "__main__":
    main()
