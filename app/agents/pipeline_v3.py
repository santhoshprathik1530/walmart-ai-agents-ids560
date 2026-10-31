"""Phase 2 agent: looks for evidence that supports each ML flag (v3.4 cases since 2026-10-30: 40 ranked store-weeks,
per-store MAD thresholds, several flagged departments each; v3.3 outputs are archived in data/v33_archive/).

    python3 -m agents.pipeline_v3                 all 40 cases (cached: finished cases are skipped)
    python3 -m agents.pipeline_v3 --ranks 1 2 3   only these ranks;  --force  re-run them
    python3 -m agents.pipeline_v3 --reevaluate    re-run only the code checks on the saved answers
    The dashboard can also add a case file and run it live (add_case, run_live -> data/agent_outputs_v3_live.json).

The ML team defines the exception (Santhosh, 2026-10-31): the flagged store-week and departments, the thresholds, the
priority order and the status ("Analyst review required") come from the ML files and are never re-judged here.

    intake (code)       the ML numbers per flagged department + evidence from the ML team's own forecasts (agents/support.py):
                        Walmart overall that week, this store's other departments, the same department at every store and
                        in the same region, outside factors (holiday, fuel, temperature, unemployment, markdowns, reported comps)
    orchestrator (LLM)  picks up to 3 departments to research (largest gaps first) and writes 2-4 report search questions
    RAG (code)          retrievers.search, setup E (section chunks, hybrid, time + Fed district filter), merged to 6 passages
    reasoning (LLM)     what supports the flag: findings tagged by where they come from, per department, what was not found
    evaluation (code)   7 checks (evaluate.evaluate_v3); a failed check shows "Answer needs a check"
Batch runs (main) pin one model (the first in LLM_MODEL), with no fallback. Writes data/agent_outputs_v3.json.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from functools import lru_cache

import pandas as pd

from . import evaluate, llm, retrievers, support
from .cases_v3 import DATA, STATUS, case_rows, check_case, dept_rows, load_cases, normalize
from .retrievers import allowed_districts

OUT = DATA / "agent_outputs_v3.json"
LIVE = DATA / "agent_outputs_v3_live.json"          # cases run from the dashboard (new uploads, "run again")
UPLOADS = DATA / "cases_v3_uploaded"                 # case files uploaded in the dashboard
VARIANT, PER_QUERY, N_PASSAGES, MAX_PER_DOC, GRACE = "E", 6, 6, 2, 21
NEEDS_CHECK = "Answer needs a check"                 # shown when the assistant's answer fails a code check
EVIDENCE_FOUND = ("Strong", "Some", "Little")
SCOPES = ("walmart", "department", "region", "store", "outside", "report", "ml_note")
MODELS: list[str] | None = None                      # None = the LLM_MODEL chain with fallback; main() pins one model
MAX_TOKENS = 6000


def usd(x: float) -> str:
    return f"${x:,.0f}"


def pc(x: float) -> str:
    return "n/a" if x != x else f"{x:+.1f}%"


def day(d) -> str:
    return pd.Timestamp(d).strftime("%b %-d, %Y")


@lru_cache(maxsize=1)
def _base_tables():
    return (pd.read_csv(DATA / "triage_v3_depts.csv"), pd.read_csv(DATA / "triage_v3_cases.csv"),
            {c["case_id"]: c for c in load_cases()})


@lru_cache(maxsize=8)
def _uploaded_tables(stamp: tuple):
    files = [normalize(json.loads((UPLOADS / name).read_text())) for name, _ in stamp]
    d = dept_rows(files)
    return d, case_rows(d, files), {x["case_id"]: x for x in files}


def tables():
    """(departments, cases indexed by CaseID, raw case files): the ML team's 40 cases plus any uploaded in the dashboard
    (an uploaded case with the same case_id replaces the original)."""
    d, c, raw = _base_tables()
    stamp = tuple(sorted((f.name, f.stat().st_mtime) for f in UPLOADS.glob("*.json"))) if UPLOADS.exists() else ()
    if stamp:
        ud, uc, uraw = _uploaded_tables(stamp)
        new = set(uraw)
        d = pd.concat([d[~d.CaseID.isin(new)], ud], ignore_index=True)
        c = pd.concat([c[~c.CaseID.isin(new)], uc], ignore_index=True)
        raw = {**raw, **uraw}
    return d, c.set_index("CaseID"), raw


def add_case(js: dict) -> str:
    """Save a new case file (from the dashboard) so it is used with the others. Returns its case id."""
    probs = check_case(js)
    if probs:
        raise ValueError("; ".join(probs))
    UPLOADS.mkdir(exist_ok=True)
    cid = normalize(js)["case_id"]
    (UPLOADS / f"{re.sub(r'[^A-Za-z0-9_-]', '_', cid)}.json").write_text(json.dumps(js, indent=1))
    return cid


def outputs() -> dict:
    """Saved answers: the batch run, overridden by any live run from the dashboard."""
    out = json.loads(OUT.read_text()) if OUT.exists() else {}
    return {**out, **(json.loads(LIVE.read_text()) if LIVE.exists() else {})}


def run_live(cid: str, progress=None) -> dict:
    """Run one case now (dashboard: new upload or 'run again') and save it to the live file."""
    res = run_case(cid, progress)
    res["run"], res["ran_at"] = "live", time.strftime("%b %-d, %Y %H:%M")
    live = json.loads(LIVE.read_text()) if LIVE.exists() else {}
    live[cid] = res
    LIVE.write_text(json.dumps(live, indent=1, default=str))
    return res


# ------------------------------------------------------------------------------------------ intake
def _dept_item(r, have_ml: bool) -> dict:
    item = dict(
        id=f"dept_{int(r.Dept)}", kind="ML flag",
        label=f"Dept {int(r.Dept)} {r.DeptName} ({r.Unit} unit; name {r.DeptConf.lower()} confidence)",
        actual=usd(r.Actual), ml_forecast=usd(r.Expected), below_forecast=f"{usd(r.Shortfall)} ({pc(-r.ShortfallPct)})",
        store_threshold=f"{r.ThresholdPct:.1f}%" if r.ThresholdPct == r.ThresholdPct else "n/a",
        ml_notes=(f"vs the median of the last 4 weeks {pc(r.VsRecent4Pct)}; vs the same season in earlier years "
                  f"{pc(r.VsSeasonPct)}; model too high at {r.ChainOverpredPct:.1f}% of other stores; signals: {r.MLNotes}"))
    if have_ml:
        s = support.dept_summary(int(r.Dept), r.Date, int(r.Store))
        item["same_department_all_stores"] = (
            f"{s['below']} of {s['stores']} other stores were below the ML forecast in this department that week "
            f"(median {pc(s['median_pct'])}, all together {pc(s['all_pct'])}); {s['flagged']} of them were also flagged by "
            f"the ML team; this store {pc(s['this_pct'])}, number {s['rank_low']} from the bottom of {s['stores'] + 1}")
        item["same_department_same_region"] = (
            f"{s['region']} (region publicly inferred): {s['region_below']} of {s['region_stores']} other stores below the "
            f"ML forecast, {s['region_flagged']} flagged" + (f" ({s['region_list']})" if s["region_list"] else ""))
    return item


def case_facts(cid: str) -> dict:
    depts, cases, raw = tables()
    row, js = cases.loc[cid], raw[cid]
    g = depts[depts.CaseID == cid].sort_values("Shortfall", ascending=False)
    first = g.iloc[0]
    md = js["markdown_context"]
    have_ml = support.covered(row.Date)
    case = dict(
        store=int(row.Store), store_type=row.Type, store_size=f"{int(first.Size):,} sq ft", region=row.Region,
        fed_district=row.District, week_ending=day(row.Date), walmart_quarter=row.FiscalPeriod,
        holiday_week=row.HolidayWeek if isinstance(row.HolidayWeek, str) else "none",
        ml_priority_rank=f"{int(row.Rank)} of 40", ml_status=f"{STATUS} (root cause not verified)",
        flagged_departments=int(row.FlaggedDepts),
        total_below_forecast=f"{usd(row.FlaggedShortfall)} in the flagged departments (ML estimate, not a verified loss)",
        store_threshold=(f"{row.ThresholdPct:.1f}% (a department is flagged when it sells at least this far below the ML "
                         f"forecast)") if row.ThresholdPct == row.ThresholdPct else "n/a",
        detector=("Isolation Forest screen, then Extra Trees forecast with a per-store MAD threshold"
                  if row.ThresholdPct == row.ThresholdPct else "Isolation Forest screen, then Extra Trees forecast with a Global MAD filter"))
    ev = [{k: v for k, v in _dept_item(r, have_ml).items() if v is not None} for r in g.itertuples()]
    if have_ml:
        sw, ww = support.store_week(int(row.Store), row.Date), support.walmart_week(row.Date)
        ev.append(dict(id="this_store", kind="ML forecast", label=f"All of Store {int(row.Store)}'s departments that week",
                       value=f"{sw['below']} of {sw['depts']} departments below the ML forecast, {sw['flagged']} flagged; the "
                             f"store as a whole {usd(sw['actual'])} vs {usd(sw['expected'])} forecast ({pc(sw['pct'])})"))
        ev.append(dict(id="walmart_week", kind="ML forecast", label="All 45 stores that week",
                       value=f"{usd(ww['actual'])} vs {usd(ww['expected'])} forecast ({pc(ww['pct'])}); {ww['stores_below']} of 45 "
                             f"stores below the forecast; {ww['stores_flagged']} stores had at least one flagged department; "
                             f"number {ww['rank_low']} from the bottom of the {ww['weeks']} test weeks (median week "
                             f"{pc(ww['median_week_pct'])})"))
    else:
        ev.append(dict(id="this_store", kind="ML forecast", label="Other stores and departments",
                       value="not available: the ML team's forecasts for all stores cover Jul 20 - Oct 26, 2012 only"))
    o = support.outside(int(row.Store), row.Date)
    bits = [f"holiday: {o['holiday']}"]
    if "Fuel_Price" in o:
        bits.append(f"local fuel price ${o['Fuel_Price']['current']:.2f}/gal vs ${o['Fuel_Price']['prior_4_week_median']:.2f}")
    if "Temperature" in o:
        bits.append(f"temperature {o['Temperature']['current']:.0f}°F vs {o['Temperature']['prior_4_week_median']:.0f}°F")
    if "Unemployment" in o:
        bits.append(f"unemployment {o['Unemployment']['current']:.1f}% vs {o['Unemployment']['prior_4_week_median']:.1f}%")
    ev.append(dict(id="outside", kind="data", label="Outside factors that week (vs the median of the 4 weeks before)",
                   value="; ".join(bits)))
    if md.get("markdown_recorded"):
        ev.append(dict(id="markdowns", kind="data", label="Markdowns recorded for the whole store this week",
                       value=f"{usd(md['recorded_markdown_total'])} across {md['recorded_markdown_count']} fields. "
                             "Store-level only: cannot be tied to a department."))
    if o.get("reported_comp") is not None:
        ev.append(dict(id="walmart_quarter", kind="report", label=f"Walmart U.S. comparable sales reported for {o['quarter']}",
                       value=pc(float(o["reported_comp"]) * 100)))
    return dict(case=case, evidence=ev, guardrails=js["rag_investigation"]["guardrails"], code_status=STATUS,
                top_depts=[int(d) for d in g.Dept.head(3)], questions=js["rag_investigation"]["questions_for_agent"])


# ------------------------------------------------------------------------------------------ orchestrator
PLAN_SYS = (
    "You are the orchestrator of a Walmart sales investigation. The ML team flagged a store-week where several departments "
    "sold below the ML forecast; the flag is theirs and is not questioned. Your job is to find evidence that supports it. "
    "The sales comparisons are already done. Decide what to look up in a library of Walmart earnings releases, earnings "
    "call transcripts, 10-Qs, 10-Ks, Walmart news releases and Federal Reserve Beige Books from the same weeks and region. "
    "1) Pick the 1-3 departments with the largest dollar gaps. 2) Write 2 to 4 short search questions about what could "
    "support the drops: the product category, Walmart's results that quarter, the region's economy or weather, fuel "
    "prices, a holiday. Never use the store number. "
    'Reply with JSON only: {"focus": ["dept_<number>", ...], "queries": [{"name": "one word", "text": "question"}], '
    '"why": "one sentence"}')


def plan(f: dict) -> dict:
    ids = {e["id"] for e in f["evidence"] if e["id"].startswith("dept_")}
    brief = dict(case=f["case"], departments=[dict(id=e["id"], name=e["label"], below_forecast=e["below_forecast"],
                                                   same_department_all_stores=e.get("same_department_all_stores", "n/a"))
                                              for e in f["evidence"] if e["id"] in ids],
                 context=[e for e in f["evidence"] if e["id"] in ("walmart_week", "outside")])

    def ok(o):
        if not isinstance(o, dict) or not [q for q in o.get("queries", []) if isinstance(q, dict) and q.get("text")]:
            return False, "no search questions"
        return True, ""
    out = llm.complete_json(PLAN_SYS, "CASE (JSON):\n" + llm.dumps(brief), ok, max_tokens=1200, models=MODELS)
    if not out:
        return dict(error=f"Orchestrator LLM gave no plan ({llm.last_error})")
    v = out["value"]
    qs = [dict(name=re.sub(r"[^a-z_]", "", str(q.get("name", "q")).lower())[:20] or f"q{i}", text=str(q["text"]).strip()[:200])
          for i, q in enumerate(x for x in v["queries"] if isinstance(x, dict) and x.get("text"))][:4]
    return dict(focus=[d for d in v.get("focus", []) if d in ids][:3], queries=qs, why=str(v.get("why", "")),
                llm=_meta(out))


def _meta(out: dict) -> dict:
    return dict(model=out["model"], ms=out["ms"], tokens_in=out["input_tokens"], tokens_out=out["output_tokens"])


# ------------------------------------------------------------------------------------------ RAG (setup E)
def retrieve(f: dict, queries: list[dict]) -> dict:
    t0 = time.time()
    w = pd.Timestamp(f["case"]["week_ending"])
    ctx = dict(start=w - pd.Timedelta(days=GRACE), end=w, districts=allowed_districts(f["case"]["fed_district"]))
    score: dict[str, float] = {}
    rows: dict[str, dict] = {}
    for q in queries:
        res = retrievers.search(q["text"], VARIANT, PER_QUERY, ctx)
        q["hits"] = [r["id"] for r in res]
        for r in res:                                         # reciprocal-rank fusion across the questions
            score[r["id"]] = score.get(r["id"], 0) + 1 / (60 + r["rank"])
            rows.setdefault(r["id"], dict(r, queries=[]))["queries"].append(q["name"])
    ranked = sorted(rows.values(), key=lambda r: score[r["id"]], reverse=True)
    chosen: list[dict] = []

    def take(r):
        if r and r not in chosen and sum(x["meta"]["doc_id"] == r["meta"]["doc_id"] for x in chosen) < MAX_PER_DOC:
            chosen.append(r)
    take(next((r for r in ranked if r["meta"]["evidence_type"].startswith("Walmart")), None))
    take(next((r for r in ranked if r["meta"]["doc_type"] == "beige_book" and r["meta"]["district"] in ctx["districts"]), None))
    for r in ranked:
        if len(chosen) >= N_PASSAGES:
            break
        take(r)
    chosen.sort(key=lambda r: score[r["id"]], reverse=True)
    m = lambda r: r["meta"]
    passages = [dict(id=f"P{i + 1}", source=m(r)["title"], date=day(str(m(r)["published"])),
                     district="National" if m(r)["district"] == "National" else f"{m(r)['district']} Fed District",
                     kind=m(r)["evidence_type"], section=m(r).get("section", ""), url=m(r)["url"], chunk_id=r["id"],
                     queries=sorted(set(r["queries"])), text=r["text"]) for i, r in enumerate(chosen)]
    return dict(passages=passages, ms=round((time.time() - t0) * 1000), candidates=len(rows),
                filter=dict(start=str(ctx["start"].date()), end=str(ctx["end"].date()), districts=["National"] + ctx["districts"]))


# ------------------------------------------------------------------------------------------ reasoning
REASON_SYS = (
    "You support a Walmart analyst who reviews store-weeks flagged by the ML team. The ML team defines the exception: its "
    "forecast, the store's threshold and the flagged departments are given and are NOT questioned. Never say the flag is "
    "wrong, that the forecast is the problem, or that no action is needed. Your only job: find evidence that supports or "
    "explains the flagged drops, and say plainly where none was found. Look at: Walmart overall that week (walmart_week, "
    "walmart_quarter), the same department at other stores and in the same region, this store's other departments "
    "(this_store), outside factors (holiday, fuel, temperature, unemployment), and the report passages. A drop shared by "
    "many stores or the region points to a wider cause (category, economy, weather, calendar); a drop only at this store "
    "points to something local (stock, staffing, execution, local competition). The ML team's own notes (ml_notes) may be "
    "mentioned as the ML team's notes. Write short, plain sentences for a store manager: no jargon, no ids or field names "
    "in the text (name the department and the report), dates like 'Aug 31, 2012'. "
    "Use ONLY the facts in the JSON. Copy every number exactly as written; do not calculate, round or convert. Quote a "
    "passage only by copying its words exactly inside quotation marks. Rules you must follow: {} "
    "Never say a cause is verified, confirmed or proven: these are possible reasons. Say 'below the ML forecast', never "
    "'lost sales' or 'lost revenue'. Markdowns are recorded for the whole store; never say they caused or explain a "
    "department's drop. Reports describe Walmart or a Fed district as a whole, not this store. "
    "evidence_found: 'Strong' if the sales data or a report points at these departments or their category in this period; "
    "'Some' if only general evidence (Walmart overall, the economy, weather, a holiday); 'Little' if nothing beyond the ML "
    "numbers. Give 2 to 6 findings. Each finding has a scope: 'walmart' (all stores that week or the quarter), 'department' "
    "(the same department at other stores), 'region', 'store' (this store's other departments), 'outside' (holiday, fuel, "
    "weather, unemployment), 'report' (a Walmart or Fed report; must cite a passage id like P1) or 'ml_note' (the ML team's "
    "own notes). Each finding lists the ids it uses (evidence ids like 'dept_92', 'walmart_week', or passage ids like 'P2'). "
    "Under departments, cover the departments with the largest gaps (at least the first one listed). "
    "next_steps are checks the store or analyst can make on the store side (stock and deliveries, staffing, pricing and "
    "displays, local events or competitors, data entry); never ask the ML team to review, explain or confirm its forecast, "
    "notes or signals. Use only ids that appear in the JSON (evidence ids, 'case', passage ids). "
    'Reply with JSON only: {"evidence_found": "Strong|Some|Little", "summary": "2-3 sentences", '
    '"findings": [{"title": "max 6 words", "scope": "...", "text": "1-2 sentences", "evidence": ["id", ...]}], '
    '"departments": [{"department": "Dept 92 Dry Grocery", "what_supports_it": "1-2 sentences"}], '
    '"not_found": "one sentence: what was looked for and not found", "next_steps": ["short action for the analyst", ...], '
    '"data_needed": ["what data would confirm a cause"]}')


def facts_for(case: dict, evidence: list[dict], passages: list[dict]) -> dict:
    return dict(case=case, evidence=evidence,
                passages=[{k: p[k] for k in ("id", "source", "date", "district", "kind", "text")} for p in passages])


def reason(f: dict, passages: list[dict]) -> dict:
    facts = facts_for(f["case"], f["evidence"], passages)
    system = REASON_SYS.replace("{}", " ".join(f["guardrails"]), 1)

    def ok(o):
        if not isinstance(o, dict) or not isinstance(o.get("findings"), list) or not o["findings"]:
            return False, "no findings"
        return True, ""
    out = llm.complete_json(system, "FACTS (JSON):\n" + llm.dumps(facts) + "\n\nWrite the answer now as JSON.", ok,
                            max_tokens=MAX_TOKENS, models=MODELS)
    if not out:
        return dict(error=f"Reasoning LLM gave no readable answer ({llm.last_error})", facts=facts)
    return dict(report=_clean(out["value"]), facts=facts, llm=_meta(out))


def _list(x) -> list:
    return x if isinstance(x, list) else [x] if x else []


def _clean(v: dict) -> dict:
    s = lambda x: str(x or "").strip()
    return dict(
        evidence_found=s(v.get("evidence_found")), summary=s(v.get("summary")),
        findings=[dict(title=s(f.get("title")), scope=s(f.get("scope")).lower(), text=s(f.get("text")),
                       evidence=[str(x) for x in _list(f.get("evidence"))]) for f in _list(v.get("findings")) if isinstance(f, dict)],
        departments=[dict(department=s(d.get("department")), what_supports_it=s(d.get("what_supports_it")))
                     for d in _list(v.get("departments")) if isinstance(d, dict)],
        not_found=s(v.get("not_found")),
        next_steps=[s(x) for x in _list(v.get("next_steps")) if s(x)], data_needed=[s(x) for x in _list(v.get("data_needed")) if s(x)])


# ------------------------------------------------------------------------------------------ run
def run_case(cid: str, progress=None) -> dict:
    say = progress or (lambda _msg: None)
    t0 = time.time()
    f = case_facts(cid)
    say(f"Read the ML flag: {f['case']['flagged_departments']} departments below the store's threshold; compared them with "
        "all stores, the region and the store's other departments")
    out = dict(case_id=cid, case=f["case"], code_status=f["code_status"], top_depts=f["top_depts"], evidence=f["evidence"])
    p = plan(f)
    out["plan"] = p
    if p.get("error"):
        return dict(out, error=p["error"], shown_status="Try again")
    say("Planned the search: " + " | ".join(q["text"] for q in p["queries"]))
    r = retrieve(f, p["queries"])
    out["rag"] = r
    say(f"Read {len(r['passages'])} report passages ({r['filter']['start']} to {r['filter']['end']}, "
        f"{', '.join(r['filter']['districts'])})")
    a = reason(f, r["passages"])
    if a.get("error"):
        return dict(out, error=a["error"], shown_status="Try again")
    say(f"Wrote the answer: {len(a['report']['findings'])} findings")
    res = evaluate.evaluate_v3(a["report"], a["facts"], f["top_depts"])
    say(f"Checked the answer: {sum(k['passed'] for k in res['checks'])} of {len(res['checks'])} checks passed")
    shown = f["code_status"] if res["passed"] else NEEDS_CHECK
    return dict(out, report=a["report"], llm=a["llm"], evaluation=res, shown_status=shown,
                needs_review=not res["passed"], seconds=round(time.time() - t0, 1))


def reevaluate() -> dict:
    """Re-run only the code checks on the saved answers (after a change to evaluate.py); no LLM calls."""
    done = json.loads(OUT.read_text())
    for x in done.values():
        if "report" in x:
            x["evaluation"] = evaluate.evaluate_v3(x["report"], facts_for(x["case"], x["evidence"], x["rag"]["passages"]),
                                                   x["top_depts"])
            x["shown_status"] = x["code_status"] if x["evaluation"]["passed"] else NEEDS_CHECK
            x["needs_review"] = not x["evaluation"]["passed"]
    OUT.write_text(json.dumps(done, indent=1, default=str))
    return done


def main(ranks: list[int] | None = None, force: bool = False) -> dict:
    global MODELS
    MODELS = llm.model_chain()[:1]                   # one model for every case in a batch run, no fallback
    _, cases, _ = tables()
    done = json.loads(OUT.read_text()) if OUT.exists() else {}
    todo = [cid for cid, r in cases.sort_values("Rank").iterrows() if not ranks or int(r.Rank) in ranks]
    for cid in todo:
        if cid in done and not force and not done[cid].get("error"):
            continue
        res = run_case(cid)
        done[cid] = res
        OUT.write_text(json.dumps(done, indent=1, default=str))
        ev = res.get("evaluation", {})
        print(f"{cid}: model={res.get('llm', {}).get('model')} found={res.get('report', {}).get('evidence_found')} "
              f"checks={'pass' if ev.get('passed') else [c['name'] for c in ev.get('checks', []) if not c['passed']] or res.get('error')} "
              f"{res.get('seconds')}s", flush=True)
    return done


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ranks", nargs="*", type=int)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--reevaluate", action="store_true", help="re-run the code checks on saved answers only")
    a = ap.parse_args()
    reevaluate() if a.reevaluate else main(a.ranks, a.force)
