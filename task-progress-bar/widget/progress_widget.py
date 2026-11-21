"""Floating Claude progress widget, warm look (Claude design template).

Reads one JSON file per session in STATE_DIR, written by the
task-progress-bar mod. One row per working session, kept green for a moment
after it finishes. Rounded dark card, coral accent.
Frameless, draggable, one copy at a time.
"""

import glob
import json
import math
import os
import sys
import time
import tkinter as tk

CLAUDE_HOME = os.path.join(os.path.expanduser("~"), ".claude")
STATE_DIR = os.path.join(CLAUDE_HOME, "task-progress")
if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
    STATE_DIR = sys.argv[1]

FRESH_MS = 5000
SHOW_DONE_MS = 15000
CLEANUP_MS = 2 * 24 * 3600 * 1000
DEFAULT_STEP_MS = 20000

# Claude design template (dark surfaces, coral primary)
KEY = "#010203"          # made transparent: gives the card rounded corners
CARD = "#1f1e1b"         # surface-dark-soft
EDGE = "#33302b"         # hairline on dark (dividers, resize grip)
BORDER = "#5c574e"       # card outline: soft, but findable on any background
TRACK = "#2e2b27"
INK = "#faf9f5"          # on-dark
SOFT = "#a09d96"         # on-dark-soft
CORAL = "#cc785c"        # primary
CORAL_HI = "#e8a58c"     # gloss highlight
SUCCESS = "#5db872"

TITLE = "Claude progress"
W = 320
PAD = 16
RADIUS = 14
BAR_H = 6
HEADER_H = 40
ROW_H = 62
EMPTY_H = 34
MAX_ROWS = 8

GRIP = 18                # corner area that resizes, at scale 1
MIN_SCALE, MAX_SCALE = 0.75, 2.0
# After Claude's computer control last minimized us, stay invisible to
# screenshots and click-through this long.
CONTROL_QUIET_S = 60
ERROR_LOG = os.path.join(CLAUDE_HOME, "task-progress-widget.log")
# Where the Claude desktop app keeps its session files (titles live there):
# %LOCALAPPDATA%\Claude-Data\claude_<account>\claude-code-sessions
APP_SESSIONS_GLOB = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                 "Claude-Data", "claude_*",
                                 "claude-code-sessions")
TITLE_REFRESH_S = 10
SETTINGS_FILE = os.path.join(CLAUDE_HOME, "task-progress-widget.json")

SERIF = ("Georgia", 11)
SANS = "Segoe UI"


def fmt_eta(ms: float) -> str:
    s = max(0, int(ms / 1000))
    if s < 2:
        return "almost done"
    if s < 60:
        return f"~{s}s left"
    m, r = divmod(s, 60)
    return f"~{m}m {r:02d}s left"


def clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "\u2026"


def mix(a: str, b: str, t: float) -> str:
    """Blend two #rrggbb colors; t=0 gives a, t=1 gives b."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def already_running() -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    k32 = ctypes.windll.kernel32
    u32 = ctypes.windll.user32
    k32.CreateMutexW.restype = ctypes.c_void_p
    main.mutex = k32.CreateMutexW(None, False, "Local\\ClaudeProgressWidget")
    if k32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
        return False
    hwnd = u32.FindWindowW(None, TITLE)
    if hwnd:
        u32.ShowWindow(hwnd, 9)
        u32.SetForegroundWindow(hwnd)
    return True


_titles = {"at": 0.0, "map": {}}


def session_titles() -> dict:
    """Session id -> title, from the Claude app's own session files.

    The app keeps one JSON file per session (local_*.json) with its title and
    the id the mod writes under (cliSessionId). This is the app's private
    format, so anything missing just means falling back to the request text.
    Re-read at most every TITLE_REFRESH_S seconds.
    """
    now = time.time()
    if now - _titles["at"] < TITLE_REFRESH_S:
        return _titles["map"]
    _titles["at"] = now
    found = {}
    walks = (w for top in glob.glob(APP_SESSIONS_GLOB) for w in os.walk(top))
    for dirpath, _dirs, files in walks:
        for name in files:
            if not (name.startswith("local_") and name.endswith(".json")):
                continue
            try:
                with open(os.path.join(dirpath, name), "r",
                          encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                continue
            title = str(d.get("title") or "").strip()
            if not title:
                continue
            for key in ("cliSessionId", "lastAssistantCliSessionId"):
                sid = d.get(key)
                if sid:
                    found[str(sid)] = title
    _titles["map"] = found
    return found


def load_sessions(now_ms: float) -> list:
    rows = []
    try:
        names = os.listdir(STATE_DIR)
    except OSError:
        return rows
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(STATE_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        ts = int(d.get("ts", 0) or 0)
        age = now_ms - ts
        if age > CLEANUP_MS:
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        working = bool(d.get("running")) and age < FRESH_MS
        started = int(d.get("stepStartedAt", 0) or 0)
        finished = not working and started > 0 and age < SHOW_DONE_MS
        if not (working or finished):
            continue
        rows.append({
            "working": working,
            "total": int(d.get("total", 0) or 0),
            "completed": int(d.get("completed", 0) or 0),
            "label": str(d.get("label", "") or ""),
            "prompt": str(d.get("prompt", "") or ""),
            "title": session_titles().get(name[:-5], ""),
            "started": started,
            "avg": float(d.get("avgStepMs", 0) or 0) or DEFAULT_STEP_MS,
            "id": name,
        })
    rows.sort(key=lambda r: r["id"])
    return rows[:MAX_ROWS]


def round_rect(c: tk.Canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


def pill(c: tk.Canvas, x1, y, x2, h, color):
    """A bar with round ends from x1 to x2, centered on y."""
    if x2 - x1 < h:
        x2 = x1 + h
    c.create_line(x1 + h / 2, y, x2 - h / 2, y, width=h, fill=color,
                  capstyle=tk.ROUND)


def load_scale() -> float:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            v = float(json.load(f).get("scale", 1.0))
        return max(MIN_SCALE, min(MAX_SCALE, v))
    except (OSError, ValueError, TypeError, AttributeError):
        return 1.0


def save_scale(v: float) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({"scale": round(v, 3)}, f)
    except OSError:
        pass


def main() -> None:
    if already_running():
        return
    root = tk.Tk()
    root.title(TITLE)
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=KEY)
    try:
        root.attributes("-transparentcolor", KEY)
    except tk.TclError:
        pass

    # Everything is laid out at scale 1 and multiplied by z["k"], so text,
    # bars and spacing all grow and shrink together.
    z = {"k": load_scale()}

    def s(v: float) -> float:
        return v * z["k"]

    def font(size: float, *style: str) -> tuple:
        return (SANS, max(6, round(size * z["k"])), *style)

    def width() -> int:
        return round(W * z["k"])

    sw = root.winfo_screenwidth()
    root.geometry(f"{width()}x{round(s(HEADER_H + EMPTY_H))}"
                  f"+{max(0, sw - width() - 24)}+48")

    canvas = tk.Canvas(root, bg=KEY, highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    state = {"h": 0, "mode": "", "x": 0, "y": 0, "redraw": False}

    def on_grip(e: "tk.Event") -> bool:
        return e.x >= width() - s(GRIP) and e.y >= state["h"] - s(GRIP)

    def set_scale(v: float) -> None:
        v = max(MIN_SCALE, min(MAX_SCALE, v))
        if abs(v - z["k"]) > 0.001:
            z["k"] = v
            state["h"] = 0  # force a resize on the next draw
            draw()

    def press(e: "tk.Event") -> None:
        if e.x >= width() - s(34) and e.y <= s(HEADER_H):
            root.destroy()
            return
        state["mode"] = "resize" if on_grip(e) else "move"
        state["x"], state["y"] = e.x, e.y

    def motion(e: "tk.Event") -> None:
        if state["mode"] == "resize":
            set_scale((root.winfo_pointerx() - root.winfo_rootx()) / W)
        elif state["mode"] == "move":
            root.geometry(f"+{root.winfo_pointerx() - state['x']}"
                          f"+{root.winfo_pointery() - state['y']}")

    def release(_e: "tk.Event") -> None:
        if state["mode"] == "resize":
            save_scale(z["k"])
        state["mode"] = ""

    def hover(e: "tk.Event") -> None:
        canvas.config(cursor="size_nw_se" if on_grip(e) else "")

    def wheel(e: "tk.Event") -> None:
        set_scale(z["k"] + (0.1 if e.delta > 0 else -0.1))
        save_scale(z["k"])

    canvas.bind("<Button-1>", press)
    canvas.bind("<B1-Motion>", motion)
    canvas.bind("<ButtonRelease-1>", release)
    canvas.bind("<Motion>", hover)
    canvas.bind("<Control-MouseWheel>", wheel)

    def draw_row(y: float, r: dict, now_ms: float) -> None:
        total, completed = r["total"], r["completed"]
        elapsed = (now_ms - r["started"]) if r["started"] > 0 else 0
        pad, bar_w, bar_h = s(PAD), s(W - 2 * PAD), s(BAR_H)
        w = width()

        # Status dot: breathing coral while working, green when done.
        cy = y + s(11)
        if r["working"]:
            t = (math.sin(now_ms / 260.0) + 1) / 2
            rad = s(3 + 1.2 * t)
            cx = pad + s(3)
            canvas.create_oval(cx - rad, cy - rad, cx + rad, cy + rad,
                               fill=mix(CARD, CORAL, 0.55 + 0.45 * t), width=0)
        else:
            canvas.create_oval(pad, cy - s(3.5), pad + s(7), cy + s(3.5),
                               fill=SUCCESS, width=0)

        # The session's title as the app shows it; the request text if the
        # app's files don't have one.
        name = r["title"] or r["prompt"] or "(untitled session)"
        canvas.create_text(pad + s(14), cy, text=clip(name, 38), fill=INK,
                           anchor="w", font=font(9))

        by = y + s(30)
        pill(canvas, pad, by, pad + bar_w, bar_h, TRACK)

        if not r["working"]:
            pill(canvas, pad, by, pad + bar_w, bar_h, SUCCESS)
            right, right_c = "done", SUCCESS
            info, info_c = "Finished", SUCCESS
        elif total == 0:
            seg = bar_w / 4
            phase = (now_ms % 2400) / 1200.0
            pos = phase if phase <= 1 else 2 - phase
            # ease in/out so it glides instead of bouncing
            pos = 0.5 - 0.5 * math.cos(pos * math.pi)
            left = pad + (bar_w - seg) * pos
            pill(canvas, left, by, left + seg, bar_h, CORAL)
            right, right_c = f"{int(elapsed / 1000)}s", SOFT
            info, info_c = "Working, no task list", SOFT
        else:
            avg = r["avg"]
            within = max(0.0, min(0.95, elapsed / avg)) if avg > 0 else 0.0
            frac = min(1.0, (completed + within) / total)
            fill_x = pad + max(bar_h, bar_w * frac)
            pill(canvas, pad, by, fill_x, bar_h, CORAL)
            # Soft highlight drifting across the filled part.
            span = fill_x - pad - bar_h
            if span > s(24):
                gx = pad + bar_h / 2 + ((now_ms % 1600) / 1600.0) * span
                for k, gw in enumerate((18, 10, 4)):
                    col = mix(CORAL, CORAL_HI, (k + 1) / 3)
                    a = max(pad + bar_h / 2, gx - s(gw) / 2)
                    b = min(fill_x - bar_h / 2, gx + s(gw) / 2)
                    if b > a:
                        canvas.create_line(a, by, b, by,
                                           width=max(1, bar_h - s(2)),
                                           fill=col, capstyle=tk.ROUND)
            right, right_c = f"{int(frac * 100)}%", CORAL
            eta = fmt_eta(avg * (total - completed) - elapsed)
            step = f"  \u00b7  {r['label']}" if r["label"] else ""
            info = clip(f"{completed} of {total}  \u00b7  {eta}{step}", 50)
            info_c = SOFT

        canvas.create_text(w - pad, cy, text=right, fill=right_c, anchor="e",
                           font=font(9, "bold"))
        canvas.create_text(pad, by + s(15), text=info, fill=info_c,
                           anchor="w", font=font(8))

    def draw() -> int:
        """Draw everything once; returns how many sessions are working."""
        now_ms = time.time() * 1000
        rows = load_sessions(now_ms)
        w = width()
        pad = s(PAD)

        h = round(s(HEADER_H + (len(rows) * ROW_H if rows else EMPTY_H) + 6))
        if h != state["h"]:
            state["h"] = h
            root.geometry(f"{w}x{h}")

        canvas.delete("all")
        # Card with a 1px soft warm border.
        round_rect(canvas, 0, 0, w - 1, h - 1, s(RADIUS), fill=BORDER,
                   outline="")
        round_rect(canvas, 1, 1, w - 2, h - 2, s(RADIUS) - 1, fill=CARD,
                   outline="")

        working = sum(1 for r in rows if r["working"])
        canvas.create_text(pad, s(21), text="Claude", fill=INK, anchor="w",
                           font=(SERIF[0], max(7, round(SERIF[1] * z["k"]))))
        sub = f"{working} working" if working else ("idle" if not rows else "")
        if sub:
            canvas.create_text(pad + s(60), s(22), text=sub, fill=SOFT,
                               anchor="w", font=font(8))
        canvas.create_text(w - pad - s(2), s(21), text="\u2715", fill=SOFT,
                           font=font(9))
        canvas.create_line(pad, s(HEADER_H - 2), w - pad, s(HEADER_H - 2),
                           fill=EDGE)

        if not rows:
            canvas.create_text(pad, s(HEADER_H + 14), text="Nothing running",
                               fill=SOFT, anchor="w", font=font(8))
        for i, r in enumerate(rows):
            y = s(HEADER_H + 4 + i * ROW_H)
            if i:
                canvas.create_line(pad, y - s(4), w - pad, y - s(4),
                                   fill=TRACK)
            draw_row(y, r, now_ms)

        # Resize grip: three short diagonal strokes in the bottom-right corner.
        gx, gy = w - s(6), h - s(6)
        for n in (4, 8, 12):
            canvas.create_line(gx - s(n), gy, gx, gy - s(n), fill=EDGE,
                               width=max(1, s(1.2)))
        return working

    # Claude's computer control minimizes every window it wasn't given, this
    # one included, and leaves it minimized. Our window can't be minimized any
    # other way (it has no title bar or taskbar button), so a minimize means
    # Claude is controlling the screen: come straight back, but hidden from
    # screenshots and letting clicks pass through, so Claude never sees or
    # clicks it. Back to normal once no minimize has happened for a while.
    ctl = {"top": 0, "until": 0.0, "on": False}

    def guard() -> None:
        if sys.platform != "win32":
            return
        import ctypes
        u32 = ctypes.windll.user32
        vp = ctypes.c_void_p
        if not ctl["top"]:
            u32.FindWindowW.restype = vp
            u32.GetWindowThreadProcessId.argtypes = [vp, vp]
            for fn in ("IsIconic", "IsWindowVisible"):
                getattr(u32, fn).argtypes = [vp]
            u32.ShowWindow.argtypes = [vp, ctypes.c_int]
            u32.SetWindowDisplayAffinity.argtypes = [vp, ctypes.c_uint]
            u32.GetWindowLongW.argtypes = [vp, ctypes.c_int]
            u32.SetWindowLongW.argtypes = [vp, ctypes.c_int, ctypes.c_long]
            u32.SetWindowPos.argtypes = [vp, vp, ctypes.c_int, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_int,
                                         ctypes.c_uint]
            # The widget's real window: the titled "TkTopLevel" one in this
            # process. Tk keeps another, hidden helper window; never touch it.
            top = u32.FindWindowW(None, TITLE)
            pid = ctypes.c_ulong()
            if top:
                u32.GetWindowThreadProcessId(top, ctypes.byref(pid))
            if not top or pid.value != os.getpid():
                return  # not created yet; try again next tick
            ctl["top"] = top
        top = ctl["top"]
        now = time.time()
        if u32.IsIconic(top):
            ctl["until"] = now + CONTROL_QUIET_S
            if not ctl["on"]:
                ctl["on"] = True
                u32.SetWindowDisplayAffinity(top, 0x11)  # hide from capture
                ex = u32.GetWindowLongW(top, -20)
                # click-through (needs layered, which it already is)
                u32.SetWindowLongW(top, -20, ex | 0x20 | 0x80000)
            u32.ShowWindow(top, 4)  # SW_SHOWNOACTIVATE: back, no focus steal
            # HWND_TOPMOST, without moving, resizing or taking focus
            u32.SetWindowPos(top, vp(-1), 0, 0, 0, 0, 0x13)
        elif ctl["on"] and now > ctl["until"]:
            ctl["on"] = False
            u32.SetWindowDisplayAffinity(top, 0)
            ex = u32.GetWindowLongW(top, -20)
            u32.SetWindowLongW(top, -20, ex & ~0x20)

    def refresh() -> None:
        try:
            guard()
        except Exception as ex:  # never let this stop the widget drawing
            if not ctl.get("logged"):
                ctl["logged"] = True
                try:
                    with open(ERROR_LOG, "a", encoding="utf-8") as f:
                        f.write(f"{time.ctime()} guard: {ex!r}\n")
                except OSError:
                    pass
        working = draw()
        root.after(50 if working or state["mode"] else 500, refresh)

    refresh()
    root.mainloop()


if __name__ == "__main__":
    main()
