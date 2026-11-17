"""Show my clicks (2.11): a picture of the screen with the macro's clicks drawn on it as numbered dots
and its mouse moves as thin lines, one action (part) at a time or all together. Clicking a dot chooses
that action in the Edit window. The screenshot is only shown: it's never saved or sent anywhere."""
import base64
import tkinter as tk
from tkinter import ttk

import macro_steps as workflow
from ui_common import *  # noqa: F401,F403

MAX_W, MAX_H = 1100, 640
MAX_PATH_POINTS = 300  # a long mouse path is drawn with at most this many points


def parts(steps):
    """[(step id, step name, [("click", x, y, n) / ("path", [(x, y), ...])])] for every action that
    has spots on the screen, in playing order. Clicks are numbered across the whole macro."""
    out = []
    n = 0
    for a, _l, _i, _p in workflow.walk(steps):
        if a.get("off"):
            continue
        kind = a.get("kind")
        marks = []
        if kind == "recorded":
            path = []
            for ev in a.get("events", []):
                t = ev.get("type")
                if t == "move" and "x" in ev:
                    path.append((ev["x"], ev["y"]))
                elif t == "click" and ev.get("pressed") and "x" in ev:
                    n += 1
                    marks.append(("click", ev["x"], ev["y"], n))
                    path.append((ev["x"], ev["y"]))
            if len(path) == 1:  # (a single move still shows, as a point)
                marks.insert(0, ("path", path * 2))
            elif len(path) > 1:
                step = max(1, -(-len(path) // MAX_PATH_POINTS))  # (rounded up)
                marks.insert(0, ("path", path[::step] + [path[-1]]))
        elif kind == "click":
            n += 1
            marks.append(("click", a.get("x", 0), a.get("y", 0), n))
        elif kind == "move":
            marks.append(("path", [(a.get("x", 0), a.get("y", 0))] * 2))
        if marks:
            out.append((a.get("id"), workflow.describe(a)[0], marks))
    return out


def open_clicks(editor, steps=None, owner=None):
    """The Show my clicks window for what the Edit window shows now (or for some steps only, e.g. the
    chosen rows of "Edit the recorded events…", shown over `owner`)."""
    app = editor.app
    owner = owner or editor.win
    screen_size, program = editor._macro_fit()
    play_on = (app.screen_w, app.screen_h)
    source = steps if steps is not None else editor.steps
    try:
        steps, _note = app._fit_steps(workflow.snapshot(source), screen_size, program, play_on)
    except Exception:
        steps = source
    found = parts(steps)
    if not found:
        app.boxes.showinfo("Show my clicks", "There are no clicks or mouse moves to show.", parent=owner)
        return None
    # a picture of the screen without this app's windows on it (only shown here, never kept)
    shown = [w for w in (owner, editor.win, app.root) if w.winfo_exists() and w.state() != "withdrawn"]
    for w in shown:
        w.withdraw()
    app.root.update()
    app.root.after(250)
    try:
        import image_watch

        shot = image_watch.grab_screen()
        origin = image_watch.screen_origin()
    except Exception:
        shot, origin = None, (0, 0)
    finally:
        for w in shown:
            w.deiconify()
    win = tk.Toplevel(owner, bg=BG)
    win.title("Show my clicks")
    win.transient(owner)
    win.resizable(False, False)
    dark_title_bar(win)
    sw, sh = (shot.shape[1], shot.shape[0]) if shot is not None else play_on
    scale = min(MAX_W / sw, MAX_H / sh, 1.0)
    cw, ch = int(sw * scale), int(sh * scale)
    canvas = tk.Canvas(win, width=cw, height=ch, bg=FIELD, highlightthickness=0)
    canvas.pack(padx=12, pady=(12, 6))
    if shot is not None:
        try:
            import cv2

            small = cv2.resize(shot, (cw, ch), interpolation=cv2.INTER_AREA)
            ok, png = cv2.imencode(".png", small)
            if ok:
                win.photo = tk.PhotoImage(data=base64.b64encode(png.tobytes()))
                canvas.create_image(0, 0, image=win.photo, anchor="nw")
        except Exception:
            pass
    del shot  # (only the small picture on the canvas stays, until the window closes)
    bar = tk.Frame(win, bg=BG)
    bar.pack(fill="x", padx=12, pady=(0, 12))
    label = tk.Label(bar, text="", bg=BG, fg=TEXT, font=F_BASE, anchor="w")
    view = {"k": -1}  # -1 = every part

    def xy(x, y):
        return (x - origin[0]) * scale, (y - origin[1]) * scale

    def draw():
        canvas.delete("mark")
        k = view["k"]
        chosen = found if k < 0 else [found[k]]
        for sid, _name, marks in chosen:
            for m in marks:
                if m[0] == "path" and len(m[1]) > 1:
                    pts = [c for p in m[1] for c in xy(*p)]
                    canvas.create_line(*pts, fill=ACCENT, width=1, tags="mark")
            for m in marks:
                if m[0] == "click":
                    cx, cy = xy(m[1], m[2])
                    tag = ("mark", "dot", "step:" + str(sid))
                    canvas.create_oval(cx - 8, cy - 8, cx + 8, cy + 8, fill=RED, outline="white", width=1, tags=tag)
                    canvas.create_text(cx, cy, text=str(m[3]), fill="white", font=(FAMILY, 7, "bold"), tags=tag)
        if k < 0:
            label.config(text=f"All {len(found)} part{'s' if len(found) != 1 else ''}  ·  red dots are clicks, "
                              "in order; blue lines are mouse moves. Click a dot to choose its action.")
        else:
            label.config(text=f"Part {k + 1} of {len(found)}: {found[k][1]}")

    def step(d):
        view["k"] = (view["k"] + d + 1) % (len(found) + 1) - 1
        draw()

    def clicked(e):
        for item in canvas.find_overlapping(e.x - 2, e.y - 2, e.x + 2, e.y + 2)[::-1]:
            for tag in canvas.gettags(item):
                if tag.startswith("step:"):
                    sid = tag[5:]
                    if editor.tree.exists(sid):
                        editor.tree.selection_set(sid)
                        editor.tree.see(sid)
                        editor._step_clicked()
                        editor.win.lift()
                    return
    canvas.tag_bind("dot", "<Button-1>", clicked)
    canvas.tag_bind("dot", "<Enter>", lambda e: canvas.config(cursor="hand2"))
    canvas.tag_bind("dot", "<Leave>", lambda e: canvas.config(cursor=""))
    ttk.Button(bar, text="◀", width=3, command=lambda: step(-1)).pack(side="left")
    ttk.Button(bar, text="▶", width=3, command=lambda: step(1)).pack(side="left", padx=(4, 10))
    label.pack(side="left", fill="x", expand=True)
    ttk.Button(bar, text="Close", command=win.destroy).pack(side="right")
    tk.Label(win, text="The picture of your screen is only shown here: it isn't saved or sent anywhere.",
             bg=BG, fg=DIM, font=F_SMALL, anchor="w").pack(fill="x", padx=12, pady=(0, 10))
    draw()
    win.found, win.view, win.step, win.canvas = found, view, step, canvas
    return win
