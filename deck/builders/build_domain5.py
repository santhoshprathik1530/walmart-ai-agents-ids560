"""Domain 5 (Model Building) for the AI agent, as its own deck (2026-11-02, Santhosh: redo Domain 5 so the order, flow
and headings make sense to the audience and every JTA Domain V task is answered; keep slides clean).

The story follows Store 27 (the ML model's rank-1 v4 case) through the agent's six steps, then zooms out:
  1  What the Agent Receives, and What It Answers   V T-4 integrate (input = the ML model's v4 output)
  2  Six Steps from Flag to Answer                  V T-1 conceptual model (step names match the slide titles below)
  3  Step 2 · Compare Stores                        V T-1a build
  4  Steps 3–4 · Plan and Search the Reports        V T-1a build
  5  Step 5 · Write the Answer                      V T-1a build, T-2 run
  6  Step 6 · Check the Answer                      V T-1a verify
  7  Results on the Top 20                          V T-2 run and evaluate
  8  Tuning the Agent                               V T-3 calibrate
  9  What the Agent Can and Cannot Tell You         V T-5 assumptions and limitations
Details live in the speaker notes. Numbers come from app/data/agent_outputs_v3_v4.json, app/eval/results/ and the ML
team's forecast file.

    python3 deck/builders/build_domain5.py
"""
import collections
import json
import sys
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_rag_methodology import BODY, BROWN, CARD, INK, SUB, TITLE, YEL, rgb, shape, text  # noqa: E402
from update_rag_model_building import APP, BLUE, LIGHT, MID, new_slide, style_chart, takeaway  # noqa: E402

DECK = Path(__file__).resolve().parent.parent
SRC = DECK / "AI Agents and RAG - Final Presentation Slides.pptx"      # same theme, layouts and fonts
OUT = DECK / "AI Agents - Domain 5 (Model Building).pptx"
GREEN = "2E8B57"
CID = "Store_27_2012-09-14"


def arrow(sl, x, y, w=0.16, h=0.16, kind=MSO_SHAPE.RIGHT_ARROW):
    a = sl.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    a.fill.solid()
    a.fill.fore_color.rgb = rgb(TITLE)
    a.line.fill.background()


def bullets(items, size=12, space=10):
    return [("•  " + t, {"size": size, "space": space}) for t in items]


def panel(sl, x, y, w, h, head, fill=CARD, head_color=TITLE):
    shape(sl, x, y, w, h, fill, adj=0.06)
    text(sl, x + 0.2, y + 0.12, w - 0.4, 0.3, head, size=10.5, color=head_color, bold=True)


# ------------------------------------------------------------------------------------------------ 1  T-4
def s1_receives(prs, v4):
    sl = new_slide(prs, "What the Agent Receives, and What It Answers",
                   "Input: the ML model’s v4 output, 127 store-weeks, Top 20 reviewed first",
                   "JTA V T-4 (integrate the models). The agent reads the ML model's final v4 output directly (127 case files, "
                   "Extra Trees + Global MAD, Isolation Forest as a supporting signal) through a v4 loader "
                   "(agents/cases_v3.py, AGENT_CASE_SET=v4). Flags, priority and status are used exactly as given; the agent "
                   "never re-judges them. v4 has no per-department history, peer rates or per-store thresholds, so the "
                   "comparisons in step 2 come from the ML model's forecast file, which matches v4 exactly on actual and "
                   "expected sales. Example for the whole section: the ML model's rank-1 case, Store 27 (also on the ML section's Three "
                   f"Store-Week slide): ${v4['net']:,.0f} net modeled shortfall, {v4['flagged']} of {v4['depts']} departments "
                   "flagged, status 'Needs analyst review'. The agent's question is not whether the flag is right, but what "
                   "evidence supports it and what the store should check.")
    panel(sl, 0.58, 1.3, 4.0, 3.12, "FROM THE ML MODEL · RANK 1 OF 127")
    text(sl, 0.78, 1.8, 3.6, 0.4, "Store 27 · week of Sep 14, 2012", size=14, color=INK, bold=True)
    text(sl, 0.78, 2.3, 3.6, 0.6, f"${v4['net']:,.0f}", size=30, color=TITLE, bold=True)
    text(sl, 0.78, 2.92, 3.6, 0.3, "below the ML forecast (net)", size=10.5, color=SUB)
    text(sl, 0.78, 3.4, 3.6, 0.9, [(f"{v4['flagged']} of {v4['depts']} departments flagged", {"space": 4}),
                                   ("Status: Needs analyst review", {})], size=11.5, color=BODY)
    arrow(sl, 4.72, 2.7, 0.36, 0.32)
    shape(sl, 5.22, 1.3, 4.2, 3.12, BLUE, adj=0.06)
    text(sl, 5.42, 1.42, 3.8, 0.3, "THE AGENT’S QUESTION", size=10.5, color="FFFFFF", bold=True)
    text(sl, 5.42, 1.95, 3.8, 2.2, "What evidence supports this flag, and what should the store check?",
         size=20, color="FFFFFF", bold=True)
    takeaway(sl, "Roles:", "the ML model decides what is unusual; the agent finds the evidence and the next checks.")


# ------------------------------------------------------------------------------------------------ 2  T-1
STEPS = [("1", "ML FLAG", "The ML model’s case, used as given", "ml"),
         ("2", "COMPARE STORES", "Did other stores drop too?", "code"),
         ("3", "PLAN SEARCHES", "Pick the biggest gaps, write questions", "llm"),
         ("4", "SEARCH REPORTS", "Walmart and Fed, same weeks and region", "code"),
         ("5", "WRITE ANSWER", "Why it happened, what to check", "llm"),
         ("6", "CHECK ANSWER", "7 code checks before it is shown", "code")]


def s2_steps(prs):
    sl = new_slide(prs, "Six Steps from Flag to Answer", "Each step has one owner; the next slides follow Store 27 through steps 2 to 6",
                   "JTA V T-1 (conceptual model). Yellow: the ML model (flag, thresholds, priority, status, used as given). "
                   "Light blue: code, which handles every number: step 2 compares each flagged department with every other "
                   "store, the same region, the store's other departments, Walmart overall and outside factors, all from the "
                   "ML model's forecasts; step 4 searches the reports with setup E (chosen in Domain 4); step 6 runs 7 checks. "
                   "Dark blue: the language model (Claude Haiku 5.5): step 3 picks the 1-3 departments with the biggest dollar "
                   "gaps and writes 2-4 search questions; step 5 writes the answer from the evidence and passages only. The "
                   "answer goes to the analyst dashboard (Domain 6).")
    fills = {"ml": (YEL, BROWN, INK), "code": (CARD, TITLE, BODY), "llm": (BLUE, "FFFFFF", "FFFFFF")}
    w, gap, y, h = 1.32, 0.18, 1.35, 1.75
    for i, (n, head, body, kind) in enumerate(STEPS):
        x = 0.58 + i * (w + gap)
        f, hc, bc = fills[kind]
        shape(sl, x, y, w, h, f, adj=0.12)
        text(sl, x + 0.1, y + 0.12, w - 0.2, 0.3, n, size=16, color=hc, bold=True)
        text(sl, x + 0.1, y + 0.5, w - 0.2, 0.42, head, size=9, color=hc, bold=True)
        text(sl, x + 0.1, y + 0.95, w - 0.2, 0.75, body, size=10, color=bc)
        if i < 5:
            arrow(sl, x + w + 0.02, y + h / 2 - 0.07, 0.14, 0.14)
    arrow(sl, 8.66, 3.17, 0.2, 0.25, MSO_SHAPE.DOWN_ARROW)
    shape(sl, 5.6, 3.47, 3.82, 0.55, CARD, adj=0.2)
    text(sl, 5.75, 3.52, 3.6, 0.45, [[("Analyst dashboard ", {"bold": True, "color": INK}), ("(Domain 6)", {})]],
         size=11, anchor=MSO_ANCHOR.MIDDLE)
    for i, (label, kind) in enumerate([("ML model", "ml"), ("Code", "code"), ("Language model", "llm")]):
        x = 0.58 + i * 1.3
        shape(sl, x, 3.62, 0.22, 0.22, fills[kind][0], adj=0.2)
        text(sl, x + 0.28, 3.6, 1.4, 0.28, label, size=9.5, color=BODY)
    takeaway(sl, "Design rule:", "code handles every number; the language model only plans searches and writes.")


# ------------------------------------------------------------------------------------------------ 3  T-1a
def s3_compare(prs, week):
    sl = new_slide(prs, "Step 2 · Compare Stores", "Five comparisons for every flagged department; two Store 27 examples (one bar per store, % vs ML forecast)",
                   "JTA V T-1a (build). For every flagged department, code compares the store with the same department at "
                   "every other store that week, using the ML model's own forecasts (Jul 20 - Oct 26, 2012, all 45 stores). "
                   "Stationery: below forecast at 43 of 44 other stores, so the drop is shared and a wider cause (season, "
                   "category, calendar) is more likely. Electronics: -28.4% at Store 27 while the other New York stores were "
                   "at or above forecast (+0.1%, +2.4%, +18.2%) and all stores together +0.3%, so the store should look at its "
                   "own stock, pricing and displays. Regions are publicly inferred. The same step also compares Walmart "
                   "overall that week (-5.3%), the store's other departments (60 of 69 below forecast) and outside factors "
                   "(holiday, fuel, temperature, unemployment).")
    comps = ["Same department, every other store", "Same department, same region", "The store\u2019s other departments",
             "Walmart overall that week", "Outside factors: holiday, fuel, weather, jobs"]
    panel(sl, 0.58, 1.25, 2.95, 3.22, "5 COMPARISONS")
    for i, c in enumerate(comps):
        y = 1.66 + i * 0.55
        hot = i < 2                                   # shown in the two examples
        shape(sl, 0.74, y, 2.63, 0.46, BLUE if hot else "FFFFFF", adj=0.18)
        text(sl, 0.84, y + 0.03, 2.45, 0.4, [[(f"{i + 1}  ", {"bold": True}), (c, {})]], size=9.5,
             color="FFFFFF" if hot else INK, anchor=MSO_ANCHOR.MIDDLE)
    ny = {24, 19, 15}
    for dept, name, x, verdict in [(3, "Stationery", 3.68, "Shared: 43 of 44 stores fell too"),
                                   (72, "Electronics", 6.58, "Only here: NY stores did not fall")]:
        g = week[week.Dept == dept].sort_values("Pct")
        groups = [("Store 27", BLUE, lambda s: s == 27), ("Other New York stores", MID, lambda s: dept == 72 and s in ny),
                  ("Other stores", LIGHT, lambda s: s != 27 and not (dept == 72 and s in ny))]
        groups = [gr for gr in groups if any(gr[2](s) for s in g.Store)]
        cd = CategoryChartData()
        cd.categories = [f"Store {s}" for s in g.Store]
        for nm, _, keep in groups:
            cd.add_series(nm, [round(v, 1) if keep(s) else None for s, v in zip(g.Store, g.Pct)])
        panel(sl, x, 1.25, 2.84, 3.22, "EXAMPLE \u00b7 " + name.upper())
        gf = sl.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x + 0.05), Inches(1.58), Inches(2.74), Inches(2.25), cd)
        ch = gf.chart
        style_chart(ch, size=8)
        ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.NONE
        ch.value_axis.tick_labels.number_format = '0"%"'
        ch.value_axis.tick_labels.number_format_is_linked = False
        pl = ch.plots[0]
        pl.gap_width = 30
        pl.overlap = 100
        for ser, (_, colour, _) in zip(pl.series, groups):
            ser.invert_if_negative = False
            ser.format.fill.solid()
            ser.format.fill.fore_color.rgb = rgb(colour)
        text(sl, x + 0.16, 3.88, 2.6, 0.55, [[("Store 27 (dark). ", {"bold": True, "color": INK}), (verdict, {})]], size=9.5)
    takeaway(sl, "Why it matters:", "shared drop → look for a wider cause; only here → check the store.")


# ------------------------------------------------------------------------------------------------ 4  T-1a
def s4_search(prs, case):
    f = case["rag"]["filter"]
    sl = new_slide(prs, "Steps 3–4 · Plan and Search the Reports", "The agent asks the reports about the biggest gaps",
                   "JTA V T-1a (build). Step 3, the language model: picks the 1-3 departments with the biggest dollar gaps "
                   "(Store 27: Stationery $34,988, Snacks & Beverages $17,446, Electronics $15,397) and writes 2-4 search "
                   "questions (the slide shortens the three it wrote). Step 4, code, setup E: only reports whose period covers, "
                   f"or that were published in, the case week and the 3 weeks before ({f['start']} to {f['end']}); Beige Books "
                   "only for national and the store's Fed district (New York); at least one Walmart passage and one local Beige "
                   "Book passage are kept; 6 passages go to step 5. The Q3 FY2013 earnings release counts because it covers the "
                   "quarter, although it was published on Nov 15.")
    panel(sl, 0.58, 1.3, 4.34, 3.12, "STEP 3 · QUESTIONS THE AGENT WROTE")
    qs = ["What did Walmart’s Q3 results say about back-to-school and stationery?",
          "What did Walmart and the New York Fed say about electronics demand?",
          "What did the New York Fed say about spending, fuel and weather in September?"]
    for i, q in enumerate(qs):
        y = 1.78 + i * 0.85
        shape(sl, 0.78, y, 3.94, 0.72, "FFFFFF", adj=0.15)
        text(sl, 0.9, y + 0.04, 3.72, 0.64, q, size=10.5, color=INK, anchor=MSO_ANCHOR.MIDDLE)
    arrow(sl, 5.0, 2.7, 0.3, 0.3)
    panel(sl, 5.38, 1.3, 4.04, 3.12, "STEP 4 · 6 PASSAGES FOUND")
    rows = [("Fed Beige Book, New York", "Oct 10"), ("Fed Beige Book, national", "Aug 29, Oct 10"),
            ("Walmart Q3 earnings release", "2 passages"), ("Walmart Q3 earnings call", "1 passage")]
    for i, (a, b) in enumerate(rows):
        y = 1.78 + i * 0.64
        shape(sl, 5.58, y, 3.64, 0.52, "FFFFFF", adj=0.18)
        text(sl, 5.7, y + 0.04, 3.45, 0.44, [[(a, {"bold": True, "color": INK}), ("   " + b, {"size": 9.5, "color": SUB})]],
             size=10.5, anchor=MSO_ANCHOR.MIDDLE)
    takeaway(sl, "Search filter:", "reports for Aug 24 – Sep 14, 2012; Walmart plus the national and New York Fed.")


# ------------------------------------------------------------------------------------------------ 5  T-1a / T-2
def s5_answer(prs):
    sl = new_slide(prs, "Step 5 · Write the Answer", "What the analyst reads for Store 27",
                   "JTA V T-1a (build), T-2 (run). The language model writes the answer only from the step 2 evidence and the "
                   "step 4 passages. This is the saved answer for Store 27 (agent_outputs_v3_v4.json), shortened. Evidence "
                   "found: Strong. Shared drops (Stationery, Lawn & Garden) go to 'why it happened'; the store-only drop "
                   "(Electronics) goes to 'what to check'. The quote is word for word from the Oct 10, 2012 Beige Book (New "
                   "York District); the agent states it describes the district in August-September, not this week or store. "
                   "Guardrails: no verified or confirmed cause, no 'lost sales', no markdown as a cause, never questions the "
                   "ML flag.")
    cols = [("WHY IT HAPPENED", ["Stationery and Lawn & Garden fell at almost every store",
                                 "Walmart overall −5.3% that week; Store 27 −13.7%"]),
            ("WHAT TO CHECK", ["Electronics: −28.4% only here; check pricing, displays, stock",
                               "Stock and deliveries in Stationery and Lawn & Garden"])]
    for i, (h, items) in enumerate(cols):
        x = 0.58 + i * 4.5
        panel(sl, x, 1.3, 4.34, 1.95, h)
        text(sl, x + 0.2, 1.72, 3.95, 1.5, bullets(items, size=13.5), color=BODY)
    shape(sl, 0.58, 3.4, 8.84, 1.02, CARD, adj=0.12)
    text(sl, 0.8, 3.46, 8.4, 0.92, [
        ("“Some of the weakness is attributed to unseasonably mild weather, which dampened sales of seasonal "
         "merchandise.”", {"size": 12.5, "bold": True, "color": INK, "space": 3}),
        ("Fed Beige Book, New York District, Oct 10, 2012 · context for Lawn & Garden, not proof for this store",
         {"size": 9.5, "color": SUB})], anchor=MSO_ANCHOR.MIDDLE)
    takeaway(sl, "Evidence found: Strong.", "The answer supports the flag and never claims a verified cause.")


# ------------------------------------------------------------------------------------------------ 6  T-1a verify
def s6_check(prs, case):
    names = [k["name"] for k in case["evaluation"]["checks"]]
    sl = new_slide(prs, "Step 6 · Check the Answer", "Seven code checks run before anyone sees the answer",
                   "JTA V T-1a (verify). The checks are code, not a language model. They confirm every number and quote is in "
                   "the evidence, every finding cites evidence and is tagged by type, the answer is complete, the guardrails "
                   "hold, and the department with the biggest gap is covered. Store 27 passed all 7, so the answer is shown. "
                   "If any check fails, the dashboard shows 'Answer needs a check' instead, and an analyst looks at it. The "
                   "checks test that the answer is grounded, not that the reason is right (that needs the blind labels, see "
                   "the last slide).")
    panel(sl, 0.58, 1.3, 4.6, 3.12, "STORE 27 · 7 OF 7 PASSED")
    for i, n in enumerate(names):
        y = 1.75 + i * 0.37
        d = sl.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.8), Inches(y + 0.07), Inches(0.17), Inches(0.17))
        d.fill.solid()
        d.fill.fore_color.rgb = rgb(GREEN)
        d.line.fill.background()
        text(sl, 1.08, y, 4.0, 0.3, n, size=11, color=BODY)
    panel(sl, 5.35, 1.3, 4.07, 1.45, "ALL PASS")
    text(sl, 5.55, 1.72, 3.7, 0.9, "The answer is shown to the analyst.", size=12, color=BODY)
    shape(sl, 5.35, 2.97, 4.07, 1.45, YEL, adj=0.1)
    text(sl, 5.55, 3.09, 3.7, 0.3, "ANY CHECK FAILS", size=10.5, color=BROWN, bold=True)
    text(sl, 5.55, 3.5, 3.7, 0.85, "The dashboard shows “Answer needs a check” instead.", size=12, color=INK)
    takeaway(sl, "Limit:", "the checks prove the answer is grounded, not that the reason is right.")


# ------------------------------------------------------------------------------------------------ 7  T-2
def s7_results(prs, out):
    n = len(out)
    ev = collections.Counter(x["report"]["evidence_found"] for x in out.values())
    passed = sum(x["evaluation"]["passed"] for x in out.values())
    scopes = collections.Counter(f["scope"] for x in out.values() for f in x["report"]["findings"])
    secs = sum(x["seconds"] for x in out.values()) / n
    cite = sum(any(f["scope"] == "report" for f in x["report"]["findings"]) for x in out.values())
    sl = new_slide(prs, "Results on the Top 20", "ML rank 1–20 of 127 store-weeks · one model (Claude Haiku 5.5) for the whole run",
                   f"JTA V T-2 (run and evaluate). v4 Top 20, run Nov 2, 2026: {n} of {n} answered, {passed} of {n} passed all 7 "
                   f"checks, evidence found {ev['Strong']} Strong and {ev['Some']} Some (none Little), {cite} of {n} answers cite a "
                   f"Walmart or Fed report, about {secs:.0f} seconds per case. The chart counts the {sum(scopes.values())} findings "
                   "by what their evidence is about. An earlier run on the 40 store-weeks of the ML model's v3.4 file gave 39 of "
                   "40 passing all checks (one quote not word for word) and 35 Strong / 5 Some. The other 107 v4 cases have not "
                   "been run yet.")
    depts = sum(x["case"]["flagged_departments"] for x in out.values())
    flow = [(f"{n}", "store-weeks", "flagged by the ML model (Top 20)", YEL),
            (f"{depts}", "departments", "flagged inside those store-weeks", CARD),
            (f"{sum(scopes.values())}", "findings", "written by the agent, 5\u20136 per answer", BLUE)]
    for i, (big, unit, small, fill) in enumerate(flow):
        x = 0.58 + i * 3.02
        dark = fill == BLUE
        shape(sl, x, 1.22, 2.8, 0.9, fill, adj=0.14)
        text(sl, x + 0.16, 1.26, 2.5, 0.45, [[(big + " ", {"size": 22, "bold": True}), (unit, {"size": 13, "bold": True})]],
             color="FFFFFF" if dark else TITLE)
        text(sl, x + 0.16, 1.74, 2.55, 0.32, small, size=9.5, color="FFFFFF" if dark else SUB)
        if i < 2:
            arrow(sl, x + 2.83, 1.56, 0.16, 0.2)
    label = {"store": "The store’s other departments", "report": "A Walmart or Fed report",
             "department": "Same department, other stores", "walmart": "Walmart overall", "region": "Same region",
             "outside": "Outside factors", "ml_note": "ML model note"}
    order = [k for k, _ in scopes.most_common()][::-1]
    panel(sl, 0.58, 2.25, 8.84, 2.23, f"WHAT THE {sum(scopes.values())} FINDINGS WERE BASED ON (one finding can cover several departments)")
    cd = CategoryChartData()
    cd.categories = [label[k] for k in order]
    cd.add_series("Findings", [scopes[k] for k in order])
    gf = sl.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.7), Inches(2.55), Inches(8.6), Inches(1.9), cd)
    ch = gf.chart
    style_chart(ch, size=10)
    ch.value_axis.visible = False
    ch.value_axis.has_major_gridlines = False
    pl = ch.plots[0]
    pl.gap_width = 45
    pl.has_data_labels = True
    pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    pl.data_labels.font.size = Pt(10)
    pl.data_labels.font.bold = True
    pl.data_labels.font.color.rgb = rgb(INK)
    pl.series[0].format.fill.solid()
    pl.series[0].format.fill.fore_color.rgb = rgb(BLUE)
    takeaway(sl, "Quality:", f"{passed} of {n} answers passed all 7 checks; evidence {ev['Strong']} Strong, {ev['Some']} Some; about {secs:.0f} s per case.")


# ------------------------------------------------------------------------------------------------ 8  T-3
def s8_tuning(prs):
    sl = new_slide(prs, "What We Fixed After the First Runs", "Tuning the agent: four problems we found and how we fixed them",
                   "JTA V T-3 (calibrate models and data). Role (Oct 31): the first version had its own status rule "
                   "('Action needed / Check before acting / No action needed', using our 10% / $2,000 / 70% thresholds) and "
                   "sometimes suggested the forecast might be off. After Santhosh's decision that the ML model defines the "
                   "exception, that rule was removed; the prompt now forbids saying the flag is wrong, that no action is "
                   "needed, or asking the ML model to review its forecast, and a code check enforces it. Facts (Oct 30): the "
                   "agent can only state numbers it is given. 4 of the 20 approved case questions needed numbers that were "
                   "missing (earlier-year dollar figures, e.g. Store 39 Stationery $21,905, and one-decimal rates, e.g. "
                   "81.8%); after adding them all 20 were available. Tested on the v3.4 cases; v4 files do not carry those two "
                   "fields, so on v4 the agent uses the five store comparisons instead. Checks (Oct 30): the quote check "
                   "failed sales facts quoted word for word, and the guardrail check failed hedged wording such as 'a possible "
                   "explanation rather than a confirmed one'; both fixed and re-scored on saved answers in code, no new LLM "
                   "calls. Runs: the LLM setup could fall back to another model; batch runs now pin Claude Haiku 5.5. Also: "
                   "the answer length limit was raised after some answers were cut off.")
    rows = [("1", "The agent sometimes questioned the ML flag", "Now it never does, and a check blocks it"),
            ("2", "Some numbers it needed were missing", "We added them to what it reads"),
            ("3", "Two checks rejected correct answers", "Fixed, so only real mistakes are caught"),
            ("4", "Runs could use different AI models", "Every run now uses the same model")]
    text(sl, 1.3, 1.2, 3.9, 0.3, "WHAT WAS WRONG", size=10, color=SUB, bold=True)
    text(sl, 5.95, 1.2, 3.4, 0.3, "WHAT WE DID", size=10, color=TITLE, bold=True)
    for i, (num, before, after) in enumerate(rows):
        y = 1.5 + i * 0.75
        d = sl.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.62), Inches(y + 0.08), Inches(0.46), Inches(0.46))
        d.fill.solid()
        d.fill.fore_color.rgb = rgb(BLUE)
        d.line.fill.background()
        t = text(sl, 0.62, y + 0.1, 0.46, 0.42, num, size=14, color="FFFFFF", bold=True, anchor=MSO_ANCHOR.MIDDLE)
        t.text_frame.paragraphs[0].alignment = 2
        shape(sl, 1.3, y, 4.2, 0.62, "F3F5F9", adj=0.18)
        text(sl, 1.45, y + 0.05, 3.95, 0.52, before, size=12, color=SUB, anchor=MSO_ANCHOR.MIDDLE)
        arrow(sl, 5.58, y + 0.22, 0.26, 0.2)
        shape(sl, 5.95, y, 3.47, 0.62, CARD, adj=0.18)
        text(sl, 6.1, y + 0.05, 3.25, 0.52, after, size=12, color=INK, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    takeaway(sl, "Result:", "the agent stays in its role, and its results are fair and repeatable.")


# ------------------------------------------------------------------------------------------------ 9  T-5
def s9_limits(prs):
    sl = new_slide(prs, "What the Agent Can and Cannot Tell You", "Assumptions and limitations, in plain terms",
                   "JTA V T-5 (document findings, assumptions, limitations, constraints). Assumptions: the ML flag, thresholds, "
                   "priority and status are correct as given; department names and store regions are publicly inferred (each "
                   "with a confidence level) and not validated with internal Walmart knowledge. Limits: Walmart and Fed reports "
                   "cover the company or a district, never one store; markdowns are recorded per store-week only; the 7 checks "
                   "test grounding, not correctness; graders are language models and the benchmark is small. Not done yet: "
                   "blind labels on 10 cases by two teammates (main evidence and its strength), and the other 107 v4 cases.")
    panel(sl, 0.58, 1.3, 4.34, 2.35, "IT CAN TELL YOU")
    text(sl, 0.78, 1.8, 3.95, 1.8, bullets(["Whether a drop is shared or only at this store",
                                              "What Walmart and the Fed said at the time",
                                              "Where the store should look first"], size=14, space=12), color=BODY)
    panel(sl, 5.08, 1.3, 4.34, 2.35, "IT CANNOT", fill=YEL, head_color=BROWN)
    text(sl, 5.28, 1.8, 3.95, 1.8, bullets(["Prove a cause: no store-level records",
                                              "Tie markdowns to a department",
                                              "Replace the analyst’s review"], size=14, space=12), color=INK)
    shape(sl, 0.58, 3.8, 8.84, 0.62, CARD, adj=0.2)
    text(sl, 0.78, 3.88, 8.5, 0.46, [[("Not done yet: ", {"bold": True, "color": INK}),
                                      ("blind labels on 10 cases by two teammates · the other 107 v4 cases", {})]],
         size=11, color=BODY, anchor=MSO_ANCHOR.MIDDLE)
    takeaway(sl, "Bottom line:", "decision support; every flagged week still needs an analyst. Next: the dashboard.")


# ------------------------------------------------------------------------------------------------ build
def main():
    out = json.load(open(APP / "data" / "agent_outputs_v3_v4.json"))
    case = out[CID]
    raw = json.load(open(APP / "data" / "cases_v4" / "rank_001_Store_27_2012-09-14.json"))
    v4 = dict(net=raw["sales_performance"]["net_modeled_gap"], flagged=raw["department_summary"]["flagged_departments"],
              depts=raw["department_summary"]["department_count"])
    ml = pd.read_csv(APP / "data" / "ml_v33_complete" / "per_store_mad_experiment" / "per_store_mad_department_flags.csv",
                     usecols=["Store", "Dept", "Date", "Actual", "Expected"])
    week = ml[ml.Date == "2012-09-14"].assign(Pct=lambda x: (x.Actual / x.Expected - 1) * 100)

    prs = Presentation(SRC)
    lst = prs.slides._sldIdLst
    for sid in list(lst):
        prs.part.drop_rel(sid.rId)
        lst.remove(sid)
    s1_receives(prs, v4)
    s2_steps(prs)
    s3_compare(prs, week)
    s4_search(prs, case)
    s5_answer(prs)
    s6_check(prs, case)
    s7_results(prs, out)
    s8_tuning(prs)
    s9_limits(prs)
    prs.save(OUT)
    print(f"{OUT.name}: {len(prs.slides)} slides")


if __name__ == "__main__":
    main()
