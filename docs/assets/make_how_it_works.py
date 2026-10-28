"""Generate docs/assets/how-it-works.svg (run: python3 docs/assets/make_how_it_works.py docs/assets/how-it-works.svg): an animated (CSS) diagram of the
async newsletter + sandbox flow. Pass --static to render every element visible
(for previewing the layout)."""

import sys

STATIC = "--static" in sys.argv
OUT = sys.argv[1]
T = 22  # loop length, seconds
W, H = 960, 560

BG, PANEL, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, MUTED = "#e6edf3", "#8b949e"
USER, AGENT = "#1f6feb", "#21262d"
ACCENT, ASYNC, SANDBOX, OK = "#a371f7", "#d29922", "#3fb950", "#3fb950"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

css: list[str] = []
body: list[str] = []
_n = 0


def pct(t: float) -> str:
    return f"{min(max(t / T * 100, 0), 100):.2f}%"


def anim(start: float, end: float = T - 1.2, fade: float = 0.35) -> str:
    """Class name for an element visible from `start` to `end` (seconds)."""
    global _n
    _n += 1
    name = f"a{_n}"
    css.append(
        f"@keyframes {name}{{0%,{pct(start)}{{opacity:0}}"
        f"{pct(start + fade)},{pct(end)}{{opacity:1}}"
        f"{pct(end + fade)},100%{{opacity:0}}}}"
        f".{name}{{opacity:0;animation:{name} {T}s linear infinite}}"
    )
    return name


def grow(start: float, end: float) -> str:
    """Class for a progress bar that fills from `start` to `end`."""
    global _n
    _n += 1
    name = f"g{_n}"
    css.append(
        f"@keyframes {name}{{0%,{pct(start)}{{transform:scaleX(0)}}"
        f"{pct(end)},{pct(T - 1.2)}{{transform:scaleX(1)}}"
        f"{pct(T - 0.8)},100%{{transform:scaleX(0)}}}}"
        f".{name}{{transform-box:fill-box;transform-origin:left;"
        f"transform:scaleX(0);animation:{name} {T}s linear infinite}}"
    )
    return name


def g(cls: str, inner: str) -> None:
    body.append(f'<g class="{cls}">{inner}</g>')


def text(x, y, s, size=13, fill=TEXT, weight=400, anchor="start", mono=False):
    fam = MONO if mono else FONT
    return (f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{s}</text>')


def rect(x, y, w, h, fill, stroke="none", r=10, sw=1, extra=""):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')


def arrow(d, color, label=None, lx=0, ly=0):
    s = (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.5" '
         f'stroke-dasharray="7 6" class="flow" marker-end="url(#head-{color[1:]})"/>')
    if label:
        s += text(lx, ly, label, 10.5, color, 600, "middle", mono=True)
    return s


# ── Static frame ────────────────────────────────────────────────────────────
body.append(rect(0, 0, W, H, BG, r=16))
body.append(text(W / 2, 34, "How Deep Sales Assistant works: background tasks + a sandbox per thread",
                 16, TEXT, 600, "middle"))

# Panels
COLS = [(20, "Chat UI", "Jane"), (340, "LangGraph server", "localhost:2024"),
        (660, "LangSmith sandbox", "thread-7f3c…")]
for x, title, sub in COLS:
    body.append(rect(x, 56, 280, 484, PANEL, BORDER, r=12))
    body.append(text(x + 16, 82, title, 14, TEXT, 600))
    body.append(text(x + 264, 82, sub, 11.5, MUTED, 400, "end", mono=True))
    body.append(f'<line x1="{x}" y1="94" x2="{x + 280}" y2="94" stroke="{BORDER}"/>')

# Server: main agent + newsletter agent boxes
MAIN = (360, 110, 240, 92)
NEWS = (360, 300, 240, 220)
body.append(rect(*MAIN, "#1c2128", ACCENT, sw=1.5))
body.append(text(480, 140, "Main agent", 14, TEXT, 600, "middle"))
body.append(text(480, 160, "plans · delegates · follows skills", 11.5, MUTED, 400, "middle"))
body.append(text(480, 184, "analyst · inbox · reviewer", 11.5, MUTED, 400, "middle", mono=True))

body.append(rect(*NEWS, "#1c2128", ASYNC, sw=1.5))
body.append(text(376, 328, "newsletter-agent", 14, TEXT, 600))
body.append(text(376, 347, "separate run · own thread · parallel research", 11.5, MUTED))

GENRES = ["Rock", "Latin", "Jazz", "Classical"]
for i, genre in enumerate(GENRES):
    y = 372 + i * 34
    body.append(text(378, y + 14, f"researcher · {genre}", 11.5, TEXT, 400, mono=True))
    body.append(rect(378, y + 20, 204, 6, "#30363d", r=3))

# Sandbox: terminal + files
body.append(rect(676, 108, 248, 128, "#010409", BORDER, r=8))
body.append(text(690, 128, "$ execute", 11.5, MUTED, 400, mono=True))
body.append(text(676, 266, "/outputs/", 12.5, TEXT, 600, mono=True))
body.append(f'<line x1="676" y1="276" x2="924" y2="276" stroke="{BORDER}"/>')

# ── Timeline ────────────────────────────────────────────────────────────────
BUBBLES = [  # (time, who, text)
    (0.6, "user", "Create this week's newsletter"),
    (2.6, "agent", "Started in the background ✓"),
    (4.2, "user", "Meanwhile, a territory report?"),
    (9.0, "agent", "Report + chart saved to /outputs"),
    (14.4, "user", "Is the newsletter ready?"),
    (17.2, "agent", "Yes! Saved newsletter.html ✓"),
]
for i, (t, who, msg) in enumerate(BUBBLES):
    y = 110 + i * 66
    if who == "user":
        inner = rect(80, y, 204, 40, USER, r=14) + text(270, y + 25, msg, 12.5, "#fff", 500, "end")
        inner += text(284, y + 54, "Jane", 10.5, MUTED, 400, "end")
    else:
        inner = rect(36, y, 224, 40, AGENT, BORDER, r=14) + text(50, y + 25, msg, 12.5, TEXT)
        inner += text(36, y + 54, "assistant", 10.5, MUTED)
    g(anim(t), inner)

# 1. start_async_task: main -> newsletter
g(anim(1.4, 3.6), arrow("M492 204 L492 296", ASYNC, "start_async_task", 549, 256))
g(anim(1.6, 16.4), rect(360, 300, 240, 220, "none", ASYNC, sw=3, extra='class="pulse"'))
g(anim(1.6, 13.4), text(588, 328, "running", 11, ASYNC, 600, "end", mono=True))

# Parallel research
ends = [11.2, 12.6, 10.4, 13.2]
for i, end in enumerate(ends):
    y = 372 + i * 34
    body.append(f'<g class="{grow(2.2 + i * 0.2, end)}">{rect(378, y + 20, 204, 6, ASYNC, r=3)}</g>')
    g(anim(end + 0.2), text(582, y + 14, "✓", 12, OK, 700, "end"))
g(anim(13.6, 16.4), text(588, 328, "success", 11, OK, 600, "end", mono=True))

# 2. Territory report in the sandbox (while research runs)
g(anim(5.0, 8.4), arrow("M602 156 L672 156", SANDBOX, "write_file", 637, 146))
g(anim(5.0, 20.8), rect(360, 110, 240, 92, "none", SANDBOX, sw=3, extra='class="pulse"'))
TERM = [
    (5.6, "$ write_file /outputs/chart.py"),
    (6.4, "$ pip install matplotlib"),
    (7.4, "$ python3 /outputs/chart.py"),
    (8.2, "  saved territory_chart.png"),
]
for i, (t, line) in enumerate(TERM):
    color = OK if line.startswith("  ") else TEXT
    g(anim(t), text(690, 150 + i * 20, line, 11.5, color, 400, mono=True))

FILES = [
    (8.0, "territory_report.md", SANDBOX),
    (8.4, "territory_chart.png", SANDBOX),
    (16.6, "newsletter-…-a1b2.html", ASYNC),
]
for i, (t, name, color) in enumerate(FILES):
    y = 290 + i * 38
    g(anim(t), rect(676, y, 248, 30, "#1c2128", color, r=8)
      + text(690, y + 20, "▪ " + name, 12, TEXT, mono=True))

# 3. check_async_task: result flows back, main writes the file
g(anim(15.0, 16.6), arrow("M455 296 L455 206", OK, "check_async_task", 400, 256))
g(anim(16.2, 17.6), arrow("M602 180 C 640 180, 640 368, 672 368", ASYNC))

# Legend
body.append(text(W / 2, 553, "Background research runs in parallel while the main agent keeps working in its sandbox.",
                 12, MUTED, 400, "middle"))

SHOW_ALL = "[class^=a],[class^=g]{opacity:1!important;transform:none!important;animation:none!important}"

# ── Assemble ────────────────────────────────────────────────────────────────
heads = "".join(
    f'<marker id="head-{c[1:]}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" '
    f'markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10z" fill="{c}"/></marker>'
    for c in (ASYNC, SANDBOX, OK)
)
base_css = (
    "@keyframes dash{to{stroke-dashoffset:-26}}.flow{animation:dash .8s linear infinite}"
    "@keyframes pulse{50%{stroke-opacity:.25}}.pulse{animation:pulse 1.4s ease-in-out infinite}"
    "@media (prefers-reduced-motion:reduce){" + SHOW_ALL + "}"
)
style = base_css + "".join(css)
if STATIC:
    style += SHOW_ALL

svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
    f'role="img" aria-label="Animated diagram: the main agent starts the newsletter agent in the '
    f'background, keeps working in its LangSmith sandbox, then collects the finished newsletter.">'
    f"<title>How Deep Sales Assistant works</title>"
    f"<defs>{heads}</defs><style>{style}</style>{''.join(body)}</svg>"
)
open(OUT, "w", encoding="utf-8").write(svg)
print(f"wrote {OUT} ({len(svg) / 1024:.1f} KB)")
