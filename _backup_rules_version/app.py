"""Sales Exception Assistant: Streamlit app with live AI agents (IDS 560, Team 2).

Click "Ask agent" on an exception and the agents run for real: an orchestrator (LangGraph) sends one task to the Evidence Agent
(pandas over the Kaggle sales data) and one to the RAG Agent (ChromaDB over Walmart / Federal Reserve / NRF reports) in parallel,
then the Reasoning Agent writes the possible factors. Progress streams live; the result ends with a box for follow-up questions.

Run:  pip install -r requirements.txt && python3 -m agents.ingest && streamlit run app.py
"""
import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from agents import engine as E, graph as G, llm, rag

APP = Path(__file__).parent
st.set_page_config(page_title="Sales Exception Assistant", page_icon="🔎", layout="wide", initial_sidebar_state="collapsed")

BLUE, NAVY, GREY, RED, GREEN, LINE = "#0071CE", "#0B2D5B", "#5A6B80", "#C0392B", "#2E7D32", "#E3E8EF"
STATUS_COLOR = {"Needs review": RED, "Likely explained": GREEN}

st.markdown(f"""
<style>
  .block-container {{padding-top: 2rem; max-width: 1250px;}}
  [data-testid="stSidebarCollapsedControl"] {{display: none;}}
  .brand {{color:{BLUE}; font-weight:700; letter-spacing:.08em; font-size:.8rem; text-transform:uppercase;}}
  .title {{color:{NAVY}; font-size:2.3rem; font-weight:800; margin:0;}}
  .sub {{color:{GREY}; margin:2px 0 18px 0;}}
  .kpi-v {{font-size:2rem; font-weight:800; color:{NAVY}; line-height:1.1;}}
  .kpi-l {{color:{GREY}; font-size:.85rem;}}
  .hdr {{color:{GREY}; font-size:.78rem; font-weight:700; text-transform:uppercase; letter-spacing:.04em;}}
  .cell {{padding-top:6px; font-size:.95rem;}}
  .pill {{display:inline-block; padding:2px 10px; border-radius:999px; border:1.5px solid; font-size:.78rem; font-weight:700;}}
  .gap {{color:{RED}; font-weight:800;}}
  .ft {{width:100%; border-collapse:collapse; font-size:.93rem;}}
  .ft th {{background:{NAVY}; color:white; text-align:left; padding:8px 10px;}}
  .ft td {{border:1px solid {LINE}; padding:9px 10px; vertical-align:top;}}
  .ft td.f {{font-weight:700; color:{NAVY};}}
  .ft td.ro {{color:{GREY};}}
  .bl {{border:1.5px solid; border-radius:8px; padding:10px 14px; margin-top:12px;}}
  .q {{border-left:3px solid {BLUE}; padding:2px 12px; margin:6px 0; font-size:.92rem;}}
  .meta {{color:{GREY}; font-size:.78rem;}}
</style>""", unsafe_allow_html=True)


def money(x):
    return f"${x/1e6:,.2f}M" if abs(x) >= 1e6 else f"${x/1000:,.1f}K"


def esc(t):
    return t.replace("$", "\\$")


def md(t):
    """**bold** -> <b>bold</b> for HTML tables; $ shown literally."""
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t).replace("$", "&#36;")


def pill(text, color):
    return f"<span class='pill' style='color:{color};border-color:{color}'>{text}</span>"


# ------------------------------------------------------------------------------------------ data and agents
@st.cache_resource(show_spinner="Loading sales data and the report library…")
def load():
    d = E.build(*E.load_data())
    rag._store()                                   # open ChromaDB and load the embedding model once
    return d, G.build_graph(d)


@st.cache_data
def vector_stats():
    p = APP / "vectorstore" / "stats.json"
    return json.loads(p.read_text()) if p.exists() else None


d, graph = load()
if "runs" not in st.session_state:
    st.session_state["runs"] = {}
    st.session_state["chat"] = {}
    st.session_state["uploads"] = []


def make_case(cid, raw, detected_by):
    pl = E.payload_from_handoff(d, raw)
    return dict(id=cid, raw=raw, pl=pl, detected_by=detected_by)


def cases():
    out = []
    for c in json.loads((APP / "data" / "cases.json").read_text())["cases"]:
        out.append(make_case(c["id"], json.loads((APP / "data" / c["payload"]).read_text()), c["detected_by"]))
    return out + st.session_state["uploads"]


def dept_label(pl):
    return "Whole store" if pl.get("grain") == "store_week" else f"{pl['dept']} · {pl['dept_name']}"


def gap(pl):
    return pl["actual_sales"] / pl["expected_sales"] - 1


# ------------------------------------------------------------------------------------------ running the agents
def run_live(case):
    """Run the LangGraph orchestrator and stream each agent's progress into the dialog."""
    t0 = time.time()
    final, trace = {}, []
    with st.status("The agents are working…", expanded=True) as status:
        st.write("**Orchestrator** reads the payload and sends one task to each agent.")
        for upd in graph.stream(dict(raw=case["raw"], trace=[]), stream_mode="updates"):
            for _, u in upd.items():
                for k, v in u.items():
                    if k != "trace":
                        final[k] = v
                for tr in u.get("trace", []):
                    trace.append(tr)
                    st.write(f"**{tr['agent']}** · {tr['ms']:,} ms: " + " · ".join(tr["lines"][:2]))
        total = time.time() - t0
        status.update(label=f"Done in {total:.1f} s", state="complete", expanded=False)
    final["trace"], final["seconds"] = trace, total
    st.session_state["runs"][case["id"]] = final
    return final


def render(case, run):
    pl, rep = run["pl"], run["report"]
    week = pd.Timestamp(pl["week_ending"]).strftime("%b %d, %Y")
    col = STATUS_COLOR[rep["status"]]
    with st.container(border=True):
        st.markdown(f"<div class='hdr'>Anomaly detected · {case['detected_by']}</div>", unsafe_allow_html=True)
        a1, a2, a3, a4 = st.columns([1, 1.3, 1.6, 0.8])
        a1.markdown(f"Store<br><b>{pl['store']} · {pl['region'].split(' (')[0]}</b>", unsafe_allow_html=True)
        a2.markdown(f"Department<br><b>{dept_label(pl)}</b><br>Week ending {week}", unsafe_allow_html=True)
        a3.markdown(f"Actual vs. expected<br><b>{md(money(pl['actual_sales']))} vs. {md(money(pl['expected_sales']))}</b>", unsafe_allow_html=True)
        a4.markdown(f"Gap<br><span class='gap' style='font-size:1.3rem'>{gap(pl)*100:+.1f}%</span>".replace("-", "−"), unsafe_allow_html=True)

    st.markdown(f"<div style='color:{NAVY};font-size:1.15rem;font-weight:700;margin:12px 0 6px 0'>Possible factors found by the agents</div>",
                unsafe_allow_html=True)
    rows = "".join(f"<tr><td class='f{' ro' if f['kind'] == 'ruled_out' else ''}'>{f['title']}</td>"
                   f"<td class='{'ro' if f['kind'] == 'ruled_out' else ''}'>{md(f['text'])}</td></tr>" for f in rep["factors"])
    st.markdown(f"<table class='ft'><tr><th style='width:26%'>Possible factor</th><th>What the evidence says</th></tr>{rows}</table>", unsafe_allow_html=True)
    ex = run.get("explanation")
    st.markdown(f"<div class='bl' style='border-color:{col}'>{pill(rep['status'] + ' · ' + rep['confidence'] + ' confidence', col)}"
                f"<div style='margin-top:6px'><b>Bottom line:</b> {md(rep['bottom_line'])}</div>"
                + (f"<div style='margin-top:6px;color:{GREY}'><b>In plain words ({ex['model']}):</b> {md(ex['text'])}</div>" if ex else "")
                + "</div>", unsafe_allow_html=True)
    lt = run.get("llm_try")
    if llm.available() and not ex:
        st.caption("The LLM's text was rejected by the guard (it added a fact that is not in the evidence), so the rules wrote the explanation." if lt
                   else "The LLM was not available (free models rate-limited), so the rules wrote the explanation.")
    st.markdown("**Suggested next steps**\n" + "\n".join(f"- {esc(r)}" for r in rep["review"]))

    with st.expander(f"📚 Evidence the RAG agent retrieved ({len(run['rag']['passages'])} passages)"):
        for h in run["rag"]["passages"]:
            link = f"[{h['doc']}]({h['url']})" if h["url"] else h["doc"]
            st.markdown(f"<div class='q'>“{md(h['quote'])}”<div class='meta'>{link} · {h['published']} · {h['district']} · {h['evidence_type']} · "
                        f"{h['relation']} · relevance {h['score']:.2f}</div></div>", unsafe_allow_html=True)
        s = run["rag"]["stats"]
        st.caption(f"{s['chunks_in_store']:,} chunks in the store → {s['chunks_after_filter']:,} after the time + region filter "
                   f"({s['reports_after_filter']} of {s['reports_in_store']} reports) → {s['candidates']} candidates → {s['returned']} returned.")
    with st.expander(f"⚙️ How the agents worked ({run['seconds']:.1f} s)"):
        for tr in run["trace"]:
            st.markdown(f"**{tr['agent']}** · {tr['ms']:,} ms\n" + "\n".join(f"- {esc(x)}" for x in tr["lines"]))


def followup(case, run):
    st.markdown(f"<div style='color:{NAVY};font-size:1.15rem;font-weight:700;margin:18px 0 6px 0'>Ask a follow-up question</div>", unsafe_allow_html=True)
    hist = st.session_state["chat"].setdefault(case["id"], [])
    for q, a in hist:
        st.chat_message("user", avatar="🧑").markdown(esc(q))
        st.chat_message("assistant", avatar="🤖").markdown(esc(a["text"]) + f"\n\n<span class='meta'>{a['meta']}</span>", unsafe_allow_html=True)
    sugg = ["How did Store 41 do?", "Did other stores see this?", "What about markdowns?", "How sure are you?"]
    cols, clicked = st.columns(len(sugg)), None
    for c, s in zip(cols, sugg):
        if c.button(s, key=f"s_{case['id']}_{s}", use_container_width=True):
            clicked = s
    with st.form(f"ff_{case['id']}", clear_on_submit=True, border=False):
        t1, t2 = st.columns([5, 1], vertical_alignment="bottom")
        q = t1.text_input("Your question", placeholder="e.g. How did Store 16 do?", label_visibility="collapsed")
        if t2.form_submit_button("Ask", use_container_width=True) and q:
            clicked = q
    if clicked:
        fg = G.build_followup_graph(d, run)
        with st.spinner("Thinking…"):
            out = fg.invoke(dict(question=clicked, trace=[]))
        ms = sum(t["ms"] for t in out["trace"])
        route = out["trace"][0]["lines"][0]
        hist.append((clicked, dict(text=out["answer"]["text"], meta=f"{route} · answered by {out['answer']['by']} · {ms:,} ms")))
        st.rerun(scope="fragment")


@st.dialog("🤖 AI Agents", width="large")
def ask_agent(case):
    run = st.session_state["runs"].get(case["id"])
    if run is None:
        run = run_live(case)
    render(case, run)
    followup(case, run)
    if st.button("↻ Run the agents again", key=f"re_{case['id']}"):
        st.session_state["runs"].pop(case["id"], None)
        st.rerun()


# ------------------------------------------------------------------------------------------ page
st.markdown("<div class='brand'>Walmart · Exception Detection</div>"
            "<div class='title'>Sales Exception Assistant</div>"
            "<div class='sub'>Weeks where sales came in well below what was expected. "
            "Click <b>Ask agent</b> and the AI agents investigate, live.</div>", unsafe_allow_html=True)

CASES = cases()
runs = st.session_state["runs"]
done = [runs[c["id"]] for c in CASES if c["id"] in runs]
k1, k2, k3, k4 = st.columns(4)
kpis = [(len(CASES), "Exceptions detected"), (money(sum(c["pl"]["expected_sales"] - c["pl"]["actual_sales"] for c in CASES)), "Total sales gap"),
        (sum(r["report"]["status"] == "Needs review" for r in done) if done else "–", "Need review"),
        (sum(r["report"]["status"] == "Likely explained" for r in done) if done else "–", "Likely explained")]
for col, (v, label) in zip([k1, k2, k3, k4], kpis):
    with col.container(border=True):
        st.markdown(f"<div class='kpi-v'>{v}</div><div class='kpi-l'>{label}</div>", unsafe_allow_html=True)

st.write("")
st.markdown(f"<h4 style='color:{NAVY};margin-bottom:6px'>Exceptions detected</h4>", unsafe_allow_html=True)
W = [1.2, 0.7, 1.2, 1.5, 1.0, 1.0, 0.8, 1.4, 1.2]
heads = ["Week ending", "Store", "Region", "Department", "Expected", "Actual", "Gap", "Status", ""]
with st.container(border=True):
    for col, h in zip(st.columns(W, vertical_alignment="center"), heads):
        col.markdown(f"<div class='hdr'>{h}</div>", unsafe_allow_html=True)
    for c in CASES:
        pl = c["pl"]
        st.markdown(f"<hr style='margin:4px 0;border:none;border-top:1px solid {LINE}'>", unsafe_allow_html=True)
        cols = st.columns(W, vertical_alignment="center")
        r = runs.get(c["id"])
        status = pill(r["report"]["status"], STATUS_COLOR[r["report"]["status"]]) if r else pill("Not investigated", GREY)
        vals = [pd.Timestamp(pl["week_ending"]).strftime("%b %d, %Y"), f"Store {pl['store']}", pl["region"].split(" (")[0], dept_label(pl),
                money(pl["expected_sales"]), money(pl["actual_sales"]), f"<span class='gap'>{gap(pl)*100:+.1f}%</span>".replace("-", "−"), status]
        for col, v in zip(cols, vals):
            col.markdown(f"<div class='cell'>{v}</div>", unsafe_allow_html=True)
        if cols[-1].button("🤖 Ask agent", key=f"ask_{c['id']}", type="primary", use_container_width=True):
            ask_agent(c)

with st.expander("Investigate another anomaly payload (JSON)"):
    st.caption("Accepts the Extra Trees hand-off (store × department × week) or the primary anomaly payload (store × week).")
    up = st.file_uploader("Payload", type="json", label_visibility="collapsed")
    if up is not None:
        try:
            raw = json.load(up)
            E.payload_kind(raw)
            cid = f"UPLOAD-{up.name}"
            if all(c["id"] != cid for c in st.session_state["uploads"]):
                st.session_state["uploads"].append(make_case(cid, raw, "Uploaded payload"))
                st.rerun()
        except Exception as e:
            st.error(f"Could not read this payload: {e}")

with st.expander("What the agents know and how they work"):
    s = vector_stats()
    if s:
        a, b, c3, d4 = st.columns(4)
        a.metric("Reports", s["files"])
        b.metric("Chunks embedded", f"{s['chunks']:,}")
        c3.metric("Vector store", f"{s['vector_store_mb']} MB")
        d4.metric("Embedding", f"{s['embedding_dim']}-dim")
        st.caption(f"{s['embedding_model']} · {s['index']} · chunks of about {s['avg_chunk_chars']} characters (target {s['chunk_target_chars']}, overlap {s['overlap_chars']}) · "
                   f"built in {s['build_seconds']} s.")
    st.markdown("**RAG strategy:** short natural-language queries → time + Fed-district filter inside ChromaDB → vector search → sentence-level re-rank → "
                "at most 2 chunks per report → verbatim quotes.  \n"
                "**Reasoning:** rules decide the verdict and confidence; " +
                (f"an LLM ({llm.model_label()}) rewrites the explanation and every number and quote it uses is checked." if llm.available()
                 else "no LLM key is set, so rules write the text (set OPENROUTER_API_KEY in app/.env to turn the LLM on).") +
                "  \nDepartment and region names are publicly inferred, not confirmed by Walmart.")
