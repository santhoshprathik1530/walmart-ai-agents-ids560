"""Reasoning Agent: turns the evidence and the retrieved passages into a verdict, confidence and possible factors.

Strategy: RULES decide (so the result is testable and every claim traces to a number or a quote); an LLM, when an API key
is available, only rewrites the explanation in plain language and may not add facts (numbers and quotes are checked).

  1. Is it just timing?  holiday moved / baseline holds a holiday peak AND flat vs. last year AND other stores dropped too
                         -> "Likely explained"
  2. Otherwise weigh     category trend (Walmart) | store-specific gap vs. chain and peers | promotions | regional demand
                         -> "Needs review"
  3. Confidence          starts at High and drops for: single-week drop, department / region not High confidence,
                         no time-aligned report, part of the drop left unexplained
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import llm
from .engine import DISCRETIONARY, EASTER, UNIT_TERMS, money, pct


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"

TAG = {"data": "Data", "map": "Mapping", "wmt": "Walmart", "reg": "Regional/Macro"}


def _factor(title, text, kind="factor", tags=()):
    return dict(title=title, text=text, kind=kind, tags=list(tags))


def _q(h):
    """A passage's verbatim quote, ready to embed in text."""
    return f"“{h['quote'].strip()}”"


def _src(h):
    return f"{h['doc']}, {h['published']}"


def _unit_hit(h, terms):
    low = h["quote"].lower()
    return sum(t in low for t in terms)


def _pick(passages, kind, terms=(), prefer_local=None):
    pool = [h for h in passages if h["evidence_type"].startswith("Walmart") == (kind == "walmart")]
    if not pool:
        return None
    return sorted(pool, key=lambda h: (prefer_local is not None and h["district"] != prefer_local, -_unit_hit(h, terms), -h["score"]))[0]


def _confidence(pl, ev, passages, persistent=True, calendar=False, gap=0.0):
    score, limits = 3, []
    if pl.get("dept_confidence", "High") != "High":
        score -= 1
        limits.append(f"Department name is {pl['dept_confidence'].lower()} confidence (publicly inferred).")
    else:
        limits.append("Department and region names are publicly inferred, not confirmed by Walmart.")
    if pl.get("region_confidence", "High") != "High":
        score -= 1
    if not persistent:
        score -= 1
        limits.append("Single-week drop; may be noise rather than a trend.")
    if calendar:
        score -= 1
    if not passages:
        score -= 1
        limits.append("No time-aligned report passages found for this quarter and region.")
    if gap < -0.05:
        score -= 1
        limits.append("The store fell much more than the chain, and public reports only describe company-wide trends, so part of the drop is unexplained.")
    limits += ["No unit or price data, so price deflation and lost volume cannot be separated.",
               "Markdowns are recorded per store, not per department.", "Reports describe Walmart or the Fed district as a whole, not this store."]
    return {3: "High", 2: "Medium"}.get(score, "Low"), limits


# ------------------------------------------------------------------------------------------ department-week payloads
def reason_department(pl: dict, ev: dict, passages: list[dict]) -> dict:
    name, unit, s = pl["dept_name"], pl["merch_unit"], pl["store"]
    w = pd.Timestamp(pl["week_ending"])
    terms = UNIT_TERMS.get(unit, []) + [name.lower().split()[0]]
    factors, claims = [], []
    store_wide = ev["store_week_yoy"] < -0.05
    persistent = ev["weeks_total"] >= 6 and ev["weeks_down"] / ev["weeks_total"] >= 0.6
    gap = ev["dept_quarter_yoy"] - ev["chain_dept_quarter_yoy"]
    md_x = ev["markdown"] / ev["markdown_avg"] if ev["markdown_avg"] else np.nan
    fuel_chg = ev["fuel"] / ev["fuel_ly"] - 1 if ev["fuel_ly"] == ev["fuel_ly"] else np.nan
    temp_d = ev["temp"] - ev["temp_ly"] if ev["temp_ly"] == ev["temp_ly"] else 0
    wal = _pick(passages, "walmart", terms)
    reg = _pick(passages, "regional", ["back-to-school", "consumer", "retail"], prefer_local=pl["fed_district"])
    shifts = [f for f in ev["calendar_flags"] if "timing" in f]
    sy = ev.get("season_yoy", np.nan)
    explained_by_timing = bool(shifts) and sy == sy and sy > -0.10
    region_short = re.sub(r"\s*\(PADD.*\)", "", pl["region"])

    claims += [dict(id="dept_q_yoy", value=ev["dept_quarter_yoy"]), dict(id="weeks_down", value=ev["weeks_down"]),
               dict(id="chain_dept_q_yoy", value=ev["chain_dept_quarter_yoy"]), dict(id="store_week_yoy", value=ev["store_week_yoy"])]

    if explained_by_timing:
        verdict = "Likely explained: holiday timing"
        event = shifts[0].split(" timing")[0]
        wal = _pick(passages, "walmart", [event.lower(), "holiday", "timing"]) or wal
        d1, d0 = pd.Timestamp(EASTER[w.year]), pd.Timestamp(EASTER[w.year - 1])
        weeks = round(abs((d1 - d0).days - 364) / 7) if event == "Easter" else 0
        direction = "earlier" if (d1.dayofyear < d0.dayofyear) else "later"
        text = (f"**Calendar:** {event} was {d1:%b %-d} in {w.year} vs. {d0:%b %-d} in {w.year - 1}, so this week is compared with last year's "
                f"pre-{event} rush.")
        if wal:
            text += f" **Walmart reports:** {_q(wal)} ({_src(wal)})."
        factors.append(_factor(f"{event} moved {direction}", text, tags=["Calendar", "Walmart"]))
        tr = ev["trend"].dropna(subset=["Sales_LY"])
        tr = tr[(tr.Date >= w - pd.Timedelta(weeks=4)) & (tr.Date <= w + pd.Timedelta(weeks=1)) & (tr.Date != w)]
        best = tr.assign(r=tr.Weekly_Sales / tr.Sales_LY).sort_values("r").iloc[-1] if len(tr) else None
        if best is not None and best.r > 1.5:
            factors.append(_factor("Sales happened earlier, not lost",
                f"**Sales data:** the week ending {best.Date:%b %-d, %Y} sold {money(best.Weekly_Sales)} vs. {money(best.Sales_LY)} the same week last year. "
                f"Over the six weeks around {event}, {name} was only {pct(sy)}.", tags=["Data"]))
        peers = ev["peers"].sort_values("YoY")
        near = ", ".join(f"{int(r.Store)} ({pct(r.YoY, True).replace('+', '+')})" for r in peers.head(2).itertuples())
        factors.append(_factor("Every store saw the same dip",
            f"**Sales data:** {name} across all 45 stores was {pct(ev['chain_week_yoy'])} that week"
            + (f"; nearby stores {near} dropped too." if near else "."), tags=["Data"]))
        ruled = (f"A problem at this store: {name} is {pct(ev['dept_quarter_yoy'])} this quarter, and markdowns were active "
                 f"(about {md_x:.1f}× a normal week).")
        factors.append(_factor("Ruled out", ruled, kind="ruled_out"))
        conf = "High" if sy > -0.05 else "Medium"
        limits = ["A small decline may remain after adjusting for timing; check it if it persists.",
                  "Department and region names are publicly inferred, not confirmed by Walmart."]
        weeks_txt = {1: "one week", 2: "two weeks"}.get(weeks, f"{weeks} weeks")
        bottom = (f"Likely not a real problem. The {event} peak moved {weeks_txt} {direction}, so the sales happened in an earlier week. "
                  f"No store action needed.")
        review = ["No action needed for this week; compare the full holiday season instead of single weeks.",
                  "Ask the detection team to add a holiday-aligned baseline so these weeks are not flagged."]
        status = "Likely explained"
        claims.append(dict(id="season_yoy", value=sy))
    else:
        verdict, status = "Needs review", "Needs review"
        # 1. company-wide / category trend
        if wal and _unit_hit(wal, terms):
            qlow = wal["quote"].lower()
            title = f"Falling {name.lower()} prices" if "deflation" in qlow or "price" in qlow else f"Weak {unit.lower()} trend company-wide"
            factors.append(_factor(title,
                f"**Walmart reports:** {_q(wal)} ({_src(wal)}). Across all 45 stores, {name} was {pct(ev['chain_dept_quarter_yoy'])} this quarter, "
                f"so company-wide trends explain only part of this store's {pct(ev['dept_quarter_yoy'])}.", tags=["Walmart", "Data"]))
        # 2. store-specific
        pq = ev["peers_q"]
        peers_txt = ", ".join(f"Store {int(r.Store)} {pct(r.YoY)}" for r in pq.sort_values("YoY").itertuples())
        if store_wide:
            factors.append(_factor("Store-wide weakness", f"**Sales data:** the whole store was {pct(ev['store_week_yoy'])} vs. last year.", tags=["Data"]))
        elif gap < -0.05:
            factors.append(_factor("A problem at this store",
                f"**Sales data:** Store {s} {name} fell {pct(ev['dept_quarter_yoy'])} this quarter (down {ev['weeks_down']} of {ev['weeks_total']} weeks)"
                + (f", while other {region_short} stores held up much better: {peers_txt}." if len(pq) else ".")
                + " Likely the store itself: stock, product range or local competition.", tags=["Data"]))
        elif persistent:
            factors.append(_factor("Persistent pattern",
                f"**Sales data:** {name} was below last year in {ev['weeks_down']} of {ev['weeks_total']} weeks this quarter "
                f"({pct(ev['dept_quarter_yoy'])} vs. store {pct(ev['store_quarter_yoy'])}).", tags=["Data"]))
        else:
            factors.append(_factor("Mostly one-off",
                f"**Sales data:** {name} was below last year in only {ev['weeks_down']} of {ev['weeks_total']} weeks this quarter.", tags=["Data"]))
        # 3. promotions (+ regional demand)
        bts = reg is not None and w.month in (7, 8, 9) and "back-to-school" in reg["quote"].lower()
        if md_x < 0.8:
            t = f"Fewer promotions{' during back-to-school' if bts else ''}"
            text = f"**Sales data:** Store {s} ran fewer markdowns than usual that week (about {md_x:.1f}× a normal week)"
            text += (f", while the **{reg['publisher']}** reported {_q(reg)} ({reg['district']})." if reg else ".")
            factors.append(_factor(t, text, tags=["Data", "Regional"]))
        else:
            factors.append(_factor("Markdowns did not offset",
                f"**Sales data:** store markdowns of {money(ev['markdown'])} were active ({md_x:.1f}× the store's average week) but did not close the gap.",
                tags=["Data"]))
        # ruled out
        out = []
        if not ev["calendar_flags"]:
            out.append("no holiday that week")
        if fuel_chg == fuel_chg and abs(fuel_chg) < 0.08:
            out.append(f"fuel prices barely changed ({pct(fuel_chg)})")
        if abs(temp_d) < 8:
            out.append("normal weather")
        if not store_wide:
            out.append(f"the rest of the store was only {pct(ev['store_week_yoy'])}")
        if out:
            joined = out[0] if len(out) == 1 else ", ".join(out[:-1]) + ", and " + out[-1]
            factors.append(_factor("Ruled out", joined[0].upper() + joined[1:] + ".", kind="ruled_out"))
        if fuel_chg == fuel_chg and fuel_chg > 0.08 and unit in DISCRETIONARY:
            factors.insert(-1, _factor("Fuel price pressure", f"Fuel was ${ev['fuel']:.3f} vs. ${ev['fuel_ly']:.3f} last year ({pct(fuel_chg)}).", tags=["Data"]))
        conf, limits = _confidence(pl, ev, passages, persistent, bool(ev["calendar_flags"]), gap)
        local_share = 1 - (ev["chain_dept_quarter_yoy"] / ev["dept_quarter_yoy"]) if ev["dept_quarter_yoy"] < 0 else 0
        if wal and gap < -0.05:
            bottom = (f"Walmart reported only a small company-wide decline in this category, but Store {s} {name} fell {pct(ev['dept_quarter_yoy'])} this quarter. "
                      f"{'Falling prices' if 'prices' in factors[0]['title'] else 'The company-wide trend'} explain{'s' if 'prices' not in factors[0]['title'] else ''} a small part; "
                      f"most of the drop is specific to Store {s}.")
        else:
            bottom = (f"{name} at Store {s} fell {pct(ev['deviation'])} vs. expected and {pct(ev['dept_quarter_yoy'])} this quarter; "
                      f"the reports describe the company, not this store, so the cause is only partly explained.")
        review = [f"Confirm whether {name} unit volume held (price effect) or fell (demand loss).",
                  f"Evaluate whether markdown spend in this period produced any lift for {name}."]
        if len(ev["peers"]):
            worst = ev["peers"].sort_values("YoY").head(2)
            review.append("Compare with other " + region_short + " stores: " + ", ".join(f"Store {int(r.Store)} {pct(r.YoY)}" for r in worst.itertuples()) + ".")
        claims.append(dict(id="md_ratio", value=md_x))
    return dict(verdict=verdict, status=status, confidence=conf, factors=factors, bottom_line=bottom, review=review,
                limitations=limits, claims=claims, grain="department_week",
                quotes=[dict(text=h["quote"], chunk_id=h["chunk_id"]) for h in passages])


# ------------------------------------------------------------------------------------------ store-week payloads
def reason_store(pl: dict, ev: dict, passages: list[dict]) -> dict:
    wk = pd.Timestamp(pl["week_ending"])
    names = {x["dept"]: x["dept_name"] for x in ev["top"] + ev["buffers"]}
    short = lambda n: n.replace(" Merchandise", "").replace(" (Rx)", "")
    top_names = ", ".join(short(names[x["dept"]]) for x in ev["top"])
    wal = _pick(passages, "walmart", ["holiday", "christmas", "season"])
    reg = _pick(passages, "regional", ["holiday", "retail", "consumer"], prefer_local=pl["fed_district"])
    b0, b1 = ev["baseline_weeks"].index.min(), ev["baseline_weeks"].index.max()
    same_as_chain = abs(ev["deviation"] - ev["chain_median_drop"]) <= 0.10
    flat_vs_ly = ev["yoy"] == ev["yoy"] and ev["yoy"] > -0.10
    seasonal = ev["christmas_in_baseline"] and flat_vs_ly and same_as_chain
    peak_depts = ev["peak_share"] == ev["peak_share"] and ev["peak_share"] >= 0.8
    md_x = ev["markdown"] / ev["markdown_avg"] if ev["markdown_avg"] else np.nan
    fuel_chg = ev["fuel"] / ev["fuel_ly"] - 1 if ev["fuel_ly"] == ev["fuel_ly"] else np.nan
    weakest = min((x for x in ev["top"] if x["yoy"] == x["yoy"]), key=lambda x: x["yoy"], default=None)
    claims = [dict(id="yoy", value=ev["yoy"]), dict(id="chain_median_drop", value=ev["chain_median_drop"]),
              dict(id="top_yoy", value=ev["top_yoy"]), dict(id="last_year_deviation", value=ev["last_year_deviation"]),
              dict(id="store_rank", value=ev["store_rank"])]
    factors, limits = [], []
    if seasonal:
        verdict, status = "Likely explained: post-holiday seasonality", "Likely explained"
        factors.append(_factor("Christmas inflated the baseline",
            f"**Sales data:** the expected {money(ev['expected'])} is the average of {b0:%b %-d}–{b1:%-d}, which includes Christmas week "
            f"({money(ev['baseline_peak'])}, {ev['baseline_peak'] / ev['typical_week']:.1f}× a typical week of {money(ev['typical_week'])}). "
            f"Against the same week last year, Store {pl['store']} is {pct(ev['yoy'])} ({money(ev['actual'])} vs. {money(ev['last_year'])}), "
            f"and the same method would have flagged last year's week too ({pct(ev['last_year_deviation'])}).", tags=["Data"]))
        factors.append(_factor("Every store dropped",
            f"**Sales data:** all {ev['n_stores']} stores fell a median {pct(ev['chain_median_drop'])} against their own 4-week baseline; "
            f"Store {pl['store']} ranks {ordinal(ev['store_rank'])} of {ev['n_stores']}. The five biggest shortfalls ({top_names}) all peak in Nov–Dec "
            f"and are together {pct(ev['top_yoy'])} vs. last year's same week.", tags=["Data"]))
        bits = []
        if wal:
            bits.append(f"**Walmart reports:** {_q(wal)} ({_src(wal)}).")
        if reg:
            bits.append(f"**{reg['publisher']}** ({reg['district']}): {_q(reg)}")
        if bits:
            factors.append(_factor("Strong season, not a slump", " ".join(bits), tags=["Walmart", "Regional"]))
        if weakest and weakest["yoy"] < -0.10:
            factors.append(_factor("Still worth a look",
                f"**Sales data:** {short(names[weakest['dept']])} is {pct(weakest['yoy'])} vs. last year's same week. Walmart said layaway lifted toy "
                f"sales earlier in the quarter, so some demand may have been pulled forward. Possible, not confirmed.", tags=["Data", "Walmart"]))
        factors.append(_factor("Ruled out",
            f"A store-specific slump: the next {ev['n_next_weeks']} weeks are {pct(ev['next_weeks_yoy'])} vs. last year. Fuel ({pct(fuel_chg)}) and weather "
            f"({ev['temp']:.0f}°F vs. {ev['temp_ly']:.0f}°F) were normal. Markdowns ({money(ev['markdown'])}, {md_x:.1f}× an average week) are "
            f"recorded for the store, not by department, so they cannot explain the gap.", kind="ruled_out"))
        conf = "High" if peak_depts and abs(ev["last_year_deviation"] - ev["deviation"]) <= 0.10 else "Medium"
        limits += ["The detector's \"structural slump\" and \"internal merchandising failure\" reading comes from a baseline that is not adjusted "
                   "for the Christmas peak; last year's comparison does not support it.",
                   "Markdowns are recorded per store, not per department, so the data cannot show whether they lifted sales."]
        bottom = (f"Likely not a real problem. The expected number is inflated by Christmas week; compared with last year Store {pl['store']} is "
                  f"{pct(ev['yoy'])} and every store dropped. The detector's \"structural slump\" flag is not supported."
                  + (f" Only {short(names[weakest['dept']])} is worth a look over the next two weeks." if weakest and weakest["yoy"] < -0.10 else ""))
        review = ["No store action needed for this week; use a same-week-last-year or holiday-aware baseline for January weeks.",
                  f"Check {short(names[weakest['dept']])} over the next two weeks ({pct(weakest['yoy'])} vs. last year)." if weakest else "Re-check next week."]
    else:
        verdict, status = "Needs review", "Needs review"
        factors.append(_factor("Store-wide drop", f"**Sales data:** Store {pl['store']} is {pct(ev['deviation'])} vs. its 4-week baseline and "
                               f"{pct(ev['yoy'])} vs. last year; the median store is {pct(ev['chain_median_drop'])}.", tags=["Data"]))
        factors.append(_factor("Largest department shortfalls", f"**Sales data:** {top_names}; {pct(ev['top_yoy'])} vs. last year's same week.", tags=["Data"]))
        if wal:
            factors.append(_factor("Company context", f"**Walmart reports:** {_q(wal)} ({_src(wal)})", tags=["Walmart"]))
        conf = "Medium"
        bottom = f"Sales fell {pct(ev['deviation'])} vs. the 4-week baseline and {pct(ev['yoy'])} vs. last year, which a seasonal pattern does not fully explain."
        review = ["Compare with stores of the same type and region.", f"Review stock and promotions in {top_names}."]
    limits += ["Department and region names are publicly inferred, not confirmed by Walmart.", "Reports describe Walmart or the Fed district as a whole, not this store.",
               "No unit, price or inventory data."]
    return dict(verdict=verdict, status=status, confidence=conf, factors=factors, bottom_line=bottom, review=review,
                limitations=limits, claims=claims, grain="store_week",
                quotes=[dict(text=h["quote"], chunk_id=h["chunk_id"]) for h in passages])


def reason(pl: dict, ev: dict, passages: list[dict]) -> dict:
    return reason_store(pl, ev, passages) if pl.get("grain") == "store_week" else reason_department(pl, ev, passages)


# ------------------------------------------------------------------------------------------ LLM writer (optional)
def facts_for_llm(pl, ev, rep, passages):
    return dict(case=dict(store=pl["store"], region=pl["region"], week_ending=pl["week_ending"], what=pl.get("dept_name"),
                          actual=round(pl["actual_sales"]), expected=round(pl["expected_sales"]), deviation_pct=pl["deviation_pct"]),
                verdict=rep["verdict"], confidence=rep["confidence"],
                factors=[dict(title=f["title"], text=re.sub(r"\*\*", "", f["text"])) for f in rep["factors"]],
                bottom_line=rep["bottom_line"],
                passages=[dict(id=h["chunk_id"], source=h["doc"], date=h["published"], quote=h["quote"]) for h in passages])


def llm_explain(pl, ev, rep, passages) -> dict | None:
    """Ask the LLM for a short plain-language explanation. Rejected (text=None) if it adds numbers or quotes that are not in the facts."""
    if not llm.available():
        return None
    facts = facts_for_llm(pl, ev, rep, passages)
    return llm.complete_grounded(llm.SYSTEM_EXPLAIN, "FACTS (JSON):\n" + llm.dumps(facts) + "\n\nWrite the explanation now.", facts)
