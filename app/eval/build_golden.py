"""Build the golden Q&A set used to compare RAG approaches and to validate the agent.

    python3 -m eval.build_golden        (run from app/, after python3 -m agents.cases_v3)

Three kinds of items:
  report    - hand-written in eval/report_qa.json: question, reference answer, verbatim evidence quote(s) + doc_id.
              Retrieval is scored by whether a retrieved chunk contains the quote, so the set works for any chunking.
              Items marked unanswerable test that the agent says "not in the sources" instead of guessing.
  case      - generated here from the v3.3 case files and the triage tables; answers are exact numbers.
  judgment  - 10 cases x 2 questions (what to do, main factor). The draft answer comes from the code triage;
              two teammates label the same cases blind in eval/labels_sheet.csv, and agreement is measured.

Writes eval/golden_qa.json (everything), eval/golden_qa_review.csv (for the reviewers), eval/labels_sheet.csv.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pandas as pd

from agents import support
from agents.cases_v3 import load_cases
from agents.ingest import clean, registry

EVAL = Path(__file__).resolve().parent
DATA = EVAL.parent / "data"

JUDGED_RANKS = [1, 2, 6, 7, 8, 12, 15, 19, 21, 25]
APPROVED = "approved (Santhosh Kasam, 2026-10-31)"
# Judgment items ask people what evidence supports the ML team's flag (never whether the flag is right). No draft answer
# from code: the agreed label of the two blind labellers becomes the reference.
EVIDENCE = {
    "shared_all": "Shared by many stores: the same department was below the ML forecast at most stores, or Walmart overall was down",
    "shared_region": "Shared by the region: the same department was below the ML forecast at the stores in the same region",
    "store_wide": "Store-wide: most of this store's departments were below the ML forecast that week",
    "local_only": "Only here: the department was down at this store but not at most other stores (points to a local cause)",
    "report": "A Walmart or Federal Reserve report (category trend, prices, economy, weather)",
    "calendar": "Holiday or calendar timing",
    "none": "No supporting evidence found",
}
STRENGTH = ["Strong", "Some", "Little"]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip().lower()


def money(x: float) -> str:
    return f"${x:,.0f}"


def nice_date(d: str) -> str:
    return pd.Timestamp(d).strftime("%b %-d, %Y")


# --------------------------------------------------------------------------- report items
def report_items() -> list[dict]:
    texts = {d["id"]: norm(clean(d["file"].read_text(errors="ignore"))) for d in registry()}
    items = json.loads((EVAL / "report_qa.json").read_text())
    for it in items:
        it["type"] = "report"
        it.setdefault("unanswerable", False)
        for ev in it["evidence"]:
            ev["found_in_source"] = norm(ev["quote"]) in texts.get(ev["doc_id"], "")
    return items


# --------------------------------------------------------------------------- case items
def case_items(cases: pd.DataFrame, depts: pd.DataFrame) -> list[dict]:
    out = []
    c = cases.set_index("Rank")

    def add(rank, kind, q, a, fields, dept=None):
        r = c.loc[rank]
        out.append(dict(id=f"C{len(out) + 1:02d}", type="case", case_id=r.CaseID, question=q, answer=a, evidence=[],
                        source_fields=fields, tags=dict(kind=kind, store=int(r.Store), date=r.Date,
                                                        dept=None if dept is None else int(dept))))

    def top(rank):
        return depts[depts.Rank == rank].sort_values("Shortfall", ascending=False).iloc[0]

    def where(rank):
        r = c.loc[rank]
        return f"Store {r.Store} in the week ending {nice_date(r.Date)}"

    for rank in [1, 2, 8, 15]:
        t = top(rank)
        add(rank, "largest_dept", f"Which flagged department has the largest modeled shortfall at {where(rank)}, and how large is it?",
            f"Dept {t.Dept} {t.DeptName}: {money(t.Shortfall)} below the Extra Trees expectation ({t.ShortfallPct:.1f}%).",
            "sales_evidence.global_mad_flagged_departments.departments[].modeled_dollar_shortfall", t.Dept)
    for rank in [2, 12, 25]:
        t = top(rank)
        add(rank, "expected_vs_actual", f"What were expected and actual sales for {t.DeptName} (Dept {t.Dept}) at {where(rank)}?",
            f"Expected {money(t.Expected)}, actual {money(t.Actual)}.",
            "expected_weekly_sales_extra_trees, actual_weekly_sales", t.Dept)
    for rank in [4, 10]:
        r = c.loc[rank]
        add(rank, "dept_count", f"How many departments were flagged at {where(rank)}, and what is their total modeled shortfall?",
            f"{r.FlaggedDepts} departments, {money(r.FlaggedShortfall)} in total.",
            "global_mad_flagged_departments.count, sum_positive_modeled_shortfalls")
    for rank in [1, 8]:
        t = top(rank)
        add(rank, "vs_last_year", f"How did {t.DeptName} sales at {where(rank)} compare with the same week in earlier years?",
            f"Actual {money(t.Actual)} vs a same-season median of {money(t.SeasonMedian)} ({t.VsSeasonPct:+.1f}%).",
            "historical_validation.same_season_previous_years", t.Dept)
    for cid, dept in [("Store_28_2012-08-31", 92), ("Store_21_2012-08-03", 38)]:      # by case, since ranks change between ML versions
        t = depts[(depts.CaseID == cid) & (depts.Dept == dept)].iloc[0]
        rank = int(t.Rank)
        s = support.dept_summary(dept, t.Date, int(t.Store))
        add(rank, "other_stores", f"How did {t.DeptName} do at the other stores that week, compared with {where(rank)}?",
            f"{s['below']} of {s['stores']} other stores were below the ML forecast (median {s['median_pct']:+.1f}%); "
            f"{s['flagged']} were also flagged; this store {s['this_pct']:+.1f}%.",
            "ML department-week file (per_store_mad_department_flags.csv), via agents/support.py", dept)
    for rank in [1, 4]:
        t = top(rank)
        add(rank, "chain_overprediction", f"At {where(rank)}, in what share of other stores did the model also overpredict {t.DeptName}?",
            f"{t.ChainOverpredPct:.1f}% of the other stores compared.",
            "cross_store_validation.overprediction_rate_pct", t.Dept)
    for rank in [1, 6]:
        r = c.loc[rank]
        raw = next(x for x in load_cases() if x["store_week"]["priority_rank"] == rank)
        md = raw["markdown_context"]
        add(rank, "markdowns", f"What markdowns were recorded at {where(rank)}, and do they explain the shortfall?",
            f"{md['recorded_markdown_count']} markdown fields recorded, {money(md['recorded_markdown_total'])} in total. "
            "They are store-week amounts and do not prove any department was discounted or caused the shortfall.",
            "markdown_context")
    for rank in [18, 14]:
        r = c.loc[rank]
        add(rank, "fiscal_link", f"Which Walmart fiscal quarter does the week ending {nice_date(r.Date)} fall in, and which earnings report covers it?",
            f"{r.FiscalPeriod}; covered by the Walmart {r.FiscalPeriod.replace('FY20', 'FY')} earnings release and call.",
            "data/fiscal_calendar.csv")
    r = c.loc[1]
    add(1, "holiday", f"Is the week ending {nice_date(r.Date)} a holiday week?", "Yes, it is the Labor Day week.",
        "data/fiscal_calendar.csv (Holiday Week)")
    return out


# --------------------------------------------------------------------------- judgment items
def brief(rank: int, cases: pd.DataFrame, depts: pd.DataFrame) -> str:
    """What a labeller sees: the ML flag and the sales evidence (not the assistant's answer, not the reports)."""
    r = cases.set_index("Rank").loc[rank]
    g = depts[depts.Rank == rank].sort_values("Shortfall", ascending=False).head(5)
    lines = [f"Store {r.Store} (type {r.Type}, {r.Region}), week ending {nice_date(r.Date)}"
             + (f" ({r.HolidayWeek} week)" if isinstance(r.HolidayWeek, str) else "")
             + f", Walmart {r.FiscalPeriod}. The ML team flagged {r.FlaggedDepts} departments, {money(r.FlaggedShortfall)} below "
             f"its forecast (store threshold {r.ThresholdPct:.1f}%). Largest gaps:"]
    for _, d in g.iterrows():
        s = support.dept_summary(int(d.Dept), d.Date, int(d.Store))
        lines.append(f"- {d.Dept} {d.DeptName}: {money(d.Actual)} vs {money(d.Expected)} forecast ({-d.ShortfallPct:+.0f}%); "
                     f"other stores below forecast {s['below']} of {s['stores']} (median {s['median_pct']:+.0f}%); same region "
                     f"{s['region_below']} of {s['region_stores']}; ML notes: {d.MLNotes}")
    sw, ww = support.store_week(int(r.Store), r.Date), support.walmart_week(r.Date)
    lines.append(f"This store: {sw['below']} of {sw['depts']} departments below forecast ({sw['pct']:+.1f}% overall). "
                 f"All 45 stores: {ww['pct']:+.1f}% vs forecast, {ww['stores_below']} of 45 below.")
    return "\n".join(lines)


def judgment_items(cases: pd.DataFrame, depts: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    items, sheet = [], []
    for rank in JUDGED_RANKS:
        r = cases.set_index("Rank").loc[rank]
        for kind, q, opts in [
            ("main_evidence", "What is the main evidence that supports the ML team's flag?", list(EVIDENCE.values())),
            ("strength", "How much supporting evidence is there?", STRENGTH),
        ]:
            items.append(dict(id=f"J{len(items) + 1:02d}", type="judgment", case_id=r.CaseID, question=q, answer="",
                              answer_source="to be filled with the agreed label of the two blind labellers", evidence=[],
                              options=opts, tags=dict(kind=kind, rank=int(rank), store=int(r.Store), date=r.Date)))
        sheet.append(dict(rank=rank, case_id=r.CaseID, case_brief=brief(rank, cases, depts),
                          evidence_options=" | ".join(EVIDENCE.values()), strength_options=" | ".join(STRENGTH),
                          labeler_A_main_evidence="", labeler_A_other_evidence="", labeler_A_strength="", labeler_A_notes="",
                          labeler_B_main_evidence="", labeler_B_other_evidence="", labeler_B_strength="", labeler_B_notes=""))
    return items, sheet


if __name__ == "__main__":
    cases = pd.read_csv(DATA / "triage_v3_cases.csv")
    depts = pd.read_csv(DATA / "triage_v3_depts.csv")
    rep = report_items()
    cas = case_items(cases, depts)
    jud, sheet = judgment_items(cases, depts)
    allq = rep + cas + jud
    for q in allq:      # Santhosh reviewed the report and case items on 2026-10-31; judgment items wait for the blind labels
        q.setdefault("review_status", APPROVED if q["type"] in ("report", "case") else "draft")
    (EVAL / "golden_qa.json").write_text(json.dumps(allq, indent=1, default=str))
    with open(EVAL / "golden_qa_review.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "type", "case_id", "question", "reference_answer", "evidence", "quote_found_in_source",
                    "reviewer_ok (Y/N)", "reviewer_fix", "reviewer"])
        for q in allq:
            ev = " || ".join(f"[{e['doc_id']}] {e['quote']}" for e in q["evidence"]) or q.get("source_fields", "")
            found = all(e.get("found_in_source") for e in q["evidence"]) if q["evidence"] else ""
            ok = q["review_status"] == APPROVED
            w.writerow([q["id"], q["type"], q.get("case_id", ""), q["question"], q["answer"], ev, found,
                        "Y" if ok else "", "", "Santhosh Kasam (2026-10-31)" if ok else ""])
    pd.DataFrame(sheet).to_csv(EVAL / "labels_sheet.csv", index=False)
    missing = [(q["id"], e["doc_id"]) for q in rep for e in q["evidence"] if not e["found_in_source"]]
    print(f"{len(rep)} report ({sum(q['unanswerable'] for q in rep)} unanswerable), {len(cas)} case, {len(jud)} judgment = {len(allq)}")
    print("quotes not found:", missing or "none")
