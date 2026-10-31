"""Store Sales Assistant: dashboard UI demo (IDS 560, Team 2).

UI only. The answers are recorded from real runs of the AI agents and stored in data/demo_data.json, so there is no backend,
no AI key and no internet needed. "Find out why" plays a short progress animation and then shows the recorded answer.

Run:  pip install -r requirements.txt && python3 -m streamlit run app.py
"""
import base64
import json
import re
import time
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

APP = Path(__file__).parent
st.set_page_config(page_title="Sales Exception Assistant", page_icon="🛒", layout="wide", initial_sidebar_state="collapsed")

# Walmart palette
NAVY, BLUE, SPARK, GREEN, RED, AMBER = "#041E42", "#0071DC", "#FFC220", "#2A8703", "#D41E00", "#B95000"
GREY, LINE, LIGHT = "#5A5F66", "#E3E6EA", "#F5F7FA"
VERDICT = {  # internal status -> (label the manager sees, one-line reason, text colour, background). Action first.
    "Likely store issue": ("Action needed", "Likely a store issue", RED, "#FDECEA"),
    "Needs human review": ("Check before acting", "The answer couldn't be fully verified", AMBER, "#FDF1E3"),
    "Likely explained": ("No action needed", "Likely explained by a holiday, the season or a chain-wide trend", GREEN, "#EAF4E4"),
    "Error": ("Try again", "The assistant didn't respond", GREY, LIGHT),
    "New": ("New", "Not looked at yet", GREY, LIGHT),
}
URGENCY = {"Likely store issue": 0, "Needs human review": 1, "Error": 2, "New": 3, "Likely explained": 4}
FAILED = {  # evaluation check -> plain reason
    "Numbers match the evidence": "a number in the answer did not match the sales data",
    "Quotes are word for word": "a quote could not be found in the reports",
    "Every factor cites evidence": "a reason was not backed by evidence",
    "Answer is complete": "part of the answer was missing",
}
STEPS = {"Anomaly payload": "Read the alert", "Orchestrator": "Decided what to check", "Evidence Agent": "Checked the sales data",
         "RAG Agent": "Read Walmart and Federal Reserve reports", "Reasoning Agent": "Wrote the answer",
         "Evaluation": "Double-checked the answer"}

st.markdown(f"""
<style>
  .stApp {{background:#F5F7FA;}}
  header[data-testid="stHeader"] {{background:transparent;}}
  .block-container {{padding-top: 1.2rem; max-width: 1180px;}}
  [data-testid="stSidebarCollapsedControl"] {{display: none;}}
  .topbar {{background:{BLUE}; border-radius:14px; padding:16px 24px; display:flex; align-items:center; gap:18px; margin-bottom:18px;}}
  .topbar img {{height:40px; margin:0 6px;}}
  .wordmark {{color:#FFFFFF; font-weight:800; font-size:1.5rem; letter-spacing:-.01em;}}
  .topbar-t {{color:#FFFFFF; font-size:1.35rem; font-weight:700; margin-left:10px;}}
  .topbar-r {{margin-left:auto; color:#FFFFFF; font-size:.85rem; text-align:right; opacity:.95;}}
  .title {{color:{NAVY}; font-size:1.7rem; font-weight:800; margin:2px 0 2px 0;}}
  .sub {{color:{GREY}; font-size:.98rem; margin-bottom:14px;}}
  .tile {{background:#FFFFFF; border:1px solid {LINE}; border-radius:12px; padding:14px 18px;}}
  .tile-v {{font-size:1.7rem; font-weight:800; color:{NAVY}; line-height:1.15;}}
  .tile-l {{color:{GREY}; font-size:.88rem;}}
  .h {{color:{NAVY}; font-size:1.15rem; font-weight:800; margin:18px 0 10px 0;}}
  .store {{color:{NAVY}; font-weight:800; font-size:1.02rem;}}
  .muted {{color:{GREY}; font-size:.9rem;}}
  .drop {{color:{RED}; font-weight:800; font-size:1.3rem;}}
  .pill {{display:inline-block; padding:3px 12px; border-radius:999px; font-size:.8rem; font-weight:700;}}
  .cat {{display:inline-block; background:#E6F1FC; color:{BLUE}; border-radius:6px; padding:1px 8px; font-size:.75rem; font-weight:700;}}
  .banner {{border-radius:12px; padding:16px 20px; margin:14px 0 6px 0;}}
  .banner-h {{font-size:1.35rem; font-weight:800;}}
  .reason {{background:{LIGHT}; border-radius:10px; padding:12px 16px; margin-bottom:10px;}}
  .reason-t {{color:{NAVY}; font-weight:800; font-size:1rem; margin-bottom:3px;}}
  .chip {{display:inline-block; background:#E6F1FC; color:{BLUE}; border-radius:6px; padding:1px 8px; font-size:.75rem;
          font-weight:700; margin:6px 6px 0 0;}}
  .step {{font-size:1rem; padding:3px 0;}}
  .quote {{border-left:3px solid {BLUE}; padding:2px 12px; margin:8px 0; font-size:.95rem;}}
  .dim {{opacity:.5;}}
  [data-testid="stVerticalBlockBorderWrapper"] {{background:#FFFFFF; border-radius:12px;}}
  div.stButton > button {{border-radius:999px;}}
  .empty {{background:#FFFFFF; border:1px dashed {LINE}; border-radius:12px; padding:28px; text-align:center; color:{GREY};}}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------ helpers
def money(x):
    return f"${x/1e6:,.2f}M" if abs(x) >= 1e6 else f"${x/1000:,.1f}K"


def esc(t):
    return t.replace("$", "\\$")


def md(t):
    """**bold** -> <b>bold</b> for HTML; $ shown literally."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t).replace("$", "&#36;")


def pill(text, color, bg):
    return f"<span class='pill' style='color:{color};background:{bg}'>{text}</span>"


def what(pl):
    return "Whole store" if pl.get("grain") == "store_week" else pl["dept_name"]


def week(pl):
    return pd.Timestamp(pl["week_ending"]).strftime("%b %-d, %Y")


def drop(pl):
    return f"{(pl['actual_sales'] / pl['expected_sales'] - 1) * 100:+.1f}%".replace("-", "−")


def status_of(run):
    if run.get("error"):
        return "Error"
    return run["report"]["verdict"] if run["evaluation"]["passed"] else "Needs human review"


# ------------------------------------------------------------------------------------------ recorded data
DEMO = json.loads((APP / "data" / "demo_data.json").read_text())
for k, v in (("runs", {}), ("chat", {})):
    st.session_state.setdefault(k, v)


def cases():
    return DEMO["cases"]


# ------------------------------------------------------------------------------------------ running the agents
def run_live(case):
    """Play the progress steps, then return the recorded run (no agents are called)."""
    t0 = time.time()
    run = dict(case["run"], pl=case["pl"])
    with st.status("Looking into it… this takes about half a minute.", expanded=True) as status:
        for tr in run["trace"]:
            st.markdown(f"<div class='step'>✓ {STEPS.get(tr['agent'], tr['agent'])}</div>", unsafe_allow_html=True)
            time.sleep(0.7)
        status.update(label="Done", state="complete", expanded=False)
    st.session_state["runs"][case["id"]] = run
    return run


def sources_of(f, facts):
    """Plain source labels for one reason: sales data, Walmart report, Fed report, NRF report."""
    ps = {p["id"]: p for p in facts["passages"]}
    out = []
    for x in f["evidence"]:
        if x in ps:
            src = ps[x]["source"]
            out.append("Walmart report" if src.startswith("Walmart") else "NRF report" if src.startswith("NRF") else "Federal Reserve report")
        else:
            out.append("Sales data")
    return list(dict.fromkeys(out))


# ------------------------------------------------------------------------------------------ answer view
def render(case, run):
    pl = run.get("pl", case["pl"])
    st.markdown(f"<div class='store'>Store {pl['store']} · {what(pl)}</div>"
                f"<div class='muted'>Week ending {week(pl)} · sold {md(money(pl['actual_sales']))} vs. "
                f"{md(money(pl['expected_sales']))} expected <b style='color:{RED}'>({drop(pl)})</b></div>", unsafe_allow_html=True)

    if run.get("error"):
        st.markdown(f"<div class='banner' style='background:{LIGHT}'><div class='banner-h' style='color:{NAVY}'>Try again"
                    f"</div><div>The assistant didn't respond (the free AI service was busy). Please try again in a minute.</div></div>",
                    unsafe_allow_html=True)
        return

    rep, res, facts = run["report"], run["evaluation"], run["facts"]
    status = status_of(run)
    head, sub, col, bg = VERDICT[status]
    if res["passed"]:
        st.markdown(f"<div class='banner' style='background:{bg}'><div class='banner-h' style='color:{col}'>{head}</div>"
                    f"<div style='font-weight:700;margin-top:2px'>{sub}</div>"
                    f"<div style='margin:4px 0 8px 0'>{md(rep['bottom_line'])}</div>{pill(rep['confidence'] + ' confidence', col, '#FFFFFF')}"
                    f"</div>", unsafe_allow_html=True)
    else:
        why = "; ".join(FAILED.get(c["name"], c["name"]) for c in res["checks"] if not c["passed"])
        st.markdown(f"<div class='banner' style='background:{bg}'><div class='banner-h' style='color:{col}'>{head}</div>"
                    f"<div style='margin-top:4px'>Please double-check this answer before acting on it: {why}.</div></div>",
                    unsafe_allow_html=True)
    dim = "" if res["passed"] else " class='dim'"

    st.markdown("<div class='h'>Why it happened</div>", unsafe_allow_html=True)
    html = "".join(f"<div class='reason'><div class='reason-t'>{i + 1}. {md(f['title'])}</div>{md(f['text'])}<div>"
                   + "".join(f"<span class='chip'>{s}</span>" for s in sources_of(f, facts)) + "</div></div>"
                   for i, f in enumerate(rep["factors"]))
    if rep["ruled_out"]:
        html += f"<div class='muted' style='margin:4px 2px 0 2px'><b>Not the cause:</b> {md(rep['ruled_out'])}</div>"
    st.markdown(f"<div{dim}>{html}</div>", unsafe_allow_html=True)

    if rep["next_steps"]:
        st.markdown("<div class='h'>What to do next</div>", unsafe_allow_html=True)
        st.markdown(f"<div{dim}>" + "".join(f"<div class='step'>☐ {md(s)}</div>" for s in rep["next_steps"]) + "</div>",
                    unsafe_allow_html=True)


def details(run):
    """The detail behind the answer, one click away."""
    if run.get("error"):
        return
    with st.expander("Show the report quotes"):
        for h in run["rag"]["passages"]:
            link = f"[{h['doc']}]({h['url']})" if h["url"] else h["doc"]
            st.markdown(f"<div class='quote'>“{md(h['quote'])}”<div class='muted'>{link} · {h['published']} · {h['district']}</div></div>",
                        unsafe_allow_html=True)
    with st.expander("Show how the answer was checked"):
        for c in run["evaluation"]["checks"]:
            st.markdown(f"{'✅' if c['passed'] else '❌'} **{c['name']}**: {esc(c['detail'])}")
        plan = run["plan"]
        st.markdown("**What the assistant decided to check**\n" + "\n".join(
            f"- {'✅' if k in plan['checks'] else '▫️'} {esc(v)}" for k, v in DEMO["menu"][("store_week" if run["pl"].get("grain") == "store_week" else "department_week")].items()))
        st.markdown("**What it searched for in the reports**\n" + "\n".join(f"- {esc(q['text'])}" for q in plan["queries"]))
        st.caption(" · ".join(f"{STEPS.get(t['agent'], t['agent'])} {t['ms'] / 1000:.1f} s" for t in run["trace"]))


def followup(case, run):
    st.markdown("<div class='h'>Ask the assistant</div>", unsafe_allow_html=True)
    hist = st.session_state["chat"].setdefault(case["id"], [])
    for q, a in hist:
        st.chat_message("user", avatar="🧑").markdown(esc(q))
        st.chat_message("assistant", avatar="🛒").markdown(esc(a["text"]))
    sugg = ["How did other stores do?", "What about promotions?", "How sure are you?", "What should I do?"]
    cols, clicked = st.columns(len(sugg)), None
    for c, s in zip(cols, sugg):
        if c.button(s, key=f"s_{case['id']}_{s}", width="stretch"):
            clicked = s
    with st.form(f"ff_{case['id']}", clear_on_submit=True, border=False):
        t1, t2 = st.columns([5, 1], vertical_alignment="bottom")
        q = t1.text_input("Your question", placeholder="Type a question, e.g. How did Store 16 do?", label_visibility="collapsed")
        if t2.form_submit_button("Ask", width="stretch") and q:
            clicked = q
    if clicked:
        with st.spinner("Thinking…"):
            time.sleep(0.8)
        hist.append((clicked, dict(text=run["chat"].get(clicked, DEMO["fallback_chat"]))))
        st.rerun(scope="fragment")


@st.dialog("What the assistant found", width="large", on_dismiss="rerun")
def ask_agent(case):
    run = st.session_state["runs"].get(case["id"]) or run_live(case)
    render(case, run)
    if not run.get("error"):
        followup(case, run)
        details(run)
    if st.button("Try again" if run.get("error") else "Run again", key=f"re_{case['id']}", type="primary" if run.get("error") else "secondary"):
        st.session_state["runs"].pop(case["id"], None)
        st.session_state["chat"].pop(case["id"], None)
        st.rerun()


# ------------------------------------------------------------------------------------------ page
def logo_html():
    """Official Walmart Spark (Spark Yellow on True Blue, an approved primary use) from app/assets, downloaded from
    brandcenter.walmart.com. Brand rules: the Spark may stand alone; it is never redrawn or placed right next to the wordmark."""
    f = APP / "assets" / "walmart_spark.svg"
    if f.exists():
        return f"<img src='data:image/svg+xml;base64,{base64.b64encode(f.read_bytes()).decode()}' alt='Walmart'>"
    return "<span class='wordmark'>Walmart</span>"


def region(pl):
    return pl["region"].split(" (")[0]


def category(pl):
    return "Whole store" if pl.get("grain") == "store_week" else (pl.get("merch_unit") or "Other")


st.markdown(f"<div class='topbar'>{logo_html()}<div class='topbar-t'>Store Sales Assistant</div>"
            f"<div class='topbar-r'>Store manager view<br>Sales data through Oct 26, 2012</div></div>", unsafe_allow_html=True)
st.markdown("<div class='title'>Sales drops to review</div>"
            "<div class='sub'>Weeks where a store sold less than expected. Pick a week and click <b>Find out why</b>: the assistant "
            "checks the sales data and Walmart's reports for you.</div>", unsafe_allow_html=True)

CASES = cases()
runs = st.session_state["runs"]
rows = pd.DataFrame([dict(id=c["id"], store=c["pl"]["store"], region=region(c["pl"]), week=pd.Timestamp(c["pl"]["week_ending"]),
                          category=category(c["pl"]), gap=c["pl"]["expected_sales"] - c["pl"]["actual_sales"],
                          pct=c["pl"]["actual_sales"] / c["pl"]["expected_sales"] - 1) for c in CASES])

# filters: options cover the whole chain, so the page looks the same when every flagged week is loaded
ALL = {"store": "All stores", "region": "All regions", "week": "All weeks", "category": "All categories"}
store_opts = [ALL["store"]] + [f"Store {n}" for n in DEMO["stores"]]
region_opts = [ALL["region"]] + DEMO["regions"]
week_opts = [ALL["week"]] + [w.strftime("%b %-d, %Y") for w in sorted(rows.week.unique(), reverse=True)]
cat_opts = [ALL["category"], "Whole store"] + DEMO["categories"]


def reset_filters():
    for k, v in ALL.items():
        st.session_state[f"f_{k}"] = v


with st.container(border=True):
    f1, f2, f3, f4, f5 = st.columns([1, 1.2, 1.1, 1.2, 0.55], vertical_alignment="bottom")
    f_store = f1.selectbox("Store", store_opts, key="f_store")
    f_region = f2.selectbox("Region", region_opts, key="f_region")
    f_week = f3.selectbox("Week", week_opts, key="f_week")
    f_cat = f4.selectbox("Category", cat_opts, key="f_category")
    f5.button("Reset", on_click=reset_filters, width="stretch")

view = rows
if f_store != ALL["store"]:
    view = view[view.store == int(f_store.split()[-1])]
if f_region != ALL["region"]:
    view = view[view.region == f_region]
if f_week != ALL["week"]:
    view = view[view.week.dt.strftime("%b %-d, %Y") == f_week]
if f_cat != ALL["category"]:
    view = view[view.category == f_cat]

done = [status_of(runs[i]) for i in view.id if i in runs]
tiles = [(len(view), "Flagged weeks"), (money(view.gap.sum()) if len(view) else "$0", "Sales below expected"),
         (sum(s == "Likely store issue" for s in done), "Action needed"),
         (sum(s == "Needs human review" for s in done), "Check before acting"),
         (sum(s == "Likely explained" for s in done), "No action needed"),
         (sum(i not in runs for i in view.id), "New")]
for col, (v, label) in zip(st.columns(len(tiles)), tiles):
    col.markdown(f"<div class='tile'><div class='tile-v'>{v}</div><div class='tile-l'>{label}</div></div>", unsafe_allow_html=True)

left, right = st.columns([2.35, 1], gap="medium")
with left:
    h1, h2 = st.columns([1.6, 1], vertical_alignment="bottom")
    h1.markdown("<div class='h'>Flagged weeks</div>", unsafe_allow_html=True)
    sort = h2.selectbox("Sort by", ["Most urgent", "Biggest drop", "Newest week", "Store number"])
    view = view.assign(urgency=[URGENCY[status_of(runs[i]) if i in runs else "New"] for i in view.id])
    view = view.sort_values(**{"Most urgent": dict(by=["urgency", "gap"], ascending=[True, False]),
                               "Biggest drop": dict(by="gap", ascending=False), "Newest week": dict(by="week", ascending=False),
                               "Store number": dict(by="store")}[sort])
    PAGE = 10
    pages = max(1, -(-len(view) // PAGE))
    page = st.session_state.get("page", 1) if pages > 1 else 1
    by_id = {c["id"]: c for c in CASES}
    if view.empty:
        st.markdown("<div class='empty'>No flagged weeks match these filters.</div>", unsafe_allow_html=True)
    for cid in view.id.iloc[(page - 1) * PAGE:page * PAGE]:
        c = by_id[cid]
        pl, r = c["pl"], runs.get(cid)
        with st.container(border=True):
            a_, b_, s_, btn = st.columns([2.1, 1.5, 1.35, 1.05], vertical_alignment="center")
            a_.markdown(f"<div class='store'>Store {pl['store']} · {what(pl)}</div>"
                        f"<div class='muted'>{region(pl)} · week ending {week(pl)}</div>"
                        f"<span class='cat'>{'All departments' if category(pl) == 'Whole store' else category(pl)}</span>",
                        unsafe_allow_html=True)
            b_.markdown(f"<span class='drop'>{drop(pl)}</span><div class='muted'>{md(money(pl['actual_sales']))} sold vs. "
                        f"{md(money(pl['expected_sales']))} expected</div>", unsafe_allow_html=True)
            head, sub, col, bg = VERDICT[status_of(r) if r else "New"]
            s_.markdown(f"{pill(head, col, bg)}<div class='muted' style='font-size:.78rem;margin-top:4px'>{sub}</div>",
                        unsafe_allow_html=True)
            if btn.button("See answer" if r and not r.get("error") else "Find out why", key=f"ask_{cid}", type="primary",
                          width="stretch"):
                ask_agent(c)
    if len(view):
        n0, n1 = (page - 1) * PAGE + 1, min(page * PAGE, len(view))
        p1, p2 = st.columns([3, 1], vertical_alignment="center")
        p1.caption(f"Showing {n0}–{n1} of {len(view)} flagged weeks")
        if pages > 1:
            p2.selectbox("Page", list(range(1, pages + 1)), key="page", label_visibility="collapsed")

with right:
    st.markdown("<div class='h'>Sales below expected by region</div>", unsafe_allow_html=True)
    with st.container(border=True):
        if view.empty:
            st.caption("Nothing to show for these filters.")
        else:
            by_region = view.groupby("region", as_index=False).gap.sum().sort_values("gap", ascending=False)
            by_region["label"] = by_region.gap.map(money)
            chart = (alt.Chart(by_region).mark_bar(color=BLUE, cornerRadiusEnd=4, height=18)
                     .encode(x=alt.X("gap:Q", title=None, axis=alt.Axis(format="$~s", grid=True, gridColor="#EEF0F3",
                                                                        labelColor=GREY, domain=False, ticks=False, tickCount=3)),
                             y=alt.Y("region:N", sort="-x", title=None, axis=alt.Axis(labelColor="#1D1D1D", domain=False, ticks=False,
                                                                                      labelFontSize=12, labelOverlap=False, labelLimit=140)),
                             tooltip=[alt.Tooltip("region:N", title="Region"), alt.Tooltip("label:N", title="Below expected")])
                     .properties(height=max(110, 44 * len(by_region)))
                     .configure_view(stroke=None))
            st.altair_chart(chart, width="stretch")
    st.markdown("<div class='h'>How it works</div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("1. **Decides what to check** for the week\n"
                    "2. **Checks the sales data** against last year, nearby stores and all 45 stores\n"
                    "3. **Reads Walmart and Federal Reserve reports** from the same time and region\n"
                    "4. **Writes the likely reasons** and double-checks every number and quote")
        st.info("Demo version: the answers are recorded from real runs, so nothing is calculated live.")
        st.caption("Region and department names are publicly inferred, not confirmed by Walmart. "
                   "The Walmart Spark design is a trademark of Walmart Apollo, LLC.")
