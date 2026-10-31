"""Evaluation: four checks in code on the Reasoning Agent's answer, before the dashboard shows it.

  1. Numbers match the evidence   every number in the answer appears in the case, an evidence item or a passage
  2. Quotes are word for word     every quotation (20+ characters) is a verbatim piece of a retrieved passage
  3. Every factor cites evidence  each factor lists at least one id, and every id exists (evidence item or P1..P6)
  4. Answer is complete           allowed verdict and confidence; 1-6 factors with title and text; bottom line; next steps

All four pass -> the dashboard shows the answer. Any fails -> "Needs human review", with the failed checks named.

evaluate_v3() is the Phase 2 version for the v3.3 cases (agents/pipeline_v3.py): the same four checks plus
  (quotes may also copy a sales evidence item word for word)
  5. Guardrails respected        no "verified / confirmed cause", no "lost sales / revenue", no markdown causing a drop,
                                 no anomaly score read as a probability (the ML file's guardrails)
  6. Every factor is tagged      type is data / report / model; a report factor cites a passage, a data or model factor
                                 cites a sales evidence item
  7. Status agrees with the data the LLM's status matches the code triage (cases_v3.py); if not, a person decides
"""
from __future__ import annotations

import re

from .llm import _norm, _nums, dumps, quotes_in
from .reasoning import CONFIDENCE, VERDICTS


def _numbers(s: str) -> set[str]:
    """Numbers in a text, with trailing decimal zeros dropped so that 100.0% and 100% count as the same number."""
    return {n.rstrip("0").rstrip(".") if "." in n else n for n in _nums(s)}


def _text(rep: dict) -> str:
    parts = [f"{f['title']}. {f['text']}" for f in rep["factors"]] + [rep["ruled_out"], rep["bottom_line"]] + rep["next_steps"]
    return "\n".join(parts)


def _check_numbers(text: str, facts: dict) -> dict:
    bad = sorted(_numbers(text) - _numbers(dumps(facts)))
    return dict(name="Numbers match the evidence", passed=not bad,
                detail="every number is in the evidence" if not bad else "not in the evidence: " + ", ".join(bad[:5]))


def _check_quotes(text: str, facts: dict, also_evidence: bool = False) -> dict:
    sources = [_norm(p["text"]) for p in facts["passages"]] + ([_norm(dumps(facts["evidence"]))] if also_evidence else [])
    wrong = []
    for q in quotes_in(text):
        for frag in re.split(r"…|\.\.\.", q):                       # a quote may be trimmed with "..."
            f = _norm(frag).strip(" .,;:!?…'")
            if len(f) >= 12 and not any(f in s for s in sources):
                wrong.append(f[:60])
                break
    n_q = len(quotes_in(text))
    return dict(name="Quotes are word for word", passed=not wrong,
                detail=(f"{n_q} quote(s), all found in the reports" if n_q else "no direct quotes") if not wrong
                else "not found in the reports: “" + wrong[0] + "…”")


def evaluate(rep: dict, facts: dict) -> dict:
    text = _text(rep)
    checks = []

    checks += [_check_numbers(text, facts), _check_quotes(text, facts)]

    ids = {e["id"] for e in facts["evidence"]} | {p["id"] for p in facts["passages"]}
    uncited = [f["title"] or "(untitled)" for f in rep["factors"] if not f["evidence"]]
    unknown = sorted({x for f in rep["factors"] for x in f["evidence"] if x not in ids})
    ok3 = not uncited and not unknown
    checks.append(dict(name="Every factor cites evidence", passed=ok3,
                       detail=f"{len(rep['factors'])} factor(s), all cite real evidence" if ok3 else
                       "; ".join(([f"no evidence for: {', '.join(uncited)}"] if uncited else [])
                                 + ([f"unknown ids: {', '.join(unknown)}"] if unknown else []))))

    missing = []
    if rep["verdict"] not in VERDICTS:
        missing.append(f"verdict '{rep['verdict']}' is not allowed")
    if rep["confidence"] not in CONFIDENCE:
        missing.append(f"confidence '{rep['confidence']}' is not allowed")
    if not 1 <= len(rep["factors"]) <= 6 or any(not (f["title"] and f["text"]) for f in rep["factors"]):
        missing.append("factors need a title and text (1-6 factors)")
    if not rep["bottom_line"]:
        missing.append("no bottom line")
    if not rep["next_steps"]:
        missing.append("no next steps")
    checks.append(dict(name="Answer is complete", passed=not missing,
                       detail="verdict, confidence, factors, bottom line, next steps" if not missing else "; ".join(missing)))
    return dict(passed=all(c["passed"] for c in checks), checks=checks)


# ------------------------------------------------------------------------------------------ Phase 2 (v3.3 cases)
_NEG = re.compile(r"\b(not|no|never|cannot|can't|isn't|aren't|wasn't|doesn't|don't|without|un|than|once|until|if|whether|"
                  r"would|could|to be|needs?|before|after)\b|n't\b", re.I)
_CERTAIN = re.compile(r"\b(verified|confirmed|proven|proves|definitely|certainly)\b", re.I)
_LOSS = re.compile(r"\blost (sales|revenue)\b|\b(revenue|sales) loss(es)?\b", re.I)
_CAUSAL = re.compile(r"\b(caus\w*|led to|drove|driven|because|due to|explain\w*|result\w*|behind)\b", re.I)


def _sentences(text: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.!?])\s+|\n", text) if x.strip()]


def _text_v3(rep: dict) -> str:
    parts = [rep["what_happened"], rep["not_the_cause"], rep["bottom_line"], rep["learn_from"]]
    parts += [f"{f['title']}. {f['text']}" for f in rep["factors"]] + rep["next_steps"]
    parts += [f"{d['department']}: {d['why']} {d['action']}" for d in rep["departments_to_check"]]
    return "\n".join(p for p in parts if p)


def guardrail_problems(text: str) -> list[str]:
    out = []
    for s in _sentences(text):
        m = _CERTAIN.search(s)
        if m and not _NEG.search(s[:m.start()][-40:]):
            out.append(f"claims certainty: “{s[:70]}”")
        if _LOSS.search(s):
            out.append(f"treats the model gap as lost sales: “{s[:70]}”")
        if re.search(r"markdown", s, re.I) and _CAUSAL.search(s) and not _NEG.search(s):
            out.append(f"links markdowns to the drop: “{s[:70]}”")
        if re.search(r"\bprobabilit|\b\d+% chance", s, re.I):
            out.append(f"reads a score as a probability: “{s[:70]}”")
    return out


def evaluate_v3(rep: dict, facts: dict, code_status: str) -> dict:
    from .pipeline_v3 import CONFIDENCE, FACTOR_TYPES, STATUSES
    text = _text_v3(rep)
    checks = [_check_numbers(text, facts), _check_quotes(text, facts, also_evidence=True)]   # may quote a sales fact too

    ev_ids, p_ids = {e["id"] for e in facts["evidence"]}, {p["id"] for p in facts["passages"]}
    uncited = [f["title"] or "(untitled)" for f in rep["factors"] if not f["evidence"]]
    unknown = sorted({x for f in rep["factors"] for x in f["evidence"] if x not in ev_ids | p_ids})
    ok3 = not uncited and not unknown
    checks.append(dict(name="Every factor cites evidence", passed=ok3,
                       detail=f"{len(rep['factors'])} factor(s), all cite real evidence" if ok3 else
                       "; ".join(([f"no evidence for: {', '.join(uncited)}"] if uncited else [])
                                 + ([f"unknown ids: {', '.join(unknown)}"] if unknown else []))))

    missing = []
    if rep["status"] not in STATUSES:
        missing.append(f"status '{rep['status']}' is not allowed")
    if rep["confidence"] not in CONFIDENCE:
        missing.append(f"confidence '{rep['confidence']}' is not allowed")
    if not rep["what_happened"]:
        missing.append("no 'what happened'")
    if not 1 <= len(rep["factors"]) <= 6 or any(not (f["title"] and f["text"]) for f in rep["factors"]):
        missing.append("factors need a title and text (1-6 factors)")
    if not rep["bottom_line"]:
        missing.append("no bottom line")
    if not rep["next_steps"]:
        missing.append("no next steps")
    checks.append(dict(name="Answer is complete", passed=not missing,
                       detail="status, confidence, what happened, factors, bottom line, next steps" if not missing
                       else "; ".join(missing)))

    probs = guardrail_problems(text)
    checks.append(dict(name="Guardrails respected", passed=not probs,
                       detail="no certainty claims, lost-sales wording, markdown causality or probabilities" if not probs
                       else "; ".join(probs[:2])))

    bad = []
    for f in rep["factors"]:
        if f["type"] not in FACTOR_TYPES:
            bad.append(f"'{f['title']}' has no type")
        elif f["type"] == "report" and not set(f["evidence"]) & p_ids:
            bad.append(f"report factor '{f['title']}' cites no report")
        elif f["type"] in ("data", "model") and not set(f["evidence"]) & ev_ids:
            bad.append(f"{f['type']} factor '{f['title']}' cites no sales evidence")
    kinds = ", ".join(f"{sum(f['type'] == t for f in rep['factors'])} {t}" for t in FACTOR_TYPES)
    checks.append(dict(name="Every factor is tagged", passed=not bad, detail=kinds if not bad else "; ".join(bad[:2])))

    agree = rep["status"] == code_status
    checks.append(dict(name="Status agrees with the data", passed=agree,
                       detail=f"both say {code_status}" if agree else f"LLM says {rep['status']}, data rules say {code_status}"))
    return dict(passed=all(c["passed"] for c in checks), checks=checks)
