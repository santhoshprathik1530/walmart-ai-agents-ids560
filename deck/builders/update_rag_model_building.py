"""Rework the Domain 5 (Model Building) AI agent slides in both decks (2026-11-02, Santhosh's request): one slide per
JTA Domain V task, with diagrams and native charts instead of text cards.

  V T-1   How the AI Agent Works                 flow diagram, coloured by who does each step (ML model / code / LLM)
  V T-1a  Shared Drop or Store-Specific?         Store 27: Stationery and Electronics at every store (ML forecasts)
  V T-1a  Reasoning, Guardrails and 7 Checks     answer parts + guardrails, and pass counts per check
  V T-2   Case Walkthrough: Store 27             kept as it is
  V T-2   Agent Results on the v4 Top 20         tiles, findings by evidence type, evidence strength
  V T-2   Follow-Up Chat                         example question and answer, and how it was graded
  V T-3   Calibrating the Agent and Its Graders  Haiku vs Sonnet grades, and what we fixed
  V T-4   Integration with the ML Model's v4 Output   the former 'Moving to the v4 Package' slide, moved from Domain 6
  V T-5   Assumptions and Limitations            six cards

Replaces: 'AI Agent Architecture and Data Handoff', 'Orchestrator and Evidence Investigation',
'Reasoning, Guardrails and Code Checks', 'Agent Results and Evaluation Limits'.
Numbers: app/data/agent_outputs_v3_v4.json, app/eval/results/ (agent_v3_summary.json, chat_v3_golden*.json,
grader_comparison.json), app/data/ml_v33_complete/per_store_mad_experiment/per_store_mad_department_flags.csv.

    python3 deck/builders/update_rag_model_building.py
"""
import collections
import json
import sys
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_rag_methodology import (BODY, BROWN, CARD, FILES, FONT, INK, SUB, TITLE, W3, X3, YEL, card, rgb,  # noqa: E402
                                    shape, table, text, title_of)

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
BLUE, LIGHT, MID, GRAY = "2041A9", "A9C1F5", "5B86E8", "B8C4DA"
D5 = "DOMAIN 5  •  MODEL BUILDING"


# ------------------------------------------------------------------------------------------------ frame + helpers
def new_slide(prs, title, subtitle, notes):
    sl = prs.slides.add_slide(prs.slide_layouts[39])        # 'DEFAULT', no placeholders (same in both decks)
    s = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(10), Inches(5.625))
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(BLUE)
    s.line.fill.background()
    s.name = "Background"
    shape(sl, 0.22, 0.12, 9.56, 5.39, "FFFFFF", adj=0.07).name = "Frame"
    text(sl, 0.55, 0.28, 8.9, 0.5, title, size=22, color=TITLE, bold=True).name = "Title"
    text(sl, 0.58, 0.80, 8.9, 0.3, subtitle, size=11, color=SUB).name = "Subtitle"
    t = text(sl, 6.6, 5.1, 2.8, 0.22, D5, size=8, color=TITLE, bold=True)
    t.text_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT
    t.name = "Domain tag"
    sl.notes_slide.notes_text_frame.text = notes
    return sl


def takeaway(sl, label, msg, y=4.62):
    shape(sl, 0.58, y, 8.84, 0.40, YEL, adj=0.25).name = "Takeaway bar"
    t = text(sl, 0.7, y + 0.05, 8.6, 0.3, [[(label + " ", {"bold": True}), (msg, {})]], size=10.5, color=BROWN,
             anchor=MSO_ANCHOR.MIDDLE)
    t.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    t.name = "Takeaway"


def style_chart(ch, legend=False, size=9):
    ch.font.size = Pt(size)
    ch.font.name = FONT
    ch.font.color.rgb = rgb(BODY)
    ch.has_title = False
    ch.has_legend = legend
    if legend:
        ch.legend.position = XL_LEGEND_POSITION.BOTTOM
        ch.legend.include_in_layout = False
    try:
        ch.value_axis.major_gridlines.format.line.color.rgb = rgb("DDE4F0")
        ch.value_axis.format.line.fill.background()
        ch.category_axis.format.line.color.rgb = rgb(GRAY)
    except Exception:
        pass


def colour_points(series, colours):
    for i, c in enumerate(colours):
        pt = series.points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = rgb(c)


# ------------------------------------------------------------------------------------------------ data
def load():
    out = json.load(open(APP / "data" / "agent_outputs_v3_v4.json"))
    ml = pd.read_csv(APP / "data" / "ml_v33_complete" / "per_store_mad_experiment" / "per_store_mad_department_flags.csv",
                     usecols=["Store", "Dept", "Date", "Actual", "Expected"])
    week = ml[ml.Date == "2012-09-14"].assign(Pct=lambda x: (x.Actual / x.Expected - 1) * 100)
    chat = json.load(open(APP / "eval" / "results" / "chat_v3_golden.json"))
    grades = json.load(open(APP / "eval" / "results" / "grader_comparison.json"))
    return out, week, chat, grades


# ------------------------------------------------------------------------------------------------ slides
def how_it_works(prs):
    sl = new_slide(prs, "How the AI Agent Works", "One flagged store-week in, a checked answer out; every step has one owner",
                   "AI agent, part 1 (JTA V T-1 conceptual model). Colours show who does each step. Yellow: the ML model. "
                   "The flag, thresholds, priority and status come straight from their files and the agent never re-judges "
                   "them. Light blue: plain code, which handles every number (comparisons from the ML model's own forecasts, "
                   "the report search with setup E, the 7 checks). Dark blue: the language model (Claude Haiku 5.5), which "
                   "only plans the searches and writes the answer from the facts and passages it is given. If any check "
                   "fails, the dashboard shows 'Answer needs a check' instead of the answer.")
    steps = [("ML FLAG", "Store, week, flagged depts, priority, status", "ml"),
             ("INTAKE", "ML numbers + comparisons from ML forecasts", "code"),
             ("ORCHESTRATOR", "Picks departments, writes 2–4 searches", "llm"),
             ("REPORT SEARCH", "Setup E: 6 Walmart and Fed passages", "code"),
             ("REASONING", "Findings with sources, next steps", "llm"),
             ("7 CHECKS", "Pass: shown. Fail: “needs a check”", "code")]
    fills = {"ml": (YEL, BROWN, INK), "code": (CARD, TITLE, BODY), "llm": (BLUE, "FFFFFF", "FFFFFF")}
    w, gap, y, h = 1.32, 0.18, 1.35, 1.75
    for i, (head, body, kind) in enumerate(steps):
        x = 0.58 + i * (w + gap)
        f, hc, bc = fills[kind]
        shape(sl, x, y, w, h, f, adj=0.12)
        text(sl, x + 0.08, y + 0.12, w - 0.16, 0.25, f"0{i + 1}", size=14, color=hc, bold=True)
        text(sl, x + 0.08, y + 0.45, w - 0.16, 0.45, head, size=8.5, color=hc, bold=True)
        text(sl, x + 0.08, y + 0.92, w - 0.16, 0.8, body, size=9.5, color=bc)
        if i < 5:
            a = sl.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + w + 0.02), Inches(y + h / 2 - 0.07), Inches(0.14), Inches(0.14))
            a.fill.solid()
            a.fill.fore_color.rgb = rgb(TITLE)
            a.line.fill.background()
    # output row
    a = sl.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, Inches(8.65), Inches(3.17), Inches(0.2), Inches(0.25))
    a.fill.solid()
    a.fill.fore_color.rgb = rgb(TITLE)
    a.line.fill.background()
    shape(sl, 5.6, 3.47, 3.82, 0.55, CARD, adj=0.2)
    text(sl, 5.75, 3.52, 3.6, 0.45, [[("Store manager dashboard ", {"bold": True, "color": INK}),
                                      ("+ follow-up chat", {})]], size=11, anchor=MSO_ANCHOR.MIDDLE)
    # legend
    for i, (label, kind) in enumerate([("ML model", "ml"), ("Code", "code"), ("Language model (Haiku 5.5)", "llm")]):
        x = 0.58 + i * 1.15
        shape(sl, x, 3.62, 0.22, 0.22, fills[kind][0], adj=0.2)
        text(sl, x + 0.28, 3.6, 2.2 if kind == "llm" else 0.85, 0.28, label, size=9.5, color=BODY)
    takeaway(sl, "Rule:", "the ML model defines the exception; the agent only finds evidence that supports each flag.")
    return sl


def evidence_charts(prs, week):
    sl = new_slide(prs, "Shared Drop or Store-Specific?", "Store 27, week ending Sep 14, 2012: each flagged department at every store, vs the ML forecast",
                   "AI agent, part 2 (JTA V T-1a build and verify). For every flagged department the code compares the store "
                   "with the same department at every other store that week, using the ML model's own forecasts (Jul 20 - "
                   "Oct 26, 2012, all 45 stores). Left: Stationery was below the forecast at 43 of the 44 other stores, so "
                   "the drop is shared (a category or calendar factor is more likely). Right: Electronics was -28.4% at "
                   "Store 27 while the other New York stores were at or above the forecast (+0.1%, +2.4%, +18.2%) and all "
                   "stores together were +0.3%, so the gap looks specific to this store. Regions are publicly inferred. The "
                   "agent also compares Walmart overall that week, the store's other departments and outside factors.")
    ny = {24, 19, 15}
    for k, (dept, name, x, note) in enumerate([
            (3, "Dept 3 Stationery", 0.58, "43 of 44 other stores below forecast: shared drop"),
            (72, "Dept 72 Electronics", 5.08, "Other New York stores at or above forecast: store-specific")]):
        g = week[week.Dept == dept].sort_values("Pct")
        cd = CategoryChartData()
        cd.categories = [f"Store {s}" for s in g.Store]
        # one series per colour (per-bar colours make LibreOffice draw negative bars upward)
        groups = [("Store 27", BLUE, lambda s: s == 27), ("Other New York stores", MID, lambda s: dept == 72 and s in ny),
                  ("Other stores", LIGHT, lambda s: s != 27 and not (dept == 72 and s in ny))]
        groups = [gr for gr in groups if any(gr[2](s) for s in g.Store)]
        for nm, _, keep in groups:
            cd.add_series(nm, [round(v, 1) if keep(s) else None for s, v in zip(g.Store, g.Pct)])
        shape(sl, x, 1.22, 4.34, 3.25, CARD, adj=0.06)
        text(sl, x + 0.15, 1.3, 4.0, 0.3, [[(name, {"bold": True, "color": TITLE}), ("  % vs ML forecast, one bar per store", {"size": 9, "color": SUB})]], size=11.5)
        gf = sl.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x + 0.08), Inches(1.6), Inches(4.18), Inches(2.3), cd)
        ch = gf.chart
        style_chart(ch)
        ch.category_axis.has_major_gridlines = False
        ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.NONE
        ch.value_axis.tick_labels.number_format = '0"%"'
        ch.value_axis.tick_labels.number_format_is_linked = False
        pl = ch.plots[0]
        pl.gap_width = 40
        pl.overlap = 100
        for ser, (_, colour, _) in zip(pl.series, groups):
            ser.invert_if_negative = False
            ser.format.fill.solid()
            ser.format.fill.fore_color.rgb = rgb(colour)
        text(sl, x + 0.15, 3.92, 4.05, 0.5, [[("Store 27 (dark): ", {"bold": True, "color": INK}), (note, {})]]
             + ([("Mid blue: other New York stores.", {"size": 9, "color": SUB})] if dept == 72 else []), size=10)
    takeaway(sl, "Method:", "the same comparison runs for every flagged department, from the ML model’s own forecasts.")
    return sl


def reasoning(prs, out):
    sl = new_slide(prs, "Reasoning, Guardrails and 7 Checks", "The language model writes the answer; code checks it before anyone sees it",
                   "AI agent, part 3 (JTA V T-1a build and verify). The answer has the parts on the left, in plain words for a "
                   "store manager. Guardrails come from the ML files and the rule that the ML model owns the exception. The 7 "
                   "checks are code, not an LLM: they test that every number and quote is in the evidence, every finding "
                   "cites and is tagged, the answer is complete, the guardrails hold and the largest flagged department is "
                   "covered. They test grounding, not whether the reason is right. Counts: v4 Top 20 run (Nov 2) and the "
                   "earlier 40-case v3.4 run, where one quote was not word for word.")
    shape(sl, 0.58, 1.25, 3.7, 3.2, CARD, adj=0.06)
    text(sl, 0.74, 1.35, 3.4, 0.3, "THE ANSWER", size=12, color=TITLE, bold=True)
    parts = [("Verdict + evidence found", "Strong / Some / Little", BLUE, "FFFFFF"),
             ("Why it happened", "findings, each with a source", MID, "FFFFFF"),
             ("What to do next", "checks for the store", LIGHT, INK),
             ("What was not found", "stated plainly", "FFFFFF", INK)]
    for i, (h, b, f, c) in enumerate(parts):
        yy = 1.72 + i * 0.4
        shape(sl, 0.74, yy, 3.38, 0.34, f, adj=0.25)
        text(sl, 0.84, yy + 0.03, 3.2, 0.28, [[(h + "  ", {"bold": True}), (b, {"size": 9})]], size=10, color=c, anchor=MSO_ANCHOR.MIDDLE)
    text(sl, 0.74, 3.36, 3.4, 1.05, [("GUARDRAILS", {"bold": True, "color": TITLE, "size": 10, "space": 2}),
                                     ("No verified cause · no “lost sales” · no markdown cause · scores are not "
                                      "probabilities · no doubt cast on the ML flag", {"size": 9.5})])
    v4 = collections.Counter(k["name"] for x in out.values() for k in x["evaluation"]["checks"] if k["passed"])
    v34 = json.load(open(APP / "eval" / "results" / "agent_v3_summary.json"))["check_pass"]
    names = list(v34)
    rows = [["Code check", "v4 Top 20", "v3.4 (40)"]] + [[n, f"{v4[n]} / 20", f"{v34[n]} / 40"] for n in names]
    table(sl, 4.45, 1.25, [2.85, 1.05, 1.07], 0.4, rows, size=10)
    takeaway(sl, "Result:", "a failed check never reaches the manager; it shows “Answer needs a check”.")
    return sl


def results(prs, out):
    n = len(out)
    ev = collections.Counter(x["report"]["evidence_found"] for x in out.values())
    passed = sum(x["evaluation"]["passed"] for x in out.values())
    scopes = collections.Counter(f["scope"] for x in out.values() for f in x["report"]["findings"])
    per = sum(len(x["report"]["findings"]) for x in out.values()) / n
    secs = sum(x["seconds"] for x in out.values()) / n
    cite = sum(any(f["scope"] == "report" for f in x["report"]["findings"]) for x in out.values())
    sl = new_slide(prs, "Agent Results on the v4 Top 20", f"ML rank 1–20 of 127 store-weeks, Claude Haiku 5.5, one model for the whole run",
                   f"AI agent, part 5 (JTA V T-2 run and evaluate). v4 Top 20: {n} of {n} answered, {passed} of {n} passed all 7 "
                   f"checks; evidence found {ev['Strong']} Strong, {ev['Some']} Some, {ev['Little']} Little; {per:.1f} findings per "
                   f"case; {cite} of {n} answers cite a Walmart or Fed report; about {secs:.0f} seconds per case. Findings are "
                   "tagged by what the evidence is about: the store's own other departments, a report, the same department at "
                   "other stores, Walmart overall, the region, or outside factors. Earlier 40-case v3.4 run for comparison: "
                   "35 Strong, 5 Some, 39 of 40 passed all checks. The remaining 107 v4 cases have not been run.")
    for i, (b, s) in enumerate([(f"{n} / {n}", "answered"), (f"{passed} / {n}", "passed all 7 checks"),
                                (f"{per:.1f}", "findings per case"), (f"{secs:.0f} s", "per store-week")]):
        x = 0.58 + i * 2.25
        shape(sl, x, 1.22, 2.09, 0.82, CARD, adj=0.14)
        text(sl, x + 0.12, 1.26, 1.85, 0.4, b, size=19, color=TITLE, bold=True)
        text(sl, x + 0.12, 1.68, 1.85, 0.3, s, size=9.5, color=SUB)
    # findings by evidence type
    label = {"store": "Store’s other depts", "report": "Walmart / Fed report", "department": "Same dept, other stores",
             "walmart": "Walmart overall", "region": "Same region", "outside": "Outside factors", "ml_note": "ML model note"}
    order = [k for k, _ in scopes.most_common()][::-1]
    shape(sl, 0.58, 2.18, 5.05, 2.3, CARD, adj=0.06)
    text(sl, 0.72, 2.24, 4.8, 0.3, [[("What the findings were about", {"bold": True, "color": TITLE}),
                                     (f"  ({sum(scopes.values())} findings)", {"size": 9, "color": SUB})]], size=11)
    cd = CategoryChartData()
    cd.categories = [label[k] for k in order]
    cd.add_series("Findings", [scopes[k] for k in order])
    gf = sl.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.68), Inches(2.5), Inches(4.85), Inches(1.95), cd)
    ch = gf.chart
    style_chart(ch)
    ch.value_axis.visible = False
    ch.value_axis.has_major_gridlines = False
    pl = ch.plots[0]
    pl.gap_width = 45
    pl.has_data_labels = True
    pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    pl.data_labels.font.size = Pt(9)
    pl.data_labels.font.bold = True
    pl.data_labels.font.color.rgb = rgb(INK)
    pl.series[0].format.fill.solid()
    pl.series[0].format.fill.fore_color.rgb = rgb(BLUE)
    # evidence strength, two runs
    shape(sl, 5.78, 2.18, 3.64, 2.3, CARD, adj=0.06)
    text(sl, 5.92, 2.24, 3.4, 0.3, "Evidence found per case", size=11, color=TITLE, bold=True)
    cd = CategoryChartData()
    cd.categories = ["v3.4 (40)", "v4 Top 20"]          # bar charts draw bottom-up: v4 ends on top
    cd.add_series("Strong", (35, ev["Strong"]))
    cd.add_series("Some", (5, ev["Some"]))
    cd.add_series("Little", (0, ev["Little"]))
    gf = sl.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED_100, Inches(5.86), Inches(2.5), Inches(3.48), Inches(1.95), cd)
    ch = gf.chart
    style_chart(ch, legend=True)
    ch.value_axis.visible = False
    ch.value_axis.has_major_gridlines = False
    pl = ch.plots[0]
    pl.gap_width = 55
    pl.has_data_labels = True
    pl.data_labels.position = XL_LABEL_POSITION.CENTER
    pl.data_labels.font.size = Pt(9)
    pl.data_labels.font.bold = True
    for s, c in zip(pl.series, (BLUE, LIGHT, GRAY)):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = rgb(c)
    pl.series[0].data_labels.show_value = True
    pl.series[0].data_labels.font.color.rgb = rgb("FFFFFF")
    pl.series[0].data_labels.font.bold = True
    pl.series[2].data_labels.show_value = False
    takeaway(sl, "Result:", f"{cite} of {n} answers cite a Walmart or Fed report; no case came back with little evidence.")
    return sl


def chat_slide(prs, chat, grades):
    c = chat["C01"]
    n, strict = len(chat), sum(v["correct"] for v in chat.values())
    checks = sum(v["checks_passed"] for v in chat.values())
    ms = sum(v["ms"] for v in chat.values()) / n / 1000
    sonnet = grades["chat"]["sonnet_full_marks"]
    sl = new_slide(prs, "Follow-Up Chat", "A manager can ask about any flagged week; the chat follows the same rules and checks",
                   f"AI agent, part 6 (JTA V T-2 run and evaluate). The chat (agents/chat_v3.py) answers in 2-4 sentences from "
                   f"the case facts, a store lookup tool and a fresh report search (setup E, same week and Fed district), and "
                   f"its answers go through the same number, quote and guardrail checks. Tested on the 20 approved case "
                   f"questions (written on the v3.4 cases): {checks} of {n} passed the checks, about {ms:.1f} seconds each. "
                   f"A strict code test that looks for every reference number found {strict} of {n}; the 5 misses wrote the "
                   f"department name without its number (for example 'Stationery' instead of 'Dept 3 Stationery') or wrote a "
                   f"zero differently. Claude Sonnet 5.5, grading against the reference, marked {sonnet} of {n} correct.")
    shape(sl, 0.58, 1.25, 5.2, 3.2, CARD, adj=0.06)
    text(sl, 0.74, 1.33, 4.9, 0.3, "EXAMPLE · CASE QUESTION C01", size=10.5, color=TITLE, bold=True)
    shape(sl, 0.74, 1.68, 4.88, 0.62, BLUE, adj=0.2)
    text(sl, 0.86, 1.72, 4.66, 0.55, c["question"], size=10, color="FFFFFF", anchor=MSO_ANCHOR.MIDDLE)
    shape(sl, 0.74, 2.4, 4.88, 1.95, "FFFFFF", adj=0.08)
    text(sl, 0.86, 2.5, 4.66, 1.8, c["answer"], size=11.5, color=BODY)
    tiles = [(f"{sonnet} / {n}", "correct, graded by Sonnet"), (f"{strict} / {n}", "strict number match in code"),
             (f"{checks} / {n}", "passed the checks"), (f"{ms:.1f} s", "per answer")]
    for i, (b, s) in enumerate(tiles):
        y = 1.25 + i * 0.82
        shape(sl, 5.95, y, 3.47, 0.7, CARD, adj=0.15)
        text(sl, 6.08, y + 0.07, 1.35, 0.55, b, size=17, color=TITLE, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        text(sl, 7.42, y + 0.07, 1.95, 0.55, s, size=10, color=BODY, anchor=MSO_ANCHOR.MIDDLE)
    takeaway(sl, "Why two scores:", "the strict test missed “Stationery” written without “Dept 3”; the answers were right.")
    return sl


def calibration(prs, grades):
    sl = new_slide(prs, "Calibrating the Agent and Its Graders", "What we adjusted so the results are fair and repeatable",
                   "AI agent, part 7 (JTA V T-3 calibrate models and data). Graders: Haiku wrote the answers and also graded "
                   "them, so Claude Sonnet 5.5 re-graded A2, E and F. On the weak setup A2 Haiku said 64% correct and Sonnet "
                   "44% (they agreed on 28 of 36 items); on E they agreed on 35 of 37 (88% vs 87%). So we report both. Agent: "
                   "one model is pinned for every batch run (no fallback), so runs are comparable. Facts: after adding the "
                   "earlier-year dollar figures and one-decimal chain rates to what the agent receives, 20 of 20 golden case "
                   "facts were available (was 16). Checks: two false alarms were fixed (a sales fact quoted word for word; "
                   "hedged wording such as 'a possible explanation rather than a confirmed one'), and a guardrail was added "
                   "so the agent never questions the ML forecast. Check changes were re-scored on the saved "
                   "answers in code, without new LLM calls.")
    shape(sl, 0.58, 1.25, 4.3, 3.2, CARD, adj=0.06)
    text(sl, 0.72, 1.32, 4.0, 0.3, [[("Answers graded correct", {"bold": True, "color": TITLE}),
                                     ("  same answers, two graders", {"size": 9, "color": SUB})]], size=11)
    cd = CategoryChartData()
    cd.categories = ["A2 (first app)", "E (chosen)", "F (reranked)"]
    cd.add_series("Haiku", (grades["A2"]["haiku_correct"], grades["E"]["haiku_correct"], grades["F"]["haiku_correct"]))
    cd.add_series("Sonnet", (grades["A2"]["sonnet_correct"], grades["E"]["sonnet_correct"], grades["F"]["sonnet_correct"]))
    gf = sl.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.68), Inches(1.62), Inches(4.1), Inches(2.4), cd)
    ch = gf.chart
    style_chart(ch, legend=True)
    ch.value_axis.maximum_scale = 100
    ch.value_axis.minimum_scale = 0
    ch.value_axis.tick_labels.number_format = '0"%"'
    ch.value_axis.tick_labels.number_format_is_linked = False
    pl = ch.plots[0]
    pl.gap_width = 70
    pl.has_data_labels = True
    pl.data_labels.number_format = '0"%"'
    pl.data_labels.number_format_is_linked = False
    pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    pl.data_labels.font.size = Pt(9)
    pl.data_labels.font.bold = True
    for s, c in zip(pl.series, (LIGHT, BLUE)):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = rgb(c)
    text(sl, 0.72, 4.02, 4.05, 0.4, "Haiku was easier on the weak setup; on E the two agree.", size=9.5, color=SUB)
    fixes = [("ONE MODEL PER RUN", "Haiku 5.5 pinned, no fallback, so runs compare."),
             ("FACTS THE AGENT GETS", "Golden case facts available: 16 → 20 of 20."),
             ("CHECKS", "Two false alarms fixed; new guardrail: never question the ML forecast.")]
    for i, (h, b) in enumerate(fixes):
        y = 1.25 + i * 1.08
        shape(sl, 5.05, y, 4.37, 0.96, CARD, adj=0.12)
        text(sl, 5.2, y + 0.07, 4.1, 0.28, h, size=10.5, color=TITLE, bold=True)
        text(sl, 5.2, y + 0.36, 4.1, 0.58, b, size=10.5, color=BODY)
    takeaway(sl, "Practice:", "check changes are re-scored on saved answers in code, with no new LLM calls.")
    return sl


def limits(prs):
    sl = new_slide(prs, "Assumptions and Limitations", "What the agent’s answers can and cannot tell an analyst",
                   "AI agent, part 9 (JTA V T-5 document findings, assumptions and limitations). The ML flag, thresholds, "
                   "priority and status are used as given. Department names and store regions are publicly inferred (with a "
                   "confidence level) and are not validated with internal Walmart knowledge. Walmart and Fed reports are "
                   "company- or district-level, so they give context, never proof for one store. Markdowns are recorded for "
                   "the whole store only. The 7 checks test grounding; the graders are language models and the benchmark "
                   "is small. Not done yet: the blind labels on 10 cases by two teammates, and the other 107 v4 cases.")
    cards = [("ML FLAG AS GIVEN", "Flags, thresholds, priority and status come from the ML files; the agent never re-judges them."),
             ("INFERRED MAPPINGS", "Department names and store regions are publicly inferred, each with a confidence level."),
             ("REPORTS = CONTEXT", "Walmart and Fed reports cover the company or a district, never one store."),
             ("MARKDOWNS", "Markdowns are recorded per store-week; they cannot be tied to a department."),
             ("CHECKS ≠ TRUTH", "Checks test grounding. Graders are LLMs and the benchmark is small."),
             ("NOT DONE YET", "Blind labels on 10 cases by two teammates; the other 107 v4 cases.")]
    for i, (h, b) in enumerate(cards):
        card(sl, X3[i % 3], 1.25 if i < 3 else 2.9, W3, 1.5, f"0{i + 1}", h, [(b, {"size": 10.5})])
    takeaway(sl, "Bottom line:", "decision support only; every flagged week still needs analyst review.")
    return sl


# ------------------------------------------------------------------------------------------------ apply
OLD = ["AI Agent Architecture and Data Handoff", "Orchestrator and Evidence Investigation",
       "Reasoning, Guardrails and Code Checks", "Agent Results and Evaluation Limits"]


def retag_v4(sl):
    named = {s.name: s for s in sl.shapes}
    for key, val in (("Title", "Integration with the ML Model’s v4 Output"), ("Domain tag", D5)):
        runs = [r for p in named[key].text_frame.paragraphs for r in p.runs]
        runs[0].text = val
        for r in runs[1:]:
            r.text = ""
    nt = sl.notes_slide.notes_text_frame
    nt.text = "AI agent, part 8 (JTA V T-4 integrate the models). " + nt.text.split(") ", 1)[-1]


def update(path):
    out, week, chat, grades = load()
    prs = Presentation(path)
    lst = prs.slides._sldIdLst
    sid_of = {title_of(s): sid for s, sid in zip(prs.slides, list(lst))}
    slide_of = {title_of(s): s for s in prs.slides}
    anchor = list(lst).index(sid_of[OLD[0]])
    walk = sid_of["Case Walkthrough: Store 27"]
    v4 = sid_of["Moving to the v4 Package"]
    retag_v4(slide_of["Moving to the v4 Package"])
    new = [how_it_works(prs), evidence_charts(prs, week), reasoning(prs, out)]
    new_ids = list(lst)[-3:]
    tail = [results(prs, out), chat_slide(prs, chat, grades), calibration(prs, grades)]
    tail_ids = list(lst)[-3:]
    limits(prs)
    lim_id = list(lst)[-1]
    seq = new_ids + [walk] + tail_ids + [v4, lim_id]
    for t in OLD:
        prs.part.drop_rel(sid_of[t].rId)
        lst.remove(sid_of[t])
    for sid in seq:
        lst.remove(sid)
    for k, sid in enumerate(seq):
        lst.insert(anchor + k, sid)
    prs.save(path)
    print(f"{path.name}: {len(prs.slides)} slides")


if __name__ == "__main__":
    for f in FILES:
        update(f)
