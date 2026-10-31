"""Orchestrator planner: an LLM decides what evidence to gather for one flagged week.

    in:   the case (store, department, week, actual vs. expected), cheap signals computed in code (calendar, fuel, weather),
          and the menu of Evidence Agent checks for this payload's grain
    out:  {"checks": [ids from the menu], "queries": [{"name", "text"}], "why": one sentence}

The plan is validated in code: only menu ids are kept, 1-4 search questions. The time and region filter for the reports is
not the LLM's choice; it comes from the payload (week + the store's Fed district) and is added in rag.retrieve().
If no model returns a usable plan, plan() returns {"error": ...} and the app asks the user to run again.
"""
from __future__ import annotations

import re

from . import llm
from .engine import menu, money, pct

SYSTEM = (
    "You are the orchestrator of a retail sales investigation at Walmart. A detector flagged a week where sales came in below "
    "expected. Decide what evidence to gather before anyone explains it. "
    "1) Choose the data checks that help explain this drop, using ONLY ids from the menu. Pick enough checks to tell apart "
    "a one-week blip, a holiday or seasonal timing effect, a problem at this store, and a trend across all stores. "
    "2) Write 2 to 4 short search questions for a library of Walmart earnings releases, earnings call transcripts, 10-Ks and "
    "Federal Reserve Beige Book / NRF reports from the same period and region. Each question should name the product category "
    "or the economic topic (e.g. consumer spending, a holiday, prices), not the store number. "
    'Reply with JSON only: {"checks": ["id", ...], "queries": [{"name": "one word", "text": "question"}], '
    '"why": "one sentence"}')


def _case(pl: dict, sig: dict) -> dict:
    fuel_chg = sig["fuel"] / sig["fuel_ly"] - 1 if sig["fuel_ly"] == sig["fuel_ly"] else float("nan")
    return dict(
        store=pl["store"], region=pl["region"], fed_district=pl.get("fed_district"),
        what="whole store" if pl.get("grain") == "store_week" else f"Dept {pl['dept']} {pl['dept_name']} ({pl.get('merch_unit')} unit)",
        top_departments=[x["dept_name"] for x in pl.get("top_depts", [])] or None,
        week_ending=pl["week_ending"], fiscal_period=pl["fiscal_period"], actual=money(pl["actual_sales"]),
        expected=money(pl["expected_sales"]), deviation=f"{pl['deviation_pct']:+.1f}%", expected_method=pl.get("expected_method"),
        signals=dict(calendar=sig["calendar_flags"] or ["no holiday or holiday shift"],
                     fuel_vs_last_year=pct(fuel_chg), temperature=f"{sig['temp']:.0f}°F vs. {sig['temp_ly']:.0f}°F last year"))


def plan(pl: dict, sig: dict) -> dict:
    options = menu(pl)
    facts = dict(case={k: v for k, v in _case(pl, sig).items() if v is not None},
                 menu=[dict(id=k, question=v) for k, v in options.items()])

    def validate(obj):
        if not isinstance(obj, dict):
            return False, "not an object"
        checks = [c for c in obj.get("checks", []) if c in options]
        qs = [q for q in obj.get("queries", []) if isinstance(q, dict) and str(q.get("text", "")).strip()]
        if not checks:
            return False, "no valid check ids"
        if not qs:
            return False, "no search questions"
        return True, ""

    if not llm.available():
        return dict(error="No LLM key is set (OPENROUTER_API_KEY or ANTHROPIC_API_KEY in app/.env).")
    out = llm.complete_json(SYSTEM, "FACTS (JSON):\n" + llm.dumps(facts) + "\n\nReply with the plan as JSON.", validate, max_tokens=1500)
    if not out:
        return dict(error=f"The orchestrator LLM did not return a plan ({llm.last_error}).")
    v = out["value"]
    checks = list(dict.fromkeys(c for c in v["checks"] if c in options))
    queries = []
    for i, q in enumerate([q for q in v["queries"] if isinstance(q, dict) and str(q.get("text", "")).strip()][:4]):
        name = re.sub(r"[^a-z_]", "", str(q.get("name", "")).lower().replace(" ", "_"))[:20] or f"q{i + 1}"
        queries.append(dict(name=name, text=str(q["text"]).strip()[:200]))
    dropped = [c for c in v["checks"] if c not in options]
    return dict(checks=checks, queries=queries, why=str(v.get("why", "")).strip(), dropped=dropped,
                llm=dict(model=out["model"], ms=out["ms"], tokens_in=out["input_tokens"], tokens_out=out["output_tokens"],
                         attempts=out["attempts"]))
