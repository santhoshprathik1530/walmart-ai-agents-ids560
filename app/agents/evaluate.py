"""Evaluation: checks in code on the assistant's answer, before the dashboard shows it (the old 4-check version for the
first app is in _old_app_archive/).

evaluate_v3() checks each answer from agents/pipeline_v3.py:
  1. Numbers match the evidence   every number in the answer appears in the case, an evidence item or a passage
  2. Quotes are word for word     every quotation is a verbatim piece of a retrieved passage or a sales evidence item
  3. Every finding cites evidence each finding lists at least one id, and every id exists (evidence item or P1..P6)
  4. Answer is complete           allowed evidence_found; summary; 1-6 findings with title and text; next steps
  5. Guardrails respected        no "verified / confirmed cause", no "lost sales / revenue", no markdown causing a drop,
                                 no anomaly score read as a probability (the ML file's guardrails), and no doubt cast on the
                                 ML flag ("no action needed", "false alarm"): the ML team defines the exception
  6. Every finding is tagged      scope is walmart / department / region / store / outside / report / ml_note; a report
                                 finding cites a passage, the others cite a sales evidence item
  7. Covers the largest flagged department   the per-department part covers the department with the largest gap
"""
from __future__ import annotations

import re

from .llm import _norm, _nums, dumps, quotes_in


def _numbers(s: str) -> set[str]:
    """Numbers in a text, with trailing decimal zeros dropped so that 100.0% and 100% count as the same number."""
    return {n.rstrip("0").rstrip(".") if "." in n else n for n in _nums(s)}


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


# ------------------------------------------------------------------------------------------ Phase 2 (v3.3 cases)
_NEG = re.compile(r"\b(not|no|never|cannot|can't|isn't|aren't|wasn't|doesn't|don't|without|un|than|once|until|if|whether|"
                  r"would|could|to be|needs?|before|after|none|nothing|neither|nor|should|must|can|will)\b|n't\b", re.I)
_CERTAIN = re.compile(r"\b(verified|confirmed|proven|proves|definitely|certainly)\b", re.I)
_LOSS = re.compile(r"\blost (sales|revenue)\b|\b(revenue|sales) loss(es)?\b", re.I)
_AGAINST = re.compile(r"\b(no action (is )?needed|false (alarm|positive)|flag(ged)? (was|is) (wrong|incorrect|not justified)|"
                      r"not a real (drop|exception)|ask the ML team|(review|check|confirm|question) (the |its |their )?(ML )?"
                      r"forecasts?\b)", re.I)
_CAUSAL = re.compile(r"\b(caus\w*|led to|drove|driven|because|due to|explain\w*|result\w*|behind)\b", re.I)


def _sentences(text: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.!?])\s+|\n", text) if x.strip()]


def _text_v3(rep: dict) -> str:
    parts = [rep["summary"], rep["not_found"]] + [f"{f['title']}. {f['text']}" for f in rep["findings"]] + rep["next_steps"]
    parts += [f"{d['department']}: {d['what_supports_it']}" for d in rep["departments"]]
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


def evaluate_v3(rep: dict, facts: dict, top_depts: list[int]) -> dict:
    from .pipeline_v3 import EVIDENCE_FOUND, SCOPES
    text = _text_v3(rep)
    checks = [_check_numbers(text, facts), _check_quotes(text, facts, also_evidence=True)]   # may quote a sales fact too

    ev_ids, p_ids = {e["id"] for e in facts["evidence"]} | {"case"}, {p["id"] for p in facts["passages"]}
    uncited = [f["title"] or "(untitled)" for f in rep["findings"] if not f["evidence"]]
    unknown = sorted({x for f in rep["findings"] for x in f["evidence"] if x not in ev_ids | p_ids})
    ok3 = not uncited and not unknown
    checks.append(dict(name="Every finding cites evidence", passed=ok3,
                       detail=f"{len(rep['findings'])} finding(s), all cite real evidence" if ok3 else
                       "; ".join(([f"no evidence for: {', '.join(uncited)}"] if uncited else [])
                                 + ([f"unknown ids: {', '.join(unknown)}"] if unknown else []))))

    missing = []
    if rep["evidence_found"] not in EVIDENCE_FOUND:
        missing.append(f"evidence_found '{rep['evidence_found']}' is not allowed")
    if not rep["summary"]:
        missing.append("no summary")
    if not 1 <= len(rep["findings"]) <= 6 or any(not (f["title"] and f["text"]) for f in rep["findings"]):
        missing.append("findings need a title and text (1-6 findings)")
    if not rep["next_steps"]:
        missing.append("no next steps")
    checks.append(dict(name="Answer is complete", passed=not missing,
                       detail="evidence found, summary, findings, next steps" if not missing else "; ".join(missing)))

    probs = guardrail_problems(text) + [f"questions the ML flag: “{x[:70]}”" for x in _sentences(text) if _AGAINST.search(x)]
    checks.append(dict(name="Guardrails respected", passed=not probs,
                       detail="no certainty claims, lost-sales wording, markdown causality, probabilities or doubts about "
                              "the ML flag" if not probs else "; ".join(probs[:2])))

    bad = []
    for f in rep["findings"]:
        if f["scope"] not in SCOPES:
            bad.append(f"'{f['title']}' has no scope")
        elif f["scope"] == "report" and not set(f["evidence"]) & p_ids:
            bad.append(f"report finding '{f['title']}' cites no report")
        elif f["scope"] != "report" and not set(f["evidence"]) & ev_ids:
            bad.append(f"{f['scope']} finding '{f['title']}' cites no sales evidence")
    kinds = ", ".join(f"{n} {t}" for t in SCOPES if (n := sum(f["scope"] == t for f in rep["findings"])))
    checks.append(dict(name="Every finding is tagged", passed=not bad, detail=kinds if not bad else "; ".join(bad[:2])))

    names = {e["id"]: e["label"].split(" (")[0] for e in facts["evidence"]}
    top = top_depts[0] if top_depts else None
    want = names.get(f"dept_{top}", f"Dept {top}")
    covered = any(re.search(rf"\b{top}\b", d["department"]) or want.lower().removeprefix(f"dept {top} ") in d["department"].lower()
                  for d in rep["departments"]) if top else True
    checks.append(dict(name="Covers the largest flagged department", passed=covered,
                       detail=f"{want} is covered" if covered else f"{want} (largest gap) is not covered"))
    return dict(passed=all(c["passed"] for c in checks), checks=checks)
