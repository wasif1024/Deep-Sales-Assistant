"""Generate the README's illustrations from the real Chinook data.

    python3 docs/assets/make_readme_images.py docs/assets

Writes two static SVGs:
- territory-board.svg: the figures the territory-report playbook gathers for
  Jane (customers, revenue, yearly trend, genre mix, top customers) and the
  two writes the assistant pauses on for her approval.
- quote-preview.svg: a quote priced the way the rfq-quote playbook says
  (catalogue prices, 10% off at 50+ tracks) and the steps around it.

Every number is read from data/chinook.db when the script runs, so the
pictures stay true to the data. Rerun it if the database changes.
"""

from __future__ import annotations

import math
import sqlite3
import sys
from decimal import Decimal
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "chinook.db"
REP_ID = 3  # Jane Peacock

PAGE, CARD, BORDER = "#f5f3ff", "#ffffff", "#e7e3f6"
INK, MUTED, FAINT = "#1e1b4b", "#6b6890", "#a19ec0"
ACCENT, ACCENT_SOFT = "#7c3aed", "#ede9fe"
SIDEBAR_TOP, SIDEBAR_BOTTOM = "#6d28d9", "#8b5cf6"
OK, OK_SOFT, WAIT, WAIT_SOFT = "#16a34a", "#dcfce7", "#d97706", "#fef3c7"
SERIES = ["#7c3aed", "#3b82f6", "#ec4899", "#f97316", "#c4b5fd"]
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"


def text(x, y, s, size=12, fill=INK, weight=400, anchor="start", family=FONT):
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(str(s))}</text>'
    )


def rect(x, y, w, h, fill=CARD, r=12, stroke=BORDER, opacity=1.0):
    stroke_attr = f' stroke="{stroke}"' if stroke else ""
    opacity_attr = f' fill-opacity="{opacity}"' if opacity < 1 else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{opacity_attr}{stroke_attr}/>'


def chip(x, y, label, fg, bg, w=None, h=20, size=11):
    w = w or 8 + len(label) * 6.6
    return rect(x, y, w, h, bg, h / 2, None) + text(x + w / 2, y + h / 2 + size * 0.36, label, size, fg, 600, "middle")


def svg(w, h, parts, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-label="{escape(title)}"><title>{escape(title)}</title>'
        f'<defs><linearGradient id="side" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{SIDEBAR_TOP}"/><stop offset="1" stop-color="{SIDEBAR_BOTTOM}"/>'
        f"</linearGradient></defs>"
        f'{rect(0, 0, w, h, PAGE, 18, None)}{"".join(parts)}</svg>\n'
    )


def money(value) -> str:
    return f"${Decimal(str(value)):,.2f}"


# --- Data -------------------------------------------------------------------


def territory(conn):
    q = lambda sql: conn.execute(sql, (REP_ID,)).fetchall()  # noqa: E731
    customers = q("SELECT COUNT(*) FROM Customer WHERE SupportRepId = ?")[0][0]
    buyers, invoices, revenue = q(
        "SELECT COUNT(DISTINCT c.CustomerId), COUNT(*), ROUND(SUM(i.Total), 2) "
        "FROM Invoice i JOIN Customer c ON c.CustomerId = i.CustomerId WHERE c.SupportRepId = ?"
    )[0]
    years = q(
        "SELECT strftime('%Y', i.InvoiceDate), ROUND(SUM(i.Total), 2) FROM Invoice i "
        "JOIN Customer c ON c.CustomerId = i.CustomerId WHERE c.SupportRepId = ? GROUP BY 1 ORDER BY 1"
    )
    top = q(
        "SELECT c.FirstName || ' ' || c.LastName, c.Country, ROUND(SUM(i.Total), 2) AS rev "
        "FROM Customer c JOIN Invoice i ON i.CustomerId = c.CustomerId WHERE c.SupportRepId = ? "
        "GROUP BY c.CustomerId ORDER BY rev DESC, c.LastName LIMIT 5"
    )
    genres = q(
        "SELECT g.Name, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS rev FROM InvoiceLine il "
        "JOIN Invoice i ON i.InvoiceId = il.InvoiceId JOIN Customer c ON c.CustomerId = i.CustomerId "
        "JOIN Track t ON t.TrackId = il.TrackId JOIN Genre g ON g.GenreId = t.GenreId "
        "WHERE c.SupportRepId = ? GROUP BY g.Name ORDER BY rev DESC"
    )
    shown = genres[:4]
    other = round(sum(r for _, r in genres[4:]), 2)
    return {
        "customers": customers, "buyers": buyers, "invoices": invoices, "revenue": revenue,
        "years": years, "top": top, "genres": shown + [("Other genres", other)],
    }


QUOTE_FOR = ("Jennifer Peterson", "Rogers Canada")
QUOTE_LINES = [("Rock", 30), ("Metal", 30)]


def quote(conn):
    lines = []
    for genre, qty in QUOTE_LINES:
        (price,) = conn.execute(
            "SELECT DISTINCT t.UnitPrice FROM Track t JOIN Genre g ON g.GenreId = t.GenreId WHERE g.Name = ?",
            (genre,),
        ).fetchone()
        unit = Decimal(str(price))
        lines.append((f"{genre} tracks", qty, unit, unit * qty))
    subtotal = sum(line[3] for line in lines)
    tracks = sum(line[1] for line in lines)
    discount = (subtotal * Decimal("0.10")).quantize(Decimal("0.01")) if tracks >= 50 else Decimal(0)
    return {"lines": lines, "tracks": tracks, "subtotal": subtotal, "discount": discount, "total": subtotal - discount}


# --- Territory board --------------------------------------------------------


def sidebar(h):
    parts = [
        f'<rect x="0" y="0" width="200" height="{h}" rx="18" fill="url(#side)"/>',
        f'<rect x="182" y="0" width="18" height="{h}" fill="url(#side)"/>',
        '<circle cx="38" cy="44" r="18" fill="#ffffff" fill-opacity="0.22"/>',
        text(38, 49, "JP", 13, "#fff", 700, "middle"),
        text(64, 40, "Jane Peacock", 13, "#fff", 700),
        text(64, 56, "Sales Support Agent", 11, "#e9e3ff"),
        '<line x1="20" y1="80" x2="180" y2="80" stroke="#ffffff" stroke-opacity="0.25"/>',
        text(20, 106, "YOUR TEAM", 10, "#ddd6fe", 700),
    ]
    team = ["chinook-analyst", "inbox-manager", "quote-reviewer", "newsletter-agent"]
    for i, name in enumerate(team):
        y = 128 + i * 28
        parts.append(f'<circle cx="28" cy="{y - 4}" r="4" fill="#fff" fill-opacity="0.8"/>')
        parts.append(text(42, y, name, 12, "#fff", 500))
    parts.append(text(20, 258, "PLAYBOOKS", 10, "#ddd6fe", 700))
    playbooks = [("rfq-quote", False), ("territory-report", True), ("weekly-newsletter", False)]
    for i, (name, active) in enumerate(playbooks):
        y = 280 + i * 28
        if active:
            parts.append(rect(12, y - 18, 176, 26, "#ffffff", 8, None, 0.2))
        parts.append(text(28, y, name, 12, "#fff", 700 if active else 500))
    parts.append(text(20, h - 28, "You approve every write.", 11, "#ede9fe"))
    return parts


def territory_board(data):
    w, h = 960, 580
    parts = sidebar(h)
    x0, x_split, x1 = 224, 640, 936

    parts += [
        text(x0, 46, "Territory overview", 22, INK, 700),
        text(x0, 68, f"Jane's accounts (SupportRepId {REP_ID}), straight from data/chinook.db", 12, MUTED),
        chip(x1 - 128, 34, "territory-report", ACCENT, ACCENT_SOFT, 128),
    ]

    tiles = [
        ("Customers", str(data["customers"]), f"{data['buyers']} have purchased"),
        ("Lifetime revenue", money(data["revenue"]), "all invoices"),
        ("Invoices", str(data["invoices"]), f"{len(data['years'])} years of orders"),
        ("Average invoice", money(Decimal(str(data["revenue"])) / data["invoices"]), "per order"),
    ]
    tile_w = (x1 - x0 - 3 * 14) / 4
    for i, (label, value, sub) in enumerate(tiles):
        x = x0 + i * (tile_w + 14)
        parts += [
            rect(x, 88, tile_w, 82),
            f'<rect x="{x}" y="88" width="4" height="82" rx="2" fill="{SERIES[i]}"/>',
            text(x + 16, 112, label, 11, MUTED, 600),
            text(x + 16, 140, value, 22, INK, 700),
            text(x + 16, 158, sub, 10, FAINT),
        ]

    # Revenue by year
    parts += [rect(x0, 186, x_split - x0 - 16, 186), text(x0 + 16, 210, "Revenue by year", 13, INK, 700)]
    years = data["years"]
    top_rev = max(r for _, r in years)
    chart_left, chart_w, base = x0 + 28, x_split - x0 - 72, 344
    slot = chart_w / len(years)
    for f in (0.5, 1.0):
        y = base - 100 * f
        parts.append(f'<line x1="{chart_left}" y1="{y}" x2="{chart_left + chart_w}" y2="{y}" stroke="{BORDER}" stroke-dasharray="3 4"/>')
    for i, (year, rev) in enumerate(years):
        bar_h = 100 * rev / top_rev
        bx = chart_left + i * slot + slot * 0.25
        bw = slot * 0.5
        best = rev == top_rev
        parts += [
            f'<rect x="{bx:.1f}" y="{base - bar_h:.1f}" width="{bw:.1f}" height="{bar_h:.1f}" rx="6" fill="{ACCENT if best else "#c4b5fd"}"/>',
            text(bx + bw / 2, base - bar_h - 6, money(rev), 10, INK if best else MUTED, 600, "middle"),
            text(bx + bw / 2, base + 16, year, 11, MUTED, 500, "middle"),
        ]

    # Genre mix donut
    parts += [rect(x_split, 186, x1 - x_split, 186), text(x_split + 16, 210, "Genre mix", 13, INK, 700)]
    cx, cy, r, sw = x_split + 76, 292, 48, 20
    circumference = 2 * math.pi * r
    total = sum(v for _, v in data["genres"])
    start = 0.0
    for i, (name, value) in enumerate(data["genres"]):
        length = circumference * value / total
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{SERIES[i]}" stroke-width="{sw}" '
            f'stroke-dasharray="{length:.2f} {circumference - length:.2f}" stroke-dashoffset="{-start:.2f}" '
            f'transform="rotate(-90 {cx} {cy})"/>'
        )
        start += length
        ly = 246 + i * 22
        parts += [
            f'<rect x="{x_split + 146}" y="{ly - 9}" width="10" height="10" rx="3" fill="{SERIES[i]}"/>',
            text(x_split + 162, ly, name, 11, INK, 500),
            text(x1 - 14, ly, f"{100 * value / total:.0f}%", 11, MUTED, 600, "end"),
        ]
    parts.append(text(cx, cy + 5, money(total), 12, INK, 700, "middle"))

    # Top customers
    parts += [rect(x0, 388, x_split - x0 - 16, 176), text(x0 + 16, 412, "Top customers by revenue", 13, INK, 700)]
    col_country, col_rev = x0 + 230, x_split - 32
    parts += [
        text(x0 + 16, 434, "CUSTOMER", 10, FAINT, 700),
        text(col_country, 434, "COUNTRY", 10, FAINT, 700),
        text(col_rev, 434, "REVENUE", 10, FAINT, 700, "end"),
    ]
    for i, (name, country, rev) in enumerate(data["top"]):
        y = 458 + i * 22
        if i % 2 == 0:
            parts.append(rect(x0 + 8, y - 15, x_split - x0 - 32, 22, "#faf8ff", 6, None))
        parts += [
            text(x0 + 16, y, f"{i + 1}.  {name}", 12, INK, 500),
            text(col_country, y, country, 12, MUTED),
            text(col_rev, y, money(rev), 12, INK, 600, "end"),
        ]

    # Approvals
    parts += [rect(x_split, 388, x1 - x_split, 176), text(x_split + 16, 412, "Waiting for your approval", 13, INK, 700)]
    approvals = [
        ("add_customer", "Priya Raman, PulseFit Studios"),
        ("mail_create_draft", "Quote: 30 Rock + 30 Metal tracks"),
    ]
    for i, (tool, what) in enumerate(approvals):
        y = 426 + i * 66
        parts += [
            rect(x_split + 12, y, x1 - x_split - 24, 58, "#fffbeb", 10, "#fde68a"),
            text(x_split + 24, y + 19, tool, 11, WAIT, 700, family=MONO),
            text(x_split + 24, y + 36, what, 11, INK, 500),
        ]
        cx0 = x_split + 24
        for label, fg, bg, cw in (("Approve", OK, OK_SOFT, 58), ("Edit", ACCENT, ACCENT_SOFT, 38), ("Reject", "#b91c1c", "#fee2e2", 50)):
            parts.append(chip(cx0, y + 40, label, fg, bg, cw, h=14, size=9))
            cx0 += cw + 6

    return svg(w, h, parts, "Territory overview: the figures the territory-report playbook gathers for Jane")


# --- Quote preview ----------------------------------------------------------


def quote_preview(q):
    w, h = 960, 480
    name, company = QUOTE_FOR
    dx, dw = 32, 540
    parts = [
        rect(dx, 28, dw, h - 56),
        f'<rect x="{dx}" y="28" width="{dw}" height="8" rx="4" fill="{ACCENT}"/>',
        text(dx + 32, 86, "QUOTE", 34, INK, 800),
        text(dx + dw - 32, 70, "Chinook", 15, ACCENT, 700, "end"),
        text(dx + dw - 32, 88, "Online music store", 11, MUTED, 400, "end"),
        text(dx + 32, 120, "PREPARED FOR", 10, FAINT, 700),
        text(dx + 32, 138, f"{name}, {company}", 13, INK, 600),
        text(dx + dw - 32, 120, "FROM", 10, FAINT, 700, "end"),
        text(dx + dw - 32, 138, "Jane Peacock", 13, INK, 600, "end"),
    ]
    cols = (dx + 32, dx + 290, dx + 390, dx + dw - 32)
    parts.append(rect(dx + 20, 160, dw - 40, 30, ACCENT_SOFT, 8, None))
    for x, label, anchor in zip(cols, ("ITEM", "QTY", "UNIT PRICE", "LINE TOTAL"), ("start", "end", "end", "end")):
        parts.append(text(x, 180, label, 10, ACCENT, 700, anchor))
    y = 216
    for item, qty, unit, total in q["lines"]:
        parts += [
            text(cols[0], y, item, 13, INK, 500),
            text(cols[1], y, qty, 13, INK, 400, "end"),
            text(cols[2], y, money(unit), 13, INK, 400, "end"),
            text(cols[3], y, money(total), 13, INK, 600, "end"),
            f'<line x1="{dx + 20}" y1="{y + 12}" x2="{dx + dw - 20}" y2="{y + 12}" stroke="{BORDER}"/>',
        ]
        y += 34
    y += 6
    label_x = cols[2] - 10
    parts += [
        text(label_x, y, f"Subtotal ({q['tracks']} tracks)", 12, MUTED, 500, "end"),
        text(cols[3], y, money(q["subtotal"]), 12, INK, 500, "end"),
    ]
    if q["discount"]:
        y += 24
        parts += [
            text(label_x, y, "Volume discount (10%, 50+ tracks)", 12, OK, 600, "end"),
            text(cols[3], y, f"-{money(q['discount'])}", 12, OK, 600, "end"),
        ]
    y += 18
    parts += [
        rect(dx + 250, y, dw - 270, 40, ACCENT, 10, None),
        text(dx + 270, y + 26, "Total", 14, "#fff", 700),
        text(cols[3], y + 26, money(q["total"]), 18, "#fff", 800, "end"),
        text(dx + 32, h - 52, "Prices from data/chinook.db  ·  math by the code interpreter", 11, MUTED),
    ]

    # The steps around the quote
    sx, sw = dx + dw + 28, w - (dx + dw + 28) - 32
    parts.append(text(sx, 52, "How this quote was made", 15, INK, 700))
    steps = [
        ("done", "Prices looked up", "chinook-analyst runs query_chinook"),
        ("done", "Numbers double-checked", "quote-reviewer: \"Looks correct\""),
        ("wait", "Draft reply saved?", "Paused until Jane decides"),
    ]
    for i, (state, title, sub) in enumerate(steps):
        y = 72 + i * 82
        done = state == "done"
        parts += [
            rect(sx, y, sw, 68, CARD if done else "#fffbeb", 12, BORDER if done else "#fde68a"),
            f'<circle cx="{sx + 26}" cy="{y + 34}" r="12" fill="{OK_SOFT if done else WAIT_SOFT}"/>',
            text(sx + 26, y + 39, "✓" if done else "…", 13, OK if done else WAIT, 800, "middle"),
            text(sx + 48, y + 30, title, 13, INK, 700),
            text(sx + 48, y + 48, sub, 11, MUTED),
        ]
        if i < len(steps) - 1:
            parts.append(f'<line x1="{sx + 26}" y1="{y + 50}" x2="{sx + 26}" y2="{y + 82 + 18}" stroke="{BORDER}" stroke-width="2"/>')
    y = 72 + 2 * 82 + 76
    cx0 = sx + 48
    for label, fg, bg, cw in (("Approve", OK, OK_SOFT, 70), ("Edit", ACCENT, ACCENT_SOFT, 50), ("Reject", "#b91c1c", "#fee2e2", 62)):
        parts.append(chip(cx0, y, label, fg, bg, cw))
        cx0 += cw + 8

    ey = y + 40
    parts += [
        rect(sx, ey, sw, h - 28 - ey, ACCENT_SOFT, 12, None),
        text(sx + 16, ey + 24, "Checked in every evaluation run", 12, ACCENT, 700),
    ]
    for i, (name_, what) in enumerate((
        ("quote_accuracy", "total matches the database"),
        ("tool_call_order", "reviewed before the draft"),
        ("draft_quality", "LLM judge: the reply checklist"),
    )):
        yy = ey + 46 + i * 20
        parts += [text(sx + 16, yy, name_, 11, INK, 700, family=MONO), text(sx + 136, yy, what, 11, MUTED)]

    return svg(w, h, parts, f"A quote for {name}: {money(q['total'])}, reviewed and waiting for Jane's approval")


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent)
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        (out / "territory-board.svg").write_text(territory_board(territory(conn)))
        (out / "quote-preview.svg").write_text(quote_preview(quote(conn)))
    finally:
        conn.close()
    print(f"Wrote territory-board.svg and quote-preview.svg to {out}")


if __name__ == "__main__":
    main()
