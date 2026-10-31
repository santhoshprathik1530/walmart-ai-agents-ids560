"""Data layer, payload intake and the Evidence Agent.

  load_data() / build()          -> Kaggle sales data + public mapping tables, joined into a store x dept x week panel
  payload_from_handoff()         -> any anomaly payload format -> one internal payload
  evidence_agent[_store]()       -> pandas checks on the sales data (what happened, vs. last year, peers, chain)
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


# --------------------------------------------------------------------------- evidence agent
def _quarter_rows(d: Data, period):
    weeks = d.cal.loc[d.cal.FiscalPeriod == period, "Date"]
    return weeks.min(), weeks.max()


def evidence_agent(d: Data, pl: dict) -> dict:
    p, s, dept = d.panel, pl["store"], pl["dept"]
    w = pd.Timestamp(pl["week_ending"])
    row = p[(p.Store == s) & (p.Dept == dept) & (p.Date == w)].iloc[0]
    q0, q1 = _quarter_rows(d, pl["fiscal_period"])
    q0 = max(q0, w - pd.Timedelta(weeks=12))
    q = p[(p.Store == s) & (p.Date >= q0) & (p.Date <= q1) & p.Sales_LY.notna()]
    qd = q[q.Dept == dept]
    dept_q_yoy = qd.Weekly_Sales.sum() / qd.Sales_LY.sum() - 1 if len(qd) else np.nan
    weeks_down = int((qd.Weekly_Sales < qd.Sales_LY).sum())
    store_q = d.store_week[(d.store_week.Store == s) & (d.store_week.Date >= q0) & (d.store_week.Date <= q1)
                           & d.store_week.StoreSales_LY.notna()]
    store_q_yoy = store_q.StoreSales.sum() / store_q.StoreSales_LY.sum() - 1

    units = (q.groupby("Unit")[["Weekly_Sales", "Sales_LY"]].sum()
             .assign(YoY=lambda x: x.Weekly_Sales / x.Sales_LY - 1)["YoY"].dropna().to_dict())
    sib = q[(q.Unit == pl["merch_unit"]) & (q.Dept != dept) & (q.DeptConf == "High")]
    siblings = (sib.groupby(["Dept", "DeptName"])[["Weekly_Sales", "Sales_LY"]].sum()
                .query("Sales_LY > 20000").assign(YoY=lambda x: x.Weekly_Sales / x.Sales_LY - 1)
                .reset_index().sort_values("YoY").head(4))

    peers = p[(p.Dept == dept) & (p.Date == w) & (p.Region == pl["region"]) & (p.Store != s)
              & (p.Sales_LY > 1000)].assign(YoY=lambda x: x.Weekly_Sales / x.Sales_LY - 1)
    cq = p[(p.Dept == dept) & (p.Date >= q0) & (p.Date <= q1) & p.Sales_LY.notna()]
    chain_q_yoy = cq.Weekly_Sales.sum() / cq.Sales_LY.sum() - 1
    pq = p[(p.Dept == dept) & (p.Date >= q0) & (p.Date <= q1) & (p.Region == pl["region"]) & (p.Store != s) & p.Sales_LY.notna()]
    peers_q = (pq.groupby("Store")[["Weekly_Sales", "Sales_LY"]].sum().query("Sales_LY > 5000")
               .assign(YoY=lambda x: x.Weekly_Sales / x.Sales_LY - 1).reset_index().sort_values("YoY"))
    chain = p[(p.Dept == dept) & (p.Date == w) & (p.Sales_LY > 1000)]
    chain_yoy = chain.Weekly_Sales.sum() / chain.Sales_LY.sum() - 1

    ft = d.ft[d.ft.Store == s].set_index("Date")
    cur, ly = ft.loc[w], ft.loc[w - LAG] if (w - LAG) in ft.index else None
    md_avg = ft.loc[WINDOW_START:WINDOW_END, "MarkDown_Total"].mean()

    cal_flags = calendar_flags(w)
    if bool(cur.IsHoliday):
        cal_flags.insert(0, "Holiday week")

    # holiday-season comparison: 6 weeks around the flagged week vs. the same 6 weeks last year
    sea = p[(p.Store == s) & (p.Dept == dept) & (p.Date >= w - pd.Timedelta(weeks=4))
            & (p.Date <= w + pd.Timedelta(weeks=1)) & p.Sales_LY.notna()]
    season_yoy = sea.Weekly_Sales.sum() / sea.Sales_LY.sum() - 1 if len(sea) >= 4 else np.nan

    trend = p[(p.Store == s) & (p.Dept == dept) & (p.Date >= w - pd.Timedelta(weeks=26)) & (p.Date <= w + pd.Timedelta(weeks=8))]

    expected = float(pl.get("expected_sales", row.Expected))
    return {
        "actual": float(row.Weekly_Sales), "last_year": float(row.Sales_LY), "expected": expected,
        "deviation": float(row.Weekly_Sales) / expected - 1, "store_trend": float(row.StoreTrend),
        "store_week_yoy": float(row.StoreYoY), "dept_quarter_yoy": float(dept_q_yoy),
        "store_quarter_yoy": float(store_q_yoy), "weeks_down": weeks_down, "weeks_total": int(len(qd)),
        "unit_yoy": units, "siblings": siblings, "peers": peers[["Store", "Weekly_Sales", "Sales_LY", "YoY"]], "peers_q": peers_q,
        "peer_median_yoy": float(peers.YoY.median()) if len(peers) else np.nan, "chain_week_yoy": float(chain_yoy),
        "chain_dept_quarter_yoy": float(chain_q_yoy),
        "markdown": float(cur.MarkDown_Total), "markdown_avg": float(md_avg),
        "fuel": float(cur.Fuel_Price), "fuel_ly": float(ly.Fuel_Price) if ly is not None else np.nan,
        "temp": float(cur.Temperature), "temp_ly": float(ly.Temperature) if ly is not None else np.nan,
        "cpi": float(cur.CPI), "unemp": float(cur.Unemployment),
        "calendar_flags": cal_flags, "trend": trend[["Date", "Weekly_Sales", "Expected", "Sales_LY"]],
        "quarter_window": (q0, q1), "season_yoy": float(season_yoy),
        "season_window": (w - pd.Timedelta(weeks=4), w + pd.Timedelta(weeks=1)),
    }


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


# --------------------------------------------------------------------------- evidence agent (store-level payloads)
def evidence_agent_store(d: Data, pl: dict) -> dict:
    s, w = pl["store"], pd.Timestamp(pl["week_ending"])
    sw = d.store_week
    mine = sw[sw.Store == s].set_index("Date").StoreSales
    prior, ly = mine[mine.index < w], w - LAG
    base = prior.tail(4)
    typical = float(prior.tail(52).median())

    base_holidays = [HOLIDAY_NAMES[e.month] for e in base.index
                     if bool(d.ft[(d.ft.Store == s) & (d.ft.Date == e)].IsHoliday.iloc[0]) and e.month in HOLIDAY_NAMES]
    christmas_in_base = any(_contains(e, pd.Timestamp(f"{e.year}-12-24")) or _contains(e, pd.Timestamp(f"{e.year}-12-25"))
                            for e in base.index)

    ly_sales = float(mine[ly]) if ly in mine.index else np.nan
    ly_base = mine[mine.index < ly].tail(4).mean() if ly in mine.index else np.nan
    ly_dev = ly_sales / ly_base - 1 if ly_sales == ly_sales else np.nan

    wide = sw.pivot(index="Date", columns="Store", values="StoreSales")
    drops = wide.loc[w] / wide[wide.index < w].tail(4).mean() - 1
    chain_yoy = wide.loc[w].sum() / wide.loc[ly].sum() - 1 if ly in wide.index else np.nan

    nxt = [w + pd.Timedelta(weeks=i) for i in range(1, 5)]
    nxt = [x for x in nxt if x in mine.index and (x - LAG) in mine.index]
    next_yoy = sum(mine[x] for x in nxt) / sum(mine[x - LAG] for x in nxt) - 1 if nxt else np.nan

    p = d.panel
    pw = p[(p.Store == s) & (p.Date == w)].set_index("Dept")

    def enrich(x):
        ly_d = float(pw.Sales_LY.get(x["dept"], np.nan))
        peak = x["peak_month"] in (11, 12) and x["peak_idx"] >= 1.5
        return {**x, "last_year": ly_d, "yoy": x["actual"] / ly_d - 1 if ly_d == ly_d and ly_d else np.nan, "holiday_peak": peak}

    top = [enrich(x) for x in pl["top_depts"]]
    buf = [enrich(x) for x in pl["buffer_depts"]]
    tot_short = sum(x["shortfall"] for x in top)
    peak_short = sum(x["shortfall"] for x in top if x["holiday_peak"])
    ly_top = sum(x["last_year"] for x in top)
    top_yoy = sum(x["actual"] for x in top) / ly_top - 1 if ly_top else np.nan

    ft = d.ft[d.ft.Store == s].set_index("Date")
    cur = ft.loc[w]
    lyr = ft.loc[ly] if ly in ft.index else None
    md_avg = ft.loc[WINDOW_START:WINDOW_END, "MarkDown_Total"].mean()
    md_prior = ft.loc[w - pd.Timedelta(weeks=4):w - pd.Timedelta(weeks=1), "MarkDown_Total"]
    flags = []
    if christmas_in_base:
        flags.append("Post-holiday week: the 4-week baseline includes Christmas")
    return {
        "actual": float(mine[w]), "expected": float(pl["expected_sales"]), "deviation": float(mine[w]) / float(pl["expected_sales"]) - 1,
        "baseline_weeks": base, "baseline_avg": float(base.mean()), "typical_week": typical,
        "baseline_peak": float(base.max()), "baseline_peak_date": base.idxmax(), "baseline_holidays": base_holidays,
        "christmas_in_baseline": christmas_in_base,
        "last_year": ly_sales, "yoy": float(mine[w]) / ly_sales - 1 if ly_sales == ly_sales else np.nan, "last_year_deviation": ly_dev,
        "chain_median_drop": float(drops.median()), "chain_drops": drops, "store_rank": int(drops.rank()[s]),
        "n_stores": int(drops.notna().sum()), "chain_yoy": float(chain_yoy), "next_weeks_yoy": float(next_yoy),
        "n_next_weeks": len(nxt), "top": top, "buffers": buf, "top_total": tot_short,
        "peak_share": peak_short / tot_short if tot_short else np.nan, "top_yoy": float(top_yoy),
        "markdown": float(cur.MarkDown_Total), "markdown_avg": float(md_avg), "markdown_prior_avg": float(md_prior.mean()),
        "fuel": float(cur.Fuel_Price), "fuel_ly": float(lyr.Fuel_Price) if lyr is not None else np.nan,
        "temp": float(cur.Temperature), "temp_ly": float(lyr.Temperature) if lyr is not None else np.nan,
        "cpi": float(cur.CPI), "unemp": float(cur.Unemployment), "calendar_flags": flags,
        "trend": mine[w - pd.Timedelta(weeks=12):w + pd.Timedelta(weeks=8)],
        "trend_ly": mine[w - pd.Timedelta(weeks=12) - LAG:w + pd.Timedelta(weeks=8) - LAG],
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
