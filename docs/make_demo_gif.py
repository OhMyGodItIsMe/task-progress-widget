"""Draws the README animation (docs/demo.gif) from scratch, no screen capture.

Same layout, colors and fonts as the widget (dark theme), with four made-up
sessions on a timeline that loops seamlessly every LOOP seconds. Needs Pillow
and the Windows fonts Georgia and Segoe UI.

usage: python docs/make_demo_gif.py docs/demo.gif
"""
import math
import sys

from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 else "demo.gif"
SCALE = 1.5      # final size: widget at 150%
SS = 3           # supersampling for smooth edges and text
FPS = 12
LOOP = 20.0      # seconds; every cycle below divides it

K = SCALE * SS


def s(v):
    return v * K


# Widget constants (progress_widget.py), dark theme
W, PAD, RADIUS, BAR_H, HEADER_H, ROW_H = 320, 16, 14, 6, 40, 62
CARD, BORDER, EDGE, TRACK = "#1f1e1b", "#5c574e", "#33302b", "#2e2b27"
INK, SOFT, CORAL, CORAL_HI = "#faf9f5", "#a09d96", "#cc785c", "#e8a58c"
SUCCESS, AMBER = "#5db872", "#e8a55a"
PT = 96 / 72  # tk point sizes -> pixels at 96 dpi


def font(name, pt):
    return ImageFont.truetype(f"C:/Windows/Fonts/{name}", round(pt * PT * K))


F_TITLE = font("georgia.ttf", 11)
F_NAME, F_RIGHT, F_SMALL = font("segoeui.ttf", 9), font("segoeuib.ttf", 9), font("segoeui.ttf", 8)


def mix(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def fmt_eta(ms):
    sec = max(0, int(ms / 1000))
    if sec < 2:
        return "almost done"
    if sec < 60:
        return f"~{sec}s left"
    m, r = divmod(sec, 60)
    return f"~{m}m {r:02d}s left"


def clip(text, n):
    return text if len(text) <= n else text[: n - 1] + "\u2026"


# Made-up sessions. Each runs its steps, may pause for a permission prompt
# after `wait_after` steps, shows "done" for `hold` seconds, then restarts.
SESSIONS = [
    dict(title="Refactor login page", steps=4, per=4.0, hold=4.0, off=3.0,
         labels=["Read current form", "Split components", "Add validation", "Run tests"]),
    dict(title="Clean up old build files", steps=3, per=2.5, hold=5.0, off=0.0,
         wait_after=2, wait=7.5, labels=["Find old builds", "List what to delete", "Delete dist folder"]),
    dict(title="Fix flaky CI test", cli=True, steps=5, per=3.2, hold=4.0, off=11.0,
         labels=["Reproduce locally", "Find race condition", "Patch", "Re-run CI", "Clean up"]),
    dict(title="Write weekly blog post", steps=3, per=2.5, hold=2.5, off=7.0,
         labels=["Outline", "Draft sections", "Proofread"]),
]
for x in SESSIONS:
    cycle = x["steps"] * x["per"] + x.get("wait", 0) + x["hold"]
    assert abs(LOOP / cycle - round(LOOP / cycle)) < 1e-9, x["title"]


def state(x, t):
    cycle = x["steps"] * x["per"] + x.get("wait", 0) + x["hold"]
    el = (t + x["off"]) % cycle
    wa = x.get("wait_after")
    if wa is not None:
        start_wait = wa * x["per"]
        if start_wait <= el < start_wait + x["wait"]:
            return dict(x, status="waiting", completed=wa)
        if el >= start_wait + x["wait"]:
            el -= x["wait"]
    if el >= x["steps"] * x["per"]:
        return dict(x, status="finished")
    done = int(el // x["per"])
    return dict(x, status="working", completed=done, elapsed=el - done * x["per"])


def pill(d, x1, y, x2, h, color):
    if x2 - x1 < h:
        x2 = x1 + h
    d.rounded_rectangle((x1, y - h / 2, x2, y + h / 2), radius=h / 2, fill=color)


def frame(t):
    rows = [state(x, t) for x in SESSIONS]
    w, h = s(W), s(HEADER_H + len(rows) * ROW_H + 6)
    img = Image.new("RGBA", (round(w), round(h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    one = s(1) / SCALE
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=s(RADIUS), fill=BORDER)
    d.rounded_rectangle((one, one, w - 1 - one, h - 1 - one), radius=s(RADIUS) - one, fill=CARD)
    pad, bar_w, bar_h = s(PAD), s(W - 2 * PAD), s(BAR_H)

    working = sum(r["status"] == "working" for r in rows)
    waiting = sum(r["status"] == "waiting" for r in rows)
    parts = [f"{working} working"] + ([f"{waiting} needs you"] if waiting else [])
    d.text((pad, s(21)), "Claude", font=F_TITLE, fill=INK, anchor="lm")
    d.text((pad + s(60), s(22)), "  \u00b7  ".join(parts), font=F_SMALL, fill=SOFT, anchor="lm")
    xc, yc, xr = w - pad - s(2), s(21), s(4.5)  # close button: an x drawn as two lines
    for sx in (1, -1):
        d.line((xc - xr, yc - sx * xr, xc + xr, yc + sx * xr), fill=SOFT, width=max(1, round(s(1.2))))
    d.line((pad, s(HEADER_H - 2), w - pad, s(HEADER_H - 2)), fill=EDGE, width=max(1, round(K)))

    for i, r in enumerate(rows):
        y = s(HEADER_H + 4 + i * ROW_H)
        if i:
            d.line((pad, y - s(4), w - pad, y - s(4)), fill=TRACK, width=max(1, round(K)))
        cy, by = y + s(11), y + s(30)
        st = r["status"]
        if st == "finished":
            d.ellipse((pad, cy - s(3.5), pad + s(7), cy + s(3.5)), fill=SUCCESS)
        else:
            amber = st == "waiting"
            b = (math.sin(t * 2 * math.pi / (4.0 if amber else 2.0)) + 1) / 2  # breathing dot
            rad, cx = s(3 + 1.2 * b), pad + s(3)
            d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad),
                      fill=mix(CARD, AMBER if amber else CORAL, 0.55 + 0.45 * b))
        name = ("\u203a " if r.get("cli") else "") + r["title"]
        d.text((pad + s(14), cy), clip(name, 34), font=F_NAME, fill=INK, anchor="lm")
        pill(d, pad, by, pad + bar_w, bar_h, TRACK)

        if st == "finished":
            pill(d, pad, by, pad + bar_w, bar_h, SUCCESS)
            right, right_c, info, info_c = "done", SUCCESS, "Finished", SUCCESS
        elif st == "waiting":
            frac = r["completed"] / r["steps"]
            pill(d, pad, by, pad + max(bar_h, bar_w * frac), bar_h, AMBER)
            right, right_c, info, info_c = "needs you", AMBER, "Waiting for your permission", AMBER
        else:
            total, done, el, avg = r["steps"], r["completed"], r["elapsed"] * 1000, r["per"] * 1000
            frac = min(1.0, (done + max(0.0, min(0.95, el / avg))) / total)
            fill_x = pad + max(bar_h, bar_w * frac)
            pill(d, pad, by, fill_x, bar_h, CORAL)
            span = fill_x - pad - bar_h
            if span > s(24):
                gx = pad + bar_h / 2 + ((t % 2.0) / 2.0) * span  # gloss, 2 s period
                for k, gw in enumerate((18, 10, 4)):
                    a = max(pad + bar_h / 2, gx - s(gw) / 2)
                    b2 = min(fill_x - bar_h / 2, gx + s(gw) / 2)
                    if b2 > a:
                        pill(d, a - (bar_h - s(2)) / 2, by, b2 + (bar_h - s(2)) / 2, bar_h - s(2),
                             mix(CORAL, CORAL_HI, (k + 1) / 3))
            right, right_c = f"{int(frac * 100)}%", CORAL
            eta = fmt_eta(avg * (total - done) - el)
            info = clip(f"{done} of {total}  \u00b7  {eta}  \u00b7  {r['labels'][done]}", 50)
            info_c = SOFT
        d.text((w - pad, cy), right, font=F_RIGHT, fill=right_c, anchor="rm")
        d.text((pad, by + s(15)), info, font=F_SMALL, fill=info_c, anchor="lm")

    return img.resize((round(w / SS), round(h / SS)), Image.LANCZOS)


raw = [frame(n / FPS) for n in range(int(LOOP * FPS))]
# One shared palette (from a strip of sample frames), so unchanged pixels stay
# identical between frames and compress away.
sample = Image.new("RGB", (raw[0].width, raw[0].height * 6))
for j, n in enumerate(range(0, len(raw), len(raw) // 6)[:6]):
    sample.paste(raw[n].convert("RGB"), (0, raw[0].height * j))
pal_img = sample.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
pal_img.putpalette(pal_img.getpalette()[:255 * 3] + [0, 0, 0])

frames = []
for rgba in raw:
    alpha = rgba.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
    p = rgba.convert("RGB").quantize(palette=pal_img, dither=Image.Dither.NONE)
    p.paste(255, mask=Image.eval(alpha, lambda v: 255 - v))  # index 255 = transparent
    frames.append(p)

frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=round(1000 / FPS),
               loop=0, transparency=255, disposal=1, optimize=True)
print(f"{len(frames)} frames, {frames[0].size[0]}x{frames[0].size[1]} -> {OUT}")
