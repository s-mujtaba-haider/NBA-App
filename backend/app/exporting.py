"""CSV and PDF exports: a day's picks, the bet history, and the track-record report."""
from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd

from . import record, slate
from .markets import BOOKS, MARKETS, ORDER, RULE_OF_RECORD


def _pct(x) -> str:
    return "" if x is None else f"{x * 100:+.1f}%"


def _price(p) -> str:
    return f"{int(p):+d}"


def picks_frame(day: str) -> pd.DataFrame:
    rows = slate.board(day)["picks"]
    cols = ["slate", "label", "away", "home", "who", "side", "point", "book", "price", "p_win", "breakeven", "ev", "confidence", "state", "profit"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


def bets_frame(market: str | None = None, season: str | None = None) -> pd.DataFrame:
    d = record.all_bets(True)
    if market:
        d = d[d.market == market]
    if season:
        d = d[d.season == season]
    return d.sort_values(["slate", "market"])[["slate", "season", "market", "who", "side", "point", "book", "price", "dec", "ev", "p_win", "result", "profit", "source"]]


def to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# ---------------------------------------------------------------- PDF
def _doc(title: str):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=title, author="Baseline", creator="Baseline", subject="NBA market picks")
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=20, alignment=0, spaceAfter=4, textColor=colors.HexColor("#0B0D10"))
    sub = ParagraphStyle("s", parent=ss["Normal"], fontSize=9, textColor=colors.HexColor("#5B6470"))
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=9, leading=12)

    def table(data, widths=None):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B0D10")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#C8F560")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F5F7")]),
            ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#D5DAE0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t

    return buf, doc, dict(h=h, sub=sub, body=body), table, Paragraph, Spacer, mm


def picks_pdf(day: str) -> bytes:
    buf, doc, st, table, P, S, mm = _doc(f"Baseline picks {day}")
    rows = slate.board(day)["picks"]
    story = [P(f"Picks for {day}", st["h"]),
             P(f"Six WINNER markets, frozen rules, best price across 8 books at pick time. Generated "
               f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.", st["sub"]), S(1, 6 * mm)]
    data = [["Market", "Game", "Selection", "Book", "Price", "Win prob", "Break-even", "Edge (EV)", "Grade", "Result"]]
    for r in rows:
        sel = r["who"] + " " if r["kind"] == "prop" else ""
        sel += r["side"].upper() + (f" {r['point']:g}" if r["point"] is not None else "")
        res = "pending" if r["state"] != "graded" else ("WON" if r["result"] > 0 else "LOST" if r["result"] < 0 else "PUSH")
        data.append([r["label"], f"{r['away']} @ {r['home']}", sel, BOOKS.get(r["book"], r["book"]), _price(r["price"]),
                     f"{(r['p_win'] or 0) * 100:.1f}%", f"{r['breakeven'] * 100:.1f}%", _pct(r["ev"]), r["confidence"], res])
    if len(data) == 1:
        data.append(["No picks logged for this day yet", "", "", "", "", "", "", "", "", ""])
    story.append(table(data))
    story += [S(1, 6 * mm), P("Flat 1 unit per pick. Picks are made before tip and never changed. Past results do not guarantee future results.", st["sub"])]
    doc.build(story)
    return buf.getvalue()


def report_pdf() -> bytes:
    buf, doc, st, table, P, S, mm = _doc("Baseline track record")
    s = record.summary()
    t = s["totals"]
    story = [P("Track record: six WINNER markets", st["h"]),
             P(f"Rule of record: {RULE_OF_RECORD['name']}: {RULE_OF_RECORD['definition']}.", st["sub"]), S(1, 5 * mm)]
    s25 = t["season_2025_26"]
    story.append(P(f"<b>2025-26 (unseen season):</b> {s25['bets']:,} bets, {s25['units']:+.1f} units, ROI {_pct(s25['roi'])}, "
                   f"{s25['months_profit']} of {s25['months']} months in profit, worst drop {s25['worst_drop']:.1f} units. "
                   f"<b>2026-27 live:</b> {t['live']['bets']} bets, {t['live']['units']:+.1f} units, ROI {_pct(t['live']['roi'])} "
                   f"(through {t['live_last_slate']}).", st["body"]))
    story.append(S(1, 5 * mm))
    data = [["Market", "Window", "Bets (2 seasons)", "ROI", "95% CI low", "2025-26 bets", "2025-26 ROI", "Live bets", "Live ROI", "Status"]]
    for m in s["markets"]:
        two, s5, lv = m["two_season"], m["season_2025_26"], m["live"]
        data.append([m["label"], m["window"], f"{two['bets']:,}", _pct(two["roi"]), _pct(two["ci_low"]), f"{s5['bets']:,}", _pct(s5["roi"]),
                     str(lv["bets"]), _pct(lv["roi"]), m["status"]])
    story.append(table(data))
    story.append(S(1, 5 * mm))
    mo = pd.DataFrame(record.monthly(False)["rows"])
    mo = mo[mo.month >= "2025-10"].pivot_table(index="month", columns="market", values="units", aggfunc="sum").fillna(0)
    data = [["Month"] + [MARKETS[m]["short"] for m in ORDER if m in mo.columns] + ["Total"]]
    for k, r in mo.iterrows():
        data.append([k] + [f"{r[m]:+.1f}" for m in ORDER if m in mo.columns] + [f"{r.sum():+.1f}"])
    story += [P("<b>Units by month, 2025-26</b>", st["body"]), S(1, 2 * mm), table(data), S(1, 5 * mm)]
    story += [P("<b>Disclosure</b>", st["body"])] + [P("- " + x, st["sub"]) for x in RULE_OF_RECORD["disclosure"]]
    doc.build(story)
    return buf.getvalue()
