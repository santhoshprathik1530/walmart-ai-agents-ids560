"""Walmart stakeholder deck: 8 slides on a white background in Walmart colours.

    1 Why an AI agent, not just a dashboard      2 AI agent knowledge sources
    3 System architecture   4 Orchestrator   5 Evidence Agent   6 RAG Agent   7 Reasoning + Evaluation + Dashboard
    8 How we will evaluate the agent

Slides 3-7 are the v3 architecture slides (build_architecture_v3.py) restyled and trimmed: same content, fewer labels.
Run-dependent values come from app/data/agent_outputs.json (Store 7 case); regenerate it first: cd app && python3 -m agents.export_outputs
Drawing helpers are shared with build_architecture_v2.py; LLM steps carry a Spark-yellow "LLM" tag.

Usage:  python3 build_walmart_deck.py "<output>.pptx"
"""
import io
import json
import re
import sys
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

from build_architecture_v2 import CAN, DASH, DIAMOND, DOT, MONO, OVAL, RECT, ROUND, box, line, notes, num, pill, tx
from build_architecture_v2 import can as _can

# Walmart palette
NAVY, BLUE, SPARK, GREEN, RED = "041E42", "0071DC", "FFC220", "2A8703", "EA1100"
INK, GREY, MUTE, WHITE = "1D1D1D", "5A5F66", "8A9099", "FFFFFF"
LIGHT, LINEC = "F4F6F9", "DDE2E8"
ORCH, ORCH_T = NAVY, "E8ECF3"
EVID, EVID_T = BLUE, "E6F1FC"
RAG, RAG_F, RAG_T = "4AA3DF", "A9DDF7", "EEF8FD"      # RAG: light-blue boxes with navy text; lines in a mid blue
REAS, REAS_F, REAS_T = "D99A00", SPARK, "FFF6DA"      # Reasoning: Spark-yellow boxes with navy text; lines in dark gold
OK, OK_T = GREEN, "EAF4E4"
ERR, ERR_T = RED, "FDE8E6"
AMBER, AMBER_T = "B95000", "FDEEDB"                   # Check before acting
STORE, STORE_F = "9AA3AE", "EEF1F5"
ICONS = Path(__file__).resolve().parent / "assets" / "icons"


def can(s, x, y, w, h, paras, size=9, **kw):
    kw.setdefault("fill", STORE_F)
    return _can(s, x, y, w, h, paras, size=size, line_=STORE, **kw)


def new_slide(prs, title, subtitle=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])                       # blank
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = RGBColor.from_string(WHITE)
    tx(s, 0.4, 0.28, 9.2, 0.5, [[(title, dict(bold=True, size=26, color=NAVY))]], name="Title")
    if subtitle:
        tx(s, 0.4, 0.8, 9.2, 0.3, subtitle, size=13, color=GREY, name="Subtitle")
    return s


def icon(s, name, x, y, d, circle, fg=WHITE):
    """Line icon (recoloured from assets/icons) on a filled circle."""
    box(s, x, y, d, d, None, kind=OVAL, fill=circle, name=f"icon {name}")
    src = sorted(ICONS.glob(f"{name}_*.png"))[0]
    im = Image.open(src).convert("RGBA")
    r, g, b = (int(fg[i:i + 2], 16) for i in (0, 2, 4))
    solid = Image.new("RGBA", im.size, (r, g, b, 255))
    solid.putalpha(im.getchannel("A"))
    buf = io.BytesIO()
    solid.save(buf, "PNG")
    buf.seek(0)
    pad = d * 0.24
    s.shapes.add_picture(buf, Inches(x + pad), Inches(y + pad), Inches(d - 2 * pad), Inches(d - 2 * pad))


ROOT = Path(__file__).resolve().parents[2]
OUT = json.loads((ROOT / "app" / "data" / "agent_outputs.json").read_text())
CASE = OUT["cases"]["EXC-S07-D72-20120824"]
FACT = {f["id"]: f["value"] for f in CASE["evidence"]}
AMBER = "B26A00"
MENU = [("store_wide", "Whole store down?"), ("persistence", "One-off or persistent?"), ("regional_peers", "Regional peers?"),
        ("chain", "Whole chain?"), ("promo_macro", "Promos, fuel, weather?"), ("calendar", "Calendar effect?")]


def llm_tag(s, x, y, color=None):
    """Small Spark-yellow tag on the top edge of a box whose decision is made by an LLM."""
    return pill(s, x, y, 0.42, "LLM", SPARK, color=NAVY, line_=NAVY, h=0.2, size=8)


def short(t, n):
    return t if len(t) <= n else t[:n - 1].rstrip(" ,;") + "…"


# ------------------------------------------------------------------------------------------ 1. system map
def system_map(prs):
    s = new_slide(prs, "System Architecture: End to End")
    box(s, 1.6, 1.3, 6.55, 3.05, fill=None, line=MUTE, lw=1, dash=DASH, kind=RECT, name="boundary: LangGraph")
    tx(s, 2.45, 4.1, 1.2, 0.2, "LangGraph", size=8.5, color=GREY, bold=True)

    box(s, 0.35, 1.85, 1.1, 1.75, [
        dict(runs=[("Anomaly payload", dict(bold=True, size=10))], after=3),
        dict(runs=["store 7"], font=MONO, size=8.5), dict(runs=["dept 72"], font=MONO, size=8.5),
        dict(runs=["2012-08-24"], font=MONO, size=8.5), dict(runs=["exp 45,010"], font=MONO, size=8.5),
        dict(runs=["act 33,958"], font=MONO, size=8.5),
        dict(runs=[("−24.6%", dict(bold=True, color=ERR, size=11))], before=3)],
        line=INK, lw=1, align="l", anchor="t", margin=0.08, name="payload")
    line(s, [(1.45, 2.725), (1.75, 2.725)])

    box(s, 1.75, 2.0, 1.15, 1.45, [dict(runs=[("Orchestrator", dict(bold=True, size=11))], after=4),
                                   "LLM picks checks,", "writes searches"], fill=ORCH, color=WHITE, size=9, name="Orchestrator")
    llm_tag(s, 2.12, 1.9, ORCH)
    box(s, 3.75, 2.0, 1.45, 0.6, [[("Evidence Agent", dict(bold=True, size=10.5))], "pandas · chosen checks"],
        fill=EVID, color=WHITE, size=8.5, name="Evidence Agent")
    box(s, 3.75, 2.85, 1.45, 0.6, [[("RAG Agent", dict(bold=True, size=10.5))], "filter → search → rank"],
        fill=RAG_F, color=NAVY, size=8.5, name="RAG Agent")
    can(s, 3.85, 1.36, 1.25, 0.46, ["Sales data · 6 CSVs", "421,570 rows"], size=8.5)
    can(s, 3.85, 3.62, 1.25, 0.5, ["ChromaDB", "6,560 chunks"], size=8.5)
    line(s, [(4.475, 1.82), (4.475, 2.0)], color=STORE, w=1.25)
    line(s, [(4.475, 3.62), (4.475, 3.45)], color=STORE, w=1.25)
    line(s, [(2.9, 2.3), (3.75, 2.3)])
    tx(s, 2.92, 2.08, 0.81, 0.2, "chosen checks", size=8.5, align="c")
    line(s, [(2.9, 3.15), (3.75, 3.15)])
    tx(s, 2.92, 2.93, 0.81, 0.2, "questions", size=8.5, align="c")
    tx(s, 2.92, 2.6, 0.81, 0.2, "in parallel", size=8.5, color=GREY, italic=True, align="c")

    box(s, 5.75, 2.0, 1.1, 1.45, [dict(runs=[("Reasoning Agent", dict(bold=True, size=10.5))], after=4),
                                  "LLM writes factors"], fill=REAS_F, color=NAVY, size=9, name="Reasoning Agent")
    llm_tag(s, 6.09, 1.9, REAS)
    line(s, [(5.2, 2.3), (5.75, 2.3)], color=EVID, w=2)
    tx(s, 5.2, 2.08, 0.55, 0.2, "facts", size=8.5, color=EVID, align="c", bold=True)
    line(s, [(5.2, 3.15), (5.75, 3.15)], color=RAG, w=2)
    tx(s, 5.2, 2.93, 0.55, 0.2, "quotes", size=8.5, color=NAVY, align="c", bold=True)

    box(s, 7.05, 2.0, 0.95, 1.45, [dict(runs=[("Evaluation", dict(bold=True, size=10.5))], after=4), "4 checks", "in code"],
        fill=OK, color=WHITE, size=9, name="Evaluation")
    line(s, [(6.85, 2.725), (7.05, 2.725)], color=REAS, w=2)

    # dashboard
    box(s, 8.35, 1.65, 1.3, 2.25, None, line=INK, lw=1, name="dashboard")
    tx(s, 8.42, 1.71, 1.2, 0.2, "Dashboard", size=9.5, bold=True)
    tx(s, 8.42, 1.95, 1.2, 0.18, "pass", size=8, color=OK, bold=True)
    pill(s, 8.42, 2.13, 1.16, "Action needed", ERR_T, color=ERR, size=8)
    tx(s, 8.42, 2.42, 1.2, 0.18, "a check fails", size=8, color=AMBER, bold=True)
    pill(s, 8.42, 2.6, 1.16, "Check before acting", AMBER_T, color=AMBER, size=7.5)
    for i, t in enumerate(["Factors + evidence", "Source quotes", "Live trace · chat"]):
        box(s, 8.42, 2.95 + i * 0.3, 1.16, 0.24, t, fill=LIGHT, size=8.5, align="l", margin=0.05, radius=0.03)
    line(s, [(8.0, 2.725), (8.35, 2.725)], color=OK, w=2)

    # LLM API (external) + offline index
    box(s, 5.45, 4.6, 1.7, 0.42, ["LLM API", "(OpenRouter)"], fill=WHITE, line=MUTE, lw=1, dash=DASH,
        size=8.5, name="LLM API")
    line(s, [(6.3, 3.45), (6.3, 4.6)], color=REAS, w=1.25, dash=DASH, head=True)
    line(s, [(2.325, 3.45), (2.325, 5.2), (6.0, 5.2), (6.0, 5.02)], color=ORCH, w=1.25, dash=DASH, head=True)
    box(s, 3.85, 4.6, 1.25, 0.42, ["59 reports", "indexed offline"], fill=WHITE, line=MUTE, lw=1, dash=DASH, size=8.5, name="ingest")
    line(s, [(4.475, 4.6), (4.475, 4.12)], color=MUTE, w=1.25, dash=DASH)

    # follow-up loop
    line(s, [(9.0, 1.65), (9.0, 1.08), (2.325, 1.08), (2.325, 2.0)], color=GREY, w=1.25, dash=DOT)
    tx(s, 5.4, 1.11, 3.4, 0.18, "follow-up questions", size=8.5, color=GREY, italic=True, align="r")

    # legend (right column) and run note (left column)
    ly = 4.47
    legend = [("line", INK, None, "task"), ("line", EVID, None, "result"),
              ("line", MUTE, DASH, "LLM call · offline build"), ("line", GREY, DOT, "follow-up")]
    for i, (_, c, d, t) in enumerate(legend):
        y = ly + i * 0.22
        line(s, [(7.45, y + 0.09), (7.78, y + 0.09)], color=c, w=1.5, dash=d)
        tx(s, 7.85, y, 1.8, 0.2, t, size=8.5, color=GREY)
    llm_tag(s, 7.42, ly + 0.88)
    tx(s, 7.92, ly + 0.88, 1.7, 0.2, "LLM decides", size=8.5, color=GREY)

    notes(s, """SYSTEM ARCHITECTURE — one flagged week, end to end. Running example: Store 7, Dept 72 Electronics, week ending Aug 24, 2012.

1. INPUT. The ML team's detector (Extra Trees) hands us a payload: Store 7 Electronics sold $33,958 against $45,010 expected, −24.6%. The question is always: why?

2. ORCHESTRATOR. A LangGraph graph. Code first reads the payload (three formats are accepted). Then an LLM plans the investigation: it picks which data checks to run from a fixed menu of six, and writes 2 to 4 search questions for the reports. The plan is validated in code.

3. EVIDENCE AND RAG, IN PARALLEL. The Evidence Agent runs only the chosen checks, in pandas, on the Kaggle sales data (421,570 rows). The RAG Agent searches 6,560 report chunks in ChromaDB with the LLM's questions, filtered to the right time and the store's Fed district. Neither of these uses an LLM.

4. REASONING AGENT. An LLM reads the numbers and the quotes and writes the answer: likely explained or likely store issue, a confidence, 2 to 4 possible factors with the evidence each one uses, what was ruled out, a bottom line and next steps.

5. EVALUATION. Four checks in code: the numbers are in the evidence, the quotes are word for word, every factor cites evidence, and the answer is complete. Pass → the dashboard shows the answer. Fail → the dashboard flags it 'Check before acting' and says which check failed.

6. DASHBOARD. Streamlit: the answer, the source quotes, a live trace of every step, and a follow-up chat.

The LLM calls go to free models on OpenRouter (or Anthropic if that key is set). If no model answers, the run stops with an error and the user clicks 'Run the agents again'. The reports are indexed once, offline (dashed).""")
    return s


# ------------------------------------------------------------------------------------------ 2. orchestrator
def orchestrator(prs):
    plan = CASE["plan"]
    s = new_slide(prs, "Orchestrator: LLM Planner")
    tx(s, 0.35, 1.06, 9.3, 0.25, [[("Every payload asks:  ", dict(bold=True, color=ORCH)),
                                   ("why did this store / department / week come in below expected?", {})]], size=11)

    box(s, 0.35, 1.5, 2.05, 2.7, None, line=INK, lw=1, name="incoming payload")
    tx(s, 0.45, 1.57, 1.9, 0.4, [[("Incoming payload", dict(bold=True, size=10))], [("Extra Trees hand-off", dict(color=GREY, size=9))]])
    tx(s, 0.45, 2.02, 1.9, 2.1, ["store_id: 7", "department_id: 72", "week_start_date:", '  "2012-08-24"', "expected_sales:",
                                 "  45010.06", "actual_sales:", "  33957.54", "detector: Extra", "  Trees"], size=8.5, font=MONO, spacing=1)
    line(s, [(2.4, 2.15), (2.75, 2.15)])

    box(s, 2.6, 1.5, 3.45, 2.7, None, fill=ORCH_T, line=ORCH, lw=1.25, name="Orchestrator panel")
    tx(s, 2.72, 1.55, 2.5, 0.22, "Orchestrator", size=10.5, bold=True, color=ORCH)
    # intake (code)
    box(s, 2.75, 1.85, 3.15, 0.6, None, line=ORCH, lw=0.75, name="intake")
    tx(s, 2.85, 1.88, 3.0, 0.55, [[("1 Read payload  ", dict(bold=True)), ("code", dict(color=GREY))],
                                  "3 formats → one internal payload + public mappings (Electronics, Colorado → Kansas City Fed)"],
       size=8.5)
    line(s, [(4.325, 2.45), (4.325, 2.55)], color=ORCH, w=1.25)
    # LLM planner
    box(s, 2.75, 2.55, 3.15, 0.92, None, line=ORCH, lw=1.25, name="LLM planner")
    llm_tag(s, 5.4, 2.45, ORCH)
    tx(s, 2.85, 2.6, 3.0, 0.85, [[("2 Plan  ", dict(bold=True)), ("LLM", dict(color=GREY))],
                                 [("in: ", dict(bold=True)), "case + signals computed in code (no holiday, fuel +2.1%, 59°F vs 58°F) + menu of 6 checks"],
                                 [("out: ", dict(bold=True)), "JSON { checks, questions, why }"]], size=8.5, spacing=1)
    line(s, [(4.325, 3.47), (4.325, 3.57)], color=ORCH, w=1.25)
    box(s, 2.75, 3.57, 3.15, 0.55, None, line=ORCH, lw=0.75, name="validate")
    tx(s, 2.85, 3.6, 3.0, 0.5, [[("3 Check the plan  ", dict(bold=True)), ("code", dict(color=GREY))],
                                "keep menu ids only · 1–4 questions · add time + region filter from the payload"], size=8.5)

    # branches
    line(s, [(5.9, 3.7), (6.12, 3.7), (6.12, 2.1), (6.3, 2.1)])
    line(s, [(5.9, 3.95), (6.3, 3.95)])
    box(s, 6.3, 1.5, 3.35, 1.45, None, fill=EVID_T, line=EVID, lw=1.25, name="evidence task")
    tx(s, 6.42, 1.55, 3.15, 0.22, [[("Evidence task", dict(bold=True, color=EVID)), ("  → Evidence Agent", dict(color=GREY))]], size=10)
    for i, (cid, label) in enumerate(MENU):
        on = cid in plan["checks"]
        x, y = 6.42 + (i % 2) * 1.6, 1.86 + (i // 2) * 0.33
        pill(s, x, y, 1.5, ("✓ " if on else "– ") + label.rstrip("?"), EVID if on else WHITE, color=WHITE if on else GREY,
             line_=None if on else MUTE, dash=None if on else DASH, h=0.25, size=8)
    box(s, 6.3, 3.05, 3.35, 1.15, None, fill=RAG_T, line=RAG, lw=1.25, name="RAG task")
    tx(s, 6.42, 3.1, 3.15, 0.22, [[("RAG task", dict(bold=True, color=NAVY)), ("  → RAG Agent", dict(color=GREY))]], size=10)
    qs = plan["queries"]
    tx(s, 6.42, 3.35, 3.15, 0.85, [dict(runs=[f"“{short(q['text'], 52)}”"], after=1) for q in qs[:3]]
       + ([f"+ {len(qs) - 3} more"] if len(qs) > 3 else []) + [[("filter: wk 2012-08-24 · National + Kansas City", dict(color=GREY))]],
       size=8)

    # bottom row
    box(s, 0.35, 4.4, 5.7, 0.95, None, line=ORCH, lw=0.75, name="hand-off")
    tx(s, 0.47, 4.47, 1.45, 0.8, [[("Hand-off", dict(bold=True, color=ORCH, size=10))],
                                  [("run in parallel, then join", dict(color=GREY))]], size=8.5)
    pill(s, 2.05, 4.5, 0.9, "evidence", EVID, h=0.26, size=9)
    pill(s, 2.05, 4.93, 0.9, "rag", RAG_F, color=NAVY, h=0.26, size=9)
    tx(s, 2.05, 4.77, 0.9, 0.16, "same step", size=8.5, color=GREY, italic=True, align="c")
    box(s, 3.35, 4.71, 1.15, 0.28, [[("shared state", dict(bold=True))]], fill=STORE_F, line=STORE, size=8.5)
    pill(s, 4.9, 4.71, 0.95, "reason", REAS_F, color=NAVY, h=0.28, size=9)
    line(s, [(2.95, 4.63), (3.15, 4.63), (3.15, 4.85), (3.35, 4.85)], color=EVID, w=1.5)
    line(s, [(2.95, 5.06), (3.15, 5.06), (3.15, 4.85)], color=RAG, w=1.5, tail=False)
    line(s, [(4.5, 4.85), (4.9, 4.85)], color=INK, w=1.25)
    tx(s, 3.35, 5.04, 2.6, 0.2, "no plan from any model → error, run again", size=8.5, color=ERR, italic=True)

    box(s, 6.3, 4.4, 3.35, 0.95, None, line=GREY, lw=1, dash=DOT, name="follow-up routing")
    tx(s, 6.42, 4.45, 3.15, 0.88, [
        dict(runs=[("Follow-up questions", dict(bold=True, size=9.5, color=ORCH))], after=2),
        "keyword router (9 question types)",
        "“How did Store 41 do?” → store lookup tool",
        "needs a skipped check → Evidence Agent runs it now"], size=8.5)

    why = plan.get("why", "")
    notes(s, f"""ORCHESTRATOR — how one payload becomes a plan and two tasks.

Every payload asks the same question: why did this store, department and week come in below expected? The orchestrator decides what evidence is needed to answer it.

1 Read the payload (code). Three formats are accepted: the Extra Trees hand-off (store × department × week), the primary anomaly payload (store × week) and an internal format. Code turns any of them into one internal payload and adds the public mappings: Dept 72 is Electronics in the Entertainment unit; Store 7 is in Colorado, in the Kansas City Fed district. These mappings are publicly inferred, not confirmed by Walmart.

2 Plan (LLM). The LLM gets the case, a few signals computed in code (no holiday that week, fuel +2.1% vs last year, 59°F vs 58°F) and the menu of six data checks. It answers in JSON: which checks to run, 2 to 4 search questions for the reports, and one sentence on why. In this run it chose {len(plan['checks'])} of 6 checks ({', '.join(plan['checks'])}) and wrote {len(plan['queries'])} questions. Its reason: "{why}"

3 Check the plan (code). Only ids from the menu are kept, at most 4 questions. The time and region filter for the reports is not the LLM's choice: it comes from the payload (the week, the national reports plus the store's Fed district).

Hand-off. The Evidence and RAG agents both depend only on the plan, so LangGraph runs them in the same step; the Reasoning Agent starts when both have written their results to the shared state.

If no free model returns a usable plan, the run stops with an error and the user clicks 'Run the agents again'.

Follow-up questions use a simple keyword router with 9 intents. 'How did Store 41 do?' calls a store lookup. If a question needs a check the plan skipped (for example markdowns), the Evidence Agent runs that check on demand.""")
    return s


# ------------------------------------------------------------------------------------------ 3. evidence
def _result(cid):
    """(main, sub) text for one check row, from the saved evidence facts."""
    f = FACT
    if cid == "store_wide":
        return f["store_week_yoy"], f"whole store vs LY; quarter {f['store_quarter_yoy']}"
    if cid == "persistence":
        return f["dept_quarter_yoy"], f"{f['weeks_down']} weeks below LY"
    if cid == "regional_peers":
        p = re.findall(r"[+−-]\d+\.\d%", f["peers_quarter"])
        stores = re.findall(r"Store (\d+)", f["peers_quarter"])
        return (f"{p[0]} to {p[-1]}" if p else "n/a"), "Stores " + ", ".join(stores)
    if cid == "chain":
        return f["chain_dept_quarter_yoy"], f"store − chain {f['store_vs_chain'].replace(' percentage points', ' pts')}" if "store_vs_chain" in f else "45 stores"
    if cid == "promo_macro":
        return "markdowns " + f["markdown_ratio"].split(" ")[0], "fuel " + re.search(r"\(([^)]+)\)", f["fuel"]).group(1)
    if cid == "calendar":
        return f["calendar_flags"], f"6 weeks around: {f['season_yoy']}"


def evidence(prs):
    plan = CASE["plan"]
    s = new_slide(prs, "Evidence Agent: Checks the Plan Chose")
    for x, n, t in [(0.35, 1, "Plan → checks"), (2.75, 2, "Run the chosen checks"), (7.3, 3, "Labelled facts")]:
        num(s, x, 1.08, n, EVID, d=0.24, size=9.5)
        tx(s, x + 0.32, 1.1, 2.2, 0.22, t, size=10.5, bold=True, color=EVID)
    tx(s, 5.35, 1.13, 1.65, 0.2, "code only · no LLM", size=9, color=GREY, italic=True, align="r")
    line(s, [(2.0, 1.2), (2.65, 1.2)], color=EVID, w=1.25)
    line(s, [(7.08, 1.2), (7.25, 1.2)], color=EVID, w=1.25)

    box(s, 0.35, 1.5, 2.15, 1.45, None, fill=EVID_T, line=EVID, lw=1, name="evidence task")
    tx(s, 0.45, 1.55, 2.0, 1.38, [
        dict(runs=[("from the orchestrator's plan", dict(font="Arial", color=GREY, size=9))], after=2),
        [(f"checks = {len(plan['checks'])} of 6", dict(bold=True))]] + [f" {c}" for c in plan["checks"]]
        + ["store=7  dept=72", "week=2012-08-24"], size=8.5, font=MONO)

    tx(s, 0.35, 3.08, 2.2, 0.2, "Data layer · joined once at startup", size=9, bold=True, color=GREY)
    tables = [("train.csv", "421,570 sales rows"), ("features.csv", "MarkDown1–5, fuel"), ("stores.csv", "type, size"),
              ("dept_mapping", "name, unit"), ("store_mapping", "region, Fed district"), ("fiscal_calendar", "FY weeks")]
    for i, (n, d) in enumerate(tables):
        box(s, 0.35, 3.33 + i * 0.3, 2.15, 0.26, [[(n, dict(font=MONO, bold=True)), (" " + d, dict(color=GREY))]], fill=STORE_F,
            line=STORE, lw=0.75, size=8.5, align="l", margin=0.06, radius=0.03)
    line(s, [(2.5, 3.6), (2.75, 3.6)], color=STORE, w=1.5)

    exprs = {"store_wide": "store_week[7, wk] vs wk−52", "persistence": "panel[7, 72, Q3]: Σsales / ΣLY",
             "regional_peers": "panel[72, Colorado, ≠7, Q3]", "chain": "panel[72, all 45 stores, Q3]",
             "promo_macro": "features[7, wk] vs avg / LY", "calendar": "holiday flag; Easter/Xmas vs LY"}
    ran = []
    for i, (cid, q) in enumerate(MENU):
        y = 1.5 + i * 0.63
        on = cid in plan["checks"]
        box(s, 2.75, y, 4.3, 0.55, None, line=EVID if on else MUTE, lw=0.75, dash=None if on else DASH,
            fill=WHITE if on else None, name=f"check {cid}")
        num(s, 2.84, y + 0.145, i + 1, EVID if on else MUTE, d=0.26, size=9.5)
        tx(s, 3.2, y + 0.06, 2.35, 0.45, [[(q, dict(bold=True, size=10.5, color=INK if on else GREY))]], anchor="m")
        if on:
            main, sub = _result(cid)
            tx(s, 5.6, y + 0.06, 1.42, 0.45, [[(main, dict(bold=True, color=EVID, size=10 if len(main) > 12 else 11))],
                                              [(sub, dict(color=GREY, size=8))]])
            line(s, [(7.05, y + 0.275), (7.15, y + 0.275)], color=EVID, w=1.25, tail=False)
            ran.append(y + 0.275)
        else:
            tx(s, 5.6, y + 0.08, 1.42, 0.42, [[("skipped", dict(bold=True, color=GREY, size=10))],
                                              [("runs on demand in chat", dict(color=GREY, size=8))]])
    line(s, [(7.15, min(ran)), (7.15, max(ran))], color=EVID, w=1.25, tail=False)
    mid = (min(ran) + max(ran)) / 2
    line(s, [(7.15, mid), (7.3, mid)], color=EVID, w=1.5)

    box(s, 7.3, 1.5, 2.35, 2.45, None, line=EVID, lw=1, name="facts")
    tx(s, 7.4, 1.56, 2.2, 0.2, [[("Store 7 results", dict(bold=True, color=EVID))]], size=10)
    rows = []
    for f in CASE["evidence"][:7]:
        rows.append(dict(runs=[(f["id"], dict(font=MONO, bold=True, size=7.5))], after=0))
        rows.append(dict(runs=[(short(f["value"], 36), dict(size=8, color=GREY))], after=2))
    if len(CASE["evidence"]) > 7:
        rows.append(dict(runs=[(f"+ {len(CASE['evidence']) - 7} more", dict(size=8, color=GREY))]))
    tx(s, 7.4, 1.8, 2.2, 2.12, rows, size=8)
    line(s, [(8.475, 3.95), (8.475, 4.12)], color=REAS, w=1.5)
    pill(s, 7.3, 4.12, 2.35, "→ Reasoning Agent", REAS_F, color=NAVY, h=0.26, size=9)

    notes(s, f"""EVIDENCE AGENT — runs the checks the orchestrator chose.

What it is: plain Python with pandas (agents/engine.py). No LLM and no SQL. The six Kaggle and mapping CSVs are loaded once when the app starts and joined into two in-memory tables: store × department × week (with the same week last year and the expected value), and store-week totals.

1 Plan → checks. The orchestrator's LLM picked {len(plan['checks'])} of the 6 checks on the menu for Store 7: {', '.join(plan['checks'])}. Only those run. Each check is a fixed pandas filter + sum + ratio; its parameters (store 7, dept 72, the week, fiscal Q3, Colorado, last year = 52 weeks earlier) come from the payload.

2 The checks (Store 7 Electronics):
 1 Whole store down? Is the whole store down that week, or only this department?
 2 One-off or persistent? Below last year for most of the quarter, or one bad week?
 3 Regional peers? Same department at other Colorado stores, same quarter.
 4 Whole chain? Same department across all 45 stores.
 5 Promos, fuel, weather? Store markdowns vs its average week, fuel and temperature vs last year.
 6 Calendar? A holiday, or Easter / Christmas in a different week than last year.
Skipped checks are not lost: if a follow-up question needs one (for example 'what about markdowns?'), the Evidence Agent runs it then.

3 Labelled facts. The results are written as facts with an id, a plain label and a formatted value, for example "dept_quarter_yoy: Electronics at this store, this quarter vs. last year = {FACT.get('dept_quarter_yoy', 'n/a')}". The Reasoning Agent's LLM reads these, cites them by id, and the evaluation checks that every number in the answer appears here. The LLM never calculates a number.

Note on 'MarkDown': MarkDown1–5 in features.csv are promotional markdown dollars per store-week, not Markdown documents.
Note on the window: 'this quarter' is the fiscal quarter capped at 12 weeks before the flagged week, so it includes weeks after it (fine for looking back, not for real-time use).""")
    return s


# ------------------------------------------------------------------------------------------ 4. RAG
def rag(prs):
    st, qs, ps = CASE["rag_stats"], CASE["plan"]["queries"], CASE["passages"]
    s = new_slide(prs, "RAG Agent: Indexing and Retrieval")
    box(s, 0.35, 1.02, 9.3, 1.28, None, kind=RECT, fill=LIGHT, line=MUTE, lw=0.75, dash=DASH, name="offline band")
    tx(s, 0.45, 1.06, 6.0, 0.2, [[("OFFLINE INDEXING", dict(bold=True, color=GREY)),
                                  ("   run once, about 2 minutes", dict(color=GREY))]], size=8.5)
    box(s, 0.45, 1.3, 1.65, 0.92, [
        dict(runs=[("59 source files (.txt)", dict(bold=True, size=9))], after=1),
        "Earnings releases 11", "Earnings calls 11", "10-K 4 · annual report 4", "Comp sales 2 · NRF 3", "Fed Beige Books 24"],
        size=8, line=MUTE, lw=0.75, align="l", anchor="t", margin=0.06, name="sources")
    steps = [("Clean", "page nos.,\nquotes, spaces"), ("Split", "Beige Books by\n12 Fed districts"),
             ("Chunk", "≈900 chars, 150\noverlap, sentences"), ("Prose filter", "drops 299\ntable chunks")]
    for x, (t, d) in zip([2.3, 3.55, 4.8, 6.05], steps):
        box(s, x, 1.42, 1.05, 0.68, [[(t, dict(bold=True, size=9))], d], size=8, line=MUTE, lw=0.75)
    for a, b in [(2.1, 2.3), (3.35, 3.55), (4.6, 4.8), (5.85, 6.05), (7.1, 7.3)]:
        line(s, [(a, 1.76), (b, 1.76)], color=MUTE, w=1.25, dash=DASH)
    for i, (t, d) in enumerate([("chunk text", "≈814 chars avg"), ("metadata", "doc_type, district, dates"), ("vector", "MiniLM-L6 · 384-d")]):
        box(s, 7.3, 1.33 + i * 0.3, 2.25, 0.26, [[(t, dict(bold=True)), ("  " + d, dict(color=GREY))]], size=8.5, line=MUTE, lw=0.75,
            align="l", radius=0.03)
    for xx in (7.7, 8.4, 9.1):
        line(s, [(xx, 2.22), (xx, 2.42)], color=MUTE, w=1.25, dash=DASH)

    can(s, 0.9, 2.38, 8.7, 0.62, None, adj=0.22, fill=STORE_F, name="ChromaDB")
    tx(s, 1.1, 2.55, 8.3, 0.42, [
        [("ChromaDB", dict(bold=True, size=10)), ("  collection walmart_reports · 6,560 records · HNSW, cosine · 60.7 MB   ", {}),
         ("record = id + text + metadata + vector", dict(bold=True))],
        [("metadata: ", dict(color=GREY)),
         ("doc_id, doc_type, publisher, evidence_type, district, published, period_start, period_end, source_file, chunk_index",
          dict(font=MONO, color=GREY, size=8))]], size=9, align="c")

    box(s, 0.35, 3.08, 9.3, 2.3, None, kind=RECT, fill=WHITE, line=RAG, lw=0.75, name="online band")
    tx(s, 0.45, 3.13, 1.6, 0.2, "ONLINE RETRIEVAL", size=8.5, bold=True, color=NAVY)
    tx(s, 4.2, 3.13, 3.4, 0.2, "every anomaly", size=8.5, color=GREY, align="r")
    box(s, 0.45, 3.42, 0.95, 0.5, [[("RAG task", dict(bold=True))], f"{len(qs)} questions"], fill=RAG_T, line=RAG, lw=0.75, size=8.5)
    cols = [(1.6, 1.45, "Metadata filter", f"{st['chunks_in_store']:,} → {st['chunks_after_filter']:,} chunks",
             f"{st['reports_after_filter']} of {st['reports_in_store']} reports",
             "Inside ChromaDB, before the search. Time: period covers the week, or published / ended ≤21 days before. "
             "Place: National + Kansas City."),
            (3.25, 1.15, "Vector search", f"{st['queries']} × top 25 → {st['candidates']}", "unique candidates",
             "Each question embedded (MiniLM); cosine top 25 per question; merged by chunk id."),
            (4.6, 1.6, "Re-rank", "top 30 re-scored", "sentence by sentence",
             "Not a cross-encoder. Each sentence embedded; score = .45 chunk sim + .55 best sentence + .25 keyword "
             "overlap + district / period boosts."),
            (6.4, 1.25, "Source-aware select", f"→ {st['returned']} passages", "≤2 per report",
             "Reserve the best Walmart chunk and the best local Beige Book chunk; fill to k = 6 by score.")]
    for i, (x, w, t, n1, n2, d) in enumerate(cols):
        box(s, x, 3.42, w, 0.5, [[(t, dict(bold=True, size=9.5))]], fill=RAG_F, color=NAVY, size=9)
        num(s, x - 0.11, 3.31, i + 1, INK, d=0.22, size=8.5)
        tx(s, x, 3.99, w, 0.8, d, size=8.5)
        tx(s, x, 4.9, w, 0.42, [[(n1, dict(bold=True, color=NAVY, size=9.5))], [(n2, dict(color=GREY, size=8.5))]])
    for a, b in [(1.4, 1.6), (3.05, 3.25), (4.4, 4.6), (6.2, 6.4)]:
        line(s, [(a, 3.67), (b, 3.67)], color=RAG, w=1.5)
    line(s, [(2.33, 3.0), (2.33, 3.42)], color=RAG, w=1.5)
    line(s, [(3.83, 3.0), (3.83, 3.42)], color=RAG, w=1.5)
    tx(s, 0.45, 4.9, 1.05, 0.42, [[("Store 7 run", dict(bold=True, color=NAVY))]], size=8.5)

    line(s, [(7.65, 3.67), (7.85, 3.67)], color=RAG, w=1.5)
    box(s, 7.85, 3.2, 1.72, 2.1, None, fill=RAG_T, line=RAG, lw=1, name="returned passages")
    num(s, 7.74, 3.09, 5, INK, d=0.22, size=8.5)
    n_wmt = sum(p["evidence_type"].startswith("Walmart") for p in ps)
    cited = [x for f in CASE["report"]["factors"] for x in f["evidence"] if x.startswith("P")]
    ex = next((p for p in ps if p["id"] in cited), ps[0])
    paras = [dict(runs=[("Package → Reasoning", dict(bold=True, color=NAVY, size=9))], after=3),
             dict(runs=[(f"Walmart {n_wmt} · Fed / NRF {len(ps) - n_wmt}", dict(bold=True))], after=3),
             dict(runs=[(f"{ex['id']} (cited in the answer)", dict(bold=True))], after=0),
             dict(runs=[f"“{short(ex['quote'], 120)}”"], italic=True, after=0),
             dict(runs=[(f"{ex['doc'].replace('Walmart ', '')}, {ex['published']}", dict(color=GREY))], after=3),
             ]
    tx(s, 7.95, 3.27, 1.58, 2.0, paras, size=8)

    notes(s, f"""RAG AGENT — two separate workflows sharing one vector store.

OFFLINE INDEXING (top, dashed): python3 -m agents.ingest, run once, about 2 minutes. Not part of any request.
• 59 original text files: Walmart earnings releases (11), earnings call transcripts (11), 10-Ks (4), annual-report MD&A (4), comp-sales disclosures (2), Fed Beige Books (24), NRF holiday forecasts (3). There are no Markdown-format reports.
• Clean the text; split Beige Books by the 12 Fed districts so every chunk knows its district.
• Chunk to about 900 characters with 150 characters of overlap, cut at sentence boundaries; drop 299 chunks that are mostly tables (6,859 → 6,560).
• ChromaDB embeds each chunk with all-MiniLM-L6-v2 (384 dimensions) and stores id + text + metadata + vector in one collection.

ONLINE RETRIEVAL (bottom): per anomaly. The search questions now come from the orchestrator's LLM; this run had {len(qs)}:
""" + "\n".join(f"  • {q['text']}" for q in qs) + f"""
1 Metadata filter inside ChromaDB, before the search. Time: the report covers the week, or was published or ended in the 21 days before. Place: national reports plus the store's Fed district (Kansas City). {st['chunks_in_store']:,} → {st['chunks_after_filter']:,} chunks from {st['reports_after_filter']} of {st['reports_in_store']} reports. This filter comes from the payload, not from the LLM.
2 Vector search: each question is embedded; the top 25 chunks per question by cosine similarity are merged → {st['candidates']} candidates.
3 Re-rank: the 30 best are scored again sentence by sentence (not a cross-encoder): chunk similarity, best-sentence similarity, keyword overlap, small boosts for the local district and for reports covering the week.
4 Source-aware selection: one slot for the best Walmart chunk, one for the best local Beige Book chunk, the rest by score up to 6, at most 2 per report. Counts per source are not fixed; they depend on what passes the filter.
5 Package: each passage gets an id (P1–P6) with its text, best sentence, document, date and district. The Reasoning Agent cites these ids; the RAG Agent does not write an answer.""")
    return s


# ------------------------------------------------------------------------------------------ 5. reasoning + evaluation + dashboard
def reasoning(prs):
    rep, res = CASE["report"], CASE["evaluation"]
    s = new_slide(prs, "Reasoning Agent: Write and Check")

    # inputs
    box(s, 0.35, 1.15, 1.6, 1.45, None, fill=EVID_T, line=EVID, lw=1, name="facts in")
    tx(s, 0.43, 1.2, 1.47, 1.38, [dict(runs=[("Evidence facts", dict(bold=True, color=EVID, size=9.5))], after=2)]
       + [dict(runs=[(f["id"], dict(font=MONO, size=7.5, bold=True))], after=0) for f in CASE["evidence"][:6]]
       + [dict(runs=[(f"+ {max(0, len(CASE['evidence']) - 6)} more", dict(color=GREY))])], size=8)
    box(s, 0.35, 2.8, 1.6, 1.3, None, fill=RAG_T, line=RAG, lw=1, name="passages in")
    tx(s, 0.43, 2.85, 1.47, 1.22, [dict(runs=[("Report passages", dict(bold=True, color=NAVY, size=9.5))], after=2),
                                   dict(runs=[f"P1–P{len(CASE['passages'])}: text, quote, source, date"], after=2),
                                   ] + [dict(runs=[(f"{p['id']} " + p["doc"].replace("Walmart ", "").replace(" earnings call transcript", " call")
                                                    .replace(" earnings release", " release").replace("Federal Reserve Beige Book,", "Beige Book"),
                                                    dict(color=GREY, size=7.5))], after=0) for p in CASE["passages"]], size=8)
    line(s, [(1.95, 1.9), (2.2, 1.9)], color=EVID, w=2)
    line(s, [(1.95, 3.45), (2.2, 3.45)], color=RAG, w=2)

    # LLM summarizer
    box(s, 2.2, 1.15, 2.55, 2.95, None, fill=REAS_T, line=REAS, lw=1.25, name="LLM summarizer")
    llm_tag(s, 4.2, 1.05, REAS)
    tx(s, 2.3, 1.2, 2.4, 0.22, "1 Write the answer", size=10, bold=True, color=NAVY)
    tx(s, 2.3, 1.48, 2.38, 1.0, [dict(runs=["Uses only the facts and passages; copies numbers exactly; quotes word for word."], after=3),
                                 dict(runs=["Picks the useful quotes itself; cites ids for every factor."])], size=8.5)
    box(s, 2.3, 2.45, 2.35, 1.55, None, fill=WHITE, line=REAS, lw=0.75, name="answer json")
    f0 = rep["factors"]
    tx(s, 2.38, 2.5, 2.22, 1.48, [f'verdict: "{rep["verdict"]}"', f'confidence: "{rep["confidence"]}"', f"factors: [{len(f0)}]"]
       + [f"  {short(f['title'], 24)}" for f in f0[:3]] + ["  + evidence ids", "ruled_out, bottom_line,", "next_steps"],
       size=7.5, font=MONO)

    # evaluation
    line(s, [(4.75, 2.6), (5.0, 2.6)], color=REAS, w=2)
    box(s, 5.0, 1.15, 1.95, 2.95, None, fill=OK_T, line=OK, lw=1.25, name="evaluation")
    tx(s, 5.1, 1.2, 1.8, 0.22, "2 Evaluation (code)", size=10, bold=True, color=OK)
    rows = []
    for c in res["checks"]:
        rows.append(dict(runs=[("✓ " if c["passed"] else "✗ ", dict(bold=True, color=OK if c["passed"] else ERR)),
                               (c["name"], dict(bold=True))], after=0))
        rows.append(dict(runs=[(short(c["detail"], 64), dict(color=GREY, size=7.5))], after=4))
    tx(s, 5.1, 1.5, 1.8, 2.5, rows, size=8.5)

    # outcomes
    line(s, [(6.95, 1.9), (7.3, 1.9)], color=OK, w=2)
    tx(s, 6.95, 1.68, 0.35, 0.2, "pass", size=8, color=OK, bold=True, align="c")
    box(s, 7.3, 1.15, 2.35, 1.7, None, line=INK, lw=1, name="dashboard pass")
    tx(s, 7.38, 1.2, 2.2, 0.2, "Dashboard", size=9.5, bold=True)
    label = {"Likely store issue": "Action needed", "Likely explained": "No action needed"}.get(rep["verdict"], rep["verdict"])
    pill(s, 7.38, 1.45, 2.2, f"{label} · {rep['confidence']} confidence",
         ERR_T if rep["verdict"] == "Likely store issue" else OK_T, color=ERR if rep["verdict"] == "Likely store issue" else OK, size=8.5)
    tx(s, 7.38, 1.74, 2.2, 1.1, [dict(runs=[(short(f["title"], 34), dict(bold=True))], after=1) for f in f0[:4]]
       + [dict(runs=[("each with its evidence", dict(color=GREY))])], size=8)
    line(s, [(6.95, 3.4), (7.3, 3.4)], color=AMBER, w=2)
    tx(s, 6.95, 3.18, 0.35, 0.2, "fail", size=8, color=AMBER, bold=True, align="c")
    box(s, 7.3, 3.0, 2.35, 1.1, None, fill=AMBER_T, line=AMBER, lw=1, name="check before acting")
    tx(s, 7.38, 3.05, 2.2, 1.0, [dict(runs=[("Check before acting", dict(bold=True, color=AMBER, size=9.5))], after=2),
                                 dict(runs=["answer shown greyed out, with the failed check named"], after=0)], size=8.5)

    # bottom
    box(s, 0.35, 4.35, 9.3, 0.42, None, fill=LIGHT, line=LINEC, lw=0.75, name="no answer")
    tx(s, 0.47, 4.39, 9.1, 0.36, [[("No readable answer from any model  ", dict(bold=True)),
                                   "→ status 'Try again'. Nothing is guessed."]], size=9, anchor="m")

    notes(s, f"""REASONING AGENT, EVALUATION AND DASHBOARD — from evidence to a checked answer.

Inputs. From the Evidence Agent: labelled facts (id, label, value) for the checks the plan chose. From the RAG Agent: 6 report passages with ids P1 to P6.

1 Write the answer (LLM). The Reasoning Agent is a summarizer. An LLM reads the facts and the passages and writes, in JSON: a verdict ('Likely explained' when a calendar or seasonal effect or a drop shared with other stores explains it; 'Likely store issue' when this store fell clearly more than comparable stores and the chain), a confidence (High, Medium, Low), 2 to 4 possible factors each with the ids of the evidence it uses, what was ruled out, a bottom line and next steps. It picks the useful quotes itself. It is told to copy numbers exactly and never calculate: every number was already computed by the Evidence Agent in Python.

What the store manager sees: 'Likely store issue' is shown as ACTION NEEDED, 'Likely explained' as NO ACTION NEEDED, and an answer that fails a check as CHECK BEFORE ACTING (with the reason). Weeks not looked at yet are NEW.

For Store 7 this run said: {rep['verdict']}, {rep['confidence']} confidence (shown as Action needed). Bottom line: "{rep['bottom_line']}"

2 Evaluation (code, not AI). Four checks:
 • Numbers match the evidence: every number in the answer appears in the case, the facts or a passage.
 • Quotes are word for word: anything in quotation marks must appear in a retrieved passage.
 • Every factor cites evidence: each factor lists ids, and the ids exist.
 • Answer is complete: allowed verdict and confidence, factors with title and text, bottom line, next steps.
Pass → the dashboard shows the answer with its evidence. Fail → the dashboard flags it 'Check before acting', shows the answer greyed out and names the failed check, so a person checks it before anyone acts on it.

If no model returns a readable answer (the free models are often busy), the run stops with an error and the user clicks 'Run the agents again'.

Important limit: the evaluation checks that the answer is grounded in the evidence. It cannot tell whether the reasoning is right (for example comparing the wrong two numbers). That is the people check, not built yet: two teammates label about 10 flagged weeks (6 regular, 4 holiday-shift) for verdict and main factor, and we compare with the agent.""")
    return s


# ------------------------------------------------------------------------------------------ why an agent
def why_agent(prs):
    s = new_slide(prs, "Why an AI Agent, Not Just a Dashboard", "A dashboard shows what happened. Analysts still need to know why.")
    box(s, 0.4, 1.3, 4.45, 0.42, "Dashboard alone", fill="E6F1FC", color=NAVY, size=13, bold=True, align="l", margin=0.15)
    box(s, 5.15, 1.3, 4.45, 0.42, "With the AI agent", fill=NAVY, color=WHITE, size=13, bold=True, align="l", margin=0.15)
    rows = [("chart", "Shows Store 7 Electronics down 24.6%", "Checks if the drop is a one-off or a pattern, and how other stores did"),
            ("search", "Analyst searches reports manually", "Pulls Walmart and Federal Reserve reports from the same quarter"),
            ("help", "No sense of how reliable a number is", "Tags every factor with its evidence and a confidence level"),
            ("list", "Raw numbers only", "Weighs possible explanations and recommends next steps")]
    for i, (ic, left, right) in enumerate(rows):
        y = 1.88 + i * 0.78
        box(s, 0.4, y, 4.45, 0.66, None, fill=LIGHT, name=f"dashboard {i + 1}")
        icon(s, ic, 0.55, y + 0.11, 0.44, "74767C")
        tx(s, 1.15, y, 3.6, 0.66, left, size=12, anchor="m")
        box(s, 5.15, y, 4.45, 0.66, None, fill=REAS_T, name=f"agent {i + 1}")
        icon(s, ic, 5.3, y + 0.11, 0.44, BLUE)
        tx(s, 5.9, y, 3.6, 0.66, [[(right, dict(bold=True, color=NAVY))]], size=12, anchor="m")
    tx(s, 0.4, 5.08, 9.2, 0.25, "The agent does not replace the analyst. It does the first round of investigation so the analyst starts from evidence.",
       size=10.5, color=GREY)
    notes(s, """A dashboard tells you Store 7 Electronics is down 24.6%. It does not tell you why. Today an analyst would dig through the sales data and search Walmart's and the Fed's reports by hand.

The AI agent does that first round of investigation: it checks whether the drop is one week or a pattern and how other stores did, pulls the Walmart and Federal Reserve reports from the same quarter and region, ties every possible factor to its evidence with a confidence level, and suggests next steps. The analyst still makes the call; they just start from evidence instead of a blank page.""")
    return s


# ------------------------------------------------------------------------------------------ knowledge sources
def sources(prs):
    s = new_slide(prs, "AI Agent Knowledge Sources", "What the agent uses to explain an exception, and what kind of information each source gives")
    heads = [(0.4, 2.75, "Source"), (3.25, 4.25, "What it tells the agent"), (7.6, 2.0, "Type of information")]
    for x, w, t in heads:
        box(s, x, 1.3, w, 0.36, t, fill=NAVY, color=WHITE, size=11, bold=True, align="l", margin=0.12, radius=0.05)
    TYPES = {"d": ("Direct structured evidence", BLUE, WHITE), "w": ("Walmart-level context", NAVY, WHITE),
             "r": ("Regional / macro context", SPARK, NAVY)}
    rows = [("db", "Walmart sales data (Kaggle)", "Weekly sales by store and department, with markdowns, fuel, temperature, CPI and "
             "unemployment. Shows exactly what happened vs. last year and other stores.", "d"),
            ("file", "Walmart quarterly earnings releases", "Company-wide comp sales, traffic and ticket each quarter: was Walmart growing or slowing?", "w"),
            ("msg", "Walmart earnings call transcripts", "Management commentary by category, e.g. electronics deflation or Easter timing.", "w"),
            ("book", "Walmart 10-K / annual report", "Merchandise units, strategy and risks: which departments belong together, what Walmart focused on.", "w"),
            ("map", "Federal Reserve Beige Book", "What retailers in each Fed district reported, e.g. “back-to-school items sold well.”", "r"),
            ("gift", "NRF holiday forecast", "Expected holiday spending: was a seasonal drop expected industry-wide?", "r"),
            ("bar", "EIA fuel prices", "Weekly gas prices by region, used to match each store to its likely region.", "r")]
    for i, (ic, name, what, kind) in enumerate(rows):
        y = 1.74 + i * 0.53
        label, col, fg = TYPES[kind]
        box(s, 0.4, y, 9.2, 0.48, None, fill=LIGHT, name=f"source {i + 1}")
        icon(s, ic, 0.48, y + 0.07, 0.34, col, NAVY if col == SPARK else WHITE)
        tx(s, 0.92, y, 2.25, 0.48, [[(name, dict(bold=True, color=NAVY))]], size=10.5, anchor="m")
        tx(s, 3.37, y, 4.15, 0.48, what, size=9, anchor="m")
        pill(s, 7.7, y + 0.1, 1.8, label, col, color=fg, h=0.28, size=9)
    notes(s, """These are the agent's knowledge sources. Only the first is data about the stores themselves: the Kaggle Walmart sales data, which the Evidence Agent checks directly. Everything else is context.

Walmart's own documents (earnings releases, call transcripts, 10-K and annual report) tell the agent what Walmart said about each quarter and category, for example deflation in electronics or the Easter shift. The Federal Reserve Beige Book and the NRF holiday forecast add regional and economy-wide context, matched to the store's Fed district and the same time period.

The EIA fuel price series is used to match each store to its likely region; the fuel prices the agent compares come from the Kaggle data. Department and region names are publicly inferred, not confirmed by Walmart.""")
    return s


# ------------------------------------------------------------------------------------------ evaluation
def evaluation(prs):
    s = new_slide(prs, "How We Will Evaluate the Agent", "Six checks on flagged exceptions")
    auto, people = ("Automatic · every answer", OK_T, GREEN), ("People check · planned", "E8ECF3", NAVY)
    cards = [("calc", "Number accuracy", "Is every number in the agent's answer correct?", auto),
             ("calcheck", "Right time and place", "Is every report from the same quarter and the store's region?",
              ("Automatic · built into search", OK_T, GREEN)),
             ("quote", "Quote accuracy", "Does every quote really appear in the cited report?", auto),
             ("user", "Main factor agreement", "Does the agent pick the same main factor a person would?", people),
             ("cal", "Holiday-shift detection", "Does the agent recognize weeks where a holiday moved?", people),
             ("scale", "Confidence check", "Does the confidence level match the evidence?", people)]
    for i, (ic, title, q, (status, sf, sc)) in enumerate(cards):
        x, y = 0.4 + (i % 3) * 3.1, 1.35 + (i // 3) * 2.0
        box(s, x, y, 2.9, 1.75, None, fill=LIGHT, line=LINEC, lw=1, radius=0.1, name=title)
        icon(s, ic, x + 0.18, y + 0.18, 0.5, BLUE if sc == GREEN else NAVY)
        tx(s, x + 0.8, y + 0.18, 2.0, 0.5, [[(title, dict(bold=True, color=NAVY))]], size=13, anchor="m")
        tx(s, x + 0.2, y + 0.82, 2.55, 0.5, q, size=11)
        pill(s, x + 0.2, y + 1.38, 2.0, status, sf, color=sc, h=0.24, size=8.5)
    notes(s, """Six checks, in two groups.

Automatic, on every answer, before the dashboard shows it:
• Number accuracy: every number in the answer must appear in the evidence the Evidence Agent computed from the sales data.
• Right time and place: built into the search itself. The RAG Agent only searches reports from the same period and the store's Fed district (plus national reports).
• Quote accuracy: anything in quotation marks must appear word for word in a retrieved report.
(The evaluation also checks that every factor cites its evidence and that the answer is complete.) If any automatic check fails, the dashboard flags the answer 'Check before acting'.

People check, planned, not run yet: two teammates independently label about 10 flagged weeks (6 regular, 4 where a holiday moved) and we compare with the agent:
• Main factor agreement: does the agent pick the same main factor a person would?
• Holiday-shift detection: does it recognize the weeks where Easter or Christmas moved?
• Confidence check: is High confidence right more often than Medium?

Why both: the automatic checks catch made-up numbers and quotes. They cannot tell whether the reasoning is right; that is what the people check is for.""")
    return s


def main(dst):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(10), Inches(5.625)
    for fn in (why_agent, sources, system_map, orchestrator, evidence, rag, reasoning, evaluation):
        fn(prs)
    prs.save(dst)
    print("saved", dst, "slides:", len(prs.slides))


if __name__ == "__main__":
    main(sys.argv[1])
