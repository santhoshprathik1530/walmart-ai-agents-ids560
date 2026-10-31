"""Reasoning Agent: an LLM summarizes the evidence and the report passages into possible factors for a store user.

    in:   the case, the Evidence Agent's results as labelled facts (engine.evidence_facts), the RAG Agent's passages (P1..P6)
    out:  {"verdict", "confidence", "factors": [{"title", "text", "evidence": [ids]}], "ruled_out", "bottom_line", "next_steps"}

The LLM picks which numbers and quotes to use and writes the answer. Every number has already been computed in Python by the
Evidence Agent; the LLM only copies them. The answer is then checked in code by agents/evaluate.py before the dashboard shows it.
If no model returns a readable answer, summarize() returns {"error": ...} and the app asks the user to run again.
"""
from __future__ import annotations

from . import llm
from .engine import evidence_facts, money

VERDICTS = ("Likely explained", "Likely store issue")
CONFIDENCE = ("High", "Medium", "Low")
LIMITS = ["Department and region names are publicly inferred, not confirmed by Walmart.",
          "Reports describe Walmart or a Fed district as a whole, not this store.",
          "No unit, price or inventory data; markdowns are recorded per store, not per department."]

SYSTEM = (
    "You are a retail analyst explaining a Walmart sales exception to a store manager. Write short, plain sentences a store "
    "manager understands: no jargon (say 'compared with last year', not YoY, comps or 4-5-4), no field names or ids in the text "
    "(name the report instead, e.g. 'Walmart's Q3 earnings call'), and dates like 'Aug 24, 2012'. Only include reasons that "
    "help explain this drop; leave out report passages that are not relevant. "
    "Use ONLY the facts in the JSON: the case, the evidence items (computed from the sales data) and the report passages. "
    "Copy every number exactly as it is written in the facts; do not calculate, round or convert numbers. "
    "If you quote a passage, copy the words exactly inside quotation marks; otherwise paraphrase without quotation marks. "
    "Verdict: 'Likely explained' when a calendar or seasonal effect, or a drop shared by the comparable stores and the chain, "
    "explains the week; 'Likely store issue' when this store fell clearly more than comparable stores and the chain. "
    "Confidence: 'High' when the sales data and the reports agree; 'Medium' when part of the drop is unexplained; "
    "'Low' when the evidence is thin or conflicting. "
    "Give 2 to 4 possible factors. When a report passage is relevant, include what Walmart or the Federal Reserve said and "
    "name the report. Each factor lists the ids of the evidence items and passages it uses (e.g. "
    '"dept_quarter_yoy", "P1"). '
    'Reply with JSON only: {"verdict": "...", "confidence": "...", "factors": [{"title": "max 6 words", '
    '"text": "1-2 sentences", "evidence": ["id", ...]}], "ruled_out": "one sentence on what is not the cause", '
    '"bottom_line": "1-2 sentences", "next_steps": ["short action", ...]}')


def facts(pl: dict, ev: dict, passages: list[dict]) -> dict:
    what = "whole store" if pl.get("grain") == "store_week" else (
        f"Dept {pl['dept']} {pl['dept_name']} (name confidence: {pl.get('dept_confidence', 'n/a')})")
    case = dict(store=pl["store"], region=f"{pl['region']} (confidence: {pl.get('region_confidence', 'n/a')})",
                fed_district=pl.get("fed_district"), what=what, week_ending=pl["week_ending"], fiscal_period=pl["fiscal_period"],
                actual=money(pl["actual_sales"]), expected=money(pl["expected_sales"]),
                deviation=f"{pl['deviation_pct']:+.1f}%".replace("-", "−"), expected_method=pl.get("expected_method"))
    return dict(case=case,
                evidence=[dict(id=f["id"], label=f["label"], value=f["value"]) for f in evidence_facts(pl, ev)],
                passages=[dict(id=f"P{i + 1}", source=h["doc"], date=h["published"], district=h["district"],
                               kind=h["evidence_type"], text=h["text"]) for i, h in enumerate(passages)])


def _readable(obj):
    if not isinstance(obj, dict):
        return False, "not an object"
    if not isinstance(obj.get("factors"), list) or not obj["factors"]:
        return False, "no factors"
    return True, ""


def _clean(v: dict) -> dict:
    factors = []
    for f in v.get("factors", []):
        if isinstance(f, dict):
            ev = f.get("evidence", [])
            factors.append(dict(title=str(f.get("title", "")).strip(), text=str(f.get("text", "")).strip(),
                                evidence=[str(x) for x in (ev if isinstance(ev, list) else [ev])]))
    steps = v.get("next_steps", [])
    return dict(verdict=str(v.get("verdict", "")).strip(), confidence=str(v.get("confidence", "")).strip(), factors=factors,
                ruled_out=str(v.get("ruled_out", "")).strip(), bottom_line=str(v.get("bottom_line", "")).strip(),
                next_steps=[str(x).strip() for x in (steps if isinstance(steps, list) else [steps]) if str(x).strip()])


def summarize(pl: dict, ev: dict, passages: list[dict]) -> dict:
    f = facts(pl, ev, passages)
    if not llm.available():
        return dict(error="No LLM key is set (OPENROUTER_API_KEY or ANTHROPIC_API_KEY in app/.env).", facts=f)
    out = llm.complete_json(SYSTEM, "FACTS (JSON):\n" + llm.dumps(f) + "\n\nWrite the answer now as JSON.", _readable,
                            max_tokens=4000)
    if not out:
        return dict(error=f"The Reasoning Agent's LLM did not return a readable answer ({llm.last_error}).", facts=f)
    return dict(report=_clean(out["value"]), facts=f,
                llm=dict(model=out["model"], ms=out["ms"], tokens_in=out["input_tokens"], tokens_out=out["output_tokens"],
                         attempts=out["attempts"]))
