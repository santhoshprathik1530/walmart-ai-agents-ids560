"""Intake for the ML team's case files: v3.4 (data/cases_v34/, per-store MAD thresholds, current) or v3.3
(data/cases_v3/, kept for reference and uploads). 40 ranked store-weeks either way.

Rule (Santhosh, 2026-10-31): the ML team defines the exception. Which store-weeks and departments are flagged, the
thresholds, the priority order and the status ("Analyst review required") come straight from the ML files; nothing here
re-judges a flag. The agent's job is only to look for evidence that supports each flag (agents/support.py, the reports).

  load_cases()   -> the 40 JSON cases, ML rank order (v3.4 files are read into the v3.3 layout by from_v34)
  dept_rows()    -> one row per flagged department with the ML numbers and the ML team's own notes, plus our
                    (publicly inferred) department name / merchandise unit and the store's region, Fed district, quarter
  case_rows()    -> one row per case, from the ML numbers
  check_case()   -> what is missing from a case file before it can be used

Run `python3 -m agents.cases_v3` to write data/triage_v3_depts.csv and data/triage_v3_cases.csv.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
CASES = DATA / "cases_v34"          # switched from cases_v3 (v3.3) on 2026-10-30
STATUS = "Analyst review required"  # the ML files' business_action for every case

# The v3.3 files carried these rules and questions for the agent; v3.4 files do not, so the same ones are kept here.
GUARDRAILS = ["Do not claim markdown causality.", "Do not treat modeled shortfalls as verified revenue losses.",
              "Do not infer department-level markdown activity from store-level fields.",
              "Do not equate anomaly scores with probabilities.",
              "Distinguish actual observations, derived fields and model estimates.",
              "Do not fabricate historical comparisons or retrieved documents.", "No verified anomaly ground-truth labels."]
QUESTIONS = ["Which flagged departments have the largest modeled negative sales deviations?",
             "Do historical observations support or challenge these deviations?",
             "What markdown and external context is available?",
             "Which explanations require additional operational or external evidence?",
             "What is the safest next investigation step?"]


def load_cases() -> list[dict]:
    cases = [normalize(json.loads(p.read_text())) for p in CASES.glob("*.json")]
    return sorted(cases, key=lambda c: c["store_week"]["priority_rank"])


def normalize(c: dict) -> dict:
    return from_v34(c) if str(c.get("schema_version", "")).startswith("3.4") else c


def from_v34(c: dict) -> dict:
    """A v3.4 case in the v3.3 layout, with every number taken from the file as it is."""
    sw = c["store_week"]
    store = int(sw["store"])
    depts, total = [], sum(d["positive_modeled_gap"] for d in c["flagged_department_evidence"])
    for d in c["flagged_department_evidence"]:
        hc, pc, sig = d["historical_comparisons"], d["peer_comparison"], d["diagnostic_signals"]
        depts.append(dict(
            department_id=int(d["department"]), actual_weekly_sales=d["actual_sales"],
            expected_weekly_sales_extra_trees=d["expected_sales"], modeled_dollar_shortfall=d["positive_modeled_gap"],
            modeled_shortfall_percent=-d["relative_residual_pct"], per_store_threshold_pct=d["per_store_threshold_pct"],
            per_store_mad_flag=d["per_store_mad_flag"], global_mad_flag=d["global_mad_flag"],
            historical_validation=dict(
                recent_4_weeks=dict(observations=hc["recent_4_observations"], median_actual_sales=hc["recent_4_week_median"],
                                    current_actual_vs_median_pct=hc["actual_vs_recent_4wk_pct"]),
                recent_8_weeks=dict(observations=hc["recent_8_observations"], median_actual_sales=hc["recent_8_week_median"]),
                same_season_previous_years=dict(observations=hc["same_season_observations"],
                                                median_actual_sales=hc["same_season_prior_years_median"],
                                                current_actual_vs_seasonal_pct=hc["actual_vs_same_season_pct"])),
            cross_store_validation=dict(other_stores_compared=pc["peer_count"], overprediction_rate_pct=pc["peers_overpredicted_pct"]),
            diagnostic_signals=dict(recent_sales_decline_20pct=sig["recent_sales_decline"],
                                    prior_year_seasonal_decline_20pct=sig["seasonal_sales_decline"],
                                    possible_forecast_overprediction=sig["potential_forecast_overprediction"],
                                    widespread_cross_store_overprediction_70pct=sig["widespread_peer_overprediction"])))
    md = c["markdown_information"]
    return dict(
        schema_version="3.4 (read as 3.3)", source_schema=c["schema_version"], original_case_id=c["case_id"],
        case_id=f"Store_{store}_{sw['date']}",
        store_week=dict(store_id=store, date=sw["date"], store_type=sw["store_type"], priority_rank=int(c["priority_rank"])),
        anomaly_detection=c["anomaly_detection"],
        sales_evidence=dict(global_mad_flagged_departments=dict(count=len(depts), sum_positive_modeled_shortfalls=total,
                                                                 departments=depts),
                            eligible_department_aggregate=dict(expected_sales=sw["expected_eligible_sales"],
                                                               actual_sales=sw["actual_eligible_sales"],
                                                               net_modeled_shortfall=sw["aggregate_net_modeled_shortfall"],
                                                               eligible_departments=sw.get("eligible_departments"))),
        markdown_context=dict(markdown_recorded=md["markdown_recorded"], recorded_markdown_total=md["recorded_markdown_total"],
                              recorded_markdown_count=sum(v is not None for v in md["markdown_fields"].values()),
                              markdown_fields=md["markdown_fields"], interpretation=md.get("note", "")),
        rag_investigation=dict(retrieved_documents=[], questions_for_agent=QUESTIONS,
                               guardrails=GUARDRAILS + [c["root_cause_assessment"].get("caution", "")][:1]),
        root_cause_assessment=c["root_cause_assessment"])


@lru_cache(maxsize=1)
def lookups():
    dm = pd.read_csv(DATA / "dept_mapping.csv").rename(columns={
        "Inferred Name": "DeptName", "Walmart Merchandise Unit (FY2013 10-K)": "Unit", "Confidence": "DeptConf",
        "Peak Month": "PeakMonth"})
    sm = pd.read_csv(DATA / "store_mapping.csv").rename(columns={
        "Region (EIA fuel series)": "Region", "Fed Beige Book District": "District", "Size (sq ft)": "Size",
        "Possible States": "States"})
    cal = pd.read_csv(DATA / "fiscal_calendar.csv").rename(columns={
        "Week Ending": "Date", "Fiscal Period": "FiscalPeriod", "Holiday Week": "HolidayWeek",
        "Earnings Release for this Quarter": "EarningsRelease", "Walmart U.S. Comp Sales (reported)": "ReportedComp"})
    return (dm.set_index("Dept")[["DeptName", "Unit", "DeptConf", "PeakMonth"]],
            sm.set_index("Store")[["Region", "States", "District", "Type", "Size"]],
            cal.set_index("Date")[["FiscalPeriod", "HolidayWeek", "EarningsRelease", "ReportedComp"]])


_SIGNALS = {"recent_sales_decline_20pct": "recent decline", "prior_year_seasonal_decline_20pct": "seasonal decline",
            "possible_forecast_overprediction": "forecast may be too high",
            "widespread_cross_store_overprediction_70pct": "model too high at most stores"}


def dept_rows(cases: list[dict]) -> pd.DataFrame:
    dm, sm, cal = lookups()
    rows = []
    for c in cases:
        sw = c["store_week"]
        flagged = c["sales_evidence"]["global_mad_flagged_departments"]
        for d in flagged["departments"]:
            hv, cs, sig = d["historical_validation"], d["cross_store_validation"], d["diagnostic_signals"]
            ss = hv["same_season_previous_years"]
            rows.append({
                "CaseID": c["case_id"], "Rank": sw["priority_rank"], "Store": sw["store_id"], "Date": sw["date"],
                "ThresholdPct": d.get("per_store_threshold_pct", float("nan")),
                "Dept": d["department_id"], "Actual": d["actual_weekly_sales"],
                "Expected": d["expected_weekly_sales_extra_trees"], "Shortfall": d["modeled_dollar_shortfall"],
                "ShortfallPct": d["modeled_shortfall_percent"],
                "Recent4Median": hv["recent_4_weeks"]["median_actual_sales"],
                "VsRecent4Pct": hv["recent_4_weeks"]["current_actual_vs_median_pct"],
                "SeasonMedian": ss["median_actual_sales"], "VsSeasonPct": ss["current_actual_vs_seasonal_pct"],
                "ChainOverpredPct": cs["overprediction_rate_pct"],
                "MLNotes": ", ".join(n for k, n in _SIGNALS.items() if sig.get(k)) or "none",
                "MLAction": c.get("root_cause_assessment", {}).get("business_action")
                or c.get("rag_investigation", {}).get("recommended_action_status", ""),
            })
    df = pd.DataFrame(rows)
    return df.join(dm, on="Dept").join(sm, on="Store").join(cal, on="Date")


def case_rows(depts: pd.DataFrame, cases: list[dict]) -> pd.DataFrame:
    agg = {c["case_id"]: c["sales_evidence"]["eligible_department_aggregate"] for c in cases}
    out = []
    for cid, g in depts.groupby("CaseID", sort=False):
        top, a = g.sort_values("Shortfall", ascending=False).iloc[0], agg[cid]
        out.append({
            "CaseID": cid, "Rank": g.Rank.iloc[0], "Store": g.Store.iloc[0], "Date": g.Date.iloc[0], "Type": g.Type.iloc[0],
            "ThresholdPct": g.ThresholdPct.iloc[0], "Region": g.Region.iloc[0], "District": g.District.iloc[0],
            "FiscalPeriod": g.FiscalPeriod.iloc[0], "HolidayWeek": g.HolidayWeek.iloc[0],
            "EligibleDepts": a.get("eligible_departments"), "StoreActual": a["actual_sales"], "StoreExpected": a["expected_sales"],
            "FlaggedDepts": len(g), "FlaggedShortfall": g.Shortfall.sum(), "TopDept": f"{top.Dept} {top.DeptName}",
            "Status": STATUS, "MLAction": g.MLAction.iloc[0],
        })
    return pd.DataFrame(out).sort_values("Rank").reset_index(drop=True)


def check_case(c) -> list[str]:
    """Problems that stop a file from being used as a v3.3 or v3.4 case (empty list = fine)."""
    if not isinstance(c, dict):
        return ["the file is not a JSON object"]
    if str(c.get("schema_version", "")).startswith("3.4"):
        miss = [k for k in ("case_id", "priority_rank", "store_week", "anomaly_detection", "markdown_information",
                            "flagged_department_evidence", "root_cause_assessment") if k not in c]
        if miss:
            return [f"missing '{k}'" for k in miss]
        try:
            c = from_v34(c)
        except (KeyError, TypeError, ValueError) as e:
            return [f"v3.4 file could not be read ({type(e).__name__}: {e})"]
    probs = [f"missing '{k}'" for k in ("case_id", "store_week", "sales_evidence", "markdown_context", "rag_investigation")
             if k not in c]
    if probs:
        return probs
    sw = c["store_week"]
    probs += [f"store_week has no '{k}'" for k in ("store_id", "date", "priority_rank") if k not in sw]
    deps = c["sales_evidence"].get("global_mad_flagged_departments", {}).get("departments")
    if not deps:
        probs.append("no flagged departments in sales_evidence.global_mad_flagged_departments")
    if not probs:
        _, sm, cal = lookups()
        if sw["store_id"] not in sm.index:
            probs.append(f"Store {sw['store_id']} is not one of the 45 stores in the sales data")
        if sw["date"] not in cal.index:
            probs.append(f"week ending {sw['date']} is not a Friday week-ending in the sales data (2010-02-05 to 2012-10-26)")
    return probs


if __name__ == "__main__":
    cs = load_cases()
    d = dept_rows(cs)
    c = case_rows(d, cs)
    d.to_csv(DATA / "triage_v3_depts.csv", index=False)
    c.to_csv(DATA / "triage_v3_cases.csv", index=False)
    (DATA / "triage_v3_peers.csv").unlink(missing_ok=True)     # our own similar-store table: removed 2026-10-31
    print(f"{len(cs)} cases, {len(d)} flagged departments; status: {c.Status.value_counts().to_dict()}")
