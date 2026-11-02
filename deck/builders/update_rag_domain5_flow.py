"""Domain 5 as one story that follows Store 27 through the agent (2026-11-02, Santhosh: 'the flow is breaking';
keep slides clean). Runs after update_rag_model_building.py.

Domain 5 becomes:
  1 From ML Flag to Agent Question         new (was 'Integration with the ML Model's v4 Output', V T-4)
  2 How the AI Agent Works                 kept, subtitle points to the steps that follow (V T-1)
  3 Step 2: Shared Drop or Store-Specific? kept, retitled (V T-1a)
  4 Step 4: What the Reports Say           new (V T-1a)
  5 Steps 5-6: The Answer and Its Checks   new (was 'Case Walkthrough: Store 27' + 'Reasoning, Guardrails and 7 Checks')
  6 Agent Results on the v4 Top 20         kept (V T-2)
  7 Assumptions and Limitations            kept, takeaway bridges to Domain 6 (V T-5)
Moved: 'Follow-Up Chat' -> Domain 6 after the dashboard. 'Calibrating the Agent and Its Graders' -> replaced by
'Checking the Graders' at the end of Domain 4 (its chart grades the A2/E/F setups); the agent-side calibration (one
model per run, facts 16 -> 20 of 20, check fixes) is in the notes of slide 5.

    python3 deck/builders/update_rag_domain5_flow.py
"""
import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_rag_methodology import (BODY, CARD, FILES, INK, SUB, TITLE, YEL, rgb, set_takeaway, set_text,  # noqa: E402
                                    shape, text, title_of)
from update_rag_model_building import APP, BLUE, LIGHT, new_slide, style_chart, takeaway  # noqa: E402

D4, D6 = "DOMAIN 4  •  METHODOLOGY", "DOMAIN 6  •  DEPLOYMENT"
GREEN = "2E8B57"


def set_tag(sl, tag):
    set_text([s for s in sl.shapes if s.name == "Domain tag"][0], tag)


# ------------------------------------------------------------------------------------------------ new slides
def flag_question(prs):
    sl = new_slide(prs, "From ML Flag to Agent Question", "The ML model’s v4 output: 127 eligible store-weeks, Top 20 reviewed first",
                   "AI agent, part 1 (JTA V T-4 integrate the models). The ML model's final v4 output (127 case files, Extra "
                   "Trees + Global MAD, Isolation Forest as a supporting signal) is read directly by a v4 loader "
                   "(agents/cases_v3.py, AGENT_CASE_SET=v4). Flags, priority and status are used as given. v4 has no "
                   "per-department history, peer rates or per-store thresholds, so the agent's comparisons come from the ML "
                   "team's forecast file, which matches v4 exactly on actual and expected sales. The example used through this "
                   "section is the ML model's rank-1 case, the same Store 27 shown on the Three Store-Week slide in the ML section. The agent's "
                   "question is not 'is this flag right' (the ML model decides that) but 'what evidence supports it, and what "
                   "should the store check'.")
    shape(sl, 0.58, 1.3, 4.0, 3.12, CARD, adj=0.06)
    text(sl, 0.8, 1.42, 3.6, 0.3, "THE ML FLAG · RANK 1 OF 127", size=10.5, color=TITLE, bold=True)
    text(sl, 0.8, 1.82, 3.6, 0.4, "Store 27 · Sep 14, 2012", size=15, color=INK, bold=True)
    text(sl, 0.8, 2.3, 3.6, 0.6, "$240,020", size=30, color=TITLE, bold=True)
    text(sl, 0.8, 2.92, 3.6, 0.3, "net modeled shortfall", size=10.5, color=SUB)
    text(sl, 0.8, 3.38, 3.6, 0.9, [("25 of 69 departments flagged", {"space": 4}),
                                   ("Status: Needs analyst review", {})], size=11.5, color=BODY)
    a = sl.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(4.72), Inches(2.7), Inches(0.36), Inches(0.32))
    a.fill.solid()
    a.fill.fore_color.rgb = rgb(TITLE)
    a.line.fill.background()
    shape(sl, 5.22, 1.3, 4.2, 3.12, BLUE, adj=0.06)
    text(sl, 5.45, 1.42, 3.8, 0.3, "THE AGENT’S QUESTION", size=10.5, color="FFFFFF", bold=True)
    text(sl, 5.45, 1.95, 3.75, 2.2, "What evidence supports this flag, and what should the store check?",
         size=20, color="FFFFFF", bold=True)
    takeaway(sl, "Next:", "how the agent answers it, following Store 27 step by step.")
    return sl


def reports_step(prs, case):
    f = case["rag"]["filter"]
    sl = new_slide(prs, "Step 4: What the Reports Say", "Store 27: only reports for that time and place are searched",
                   f"AI agent, part 4 (JTA V T-1a build and verify). Setup E from Domain 4. The search window is the case week "
                   f"and the 3 weeks before ({f['start']} to {f['end']}): a report is used if its period covers that window or "
                   f"it was published in it, so the Q3 FY2013 earnings release (published Nov 15, covering the quarter) counts. "
                   f"Beige Books are limited to national and the store's Fed district (New York). At least one Walmart passage "
                   f"and one local Beige Book passage are kept; 6 go to the reasoning step. Found for Store 27: Aug 29 and Oct "
                   f"10 national Beige Books, the Oct 10 New York section, the Q3 earnings release (2 passages) and the Q3 call. "
                   f"The agent used the New York quote and said it describes the district in Aug-Sep, not this week or store.")
    shape(sl, 0.58, 1.3, 4.0, 3.12, CARD, adj=0.06)
    text(sl, 0.8, 1.42, 3.6, 0.3, "6 PASSAGES FOUND", size=10.5, color=TITLE, bold=True)
    rows = [("Fed Beige Book, New York", "Oct 10, 2012"), ("Fed Beige Book, national", "Aug 29 + Oct 10"),
            ("Walmart Q3 earnings release", "2 passages"), ("Walmart Q3 earnings call", "1 passage")]
    for i, (a, b) in enumerate(rows):
        y = 1.85 + i * 0.6
        shape(sl, 0.8, y, 3.56, 0.48, "FFFFFF", adj=0.2)
        text(sl, 0.92, y + 0.04, 3.35, 0.42, [[(a, {"bold": True, "color": INK}), ("   " + b, {"size": 9.5, "color": SUB})]],
             size=10.5, anchor=MSO_ANCHOR.MIDDLE)
    shape(sl, 4.78, 1.3, 4.64, 3.12, YEL, adj=0.06)
    text(sl, 5.0, 1.42, 4.2, 0.3, "QUOTED IN THE ANSWER", size=10.5, color=TITLE, bold=True)
    text(sl, 5.0, 1.9, 4.25, 1.6, "“Some of the weakness is attributed to unseasonably mild weather, which dampened sales "
                                  "of seasonal merchandise.”", size=15, color=INK, bold=True)
    text(sl, 5.0, 3.55, 4.25, 0.7, [("Fed Beige Book, New York District, Oct 10, 2012", {"size": 10, "color": SUB, "space": 2}),
                                    ("Context for Lawn & Garden, not proof for this store", {"size": 10, "color": BODY})])
    takeaway(sl, "Filter:", f"reports for Aug 24 – Sep 14, 2012, Walmart plus national and New York Fed.")
    return sl


def answer_checks(prs, case):
    names = [k["name"] for k in case["evaluation"]["checks"]]
    passed = sum(k["passed"] for k in case["evaluation"]["checks"])
    sl = new_slide(prs, "Steps 5–6: The Answer and Its Checks", "What the store manager reads for Store 27, after code has checked it",
                   "AI agent, part 5 (JTA V T-1a build and verify, T-2 run). The language model writes the answer from the "
                   "evidence and passages only; it is the saved answer for Store 27 (agent_outputs_v3_v4.json), shortened. "
                   "Evidence found: Strong. Guardrails: no verified or confirmed cause, no 'lost sales', no markdown as a "
                   "cause, scores are not probabilities, never questions the ML flag. Then 7 code checks run; all 7 passed, so "
                   "the answer is shown; a failed check shows 'Answer needs a check' instead. The checks test grounding, not "
                   "whether the reason is right. Calibration (JTA V T-3): one model (Haiku 5.5) is pinned for each batch run "
                   "so runs compare; the facts given to the agent were extended so 20 of 20 golden case facts are available "
                   "(was 16); two false alarms in the checks were fixed and a guardrail was added so the agent never asks the "
                   "ML model to review its forecast. Check changes are re-scored on saved answers in code, without LLM calls.")
    cols = [("WHY IT HAPPENED", ["Stationery and Lawn & Garden fell at almost every store",
                                 "Walmart −5.3% that week; Store 27 −13.7%",
                                 "Electronics −28.4% only here"]),
            ("WHAT TO CHECK", ["Stock and deliveries: Stationery, Lawn & Garden",
                               "Electronics pricing, displays, stock",
                               "Staffing and local competitors"])]
    for i, (h, items) in enumerate(cols):
        x = 0.58 + i * 2.95
        shape(sl, x, 1.3, 2.8, 3.12, CARD, adj=0.06)
        text(sl, x + 0.18, 1.42, 2.5, 0.3, h, size=10.5, color=TITLE, bold=True)
        text(sl, x + 0.18, 1.85, 2.48, 2.5, [("•  " + t, {"space": 9}) for t in items], size=11.5, color=BODY)
    x = 6.48
    shape(sl, x, 1.3, 2.94, 3.12, CARD, adj=0.06)
    text(sl, x + 0.18, 1.42, 2.6, 0.3, f"{passed} OF {len(names)} CHECKS PASSED", size=10.5, color=TITLE, bold=True)
    short = {"Numbers match the evidence": "Numbers match", "Quotes are word for word": "Quotes word for word",
             "Every finding cites evidence": "Every finding cites", "Answer is complete": "Answer complete",
             "Guardrails respected": "Guardrails respected", "Every finding is tagged": "Every finding tagged",
             "Covers the largest flagged department": "Largest dept covered"}
    for i, n in enumerate(names):
        y = 1.85 + i * 0.36
        dot = sl.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + 0.2), Inches(y + 0.07), Inches(0.16), Inches(0.16))
        dot.fill.solid()
        dot.fill.fore_color.rgb = rgb(GREEN)
        dot.line.fill.background()
        text(sl, x + 0.45, y, 2.4, 0.3, short.get(n, n), size=10.5, color=BODY)
    takeaway(sl, "Evidence found: Strong.", "No cause is verified; the analyst decides.")
    return sl


def graders(prs):
    g = json.load(open(APP / "eval" / "results" / "grader_comparison.json"))
    sl = new_slide(prs, "Checking the Graders", "The same answers, graded by two different language models",
                   "RAG methodology, part 7 (JTA V T-3 calibrate, applied to the IV evaluation). Haiku wrote the answers and "
                   "also graded them, so Claude Sonnet 5.5 re-graded the answers of A2, E and F. On the weak setup A2, Haiku "
                   f"said {g['A2']['haiku_correct']}% correct and Sonnet {g['A2']['sonnet_correct']}% (they agreed on "
                   f"{g['A2']['graders_agree']} items). On E they agreed on {g['E']['graders_agree']} "
                   f"({g['E']['haiku_correct']}% vs {g['E']['sonnet_correct']}%). So both grades are reported, and the choice "
                   "of E holds under either grader.")
    set_tag(sl, D4)
    cd = CategoryChartData()
    cd.categories = ["A2 (first app)", "E (chosen)", "F (reranked)"]
    cd.add_series("Haiku", tuple(g[k]["haiku_correct"] for k in ("A2", "E", "F")))
    cd.add_series("Sonnet", tuple(g[k]["sonnet_correct"] for k in ("A2", "E", "F")))
    shape(sl, 0.58, 1.3, 8.84, 3.12, CARD, adj=0.05)
    text(sl, 0.8, 1.4, 6, 0.3, "Answers graded correct", size=11, color=TITLE, bold=True)
    gf = sl.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.75), Inches(1.7), Inches(8.5), Inches(2.65), cd)
    ch = gf.chart
    style_chart(ch, legend=True, size=10)
    ch.value_axis.maximum_scale = 100
    ch.value_axis.minimum_scale = 0
    ch.value_axis.tick_labels.number_format = '0"%"'
    ch.value_axis.tick_labels.number_format_is_linked = False
    pl = ch.plots[0]
    pl.gap_width = 90
    pl.has_data_labels = True
    pl.data_labels.number_format = '0"%"'
    pl.data_labels.number_format_is_linked = False
    pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    pl.data_labels.font.size = Pt(10)
    pl.data_labels.font.bold = True
    for s, c in zip(pl.series, (LIGHT, BLUE)):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = rgb(c)
    takeaway(sl, "Finding:", "Haiku was easier on the weak setup; on E both agree, so E holds either way.")
    return sl


# ------------------------------------------------------------------------------------------------ apply
def update(path):
    case = json.load(open(APP / "data" / "agent_outputs_v3_v4.json"))["Store_27_2012-09-14"]
    prs = Presentation(path)
    lst = prs.slides._sldIdLst
    sid = {title_of(s): i for s, i in zip(prs.slides, list(lst))}
    sl = {title_of(s): s for s in prs.slides}

    set_text([s for s in sl["How the AI Agent Works"].shapes if s.name == "Subtitle"][0],
             "Every flagged store-week goes through six steps; next we follow Store 27 through steps 2, 4 and 5–6")
    shared = sl["Shared Drop or Store-Specific?"]
    set_text([s for s in shared.shapes if s.name == "Title"][0], "Step 2: Shared Drop or Store-Specific?")
    set_takeaway(shared, "Also compared:", "Walmart overall, the region, the store’s other departments, outside factors.")
    set_takeaway(sl["Assumptions and Limitations"], "Bottom line:", "decision support; the analyst decides. Next: what the analyst sees.")
    set_tag(sl["Follow-Up Chat"], D6)

    s1, s4, s5, gr = flag_question(prs), reports_step(prs, case), answer_checks(prs, case), graders(prs)
    new = dict(zip(("q", "r", "a", "g"), list(lst)[-4:]))

    drop = ["Integration with the ML Model’s v4 Output", "Reasoning, Guardrails and 7 Checks",
            "Case Walkthrough: Store 27", "Calibrating the Agent and Its Graders"]
    d5 = [new["q"], sid["How the AI Agent Works"], sid["Shared Drop or Store-Specific?"], new["r"], new["a"],
          sid["Agent Results on the v4 Top 20"], sid["Assumptions and Limitations"]]
    anchor = list(lst).index(sid["How the AI Agent Works"])
    for t in drop:
        prs.part.drop_rel(sid[t].rId)
        lst.remove(sid[t])
    moving = d5 + [new["g"], sid["Follow-Up Chat"]]
    for x in moving:
        lst.remove(x)
    for k, x in enumerate(d5):
        lst.insert(anchor + k, x)
    ids = list(lst)
    lst.insert(ids.index(sid["Which Metrics Matter, and Why E"]) + 1, new["g"])
    ids = list(lst)
    lst.insert(ids.index(sid["Store Manager Dashboard"]) + 1, sid["Follow-Up Chat"])
    prs.save(path)
    print(f"{path.name}: {len(prs.slides)} slides")


if __name__ == "__main__":
    for f in FILES:
        update(f)
