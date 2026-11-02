"""Rework the Domain 4 RAG methodology slides in both decks (2026-11-02, Santhosh's request):
  - 'RAG Methodologies Compared': six blocks -> one table of the 7 setups
  - 'Ground-Truth Benchmark Design': rewritten to say why the benchmark exists and how it scores a setup
  - 'Retrieval Results Across Seven Setups' (chart) -> 'Evaluation Metrics for Each Setup' (table)
  - 'RAGAS: Answer and Context Quality' (chart): removed, its key number is a column in the metrics table
  - 'Why Setup E Is Recommended' -> 'Which Metrics Matter, and Why E'
Numbers come from app/eval/results/rag_metrics_table.csv. Slides are found by title and edited in place; the frame,
title, subtitle, domain tag and takeaway bar are kept so the style matches the rest of the deck.

    python3 deck/builders/update_rag_methodology.py
"""
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

DECK = Path(__file__).resolve().parent.parent
FILES = [DECK / "AI Agents and RAG - Final Presentation Slides.pptx", DECK / "Final Presentation (ML + AI Agents and RAG).pptx"]
FONT = "Inter"
TITLE, SUB, CARD, INK, BODY, YEL, BROWN = "1F3EAC", "4E6180", "EBF2FC", "1F3162", "34466B", "FFF2BF", "855521"
KEEP = {"Background", "Frame", "Title", "Subtitle", "Domain tag", "Takeaway bar", "Takeaway"}
X3, W3 = [0.58, 3.60, 6.62], 2.82


def rgb(h):
    return RGBColor.from_string(h)


def set_text(shape, text):
    runs = [r for p in shape.text_frame.paragraphs for r in p.runs]
    runs[0].text = text
    for r in runs[1:]:
        r.text = ""


def set_takeaway(sl, label, msg):
    runs = [r for p in [s for s in sl.shapes if s.name == "Takeaway"][0].text_frame.paragraphs for r in p.runs]
    runs[0].text, runs[1].text = label + " ", msg


def clear(sl):
    for s in list(sl.shapes):
        if s.name not in KEEP:
            s._element.getparent().remove(s._element)


def retitle(sl, title, subtitle, notes):
    named = {s.name: s for s in sl.shapes}
    set_text(named["Title"], title)
    set_text(named["Subtitle"], subtitle)
    sl.notes_slide.notes_text_frame.text = notes


def shape(sl, x, y, w, h, fill, adj=0.09):
    s = sl.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    s.line.fill.background()
    s.adjustments[0] = adj
    return s


def text(sl, x, y, w, h, paras, size=11, color=BODY, bold=False, anchor=None):
    tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.03)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    if anchor:
        tf.vertical_anchor = anchor
    for i, p in enumerate(paras if isinstance(paras, list) else [paras]):
        opts = {}
        if isinstance(p, tuple):
            p, opts = p
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.space_after = Pt(opts.get("space", 3))
        for rt, ro in (p if isinstance(p, list) else [(p, {})]):
            r = para.add_run()
            r.text = rt
            r.font.name = FONT
            r.font.size = Pt(ro.get("size", opts.get("size", size)))
            r.font.bold = ro.get("bold", opts.get("bold", bold))
            r.font.color.rgb = rgb(ro.get("color", opts.get("color", color)))
    return tb


def card(sl, x, y, w, h, num, head, body):
    shape(sl, x, y, w, h, CARD)
    text(sl, x + 0.16, y + 0.12, w - 0.32, 0.34, [[(num + "  ", {"size": 14}), (head, {})]], size=12, color=TITLE, bold=True)
    text(sl, x + 0.16, y + 0.52, w - 0.32, h - 0.6, body)


def borders(cell, color="C9D4E8"):
    tcPr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        for old in tcPr.findall(qn(tag)):
            tcPr.remove(old)
        ln = etree.SubElement(tcPr, qn(tag), w="6350")
        fill = etree.SubElement(ln, qn("a:solidFill"))
        etree.SubElement(fill, qn("a:srgbClr"), val=color)
    # the line elements must come before the cell fill
    for f in tcPr.findall(qn("a:solidFill")):
        tcPr.remove(f)
        tcPr.append(f)


def table(sl, x, y, widths, row_h, rows, highlight=None, size=10, left=(0,)):
    gf = sl.shapes.add_table(len(rows), len(widths), Inches(x), Inches(y), Inches(sum(widths)), Inches(row_h * len(rows)))
    tbl = gf.table
    tp = tbl._tbl.tblPr
    for flag in ("firstRow", "bandRow"):
        tp.set(flag, "0")
    for j, w in enumerate(widths):
        tbl.columns[j].width = Inches(w)
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(row_h)
        head = i == 0
        fill = TITLE if head else YEL if row[0] == highlight else ("FFFFFF" if i % 2 else CARD)
        for j, val in enumerate(row):
            c = tbl.cell(i, j)
            c.fill.solid()
            c.fill.fore_color.rgb = rgb(fill)
            c.margin_left = c.margin_right = Inches(0.06)
            c.margin_top = c.margin_bottom = Inches(0.02)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            borders(c)
            p = c.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j in left else PP_ALIGN.CENTER
            r = p.add_run()
            r.text = val
            r.font.name = FONT
            r.font.size = Pt(size - 0.5 if head else size)
            r.font.bold = head or j == 0
            r.font.color.rgb = rgb("FFFFFF" if head else INK if j == 0 else BODY)
    return gf


# ------------------------------------------------------------------------------------------------ the five slides
def methods(sl):
    clear(sl)
    retitle(sl, "RAG Methodologies Compared", "Seven setups; each one changes one thing from the one before",
            "RAG methodology, part 1 (JTA IV T-1 available approaches). Read the table top to bottom: A is the starting "
            "point (fixed ~900-character chunks with 150 overlap, vector search). A2 adds a filter on report date and Fed "
            "district; it is the setup our first app used. B swaps vector search for keyword search (BM25). C combines "
            "both searches with reciprocal rank fusion. D keeps hybrid search but cuts reports by section (~800 "
            "characters) and adds a header line with source, date and Fed district to every chunk. E adds the date and "
            "district filter to D. F adds a cross-encoder that re-orders the top 30 results. All setups use the same 68 "
            "reports and the same embedding model (all-MiniLM-L6-v2).")
    rows = [["Setup", "Chunks", "Search", "Date + district filter", "Reranker", "What changes"],
            ["A", "Fixed, ~900 characters", "Vector", "–", "–", "Starting point"],
            ["A2", "Fixed, ~900 characters", "Vector", "Yes", "–", "A + filter (our first app)"],
            ["B", "Fixed, ~900 characters", "Keyword (BM25)", "–", "–", "Keyword instead of vector"],
            ["C", "Fixed, ~900 characters", "Hybrid (vector + BM25)", "–", "–", "Both searches combined"],
            ["D", "By section, ~800 + header", "Hybrid", "–", "–", "Chunks follow report sections"],
            ["E", "By section, ~800 + header", "Hybrid", "Yes", "–", "D + filter (chosen)"],
            ["F", "By section, ~800 + header", "Hybrid", "Yes", "Cross-encoder", "E + reranker"]]
    table(sl, 0.58, 1.25, [0.7, 2.0, 1.8, 1.2, 1.1, 2.04], 0.39, rows, highlight="E", size=10.5, left=(0, 1, 2, 5))
    set_takeaway(sl, "Question:", "which combination puts the right report sentence in the top five?")


def benchmark(sl):
    clear(sl)
    retitle(sl, "Ground-Truth Benchmark: How Each Setup Is Scored",
            "To compare setups fairly we need questions whose answer and source sentence are known in advance",
            "RAG methodology, part 4 (JTA IV T-3 evaluate approaches). Why this slide: every number on the next slide "
            "comes from this benchmark. Without questions whose right answer and right source sentence are known, we "
            "could not say that one setup finds better evidence than another. We wrote 34 questions answered by the "
            "reports and 3 that the reports cannot answer (a good setup should say it does not know). For each "
            "question we stored the answer and the exact sentence from the report, checked word for word in the source. "
            "All 37 were reviewed and approved. Every setup then gets the same 37 questions. Separately, 20 case-fact "
            "questions check the agent's numbers, and 20 judgment items (10 cases, main evidence and strength) wait for "
            "blind labels from two teammates; those belong to the agent evaluation in Domain 5, not the RAG comparison.")
    card(sl, X3[0], 1.25, W3, 1.85, "01", "WRITE QUESTIONS",
         [("34 questions answered by our reports, plus 3 with no answer in them to test refusal.", {"size": 11})])
    card(sl, X3[1], 1.25, W3, 1.85, "02", "RECORD THE TRUTH",
         [("For each: the right answer and the exact report sentence it comes from. All approved.", {"size": 11})])
    card(sl, X3[2], 1.25, W3, 1.85, "03", "SCORE EVERY SETUP",
         [("Same questions for all 7: was that sentence in the top 5? Was the answer right?", {"size": 11})])
    shape(sl, 0.58, 3.27, 8.84, 1.18, YEL, adj=0.12)
    text(sl, 0.78, 3.35, 8.45, 1.05, [
        ("EXAMPLE · QUESTION R03", {"bold": True, "color": TITLE, "size": 10.5, "space": 4}),
        ([("Question: ", {"bold": True, "color": INK}), ("In Q3 FY2013, was Walmart U.S. comp growth driven by traffic or ticket?", {})], {"space": 2}),
        ([("Truth: ", {"bold": True, "color": INK}), ("ticket +1.4%, traffic +0.1%.   ", {}),
          ("Source: ", {"bold": True, "color": INK}), ("Walmart Q3 FY2013 earnings release.", {})], {"space": 0})],
         size=11, anchor=MSO_ANCHOR.MIDDLE)
    set_takeaway(sl, "Why it matters:", "without known answers there is no fair way to say one setup is better.")


def metrics(sl):
    clear(sl)
    retitle(sl, "Evaluation Metrics for Each Setup", "Same 34 questions for every setup; higher is better, except search time",
            "RAG methodology, part 5 (JTA IV T-3 evaluate approaches). Hit@1 / Hit@5: share of the 34 questions where the "
            "right sentence is ranked first / in the top 5. MRR@10: average of 1 / rank of the first right passage. "
            "nDCG@10: ranking quality of the top 10. Search: milliseconds per search. Correct (Haiku, Sonnet): share of "
            "answers graded correct against the reference; Sonnet re-graded A2, E and F only, to check Haiku was not "
            "easy on its own answers. RAGAS answer correctness: the standard RAGAS library score (0-1, judge Haiku). "
            "Every setup was 97-100% faithful and refused all 3 unanswerable questions, so those do not separate the "
            "setups. Small benchmark: differences under about 15 points are not reliable.")
    rows = [["Setup", "Hit@1", "Hit@5", "MRR@10", "nDCG@10", "Search (ms)", "Correct (Haiku)", "Correct (Sonnet)", "RAGAS score"],
            ["A", "9%", "21%", "0.16", "0.20", "148", "53%", "–", "0.24"],
            ["A2", "18%", "35%", "0.26", "0.30", "119", "64%", "44%", "0.34"],
            ["B", "12%", "21%", "0.18", "0.23", "5", "33%", "–", "0.23"],
            ["C", "15%", "35%", "0.22", "0.26", "130", "44%", "–", "0.31"],
            ["D", "29%", "68%", "0.45", "0.55", "146", "74%", "–", "0.53"],
            ["E", "44%", "88%", "0.60", "0.68", "128", "88%", "87%", "0.68"],
            ["F", "65%", "88%", "0.76", "0.80", "819", "84%", "88%", "0.67"]]
    table(sl, 0.58, 1.22, [0.72, 0.9, 0.9, 0.95, 0.95, 1.05, 1.12, 1.15, 1.1], 0.37, rows, highlight="E", size=10.5)
    text(sl, 0.58, 4.24, 8.84, 0.3, "All setups: 97–100% faithful and 3 of 3 unanswerable questions refused. Sonnet re-graded A2, E and F only.",
         size=9, color=SUB)
    set_takeaway(sl, "Result:", "E finds the evidence for 30 of 34 questions; our first app (A2) found 12.")


def why_e(sl):
    clear(sl)
    retitle(sl, "Which Metrics Matter, and Why E", "The metrics that decide whether the agent gets the right evidence, fast",
            "RAG methodology, part 6 (JTA IV T-4 select the approach). Hit@5 matters most: the agent passes the top "
            "passages to the reasoning step, so if the right sentence is not near the top the answer cannot use it. "
            "Answer correctness is the end result, graded by two different models. Speed matters because every case "
            "runs 2-4 searches, and the dashboard can run a case live. Hit@1 and MRR matter less here because the agent "
            "reads 6 passages, not only the first. Faithfulness is 97-100% for every setup, so it does not help choose. "
            "E and F tie on Hit@5 (88%) and are close on correctness (Haiku 88% vs 84%, Sonnet 87% vs 88%), but F is "
            "6.4 times slower (819 vs 128 ms). So E.")
    for i, (num, head, desc, stat) in enumerate([
            ("01", "HIT@5", "Most important. The agent reads the top passages. If the right sentence is not there, the answer cannot use it.", "E 88% vs first app 35%"),
            ("02", "ANSWER CORRECT", "The end result, checked by two different graders so no model only grades itself.", "E 88% (Haiku) · 87% (Sonnet)"),
            ("03", "SPEED", "Each case runs 2–4 searches, and the dashboard can run a case live.", "E 128 ms vs F 819 ms")]):
        card(sl, X3[i], 1.25, W3, 2.2, num, head,
             [(desc, {"size": 11, "space": 8}), (stat, {"size": 12, "bold": True, "color": TITLE})])
    shape(sl, 0.58, 3.6, 8.84, 0.85, CARD, adj=0.15)
    text(sl, 0.78, 3.66, 8.45, 0.75, [[("Less decisive here: ", {"bold": True, "color": INK}),
                                       ("Hit@1 and MRR (the agent reads 6 passages, so being first matters less) and "
                                        "faithfulness (97–100% for every setup).", {})]], size=11, anchor=MSO_ANCHOR.MIDDLE)
    set_takeaway(sl, "Choice: E", "— same Hit@5 as F, as accurate, and 6.4x faster.")


def title_of(sl):
    return next((s.text_frame.text for s in sl.shapes if s.name == "Title"), "")


def update(path: Path):
    prs = Presentation(path)
    lst = prs.slides._sldIdLst
    by_title = {title_of(s): (s, sid) for s, sid in zip(prs.slides, list(lst))}
    methods(by_title["RAG Methodologies Compared"][0])
    benchmark(by_title["Ground-Truth Benchmark Design"][0])
    metrics(by_title["Retrieval Results Across Seven Setups"][0])
    why_e(by_title["Why Setup E Is Recommended"][0])
    _, ragas = by_title["RAGAS: Answer and Context Quality"]
    prs.part.drop_rel(ragas.rId)
    lst.remove(ragas)
    # order in Domain 4: methods, tools, benchmark, metrics, why E
    ids = list(lst)
    tools = by_title["AI and RAG Technology Stack"][1]
    bench = by_title["Ground-Truth Benchmark Design"][1]
    if ids.index(bench) < ids.index(tools):
        lst.remove(bench)
        lst.insert(list(lst).index(tools) + 1, bench)
    prs.save(path)
    print(f"{path.name}: {len(prs.slides)} slides")


if __name__ == "__main__":
    for f in FILES:
        update(f)
