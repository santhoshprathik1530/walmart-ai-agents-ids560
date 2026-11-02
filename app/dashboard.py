"""Store Sales Assistant: the store dashboard for the ML model's flagged store-weeks (v4, 127 store-weeks).

    python3 -m streamlit run dashboard.py        (run from app/; answers come from data/agent_outputs_v3_v4.json)

The ML model defines the exception; the agent only looks for evidence that supports each flag (Santhosh, 2026-10-31).
UX pass 2026-11-02: the answer comes first. Home is one scannable list (column headers once, the $ gap and the evidence
strength stand out); the case page leads with the agent's short answer, puts 'Why' next to 'What to check', and moves the
charts into two tabs and the technical detail (and the live re-run) behind one panel.

Home:  tiles, filters (Show / Store / Region / Week / Category), the weeks in the ML model's priority order.
Case:  answer card (status, evidence strength, summary) · tiles · Why it may have happened | What to check
       · Where the gap is (tabs: by department, other stores) · Ask a question · 'How the agent got this answer'.
Live:  'Run the agent' runs the six steps now and shows each one (saved to data/agent_outputs_v3_v4_live.json; a
       failed run never replaces a saved answer).
"""
from __future__ import annotations

import base64
import html
import os
from pathlib import Path

os.environ.setdefault("AGENT_CASE_SET", "v4")          # the ML model's final package; must be set before agents load

import pandas as pd                                   # noqa: E402
import plotly.graph_objects as go                     # noqa: E402
import streamlit as st                                # noqa: E402

from agents import pipeline_v3 as P                   # noqa: E402
from agents import support                            # noqa: E402

APP = Path(__file__).parent
st.set_page_config(page_title="Store Sales Assistant", page_icon="🛒", layout="wide", initial_sidebar_state="collapsed")

# Walmart brand: True Blue, Bentonville Blue (navy) and Spark Yellow on white
BLUE, NAVY, SPARK, INK, GREY, LINE, LIGHT, SKY = ("#0053E2", "#001E60", "#FFC220", "#1A1A1A", "#5A5F66", "#E3E6EA",
                                                  "#F5F7FA", "#EEF4FE")
STATUS = {  # shown status -> (icon, text colour, background)
    "Needs analyst review": ("◆", NAVY, "#E6EEFC"),
    "Analyst review required": ("◆", NAVY, "#E6EEFC"),
    "Answer needs a check": ("◐", "#8A4B00", "#FDF1E3"),
    "Try again": ("↻", GREY, LIGHT),
    "Not run yet": ("○", GREY, LIGHT),
}
TAG = {"walmart": "Walmart overall", "department": "Same department, other stores", "region": "Same region",
       "store": "This store", "outside": "Outside factors", "report": "Walmart / Fed report", "ml_note": "ML model's note"}
EDGE = {"walmart": BLUE, "department": BLUE, "region": BLUE, "store": NAVY, "report": SPARK}   # finding card accent
LEVEL = {"Strong": 3, "Some": 2, "Little": 1}

st.markdown(f"""<style>
  .stApp {{background:#FFFFFF;}}
  header[data-testid="stHeader"] {{background:transparent;}}
  .block-container {{padding-top:1rem; max-width:1120px;}}
  .topbar {{background:{BLUE}; border-radius:14px; padding:12px 20px; display:flex; align-items:center; gap:14px; margin-bottom:18px;}}
  .topbar img {{height:34px;}}
  .topbar-t {{color:#fff; font-size:1.25rem; font-weight:700;}}
  .topbar-r {{margin-left:auto; color:#fff; font-size:.85rem; opacity:.9;}}
  .title {{color:{NAVY}; font-size:1.6rem; font-weight:800; margin:0; line-height:1.25;}}
  .sub {{color:{GREY}; font-size:.95rem; margin:2px 0 14px;}}
  .tile {{border:1px solid {LINE}; border-radius:12px; padding:12px 16px; height:100%;}}
  .tile.hero {{border-left:5px solid {SPARK};}}
  .tile-v {{font-size:1.5rem; font-weight:800; color:{NAVY}; line-height:1.2;}}
  .tile-l {{color:{GREY}; font-size:.85rem;}}
  .q {{color:{NAVY}; font-size:1.15rem; font-weight:800; margin:28px 0 10px; display:flex; align-items:center; gap:10px;}}
  .q::before {{content:""; width:5px; height:1.1em; background:{SPARK}; border-radius:3px;}}
  .pill {{display:inline-block; padding:2px 10px; border-radius:999px; font-size:.8rem; font-weight:700; white-space:nowrap;}}
  .ev {{display:inline-flex; align-items:center; gap:3px; color:{NAVY}; font-size:.85rem; font-weight:700; white-space:nowrap;}}
  .ev i {{width:8px; height:8px; border-radius:50%; background:#C9D6F2; display:inline-block;}}
  .ev i.on {{background:{BLUE};}}
  .ev b {{margin-left:5px;}}
  .ev.none {{color:{GREY}; font-weight:600;}}
  .answer {{border-radius:12px; padding:14px 20px 12px; margin:4px 0 16px; border-left:5px solid {BLUE};}}
  .answer-h {{display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:6px;}}
  .answer-k {{color:{NAVY}; font-weight:800; font-size:.8rem; letter-spacing:.06em; text-transform:uppercase; margin-right:auto;}}
  .answer-b {{font-size:1.05rem; line-height:1.55; color:{INK};}}
  .answer-f {{color:{GREY}; font-size:.82rem; margin-top:8px;}}
  .card {{background:{LIGHT}; border-radius:10px; padding:12px 16px; margin-bottom:10px; border-left:4px solid #B8BEC6;}}
  .card-t {{color:{NAVY}; font-weight:800; margin-bottom:2px;}}
  .tag {{display:inline-block; color:{GREY}; font-size:.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.04em;
        margin-bottom:2px;}}
  .todo {{border:1px solid {LINE}; border-top:5px solid {SPARK}; border-radius:12px; padding:6px 18px 8px;}}
  .todo-i {{display:flex; gap:10px; padding:9px 0; border-bottom:1px solid {LINE}; font-size:.93rem; line-height:1.45;}}
  .todo-i:last-child {{border-bottom:none;}}
  .todo-i span {{flex:none; width:16px; height:16px; margin-top:3px; border:2px solid {BLUE}; border-radius:4px;}}
  .muted {{color:{GREY}; font-size:.88rem;}}
  .colh {{color:{GREY}; font-size:.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; padding:0 2px;}}
  .rank {{width:30px; height:30px; border-radius:8px; background:{LIGHT}; color:{NAVY}; font-weight:800; display:flex;
         align-items:center; justify-content:center; font-size:.9rem;}}
  .rank.top {{background:{SPARK};}}
  .row-t {{color:{NAVY}; font-weight:800;}}
  .big {{color:{NAVY}; font-weight:800; font-size:1.15rem; line-height:1.2;}}
  .quote {{border-left:3px solid {BLUE}; padding:2px 12px; margin:6px 0 12px; font-size:.92rem;}}
  div.stButton > button {{border-radius:999px;}}
  div.stButton > button[kind="primary"] {{background:{BLUE}; border-color:{BLUE};}}
  [class*="st-key-open_"] button {{color:{BLUE}; border-color:{BLUE}; font-weight:700;}}
  [class*="st-key-open_"] button:hover {{background:{BLUE}; color:#fff;}}
  [class*="st-key-row_"] {{transition:border-color .15s;}}
  [class*="st-key-row_"]:hover {{border-color:{BLUE} !important;}}
  .stTabs [data-baseweb="tab"] {{font-weight:700;}}
  @media (max-width:640px) {{ .st-key-colhead {{display:none;}} .topbar-r {{display:none;}} }}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------ helpers
def usd(x: float) -> str:
    return f"${x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"${x / 1000:,.1f}K" if abs(x) >= 1000 else f"${x:,.0f}"


def plain(t) -> str:
    """One team built this: saved answers that say 'ML team' are shown as 'ML model' (Santhosh, 2026-11-02)."""
    return str(t).replace("ML team", "ML model").replace("ML Team", "ML model")


def h(t) -> str:
    return html.escape(plain(t)).replace("$", "&#36;")


def md(t: str) -> str:
    return plain(t).replace("$", "\\$")


def pill(status: str) -> str:
    icon, fg, bg = STATUS.get(status, STATUS["Not run yet"])
    return f"<span class='pill' style='color:{fg};background:{bg}'>{icon} {h(status)}</span>"


def strength(found: str, suffix: str = "") -> str:
    """Evidence strength from the agent as three dots (Strong ●●●, Some ●●○, Little ●○○)."""
    n = LEVEL.get(found)
    if not n:
        return "<span class='ev none'>Not run yet</span>"
    dots = "".join(f"<i class='{'on' if i < n else ''}'></i>" for i in range(3))
    return f"<span class='ev'>{dots}<b>{h(found)}{h(suffix)}</b></span>"


def week(d) -> str:
    return pd.Timestamp(d).strftime("%b %-d, %Y")


def logo() -> str:
    """Official Walmart Spark (brandcenter.walmart.com), Spark Yellow on True Blue; never redrawn, not next to the wordmark."""
    f = APP / "assets" / "walmart_spark.svg"
    return f"<img src='data:image/svg+xml;base64,{base64.b64encode(f.read_bytes()).decode()}' alt='Walmart Spark'>" if f.exists() else ""


def section(text: str, where=st):
    where.markdown(f"<div class='q'>{h(text)}</div>", unsafe_allow_html=True)


def tiles(items: list[tuple[str, str]]):
    """First tile is the headline number (Spark Yellow edge)."""
    for i, (col, (v, l)) in enumerate(zip(st.columns(len(items)), items)):
        col.markdown(f"<div class='tile{' hero' if i == 0 else ''}'><div class='tile-v'>{h(v)}</div>"
                     f"<div class='tile-l'>{h(l)}</div></div>", unsafe_allow_html=True)


def go_to(case_id: str | None, live: bool = False):
    if case_id:
        st.query_params["case"] = case_id
    elif "case" in st.query_params:
        del st.query_params["case"]
    if live:
        st.session_state["live_now"] = case_id
    st.rerun()


# ------------------------------------------------------------------------------------------ data
def stamp() -> tuple:
    files = [P.OUT, P.LIVE] + (sorted(P.UPLOADS.glob("*.json")) if P.UPLOADS.exists() else [])
    return tuple((str(f), f.stat().st_mtime) for f in files if f.exists())


@st.cache_data(show_spinner=False)
def load(_stamp: tuple):
    runs = {k: v for k, v in P.outputs().items() if "findings" in v.get("report", {})}
    depts, cases, _ = P.tables()
    cases = cases.reset_index()
    cases["Net"] = cases.StoreExpected - cases.StoreActual           # the ML model's net modeled shortfall (their ranking)
    cases["Shown"] = cases.CaseID.map(lambda c: runs[c]["shown_status"] if c in runs else "Not run yet")
    cases["Found"] = cases.CaseID.map(lambda c: runs.get(c, {}).get("report", {}).get("evidence_found", ""))
    cases["RegionShort"] = cases.Region.map(lambda r: r.split(" (")[0])
    cases["Units"] = cases.CaseID.map(depts.groupby("CaseID").Unit.apply(lambda s: sorted(set(s))).to_dict())
    cases["Week"] = pd.to_datetime(cases.Date)
    return runs, depts, cases


@st.cache_resource(show_spinner="Getting the assistant ready…")
def warm_chat():
    from agents import chat_v3, retrievers
    retrievers.corpus("section")
    return chat_v3


runs, depts, cases = load(stamp())
st.session_state.setdefault("chat", {})
st.session_state.setdefault("page", 0)
st.session_state.setdefault("live_log", {})
cid = st.query_params.get("case")

st.markdown(f"<div class='topbar'>{logo()}<div class='topbar-t'>Store Sales Assistant</div>"
            f"<div class='topbar-r'>Sales data through Oct 26, 2012</div></div>", unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------ live run
def run_live(case_id: str) -> dict:
    """Run the agent's six steps on one case now, showing each step as it finishes."""
    log = []
    with st.status("The agent is working on this week…", expanded=True) as box:
        def say(msg):
            log.append(msg)
            box.write(msg)
        res = P.run_live(case_id, progress=say)
        if res.get("error"):
            box.update(label=f"The run did not finish: {res['error']}", state="error")
        else:
            box.update(label=f"Done in {res['seconds']:.0f} s · {res['shown_status']}", state="complete")
    st.session_state["live_log"][case_id] = dict(log=log, error=res.get("error"), seconds=res.get("seconds"))
    st.session_state["chat"].pop(case_id, None)
    st.cache_data.clear()
    return res


# ------------------------------------------------------------------------------------------ home
ROW = [0.45, 2.3, 2.4, 1.3, 1.3, 0.85]          # priority · store and week · biggest gap · below forecast · evidence · view


def home():
    st.markdown("<div class='title'>Flagged store-weeks</div>"
                "<div class='sub'>Weeks the ML model flagged, in its priority order. Open one to see what may explain it "
                "and what to check in the store.</div>", unsafe_allow_html=True)
    answered = cases[cases.CaseID.isin(runs)]
    tiles([(usd(cases.Net.sum()), "below the ML forecast across all flagged weeks (net, estimate)"),
           (str(len(cases)), f"store-weeks flagged · {cases.Store.nunique()} stores"),
           (str(len(answered)), "ready to review: the agent has found the evidence")])
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    shows = {"Ready to review": answered, "All flagged": cases}
    c = st.columns([1.9, 0.9, 1.3, 1.3, 1.5])
    show = c[0].segmented_control("Show", list(shows), default=list(shows)[0], key="show") or list(shows)[0]
    f_store = c[1].multiselect("Store", sorted(cases.Store.unique()), placeholder="All")
    f_region = c[2].multiselect("Region", sorted(cases.RegionShort.unique()), placeholder="All")
    f_week = c[3].multiselect("Week ending", [week(w) for w in sorted(cases.Week.unique())], placeholder="All")
    f_unit = c[4].multiselect("Category", sorted({u for us in cases.Units for u in us if u != "Unknown"}), placeholder="All")
    v = shows[show]
    if f_store: v = v[v.Store.isin(f_store)]
    if f_region: v = v[v.RegionShort.isin(f_region)]
    if f_week: v = v[v.Week.map(week).isin(f_week)]
    if f_unit: v = v[v.Units.map(lambda us: bool(set(us) & set(f_unit)))]
    v = v.sort_values("Rank")

    filters = (show, tuple(f_store), tuple(f_region), tuple(f_week), tuple(f_unit))
    if st.session_state.get("filters") != filters:                     # new filter -> back to page 1
        st.session_state["filters"], st.session_state["page"] = filters, 0
    per = 10
    pages = max(1, -(-len(v) // per))
    page = min(st.session_state["page"], pages - 1)

    st.markdown(f"<div class='muted' style='margin:14px 0 6px'><b>{len(v)}</b> store-weeks · "
                f"<b>{usd(v.Net.sum())}</b> below the ML forecast</div>", unsafe_allow_html=True)
    if v.empty:
        st.info("No flagged weeks match these filters.")
        return
    with st.container(key="colhead"):                                  # column headers once (hidden on phones)
        for col, label in zip(st.columns(ROW), ["#", "Store and week", "Biggest gap", "Below forecast", "Evidence", ""]):
            col.markdown(f"<div class='colh'>{label}</div>", unsafe_allow_html=True)
    for r in v.iloc[page * per:(page + 1) * per].itertuples():
        with st.container(border=True, key=f"row_{r.CaseID}"):
            a, b, c2, d, e, f = st.columns(ROW, vertical_alignment="center")
            a.markdown(f"<div class='rank{' top' if r.Rank <= 3 else ''}'>{r.Rank}</div>", unsafe_allow_html=True)
            b.markdown(f"<div class='row-t'>Store {r.Store} · {week(r.Week)}</div>"
                       f"<div class='muted'>{h(r.RegionShort)}</div>", unsafe_allow_html=True)
            c2.markdown(f"<div>{h(r.TopDept)}</div><div class='muted'>{r.FlaggedDepts} departments flagged</div>",
                        unsafe_allow_html=True)
            d.markdown(f"<div class='big'>{usd(r.Net)}</div>", unsafe_allow_html=True)
            e.markdown(strength(r.Found), unsafe_allow_html=True)
            if f.button("View", key=f"open_{r.CaseID}", width="stretch"):
                go_to(r.CaseID)
    if pages > 1:
        p1, p2, p3 = st.columns([1, 2, 1])
        if p1.button("← Previous", disabled=page == 0):
            st.session_state["page"] = page - 1
            st.rerun()
        p2.markdown(f"<div class='muted' style='text-align:center;padding-top:8px'>Page {page + 1} of {pages}</div>",
                    unsafe_allow_html=True)
        with p3:
            if st.button("Next →", disabled=page >= pages - 1, key="next"):
                st.session_state["page"] = page + 1
                st.rerun()


# ------------------------------------------------------------------------------------------ case page
def dept_bars(g: pd.DataFrame):
    g = g.sort_values("Shortfall").tail(8)
    labels = [f"{int(r.Dept)} {r.DeptName}" for r in g.itertuples()]
    colors = ["#99B9F2"] * (len(g) - 1) + [BLUE]                        # the biggest gap stands out
    fig = go.Figure(go.Bar(x=g.Shortfall, y=labels, orientation="h", marker=dict(color=colors, cornerradius=4),
                           text=[f"{usd(s)}  ({-p:+.0f}%)" for s, p in zip(g.Shortfall, g.ShortfallPct)], textposition="outside",
                           hovertemplate="%{y}: %{text} below the ML forecast<extra></extra>"))
    fig.update_layout(height=60 + 34 * len(g), margin=dict(l=0, r=10, t=6, b=6), plot_bgcolor="#fff", paper_bgcolor="#fff",
                      xaxis=dict(visible=False, range=[0, g.Shortfall.max() * 1.3]), yaxis=dict(tickfont=dict(size=13)), bargap=.35,
                      font=dict(color=INK))
    st.plotly_chart(fig, width="stretch", config=dict(displayModeBar=False))


def everywhere_chart(dept: int, date: str, store: int):
    p = support.dept_everywhere(dept, date, store).sort_values("Pct")
    me = support.lookups()[1].Region.get(store)
    colors = [NAVY if t else "#7FA3EE" if rg == me else "#D5DFF5" for t, rg in zip(p.This, p.Region)]
    x = [f"Store {int(s)}" for s in p.Store]
    fig = go.Figure(go.Bar(x=x, y=p.Pct.clip(-100, 100), marker=dict(color=colors), customdata=p.Region,
                           hovertemplate="%{x}: %{y:+.1f}% vs the ML forecast · %{customdata}<extra></extra>"))
    mine = p[p.This]
    if not mine.empty:                                                  # label this store's bar
        y = float(mine.Pct.clip(-100, 100).iloc[0])
        fig.add_annotation(x=f"Store {store}", y=y, text=f"<b>Store {store}</b>", showarrow=True, arrowhead=0,
                           ay=-28 if y >= 0 else 28, ax=0, font=dict(color=NAVY, size=12), yshift=0)
    fig.update_layout(height=280, margin=dict(l=0, r=0, t=24, b=24), plot_bgcolor="#fff", paper_bgcolor="#fff",
                      xaxis=dict(showticklabels=False), yaxis=dict(ticksuffix="%", gridcolor=LINE, zerolinecolor=GREY),
                      bargap=.2, font=dict(color=INK))
    st.plotly_chart(fig, width="stretch", config=dict(displayModeBar=False))


def header(r):
    if st.button("← All flagged weeks", key="back"):
        go_to(None)
    holiday = f" · {r.HolidayWeek} week" if isinstance(r.HolidayWeek, str) else ""
    st.markdown(f"<div class='title'>Store {r.Store} · week ending {week(r.Week)}</div>"
                f"<div class='sub'>{h(r.RegionShort)} · Walmart {h(r.FiscalPeriod)}{h(holiday)} · ML priority {r.Rank} of "
                f"{len(cases)}</div>", unsafe_allow_html=True)


def key_numbers(r, g: pd.DataFrame):
    top = g.iloc[0]
    tiles([(usd(r.Net), "below the ML forecast (net, estimate)"),
           (f"{r.FlaggedDepts} of {int(r.EligibleDepts)}", "departments flagged"),
           (f"{top.DeptName}", f"biggest gap: {usd(top.Shortfall)} ({-top.ShortfallPct:+.0f}%)")])


def answer_card(x: dict):
    """The agent's short answer, first thing on the page: ML status, evidence strength, summary, one-line caveat."""
    rep, shown = x["report"], x["shown_status"]
    _, fg, bg = STATUS.get(shown, STATUS["Needs analyst review"])
    edge = "#E8A33D" if x.get("needs_review") else BLUE
    note = ("This answer failed one of the agent's checks; read it with care." if x.get("needs_review")
            else "The ML model flagged this week. The agent looked for evidence that supports the flag; no cause is verified.")
    st.markdown(f"<div class='answer' style='background:{SKY if not x.get('needs_review') else bg};border-left-color:{edge}'>"
                f"<div class='answer-h'><span class='answer-k'>What the agent found</span>{pill(shown)}"
                f"{strength(rep['evidence_found'], ' evidence')}</div>"
                f"<div class='answer-b'>{h(rep['summary'])}</div><div class='answer-f'>{h(note)}</div></div>",
                unsafe_allow_html=True)


def why_and_checks(rep: dict):
    left, right = st.columns([1.65, 1], gap="large")
    section("Why it may have happened", left)
    for f in rep["findings"]:
        left.markdown(f"<div class='card' style='border-left-color:{EDGE.get(f['scope'], '#B8BEC6')}'>"
                      f"<div class='tag'>{h(TAG.get(f['scope'], f['scope']))}</div>"
                      f"<div class='card-t'>{h(f['title'])}</div>{h(f['text'])}</div>", unsafe_allow_html=True)
    section("What to check", right)
    right.markdown("<div class='todo'>" + "".join(f"<div class='todo-i'><span></span><div>{h(s)}</div></div>"
                                                 for s in rep["next_steps"]) + "</div>", unsafe_allow_html=True)


def where_the_gap_is(r, g: pd.DataFrame, x: dict | None):
    section("Where the gap is")
    t1, t2 = st.tabs(["By department", "Same department at other stores"])
    with t1:
        st.markdown("<div class='muted'>Biggest gaps this week, $ below the ML forecast</div>", unsafe_allow_html=True)
        dept_bars(g)
        with st.expander(f"All {len(g)} flagged departments"):
            st.dataframe(pd.DataFrame({"Department": [f"{int(d.Dept)} {d.DeptName}" for d in g.itertuples()], "Category": g.Unit,
                                       "Actual": g.Actual.map(usd), "ML forecast": g.Expected.map(usd),
                                       "Below forecast": g.Shortfall.map(usd), "%": g.ShortfallPct.map(lambda v: f"{-v:+.1f}%")}),
                         hide_index=True, width="stretch")
            st.caption("Numbers from the ML model's case file. Department names are publicly inferred.")
    with t2:
        date = g.Date.iloc[0]
        if not support.covered(date):
            st.caption("Store-by-store numbers are not available for this week.")
            return
        names = {int(d.Dept): f"{int(d.Dept)} {d.DeptName}" for d in g.itertuples()}
        dept = st.selectbox("Department", list(names), format_func=names.get)
        everywhere_chart(dept, date, int(r.Store))
        e = {k["id"]: k for k in (x or {}).get("evidence", [])}.get(f"dept_{dept}", {})
        more = f" {e['same_department_all_stores']}." if e.get("same_department_all_stores") else ""
        st.caption(f"Each bar is one store, this week vs the ML forecast. Dark = Store {r.Store}, mid blue = same region "
                   f"(publicly inferred).{more}")


def live_note(case_id: str):
    lg = st.session_state["live_log"].get(case_id)
    if not lg:
        return
    if lg["error"]:
        st.error(f"The live run did not finish ({lg['error']}). The saved answer is shown.")
    label = "Live run: did not finish" if lg["error"] else f"Live run: done in {lg['seconds']:.0f} s"
    with st.expander(label, expanded=False):
        for m in lg["log"]:
            st.markdown(f"- {md(m)}")


def how_it_was_found(case_id: str, x: dict):
    rep = x["report"]
    with st.expander("How the agent got this answer"):
        p, rg = x["plan"], x["rag"]
        st.markdown("**Searches it wrote**")
        st.markdown("\n".join(f"- {md(q['text'])}" for q in p["queries"]))
        cited = {e for f in rep["findings"] for e in f["evidence"]}
        used = [ps for ps in rg["passages"] if ps["id"] in cited]
        st.markdown(f"**Report passages used** ({len(used)} of {len(rg['passages'])} read; reports from "
                    f"{rg['filter']['start']} to {rg['filter']['end']})")
        for ps in used:
            link = f" · <a href='{h(ps['url'])}' target='_blank'>open</a>" if ps.get("url") else ""
            st.markdown(f"<b>{h(ps['source'])}</b> <span class='muted'>· {h(ps['district'])}{link}</span>"
                        f"<div class='quote'>{h(ps['text'][:500])}{'…' if len(ps['text']) > 500 else ''}</div>",
                        unsafe_allow_html=True)
        checks = x["evaluation"]["checks"]
        st.markdown(f"**Checks: {sum(k['passed'] for k in checks)} of {len(checks)} passed**")
        st.markdown("\n".join(f"- {'✅' if k['passed'] else '❌'} {md(k['name'])}" for k in checks))
        st.caption(f"Written by {x['llm']['model']} in {x['seconds']:.0f} s"
                   f"{' (live, ' + x['ran_at'] + ')' if x.get('ran_at') else ''}. The flag and status are the ML model's.")
        if st.button("▶ Run the agent again on this week", key="rerun",
                     help="Runs the six steps on this week now (about 30 seconds)."):
            go_to(case_id, live=True)


def case_page(case_id: str):
    r = cases.set_index("CaseID").loc[case_id].copy()
    r["CaseID"] = case_id
    x = runs.get(case_id)
    g = depts[depts.CaseID == case_id].sort_values("Shortfall", ascending=False)
    header(r)

    if st.session_state.get("live_now") == case_id:
        st.session_state["live_now"] = None
        run_live(case_id)
        st.rerun()
    live_note(case_id)

    if not x:
        with st.container(border=True):
            a, b = st.columns([3, 1.2], vertical_alignment="center")
            a.markdown("<b style='color:#001E60'>○ Not run yet.</b> The agent has not looked at this week. It takes about "
                       "30 seconds to find the evidence.", unsafe_allow_html=True)
            if b.button("▶ Find the evidence now", type="primary", width="stretch", key="run_first"):
                go_to(case_id, live=True)
        key_numbers(r, g)
        where_the_gap_is(r, g, None)
        return

    answer_card(x)
    key_numbers(r, g)
    why_and_checks(x["report"])
    where_the_gap_is(r, g, x)

    section("Ask a question")
    chat_box(case_id, x, g)
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    how_it_was_found(case_id, x)


def chat_box(case_id: str, x: dict, g: pd.DataFrame):
    hist = st.session_state["chat"].setdefault(case_id, [])
    top = g.iloc[0]
    ideas = [f"How did {top.DeptName} do at other stores?", "What did Walmart report that quarter?",
             "Was anything happening in the region?"]
    asked = st.pills("Suggested questions", ideas, key=f"ideas_{case_id}_{len(hist)}", label_visibility="collapsed")
    for m in hist:
        with st.chat_message(m["role"], avatar="🧑‍💼" if m["role"] == "user" else "💬"):
            st.markdown(md(m["text"]))
            if m.get("meta"):
                st.caption(m["meta"])
    with st.container():
        asked = st.chat_input("Ask about this store-week…") or asked
    if asked:
        hist.append(dict(role="user", text=asked))
        with st.spinner("Checking the sales data and reports…"):
            a = warm_chat().answer(x, asked, hist[:-1])
        if a.get("text"):
            srcs = ", ".join(sorted({f"{s['source']} ({s['date']})" for s in a["sources"]}))
            ok = "✓ checked against the data" if a["passed"] else "⚠ could not verify everything"
            hist.append(dict(role="assistant", text=a["text"], meta=ok + (f" · Sources: {srcs}" if srcs else "")))
        else:
            hist.append(dict(role="assistant", text=a["error"]))
        st.rerun()


if cid and cid in set(cases.CaseID):
    case_page(cid)
else:
    home()
