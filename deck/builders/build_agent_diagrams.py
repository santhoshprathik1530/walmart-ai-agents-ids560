"""Five diagram-first slides: agent architecture, the RAG, Evidence and Reasoning agents, and how answers are checked.

Plain shapes, big labels, almost no sentences, in the look of the human-made slides at the start of the midterm deck
(cream background, black title, deck blue).

Usage:  python3 build_agent_diagrams.py "<source deck>.pptx" "<output>.pptx"
"""
import sys

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

FONT = "Arial"
BLUE, LIGHT, PALE = "1A36B4", "A4C2F4", "E3ECFB"
INK, GREY = "1D1D1D", "595959"
GREEN, RED, WHITE = "2E7D32", "C0392B", "FFFFFF"


def rgb(h):
    return RGBColor.from_string(h)


def new_slide(prs, title):
    layout = next(l for l in prs.slide_masters[0].slide_layouts if l.name == "TITLE_ONLY_1")
    s = prs.slides.add_slide(layout)
    for ph in list(s.placeholders):
        if ph.placeholder_format.type != 1:           # keep only the title
            ph._element.getparent().remove(ph._element)
    t = s.shapes.title
    t.left, t.top, t.width, t.height = Inches(0.34), Inches(0.32), Inches(9.32), Inches(0.63)
    t.text_frame.text = title
    for r in t.text_frame.paragraphs[0].runs:
        r.font.size = Pt(30)
    return s


def put(tf, text, size, color, bold, align="c", italic=False):
    tf.word_wrap = True
    for i, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
        r = p.add_run()
        r.text = line
        f = r.font
        f.name, f.size, f.bold, f.italic = FONT, Pt(size), bold, italic
        f.color.rgb = rgb(color)


def shape(s, kind, x, y, w, h, text="", fill=None, line=None, lw=1.5, color=INK, size=14, bold=False, dash=False, align="c"):
    shp = s.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill:
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(fill)
    else:
        shp.fill.background()
    if line:
        shp.line.color.rgb = rgb(line)
        shp.line.width = Pt(lw)
        if dash:
            shp.line.dash_style = MSO_LINE.DASH
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    tf = shp.text_frame
    tf.margin_left = tf.margin_right = Inches(0.06)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    if text:
        put(tf, text, size, color, bold, align)
    return shp


RECT, ROUND, OVAL, DIAMOND, CAN, CHEVRON = (MSO_SHAPE.RECTANGLE, MSO_SHAPE.ROUNDED_RECTANGLE, MSO_SHAPE.OVAL, MSO_SHAPE.DIAMOND,
                                           MSO_SHAPE.CAN, MSO_SHAPE.CHEVRON)


def label(s, x, y, w, h, text, size=12, color=INK, bold=False, align="c", italic=False, anchor="t"):
    box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE}[anchor]
    put(tf, text, size, color, bold, align, italic)
    return box


def arrow(s, x1, y1, x2, y2, color=INK, w=1.75, dash=False, head=True):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(w)
    if dash:
        c.line.dash_style = MSO_LINE.DASH
    if head:
        etree.SubElement(c.line._get_or_add_ln(), qn("a:tailEnd")).set("type", "triangle")
    return c


def notes(s, text):
    s.notes_slide.notes_text_frame.text = text


def agent(s, x, y, w, h, text, size=14):
    return shape(s, RECT, x, y, w, h, text, fill=BLUE, color=WHITE, size=size, bold=True)


def store(s, x, y, w, h, text, size=12):
    return shape(s, CAN, x, y, w, h, text, fill=LIGHT, line=None, color=INK, size=size)


# ------------------------------------------------------------------------------------------ 1. architecture
def architecture(prs):
    s = new_slide(prs, "AI Agent Architecture")
    shape(s, ROUND, 0.4, 2.2, 1.4, 0.9, "Anomaly\nflagged", fill=WHITE, line=INK, size=13)
    agent(s, 2.2, 2.05, 1.5, 1.2, "Orchestrator\n(LangGraph)", 13)
    agent(s, 4.3, 1.3, 1.9, 0.85, "Evidence\nAgent")
    store(s, 4.6, 2.35, 1.3, 0.75, "Sales\ndata")
    agent(s, 4.3, 3.35, 1.9, 0.85, "RAG\nAgent")
    store(s, 4.6, 4.35, 1.3, 0.75, "Reports\n(ChromaDB)", 11)
    agent(s, 6.8, 2.05, 1.5, 1.2, "Reasoning\nAgent")
    store(s, 6.85, 3.65, 1.4, 0.7, "LLM")
    shape(s, OVAL, 8.65, 2.2, 0.95, 0.95, "Analyst", fill=WHITE, line=INK, size=12)
    arrow(s, 1.8, 2.65, 2.2, 2.65)
    arrow(s, 3.7, 2.4, 4.3, 1.75)
    arrow(s, 3.7, 2.9, 4.3, 3.75)
    arrow(s, 6.2, 1.75, 6.8, 2.4)
    arrow(s, 6.2, 3.75, 6.8, 2.9)
    arrow(s, 8.3, 2.65, 8.65, 2.65)
    arrow(s, 5.25, 2.34, 5.25, 2.17, color=GREY)
    arrow(s, 5.25, 4.34, 5.25, 4.22, color=GREY)
    arrow(s, 7.55, 3.64, 7.55, 3.27, color=GREY)
    # follow-up loop
    arrow(s, 9.12, 3.17, 9.12, 5.2, color=GREY, dash=True, head=False)
    arrow(s, 9.12, 5.2, 2.95, 5.2, color=GREY, dash=True, head=False)
    arrow(s, 2.95, 5.2, 2.95, 3.27, color=GREY, dash=True)
    label(s, 5.2, 5.25, 2.6, 0.25, "follow-up questions", 12, GREY, italic=True)
    label(s, 3.0, 3.38, 1.25, 0.4, "at the\nsame time", 11, GREY, italic=True)
    notes(s, "This is the whole system on one page. A flagged anomaly goes to the orchestrator. It sends the work to two agents at the same time: "
             "the Evidence Agent looks at our sales data, and the RAG Agent looks through the Walmart and Fed reports. "
             "The Reasoning Agent takes both results, makes the call, and uses an LLM only to write it up. The analyst reads it, and if they ask a follow-up it goes back to the orchestrator.")
    return s


# ------------------------------------------------------------------------------------------ 2. RAG
def rag(prs):
    s = new_slide(prs, "RAG Agent: Finding the Evidence")
    steps = [("Question", "Store 7, Electronics,\nAug 24, 2012"), ("Filter", "right time,\nright region"), ("Search", "closest in\nmeaning"),
             ("Pick best", "best sentence\nfrom each"), ("Quotes", "with source\nand date")]
    for i, (t, c) in enumerate(steps):
        x = 0.4 + i * 1.84
        shape(s, CHEVRON, x, 1.2, 1.95, 0.85, t, fill=BLUE if i != 4 else GREEN, color=WHITE, size=14, bold=True)
        label(s, x + 0.25, 2.12, 1.55, 0.5, c, 11, INK)
    label(s, 0.5, 2.95, 4.2, 0.3, "What the filters do", 13, BLUE, True, "l")
    for i, (t, w, f, c) in enumerate([("All reports  (6,560 chunks)", 4.2, PALE, INK), ("Right time + region", 3.3, "C5D8F8", INK),
                                       ("Closest in meaning", 2.4, "8FB0EE", INK), ("6 quotes", 1.5, BLUE, WHITE)]):
        shape(s, RECT, 0.5 + (4.2 - w) / 2, 3.3 + i * 0.42, w, 0.36, t, fill=f, color=c, size=12, bold=(i == 3))
    label(s, 5.3, 2.95, 4.2, 0.3, "Built once, before any question", 13, BLUE, True, "l")
    for i, t in enumerate(["Reports", "Chunks", "Vectors"]):
        x = 5.3 + i * 1.45
        shape(s, RECT, x, 3.4, 1.1, 0.6, t, fill=WHITE, line=INK, size=13)
        if i < 2:
            arrow(s, x + 1.1, 3.7, x + 1.45, 3.7)
    arrow(s, 8.0, 4.02, 7.4, 4.35)
    store(s, 6.5, 4.35, 1.8, 0.8, "ChromaDB", 13)
    label(s, 8.4, 4.55, 1.2, 0.4, "this is what\ngets searched", 10, GREY, italic=True)
    notes(s, "Left to right is what happens when the question comes in. The filter runs first, so we only look at reports from the right time and the right Fed region. "
             "Then we search those by meaning, pick the best sentence from each, and send back a few quotes with their source and date. "
             "The funnel shows how it narrows down. At the bottom right is how the reports get ready once, before anyone asks: cut into chunks, turned into vectors, and stored in ChromaDB.")
    return s


# ------------------------------------------------------------------------------------------ 3. Evidence
def evidence(prs):
    s = new_slide(prs, "Evidence Agent: What Happened")
    shape(s, OVAL, 0.4, 2.05, 1.9, 1.3, "Store 7\nElectronics\n−24.6%", fill=BLUE, color=WHITE, size=13, bold=True)
    store(s, 0.65, 3.85, 1.4, 0.8, "Sales\ndata")
    arrow(s, 1.35, 3.84, 1.35, 3.37, color=GREY)
    rows = [("Whole store down?", "No, the rest is only −3.3%"), ("One-off week?", "No, −12.7% this quarter"),
            ("Nearby stores?", "They held up better"), ("Whole chain?", "Only −0.5%"),
            ("Promos, fuel, weather?", "Fewer promos, rest normal"), ("A holiday?", "No holiday that week")]
    for i, (q, a) in enumerate(rows):
        y = 1.15 + i * 0.57
        shape(s, ROUND, 3.0, y, 2.55, 0.45, q, fill=WHITE, line=BLUE, size=13)
        arrow(s, 2.3, 2.7, 3.0, y + 0.22, color=GREY, w=1.25, head=False)
        arrow(s, 5.55, y + 0.22, 6.0, y + 0.22, color=BLUE)
        label(s, 6.1, y, 3.5, 0.45, a, 13, INK, anchor="m", align="l")
    shape(s, ROUND, 3.0, 4.65, 6.5, 0.5, "So: the drop is mostly local to Store 7", fill=BLUE, color=WHITE, size=15, bold=True)
    notes(s, "The Evidence Agent just asks the sales data six simple questions about the flagged week. Is the whole store down, or only this department? One bad week or a trend? "
             "How did nearby stores do, and the whole chain? Did promotions, fuel or weather change? Was there a holiday? For Store 7 Electronics the answers all point the same way: "
             "the department is down 12.7 percent this quarter while the chain is flat, so the problem looks local to the store.")
    return s


# ------------------------------------------------------------------------------------------ 4. Reasoning
def reasoning(prs):
    s = new_slide(prs, "Reasoning Agent: Making the Call")
    shape(s, ROUND, 0.4, 1.5, 1.6, 0.75, "Evidence", fill=WHITE, line=INK, size=14)
    shape(s, ROUND, 0.4, 2.55, 1.6, 0.75, "Report\nquotes", fill=WHITE, line=INK, size=14)
    shape(s, DIAMOND, 2.45, 1.55, 2.2, 1.8, "Just\ntiming?", fill=WHITE, line=BLUE, lw=2, size=15, bold=True)
    arrow(s, 2.0, 1.88, 2.7, 2.2)
    arrow(s, 2.0, 2.92, 2.7, 2.7)
    shape(s, ROUND, 5.0, 1.2, 1.7, 0.7, "Likely\nexplained", fill=GREEN, color=WHITE, size=14, bold=True)
    shape(s, ROUND, 5.0, 3.0, 1.7, 0.7, "Needs\nreview", fill=RED, color=WHITE, size=14, bold=True)
    arrow(s, 4.4, 2.0, 5.0, 1.6, color=GREEN)
    label(s, 4.45, 1.45, 0.5, 0.25, "yes", 12, GREEN, True)
    arrow(s, 4.4, 2.9, 5.0, 3.3, color=RED)
    label(s, 4.5, 3.15, 0.5, 0.25, "no", 12, RED, True)
    # how sure
    shape(s, ROUND, 7.1, 1.95, 2.4, 1.1, "", fill=WHITE, line=INK)
    label(s, 7.1, 2.0, 2.4, 0.3, "How sure?", 13, INK, True)
    for i, (t_, f) in enumerate([("High", GREEN), ("Med", "E0A800"), ("Low", RED)]):
        shape(s, OVAL, 7.2 + i * 0.77, 2.38, 0.66, 0.6, t_, fill=f, color=WHITE, size=9, bold=True)
    arrow(s, 6.7, 1.55, 7.35, 1.95, color=GREEN)
    arrow(s, 6.7, 3.35, 7.35, 3.05, color=RED)
    shape(s, ROUND, 7.1, 3.5, 2.4, 0.75, "Write it up\n(LLM)", fill=BLUE, color=WHITE, size=14, bold=True)
    arrow(s, 8.3, 3.06, 8.3, 3.5)
    label(s, 7.1, 4.3, 2.4, 0.4, "guard: numbers, quotes, wording\nmust match, or rules write it", 10, GREY, italic=True)
    shape(s, OVAL, 7.7, 4.85, 1.2, 0.6, "Analyst", fill=WHITE, line=INK, size=13)
    arrow(s, 8.3, 4.72, 8.3, 4.85)
    notes(s, "Evidence and report quotes come in. The first question is simple: is this just timing, like a holiday or a baseline that includes Christmas? If yes, we say likely explained. "
             "If not, we look at the other factors and say needs review. Then the agent says how sure it is, high, medium or low. Finally an LLM writes it up in plain words, "
             "but a guard checks its numbers, quotes and wording against the evidence first, and if something doesn't match the text is thrown out and the rules write it. After that the whole answer is verified once more before the analyst sees it, which is the next slide.")
    return s


# ------------------------------------------------------------------------------------------ 5. evaluation
def evaluation(prs):
    s = new_slide(prs, "Is the Answer Right? How We Check")
    label(s, 0.4, 1.05, 6.0, 0.3, "Every answer, automatically, before the analyst sees it", 13, BLUE, True, "l")
    y, h = 1.55, 0.95
    shape(s, ROUND, 0.4, y, 1.3, h, "Rules draft\nthe answer", fill=WHITE, line=INK, size=12)
    shape(s, ROUND, 1.95, y, 1.3, h, "LLM writes\nthe words", fill=WHITE, line=INK, size=12)
    shape(s, DIAMOND, 3.5, y - 0.1, 1.3, h + 0.2, "Guard\nOK?", fill=WHITE, line=BLUE, lw=2, size=12, bold=True)
    shape(s, ROUND, 5.15, y, 1.4, h, "Verify the\nwhole answer", fill=BLUE, color=WHITE, size=12, bold=True)
    shape(s, DIAMOND, 6.8, y - 0.1, 1.25, h + 0.2, "Pass?", fill=WHITE, line=BLUE, lw=2, size=12, bold=True)
    shape(s, ROUND, 8.3, y, 1.3, h, "Final answer\n+ badges", fill=GREEN, color=WHITE, size=12, bold=True)
    mid = y + h / 2
    for x1, x2 in [(1.7, 1.95), (3.25, 3.5), (4.8, 5.15), (6.55, 6.8), (8.05, 8.3)]:
        arrow(s, x1, mid, x2, mid)
    label(s, 4.83, mid - 0.3, 0.32, 0.25, "yes", 10, GREEN, True)
    label(s, 8.04, mid - 0.3, 0.26, 0.25, "yes", 10, GREEN, True)
    # guard "no": rules write the words, then continue
    arrow(s, 4.15, y + h + 0.1, 4.15, 3.0, color=RED)
    label(s, 4.2, 2.65, 0.4, 0.25, "no", 11, RED, True)
    shape(s, ROUND, 3.35, 3.0, 1.6, 0.55, "Rules write\nthe words", fill=WHITE, line=RED, size=11)
    arrow(s, 4.95, 3.27, 5.85, 3.27, color=RED, head=False)
    arrow(s, 5.85, 3.27, 5.85, y + h, color=RED)
    # verify "no": lower confidence and warn
    arrow(s, 7.42, y + h + 0.1, 7.42, 3.0, color=RED)
    label(s, 7.47, 2.65, 0.4, 0.25, "no", 11, RED, True)
    shape(s, ROUND, 6.55, 3.0, 1.75, 0.55, "Confidence lowered\n+ warning", fill=WHITE, line=RED, size=11)
    arrow(s, 8.3, 3.27, 8.95, 3.27, color=RED, head=False)
    arrow(s, 8.95, 3.27, 8.95, y + h, color=RED)
    label(s, 1.95, 2.55, 1.9, 0.5, "numbers, quotes and\nwording match the facts", 10, GREY, italic=True)
    label(s, 0.4, 2.55, 1.5, 0.5, "rules decide\nverdict + confidence", 10, GREY, italic=True)
    label(s, 5.0, 3.62, 4.6, 0.5, "numbers recomputed from raw files, quotes found in the original reports, sources from the right time and region", 10, GREY, italic=True, align="l")
    # people
    shape(s, RECT, 0.4, 4.12, 9.2, 0.02, "", fill=GREY)
    label(s, 0.4, 4.2, 9.0, 0.3, "Is it right overall? People check a sample", 13, BLUE, True, "l")
    boxes = [("10 flagged\nweeks", 0.4, 1.3), ("2 teammates label\nverdict + main factor", 2.0, 2.2), ("Agent vs. people", 4.5, 1.7)]
    for text, x, w in boxes:
        shape(s, ROUND, x, 4.62, w, 0.62, text, fill=WHITE, line=INK, size=11)
    arrow(s, 1.7, 4.93, 2.0, 4.93)
    arrow(s, 4.2, 4.93, 4.5, 4.93)
    for i, text in enumerate(["verdict matches?", "main factor matches?", "High right more often than Medium?"]):
        arrow(s, 6.2, 4.93, 6.5, 4.5 + i * 0.32 + 0.12, w=1.25, head=False)
        label(s, 6.55, 4.5 + i * 0.32, 3.0, 0.28, text, 12, INK, anchor="m", align="l")
    notes(s, "People get confused about the order, so here it is. First the rules draft the answer: the verdict, the confidence and the factors. Then the LLM writes it up in plain words. "
             "Right after that is a guard: the numbers, quotes and wording in the LLM's text must match the facts, otherwise the text is thrown away and the rules write the words. "
             "Before the analyst sees anything, the whole answer is verified once more: we recompute the key numbers from the raw sales files, look every quote up in the original reports, and check the sources are from the right time and region. "
             "If a check fails, the confidence is lowered and a warning is shown. Otherwise the answer goes out with its check badges. "
             "Those checks catch wrong numbers and made-up quotes. They cannot tell us if the verdict is actually right. For that, two teammates will label ten flagged weeks on their own, and we compare: does the verdict match, does the main factor match, and is High confidence right more often than Medium.")
    return s


def main(src, dst):
    prs = Presentation(src)
    n_old = len(prs.slides)
    for fn in (architecture, rag, evidence, reasoning, evaluation):
        fn(prs)
    lst = prs.slides._sldIdLst
    for el in list(lst)[:n_old]:
        prs.part.drop_rel(el.get(qn("r:id")))
        lst.remove(el)
    prs.save(dst)
    print("saved", dst, "slides:", len(prs.slides))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
