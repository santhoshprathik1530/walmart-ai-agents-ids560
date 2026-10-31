"""Store Sales Assistant (Phase 2): the dashboard for the ML team's flagged store-weeks (v3.4).

    python3 -m streamlit run dashboard.py        (run from app/, after agents.pipeline_v3 has written data/agent_outputs_v3.json)

The ML team defines the exception; the assistant only looks for evidence that supports each flag (Santhosh, 2026-10-31).
Home: tiles, filters (Store / Region / Week / Category / Status), the flagged store-weeks in the ML team's priority order.
Case page:
  1 What did the ML team flag?        the ML status, the flagged departments with the ML numbers and the ML team's notes
  2 What supports the flag?           findings tagged by where they come from: all stores, same department, region, this
                                      store, outside factors, Walmart / Fed reports; what was not found
  3 Department by department          the same department at every store that week (ML forecast), per-department summary
  4 Walmart that week                 all 45 stores, week by week against the ML forecast; this store; outside factors
  5 What to check next                next steps and the data that would confirm a cause
Then a chat assistant for follow-up questions (agents/chat_v3.py) and how the answer was checked.
The 40 answers are precomputed (agents/pipeline_v3.py). Live: "Add a new case" uploads case files and runs the assistant
on them now; "Run the assistant again" re-runs one case. Live runs are saved to data/agent_outputs_v3_live.json.
"""
from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from agents import pipeline_v3 as P
from agents import support

APP = Path(__file__).parent
DATA = APP / "data"
st.set_page_config(page_title="Store Sales Assistant", page_icon="🛒", layout="wide", initial_sidebar_state="collapsed")

# Walmart brand: True Blue + Spark Yellow on white. Status colours always come with a label.
BLUE, NAVY, SPARK, INK, GREY, LINE, LIGHT = "#0053E2", "#001E60", "#FFC220", "#1A1A1A", "#5A5F66", "#E3E6EA", "#F5F7FA"
STATUS = {  # shown status -> (icon, one-line meaning, text colour, background)
    "Analyst review required": ("◆", "The ML team flagged this week for review; the cause is not verified. Below is the "
                                "evidence the assistant found that may support the flag.", NAVY, "#E6EEFC"),
    "Answer needs a check": ("◐", "The assistant's explanation failed a check; read it with care.", "#8A4B00", "#FDF1E3"),
    "Try again": ("↻", "The assistant did not finish this case. Run it again.", GREY, LIGHT),
    "New": ("+", "Added, not looked at yet. Run the assistant.", GREY, LIGHT),
}
ORDER = {"Analyst review required": 0, "Answer needs a check": 1, "Try again": 2, "New": 3}
TAG = {"walmart": ("All Walmart stores", "#E6EEFC", BLUE), "department": ("Same department, other stores", "#E6EEFC", BLUE),
       "region": ("Same region", "#E6EEFC", BLUE), "store": ("This store", "#E6EEFC", BLUE),
       "outside": ("Outside factors", "#EEF0F3", GREY), "report": ("Walmart / Fed report", "#FFF4D6", "#7A5200"),
       "ml_note": ("ML team's note", "#EEF0F3", GREY)}
FOUND = {"Strong": "Strong supporting evidence", "Some": "Some supporting evidence", "Little": "Little supporting evidence"}
SERIES = dict(actual=("Actual", "#0053E2", "circle"), expected=("ML forecast", "#EB6834", "diamond"),
              season=("Same weeks, earlier years", "#1BAF7A", "square"))          # validated: dataviz validate_palette.js
FAILED = {"Numbers match the evidence": "a number did not match the sales data",
          "Quotes are word for word": "a quote was not found in the reports",
          "Every finding cites evidence": "a finding was not backed by evidence",
          "Answer is complete": "part of the answer was missing",
          "Guardrails respected": "the wording claimed more than the data shows",
          "Every finding is tagged": "a finding was not labelled with its source",
          "Covers the largest flagged department": "the department with the largest gap was not covered"}

st.markdown(f"""<style>
  .stApp {{background:#FFFFFF;}}
  header[data-testid="stHeader"] {{background:transparent;}}
  .block-container {{padding-top:1rem; max-width:1180px;}}
  .topbar {{background:{BLUE}; border-radius:14px; padding:14px 22px; display:flex; align-items:center; gap:16px; margin-bottom:16px;}}
  .topbar img {{height:38px;}}
  .topbar-t {{color:#fff; font-size:1.3rem; font-weight:700;}}
  .topbar-r {{margin-left:auto; color:#fff; font-size:.85rem; text-align:right; opacity:.95;}}
  .title {{color:{NAVY}; font-size:1.6rem; font-weight:800; margin:2px 0;}}
  .sub {{color:{GREY}; font-size:.97rem; margin-bottom:12px;}}
  .tile {{border:1px solid {LINE}; border-radius:12px; padding:12px 16px; background:#fff;}}
  .tile-v {{font-size:1.6rem; font-weight:800; color:{NAVY}; line-height:1.2;}}
  .tile-l {{color:{GREY}; font-size:.86rem;}}
  .q {{color:{NAVY}; font-size:1.18rem; font-weight:800; margin:26px 0 8px; padding-top:10px; border-top:1px solid {LINE};}}
  .q span {{display:inline-block; background:{SPARK}; color:{NAVY}; border-radius:999px; width:1.6em; height:1.6em;
           text-align:center; line-height:1.6em; margin-right:8px; font-size:.9rem;}}
  .pill {{display:inline-block; padding:3px 12px; border-radius:999px; font-size:.82rem; font-weight:700;}}
  .banner {{border-radius:12px; padding:14px 20px; margin:8px 0;}}
  .banner-h {{font-size:1.35rem; font-weight:800;}}
  .card {{background:{LIGHT}; border-radius:10px; padding:12px 16px; margin-bottom:10px;}}
  .card-t {{color:{NAVY}; font-weight:800; margin-bottom:3px;}}
  .tag {{display:inline-block; border-radius:6px; padding:1px 8px; font-size:.75rem; font-weight:700; margin-left:8px;}}
  .muted {{color:{GREY}; font-size:.9rem;}}
  .store {{color:{NAVY}; font-weight:800; font-size:1.02rem;}}
  .big {{color:{NAVY}; font-weight:800; font-size:1.15rem;}}
  .quote {{border-left:3px solid {BLUE}; padding:2px 12px; margin:8px 0; font-size:.93rem;}}
  div.stButton > button {{border-radius:999px;}}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------ helpers
def usd(x: float) -> str:
    return f"${x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"${x / 1000:,.1f}K" if abs(x) >= 1000 else f"${x:,.0f}"


def h(t) -> str:
    return html.escape(str(t)).replace("$", "&#36;")


def pill(status: str) -> str:
    icon, _, fg, bg = STATUS[status]
    return f"<span class='pill' style='color:{fg};background:{bg}'>{icon} {status}</span>"


def region(r: str) -> str:
    return r.split(" (")[0]


def week(d) -> str:
    return pd.Timestamp(d).strftime("%b %-d, %Y")


def logo() -> str:
    """Official Walmart Spark (brandcenter.walmart.com), Spark Yellow on True Blue; never redrawn, not next to the wordmark."""
    f = APP / "assets" / "walmart_spark.svg"
    return f"<img src='data:image/svg+xml;base64,{base64.b64encode(f.read_bytes()).decode()}' alt='Walmart Spark'>" if f.exists() else ""


def section(n: int, text: str):
    st.markdown(f"<div class='q'><span>{n}</span>{h(text)}</div>", unsafe_allow_html=True)


def tiles(items: list[tuple[str, str]]):
    for col, (v, l) in zip(st.columns(len(items)), items):
        col.markdown(f"<div class='tile'><div class='tile-v'>{h(v)}</div><div class='tile-l'>{h(l)}</div></div>", unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------ data
def stamp() -> tuple:
    """Changes whenever a case is uploaded or run live, so the cached data reloads."""
    files = [P.OUT, P.LIVE] + (sorted(P.UPLOADS.glob("*.json")) if P.UPLOADS.exists() else [])
    return tuple((str(f), f.stat().st_mtime) for f in files if f.exists())


@st.cache_data(show_spinner=False)
def load(_stamp: tuple):
    runs = {k: v for k, v in P.outputs().items() if "findings" in v.get("report", {}) or v.get("error")}   # skip older formats
    depts, cases, _ = P.tables()
    cases = cases.reset_index()
    units = depts.groupby("CaseID").Unit.apply(lambda s: sorted(set(s))).to_dict()
    cases["Shown"] = cases.CaseID.map(lambda c: runs[c]["shown_status"] if c in runs else "New")
    cases["RegionShort"] = cases.Region.map(region)
    cases["Units"] = cases.CaseID.map(units)
    cases["Week"] = pd.to_datetime(cases.Date)
    cases["Summary"] = cases.CaseID.map(lambda c: runs.get(c, {}).get("report", {}).get("summary", ""))
    cases["Found"] = cases.CaseID.map(lambda c: runs.get(c, {}).get("report", {}).get("evidence_found", ""))
    return runs, depts, cases


@st.cache_resource(show_spinner="Getting the assistant ready…")
def warm_chat():
    from agents import chat_v3, retrievers
    retrievers.corpus("section")                              # load the report index once
    return chat_v3


runs, depts, cases = load(stamp())
st.session_state.setdefault("chat", {})
st.session_state.setdefault("page", 0)
cid = st.query_params.get("case")

st.markdown(f"<div class='topbar'>{logo()}<div class='topbar-t'>Store Sales Assistant</div>"
            f"<div class='topbar-r'>Store manager view<br>Sales data through Oct 26, 2012</div></div>", unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------ home
def home():
    st.markdown("<div class='title'>Weeks the ML team flagged</div>"
                "<div class='sub'>The ML team's model (v3.4, a threshold per store) flagged these store-weeks (Jul 20 – Oct 26, 2012) "
                "because departments sold below its forecast. Every week needs a review. For each one, the assistant looked for "
                "evidence that supports the flag: all Walmart stores that week, the same department at other stores and in the "
                "region, the store's other departments, outside factors, and Walmart and Federal Reserve reports.</div>",
                unsafe_allow_html=True)
    nf = cases.Found.value_counts()
    tiles([(str(len(cases)), f"flagged store-weeks · {cases.Store.nunique()} stores"),
           (str(int(cases.FlaggedDepts.sum())), "departments below the store's threshold"),
           (usd(cases.FlaggedShortfall.sum()), "below the ML forecast (estimate)"),
           (f"{nf.get('Strong', 0)} / {nf.get('Some', 0)} / {nf.get('Little', 0)}", "strong / some / little supporting evidence")])
    add_cases()
    c = st.columns([1, 1.3, 1.3, 1.3, 1.4, 1.2])
    f_store = c[0].multiselect("Store", sorted(cases.Store.unique()), placeholder="All")
    f_region = c[1].multiselect("Region", sorted(cases.RegionShort.unique()), placeholder="All")
    f_week = c[2].multiselect("Week ending", [week(w) for w in sorted(cases.Week.unique())], placeholder="All")
    f_unit = c[3].multiselect("Category", sorted({u for us in cases.Units for u in us if u != "Unknown"}), placeholder="All")
    f_found = c[4].multiselect("Evidence found", [k for k in FOUND if k in set(cases.Found)], placeholder="All")
    sort = c[5].selectbox("Sort by", ["ML priority", "Most below forecast", "Newest week"])
    v = cases.copy()
    if f_store: v = v[v.Store.isin(f_store)]
    if f_region: v = v[v.RegionShort.isin(f_region)]
    if f_week: v = v[v.Week.map(week).isin(f_week)]
    if f_unit: v = v[v.Units.map(lambda us: bool(set(us) & set(f_unit)))]
    if f_found: v = v[v.Found.isin(f_found)]
    v = {"ML priority": v.sort_values("Rank"), "Most below forecast": v.sort_values("FlaggedShortfall", ascending=False),
         "Newest week": v.sort_values(["Week", "Rank"], ascending=[False, True])}[sort]

    per = 10
    pages = max(1, -(-len(v) // per))
    page = min(st.session_state["page"], pages - 1)
    st.markdown(f"<div class='muted'>{len(v)} store-weeks</div>", unsafe_allow_html=True)
    for r in v.iloc[page * per:(page + 1) * per].itertuples():
        with st.container(border=True):
            a, b, c2, d = st.columns([2.3, 2.2, 1.2, 1])
            a.markdown(f"{pill(r.Shown)}<div class='store' style='margin-top:6px'>Store {r.Store} · week ending {week(r.Week)}</div>"
                       f"<div class='muted'>{h(r.RegionShort)} · {h(r.FiscalPeriod)}"
                       f"{' · ' + h(r.HolidayWeek) + ' week' if isinstance(r.HolidayWeek, str) else ''} · ML priority {r.Rank}</div>",
                       unsafe_allow_html=True)
            b.markdown(f"<div class='muted'>Largest gap</div><div><b>{h(r.TopDept)}</b></div>"
                       f"<div class='muted'>{r.FlaggedDepts} departments flagged"
                       f"{' · ' + h(FOUND[r.Found].lower()) if r.Found in FOUND else ''}</div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='muted'>Below forecast</div><div class='big'>{usd(r.FlaggedShortfall)}</div>", unsafe_allow_html=True)
            if d.button("See the evidence", key=f"open_{r.CaseID}", type="primary"):
                st.query_params["case"] = r.CaseID
                st.rerun()
            if r.Summary:
                st.markdown(f"<div class='muted'>{h(r.Summary)}</div>", unsafe_allow_html=True)
    if pages > 1:
        p1, p2, p3 = st.columns([1, 2, 1])
        if p1.button("← Previous", disabled=page == 0):
            st.session_state["page"] = page - 1
            st.rerun()
        p2.markdown(f"<div class='muted' style='text-align:center;padding-top:8px'>Page {page + 1} of {pages}</div>", unsafe_allow_html=True)
        if p3.button("Next →", disabled=page >= pages - 1):
            st.session_state["page"] = page + 1
            st.rerun()

    with st.expander("Where are the flagged weeks?"):
        g = cases.groupby("RegionShort").agg(n=("CaseID", "size"), d=("FlaggedShortfall", "sum")).sort_values("d")
        fig = go.Figure(go.Bar(x=g.d, y=g.index, orientation="h", marker=dict(color=BLUE, cornerradius=4),
                               text=[f"{usd(x)} · {n} weeks" for x, n in zip(g.d, g.n)], textposition="outside",
                               hovertemplate="%{y}: %{text}<extra></extra>"))
        fig.update_layout(height=60 + 34 * len(g), margin=dict(l=0, r=90, t=10, b=10), plot_bgcolor="#fff", paper_bgcolor="#fff",
                          xaxis=dict(title="Below the ML forecast", gridcolor=LINE, tickprefix="$"), bargap=.45,
                          font=dict(color=INK))
        st.plotly_chart(fig, use_container_width=True, config=dict(displayModeBar=False))


# ------------------------------------------------------------------------------------------ case page
def dept_chart(g: pd.DataFrame):
    g = g.sort_values("Shortfall").tail(8)
    labels = [f"{int(r.Dept)} {r.DeptName}" for r in g.itertuples()]
    fig = go.Figure()
    for i, lab in enumerate(labels):
        r = g.iloc[i]
        vals = [x for x in (r.Actual, r.Expected, r.SeasonMedian) if x == x]
        fig.add_trace(go.Scatter(x=[min(vals), max(vals)], y=[lab, lab], mode="lines", line=dict(color=LINE, width=2),
                                 hoverinfo="skip", showlegend=False))
    for key, col in (("actual", "Actual"), ("expected", "Expected"), ("season", "SeasonMedian")):
        name, color, sym = SERIES[key]
        fig.add_trace(go.Scatter(x=g[col], y=labels, mode="markers", name=name,
                                 marker=dict(color=color, symbol=sym, size=11, line=dict(color="#fff", width=2)),
                                 hovertemplate=f"%{{y}}<br>{name}: $%{{x:,.0f}}<extra></extra>"))
    fig.update_layout(height=80 + 38 * len(g), margin=dict(l=0, r=10, t=30, b=10), plot_bgcolor="#fff", paper_bgcolor="#fff",
                      legend=dict(orientation="h", y=1.08, x=0), font=dict(color=INK), hovermode="closest",
                      xaxis=dict(tickprefix="$", gridcolor=LINE, title="Weekly sales"), yaxis=dict(gridcolor="#fff"))
    st.plotly_chart(fig, use_container_width=True, config=dict(displayModeBar=False))


def everywhere_chart(dept: int, date: str, store: int):
    """The same department at every store that week, against the ML forecast (the ML team's numbers)."""
    p = support.dept_everywhere(dept, date, store)
    p = p.assign(bar=p.Pct.clip(-100, 100))
    me_region = support.lookups()[1].Region.get(store)
    colors = [BLUE if t else "#7FA3EE" if rg == me_region else "#C9D6F2" for t, rg in zip(p.This, p.Region)]
    labels = [f"Store {int(s)}" + (" (this store)" if t else "") + (" ⚑" if f else "") for s, t, f in zip(p.Store, p.This, p.Flag)]
    fig = go.Figure(go.Bar(x=p["bar"], y=labels, orientation="h", marker=dict(color=colors, cornerradius=4),
                           customdata=list(zip(p.Pct, p.Region)),
                           hovertemplate="%{y}: %{customdata[0]:+.1f}% vs the ML forecast · %{customdata[1]}<extra></extra>"))
    fig.update_layout(height=60 + 16 * len(p), margin=dict(l=0, r=10, t=10, b=10), plot_bgcolor="#fff", paper_bgcolor="#fff",
                      xaxis=dict(ticksuffix="%", gridcolor=LINE, zerolinecolor=GREY, title="This week vs the ML forecast"),
                      yaxis=dict(tickfont=dict(size=10)), bargap=.3, font=dict(color=INK))
    st.plotly_chart(fig, use_container_width=True, config=dict(displayModeBar=False))


def weeks_chart(date: str):
    """All 45 stores, each test week, against the ML forecast; the case week marked."""
    w = support._weeks().reset_index()
    fig = go.Figure(go.Scatter(x=pd.to_datetime(w.Date), y=w.Pct, mode="lines+markers", line=dict(color=BLUE, width=2),
                               marker=dict(size=8, color=[SPARK if d == date else BLUE for d in w.Date],
                                           line=dict(color=[NAVY if d == date else "#fff" for d in w.Date], width=2)),
                               hovertemplate="Week ending %{x|%b %-d}: %{y:+.1f}% vs the ML forecast<extra></extra>"))
    fig.update_layout(height=230, margin=dict(l=0, r=10, t=10, b=10), plot_bgcolor="#fff", paper_bgcolor="#fff",
                      xaxis=dict(gridcolor="#fff"), yaxis=dict(ticksuffix="%", gridcolor=LINE, zerolinecolor=GREY,
                                                               title="All 45 stores vs forecast"), font=dict(color=INK))
    st.plotly_chart(fig, use_container_width=True, config=dict(displayModeBar=False))


def run_now(ids: list[str]) -> list[str]:
    """Run the assistant live on these cases, showing each step. Returns the ids that finished."""
    ok = []
    for i, one in enumerate(ids):
        with st.status(f"Running the assistant on {one.replace('_', ' ')} ({i + 1} of {len(ids)})…", expanded=True) as box:
            res = P.run_live(one, progress=box.write)
            if res.get("error"):
                box.update(label=f"{one.replace('_', ' ')}: {res['error']}", state="error")
            else:
                ok.append(one)
                box.update(label=f"{one.replace('_', ' ')}: {res['shown_status']} ({res['seconds']:.0f} s)", state="complete")
        st.session_state["chat"].pop(one, None)
    return ok


def add_cases():
    with st.expander("Add a new case from the ML team"):
        st.markdown("<div class='muted'>Upload one or more case files in the ML team's v3.4 (or v3.3) JSON format. The assistant checks the "
                    "file, compares the flagged departments with all stores and the region, reads the reports for that week and writes the answer "
                    "(about 20 seconds and $0.003 per case).</div>", unsafe_allow_html=True)
        files = st.file_uploader("Case files (.json)", type=["json"], accept_multiple_files=True, key="upload")
        if files and st.button("Run the assistant on these cases", type="primary"):
            ids = []
            for f in files:
                try:
                    js = json.loads(f.getvalue())
                    cid_new = P.add_case(js)
                    ids.append(cid_new)
                    if cid_new in set(cases.CaseID):
                        st.info(f"{f.name}: replaces the existing case {cid_new.replace('_', ' ')}.")
                except json.JSONDecodeError:
                    st.error(f"{f.name}: not a valid JSON file.")
                except ValueError as e:
                    st.error(f"{f.name}: can't be used: {e}.")
            done = run_now(ids)
            st.cache_data.clear()
            if len(done) == 1:
                st.query_params["case"] = done[0]
            if done:
                st.rerun()


def not_run_page(cid: str):
    r = cases.set_index("CaseID").loc[cid]
    if st.button("← All flagged weeks"):
        del st.query_params["case"]
        st.rerun()
    st.markdown(f"<div class='title'>Store {r.Store} · week ending {week(r.Week)}</div>", unsafe_allow_html=True)
    err = runs.get(cid, {}).get("error")
    st.markdown(f"<div class='banner' style='background:{LIGHT}'><div class='banner-h' style='color:{GREY}'>"
                f"{'↻ Try again' if err else '+ New'}</div><div>{h(err or 'The assistant has not looked at this case yet.')}</div></div>",
                unsafe_allow_html=True)
    if st.button("Run the assistant", type="primary"):
        run_now([cid])
        st.cache_data.clear()
        st.rerun()


def case_page(cid: str):
    x = runs[cid]
    c, rep = x["case"], x["report"]
    g = depts[depts.CaseID == cid].sort_values("Shortfall", ascending=False)
    date = g.Date.iloc[0]
    ev = {e["id"]: e for e in x["evidence"]}
    top_l, top_r = st.columns([3, 1])
    if top_l.button("← All flagged weeks"):
        del st.query_params["case"]
        st.rerun()
    if top_r.button("↻ Run the assistant again", use_container_width=True,
                    help="Runs this case again now with the latest reports and checks (about 30 s, $0.004)."):
        run_now([cid])
        st.cache_data.clear()
        st.rerun()
    holiday = f" · {c['holiday_week']} week" if c["holiday_week"] != "none" else ""
    st.markdown(f"<div class='title'>Store {c['store']} · week ending {h(c['week_ending'])}</div>"
                f"<div class='sub'>{h(region(c['region']))} · {h(c['fed_district'])} · Walmart {h(c['walmart_quarter'])}{h(holiday)} · "
                f"Type {h(c['store_type'])}, {h(c['store_size'])} · ML priority {h(c['ml_priority_rank'])}</div>", unsafe_allow_html=True)

    # 1 -------------------------------------------------------------------------------------------
    section(1, "What did the ML team flag?")
    shown = x["shown_status"]
    icon, meaning, fg, bg = STATUS[shown]
    if x.get("needs_review"):
        why = "; ".join(FAILED.get(k["name"], k["name"]) for k in x["evaluation"]["checks"] if not k["passed"])
        meaning = f"The ML team flagged this week for review, and the assistant's write-up below also failed a check: {why}."
    st.markdown(f"<div class='banner' style='background:{bg}'><div class='banner-h' style='color:{fg}'>{icon} {shown}</div>"
                f"<div>{h(meaning)}</div></div>", unsafe_allow_html=True)
    thr = c.get("store_threshold", "n/a").split(" (")[0]
    tiles([(str(len(g)), "departments below the store's threshold"), (usd(g.Shortfall.sum()), "below the ML forecast (estimate)"),
           (thr, "this store's threshold (set by the ML team)"), (FOUND.get(rep["evidence_found"], "n/a").split(" ")[0],
                                                                  "supporting evidence found")])
    dept_chart(g)
    tbl = pd.DataFrame({"Department": [f"{int(r.Dept)} {r.DeptName}" for r in g.itertuples()], "Category": g.Unit,
                        "Actual": g.Actual.map(usd), "ML forecast": g.Expected.map(usd),
                        "vs forecast": g.ShortfallPct.map(lambda v: f"{-v:+.1f}%"),
                        "vs last 4 weeks": g.VsRecent4Pct.map(lambda v: "n/a" if v != v else f"{v:+.0f}%"),
                        "vs same season": g.VsSeasonPct.map(lambda v: "n/a" if v != v else f"{v:+.0f}%"),
                        "ML team's notes": g.MLNotes})
    with st.expander("Show all flagged departments as a table (the ML team's numbers)"):
        st.dataframe(tbl, hide_index=True, use_container_width=True)
        st.caption("All numbers come from the ML team's case file. Department names and categories are publicly inferred.")

    # 2 -------------------------------------------------------------------------------------------
    section(2, "What supports the flag?")
    st.markdown(h(rep["summary"]), unsafe_allow_html=True)
    st.markdown("<div class='muted'>Possible reasons, not confirmed causes. Each one says where it comes from.</div>", unsafe_allow_html=True)
    for f in rep["findings"]:
        lab, tbg, tfg = TAG.get(f["scope"], (f["scope"], LIGHT, GREY))
        st.markdown(f"<div class='card'><div class='card-t'>{h(f['title'])}<span class='tag' style='background:{tbg};color:{tfg}'>"
                    f"{h(lab)}</span></div>{h(f['text'])}</div>", unsafe_allow_html=True)
    if rep.get("not_found"):
        st.markdown(f"<div class='muted'><b>Looked for but not found:</b> {h(rep['not_found'])}</div>", unsafe_allow_html=True)
    cited = {e for f in rep["findings"] for e in f["evidence"]}
    with st.expander("Show the report quotes"):
        for p in x["rag"]["passages"]:
            if p["id"] in cited:
                link = f" · <a href='{h(p['url'])}' target='_blank'>open report</a>" if p.get("url") else ""
                st.markdown(f"<b>{h(p['source'])}</b> <span class='muted'>· {h(p['date'])} · {h(p['district'])}{link}</span>"
                            f"<div class='quote'>{h(p['text'][:700])}{'…' if len(p['text']) > 700 else ''}</div>", unsafe_allow_html=True)
        st.caption(f"{len(x['rag']['passages'])} passages were read; only the ones used above are shown. Reports describe Walmart or a "
                   "Federal Reserve district as a whole, never this store.")

    # 3 -------------------------------------------------------------------------------------------
    section(3, "Department by department")
    for d in rep["departments"]:
        st.markdown(f"<div class='card'><div class='card-t'>{h(d['department'])}</div>{h(d['what_supports_it'])}</div>",
                    unsafe_allow_html=True)
    if support.covered(date):
        names = {int(r.Dept): f"{int(r.Dept)} {r.DeptName}" for r in g.itertuples()}
        dept = st.selectbox("Same department at every store that week", list(names), format_func=names.get)
        everywhere_chart(dept, date, int(c["store"]))
        e = ev.get(f"dept_{dept}", {})
        st.caption(f"{e.get('same_department_all_stores', '')}. {e.get('same_department_same_region', '')}. Dark blue = this store, "
                   "mid blue = same region (publicly inferred), ⚑ = also flagged by the ML team. Bars are cut at ±100%.")

    # 4 -------------------------------------------------------------------------------------------
    section(4, "Walmart that week")
    if support.covered(date):
        weeks_chart(date)
    for k in ("walmart_week", "walmart_quarter", "this_store", "outside", "markdowns"):
        if k in ev:
            st.markdown(f"<div class='muted'><b>{h(ev[k]['label'])}:</b> {h(ev[k]['value'])}</div>", unsafe_allow_html=True)

    # 5 -------------------------------------------------------------------------------------------
    section(5, "What to check next")
    st.markdown("\n".join(f"- {s}".replace("$", "\\$") for s in rep["next_steps"]))
    if rep.get("data_needed"):
        st.markdown("<div class='muted'><b>To confirm a cause you would need:</b> " + h("; ".join(rep["data_needed"])) + "</div>",
                    unsafe_allow_html=True)

    # chat ----------------------------------------------------------------------------------------
    section(6, "Ask a follow-up question")
    hist = st.session_state["chat"].setdefault(cid, [])
    top = g.iloc[0]
    ideas = [f"How did {top.DeptName} do at other stores that week?",
             f"What did Walmart say about {str(top.Unit).lower()} around this time?", "Was anything happening in the region that week?"]
    cols = st.columns(len(ideas))
    asked = None
    for col, q in zip(cols, ideas):
        if col.button(q, key=f"idea_{cid}_{q}", use_container_width=True):
            asked = q
    for m in hist:
        with st.chat_message(m["role"], avatar="🧑‍💼" if m["role"] == "user" else "💬"):
            st.markdown(m["text"].replace("$", "\\$"))
            if m.get("meta"):
                st.caption(m["meta"])
    asked = st.chat_input("Ask about this store-week…") or asked
    if asked:
        hist.append(dict(role="user", text=asked))
        chat = warm_chat()
        with st.spinner("Checking the sales data and reports…"):
            a = chat.answer(x, asked, hist[:-1])
        if a.get("text"):
            srcs = ", ".join(sorted({f"{s['source']} ({s['date']})" for s in a["sources"]}))
            ok = "✓ numbers and quotes checked against the data" if a["passed"] else \
                "⚠ could not verify everything: " + "; ".join(k["detail"] for k in a["checks"] if not k["passed"])
            hist.append(dict(role="assistant", text=a["text"], meta=ok + (f" · Sources: {srcs}" if srcs else "")))
        else:
            hist.append(dict(role="assistant", text=a["error"]))
        st.rerun()

    with st.expander("How the assistant checked this answer"):
        for k in x["evaluation"]["checks"]:
            st.markdown(f"{'✅' if k['passed'] else '❌'} **{k['name']}**: {k['detail']}".replace("$", "\\$"))
        p, rg = x["plan"], x["rag"]
        st.markdown(f"**Searched the reports for:** " + " | ".join(q["text"] for q in p["queries"]))
        st.caption(f"Reports from {rg['filter']['start']} to {rg['filter']['end']}, districts: {', '.join(rg['filter']['districts'])}. "
                   f"{rg['candidates']} passages found, {len(rg['passages'])} read. Written by {x['llm']['model']} in "
                   f"{x['seconds']:.0f} s{' (run live on ' + x['ran_at'] + ')' if x.get('ran_at') else ' (batch run)'}. "
                   "The flag, threshold and status are the ML team's; the assistant only looks for supporting evidence.")


if cid and cid in runs and "report" in runs[cid]:
    case_page(cid)
elif cid and cid in set(cases.CaseID):
    not_run_page(cid)
else:
    home()
