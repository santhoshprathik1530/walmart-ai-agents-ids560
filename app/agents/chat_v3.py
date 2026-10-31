"""Chat assistant for one flagged case (dashboard.py). Answers a follow-up question; like the main answer, it looks for
evidence that supports the ML team's flag and never questions the flag itself.

    tools (code)   "Store 41" in the question -> that store's results in the case's flagged departments the same week,
                   against the ML forecast (the ML team's numbers, agents/support.py)
    RAG            the question is also searched (setup E, same week window and Fed district as the case) for new passages
    LLM            answers in 2-4 sentences from the case facts, the tool result and the passages only, citing ids
    check (code)   numbers, quotes and guardrails are checked like the main answer; the dashboard shows the result

answer(case_output, question, history) -> {text, cited, checks: [...], passed, model, ms, tokens}
"""
from __future__ import annotations

import re
import time

import pandas as pd

from . import evaluate, llm, pipeline_v3, retrievers, support
from .pipeline_v3 import GRACE, VARIANT, day, facts_for, pc, usd
from .retrievers import allowed_districts

SYSTEM = (
    "You are the assistant on a Walmart store manager's sales dashboard. Answer the manager's question about one flagged "
    "store-week in 2 to 4 short, plain sentences. Use ONLY the facts in the JSON: the case, the sales evidence, any store "
    "lookup, and the report passages. Copy numbers exactly as written; do not calculate new numbers. Quote a passage only "
    "word for word inside quotation marks. Name the department or report in the text, not ids. If the facts do not answer "
    "the question, say so plainly and say what data would. The ML team defines the exception: never question the flag, "
    "the forecast or the threshold, and never say no action is needed; look only for evidence that supports the flag. "
    "Never say a cause is verified or confirmed; say 'below the ML forecast', never 'lost sales'; markdowns are "
    "store-level and never explain a department's drop. "
    'Reply with JSON only: {"answer": "...", "evidence": ["ids you used"]}')


def store_lookup(case: dict, other: int) -> dict | None:
    """Another store's results in this case's flagged departments the same week, against the ML forecast."""
    date = pd.Timestamp(day(case["case"]["week_ending"])).strftime("%Y-%m-%d")
    if not support.covered(date):
        return None
    depts = [int(e["id"].split("_")[1]) for e in case["evidence"] if e["id"].startswith("dept_")]
    m = support.ml()
    g = m[(m.Store == other) & (m.Date == date) & m.Dept.isin(depts)].set_index("Dept")
    if g.empty:
        return None
    rows = [f"Dept {d}: {usd(g.Actual[d])} vs {usd(g.Expected[d])} forecast ({pc(g.Pct[d])}){', flagged by the ML team' if g.Flag[d] else ''}"
            for d in depts if d in g.index]
    return dict(id=f"store_{other}", kind="ML forecast", label=f"Store {other}, week ending {case['case']['week_ending']}",
                value="; ".join(rows))


def answer(case: dict, question: str, history: list[dict] | None = None) -> dict:
    t0 = time.time()
    evidence = list(case["evidence"])
    for n in sorted({int(x) for x in re.findall(r"\bstore\s*#?\s*(\d{1,2})\b", question, re.I)} - {case["case"]["store"]})[:2]:
        look = store_lookup(case, n)
        evidence.append(look or dict(id=f"store_{n}", kind="data", label=f"Store {n}", value="no sales in these departments that week"))

    passages = list(case["rag"]["passages"])
    w = pd.Timestamp(day(case["case"]["week_ending"]))
    ctx = dict(start=w - pd.Timedelta(days=GRACE), end=w, districts=allowed_districts(case["case"]["fed_district"]))
    seen = {p["chunk_id"] for p in passages}
    for r in retrievers.search(question, VARIANT, 4, ctx):
        if r["id"] not in seen:
            m = r["meta"]
            passages.append(dict(id=f"P{len(passages) + 1}", source=m["title"], date=day(str(m["published"])),
                                 district="National" if m["district"] == "National" else f"{m['district']} Fed District",
                                 kind=m["evidence_type"], section=m.get("section", ""), url=m["url"], chunk_id=r["id"],
                                 queries=["chat"], text=r["text"]))
    facts = facts_for(case["case"], evidence, passages)
    facts["answer_so_far"] = dict(status=case.get("shown_status"), summary=case["report"]["summary"],
                                  evidence_found=case["report"]["evidence_found"])
    convo = "".join(f"{h['role'].upper()}: {h['text']}\n" for h in (history or [])[-4:])

    def ok(o):
        return (isinstance(o, dict) and bool(str(o.get("answer", "")).strip()), "no answer")
    out = llm.complete_json(SYSTEM, "FACTS (JSON):\n" + llm.dumps(facts) + (f"\n\nEARLIER IN THIS CHAT:\n{convo}" if convo else "")
                            + f"\n\nQUESTION: {question}", ok, max_tokens=1200, models=pipeline_v3.MODELS)
    if not out:
        return dict(text=None, error=f"The assistant did not answer ({llm.last_error}). Please try again.")
    text = str(out["value"]["answer"]).strip()
    cited = [str(x) for x in (out["value"].get("evidence") or [])]
    checks = [evaluate._check_numbers(text, facts), evaluate._check_quotes(text, facts, also_evidence=True)]
    probs = evaluate.guardrail_problems(text)
    checks.append(dict(name="Guardrails respected", passed=not probs, detail="ok" if not probs else probs[0]))
    used = [p for p in passages if p["id"] in cited]
    return dict(text=text, cited=cited, sources=used, checks=checks, passed=all(c["passed"] for c in checks),
                model=out["model"], ms=round((time.time() - t0) * 1000), tokens=out["input_tokens"] + out["output_tokens"])
