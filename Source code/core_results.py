"""Results of each run: win / loss / unknown, late results, divine fragments.

Part of the core MacroRecorder class (split out of macro_recorder.py in 2.13): its methods are
unchanged; a name that lives in macro_recorder itself is written core.name."""
import diag
import late_results
import os
import own_windows
import run_history
import stats
import threading
import time
import window_tools
import macro_recorder as core


class CoreResultsMixin:
    _late_lock = threading.Lock()

    RESULT_TITLES = {stats.WIN: "MISSION COMPLETED", stats.LOSS: "MISSION FAILED"}

    _result_lock = threading.Lock()  # the watcher and the end-of-run check use the same pictures

    def _macro_name(self):
        return os.path.splitext(os.path.basename(self.current_file))[0] if self.current_file else "Macro"

    def _finish_run(self, count, how):
        """A run is over: work out whether it was won, lost or unknown, add it to the session's
        results, then tell _run_finished."""
        status = stats.UNKNOWN
        if self.result_matchers:
            self.last_result_scores = {}
            began_wall, began_clock = getattr(self, "run_began", (time.perf_counter(), self._play_clock()))
            status = self._run_result(began_wall)
            if status == stats.UNKNOWN and any(self._kinds_found().values()):
                # (2.12) nothing near the usual spot: one more look, over the whole screen
                status = self._run_result(began_wall, whole_screen=True)
            if status != stats.UNKNOWN:
                # the result showing now belongs to this run, even if the watcher only notices it
                # after the next run has started
                self.result_consumed = (status, time.perf_counter())
            seconds = self._play_clock() - began_clock
            if status == stats.UNKNOWN:  # (so a report says why, not only that it was unknown)
                need = self.settings.get("results_match", core.RESULTS_MATCH_DEFAULT) / 100.0
                diag.info(f"Run {count} ended unknown: " + self._unknown_reason(self.last_result_scores, need))
        else:
            seconds = self._play_clock() - getattr(self, "run_began", (0, self._play_clock()))[1]
        if status in (stats.WIN, stats.LOSS):
            self.last_result_clock = self._play_clock()  # (2.12: the stuck run guard counts from here)
        fragments = self._count_drops() if self.settings.get("drops_enabled", True) else 0
        if self._late_leftover(status, seconds, fragments):
            return False
        self.session.add(status, seconds, fragments)
        name = getattr(self, "chain_step", None) or getattr(self, "playing_name", None) or self._macro_name()
        self.last_run = run_history.add(name, status, seconds, fragments)
        if status == stats.UNKNOWN and self.result_matchers:
            with self._late_lock:  # its result may still show (the next run starts meanwhile)
                self.late_result = {"ended": time.perf_counter(), "index": len(self.session.runs) - 1,
                                    "run": self.last_run, "count": count, "window": self._late_window(name)}
        # saved after every run (on a helper thread, so the next run isn't held up): a crash or a power
        # cut loses no runs from the stats
        threading.Thread(target=run_history.save, daemon=True, name="save-runs").start()
        diag.info(f"Run {count} over ({how}): {status}, {seconds:.0f} s, {fragments} fragment(s)")
        self._run_finished(count, how)

    def _late_window(self, name):
        """(2.12) How long after an Unknown run its result may still show: 30 s, or half the usual run
        when runs are short (so a real short run isn't taken for the results screen)."""
        times = [s for st, s in self.session.runs if st in (stats.WIN, stats.LOSS)][-10:]
        if not times:
            times = [r["s"] for r in run_history.runs(name) if r.get("status") in ("win", "loss")][-10:]
        return late_results.window(times, core.LATE_RESULT_SECONDS)

    def _give_late_result(self, kind, now=None, late=None):
        """(2.12) A result showed: if the run before ended Unknown less than LATE_RESULT_SECONDS ago,
        the result is that run's. Returns True when it was given to it."""
        now = time.perf_counter() if now is None else now
        with self._late_lock:
            late = late or getattr(self, "late_result", None)
            if not late_results.due(late, kind, now, core.LATE_RESULT_SECONDS):
                return False
            late["given"] = True
        late_results.apply(self.session, late, kind)
        if late.get("run") is not None:
            run_history.correct(late["run"], kind)
            threading.Thread(target=run_history.save, daemon=True, name="save-runs").start()
        self.last_result_clock = self._play_clock()
        self._results_changed()
        diag.info(f"Late result: {self.RESULT_TITLES[kind]} showed {now - late['ended']:.0f} s after run "
                  f"{late['count']} ended: run {late['count']} counts as {kind} (it was unknown)")
        return True

    def _late_leftover(self, status, seconds, fragments):
        """(2.12) The run that just ended came right after an Unknown one. If the Unknown run's result
        showed in it (and went to that run) and it was short, it was only that results screen: it
        isn't counted, and its fragments go to the run before. Returns True when it isn't counted."""
        with self._late_lock:
            late = getattr(self, "late_result", None)
            self.late_result = None
        if not self.result_matchers or not late_results.is_leftover(late, seconds, core.LATE_RESULT_SECONDS):
            return False
        if not late.get("given") and not self._give_late_result(status, late=late):
            return False
        if late_results.add_fragments(self.session, late, fragments):
            if late.get("run") is not None:
                run_history.correct(late["run"], late["run"]["status"], fragments)
        diag.info(f"The short run after run {late['count']} ({seconds:.0f} s) isn't counted: it was only "
                  f"that run's results screen")
        self._run_finished(late["count"], "late")
        return True

    def _count_drops(self):
        """Divine fragments on the results screen now (counted by their pink-to-blue frame)."""
        if core.image_watch is None:
            return 0
        try:
            import drops

            # the drops always show in the OBTAINED row, under the result title: when the title was
            # found, only that part of the screen is taken and looked at (quicker, and nothing else
            # on screen can count)
            title = next((m.last_rect for m in list(self.result_matchers) if m.last_rect is not None), None)
            if title is not None:
                x, y, w, h = title
                # (the panel is about 1.4 times as wide as its title; a full OBTAINED row reaches its
                # sides, so a little more than the panel is taken)
                x0, x1 = max(0, int(x - 0.45 * w)), min(self.screen_w, int(x + 1.45 * w))
                y0, y1 = max(0, int(y + h)), min(self.screen_h, int(y + 14 * h))
                if x1 - x0 < 1 or y1 - y0 < 1:
                    return 0
                screen, origin = core.image_watch.grab_part(x0, y0, x1, y1)
                screen = self._hide_own_window(screen, origin)
            else:
                screen = self._hide_own_window(core.image_watch.grab_screen(), core.image_watch.screen_origin())
            count, _rects = drops.count_frames(screen, full_height=self.screen_h)
            if count:
                diag.info(f"Divine fragments on the results screen: {count}")
            return count
        except Exception as exc:
            diag.error("Couldn't count the drops", exc)
            return 0

    def _run_result(self, run_began, whole_screen=False):
        """"win", "loss" or "unknown" for the run that started at run_began (perf_counter time).
        whole_screen: look over the whole screen (else near where results showed before)."""
        st = self.result_state
        seen = [(t, kind) for kind, s in st.items() for t in s.get("appeared", []) if t >= run_began]
        if seen:
            return max(seen)[1]
        # not seen by the watcher yet: look at the screen once more, now
        try:
            need = self.settings.get("results_match", core.RESULTS_MATCH_DEFAULT) / 100.0
            # only around the spots where result pictures were seen before (about 0.01 s, so Retry
            # isn't held up); the whole screen only while no result picture was ever found
            whole = whole_screen or not any(self._kinds_found().values())
            region = None
            if not whole:
                areas = [m.near_last_area() for m in list(self.result_matchers) if m.last_rect is not None]
                region = (min(a[0] for a in areas), min(a[1] for a in areas),
                          max(a[2] for a in areas), max(a[3] for a in areas))
            screen = self._hide_own_window(core.image_watch.grab_screen(None, region), core.image_watch.screen_origin())
            best = self._result_scores(screen, need, whole=whole)
            if region is not None:
                self._unfound_kinds_in(screen, region, need, best)
            self.last_result_scores = dict(best)
            kind = self._best_result(best, need)
            since = st.get(kind, {}).get("since") if kind else None
            # (a picture already showing before this run started belongs to the run before; one given
            # to the Unknown run before, too)
            if kind and not st.get(kind, {}).get("given") and (since is None or since >= run_began):
                return kind
        except Exception as exc:
            diag.error("Couldn't check the result picture", exc)
        return stats.UNKNOWN

    def _unknown_reason(self, scores, need):
        """Why a run's result stayed unknown: the best score of each result picture against what it needs, and which
        of this app's own windows were blacked out of the screenshot (a banner under one can't match)."""
        if scores:
            seen = ", ".join(f"{self.RESULT_TITLES.get(k, k)} {round(v * 100)}%"
                             for k, v in sorted(scores.items(), key=lambda kv: -kv[1]))
            text = f"best match {seen} (needs {round(need * 100)}%)"
        else:
            text = f"no result picture was matched at the end of the run (needs {round(need * 100)}%)"
        blanked = ", ".join(f"{name} {rect}" for name, rect in own_windows.rects_by_name().items())
        return text + "; own windows blacked out of the screenshot: " + (blanked or "none")

    def _unfound_kinds_in(self, screen, region, need, best):
        """A kind never found yet (like MISSION FAILED) usually shows where the other one did: look
        for it in that same small part of the screen (every size: a small part, so it's quick).
        Adds its score to best (kind -> score)."""
        x0, y0 = max(0, region[0]), max(0, region[1])
        x1, y1 = max(x0, region[2]), max(y0, region[3])
        found = self._kinds_found()
        with self._result_lock:
            for m in list(self.result_matchers):
                if not found.get(m.kind) and x1 - x0 >= 8 and y1 - y0 >= 8:
                    score, _ = m.find(screen, good_enough=need, remember=False, area=(x0, y0, x1, y1))
                    best[m.kind] = max(best.get(m.kind, 0.0), score)
        return best

    def _kinds_found(self):
        """kind -> whether one of its pictures was found on screen yet (this playback)."""
        found = {}
        for m in list(self.result_matchers):
            found[m.kind] = found.get(m.kind, False) or m.last_rect is not None
        return found

    def _result_scores(self, screen, need, whole, every_size=True):
        with self._result_lock:
            return self._result_scores_now(screen, need, whole, every_size)

    def _result_scores_now(self, screen, need, whole, every_size=True):
        """every_size: a picture never found yet is looked for at all its sizes at once (the check at
        the end of a run). Otherwise (while playing) each look tries 3 other sizes, so all of them
        are covered every 5 looks without one look taking long."""
        """The best score of each kind ("win" / "loss") on a screenshot. Once a picture was found at
        one of its sizes, its other sizes aren't looked for any more (less work)."""
        scores = {}
        matchers = list(self.result_matchers)
        if whole:
            self.result_whole_checks = getattr(self, "result_whole_checks", 0) + 1
        for m in matchers:
            if m.last_rect is None and any(o is not m and o.picture_id == m.picture_id and o.last_rect is not None
                                           for o in matchers):
                continue
            if getattr(m, "fallback", False) and m.last_rect is None and \
                    getattr(self, "result_whole_checks", 0) % 6 != 5:
                continue  # the remembered size goes first; other sizes only every 6th look
            score, _ = m.find_near_last(screen, good_enough=need)
            if score < need and whole:
                # first the size it was found at before (and the ones next to it); while it was never
                # found yet, also every other size step: a title can show a few % bigger or smaller
                # than the picture, and then only matches at that exact size
                score, _ = m.find(screen, good_enough=need, quick=True)
                if score < need and m.last_rect is None:
                    main_size = getattr(m, "factor", 1.0) == (getattr(m, "picture", {}) or {}).get("found_factor", 1.0)
                    if every_size and main_size:  # (the other two sizes are covered by the watcher's turns)
                        score, _ = m.find(screen, good_enough=need)
                    elif not every_size:
                        turn = getattr(m, "size_turn", 0)
                        m.size_turn = turn + 1
                        steps = list(range(1, len(m.templates), 3))  # 1, 4, 7, ...: with their neighbours, all
                        remembered = m.last_best
                        m.last_best = steps[turn % len(steps)]
                        score, _ = m.find(screen, good_enough=need, quick=True)
                        if score < need:
                            m.last_best = remembered
            if score >= need and hasattr(m, "picture"):
                # remember this size for next time (saved with the pictures when playback ends)
                m.picture["found_factor"] = m.factor
                m.picture["found_step"] = m.last_best
                m.picture["found_screen"] = [self.screen_w, self.screen_h]
            scores[m.kind] = max(scores.get(m.kind, 0.0), score)
        if any(v >= need for v in scores.values()):
            # one result shows: before saying which, look properly (every size) for the kinds never
            # found yet, as a "failed" title can look a bit like a "completed" one
            for m in matchers:
                if m.last_rect is None and not getattr(m, "fallback", False) and \
                        not any(o.kind == m.kind and o.last_rect is not None for o in matchers):
                    score, _ = m.find(screen, good_enough=need, remember=False)  # (no lock-in on a look-alike)
                    scores[m.kind] = max(scores.get(m.kind, 0.0), score)
        return scores

    @staticmethod
    def _best_result(scores, need):
        kind = max(scores, key=scores.get) if scores else None
        return kind if kind and scores[kind] >= need else None

    def _result_worker(self, matchers, done):
        """While playing: notice when a "mission completed" or "mission failed" picture appears
        (about every 1.5 s). Each time one appears counts once, for the run that's going on."""
        need = self.settings.get("results_match", core.RESULTS_MATCH_DEFAULT) / 100.0
        window_tools.set_thread_priority(-1)  # never in the way of playback's timing
        checks = 0
        try:
            with core.image_watch.mss.mss() as sct:
                origin = core.image_watch.screen_origin(sct)
                while not done.is_set():
                    started = time.perf_counter()
                    # The whole screen is searched on every 4th look, and on every look while no
                    # result was ever found. Once one kind was found (MISSION COMPLETED), a kind not
                    # found yet (MISSION FAILED, if you rarely lose) is looked for where the other one
                    # showed, and the whole screen only every 8th look (it used to be every look).
                    kinds = self._kinds_found()
                    if not any(kinds.values()):
                        whole = True
                    elif all(kinds.values()):
                        whole = checks % 4 == 0
                    else:
                        whole = checks % 8 == 0
                    checks += 1
                    visible = {}
                    try:
                        region = None
                        if not whole:
                            # take only the parts of the screen around where results showed (a small
                            # box instead of the whole screen)
                            areas = [m.near_last_area() for m in list(matchers) if m.last_rect is not None]
                            if areas:
                                region = (min(a[0] for a in areas), min(a[1] for a in areas),
                                          max(a[2] for a in areas), max(a[3] for a in areas))
                        screen = self._hide_own_window(core.image_watch.grab_screen(sct, region), origin)
                        scores = self._result_scores(screen, need, whole, every_size=False)
                        if region is not None and not all(kinds.values()):
                            self._unfound_kinds_in(screen, region, need, scores)
                        best = self._best_result(scores, need)
                        # only the best-matching kind counts (a "failed" title can look a bit like a
                        # "completed" one)
                        visible = {kind: kind == best for kind in scores}
                    except Exception:
                        visible = {}
                    now = time.perf_counter()
                    for kind, on in visible.items():
                        s = self.result_state.setdefault(kind, {"since": None, "appeared": [], "first": True})
                        if on and s["since"] is None:
                            s["since"] = now
                            consumed = getattr(self, "result_consumed", None)
                            if consumed and consumed[0] == kind and now - consumed[1] < 15:
                                pass  # the run that just ended already counted this one
                            elif not s["first"]:  # (already showing when playing started: not this run's)
                                if self._give_late_result(kind, now):
                                    s["given"] = True  # (2.12) the Unknown run before's, shown late
                                else:
                                    s["appeared"].append(now)
                        elif not on and whole:
                            s["since"] = None
                            s["given"] = False
                        s["first"] = False
                    took = time.perf_counter() - started
                    self._note_look("results", took)
                    done.wait(max(0.5, 1.5 - took, took))
        except Exception as exc:
            diag.error("Result pictures: watching the screen failed", exc)

    def _results_changed(self):
        """A run's result changed after it ended (a late result). The dark window looks at the streak and
        the milestones again here."""
