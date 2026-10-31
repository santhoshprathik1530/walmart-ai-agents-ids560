"""Rebuild the AI-agent section (slides 34-43) of the midterm deck in the style of slides 1-33.

Usage:  python3 build_ai_agent_section.py "<source deck>.pptx" "<output deck>.pptx"

Keeps slides 1-33 and the demo / tech stack / thank-you slides untouched; replaces the six old AI-agent slides
(34-39) with ten new ones. Every number and every answer comes from app/data/agent_outputs.json, written by the live agents (app/agents/export_outputs.py).
Style: Inter, cream F9F8F4 background, white cards with CBD5E1 border, 0052CC blue, slate text (as slides 24-33).
"""
import copy
import json
import re
import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.enum.dml import MSO_LINE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).resolve().parent
ICONS, LOGOS = HERE / "assets" / "icons", HERE / "assets" / "logos"
OUT = json.loads((HERE.parent.parent / "app" / "data" / "agent_outputs.json").read_text())   # real agent runs: python3 -m agents.export_outputs
CASES = {c["store"]: c for c in OUT["cases"].values()}
VS = OUT["vector_store"]
LL = OUT["llm"]                                     # LLM writer stats from the export run

FONT = "Inter"
BG, INK, SLATE, MUTED, GREY, LINE = "F9F8F4", "0F172A", "334155", "475569", "64748B", "CBD5E1"
TINT, TINTLINE, BLUE = "F0F5FF", "BFDBFE", "0052CC"
RED, DRED, GREEN, AMBER = "DC2626", "991B1B", "16A34A", "D97706"
WHITE = "FFFFFF"
TYPE_STYLE = {"Direct structured evidence": ("DBEAFE", BLUE), "Inferred mapping": ("EDE9FE", "6D28D9"),
              "Walmart-level context": ("E2E8F0", INK), "Regional / macro context": ("FEF3C7", "B45309")}


def rgb(h):
    return RGBColor.from_string(h)


# ------------------------------------------------------------------------------------------ helpers
def new_slide(prs, layout):
    s = prs.slides.add_slide(layout)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = rgb(BG)
    return s


def _runs(par, text, size, color, bold, font=FONT, italic=False):
    """Add runs to a paragraph; **text** is bold."""
    for i, seg in enumerate(re.split(r"\*\*", text)):
        if not seg:
            continue
        r = par.add_run()
        r.text = seg
        f = r.font
        f.name, f.size, f.italic = font, Pt(size), italic
        f.bold = bold or (i % 2 == 1)
        f.color.rgb = rgb(INK if (i % 2 == 1 and not bold and color in (SLATE, MUTED, GREY)) else color)


def tb(slide, x, y, w, h, paras, size=10, color=SLATE, bold=False, align="l", anchor="t", spacing=1.0,
       after=0, name=None, italic=False):
    """Text box with zero padding. paras: str or list of str / dict(t, size, color, bold, after, align)."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        box.name = name
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    if isinstance(paras, str):
        paras = [paras]
    for i, p in enumerate(paras):
        d = p if isinstance(p, dict) else {"t": p}
        par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        par.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[d.get("align", align)]
        par.line_spacing = d.get("spacing", spacing)
        par.space_after = Pt(d.get("after", after))
        _runs(par, d["t"], d.get("size", size), d.get("color", color), d.get("bold", bold), italic=d.get("italic", italic))
    return box


def card(slide, x, y, w, h, fill=WHITE, line=LINE, radius=0.045, name=None, lw=0.56, dash=False):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.adjustments[0] = min(0.5, radius * 2 / min(w, h)) if min(w, h) else 0.05
    shp.fill.solid()
    shp.fill.fore_color.rgb = rgb(fill)
    if line:
        shp.line.color.rgb = rgb(line)
        shp.line.width = Pt(lw)
        if dash:
            shp.line.dash_style = MSO_LINE.DASH
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    if name:
        shp.name = name
    return shp


def label_card(slide, x, y, w, h, text, fill, color, size=9, bold=True, radius=0.04, align="c", line=None):
    c = card(slide, x, y, w, h, fill=fill, line=line, radius=radius)
    tf = c.text_frame
    tf.margin_left = tf.margin_right = Inches(0.06)
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.word_wrap = True
    par = tf.paragraphs[0]
    par.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER}[align]
    _runs(par, text, size, color, bold)
    return c


def icon(slide, key, color, x, y, size, tile=TINT, tile_line=None):
    """Icon in a rounded tile (same treatment as slide 25)."""
    t = card(slide, x, y, size, size, fill=tile, line=tile_line, radius=size * 0.22)
    pad = size * 0.24
    slide.shapes.add_picture(str(ICONS / f"{key}_{color}.png"), Inches(x + pad), Inches(y + pad),
                             Inches(size - 2 * pad), Inches(size - 2 * pad))
    return t


def badge(slide, n, x, y, d=0.28, fill=BLUE, color=WHITE, size=10):
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    c.fill.solid()
    c.fill.fore_color.rgb = rgb(fill)
    c.line.fill.background()
    c.shadow.inherit = False
    tf = c.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    _runs(p, str(n), size, color, True)
    return c


def arrow(slide, x1, y1, x2, y2, color=BLUE, w=1.25, dash=False, head=True):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(w)
    if dash:
        c.line.dash_style = MSO_LINE.DASH
    if head:
        ln = c.line._get_or_add_ln()
        tail = etree.SubElement(ln, qn("a:tailEnd"))
        tail.set("type", "triangle")
        tail.set("w", "med")
        tail.set("len", "med")
    return c


def frame(slide, eyebrow, title, subtitle, foot_left, foot_right):
    """Eyebrow, title, subtitle and footer, positioned as on slides 24-33."""
    tb(slide, 0.5, 0.36, 9.0, 0.16, eyebrow.upper(), size=8, color=BLUE, bold=True, name="Eyebrow")
    tb(slide, 0.5, 0.54, 9.0, 0.34, title, size=18, color=INK, bold=True, name="Title")
    tb(slide, 0.5, 0.92, 9.0, 0.2, subtitle, size=10, color=MUTED, name="Subtitle")
    ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(0.5), Inches(5.08), Inches(9.5), Inches(5.08))
    ln.line.color.rgb = rgb(LINE)
    ln.line.width = Pt(0.56)
    tb(slide, 0.5, 5.15, 6.2, 0.2, foot_left, size=8, color=GREY, name="Footer note")
    tb(slide, 6.2, 5.15, 3.3, 0.2, foot_right, size=8, color=BLUE, bold=True, align="r", name="Footer tag")


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


# ---- tables
def _border(cell, side, color=None, w=0.75):
    tcPr = cell._tc.get_or_add_tcPr()
    tag = {"b": "a:lnB", "t": "a:lnT", "l": "a:lnL", "r": "a:lnR"}[side]
    for old in tcPr.findall(qn(tag)):
        tcPr.remove(old)
    ln = etree.SubElement(tcPr, qn(tag))
    if color:
        ln.set("w", str(int(Pt(w))))
        sf = etree.SubElement(ln, qn("a:solidFill"))
        etree.SubElement(sf, qn("a:srgbClr")).set("val", color)
    else:
        ln.set("w", "0")
        etree.SubElement(ln, qn("a:noFill"))
    # borders must precede the fill element in tcPr
    fills = [e for e in tcPr if e.tag in (qn("a:solidFill"), qn("a:noFill"))]
    for f in fills:
        tcPr.remove(f)
        tcPr.append(f)


def table(slide, x, y, widths, rows, header, row_h, size=9, head_size=8.5, name=None, head_h=0.28, col_styles=None):
    """rows: list of lists of str. col_styles: {col: callable(cell_text)->(fill, color, bold)}."""
    n = len(rows) + 1
    gf = slide.shapes.add_table(n, len(widths), Inches(x), Inches(y), Inches(sum(widths)),
                                Inches(head_h + row_h * len(rows)))
    if name:
        gf.name = name
    tbl = gf.table
    tblPr = gf._element.graphic.graphicData.tbl.tblPr
    for a in ("firstRow", "bandRow"):
        tblPr.set(a, "0")
    sid = tblPr.find(qn("a:tableStyleId"))
    if sid is None:
        sid = etree.SubElement(tblPr, qn("a:tableStyleId"))
    sid.text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"  # no style, no grid
    for i, wd in enumerate(widths):
        tbl.columns[i].width = Inches(wd)
    tbl.rows[0].height = Inches(head_h)
    for r in range(1, n):
        tbl.rows[r].height = Inches(row_h)
    for c, h in enumerate(header):
        cell = tbl.cell(0, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = rgb(BLUE)
        cell.margin_left = cell.margin_right = Inches(0.07)
        cell.margin_top = cell.margin_bottom = Inches(0.02)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = cell.text_frame.paragraphs[0]
        _runs(p, h, head_size, WHITE, True)
        for s in "tblr":
            _border(cell, s)
    for r, row in enumerate(rows, start=1):
        for c, txt in enumerate(row):
            cell = tbl.cell(r, c)
            fill, color, bold = WHITE, SLATE, False
            if col_styles and c in col_styles:
                fill, color, bold = col_styles[c](txt)
            elif c == 0:
                color, bold = INK, True
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(fill)
            cell.margin_left = cell.margin_right = Inches(0.07)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.text_frame.word_wrap = True
            _runs(cell.text_frame.paragraphs[0], txt, size, color, bold)
            for s in "tlr":
                _border(cell, s)
            _border(cell, "b", LINE, 0.75)
    return gf


# ------------------------------------------------------------------------------------------ reusable pieces
def tile(s, x, y, w, h, big, label, color=BLUE, fill=WHITE, big_size=17):
    card(s, x, y, w, h, fill=fill)
    tb(s, x + 0.1, y + 0.07, w - 0.2, h * 0.5, big, size=big_size, color=color, bold=True, anchor="m")
    tb(s, x + 0.1, y + h * 0.55, w - 0.2, h * 0.42, label, size=8, color=MUTED, spacing=1.0)


def strategy_card(s, x, y, w, h, steps, tsize=9.5, bsize=8.5):
    """Numbered strategy steps in one card: (title, text) rows."""
    card(s, x, y, w, h, name="Strategy")
    tb(s, x + 0.15, y + 0.08, w - 0.3, 0.18, "STRATEGY", size=8, color=BLUE, bold=True)
    row = (h - 0.36) / len(steps)
    for i, (title, text) in enumerate(steps):
        yy = y + 0.34 + i * row
        badge(s, i + 1, x + 0.15, yy + 0.02, d=0.24, size=8.5)
        tb(s, x + 0.5, yy, w - 0.65, row - 0.04, [{"t": title, "size": tsize, "color": INK, "bold": True, "after": 1},
                                                  {"t": text, "size": bsize, "color": MUTED}], spacing=1.02)


def numbers_label(s, x, y, text="IN NUMBERS"):
    tb(s, x, y, 3.0, 0.18, text, size=8, color=BLUE, bold=True)


def fmt(n):
    return f"{n:,}"


# ------------------------------------------------------------------------------------------ slides
def s_why(prs, lay):
    s = new_slide(prs, lay)
    frame(s, "AI Agent · Why it matters", "Why an AI Agent, Not Just a Dashboard",
          "A dashboard shows what happened. Analysts still need to know why.",
          "The agent does not replace the analyst. It does the first round of investigation, live in our dashboard.", "AI Agent Workstream · Motivation")
    left = [("chart", "Shows Store 7 Electronics down 24.6%"), ("search", "Analyst searches reports manually"),
            ("help", "No sense of how reliable a number is"), ("list", "Raw numbers only")]
    right = [("down", "Checks if the drop is a one-off or a pattern, and how other stores did"),
             ("book", "Searches 59 Walmart, Federal Reserve and NRF reports from the same quarter and region"),
             ("tag", "Tags every claim with its evidence type and confidence, and checks its own numbers and quotes"),
             ("scale", "Weighs possible explanations and recommends a review")]
    label_card(s, 0.5, 1.42, 3.95, 0.32, "DASHBOARD ALONE", "E2E8F0", MUTED, size=8.5, align="l")
    label_card(s, 5.05, 1.42, 4.45, 0.32, "WITH THE AI AGENTS", BLUE, WHITE, size=8.5, align="l")
    for i, ((ik, lt), (ik2, rt)) in enumerate(zip(left, right)):
        y = 1.86 + i * 0.7
        card(s, 0.5, y, 3.95, 0.58, name=f"Dashboard row {i+1}")
        icon(s, ik, "slate", 0.62, y + 0.1, 0.38, tile="F1F5F9")
        tb(s, 1.12, y, 3.2, 0.58, lt, size=10.5, color=MUTED, anchor="m")
        arrow(s, 4.55, y + 0.29, 4.95, y + 0.29, color=BLUE)
        card(s, 5.05, y, 4.45, 0.58, name=f"Agent row {i+1}")
        icon(s, ik2, "blue", 5.17, y + 0.1, 0.38)
        tb(s, 5.67, y, 3.7, 0.58, rt, size=10, color=INK, anchor="m")
    card(s, 0.5, 4.62, 9.0, 0.38, fill=TINT, line=TINTLINE)
    tb(s, 0.65, 4.62, 5.7, 0.38, "**Same flag, two different answers.** The agents ran on three real exceptions: one needs review, two are explained.",
       size=9, color=SLATE, anchor="m")
    label_card(s, 6.45, 4.69, 1.6, 0.24, "Store 7: Needs review", "FEE2E2", DRED, size=7.5)
    label_card(s, 8.12, 4.69, 1.3, 0.24, "Store 2: Explained", "DCFCE7", "166534", size=7.5)
    notes(s, "A dashboard can tell us that Electronics in Store 7 dropped 24.6 percent. It cannot tell us whether that is unusual, how other stores did, or what Walmart and the Federal Reserve were reporting that quarter. "
             "Our agents do that first round of investigation, live. They check whether the drop is a one-off, how other stores did, search 59 original reports from the same quarter and region, tag every claim with its evidence type and confidence, and check their own numbers and quotes. "
             "The agent does not always find a problem. On the three real exceptions we ran, one needs review and two are explained by timing. The agent does not replace the analyst. It lets the analyst start from evidence.")
    return s


def s_sources(prs, lay):
    s = new_slide(prs, lay)
    pt = VS["per_type"]
    wr = pt["earnings_release"]["files"] + pt["comp_sales"]["files"], pt["earnings_release"]["chunks"] + pt["comp_sales"]["chunks"]
    tk = pt["10k"]["files"] + pt["annual_report"]["files"], pt["10k"]["chunks"] + pt["annual_report"]["chunks"]
    frame(s, "AI Agent · Knowledge sources", "AI Agent Knowledge Sources: What Is Loaded",
          f"{VS['files']} original reports are cut into {fmt(VS['chunks'])} chunks and stored in a {VS['vector_store_mb']} MB vector store; sales data is read directly",
          "Every claim the agent makes is tagged with one of four types: direct data, inferred mapping, Walmart-level or regional context.",
          "AI Agent Workstream · Sources")
    rows = [
        ["Walmart sales data (Kaggle)", "Weekly sales by store and department with markdowns, fuel, temperature, CPI, unemployment", "3 CSV files · 421,570 rows", "read by pandas", "Direct structured evidence"],
        ["Store & department mapping", "What the anonymized codes most likely mean, rated High / Medium / Unresolved", "45 stores · 81 depts", "lookup tables", "Inferred mapping"],
        ["Walmart earnings releases", "Company-wide comp sales, traffic and ticket each quarter (FY11 Q1 – FY13 Q3, plus 2 comp-sales sheets)", f"{wr[0]} files", fmt(wr[1]), "Walmart-level context"],
        ["Walmart earnings call transcripts", "Management commentary by category, e.g. electronics deflation or Easter timing", f"{pt['earnings_call']['files']} files", fmt(pt["earnings_call"]["chunks"]), "Walmart-level context"],
        ["Walmart 10-K and annual report", "Merchandise units, seasonality, strategy and risks (FY2010 – FY2013)", f"{tk[0]} files", fmt(tk[1]), "Walmart-level context"],
        ["Federal Reserve Beige Book", "What retailers in each Fed district reported, split by district (national + 12) · Jan 2010 – Nov 2012", f"{pt['beige_book']['files']} files", fmt(pt["beige_book"]["chunks"]), "Regional / macro context"],
        ["NRF holiday forecast", "Expected holiday spending (2010, 2011, 2012 forecasts)", f"{pt['nrf_forecast']['files']} files", fmt(pt["nrf_forecast"]["chunks"]), "Regional / macro context"],
        ["EIA fuel prices", "Weekly gas prices by region; used to infer each store's region", "10 weekly series", "lookup tables", "Regional / macro context"],
    ]
    table(s, 0.5, 1.28, [2.0, 3.35, 1.3, 0.95, 1.4], rows, ["Source", "What it tells the agent", "Files", "Chunks", "Type"], 0.41, size=8.5,
          name="Knowledge sources table", col_styles={4: lambda t: (TYPE_STYLE[t][0], TYPE_STYLE[t][1], True)})
    notes(s, f"These are the sources the agents use, and they are all loaded, not planned. The sales data, 421,570 rows, is read directly by the Evidence Agent. The mapping tables tell the agents what the anonymized codes most likely mean, with a confidence level; we are clear that they are publicly inferred. "
             f"The text sources are cut into chunks and stored in ChromaDB: {VS['files']} original reports, {fmt(VS['chunks'])} chunks. Walmart's own earnings releases, call transcripts and 10-K filings give company-level context for eleven quarters. The Beige Book is the largest source, 24 editions, and we split each edition by Fed district so a chunk always knows which district it describes. "
             "NRF adds the holiday forecasts and EIA fuel prices are used to infer each store's region. Every claim the agent makes is labeled with one of four types, so it is clear what is fact and what is context. No competitor or third-party data is used.")
    return s


def s_arch(prs, lay):
    s = new_slide(prs, lay)
    frame(s, "AI Agent · Architecture", "AI Agent Architecture: What Runs Today",
          "A LangGraph orchestrator runs two agents in parallel; a reasoning agent writes the report; Streamlit streams it live",
          f"Store 7, median of 3 runs: {CASES[7]['seconds_median']:.0f} s end to end with the LLM writer (about 4 s with rules only).", "AI Agent Workstream · Architecture")
    c7 = CASES[7]["ms_median"]
    boxes = [  # key, title, text, number line, x, y, w, h
        ("alert", "Anomaly Payload", "3 formats accepted: Extra Trees, store-week, baseline", "3 example cases", 0.5, 1.95, 1.4, 1.55),
        ("flow", "Orchestrator", "LangGraph: 6 nodes; sends both tasks at once", "2 agents in parallel", 2.2, 1.95, 1.65, 1.55),
        ("bar", "Evidence Agent", "pandas over the Kaggle sales data", f"421,570 rows · {c7['Evidence Agent']} ms", 4.15, 1.3, 1.75, 1.35),
        ("lib", "RAG Agent", "ChromaDB over the original reports", f"{fmt(VS['chunks'])} chunks · {c7['RAG Agent']/1000:.1f} s", 4.15, 2.85, 1.75, 1.35),
        ("brain", "Reasoning Agent", "Rules decide the verdict; a free LLM writes the text", "rules 1 ms + LLM", 6.2, 1.95, 1.5, 1.55),
        ("user", "Dashboard + Analyst", "Streamlit: live trace, follow-up chat, quality checks", "4 of 6 checks automatic", 8.0, 1.95, 1.5, 1.55),
    ]
    for key, title, text, num, x, y, w, h in boxes:
        card(s, x, y, w, h, name=f"Card: {title}")
        icon(s, key, "blue", x + 0.12, y + 0.12, 0.34)
        tb(s, x + 0.54, y + 0.12, w - 0.6, 0.34, title, size=9.5, color=INK, bold=True, anchor="m")
        tb(s, x + 0.12, y + 0.56, w - 0.24, h - 0.9, text, size=8.5, color=MUTED, spacing=1.03)
        label_card(s, x + 0.12, y + h - 0.32, w - 0.24, 0.22, num, TINT, BLUE, size=7.5, line=TINTLINE)
    arrow(s, 1.9, 2.72, 2.2, 2.72)
    arrow(s, 3.85, 2.45, 4.15, 1.98)
    arrow(s, 3.85, 3.05, 4.15, 3.5)
    arrow(s, 5.9, 1.98, 6.2, 2.45)
    arrow(s, 5.9, 3.5, 6.2, 3.05)
    arrow(s, 7.7, 2.72, 8.0, 2.72)
    arrow(s, 9.3, 3.5, 9.3, 4.3, dash=True, head=False, color=GREY, w=1)
    arrow(s, 9.3, 4.3, 3.55, 4.3, dash=True, head=False, color=GREY, w=1)
    arrow(s, 3.55, 4.3, 3.55, 3.5, dash=True, color=GREY, w=1)
    tb(s, 3.7, 4.34, 5.4, 0.15, "Follow-up questions loop back to the orchestrator", size=8, color=GREY, align="c", italic=True)

    def logo(name, x, y, d=0.18):
        s.shapes.add_picture(str(LOGOS / f"{name}.png"), Inches(x), Inches(y), Inches(d), Inches(d))
    card(s, 0.5, 4.55, 9.0, 0.4, fill=TINT, line=TINTLINE)
    tb(s, 0.65, 4.55, 1.0, 0.4, "Built with", size=8.5, color=BLUE, bold=True, anchor="m")
    x = 1.65
    for nm, lab, wd in [("python", "Python + pandas", 1.45), ("langgraph", "LangGraph", 1.1), ("chromadb", "ChromaDB", 1.1), (None, "OpenRouter free LLM", 1.65), ("streamlit", "Streamlit", 1.05), ("github", "GitHub", 0.9)]:
        if nm:
            logo(nm, x, 4.66, 0.18)
            tb(s, x + 0.25, 4.66, wd - 0.25, 0.18, lab, size=8.5, color=SLATE, anchor="m")
        else:
            tb(s, x, 4.66, wd, 0.18, lab, size=8.5, color=SLATE, anchor="m")
        x += wd + 0.12
    notes(s, "This is what is actually running today. A payload from the anomaly team arrives in one of three shapes: the Extra Trees store-department-week hand-off, the store-week payload from the multi-store screening, or a baseline detection. We normalize all three into one internal payload. "
             f"A LangGraph orchestrator with six nodes sends two tasks at the same time. The Evidence Agent runs pandas checks over the 421,570 sales rows in about {c7['Evidence Agent']} milliseconds. The RAG Agent searches {fmt(VS['chunks'])} chunks in ChromaDB in about {c7['RAG Agent']/1000:.0f} seconds. "
             "The Reasoning Agent applies rules to decide the verdict and confidence, and a free LLM through OpenRouter writes the plain-language explanation; if the model is rate-limited the rules write it instead. Streamlit shows the agents working live, then the factors, the evidence, and automatic quality checks, and the analyst can ask follow-up questions that go back to the orchestrator. "
             f"End to end it takes about {CASES[7]['seconds_median']:.0f} seconds for Store 7 with the LLM writer, and about four seconds with rules only.")
    return s


def s_rag(prs, lay):
    s = new_slide(prs, lay)
    st = CASES[7]["rag_stats"]
    frame(s, "AI Agent · RAG Agent", "RAG Agent: Strategy and Numbers",
          "Filter by time and place first, then search by meaning, then re-rank by the best-matching sentence",
          "Embeddings: all-MiniLM-L6-v2 (ONNX, 384-dim) · ChromaDB HNSW index, cosine distance · built in 133 s from the original files.",
          "AI Agent Workstream · RAG Agent")
    steps = [("Chunk the originals", f"About {VS['chunk_target_chars']} characters per chunk, cut at sentence boundaries, {VS['overlap_chars']}-character overlap. Table and number noise dropped ({VS['dropped_noise_chunks']} chunks). Beige Books split by Fed district."),
             ("Embed and store", "Each chunk keeps publisher, evidence type, Fed district, report period and publish date as metadata in ChromaDB."),
             ("Plan the query", "2 to 4 short questions per case: category trend, consumer demand, calendar event, fuel or weather signal."),
             ("Filter before searching", "Time: report covers the week, came out in the 3 weeks before, or its period just ended. Place: the store's Fed district or national."),
             ("Search and re-rank", "Top 25 chunks per query, then 30 best re-scored by their best sentence (45% chunk, 55% sentence, plus keywords and a local-district boost). Max 2 chunks per report; each keeps one verbatim quote.")]
    strategy_card(s, 0.5, 1.28, 5.7, 3.7, steps, tsize=9.5, bsize=8.5)
    numbers_label(s, 6.4, 1.3)
    tiles = [(f"{VS['files']}", "reports loaded"), (fmt(VS["chunks"]), "chunks embedded"), (f"{VS['vector_store_mb']} MB", "vector store on disk"), (f"{VS['avg_chunk_words']}", "words per chunk on average")]
    for i, (big, lab) in enumerate(tiles):
        tile(s, 6.4 + (i % 2) * 1.6, 1.52 + (i // 2) * 0.82, 1.5, 0.74, big, lab)
    card(s, 6.4, 3.22, 3.1, 1.76, name="Funnel")
    tb(s, 6.52, 3.28, 2.9, 0.16, "STORE 7 SEARCH FUNNEL", size=7.5, color=BLUE, bold=True)
    fun = [(fmt(st["chunks_in_store"]), "chunks in the store", 2.86, "E2E8F0", INK),
           (fmt(st["chunks_after_filter"]), f"after time + region filter ({st['reports_after_filter']} reports)", 2.56, "DBEAFE", INK),
           (str(st["candidates"]), f"candidates from {st['queries']} queries", 2.26, "BFDBFE", INK),
           (str(st["returned"]), f"passages returned · {st['ms']/1000:.1f} s", 1.96, BLUE, WHITE)]
    for i, (big, small, wd, fill, col) in enumerate(fun):
        label_card(s, 6.52, 3.5 + i * 0.35, wd, 0.3, f"**{big}**  {small}", fill, col, size=8, bold=False, align="l")
    notes(s, f"Here is how the RAG agent works, strategy first. We cut the original reports into chunks of about {VS['chunk_target_chars']} characters at sentence boundaries with a small overlap, drop table and number noise, split Beige Books by Fed district, and embed every chunk with a 384-dimension model into ChromaDB, with the publisher, evidence type, district, period and publish date as metadata. "
             "At question time the agent plans two to four short queries: the category trend, consumer demand, a calendar event if there is one, and a fuel or weather signal if there is one. "
             "The key design choice is to filter before searching: a report must cover the week, have come out in the three weeks before, or just have ended, and it must be national or from the store's own Fed district. A 2014 report can never be retrieved for a 2012 anomaly. "
             "Then it takes the top 25 chunks per query by meaning and re-scores the 30 best by their single best-matching sentence, because a long chunk can match for the wrong reason. At most two chunks per report, and each keeps one verbatim quote. "
             f"The numbers: {VS['files']} reports, {fmt(VS['chunks'])} chunks, a {VS['vector_store_mb']} megabyte store. For Store 7 the search narrows {fmt(st['chunks_in_store'])} chunks to {st['chunks_after_filter']} after the filter, {st['candidates']} candidates, and {st['returned']} passages returned in about {st['ms']/1000:.0f} seconds.")
    return s


def s_evidence(prs, lay):
    s = new_slide(prs, lay)
    c7, c2 = CASES[7], CASES[2]
    frame(s, "AI Agent · Evidence Agent", "Evidence Agent: Strategy and Numbers",
          "Six pandas checks, each answering one question an analyst would ask, run on the sales data in milliseconds",
          "Store-level payloads (Store 2) swap in: baseline contents, same week last year, all-45-store rank, department mix and the next 4 weeks.",
          "AI Agent Workstream · Evidence Agent")
    steps = [("Store vs. department", "Is the whole store down, or just this department? (store total vs. last year that week)"),
             ("Quarter trend", "One-off week or a pattern? (quarter vs. last year, weeks below last year)"),
             ("Regional peers", "How did the same department do in other stores of the region this quarter?"),
             ("Whole chain", "Is every store seeing this? (all 45 stores, same department and quarter)"),
             ("Markdowns and macro", "Markdowns vs. the store's average week; fuel, temperature, CPI, unemployment vs. last year."),
             ("Calendar", "Did a holiday move, or does the baseline hold a holiday peak? Compare six-week totals.")]
    strategy_card(s, 0.5, 1.28, 5.7, 3.7, steps, tsize=9.5, bsize=8.5)
    numbers_label(s, 6.4, 1.3)
    tiles = [("421,570", "sales rows scanned per run"), ("6", "checks per case"),
             (f"{min(CASES[k]['ms_median']['Evidence Agent'] for k in CASES)}–{max(CASES[k]['ms_median']['Evidence Agent'] for k in CASES)} ms", "median time per run"),
             ("5 of 5", "key numbers re-verified from raw files (Store 7)")]
    for i, (big, lab) in enumerate(tiles):
        tile(s, 6.4 + (i % 2) * 1.6, 1.52 + (i // 2) * 0.82, 1.5, 0.74, big, lab)
    card(s, 6.4, 3.22, 3.1, 1.76, name="Store 7 results")
    tb(s, 6.52, 3.28, 2.9, 0.16, "STORE 7 · ELECTRONICS RESULTS", size=7.5, color=BLUE, bold=True)
    tb(s, 6.52, 3.5, 2.88, 1.45, [{"t": "Rest of the store only **−3.3%**", "after": 3}, {"t": "Electronics **−12.7%** this quarter, down 9 of 13 weeks", "after": 3},
                                  {"t": "Colorado peers: **−3.6%, +2.8%, +14.2%**", "after": 3}, {"t": "All 45 stores: **−0.5%**", "after": 3},
                                  {"t": "Markdowns **0.6×** a normal week; fuel +2.1%", "after": 3}, {"t": "No holiday that week", "after": 0}], size=8.5, color=SLATE)
    notes(s, "The Evidence Agent is plain pandas over the 421,570 sales rows, and that is on purpose: every number it gives can be recomputed. Its strategy is six checks that mirror what an analyst would ask. Is the whole store down or just this department? Is it one week or a pattern? How did similar stores in the region do? Is the whole chain seeing it? Did markdowns, fuel or weather change? And did a holiday move, or does the baseline contain a holiday peak? "
             f"Each run takes {min(CASES[k]['ms_median']['Evidence Agent'] for k in CASES)} to {max(CASES[k]['ms_median']['Evidence Agent'] for k in CASES)} milliseconds. For Store 7 Electronics it finds the rest of the store only minus 3.3 percent, Electronics down 12.7 percent this quarter and 9 of 13 weeks, Colorado peers between minus 3.6 and plus 14.2, the chain at minus 0.5, markdowns at 0.6 times a normal week. "
             "For a store-level payload like Store 2 it swaps in checks on what the baseline contains, the same week last year, the rank among all 45 stores, and the department mix. A separate script recomputes the key numbers from the raw files, and all five match for Store 7.")
    return s


def s_reason(prs, lay):
    s = new_slide(prs, lay)
    frame(s, "AI Agent · Reasoning Agent", "Reasoning Agent: Strategy and Numbers",
          "Rules decide the verdict and confidence so every claim traces to a number or a quote; an LLM may only rewrite the text",
          f"LLM writer: free model via OpenRouter ({LL['models'][0].split('/')[1]}); {LL['accepted']} of {LL['runs']} runs got an answer, {LL['no_answer']} were rate-limited and used the rules, {LL['rejected']} rejected.", "AI Agent Workstream · Reasoning Agent")
    steps = [("Is it just timing?", "A holiday moved, or the baseline holds a holiday peak, AND sales are flat vs. last year, AND other stores dropped the same. Then: Likely explained."),
             ("Otherwise weigh the factors", "Company-wide trend (Walmart quotes), store-specific gap vs. chain and peers, promotions (markdown ratio plus Fed quote), store-wide weakness. Then: Needs review."),
             ("Rate the confidence", "Starts at High and drops for: single-week drop, department or region name not High confidence, no time-aligned report, part of the drop unexplained."),
             ("LLM writer (free model)", "Rewrites the explanation in plain language. Rejected if it adds any number or quote that is not in the facts; if the free model is rate-limited, the rules write the text.")]
    strategy_card(s, 0.5, 1.28, 5.7, 3.7, steps, tsize=9.5, bsize=8.5)
    numbers_label(s, 6.4, 1.3)
    ks = list(CASES)
    nq = sum(len(re.findall("“", f["text"])) for k in ks for f in CASES[k]["factors"])
    tiles = [("1 + 2", "cases: needs review + explained (3 run)"), ("4 to 5", "factors per answer"), (f"{nq} of {nq}", "quotes found word for word in the sources"),
             (f"{LL['ms_median']/1000:.1f} s", "LLM writer, median when it answers")]
    for i, (big, lab) in enumerate(tiles):
        tile(s, 6.4 + (i % 2) * 1.6, 1.52 + (i // 2) * 0.82, 1.5, 0.74, big, lab)
    card(s, 6.4, 3.22, 3.1, 1.76, name="Verdicts")
    tb(s, 6.52, 3.28, 2.9, 0.16, "VERDICTS ON THE THREE CASES", size=7.5, color=BLUE, bold=True)
    for i, k in enumerate((7, 13, 2)):
        c = CASES[k]
        y = 3.52 + i * 0.46
        tb(s, 6.52, y, 1.2, 0.4, [{"t": f"Store {k}", "size": 8.5, "bold": True, "color": INK}, {"t": c["dept_name"], "size": 7.5, "color": GREY}], anchor="m")
        col = (RED, "FEE2E2") if c["status"] == "Needs review" else ("166534", "DCFCE7")
        label_card(s, 7.7, y + 0.05, 1.75, 0.3, f"{c['status']} · {c['confidence']}", col[1], col[0], size=7)
    notes(s, "The Reasoning Agent decides the verdict with rules, so every claim traces to a number or a quote and the result is testable. Step one: is it just timing? If a holiday moved, or the baseline holds a holiday peak, and sales are flat versus last year, and other stores dropped by the same amount, the verdict is Likely explained. "
             "If not, it weighs the factors: the company-wide trend using Walmart's own words, whether this store is worse than the chain and its peers, promotions, and store-wide weakness. That gives Needs review. Then it rates its confidence, which starts at High and drops for a single-week drop, a department name that is not high confidence, missing time-aligned reports, or a part of the drop left unexplained. "
             f"On our three cases the verdicts are one Needs review and two Likely explained, each with four or five factors, and all {nq} quotes it used were found word for word in the original source files. "
             f"On top of that, a free LLM through OpenRouter rewrites the explanation in plain language in about {LL['ms_median']/1000:.1f} seconds, using about {LL['tokens_in_median']} tokens in and {LL['tokens_out_median']} out. Its text is rejected if it adds any number or quote that is not in the facts. In our last nine runs, {LL['accepted']} got an answer, {LL['no_answer']} were rate-limited by the free tier and fell back to the rules, and none were rejected. The factor tables on these slides are the rules; the plain-language paragraph in the app is the LLM.")
    return s


def s_flow(prs, lay):
    s = new_slide(prs, lay)
    c7 = CASES[7]
    ms = c7["ms_median"]
    frame(s, "AI Agent · Orchestrator · Request flow", "Orchestrator and Request Flow: Live Trace",
          "One request followed through the LangGraph graph; milliseconds are medians of 3 runs on Store 7",
          "Follow-ups are routed to one of 8 intents; “How did Store 41 do?” calls an Evidence lookup tool.", "AI Agent Workstream · Request Flow")
    card(s, 0.5, 1.28, 9.0, 0.38, fill=TINT, line=TINTLINE)
    tb(s, 0.65, 1.28, 8.7, 0.38, "**Request:** “Why did Electronics drop at Store 7 in the week ending Aug 24, 2012?”", size=10.5, color=INK, anchor="m")
    cols = [  # x, w, y, h, num, title, text, ms
        (0.5, 1.5, 2.45, 1.7, "1", "Payload", ["Store 7 · Electronics", "**$34.0K vs. $45.0K** (−24.6%)"], ms["Anomaly payload"]),
        (2.3, 1.6, 2.45, 1.7, "2", "Orchestrator", ["Reads the signals, plans **2 queries**, sends both tasks at once"], ms["Orchestrator"]),
        (4.25, 2.15, 1.85, 1.28, "3", "Evidence Agent", ["Electronics **−12.7%** this quarter; Colorado peers −3.6% to +14.2%"], ms["Evidence Agent"]),
        (4.25, 2.15, 3.3, 1.28, "4", "RAG Agent", [f"**{c7['rag_stats']['chunks_after_filter']}** chunks pass the filter; **{c7['rag_stats']['returned']}** passages returned"], ms["RAG Agent"]),
        (6.85, 2.65, 1.85, 1.28, "5", "Reasoning Agent", [f"**{c7['status']} · {c7['confidence']}.** Rules decide in 1 ms; the LLM writes the plain-language text"], ms["Reasoning Agent"]),
        (6.85, 2.65, 3.3, 1.28, "6", "Checks + Analyst", ["**4 of 6** checks pass automatically; analyst confirms or asks a follow-up"], ms["Checks"]),
    ]
    for x, w, y, h, num, title, text, t in cols:
        card(s, x, y, w, h, name=f"Step {num}: {title}")
        badge(s, num, x + 0.1, y + 0.1, d=0.26, size=9)
        tb(s, x + 0.45, y + 0.1, w - 0.5, 0.26, title, size=10, color=INK, bold=True, anchor="m")
        tb(s, x + 0.12, y + 0.46, w - 0.24, h - 0.8, text, size=9, color=SLATE, spacing=1.03, after=2)
        label_card(s, x + w - 0.95, y + h - 0.3, 0.85, 0.2, f"{t:,} ms", TINT, BLUE, size=7.5, line=TINTLINE)
    arrow(s, 2.0, 3.3, 2.3, 3.3)
    arrow(s, 3.9, 3.05, 4.25, 2.5)
    arrow(s, 3.9, 3.55, 4.25, 3.95)
    arrow(s, 6.4, 2.5, 6.85, 2.5)
    arrow(s, 6.4, 3.95, 6.85, 3.15)
    arrow(s, 8.17, 3.13, 8.17, 3.3)
    arrow(s, 8.17, 4.58, 8.17, 4.78, dash=True, head=False, color=GREY, w=1)
    arrow(s, 8.17, 4.78, 3.1, 4.78, dash=True, head=False, color=GREY, w=1)
    arrow(s, 3.1, 4.78, 3.1, 4.15, dash=True, color=GREY, w=1)
    tb(s, 3.3, 4.8, 4.6, 0.16, f"Follow-up loops back to the orchestrator · total {c7['seconds_median']:.1f} s", size=8, color=GREY, align="c", italic=True)
    notes(s, f"Here is one request through the orchestrator, with the real timings. The question is why Electronics dropped at Store 7 in the week ending August 24, 2012. "
             f"The payload says 34 thousand dollars against 45 thousand expected. The orchestrator, which is a LangGraph graph, reads the calendar, fuel and weather signals, plans two queries for the RAG agent, and sends both tasks at the same time. "
             f"The Evidence Agent finishes in {ms['Evidence Agent']} milliseconds with Electronics down 12.7 percent this quarter. The RAG Agent takes about {ms['RAG Agent']/1000:.0f} seconds because it embeds and re-scores sentences, and returns six passages from {c7['rag_stats']['chunks_after_filter']} chunks that passed the time and region filter. "
             f"The Reasoning Agent decides in about a millisecond with rules: Needs review with medium confidence. Most of its time here is the free LLM writing the plain-language text, which can be slower or rate-limited, in which case the rules write it. Then four of the six quality checks run automatically. Total about {c7['seconds_median']:.0f} seconds. "
             "If the analyst asks a follow-up, the orchestrator routes it to one of eight intents; asking how Store 41 did calls an Evidence lookup tool and answers with Store 41's real numbers.")
    return s


def s_example7(prs, lay):
    c = CASES[7]
    s = new_slide(prs, lay)
    frame(s, "AI Agent · Example 1 · Needs review", "Anomaly Example: Store 7, Electronics (Colorado)",
          "The ML model detects the anomaly; the agents find the possible factors (this is the live agent output)",
          "Same case and same text as the live Streamlit app.", "AI Agent Workstream · Example")
    card(s, 0.5, 1.28, 9.0, 0.62, line=RED, name="Anomaly detected")
    icon(s, "alert", "red", 0.62, 1.4, 0.38, tile="FEE2E2")
    tb(s, 1.1, 1.36, 1.8, 0.5, [{"t": "ANOMALY DETECTED", "size": 7.5, "color": RED, "bold": True}, {"t": "by the Extra Trees model", "size": 8, "color": GREY}], anchor="m")
    for x, lab, val in [(3.0, "Store", "7 · Colorado"), (4.3, "Department", "72 · Electronics"), (5.7, "Week ending", "Aug 24, 2012"), (7.0, "Actual vs. expected", "$33,958 vs. $45,010")]:
        tb(s, x, 1.36, 1.6, 0.5, [{"t": lab, "size": 7.5, "color": GREY}, {"t": val, "size": 10, "color": INK, "bold": True}], anchor="m")
    tb(s, 8.6, 1.36, 0.8, 0.5, [{"t": "Gap", "size": 7.5, "color": GREY, "align": "r"}, {"t": "−24.6%", "size": 14, "color": RED, "bold": True, "align": "r"}], anchor="m")
    rows = [[f["title"], f["text"]] for f in c["factors"]]
    table(s, 0.5, 2.05, [1.7, 7.3], rows, ["Possible factor", "What the evidence says"], 0.5, size=8, name="Possible factors")
    card(s, 0.5, 4.5, 9.0, 0.5, fill=TINT, line=BLUE, name="Bottom line")
    tb(s, 0.65, 4.5, 6.8, 0.5, "**Bottom line:** " + c["bottom_line"], size=9, color=INK, anchor="m")
    label_card(s, 7.55, 4.62, 1.85, 0.26, f"{c['status']} · {c['confidence']}", "FEE2E2", DRED, size=8.5)
    notes(s, "Here is the first example, and it is exactly what our live Streamlit app produces. The Extra Trees model flagged Store 7 Electronics in Colorado for the week ending August 24, 2012: about 34 thousand dollars against 45 thousand expected, a 24.6 percent gap. "
             "The agents found three possible factors. Walmart's own earnings call says deflation continues to impact electronics, but across all 45 stores Electronics is only down half a percent, so company-wide prices explain only part. Our sales data shows other Colorado stores held up much better, so the problem is likely at Store 7 itself. "
             "Store 7 also ran fewer markdowns than usual during back-to-school, when the Kansas City Fed said back-to-school items sold well. A holiday, fuel, weather and a whole-store slump are ruled out. "
             "The agents say Needs review with medium confidence, because the drop is proven but the cause is only partly explained.")
    return s


def s_example2(prs, lay, chart_data):
    c = CASES[2]
    s = new_slide(prs, lay)
    frame(s, "AI Agent · Example 2 · Likely explained", "Anomaly Example: Store 2, Texas, Week Ending Jan 6, 2012",
          "Same kind of flag, different answer: $1.80M vs. $2.46M expected (−26.7%), but the agents say it is the Christmas baseline",
          "Same case and same text as the live Streamlit app. Payload: store-week format.", "AI Agent Workstream · Example")
    card(s, 0.5, 1.3, 5.2, 3.05, name="Chart card")
    tb(s, 0.65, 1.37, 4.9, 0.18, "STORE 2 WEEKLY SALES ($M) · NOV 2011 – FEB 2012", size=8, color=BLUE, bold=True)
    cats, this_y, last_y = chart_data
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("This year", this_y)
    cd.add_series("Same week last year", last_y)
    tb(s, 0.65, 1.58, 4.9, 0.16, "Amber: the 4 weeks averaged into the expected $2.46M. Red: the flagged week.", size=8, color=GREY, italic=True)
    gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.6), Inches(1.78), Inches(5.0), Inches(2.52), cd)
    gf.name = "Store 2 weekly sales"
    ch = gf.chart
    ch.font.size, ch.font.name = Pt(8), FONT
    ch.font.color.rgb = rgb(MUTED)
    ch.has_legend, ch.has_title = True, False
    ch.legend.position, ch.legend.include_in_layout = XL_LEGEND_POSITION.BOTTOM, False
    ch.legend.font.size = Pt(8)
    va, ca = ch.value_axis, ch.category_axis
    va.minimum_scale, va.maximum_scale, va.major_unit = 1.0, 4.0, 0.5
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = rgb("E2E8F0")
    va.major_gridlines.format.line.width = Pt(0.5)
    va.format.line.fill.background()
    va.tick_labels.number_format, va.tick_labels.number_format_is_linked = '0.0', False
    ca.format.line.color.rgb = rgb(LINE)
    ca.has_major_gridlines = False
    ca.tick_labels.font.size = Pt(7.5)
    s_this, s_last = ch.plots[0].series
    for ser, col, wd, dash in ((s_this, BLUE, 2.5, None), (s_last, "94A3B8", 1.5, MSO_LINE.DASH)):
        ser.smooth = False
        ser.format.line.color.rgb = rgb(col)
        ser.format.line.width = Pt(wd)
        if dash:
            ser.format.line.dash_style = dash
        ser.marker.style = XL_MARKER_STYLE.CIRCLE
        ser.marker.size = 5
        ser.marker.format.fill.solid()
        ser.marker.format.fill.fore_color.rgb = rgb(col)
        ser.marker.format.line.color.rgb = rgb(col)
    for i, name in enumerate(cats):
        if name in ("Dec 9", "Dec 16", "Dec 23", "Dec 30"):
            col = AMBER
        elif name == "Jan 6":
            col = RED
        else:
            continue
        pt = s_this.points[i]
        pt.marker.style = XL_MARKER_STYLE.CIRCLE
        pt.marker.size = 9 if name == "Jan 6" else 7
        pt.marker.format.fill.solid()
        pt.marker.format.fill.fore_color.rgb = rgb(col)
        pt.marker.format.line.color.rgb = rgb(col)
    for name, text in (("Dec 23", "Christmas $3.22M"), ("Jan 6", "$1.80M")):
        dl = s_this.points[cats.index(name)].data_label
        dl.has_text_frame = True
        dl.text_frame.text = text
        dl.position = XL_LABEL_POSITION.ABOVE
        r = dl.text_frame.paragraphs[0].runs[0]
        r.font.size, r.font.bold, r.font.name = Pt(8), True, FONT
        r.font.color.rgb = rgb(AMBER if name == "Dec 23" else RED)
    f = [("cal", "Christmas inflated the baseline", "Expected = average of Dec 9–30, including Christmas week (1.8× a typical week). Store 2 is +2.4% vs. the same week last year."),
         ("globe", "Every store dropped", "All 45 stores: median −25.3%. Store 2 ranks 20th of 45. Last year's same week was −30.9% by the same method."),
         ("gift", "December-peak departments", "Toys, Electronics, Media & Gaming, Impulse, Seasonal: together +2.0% vs. last year."),
         ("book", "Strong season, not a slump", "Walmart: “successful holiday season”. Dallas Fed: holiday sales strong. Toys −13.8% is worth a look.")]
    for i, (ik, t1, t2) in enumerate(f):
        y = 1.3 + i * 0.78
        card(s, 5.85, y, 3.65, 0.7, name=f"Finding {i+1}")
        icon(s, ik, "blue", 5.95, y + 0.14, 0.42)
        tb(s, 6.48, y + 0.05, 2.95, 0.6, [{"t": t1, "size": 9.5, "color": INK, "bold": True, "after": 1}, {"t": t2, "size": 8, "color": MUTED}], anchor="m", spacing=1.0)
    card(s, 0.5, 4.45, 9.0, 0.55, fill="F0FDF4", line=GREEN, name="Bottom line")
    tb(s, 0.65, 4.45, 6.8, 0.55, "**Bottom line:** " + c["bottom_line"], size=8.5, color=INK, anchor="m", spacing=1.0)
    label_card(s, 7.6, 4.6, 1.8, 0.26, f"{c['status']} · {c['confidence']}", "DCFCE7", "166534", size=8.5)
    notes(s, "The agents do not flag everything. Here is a second example from the multi-store screening, also exactly what the live app shows: Store 2 in Texas, week ending January 6, 2012. Sales were 1.80 million dollars against an expected 2.46 million, minus 26.7 percent. "
             "But look at where the expected number comes from: the average of the four weeks before, December 9 to 30, which includes Christmas week at 3.2 million dollars, almost twice a typical week. The amber dots on the chart are those four weeks. Against the same week last year, Store 2 is actually up 2.4 percent, and last year's same week would have been flagged too, at minus 30.9 percent. "
             "All 45 stores dropped a median of 25 percent that week, and Store 2 ranks right in the middle. The five biggest shortfalls are Toys, Electronics, Media and Gaming, Impulse and Seasonal, all December-peak departments, together up 2 percent versus last year's same week. "
             "Walmart's own call says it was a successful holiday season, and the Dallas Fed describes strong holiday sales. So the verdict is Likely explained with high confidence, and the agents say the detector's structural slump flag is not supported. They still point out one thing worth a look: Toys is 13.8 percent below last year. "
             "This is how the agents save analyst time: they say no action is needed, and why.")
    return s


def s_eval(prs, lay):
    s = new_slide(prs, lay)
    c7, c2, c13 = CASES[7], CASES[2], CASES[13]
    frame(s, "AI Agent · Evaluation", "How We Evaluate the Agents: Results So Far",
          "Four of six checks run automatically on every answer, live in the app; two need independent team reviewers",
          "Automatic checks recompute numbers from raw files and look quotes up in the original source files, not in the agent's own data.",
          "AI Agent Workstream · Evaluation")
    r = {k: {c["check"]: c for c in CASES[k]["checks"]} for k in CASES}
    checks = [("calc", "Number accuracy", "Is every number in the agent's answer correct?", "Auto", r[7]["Number accuracy"]["result"].split(";")[0].replace(" recomputed from the raw sales files", " recomputed from raw files") + " ✓"),
              ("clock", "Right time and place", "Is every report from the same quarter and the store's region?", "Auto", "Store 7: " + re.sub(r"passages are from.*", "passages in the right quarter and district ✓", r[7]["Right time and place"]["result"])),
              ("quote", "Quote accuracy", "Does every quote really appear in the cited report?", "Auto", "Store 2: " + r[2]["Quote accuracy"]["result"].replace("found word for word in the original source files.", "found word for word ✓")),
              ("users", "Main factor agreement", "Does the agent pick the same main factor a person would?", "Team", "Two reviewers name it independently"),
              ("calcheck", "Holiday-shift detection", "Does the agent recognize weeks where a holiday moved?", "Auto", "Store 13 Easter ✓ · Store 2 Christmas ✓ · Store 7 none ✓"),
              ("scale", "Confidence check", "Does the confidence level match the evidence?", "Team", "Two reviewers rate it independently")]
    w, h = 3.05, 1.17
    for i, (ik, name, q, who, ex) in enumerate(checks):
        x, y = 0.5 + (i % 2) * (w + 0.15), 1.3 + (i // 2) * (h + 0.07)
        card(s, x, y, w, h, name=f"Check: {name}")
        icon(s, ik, "blue", x + 0.12, y + 0.12, 0.36)
        tb(s, x + 0.58, y + 0.1, w - 1.3, 0.4, name, size=10, color=INK, bold=True, anchor="m")
        label_card(s, x + w - 0.68, y + 0.17, 0.56, 0.2, who, "DBEAFE" if who == "Auto" else "EDE9FE", BLUE if who == "Auto" else "6D28D9", size=7.5)
        tb(s, x + 0.12, y + 0.54, w - 0.24, 0.34, q, size=8.5, color=MUTED, spacing=1.0)
        tb(s, x + 0.12, y + 0.9, w - 0.24, 0.24, ex, size=8, color=BLUE, bold=True, spacing=1.0)
    card(s, 6.95, 1.3, 2.55, 3.48, name="Where we are")
    tb(s, 7.1, 1.4, 2.3, 0.18, "WHERE WE ARE", size=8, color=BLUE, bold=True)
    for i, k in enumerate((7, 13, 2)):
        c = CASES[k]
        n = sum(x["status"] == "pass" for x in c["checks"])
        y = 1.72 + i * 0.62
        tb(s, 7.1, y, 2.3, 0.18, f"Store {k} · {c['dept_name']}", size=9, color=INK, bold=True)
        label_card(s, 7.1, y + 0.22, 1.0, 0.22, f"{n} of 6 passed", "DCFCE7", "166534", size=7.5)
        tb(s, 8.2, y + 0.22, 1.25, 0.22, c["status"], size=8, color=GREY, anchor="m")
    tb(s, 7.1, 3.62, 2.3, 1.1, [{"t": "**2 pending on each case:** main factor and confidence need independent team review.", "after": 4},
                                {"t": "**Next:** run all six checks on 10 flagged exceptions, then report the pass rate.", "after": 0}], size=8.5, color=MUTED)
    notes(s, "To know whether the agents are trustworthy, every answer goes through six checks, and four of them run automatically in the app. The number check recomputes the key numbers from the raw sales files with separate code, so a bug in the Evidence Agent cannot pass its own check. "
             "The time-and-place check confirms every report is from the week's quarter and the store's Fed district or national. The quote check looks every quote up word for word in the original source files. The holiday-shift check compares the agent's verdict with what we know about the week: Easter for Store 13, Christmas for Store 2, and no calendar effect for Store 7. "
             "On our three cases, four of six checks pass automatically on each. The two pending ones, main factor and confidence, need two team members to judge independently, so we have not claimed them yet. "
             "Next we run all six on ten flagged exceptions, six regular and four holiday-shift, and report the pass rate.")
    return s


# ------------------------------------------------------------------------------------------ main
def chart_series():
    """Store 2 weekly sales (this year vs. same week last year), from the Kaggle data."""
    import pandas as pd
    tr = pd.read_csv(HERE.parent.parent / "app" / "data" / "train.csv", parse_dates=["Date"])
    s = tr[tr.Store == 2].groupby("Date").Weekly_Sales.sum()
    rng = s.loc["2011-11-04":"2012-02-03"]
    lag = pd.Timedelta(weeks=52)
    cats = [f"{d:%b} {d.day}" for d in rng.index]
    return cats, [round(v / 1e6, 3) for v in rng.values], [round(s[d - lag] / 1e6, 3) for d in rng.index]


def main(src, dst):
    prs = Presentation(src)
    lay = next(l for l in prs.slide_masters[1].slide_layouts if l.name == "BLANK_3")
    old = list(prs.slides)
    titles = [sh.text_frame.text for sh in old[33].shapes if sh.has_text_frame]
    assert any("AI Agent" in t for t in titles), "slide 34 is not the AI-agent section"
    first_after = next(i for i, sl in enumerate(old) if i > 33 and any(sh.has_text_frame and "Streamlit Dashboard Live Demo" in sh.text_frame.text for sh in sl.shapes))
    builders = [s_why, s_sources, s_arch, s_rag, s_evidence, s_reason, s_flow, s_example7, None, s_eval]
    for b in builders:
        s_example2(prs, lay, chart_series()) if b is None else b(prs, lay)
    lst = prs.slides._sldIdLst
    ids = list(lst)
    old_ids, new_ids = ids[33:first_after], ids[len(old):]
    anchor = ids[first_after]
    for el in new_ids:
        lst.remove(el)
        anchor.addprevious(el)
    for el in old_ids:
        prs.part.drop_rel(el.get(qn("r:id")))
        lst.remove(el)
    prs.save(dst)
    print("saved", dst, "slides:", len(prs.slides), "| replaced", len(old_ids), "old slides with", len(new_ids), "new")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
