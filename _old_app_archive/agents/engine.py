"""Data layer, payload intake and the Evidence Agent.

  load_data() / build()          -> Kaggle sales data + public mapping tables, joined into a store x dept x week panel
  payload_from_handoff()         -> any anomaly payload format -> one internal payload
  CHECKS / run_checks()          -> Evidence Agent: a menu of pandas checks; the orchestrator picks which ones run
  evidence_facts()               -> the results as labelled facts for the Reasoning Agent and the evaluation
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
WINDOW_START = pd.Timestamp("2011-11-11")   # markdown data begins
WINDOW_END = pd.Timestamp("2012-10-26")     # last sales week
LAG = pd.Timedelta(weeks=52)                # same week last year (Walmart weeks run Sat-Fri)

EASTER = {2010: "2010-04-04", 2011: "2011-04-24", 2012: "2012-04-08"}
DISCRETIONARY = {"Entertainment", "Apparel", "Home", "Hardlines"}

UNIT_TERMS = {
    "Entertainment": ["entertainment", "electronic", "deflation", "media", "toys", "gaming", "televisions", "digital imaging"],
    "Grocery": ["grocery", "food", "consumables"],
    "Health & Wellness": ["health and wellness", "pharmacy"],
    "Apparel": ["apparel", "clothing", "menswear"],
    "Home": ["home", "furnishings"],
    "Hardlines": ["hardlines", "seasonal"],
}

TAG = {
    "data": "Data",
    "map": "Mapping",
    "wmt": "Walmart",
    "reg": "Regional/Macro",
}


# --------------------------------------------------------------------------- data
def load_data():
    tr = pd.read_csv(DATA / "train.csv", parse_dates=["Date"])
    ft = pd.read_csv(DATA / "features.csv", parse_dates=["Date"])
    st = pd.read_csv(DATA / "stores.csv")
    dm = pd.read_csv(DATA / "dept_mapping.csv")
    sm = pd.read_csv(DATA / "store_mapping.csv")
    sm = sm.loc[:, ~sm.columns.str.startswith("Unnamed")]
    cal = pd.read_csv(DATA / "fiscal_calendar.csv", parse_dates=["Week Ending", "Quarter Ends"])

    md_cols = [f"MarkDown{i}" for i in range(1, 6)]
    ft["MarkDown_Total"] = ft[md_cols].fillna(0).sum(axis=1)
    ft["MarkDown_Recorded"] = ft[md_cols].notna().any(axis=1)

    dm = dm.rename(columns={"Inferred Name": "DeptName", "Walmart Merchandise Unit (FY2013 10-K)": "Unit",
                            "Confidence": "DeptConf", "Peak Month": "PeakMonth",
                            "Peak Month Index (1 = avg)": "PeakIdx"})
    sm = sm.rename(columns={"Region (EIA fuel series)": "Region", "Region Confidence": "RegionConf",
                            "Fed Beige Book District": "District", "District Confidence": "DistrictConf",
                            "Likely Format (10-K)": "Format"})
    cal = cal.rename(columns={"Week Ending": "Date", "Fiscal Period": "FiscalPeriod"})
    return tr, ft, st, dm, sm, cal


@dataclass
class Data:
    tr: pd.DataFrame
    ft: pd.DataFrame
    st: pd.DataFrame
    dm: pd.DataFrame
    sm: pd.DataFrame
    cal: pd.DataFrame
    panel: pd.DataFrame        # store x dept x week with expected sales
    store_week: pd.DataFrame   # store x week totals


def build(tr, ft, st, dm, sm, cal) -> Data:
    # store-week totals and recent store trend (prior 8 weeks, year over year)
    sw = tr.groupby(["Store", "Date"], as_index=False).Weekly_Sales.sum().rename(columns={"Weekly_Sales": "StoreSales"})
    sw_ly = sw.assign(Date=sw.Date + LAG).rename(columns={"StoreSales": "StoreSales_LY"})
    sw = sw.merge(sw_ly, on=["Store", "Date"], how="left").sort_values(["Store", "Date"])
    roll_c = sw.groupby("Store").StoreSales.transform(lambda s: s.shift(1).rolling(8, min_periods=4).sum())
    roll_l = sw.groupby("Store").StoreSales_LY.transform(lambda s: s.shift(1).rolling(8, min_periods=4).sum())
    sw["StoreTrend"] = (roll_c / roll_l - 1).clip(-0.15, 0.15).fillna(0)
    sw["StoreYoY"] = sw.StoreSales / sw.StoreSales_LY - 1

    p = tr.merge(tr.assign(Date=tr.Date + LAG)[["Store", "Dept", "Date", "Weekly_Sales"]]
                 .rename(columns={"Weekly_Sales": "Sales_LY"}), on=["Store", "Dept", "Date"], how="left")
    p = p.merge(sw[["Store", "Date", "StoreSales", "StoreYoY", "StoreTrend"]], on=["Store", "Date"], how="left")
    p["Expected"] = p.Sales_LY * (1 + p.StoreTrend)
    p["Deviation"] = p.Weekly_Sales / p.Expected - 1
    p["Shortfall"] = p.Expected - p.Weekly_Sales
    p = p.merge(ft[["Store", "Date", "MarkDown_Total", "MarkDown_Recorded", "Temperature", "Fuel_Price", "CPI", "Unemployment"]],
                on=["Store", "Date"], how="left")
    p = p.merge(dm[["Dept", "DeptName", "Unit", "DeptConf"]], on="Dept", how="left")
    p = p.merge(sm[["Store", "Region", "RegionConf", "District", "DistrictConf", "Type", "Format"]], on="Store", how="left")
    p = p.merge(cal[["Date", "FiscalPeriod"]], on="Date", how="left")
    return Data(tr, ft, st, dm, sm, cal, p, sw)


# --------------------------------------------------------------------------- detection
def detect_exceptions(d: Data, threshold=-0.15, min_expected=5000, min_shortfall=2000) -> pd.DataFrame:
    p = d.panel
    m = (
        (p.Date >= WINDOW_START) & (p.Date <= WINDOW_END)
        & p.Sales_LY.notna() & (p.Expected >= min_expected)
        & (p.Deviation <= threshold) & (p.Shortfall >= min_shortfall)
        & (p.MarkDown_Total > 0)
        & (p.DeptConf != "Unresolved")
    )
    ex = p[m].copy()
    ex["CalendarShift"] = calendar_shift_mask(ex.Date)
    ex["Priority"] = np.where((ex.Shortfall >= 10000) & (ex.Deviation <= -0.25), "High", "Medium")
    ex["ExceptionID"] = ("EXC_S" + ex.Store.astype(str).str.zfill(2) + "_D" + ex.Dept.astype(str).str.zfill(2)
                         + "_" + ex.Date.dt.strftime("%Y%m%d"))
    return ex.sort_values("Shortfall", ascending=False).reset_index(drop=True)


def payload(row: pd.Series) -> dict:
    """The JSON handed from the anomaly-detection layer to the agents."""
    return {
        "exception_id": row.ExceptionID,
        "store": int(row.Store), "region": row.Region, "region_confidence": row.RegionConf,
        "fed_district": row.District, "store_format": row.Format,
        "dept": int(row.Dept), "dept_name": row.DeptName, "dept_confidence": row.DeptConf, "merch_unit": row.Unit,
        "week_ending": row.Date.strftime("%Y-%m-%d"), "fiscal_period": row.FiscalPeriod,
        "actual_sales": round(float(row.Weekly_Sales), 2), "expected_sales": round(float(row.Expected), 2),
        "deviation_pct": round(float(row.Deviation) * 100, 1), "shortfall": round(float(row.Shortfall), 2),
        "store_markdown_total": round(float(row.MarkDown_Total), 2),
        "expected_method": "Same week last year x recent 8-week store trend",
    }


# --------------------------------------------------------------------------- calendar
def _contains(week_end, day):
    return week_end - pd.Timedelta(days=6) <= day <= week_end


def calendar_flags(w):
    """Shopping events that fall in this week but not in the same week last year (or vice versa)."""
    flags, ly = [], w - LAG
    for name, getter in [("Easter", lambda y: pd.Timestamp(EASTER.get(y, "1900-01-01"))),
                         ("Christmas Eve", lambda y: pd.Timestamp(f"{y}-12-24"))]:
        for lead in (0, 7):  # the event week and the week before it
            a = _contains(w + pd.Timedelta(days=lead), getter(w.year))
            b = _contains(ly + pd.Timedelta(days=lead), getter(ly.year))
            if a != b:
                flags.append(f"{name} timing differs from last year")
                break
    return flags


def calendar_shift_mask(dates: pd.Series) -> pd.Series:
    return dates.map(lambda d: bool(calendar_flags(d)))


# --------------------------------------------------------------------------- evidence agent: menu of checks
# The orchestrator (an LLM) picks checks from this menu by id and the Evidence Agent runs only those. Every check is a fixed
# pandas computation; its parameters (store, department, week, fiscal quarter, region) come from the payload.
CHECKS = {
    "department_week": {
        "store_wide": "Is the whole store down that week, or only this department?",
        "persistence": "One bad week, or below last year for most of the quarter?",
        "regional_peers": "How did the same department do at other stores in the same region?",
        "chain": "How did the same department do across all 45 stores?",
        "promo_macro": "Were markdowns, fuel prices or weather unusual that week?",
        "calendar": "Did a holiday (Easter, Christmas) fall in a different week than last year?",
    },
    "store_week": {
        "baseline": "What is in the 4-week baseline? Does it include Christmas week?",
        "last_year": "How does the week compare with the same week last year, and would last year's week have been flagged too?",
        "all_stores": "Did all 45 stores drop against their own 4-week baseline that week?",
        "next_weeks": "Did the store recover in the next 4 weeks?",
        "departments": "Which departments drove the shortfall, and do they peak in November-December?",
        "promo_macro": "Were markdowns, fuel prices or weather unusual that week?",
    },
}


def menu(pl: dict) -> dict:
    return CHECKS["store_week" if pl.get("grain") == "store_week" else "department_week"]


def _quarter_rows(d: Data, period):
    weeks = d.cal.loc[d.cal.FiscalPeriod == period, "Date"]
    return weeks.min(), weeks.max()


def _yoy(df, cur="Weekly_Sales", ly="Sales_LY"):
    return df[cur].sum() / df[ly].sum() - 1 if len(df) and df[ly].sum() else np.nan


# department x week ----------------------------------------------------------------------------------------------
def _dept_ctx(d: Data, pl: dict) -> dict:
    p, s, dept = d.panel, pl["store"], pl["dept"]
    w = pd.Timestamp(pl["week_ending"])
    q0, q1 = _quarter_rows(d, pl["fiscal_period"])
    q0 = max(q0, w - pd.Timedelta(weeks=12))
    return dict(p=p, s=s, dept=dept, w=w, q0=q0, q1=q1, row=p[(p.Store == s) & (p.Dept == dept) & (p.Date == w)].iloc[0])


def _dept_base(d, pl, c):
    p, row = c["p"], c["row"]
    expected = float(pl.get("expected_sales", row.Expected))
    trend = p[(p.Store == c["s"]) & (p.Dept == c["dept"]) & (p.Date >= c["w"] - pd.Timedelta(weeks=26)) & (p.Date <= c["w"] + pd.Timedelta(weeks=8))]
    return {"actual": float(row.Weekly_Sales), "last_year": float(row.Sales_LY), "expected": expected,
            "deviation": float(row.Weekly_Sales) / expected - 1, "store_trend": float(row.StoreTrend),
            "quarter_window": (c["q0"], c["q1"]), "trend": trend[["Date", "Weekly_Sales", "Expected", "Sales_LY"]]}


def _d_store_wide(d, pl, c):
    sw = d.store_week
    store_q = sw[(sw.Store == c["s"]) & (sw.Date >= c["q0"]) & (sw.Date <= c["q1"]) & sw.StoreSales_LY.notna()]
    return {"store_week_yoy": float(c["row"].StoreYoY), "store_quarter_yoy": float(_yoy(store_q, "StoreSales", "StoreSales_LY"))}


def _d_persistence(d, pl, c):
    p = c["p"]
    qd = p[(p.Store == c["s"]) & (p.Dept == c["dept"]) & (p.Date >= c["q0"]) & (p.Date <= c["q1"]) & p.Sales_LY.notna()]
    return {"dept_quarter_yoy": float(_yoy(qd)), "weeks_down": int((qd.Weekly_Sales < qd.Sales_LY).sum()), "weeks_total": int(len(qd))}


def _d_regional_peers(d, pl, c):
    p = c["p"]
    peers = p[(p.Dept == c["dept"]) & (p.Date == c["w"]) & (p.Region == pl["region"]) & (p.Store != c["s"])
              & (p.Sales_LY > 1000)].assign(YoY=lambda x: x.Weekly_Sales / x.Sales_LY - 1)
    pq = p[(p.Dept == c["dept"]) & (p.Date >= c["q0"]) & (p.Date <= c["q1"]) & (p.Region == pl["region"]) & (p.Store != c["s"])
           & p.Sales_LY.notna()]
    peers_q = (pq.groupby("Store")[["Weekly_Sales", "Sales_LY"]].sum().query("Sales_LY > 5000")
               .assign(YoY=lambda x: x.Weekly_Sales / x.Sales_LY - 1).reset_index().sort_values("YoY"))
    return {"peers": peers[["Store", "Weekly_Sales", "Sales_LY", "YoY"]], "peers_q": peers_q,
            "peer_median_yoy": float(peers.YoY.median()) if len(peers) else np.nan}


def _d_chain(d, pl, c):
    p = c["p"]
    cq = p[(p.Dept == c["dept"]) & (p.Date >= c["q0"]) & (p.Date <= c["q1"]) & p.Sales_LY.notna()]
    chain = p[(p.Dept == c["dept"]) & (p.Date == c["w"]) & (p.Sales_LY > 1000)]
    return {"chain_week_yoy": float(_yoy(chain)), "chain_dept_quarter_yoy": float(_yoy(cq))}


def _promo_macro(d, pl, c=None):
    s, w = pl["store"], pd.Timestamp(pl["week_ending"])
    ft = d.ft[d.ft.Store == s].set_index("Date")
    cur, ly = ft.loc[w], (ft.loc[w - LAG] if (w - LAG) in ft.index else None)
    md_prior = ft.loc[w - pd.Timedelta(weeks=4):w - pd.Timedelta(weeks=1), "MarkDown_Total"]
    return {"markdown": float(cur.MarkDown_Total), "markdown_avg": float(ft.loc[WINDOW_START:WINDOW_END, "MarkDown_Total"].mean()),
            "markdown_prior_avg": float(md_prior.mean()),
            "fuel": float(cur.Fuel_Price), "fuel_ly": float(ly.Fuel_Price) if ly is not None else np.nan,
            "temp": float(cur.Temperature), "temp_ly": float(ly.Temperature) if ly is not None else np.nan,
            "cpi": float(cur.CPI), "unemp": float(cur.Unemployment)}


def _d_calendar(d, pl, c):
    p, w = c["p"], c["w"]
    flags = calendar_flags(w)
    if bool(d.ft[(d.ft.Store == c["s"]) & (d.ft.Date == w)].IsHoliday.iloc[0]):
        flags.insert(0, "Holiday week")
    # 6 weeks around the flagged week vs. the same 6 weeks last year
    sea = p[(p.Store == c["s"]) & (p.Dept == c["dept"]) & (p.Date >= w - pd.Timedelta(weeks=4)) & (p.Date <= w + pd.Timedelta(weeks=1))
            & p.Sales_LY.notna()]
    return {"calendar_flags": flags, "season_yoy": float(_yoy(sea)) if len(sea) >= 4 else np.nan,
            "season_window": (w - pd.Timedelta(weeks=4), w + pd.Timedelta(weeks=1))}


# store x week ---------------------------------------------------------------------------------------------------
def _store_ctx(d: Data, pl: dict) -> dict:
    s, w = pl["store"], pd.Timestamp(pl["week_ending"])
    mine = d.store_week[d.store_week.Store == s].set_index("Date").StoreSales
    return dict(s=s, w=w, mine=mine, prior=mine[mine.index < w], ly=w - LAG)


def _store_base(d, pl, c):
    mine, w = c["mine"], c["w"]
    return {"actual": float(mine[w]), "expected": float(pl["expected_sales"]), "deviation": float(mine[w]) / float(pl["expected_sales"]) - 1,
            "trend": mine[w - pd.Timedelta(weeks=12):w + pd.Timedelta(weeks=8)]}


def _s_baseline(d, pl, c):
    s, prior = c["s"], c["prior"]
    base = prior.tail(4)
    holidays = [HOLIDAY_NAMES[e.month] for e in base.index
                if bool(d.ft[(d.ft.Store == s) & (d.ft.Date == e)].IsHoliday.iloc[0]) and e.month in HOLIDAY_NAMES]
    christmas = any(_contains(e, pd.Timestamp(f"{e.year}-12-24")) or _contains(e, pd.Timestamp(f"{e.year}-12-25")) for e in base.index)
    return {"baseline_weeks": base, "baseline_avg": float(base.mean()), "typical_week": float(prior.tail(52).median()),
            "baseline_peak": float(base.max()), "baseline_peak_date": base.idxmax(), "baseline_holidays": holidays,
            "christmas_in_baseline": christmas,
            "calendar_flags": ["Post-holiday week: the 4-week baseline includes Christmas"] if christmas else []}


def _s_last_year(d, pl, c):
    mine, w, ly = c["mine"], c["w"], c["ly"]
    ly_sales = float(mine[ly]) if ly in mine.index else np.nan
    ly_base = mine[mine.index < ly].tail(4).mean() if ly in mine.index else np.nan
    return {"last_year": ly_sales, "yoy": float(mine[w]) / ly_sales - 1 if ly_sales == ly_sales else np.nan,
            "last_year_deviation": ly_sales / ly_base - 1 if ly_sales == ly_sales else np.nan,
            "trend_ly": mine[w - pd.Timedelta(weeks=12) - LAG:w + pd.Timedelta(weeks=8) - LAG]}


def _s_all_stores(d, pl, c):
    w, ly = c["w"], c["ly"]
    wide = d.store_week.pivot(index="Date", columns="Store", values="StoreSales")
    drops = wide.loc[w] / wide[wide.index < w].tail(4).mean() - 1
    return {"chain_median_drop": float(drops.median()), "chain_drops": drops, "store_rank": int(drops.rank()[c["s"]]),
            "n_stores": int(drops.notna().sum()),
            "chain_yoy": float(wide.loc[w].sum() / wide.loc[ly].sum() - 1) if ly in wide.index else np.nan}


def _s_next_weeks(d, pl, c):
    mine, w = c["mine"], c["w"]
    nxt = [w + pd.Timedelta(weeks=i) for i in range(1, 5)]
    nxt = [x for x in nxt if x in mine.index and (x - LAG) in mine.index]
    return {"next_weeks_yoy": float(sum(mine[x] for x in nxt) / sum(mine[x - LAG] for x in nxt) - 1) if nxt else np.nan,
            "n_next_weeks": len(nxt)}


def _s_departments(d, pl, c):
    p = d.panel
    pw = p[(p.Store == c["s"]) & (p.Date == c["w"])].set_index("Dept")

    def enrich(x):
        ly_d = float(pw.Sales_LY.get(x["dept"], np.nan))
        peak = x["peak_month"] in (11, 12) and x["peak_idx"] >= 1.5
        return {**x, "last_year": ly_d, "yoy": x["actual"] / ly_d - 1 if ly_d == ly_d and ly_d else np.nan, "holiday_peak": peak}

    top = [enrich(x) for x in pl["top_depts"]]
    tot = sum(x["shortfall"] for x in top)
    peak = sum(x["shortfall"] for x in top if x["holiday_peak"])
    ly_top = sum(x["last_year"] for x in top)
    return {"top": top, "buffers": [enrich(x) for x in pl["buffer_depts"]], "top_total": tot,
            "peak_share": peak / tot if tot else np.nan,
            "top_yoy": float(sum(x["actual"] for x in top) / ly_top - 1) if ly_top else np.nan}


_RUN = {
    "department_week": (_dept_ctx, _dept_base, {"store_wide": _d_store_wide, "persistence": _d_persistence,
                                                "regional_peers": _d_regional_peers, "chain": _d_chain,
                                                "promo_macro": _promo_macro, "calendar": _d_calendar}),
    "store_week": (_store_ctx, _store_base, {"baseline": _s_baseline, "last_year": _s_last_year, "all_stores": _s_all_stores,
                                             "next_weeks": _s_next_weeks, "departments": _s_departments,
                                             "promo_macro": _promo_macro}),
}


def run_checks(d: Data, pl: dict, checks: list[str]) -> dict:
    """Evidence Agent: run the selected checks (ids from menu(pl)) and return one evidence dict."""
    ctx_fn, base_fn, fns = _RUN["store_week" if pl.get("grain") == "store_week" else "department_week"]
    c = ctx_fn(d, pl)
    ev = base_fn(d, pl, c)
    ev["checks_run"] = []
    for cid in checks:
        if cid in fns and cid not in ev["checks_run"]:
            ev.update(fns[cid](d, pl, c))
            ev["checks_run"].append(cid)
    return ev


def ensure_checks(d: Data, pl: dict, ev: dict, checks: list[str]) -> list[str]:
    """Run checks that are not in `ev` yet (used by follow-up questions). Returns the ids that were newly run."""
    missing = [c for c in checks if c not in ev.get("checks_run", [])]
    if missing:
        extra = run_checks(d, pl, missing)
        ev.update({k: v for k, v in extra.items() if k != "checks_run"})
        ev.setdefault("checks_run", []).extend(missing)
    return missing


def evidence_facts(pl: dict, ev: dict) -> list[dict]:
    """The evidence as labelled facts (id, check, label, value text). This is what the Reasoning Agent reads and what the
    evaluation checks numbers against."""
    out, ran = [], ev.get("checks_run", [])

    def add(check, fid, label, value):
        if check in ran:
            out.append(dict(id=fid, check=check, label=label, value=value))

    def x(v):
        return "n/a" if v != v else f"{v:.1f}×"

    if "promo_macro" in ran:
        mdx = ev["markdown"] / ev["markdown_avg"] if ev["markdown_avg"] else np.nan
        fuel_chg = ev["fuel"] / ev["fuel_ly"] - 1 if ev["fuel_ly"] == ev["fuel_ly"] else np.nan
        add("promo_macro", "markdown_ratio", "Store markdowns that week vs. the store's average week",
            f"{x(mdx)} ({money(ev['markdown'])} vs. {money(ev['markdown_avg'])})")
        add("promo_macro", "fuel", "Fuel price vs. same week last year", f"${ev['fuel']:.2f} vs. ${ev['fuel_ly']:.2f} ({pct(fuel_chg)})")
        add("promo_macro", "temperature", "Temperature vs. same week last year", f"{ev['temp']:.0f}°F vs. {ev['temp_ly']:.0f}°F")

    if pl.get("grain") == "store_week":
        if "baseline" in ran:
            b = ev["baseline_weeks"]
            add("baseline", "baseline_avg", "Expected sales = average of the 4 weeks before",
                f"{money(ev['baseline_avg'])} (weeks ending {b.index.min():%b %-d} to {b.index.max():%b %-d})")
            add("baseline", "christmas_in_baseline", "Those 4 weeks include Christmas week", "yes" if ev["christmas_in_baseline"] else "no")
            add("baseline", "baseline_peak", "Highest of the 4 baseline weeks",
                f"{money(ev['baseline_peak'])}, {ev['baseline_peak'] / ev['typical_week']:.1f}× a typical week ({money(ev['typical_week'])})")
        if "last_year" in ran:
            add("last_year", "yoy", "This week vs. the same week last year", f"{pct(ev['yoy'])} ({money(ev['actual'])} vs. {money(ev['last_year'])})")
            add("last_year", "last_year_deviation", "The same 4-week method applied to last year's week", pct(ev["last_year_deviation"]))
        if "all_stores" in ran:
            add("all_stores", "chain_median_drop", f"Median of all {ev['n_stores']} stores vs. their own 4-week baseline", pct(ev["chain_median_drop"]))
            add("all_stores", "store_rank", "This store's rank among all stores (1 = worst drop)", f"{ev['store_rank']} of {ev['n_stores']}")
            diff = (ev["deviation"] - ev["chain_median_drop"]) * 100
            add("all_stores", "store_vs_median", "This store's drop compared with the median store's drop",
                f"{abs(diff):.1f} percentage points {'more' if diff < 0 else 'less'} than the median store "
                f"({pct(ev['deviation'])} vs. {pct(ev['chain_median_drop'])})")
            add("all_stores", "chain_yoy", "All stores together, this week vs. last year", pct(ev["chain_yoy"]))
        if "next_weeks" in ran:
            add("next_weeks", "next_weeks_yoy", f"Next {ev['n_next_weeks']} weeks vs. the same weeks last year", pct(ev["next_weeks_yoy"]))
        if "departments" in ran:
            add("departments", "top_departments", "Departments with the biggest shortfalls",
                "; ".join(f"{t['dept_name']} (Dept {t['dept']}): {money(t['actual'])} vs. {money(t['expected'])} expected, "
                          f"{pct(t['yoy'])} vs. last year{', peaks in Nov-Dec' if t['holiday_peak'] else ''}" for t in ev["top"]))
            add("departments", "peak_share", "Share of that shortfall from departments that peak in Nov-Dec", pct(ev["peak_share"], False))
            add("departments", "top_yoy", "Those departments together vs. the same week last year", pct(ev["top_yoy"]))
        return out

    name = pl["dept_name"]
    if "store_wide" in ran:
        add("store_wide", "store_week_yoy", f"Whole Store {pl['store']}, this week vs. the same week last year", pct(ev["store_week_yoy"]))
        add("store_wide", "store_quarter_yoy", f"Whole Store {pl['store']}, this quarter vs. last year", pct(ev["store_quarter_yoy"]))
    if "persistence" in ran:
        add("persistence", "dept_quarter_yoy", f"{name} at this store, this quarter vs. last year", pct(ev["dept_quarter_yoy"]))
        add("persistence", "weeks_down", f"Weeks {name} at this store was below last year this quarter",
            f"{ev['weeks_down']} of {ev['weeks_total']}")
    if "regional_peers" in ran:
        region = re.sub(r"\s*\(PADD.*\)", "", pl["region"])
        pq = ev["peers_q"]
        add("regional_peers", "peers_quarter", f"{name} at other {region} stores, this quarter vs. last year",
            "; ".join(f"Store {int(r.Store)} {pct(r.YoY)}" for r in pq.itertuples()) or "no comparable stores")
        pw = ev["peers"].sort_values("YoY")
        add("regional_peers", "peers_week", f"{name} at those stores, this week vs. last year",
            "; ".join(f"Store {int(r.Store)} {pct(r.YoY)}" for r in pw.itertuples()) or "no comparable stores")
    if "chain" in ran:
        add("chain", "chain_dept_quarter_yoy", f"{name} across all 45 stores, this quarter vs. last year", pct(ev["chain_dept_quarter_yoy"]))
        add("chain", "chain_week_yoy", f"{name} across all 45 stores, this week vs. last year", pct(ev["chain_week_yoy"]))
        if "dept_quarter_yoy" in ev:
            gap = (ev["dept_quarter_yoy"] - ev["chain_dept_quarter_yoy"]) * 100
            add("chain", "store_vs_chain", "This store minus the chain, this quarter", f"{gap:+.1f} percentage points".replace("-", "−"))
    if "calendar" in ran:
        add("calendar", "calendar_flags", "Holiday or holiday shift vs. last year", "; ".join(ev["calendar_flags"]) or "none")
        add("calendar", "season_yoy", f"{name}, the 6 weeks around this week vs. last year", pct(ev["season_yoy"]))
    return out


# --------------------------------------------------------------------------- payload intake
# The anomaly team sends two formats. Both are turned into the same internal payload so the agents can run on either.
#   department_week : Extra Trees hand-off (store x department x week), "record_type": "forecast_exception_ai_rag_handoff"
#   store_week      : primary anomaly payload (store x week, 4-week moving average + Isolation Forest)
#   internal        : an already-normalized payload (used for the baseline-detected Store 13 case)
HOLIDAY_NAMES = {2: "Super Bowl", 9: "Labor Day", 11: "Thanksgiving", 12: "Christmas"}


def payload_kind(raw: dict) -> str:
    if "grain" in raw and "week_ending" in raw:
        return "internal"
    if "quantitative_exception" in raw and "metadata" in raw:
        return "store_week"
    if "case" in raw and "sales" in raw:
        return "department_week"
    raise ValueError("Unrecognized payload format: expected the Extra Trees hand-off or the primary anomaly payload")


def load_handoff(source) -> dict:
    """Read an anomaly-team payload from a file path or an already-loaded dict."""
    return source if isinstance(source, dict) else json.loads(Path(source).read_text())


def payload_from_handoff(d: Data, raw: dict) -> dict:
    """Any supported anomaly payload -> the internal payload the agents use."""
    kind = payload_kind(raw)
    if kind == "internal":
        return raw
    return payload_from_extra_trees(d, raw) if kind == "department_week" else payload_from_store_week(d, raw)


def payload_from_extra_trees(d: Data, raw: dict) -> dict:
    c, s = raw["case"], raw["sales"]
    w = pd.Timestamp(c["week_start_date"])
    p = d.panel
    row = p[(p.Store == c["store_id"]) & (p.Dept == c["department_id"]) & (p.Date == w)].iloc[0].copy()
    exp = s["expected_sales"]
    row["Expected"], row["Deviation"], row["Shortfall"] = exp, row.Weekly_Sales / exp - 1, exp - row.Weekly_Sales
    row["ExceptionID"] = raw["exception_id"]
    pl = payload(row)
    pl["grain"] = "department_week"
    pl["expected_method"] = f"{raw['detector']['model']} (anomaly detection team)"
    return pl


def payload_from_store_week(d: Data, raw: dict) -> dict:
    m, q = raw["metadata"], raw["quantitative_exception"]
    pr, mac = raw["promotional_allocation"], raw["internal_macro_features"]
    s, w = m["store_id"], pd.Timestamp(m["date"])
    st = d.sm.set_index("Store").loc[s]
    dm = d.dm.set_index("Dept")

    def dept(r, buffer=False):
        info = dm.loc[r["dept_id"]]
        gap = -r["dept_surplus"] if buffer else r["dept_shortfall"]
        return {"dept": int(r["dept_id"]), "dept_name": info.DeptName, "unit": info.Unit, "conf": info.DeptConf,
                "actual": r["actual_sales"], "expected": r["expected_sales"], "shortfall": gap,
                "share_pct": abs(r["pct_of_store_shortfall"]), "peak_month": int(info.PeakMonth),
                "peak_idx": float(info.PeakIdx)}

    top = [dept(r) for r in raw["top_shortfall_departments"]]
    buf = [dept(r, True) for r in raw.get("top_buffer_departments", [])]
    fiscal = d.cal.set_index("Date").FiscalPeriod.get(w, m.get("fiscal_period"))
    return {
        "grain": "store_week", "exception_id": raw.get("metadata", {}).get("exception_id", f"EXC_STORE{s:02d}_{w:%Y%m%d}"),
        "store": int(s), "region": st.Region, "region_confidence": st.RegionConf, "fed_district": st.District,
        "store_format": st.Format, "store_type": m.get("store_type"), "size_sqft": m.get("size_sq_ft"),
        "dept_name": "All departments", "week_ending": w.strftime("%Y-%m-%d"), "fiscal_period": fiscal,
        "actual_sales": round(q["actual_weekly_sales"], 2), "expected_sales": round(q["expected_baseline_4wk_ma"], 2),
        "deviation_pct": round(q["sales_deviation_pct"], 1), "shortfall": round(q["sales_shortfall_dollars"], 2),
        "store_markdown_total": round(pr["total_markdown_spend"], 2), "markdown_channels": pr["channel_breakdown"],
        "expected_method": "4-week trailing average (anomaly detection team)",
        "detector": {"method": m.get("detection_method"), "structural_slump": q.get("structural_slump_flag"),
                     "isolation_forest": q.get("isolation_forest_anomaly"),
                     "reading": mac.get("macro_shock_rule_out")},
        "top_depts": top, "buffer_depts": buf, "units": sorted({x["unit"] for x in top}),
    }


# --------------------------------------------------------------------------- reasoning agent
def pct(x, signed=True):
    if x != x:
        return "n/a"
    s = f"{x*100:+.1f}%" if signed else f"{x*100:.1f}%"
    return s.replace("-", "\u2212")


def money(x):
    return f"${x/1000:,.1f}K" if abs(x) < 1e6 else f"${x/1e6:,.2f}M"




# --------------------------------------------------------------------------- evidence agent: follow-up lookups
def store_lookup(d: Data, pl: dict, store: int) -> dict | None:
    """Follow-up tool: how did another store do on the same department / week? (answers 'How did Store 41 do?')"""
    p, w = d.panel, pd.Timestamp(pl["week_ending"])
    if store == pl["store"] or store not in d.sm.Store.values:
        return None
    sm = d.sm.set_index("Store").loc[store]
    if pl.get("grain") == "store_week":
        sw = d.store_week
        row = sw[(sw.Store == store) & (sw.Date == w)]
        if row.empty:
            return None
        base = sw[(sw.Store == store) & (sw.Date < w)].tail(4).StoreSales.mean()
        r = row.iloc[0]
        return {"store": store, "region": sm.Region, "what": "whole store", "actual": float(r.StoreSales),
                "vs_baseline": float(r.StoreSales / base - 1), "yoy": float(r.StoreYoY) if r.StoreYoY == r.StoreYoY else np.nan}
    q0, q1 = _quarter_rows(d, pl["fiscal_period"])
    q0 = max(q0, w - pd.Timedelta(weeks=12))
    x = p[(p.Store == store) & (p.Dept == pl["dept"]) & (p.Date >= q0) & (p.Date <= q1) & p.Sales_LY.notna()]
    wk = p[(p.Store == store) & (p.Dept == pl["dept"]) & (p.Date == w)]
    if x.empty or wk.empty:
        return None
    r = wk.iloc[0]
    return {"store": store, "region": sm.Region, "what": pl["dept_name"], "actual": float(r.Weekly_Sales),
            "week_yoy": float(r.Weekly_Sales / r.Sales_LY - 1) if r.Sales_LY == r.Sales_LY and r.Sales_LY else np.nan,
            "quarter_yoy": float(x.Weekly_Sales.sum() / x.Sales_LY.sum() - 1), "weeks_down": int((x.Weekly_Sales < x.Sales_LY).sum()),
            "weeks_total": int(len(x))}


# --------------------------------------------------------------------------- orchestrator signals
def signals(d: Data, pl: dict) -> dict:
    """Cheap context the orchestrator computes up front so the RAG Agent can start at the same time as the Evidence Agent."""
    s, w = pl["store"], pd.Timestamp(pl["week_ending"])
    ft = d.ft[d.ft.Store == s].set_index("Date")
    cur, ly = ft.loc[w], (ft.loc[w - LAG] if (w - LAG) in ft.index else None)
    flags = calendar_flags(w)
    if bool(cur.IsHoliday):
        flags.insert(0, "Holiday week")
    if pl.get("grain") == "store_week":
        base = [w - pd.Timedelta(weeks=i) for i in range(1, 5)]
        if any(_contains(e, pd.Timestamp(f"{e.year}-12-24")) or _contains(e, pd.Timestamp(f"{e.year}-12-25")) for e in base):
            flags.append("Post-holiday week: the 4-week baseline includes Christmas")
    return {"calendar_flags": flags, "fuel": float(cur.Fuel_Price), "fuel_ly": float(ly.Fuel_Price) if ly is not None else np.nan,
            "temp": float(cur.Temperature), "temp_ly": float(ly.Temperature) if ly is not None else np.nan}
