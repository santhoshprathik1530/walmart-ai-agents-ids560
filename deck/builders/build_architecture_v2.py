"""Five architecture slides (v2): system map, Orchestrator, Evidence Agent, RAG Agent, Reasoning Agent.

Every box, label and value comes from the code in app/agents/ (graph.py, engine.py, ingest.py, rag.py, reasoning.py, llm.py)
and from a run on the Store 7 / Dept 72 Electronics payload (week ending 2012-08-24). Things that are not built are drawn in
dashed grey boxes marked "Not built".

Semantic colours (same component = same colour on every slide):
    Orchestrator  deck blue     Evidence  teal     RAG  violet     Reasoning  amber
    data stores   warm grey     guard     green    failure / fallback  muted red
Line styles: solid ink = task / request · solid colour = results returned by that component · dashed grey = offline build
             dotted grey = follow-up question · dashed box = LLM call (optional)

Usage:  python3 build_architecture_v2.py "<source deck>.pptx" "<output>.pptx"
"""
import sys

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

FONT, MONO = "Arial", "Courier New"
INK, GREY, MUTE, WHITE = "1D1D1D", "595959", "8C8A80", "FFFFFF"
ORCH, ORCH_T = "1A36B4", "E3E8F8"
EVID, EVID_T = "00766C", "DDEFEC"
RAG, RAG_T = "5B3FA0", "ECE6F6"
REAS, REAS_T = "9A5B00", "FBEBD0"
STORE, STORE_F = "8C8A80", "E4E2D8"
OK, OK_T = "2E7D32", "E2F0E3"
ERR, ERR_T = "B23A2E", "F6E0DD"
BAND = "ECEAE0"

RECT, ROUND, OVAL, DIAMOND, CAN = (MSO_SHAPE.RECTANGLE, MSO_SHAPE.ROUNDED_RECTANGLE, MSO_SHAPE.OVAL, MSO_SHAPE.DIAMOND,
                                   MSO_SHAPE.CAN)
DASH, DOT = MSO_LINE.DASH, MSO_LINE.ROUND_DOT


def rgb(h):
    return RGBColor.from_string(h)


def I(v):
    return int(Inches(v))


# ------------------------------------------------------------------------------------------ text
def _fill_tf(tf, paras, size, color, bold, align, font, italic, spacing):
    """paras: list of paragraphs; a paragraph is a str, a list of runs, or a dict(runs=..., align=..., after=...).
    A run is a str or (str, dict(size, color, bold, italic, font))."""
    tf.word_wrap = True
    if isinstance(paras, str):
        paras = paras.split("\n")
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        opts = {}
        if isinstance(para, dict):
            opts, para = para, para["runs"]
        if isinstance(para, str):
            para = [para]
        p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[opts.get("align", align)]
        if opts.get("after") is not None:
            p.space_after = Pt(opts["after"])
        elif spacing:
            p.space_after = Pt(spacing)
        if opts.get("before") is not None:
            p.space_before = Pt(opts["before"])
        for run in para:
            text, st = (run, {}) if isinstance(run, str) else run
            r = p.add_run()
            r.text = text
            f = r.font
            f.name = st.get("font", opts.get("font", font))
            f.size = Pt(st.get("size", opts.get("size", size)))
            f.bold = st.get("bold", opts.get("bold", bold))
            f.italic = st.get("italic", opts.get("italic", italic))
            f.color.rgb = rgb(st.get("color", opts.get("color", color)))


def tx(s, x, y, w, h, paras, size=10, color=INK, bold=False, align="l", anchor="t", font=FONT, italic=False, spacing=0, name=None):
    box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    _fill_tf(tf, paras, size, color, bold, align, font, italic, spacing)
    if name:
        box.name = name
    return box


def box(s, x, y, w, h, paras=None, kind=ROUND, fill=WHITE, line=None, lw=1.0, dash=None, size=10, color=INK, bold=False,
        align="c", anchor="m", font=FONT, italic=False, margin=0.06, radius=0.06, spacing=0, name=None, adj=None):
    shp = s.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if kind == ROUND:
        shp.adjustments[0] = min(0.5, radius / min(w, h))
    if adj is not None:
        shp.adjustments[0] = adj
    if fill:
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(fill)
    else:
        shp.fill.background()
    if line:
        shp.line.color.rgb = rgb(line)
        shp.line.width = Pt(lw)
        if dash:
            shp.line.dash_style = dash
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    tf = shp.text_frame
    tf.margin_left = tf.margin_right = Inches(margin)
    tf.margin_top = tf.margin_bottom = Inches(min(margin, 0.04))
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    if paras:
        _fill_tf(tf, paras, size, color, bold, align, font, italic, spacing)
    _flat(shp)
    if name:
        shp.name = name
    return shp


def _flat(shp):
    st = shp._element.find(qn("p:style"))
    if st is not None:
        shp._element.remove(st)


def _ends(ln, head, tail):
    """Arrowheads; headEnd must come before tailEnd inside <a:ln>."""
    for tag, on in (("a:headEnd", head), ("a:tailEnd", tail)):
        if on:
            el = etree.SubElement(ln, qn(tag))
            el.set("type", "triangle")
            el.set("w", "med")
            el.set("len", "med")


def line(s, pts, color=INK, w=1.5, dash=None, tail=True, head=False, name=None):
    """Orthogonal or straight route through `pts` (inches). Two points -> straight connector, more -> one freeform polyline."""
    if len(pts) == 2:
        (x1, y1), (x2, y2) = pts
        shp = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    else:
        ff = s.shapes.build_freeform(I(pts[0][0]), I(pts[0][1]), scale=1.0)
        ff.add_line_segments([(I(x), I(y)) for x, y in pts[1:]], close=False)
        shp = ff.convert_to_shape()
        shp.fill.background()
        shp.shadow.inherit = False
    shp.line.color.rgb = rgb(color)
    shp.line.width = Pt(w)
    if dash:
        shp.line.dash_style = dash
    _ends(shp.line._get_or_add_ln(), head, tail)
    _flat(shp)
    if name:
        shp.name = name
    return shp


def can(s, x, y, w, h, paras, size=9, fill=STORE_F, line_=STORE, adj=0.18, **kw):
    return box(s, x, y, w, h, paras, kind=CAN, fill=fill, line=line_, lw=1.0, size=size, adj=adj, **kw)


def num(s, x, y, n, color, d=0.26, size=10):
    return box(s, x, y, d, d, str(n), kind=OVAL, fill=color, size=size, bold=True, color=WHITE, margin=0)


def pill(s, x, y, w, text, fill, color=WHITE, h=0.22, size=8.5, line_=None, dash=None):
    return box(s, x, y, w, h, text, fill=fill, line=line_, dash=dash, size=size, bold=True, color=color, margin=0.02,
               radius=h / 2)


def new_slide(prs, title):
    layout = next(l for l in prs.slide_masters[0].slide_layouts if l.name == "TITLE_ONLY_1")
    s = prs.slides.add_slide(layout)
    for ph in list(s.placeholders):
        if ph.placeholder_format.type != 1:
            ph._element.getparent().remove(ph._element)
    t = s.shapes.title
    t.left, t.top, t.width, t.height = Inches(0.34), Inches(0.32), Inches(9.32), Inches(0.63)
    t.text_frame.text = title
    for r in t.text_frame.paragraphs[0].runs:
        r.font.size = Pt(30)
    return s


def notes(s, text):
    s.notes_slide.notes_text_frame.text = text


def not_built(s, x, y, w, h, text, size=9):
    b = box(s, x, y, w, h, None, fill=None, line=MUTE, lw=1, dash=DASH, name="not built")
    tx(s, x + 0.08, y + 0.05, w - 0.16, h - 0.08, [[("Not built: ", dict(bold=True)), text]], size=size, color=GREY,
       anchor="m")
    return b


# ------------------------------------------------------------------------------------------ 1. system map
def system_map(prs):
    s = new_slide(prs, "System Architecture: End to End")

    # runtime boundary
    box(s, 1.75, 1.3, 6.0, 3.2, fill=None, line=MUTE, lw=1, dash=DASH, kind=RECT, name="boundary: LangGraph")
    tx(s, 1.85, 4.24, 3.0, 0.2, "LANGGRAPH STATEGRAPH · agents/graph.py", size=8.5, color=GREY, bold=True)

    # input
    tx(s, 0.35, 1.5, 1.2, 0.3, "from the ML team\n(Extra Trees)", size=9, color=GREY, italic=True, align="c")
    box(s, 0.35, 1.85, 1.2, 1.75, [
        dict(runs=[("Anomaly payload", dict(bold=True, size=10))], after=3),
        dict(runs=["store 7"], font=MONO, size=8.5),
        dict(runs=["dept 72"], font=MONO, size=8.5),
        dict(runs=["wk 2012-08-24"], font=MONO, size=8.5),
        dict(runs=["exp  45,010"], font=MONO, size=8.5),
        dict(runs=["act  33,958"], font=MONO, size=8.5),
        dict(runs=[("−24.6%", dict(bold=True, color=ERR, size=11))], before=3)],
        line=INK, lw=1, align="l", anchor="t", margin=0.1, name="payload")
    line(s, [(1.55, 2.725), (1.9, 2.725)])

    # orchestrator
    box(s, 1.9, 2.0, 1.25, 1.45, [dict(runs=[("Orchestrator", dict(bold=True, size=11.5))], after=4),
                                  "intake → plan", ("rules · no LLM", )], fill=ORCH, color=WHITE, size=9, name="Orchestrator")
    # agents
    box(s, 4.15, 2.0, 1.6, 0.6, [[("Evidence Agent", dict(bold=True, size=11))], "pandas · 6 checks"],
        fill=EVID, color=WHITE, size=9, name="Evidence Agent")
    box(s, 4.15, 2.85, 1.6, 0.6, [[("RAG Agent", dict(bold=True, size=11))], "filter → search → rank"],
        fill=RAG, color=WHITE, size=9, name="RAG Agent")
    can(s, 4.3, 1.36, 1.3, 0.46, ["Sales data · 6 CSVs", "421,570 rows"], size=8.5)
    can(s, 4.3, 3.62, 1.3, 0.5, ["ChromaDB", "6,560 chunks"], size=8.5)
    line(s, [(4.95, 1.82), (4.95, 2.0)], color=STORE, w=1.25)
    line(s, [(4.95, 3.62), (4.95, 3.45)], color=STORE, w=1.25)
    # tasks out, results back
    line(s, [(3.15, 2.3), (4.15, 2.3)])
    tx(s, 3.17, 2.08, 0.96, 0.2, "evidence task", size=9, align="c")
    line(s, [(3.15, 3.15), (4.15, 3.15)])
    tx(s, 3.17, 2.93, 0.96, 0.2, "RAG task", size=9, align="c")
    tx(s, 3.2, 2.62, 0.9, 0.2, "run in parallel", size=9, color=GREY, italic=True, align="c")
    line(s, [(5.75, 2.3), (6.45, 2.3)], color=EVID, w=2)
    tx(s, 5.75, 2.08, 0.7, 0.2, "metrics", size=9, color=EVID, align="c", bold=True)
    line(s, [(5.75, 3.15), (6.45, 3.15)], color=RAG, w=2)
    tx(s, 5.75, 2.93, 0.7, 0.2, "quotes", size=9, color=RAG, align="c", bold=True)

    # reasoning + LLM
    box(s, 6.45, 2.0, 1.15, 1.45, [dict(runs=[("Reasoning Agent", dict(bold=True, size=11))], after=4),
                                  "rules decide", "LLM explains", "guard checks"], fill=REAS, color=WHITE, size=9,
        name="Reasoning Agent")
    box(s, 6.3, 4.65, 1.45, 0.5, ["LLM API (optional)", "OpenRouter · Anthropic"], fill=WHITE, line=REAS, lw=1.25,
        dash=DASH, size=8.5, name="LLM API")
    line(s, [(6.8, 3.45), (6.8, 4.65)], color=INK, w=1.25, dash=DASH)
    line(s, [(7.25, 4.65), (7.25, 3.45)], color=REAS, w=1.5, dash=DASH)
    tx(s, 6.15, 3.85, 0.6, 0.2, "facts", size=9, align="r")
    tx(s, 7.3, 3.85, 0.45, 0.2, "draft", size=9, color=REAS, bold=True)

    # offline ingest
    box(s, 0.35, 3.62, 1.2, 0.5, ["agents.ingest", "59 reports"], fill=WHITE, line=MUTE, dash=DASH, size=8.5, name="ingest")
    line(s, [(1.55, 3.87), (4.3, 3.87)], color=MUTE, w=1.25, dash=DASH)
    tx(s, 1.85, 3.66, 1.6, 0.2, "offline: build index", size=9, color=GREY, italic=True)

    # dashboard
    box(s, 8.05, 1.65, 1.6, 2.15, None, line=INK, lw=1, name="dashboard")
    tx(s, 8.13, 1.72, 1.45, 0.22, "Streamlit dashboard", size=9.5, bold=True)
    pill(s, 8.13, 2.0, 1.45, "Needs review · Medium", ERR_T, color=ERR, size=8.5)
    for i, t in enumerate(["Possible factors", "Bottom line, next steps", "Source quotes (6)", "Live agent trace", "Follow-up chat"]):
        box(s, 8.13, 2.3 + i * 0.28, 1.45, 0.23, t, fill="ECEAE0", size=8.5, align="l", margin=0.06, radius=0.03)
    line(s, [(7.6, 2.725), (8.05, 2.725)], color=REAS, w=2)
    tx(s, 7.6, 2.5, 0.45, 0.2, "report", size=9, color=REAS, bold=True, align="c")

    # follow-up loop
    line(s, [(8.85, 1.65), (8.85, 1.08), (2.525, 1.08), (2.525, 2.0)], color=GREY, w=1.25, dash=DOT)
    tx(s, 5.75, 1.11, 2.95, 0.18, "follow-up question → route → tool → answer", size=9, color=GREY, italic=True, align="r")

    tx(s, 8.05, 3.95, 1.6, 1.4, [
        dict(runs=["Each node appends a trace entry (action, numbers, ms); graph.stream() pushes it to the dashboard live."], after=5),
        dict(runs=[("Median run, Store 7: ", dict(bold=True)), "evidence 0.03 s · RAG 4.1 s · reasoning incl. LLM 7.7 s"])],
        size=8.5, color=GREY)

    # legend
    lx, ly = 0.35, 4.72
    items = [(INK, None, "task / request"), (EVID, None, "result, agent colour"), (MUTE, DASH, "offline build"),
             (GREY, DOT, "follow-up")]
    for i, (c, d, t) in enumerate(items):
        x = lx + [0, 1.45, 3.15, 4.6][i]
        line(s, [(x, ly + 0.1), (x + 0.35, ly + 0.1)], color=c, w=1.75 if c in (EVID,) else 1.25, dash=d)
        tx(s, x + 0.42, ly, 1.3, 0.2, t, size=9, color=GREY)
    box(s, lx, ly + 0.36, 0.35, 0.2, None, fill=ORCH)
    tx(s, lx + 0.42, ly + 0.36, 1.6, 0.2, "deterministic Python", size=9, color=GREY)
    box(s, lx + 1.95, ly + 0.36, 0.35, 0.2, None, fill=WHITE, line=REAS, dash=DASH)
    tx(s, lx + 2.37, ly + 0.36, 1.3, 0.2, "LLM call (optional)", size=9, color=GREY)
    can(s, lx + 3.85, ly + 0.33, 0.35, 0.26, None, adj=0.25)
    tx(s, lx + 4.27, ly + 0.36, 1.3, 0.2, "in-process store", size=9, color=GREY)

    notes(s, """SYSTEM ARCHITECTURE — one flagged week, end to end. Running example: Store 7, Dept 72 Electronics, week ending Aug 24, 2012.

1. INPUT. The ML team's detector (Extra Trees) flags a store × department × week and hands us a JSON payload: store, department, week, expected $45,010 vs actual $33,958 (−24.6%). The question is always the same: why is this week below expected?

2. ORCHESTRATOR. A LangGraph state graph (agents/graph.py). Two nodes: intake normalizes any of the three payload formats into one internal payload; plan computes cheap signals (calendar, fuel, weather) and writes one task per agent. It is rules, not an LLM: the payload already states the question, so there is no intent to guess.

3. EVIDENCE AND RAG IN PARALLEL. Both nodes hang off plan, so LangGraph runs them in the same step. The Evidence Agent runs six parameterized pandas checks on the Kaggle sales data (421,570 rows, loaded once). The RAG Agent filters, searches and re-ranks 6,560 report chunks in ChromaDB. Both stores are in-process; nothing here calls an LLM.

4. REASONING. Rules decide the verdict and confidence from the metrics and quotes. Optionally an LLM (OpenRouter free models or Anthropic) rewrites the explanation in plain words; a guard checks every number and quote it uses, and if anything fails the rule-written text is used. The LLM never changes the verdict.

5. DASHBOARD. The Streamlit app shows the verdict, possible factors, source quotes and a live trace (every node streams a trace entry). Follow-up questions go through a second small graph: route → tool → answer.

Offline (dashed): agents.ingest builds the vector store once from 59 reports. It is not part of the request path.

Timing (median of 3 runs, Store 7, last export): evidence 26 ms, RAG 4.1 s, reasoning including the LLM call 7.7 s, about 12 s in total.""")
    return s


# ------------------------------------------------------------------------------------------ 2. orchestrator
def orchestrator(prs):
    s = new_slide(prs, "Orchestrator: Payload to Two Tasks")
    tx(s, 0.35, 1.06, 9.3, 0.25, [[("Fixed question in every payload:  ", dict(bold=True, color=ORCH)),
                                   ("why did this store / department / week come in below expected?", dict(italic=True))]], size=11)

    # input payload
    box(s, 0.35, 1.5, 2.35, 2.75, None, line=INK, lw=1, name="incoming payload")
    tx(s, 0.47, 1.58, 2.15, 0.4, [[("Incoming payload", dict(bold=True, size=10))],
                                   [("Extra Trees hand-off (JSON)", dict(color=GREY, size=9))]])
    tx(s, 0.47, 2.02, 2.15, 2.15, ["case.store_id: 7", "case.department_id: 72", "case.week_start_date:", '  "2012-08-24"',
                                   "sales.expected_sales:", "  45010.06", "sales.actual_sales:", "  33957.54",
                                   "detector.model:", '  "ExtraTreesRegressor"'], size=8.5, font=MONO, spacing=1)
    line(s, [(2.7, 2.5), (3.1, 2.5)])

    # orchestrator panel
    box(s, 2.95, 1.5, 3.0, 2.75, None, fill=ORCH_T, line=ORCH, lw=1.25, name="Orchestrator panel")
    tx(s, 3.07, 1.57, 1.9, 0.22, "Orchestrator", size=10.5, bold=True, color=ORCH)
    pill(s, 4.6, 1.57, 1.25, "RULES · NO LLM", ORCH)

    box(s, 3.1, 1.9, 2.7, 1.12, None, line=ORCH, lw=0.75, name="intake")
    tx(s, 3.2, 1.95, 2.55, 0.2, [[("intake  ", dict(bold=True)), ("payload_kind()", dict(font=MONO, size=8.5, color=GREY))]],
       size=9.5)
    for x, w, t, sel in [(3.2, 1.12, "department_week", True), (4.39, 0.74, "store_week", False), (5.2, 0.55, "internal", False)]:
        pill(s, x, 2.2, w, t, ORCH if sel else WHITE, color=WHITE if sel else ORCH, line_=None if sel else ORCH, size=8, h=0.21)
    tx(s, 3.2, 2.48, 2.55, 0.5, ["Normalize to one internal payload; add public mappings: Electronics → Entertainment unit,"
                                 " Colorado → Kansas City Fed district."], size=8.5, color=INK)
    line(s, [(4.45, 3.02), (4.45, 3.13)], color=ORCH, w=1.25)
    box(s, 3.1, 3.13, 2.7, 1.02, None, line=ORCH, lw=0.75, name="plan")
    tx(s, 3.2, 3.17, 2.55, 0.95, [
        dict(runs=[("plan  ", dict(bold=True, size=9.5)), ("signals() · build_queries()", dict(font=MONO, size=8.5, color=GREY))],
             after=2),
        "calendar: no holiday, no Easter / Christmas shift",
        "fuel $3.56 vs $3.49 LY (+2.1%) · 59°F vs 58°F",
        [("queries: ", dict(bold=True)), ("category ✓  demand ✓", dict(color=OK, bold=True))],
        [("skipped: ", dict(color=GREY)), ("event, fuel (<8%), weather (<8°F)", dict(color=GREY))]], size=8.5, spacing=1)

    # branches
    line(s, [(5.8, 3.45), (6.08, 3.45), (6.08, 2.15), (6.3, 2.15)])
    line(s, [(5.8, 3.75), (6.3, 3.75)])
    box(s, 6.3, 1.5, 3.35, 1.3, None, fill=EVID_T, line=EVID, lw=1.25, name="evidence task")
    tx(s, 6.42, 1.56, 3.15, 0.22, [[("Evidence task", dict(bold=True, color=EVID)), ("  → Evidence Agent", dict(color=GREY))]],
       size=10)
    tx(s, 6.42, 1.83, 3.15, 0.95, ["grain: department_week → 6 checks", "store 7 · dept 72 (Electronics)",
                                   "week 2012-08-24 · FY2013 Q3", "region Colorado · unit Entertainment",
                                   "expected 45,010.06 (Extra Trees)"], size=8.5, font=MONO, spacing=1)
    box(s, 6.3, 2.95, 3.35, 1.3, None, fill=RAG_T, line=RAG, lw=1.25, name="RAG task")
    tx(s, 6.42, 3.01, 3.15, 0.22, [[("RAG task", dict(bold=True, color=RAG)), ("  → RAG Agent", dict(color=GREY))]], size=10)
    tx(s, 6.42, 3.28, 3.15, 0.95, ['category: "electronics sales and comp',
                                   '  trend, entertainment business, …"',
                                   'demand: "retail sales and consumer',
                                   '  spending, back-to-school"',
                                   "time: wk 2012-08-24 · 21-day grace",
                                   "place: National, Kansas City · k=6"], size=8.5, font=MONO)

    # coordination
    box(s, 0.35, 4.45, 5.6, 0.9, None, line=ORCH, lw=0.75, name="hand-off")
    tx(s, 0.47, 4.52, 1.45, 0.75, [[("Hand-off", dict(bold=True, color=ORCH, size=10))],
                                   [("fan-out, then join on shared state", dict(color=GREY))]], size=8.5)
    pill(s, 2.05, 4.55, 0.9, "evidence", EVID, h=0.26, size=9)
    pill(s, 2.05, 4.98, 0.9, "rag", RAG, h=0.26, size=9)
    tx(s, 2.05, 4.82, 0.9, 0.16, "same step", size=8.5, color=GREY, italic=True, align="c")
    box(s, 3.35, 4.76, 1.15, 0.28, [[("state ", dict(bold=True)), ("{ev, rag}", dict(font=MONO))]], fill=STORE_F,
        line=STORE, size=8.5)
    pill(s, 4.9, 4.76, 0.9, "reason", REAS, h=0.28, size=9)
    line(s, [(2.95, 4.68), (3.15, 4.68), (3.15, 4.9), (3.35, 4.9)], color=EVID, w=1.5)
    line(s, [(2.95, 5.11), (3.15, 5.11), (3.15, 4.9)], color=RAG, w=1.5, tail=False)
    line(s, [(4.5, 4.9), (4.9, 4.9)], color=INK, w=1.25)
    tx(s, 3.35, 5.08, 2.5, 0.2, "reason starts when both keys are written", size=8.5, color=GREY, italic=True)

    box(s, 6.3, 4.45, 3.35, 0.9, None, line=GREY, lw=1, dash=DOT, name="follow-up routing")
    tx(s, 6.42, 4.5, 3.15, 0.85, [
        dict(runs=[("Follow-up questions: selective", dict(bold=True, size=9.5, color=ORCH))], after=2),
        [("chat.route()", dict(font=MONO)), " keyword router, 9 intents"],
        "“How did Store 41 do?” → store lookup tool",
        "other intents → reuse evidence already gathered",
        [("LLM router: not built", dict(color=GREY, italic=True))]], size=8.5)

    notes(s, """ORCHESTRATOR — how one payload becomes two retrieval tasks.

What it is: two LangGraph nodes, intake and plan (agents/graph.py). Both are deterministic Python. There is no LLM here, on purpose: every payload asks the same question (why is this week below expected?), so the work is decomposing a known question, not interpreting free text.

1. Receive. The payload arrives as JSON. Left: the Extra Trees hand-off for Store 7, Dept 72, week of Aug 24, 2012.

2. Intake. payload_kind() recognizes one of three formats: the Extra Trees hand-off (store × department × week), the primary anomaly payload (store × week), or an already-normalized internal payload. payload_from_handoff() turns any of them into one internal payload and joins the public mapping tables: Dept 72 → Electronics in the Entertainment merchandise unit, Store 7 → Colorado → Kansas City Fed district. These mappings are publicly inferred, with High / Medium / Unresolved confidence.

3. Plan. signals() computes cheap context: is there a holiday or an Easter / Christmas shift vs last year, how fuel and temperature compare with the same week last year. build_queries() then chooses which RAG queries to send: category and consumer demand are always sent; an event query only if the calendar flags a shift; fuel only if fuel moved more than 8%; weather only if temperature moved more than 8°F. For Store 7 none of those triggered, so two queries.

4. Tasks. The Evidence task is the normalized payload plus its grain, which selects the check set (6 department-week checks, or the store-level set for whole-store payloads). The RAG task is the query list plus the time and place filter: the week, a 21-day grace window, the national reports plus the store's Fed district, k = 6 passages.

5. Hand-off. Both agent nodes depend only on plan, so LangGraph runs them in the same step. Each writes its own key to the shared state (ev, rag); the reason node starts when both are written.

Selective routing: the main investigation always runs both agents, because every anomaly needs both the sales evidence and the report context. Routing is selective for follow-up questions: chat.route() is a keyword router with 9 intents. "How did Store 41 do?" calls the store-lookup tool; other questions reuse the evidence already gathered, with no new retrieval. An LLM-based router for free-text questions is a possible upgrade; it is not built.""")
    return s


# ------------------------------------------------------------------------------------------ 3. evidence
def evidence(prs):
    s = new_slide(prs, "Evidence Agent: Six Data Checks")
    for x, n, t in [(0.35, 1, "Task → check set"), (2.75, 2, "Run parameterized checks"), (7.3, 3, "Consolidate")]:
        num(s, x, 1.08, n, EVID, d=0.24, size=9.5)
        tx(s, x + 0.32, 1.1, 2.2, 0.22, t, size=10.5, bold=True, color=EVID)
    tx(s, 5.35, 1.13, 1.65, 0.2, "pandas · no LLM · no SQL", size=9, color=GREY, italic=True, align="r")
    line(s, [(2.08, 1.2), (2.65, 1.2)], color=EVID, w=1.25)
    line(s, [(7.08, 1.2), (7.25, 1.2)], color=EVID, w=1.25)

    # task card
    box(s, 0.35, 1.5, 2.15, 1.45, None, fill=EVID_T, line=EVID, lw=1, name="evidence task")
    tx(s, 0.45, 1.55, 2.0, 1.38, [
        dict(runs=[("from the orchestrator", dict(font=FONT, color=GREY, size=9))], after=2),
        [("grain=department_week", dict(bold=True))], "→ 6 checks below", [("(store_week grain →", dict(color=GREY))],
        [(" 7 store-level checks)", dict(color=GREY))],
        "store=7  dept=72", "week=2012-08-24", "quarter=FY2013 Q3", "last_year=week − 52"], size=8.5, font=MONO)

    # data layer
    tx(s, 0.35, 3.08, 2.2, 0.2, "Data layer · joined once at startup", size=9, bold=True, color=GREY)
    tables = [("train.csv", "421,570 sales rows"), ("features.csv", "MarkDown1–5, fuel"), ("stores.csv", "type, size"),
              ("dept_mapping", "name, unit"), ("store_mapping", "region, Fed district"), ("fiscal_calendar", "FY weeks")]
    for i, (n, d) in enumerate(tables):
        y = 3.33 + i * 0.3
        box(s, 0.35, y, 2.15, 0.26, [[(n, dict(font=MONO, bold=True)), (" " + d, dict(color=GREY))]], fill=STORE_F,
            line=STORE, lw=0.75, size=8.5, align="l", margin=0.06, radius=0.03)
    line(s, [(2.5, 4.2), (2.75, 4.2)], color=STORE, w=1.5)

    # six checks
    rows = [("Whole store down?", "store_week[7, wk] vs wk−52", ["−3.3%", "whole store vs LY"]),
            ("One-off or persistent?", "panel[7, 72, Q3]: Σsales / ΣLY", ["−12.7%", "9 of 13 wks down"]),
            ("Regional peers?", "panel[72, Colorado, ≠7, Q3]", ["−3.6% to +14.2%", "Stores 16, 41, 32"]),
            ("Whole chain?", "panel[72, all 45 stores, Q3]", ["−0.5%", "chain, same quarter"]),
            ("Promos, fuel, weather?", "features[7, wk] vs avg / LY", ["markdowns 0.6×", "fuel +2.1% · 59 vs 58°F"]),
            ("Calendar effect?", "holiday flag; Easter/Xmas vs LY", ["none", "no shift vs last year"])]
    for i, (q, e, r) in enumerate(rows):
        y = 1.5 + i * 0.63
        box(s, 2.75, y, 4.3, 0.55, None, line=EVID, lw=0.75, name=f"check {i + 1}")
        num(s, 2.84, y + 0.145, i + 1, EVID, d=0.26, size=9.5)
        tx(s, 3.2, y + 0.06, 2.35, 0.45, [[(q, dict(bold=True, size=10))], [(e, dict(font=MONO, size=8.5, color=GREY))]])
        tx(s, 5.6, y + 0.06, 1.42, 0.45, [[(r[0], dict(bold=True, color=EVID, size=10 if len(r[0]) > 12 else 11))],
                                           [(r[1], dict(color=GREY, size=8.5))]])
        line(s, [(7.05, y + 0.275), (7.15, y + 0.275)], color=EVID, w=1.25, tail=False)
    line(s, [(7.15, 1.775), (7.15, 1.5 + 5 * 0.63 + 0.275)], color=EVID, w=1.25, tail=False)
    line(s, [(7.15, 3.35), (7.3, 3.35)], color=EVID, w=1.5)

    # evidence package
    box(s, 7.3, 1.5, 2.35, 2.45, None, line=EVID, lw=1, name="state.ev")
    tx(s, 7.4, 1.56, 2.2, 0.2, [[("state.ev", dict(font=MONO, bold=True, color=EVID)), ("  evidence package", dict(color=GREY))]],
       size=9.5)
    tx(s, 7.4, 1.82, 2.2, 2.1, ["dept_quarter_yoy: -0.127", "weeks_down: 9 / 13", "chain_dept_q_yoy: -0.005",
                                "peers_q: 16, 41, 32", "store_week_yoy: -0.033", "markdown: 8,099",
                                "markdown_avg: 13,770", "fuel: 3.558 (ly 3.485)", "calendar_flags: []",
                                "quarter_window:", "  2012-08-03..10-26", "+ trend, siblings, units"], size=8.5, font=MONO)
    line(s, [(8.475, 3.95), (8.475, 4.12)], color=REAS, w=1.5)
    pill(s, 7.3, 4.12, 2.35, "→ graph state → Reasoning Agent", REAS, h=0.26, size=9)
    tx(s, 7.3, 4.47, 2.35, 0.3, "Named fields + time windows: every value can be recomputed from the CSVs.", size=8.5, color=GREY)
    not_built(s, 7.3, 4.9, 2.35, 0.42, "LLM-written queries with a read-only validator", size=8.5)

    notes(s, """EVIDENCE AGENT — what the sales data says about the flagged week.

What it is: deterministic Python (agents/engine.py, evidence_agent). No LLM and no SQL. The six Kaggle / mapping CSVs are loaded once at startup and joined into two in-memory tables: a store × department × week panel (with the same week last year and the expected value) and store-week totals. Each check is a fixed pandas filter + group-by + ratio whose parameters come from the task.

1. Task → check set. The grain picks the check set: department-week payloads get the six checks shown; whole-store payloads get a store-level set (baseline composition, same week last year, all 45 stores, next four weeks, December-peak departments, promotions / fuel / weather). Parameters are bound from the payload: store 7, dept 72, week, fiscal quarter, region, and last year = week − 52 weeks (Walmart weeks align at 52).

2. Run the checks (Store 7 Electronics values):
 1 Whole store down? The store as a whole was only −3.3% vs last year that week, so the problem is not store-wide.
 2 One-off or persistent? Electronics −12.7% over the quarter, below last year in 9 of 13 weeks.
 3 Regional peers? Other Colorado stores, same department, same quarter: Store 16 −3.6%, Store 41 +2.8%, Store 32 +14.2%.
 4 Whole chain? All 45 stores: −0.5%.
 5 Promotions, fuel, weather? Store markdowns about 0.6× an average week; fuel +2.1%; 59°F vs 58°F.
 6 Calendar? No holiday and no Easter / Christmas shift vs last year.

3. Consolidate. The results are written as named fields to the graph state key ev, with their time windows, plus the trend series, sibling departments and merchandise-unit totals. That package goes to the Reasoning Agent through LangGraph state. The Evidence Agent never writes the answer.

Note on 'Markdown': MarkDown1–5 in features.csv are anonymized promotional markdown dollars per store-week. They are structured numbers used in check 5, not Markdown-format documents. There are no Markdown reports in this project.

Note on the window: 'this quarter' is the full fiscal quarter capped at 12 weeks before the flagged week, so it also includes weeks after the flagged week (here Aug 3 – Oct 26). That is fine for a retrospective investigation, not for real-time use.

Not built: LLM-written queries (text-to-pandas or SQL) behind a read-only validator. The fixed checks were chosen because they are testable and fast (≈26 ms per case).""")
    return s


# ------------------------------------------------------------------------------------------ 4. RAG
def rag(prs):
    s = new_slide(prs, "RAG Agent: Indexing and Retrieval")

    # offline band
    box(s, 0.35, 1.02, 9.3, 1.28, None, kind=RECT, fill=BAND, line=MUTE, lw=0.75, dash=DASH, name="offline band")
    tx(s, 0.45, 1.06, 6.0, 0.2, [[("OFFLINE INDEXING", dict(bold=True, color=GREY)),
                                  ("   python3 -m agents.ingest · run once · 133 s", dict(color=GREY))]], size=8.5)
    box(s, 0.45, 1.3, 1.65, 0.92, [
        dict(runs=[("59 source files (.txt)", dict(bold=True, size=9))], after=1),
        "Earnings releases 11", "Earnings calls 11", "10-K 4 · annual report 4", "Comp sales 2 · NRF 3", "Fed Beige Books 24"],
        size=8, line=MUTE, lw=0.75, align="l", anchor="t", margin=0.06, name="sources")
    steps = [("Clean", "page nos.,\nquotes, spaces"), ("Split", "Beige Books by\n12 Fed districts"),
             ("Chunk", "≈900 chars, 150\noverlap, sentences"), ("Prose filter", "drops 299\ntable chunks")]
    xs = [2.3, 3.55, 4.8, 6.05]
    for x, (t, d) in zip(xs, steps):
        box(s, x, 1.42, 1.05, 0.68, [[(t, dict(bold=True, size=9))], d], size=8, line=MUTE, lw=0.75)
    for a, b in [(2.1, 2.3), (3.35, 3.55), (4.6, 4.8), (5.85, 6.05)]:
        line(s, [(a, 1.76), (b, 1.76)], color=MUTE, w=1.25, dash=DASH)
    line(s, [(7.1, 1.76), (7.3, 1.76)], color=MUTE, w=1.25, dash=DASH)
    chips = [("chunk text", "≈814 chars avg"), ("metadata", "doc_type, district, dates"), ("vector", "MiniLM-L6 · 384-d")]
    for i, (t, d) in enumerate(chips):
        box(s, 7.3, 1.33 + i * 0.3, 2.25, 0.26, [[(t, dict(bold=True)), ("  " + d, dict(color=GREY))]], size=8.5, line=MUTE,
            lw=0.75, align="l", radius=0.03)
    for xx in (7.7, 8.4, 9.1):
        line(s, [(xx, 2.22), (xx, 2.42)], color=MUTE, w=1.25, dash=DASH)

    # vector database: shared
    can(s, 0.9, 2.38, 8.7, 0.62, None, adj=0.22, fill=STORE_F, name="ChromaDB")
    tx(s, 1.1, 2.55, 8.3, 0.42, [
        [("ChromaDB", dict(bold=True, size=10)), ("  collection walmart_reports · 6,560 records · HNSW, cosine · 60.7 MB   ", {}),
         ("record = id + text + metadata + vector", dict(bold=True))],
        [("metadata: ", dict(color=GREY)),
         ("doc_id, doc_type, publisher, evidence_type, district, published, period_start, period_end, source_file, chunk_index",
          dict(font=MONO, color=GREY, size=8))]], size=9, align="c")

    # online band
    box(s, 0.35, 3.08, 9.3, 2.3, None, kind=RECT, fill=WHITE, line=RAG, lw=0.75, name="online band")
    tx(s, 0.45, 3.13, 1.6, 0.2, "ONLINE RETRIEVAL", size=8.5, bold=True, color=RAG)
    tx(s, 4.2, 3.13, 3.4, 0.2, "per anomaly · ≈4 s · agents/rag.py", size=8.5, color=GREY, align="r")
    box(s, 0.45, 3.42, 0.95, 0.5, [[("RAG task", dict(bold=True))], "2 queries"], fill=RAG_T, line=RAG, lw=0.75, size=8.5)
    cols = [(1.6, 1.45, "Metadata filter", "6,560 → 705 chunks", "7 of 59 reports",
             "Inside ChromaDB, before the search. Time: period covers the week, or published / ended ≤21 days before. "
             "Place: National + Kansas City."),
            (3.25, 1.15, "Vector search", "2 × top 25 → 42", "unique candidates",
             "Each query embedded (MiniLM); cosine top 25 per query; merged by chunk id."),
            (4.6, 1.6, "Re-rank", "top 30 re-scored", "sentence by sentence",
             "Not a cross-encoder. Each sentence embedded; score = .45 chunk sim + .55 best sentence + .25 keyword "
             "overlap + district / period boosts."),
            (6.4, 1.25, "Source-aware select", "→ 6 passages", "≤2 per report",
             "Reserve the best Walmart chunk and the best local Beige Book chunk; fill to k = 6 by score.")]
    for i, (x, w, t, n1, n2, d) in enumerate(cols):
        box(s, x, 3.42, w, 0.5, [[(t, dict(bold=True, size=9.5))]], fill=RAG, color=WHITE, size=9)
        num(s, x - 0.11, 3.31, i + 1, INK, d=0.22, size=8.5)
        tx(s, x, 3.99, w, 0.8, d, size=8.5, color=INK)
        tx(s, x, 4.9, w, 0.42, [[(n1, dict(bold=True, color=RAG, size=9.5))], [(n2, dict(color=GREY, size=8.5))]])
    for a, b in [(1.4, 1.6), (3.05, 3.25), (4.4, 4.6), (6.2, 6.4)]:
        line(s, [(a, 3.67), (b, 3.67)], color=RAG, w=1.5)
    # chroma -> filter + search (online read)
    line(s, [(2.33, 3.0), (2.33, 3.42)], color=RAG, w=1.5)
    line(s, [(3.83, 3.0), (3.83, 3.42)], color=RAG, w=1.5)
    tx(s, 0.45, 4.9, 1.05, 0.42, [[("Store 7 run", dict(bold=True, color=RAG))], [("measured", dict(color=GREY))]], size=8.5)
    not_built(s, 0.45, 3.99, 1.0, 0.78, "cross-encoder, per-type quotas, query rewrite", size=8)

    # package -> reasoning
    line(s, [(7.65, 3.67), (7.85, 3.67)], color=RAG, w=1.5)
    box(s, 7.85, 3.2, 1.72, 2.1, None, fill=RAG_T, line=RAG, lw=1, name="returned passages")
    num(s, 7.74, 3.09, 5, INK, d=0.22, size=8.5)
    tx(s, 7.95, 3.27, 1.58, 2.0, [
        dict(runs=[("Package → Reasoning", dict(bold=True, color=RAG, size=9))], after=3),
        dict(runs=[("Walmart calls · 4", dict(bold=True))], after=0),
        dict(runs=["“Within entertainment, deflation continues to impact sales growth in electronics.”"], after=3, italic=True),
        dict(runs=[("Beige Book, KC · 1", dict(bold=True))], after=0),
        dict(runs=["“…back-to-school items sold well…”"], after=3, italic=True),
        dict(runs=[("Beige Book, national · 1", dict(bold=True))], after=3),
        dict(runs=[("each: quote, doc, date, district, score, chunk_id", dict(color=GREY))])], size=8)

    notes(s, """RAG AGENT — two separate workflows sharing one vector store.

OFFLINE INDEXING (top, dashed): python3 -m agents.ingest, run once, about 2 minutes. Not part of any request.
• Sources: 59 original files — Walmart earnings releases (11), earnings call transcripts (11), 10-Ks (4), annual-report MD&A (4), comp-sales disclosures (2), Fed Beige Books (24), NRF holiday forecasts (3). All plain text; there are no Markdown-format reports. EIA fuel files are kept in sources/ but are not embedded; fuel prices come from features.csv.
• Each file inherits metadata from a registry built from the file names, the Walmart fiscal calendar and MANIFEST.csv: report type, publisher, published date, and the period it covers.
• Clean the text (page numbers, curly quotes, whitespace). Split Beige Books by the 12 Fed districts so every chunk knows which district it describes.
• Chunk to about 900 characters with 150 characters of overlap, cut at sentence boundaries. A prose filter drops 299 chunks that are mostly numbers or tables (6,859 → 6,560).
• ChromaDB embeds each chunk with all-MiniLM-L6-v2 (ONNX, 384 dimensions) and stores id + text + metadata + vector in one HNSW cosine collection (60.7 MB).

ONLINE RETRIEVAL (bottom, solid): per anomaly, about 4 seconds. Store 7 numbers are from a real run.
1 Metadata filter, applied inside ChromaDB before the vector search. Time: the report's period covers the week, or it was published or its period ended in the 21 days before. Place: national reports plus the store's Fed district (Kansas City). 6,560 → 705 chunks from 7 of 59 reports.
2 Vector search: each of the 2 queries is embedded and the top 25 chunks by cosine similarity are returned; merged by chunk id → 42 unique candidates.
3 Re-rank: a second, finer score, not a cross-encoder. The 30 best candidates are split into sentences, every sentence is embedded, and the score combines chunk similarity, best-sentence similarity, keyword overlap and small boosts for the local district and for reports covering the week.
4 Source-aware selection: one slot is reserved for the best Walmart chunk and one for the best local-district Beige Book chunk; the rest are filled by score up to k = 6, with at most 2 chunks per report. This keeps both Walmart and regional context in the answer. The counts per source are not fixed: they depend on what passes the filter and what scores well.
5 Package: each passage carries the chunk text, the best-matching sentence as a verbatim quote, document, date, district, how it relates to the week, score and chunk id. These go to the Reasoning Agent through graph state. The RAG Agent does not write an answer.

Not built: a cross-encoder re-ranker, fixed per-document-type quotas, LLM query rewriting.""")
    return s


# ------------------------------------------------------------------------------------------ 5. reasoning
def reasoning(prs):
    s = new_slide(prs, "Reasoning Agent: Rules, LLM, Guard")

    # inputs
    box(s, 0.35, 1.15, 1.45, 1.15, None, fill=EVID_T, line=EVID, lw=1, name="from evidence")
    tx(s, 0.43, 1.2, 1.32, 1.08, [dict(runs=[("From Evidence", dict(bold=True, color=EVID, size=9.5))], after=2),
                                  dict(runs=["named metrics"], color=GREY, after=2),
                                  dict(runs=["store −12.7%"], font=MONO), dict(runs=["chain −0.5%"], font=MONO),
                                  dict(runs=["9/13 wks down"], font=MONO), dict(runs=["markdown 0.6×"], font=MONO)], size=8.5)
    box(s, 0.35, 2.45, 1.45, 1.1, None, fill=RAG_T, line=RAG, lw=1, name="from RAG")
    tx(s, 0.43, 2.5, 1.32, 1.02, [dict(runs=[("From RAG", dict(bold=True, color=RAG, size=9.5))], after=2),
                                  dict(runs=["6 passages: verbatim quote, source, date, district"], after=3),
                                  dict(runs=["4 Walmart · 2 Fed"], font=MONO)], size=8.5)
    line(s, [(1.8, 1.72), (2.05, 1.72)], color=EVID, w=2)
    line(s, [(1.8, 3.0), (2.05, 3.0)], color=RAG, w=2)

    # 1 align
    box(s, 2.05, 1.15, 1.4, 2.4, None, fill=REAS_T, line=REAS, lw=1, name="align")
    num(s, 2.13, 1.22, 1, REAS, d=0.24, size=9)
    tx(s, 2.43, 1.23, 1.0, 0.22, "Align", size=10, bold=True, color=REAS)
    tx(s, 2.13, 1.55, 1.27, 1.95, [dict(runs=["Pick the Walmart quote that names the category (deflation, electronics)."], after=4),
                                   dict(runs=["Pick the regional quote, preferring the store's district."], after=4),
                                   dict(runs=["Tag every factor: Data · Walmart · Regional · Calendar."])], size=8.5)
    line(s, [(3.45, 2.35), (3.65, 2.35)], color=REAS, w=1.5)

    # 2 decide
    box(s, 3.65, 1.15, 2.2, 2.4, None, line=REAS, lw=1, name="rule engine")
    num(s, 3.73, 1.22, 2, REAS, d=0.24, size=9)
    tx(s, 4.03, 1.23, 1.8, 0.22, "Decide (rules)", size=10, bold=True, color=REAS)
    box(s, 3.75, 1.5, 1.15, 0.62, "Just timing?", kind=DIAMOND, line=REAS, lw=1.25, size=8.5, bold=True, margin=0)
    pill(s, 5.03, 1.63, 0.75, "Likely explained", OK_T, color=OK, h=0.36, size=8)
    line(s, [(4.9, 1.81), (5.03, 1.81)], color=OK, w=1.25)
    tx(s, 4.88, 1.52, 0.3, 0.16, "yes", size=8.5, color=OK, bold=True)
    line(s, [(4.325, 2.12), (4.325, 2.25)], color=ERR, w=1.25)
    tx(s, 4.4, 2.08, 0.3, 0.16, "no", size=8.5, color=ERR, bold=True)
    pill(s, 3.75, 2.25, 2.0, "Needs review · weigh factors", ERR_T, color=ERR, h=0.26, size=8.5)
    tx(s, 3.75, 2.56, 2.05, 0.3, "category trend · store vs chain · persistence · promotions · fuel", size=8, color=GREY)
    tx(s, 3.75, 2.9, 2.05, 0.6, [[("Confidence ", dict(bold=True)), ("starts High, −1 per limit", dict(color=GREY))],
                                 [("Store 7: ", dict(bold=True)), "store −12.2 pts vs chain → ",
                                  ("Medium", dict(bold=True, color=REAS))]], size=8.5)

    # python support
    box(s, 2.05, 3.75, 3.8, 0.62, None, fill=STORE_F, line=STORE, lw=0.75, name="python")
    tx(s, 2.15, 3.79, 3.65, 0.56, [[("Python (pandas / numpy) computes every number ", dict(bold=True)),
                                    ("before any LLM sees it", dict(bold=True, color=REAS))],
                                   [("gap = −12.7 − (−0.5) = −12.2 pts · md = 8,099/13,770", dict(font=MONO, size=8))]],
       size=8.5)
    line(s, [(2.75, 3.75), (2.75, 3.55)], color=STORE, w=1.25, dash=DOT, head=True)
    line(s, [(4.75, 3.75), (4.75, 3.55)], color=STORE, w=1.25, dash=DOT, head=True)

    # 3 report
    line(s, [(5.85, 2.0), (6.05, 2.0)], color=REAS, w=1.5)
    box(s, 6.05, 1.15, 1.45, 1.75, None, line=REAS, lw=1, name="report")
    num(s, 6.13, 1.22, 3, REAS, d=0.24, size=9)
    tx(s, 6.43, 1.23, 1.05, 0.22, "Report", size=10, bold=True, color=REAS)
    tx(s, 6.15, 1.52, 1.3, 1.35, ["verdict", "confidence", "factors[ ]", "ruled_out", "bottom_line", "review[ ]", "limitations[ ]",
                                  "quotes[chunk_id]"], size=8.5, font=MONO)

    # dashboard
    line(s, [(7.5, 2.0), (7.75, 2.0)], color=REAS, w=2)
    box(s, 7.75, 1.15, 1.9, 1.9, None, line=INK, lw=1, name="dashboard")
    tx(s, 7.83, 1.2, 1.75, 0.2, "Dashboard", size=9.5, bold=True)
    pill(s, 7.83, 1.45, 1.74, "Needs review · Medium", ERR_T, color=ERR, h=0.22, size=8.5)
    tx(s, 7.83, 1.74, 1.75, 1.3, [dict(runs=[("Falling electronics prices ", dict(bold=True)), ("Walmart+Data", dict(color=GREY))], after=2),
                                  dict(runs=[("A problem at this store ", dict(bold=True)), ("Data", dict(color=GREY))], after=2),
                                  dict(runs=[("Fewer promos, back-to-school ", dict(bold=True)), ("Data+Regional", dict(color=GREY))], after=2),
                                  dict(runs=[("Ruled out: ", dict(bold=True)), ("holiday, fuel, weather", dict(color=GREY))])], size=8)

    # 4 LLM writer + guard
    line(s, [(6.775, 2.9), (6.775, 3.35)], color=INK, w=1.25, dash=DASH)
    tx(s, 6.82, 3.02, 0.9, 0.2, "facts JSON", size=8.5)
    box(s, 6.05, 3.35, 1.45, 0.75, None, fill=WHITE, line=REAS, lw=1.25, dash=DASH, name="LLM writer")
    num(s, 6.13, 3.42, 4, REAS, d=0.22, size=8.5)
    tx(s, 6.4, 3.42, 1.05, 0.66, [[("LLM writer", dict(bold=True))], [("optional · 4 free models in order", dict(color=GREY, size=8))]],
       size=9)
    box(s, 7.75, 3.32, 0.9, 0.8, "Guard", kind=DIAMOND, line=OK, lw=1.5, size=9, bold=True, color=OK, margin=0)
    line(s, [(7.5, 3.72), (7.75, 3.72)], color=REAS, w=1.5, dash=DASH)
    tx(s, 8.7, 3.3, 0.98, 0.85, [dict(runs=["numbers ∈ facts"], after=2), dict(runs=["quotes verbatim"], after=2),
                                 "matches verdict"], size=8.5, color=OK, bold=True)
    line(s, [(8.2, 3.32), (8.2, 3.05)], color=OK, w=1.5)
    tx(s, 8.25, 3.08, 1.4, 0.2, "pass: plain-words text", size=8.5, color=OK)
    line(s, [(8.0, 3.93), (8.0, 4.3), (6.95, 4.3), (6.95, 4.1)], color=ERR, w=1.25, dash=DOT)
    tx(s, 6.98, 4.33, 1.1, 0.2, "fail: next model", size=8.5, color=ERR)
    line(s, [(8.2, 4.12), (8.2, 4.75), (7.5, 4.75)], color=ERR, w=1.25, dash=DOT)
    tx(s, 8.26, 4.5, 1.4, 0.2, "attempts used up", size=8.5, color=ERR)
    box(s, 6.05, 4.55, 1.45, 0.42, ["Rule text shown;", "verdict unchanged"], fill=ERR_T, line=ERR, lw=0.75, size=8.5,
        name="fallback")
    tx(s, 6.05, 5.05, 3.6, 0.3, "Last export: 9 runs → 5 LLM texts accepted, 0 rejected by the guard, 4 no answer (free models busy) → rule text",
       size=8.5, color=GREY)

    # built vs not built
    box(s, 0.35, 4.55, 0.85, 0.22, "BUILT", fill=OK, color=WHITE, size=8.5, bold=True, radius=0.11, margin=0)
    tx(s, 1.3, 4.565, 4.6, 0.2, "guard on every LLM text · confidence rules · listed limitations · bounded retries", size=8.5)
    not_built(s, 0.35, 4.88, 5.5, 0.47, "LLM-called Python tool (not needed) · re-retrieval when a check fails · "
                                        "people check: 2 teammates label ~10 weeks", size=8.5)

    notes(s, """REASONING AGENT — from retrieved evidence to a checked answer.

Design: rules decide, the LLM only explains, a guard checks the LLM (agents/reasoning.py, agents/llm.py).

Inputs. From the Evidence Agent: named metrics (Store 7 Electronics −12.7% this quarter, chain −0.5%, 9 of 13 weeks down, markdowns 0.6× normal). From the RAG Agent: 6 passages with verbatim quotes, source, date and district.

1 Align. Pick the Walmart quote whose sentence names the category (here: deflation in electronics) and the regional quote, preferring the store's own Fed district. Every factor is tagged with where it comes from: Data, Walmart, Regional or Calendar.

2 Decide (rules). First test: is it just timing? For a department-week, a holiday moved vs last year and the six weeks around it are within −10% of last year. For a whole-store week, the 4-week baseline contains Christmas, the week is within −10% of last year, and it fell about as much as the median store. Yes → 'Likely explained'. No → 'Needs review', and the rules weigh the category trend from Walmart's reports, the store vs chain and peer gap, persistence, promotions and fuel. Confidence starts at High and drops one level for each limit: a mapping that is not High confidence, a single-week drop, a calendar effect, no time-aligned report, or the store falling more than 5 points below the chain. Store 7 drops one level for the −12.2-point gap → Medium.

Python. All arithmetic is plain pandas / numpy in the Evidence Agent and the rules, before any LLM runs. The LLM never computes a number, so no LLM-called Python tool is needed.

3 Report. The rules produce a structured report: verdict, confidence, factors, ruled-out items, bottom line, next steps, limitations and the quotes with their chunk ids. This report always reaches the dashboard.

4 LLM writer (optional). The facts JSON (verdict, factors, quotes; no raw data) goes to an LLM: four free OpenRouter models tried in order, or Anthropic if that key is set. It writes 3–4 plain sentences.

Guard (built, runs on every LLM text): every number in the text must appear in the facts; every quotation must be a verbatim piece of a retrieved quote; the wording must not contradict the verdict (e.g. 'no action needed' on a Needs-review case). Pass → the text is shown as 'In plain words'. Fail → the next model in the chain is tried; each model gets one attempt, and a second round over the chain happens only if no model answered at all (rate limits). If nothing passes, the rule-written text is shown. The verdict and confidence never change.

Last export: 9 runs, 5 LLM texts accepted, 0 rejected by the guard, 4 with no answer because the free models were busy; those showed the rule-written text.

Not built: an LLM-called Python tool (not needed), re-retrieving evidence when a check fails, and the people check: two teammates will label about 10 flagged weeks (6 regular, 4 holiday-shift) for verdict and main factor, and we compare with the agent and check that High confidence is right more often than Medium. Not run yet.""")
    return s


def main(src, dst):
    prs = Presentation(src)
    n_old = len(prs.slides)
    for fn in (system_map, orchestrator, evidence, rag, reasoning):
        fn(prs)
    lst = prs.slides._sldIdLst
    for el in list(lst)[:n_old]:
        prs.part.drop_rel(el.get(qn("r:id")))
        lst.remove(el)
    prs.save(dst)
    print("saved", dst, "slides:", len(prs.slides))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
