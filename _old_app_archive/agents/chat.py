"""Follow-up questions. The orchestrator routes a question to a tool, then the answer is written by rules (default) or the LLM.

Routes:  other store ("How did Store 41 do?") -> Evidence Agent lookup | peers / chain | departments | markdowns | macro |
         sources | confidence | next step | why.   If the question needs a check the orchestrator's plan skipped, the Evidence
         Agent runs it now (needed_checks). The LLM, when available, only rewrites the tool result; it may not add facts.
"""
from __future__ import annotations

import re

from . import llm
from .engine import money, pct, store_lookup
from .reasoning import LIMITS

ROUTES = [("departments", ["department", "dept", "category", "which product"]),
          ("peers", ["other store", "peer", "region", "similar", "nearby", "chain", "everyone", "all store", "did other"]),
          ("markdown", ["markdown", "promo", "discount", "clearance"]),
          ("macro", ["fuel", "gas", "weather", "temperature", "cpi", "unemploy", "macro", "economy"]),
          ("sources", ["source", "evidence", "document", "report", "cite", "quote"]),
          ("confidence", ["confiden", "limit", "trust", "sure"]),
          ("next", ["recommend", "next", "action", "should"]),
          ("why", ["why", "explain", "cause", "reason", "baseline", "christmas", "holiday", "last year"])]


def route(question: str) -> tuple[str, int | None]:
    q = question.lower()
    m = re.search(r"\bstore\s+#?(\d{1,2})\b", q)
    if m:
        return "lookup_store", int(m.group(1))
    for intent, words in ROUTES:
        if any(w in q for w in words):
            return intent, None
    return "help", None


def needed_checks(pl, intent) -> list[str]:
    """Evidence Agent checks a follow-up answer needs (run now if the original plan skipped them)."""
    if pl.get("grain") == "store_week":
        return {"peers": ["all_stores"], "departments": ["departments"], "markdown": ["promo_macro"], "macro": ["promo_macro"]}.get(intent, [])
    return {"peers": ["regional_peers", "chain", "persistence"], "markdown": ["promo_macro"], "macro": ["promo_macro"]}.get(intent, [])


def run_tool(d, pl, intent, arg):
    return store_lookup(d, pl, arg) if intent == "lookup_store" else None


def answer_rules(intent, arg, lookup, pl, ev, rep, passages, res=None) -> str:
    store_grain = pl.get("grain") == "store_week"
    s = pl["store"]
    if intent == "lookup_store":
        if not lookup:
            return f"I could not find comparable data for Store {arg} in that week."
        if store_grain:
            return (f"**[Data]** Store {arg} ({lookup['region']}) sold {money(lookup['actual'])} that week: {pct(lookup['vs_baseline'])} vs. its own 4-week "
                    f"baseline and {pct(lookup['yoy'])} vs. last year. Store {s} was {pct(ev['deviation'])} and {pct(ev['yoy'])}.")
        return (f"**[Data]** Store {arg} ({lookup['region']}) {lookup['what']}: {pct(lookup['week_yoy'])} vs. last year that week and "
                f"{pct(lookup['quarter_yoy'])} this quarter (below last year in {lookup['weeks_down']} of {lookup['weeks_total']} weeks). "
                f"Store {s} was {pct(ev['dept_quarter_yoy'])} this quarter.")
    if intent == "peers":
        if store_grain:
            dr = ev["chain_drops"].sort_values()
            return (f"**[Data]** Against their own 4-week baseline, all {ev['n_stores']} stores fell a median {pct(ev['chain_median_drop'])} that week. "
                    f"Worst: " + ", ".join(f"Store {i} {pct(v)}" for i, v in dr.head(3).items()) + ". Best: "
                    + ", ".join(f"Store {i} {pct(v)}" for i, v in dr.tail(3).items())
                    + f". Store {s} is {pct(ev['deviation'])}, rank {ev['store_rank']} of {ev['n_stores']} (1 = worst).")
        pq = ev["peers_q"]
        rows = "; ".join(f"Store {int(r.Store)} {pct(r.YoY)}" for r in pq.sort_values("YoY").itertuples())
        return (f"**[Data]** {pl['dept_name']} this quarter vs. last year in other {pl['region']} stores: {rows or 'no comparable stores'}. "
                f"Across all 45 stores: {pct(ev['chain_dept_quarter_yoy'])}. Store {s}: {pct(ev['dept_quarter_yoy'])}.")
    if intent == "departments" and store_grain:
        rows = [f"- {x['dept_name']} (Dept {x['dept']}): {money(x['actual'])} vs. {money(x['expected'])} expected; {pct(x['yoy'])} vs. last year; "
                f"{'peaks in Nov–Dec' if x['holiday_peak'] else 'not a December-peak department'}" for x in ev["top"]]
        return "**[Data]** Largest shortfalls:\n" + "\n".join(rows)
    if intent == "markdown":
        x = ev["markdown"] / ev["markdown_avg"]
        extra = (" (" + ", ".join(f"{k.replace('MarkDown', 'MD')} {money(v)}" for k, v in pl["markdown_channels"].items()) + ")") if store_grain else ""
        return (f"**[Data]** Store {s} recorded {money(ev['markdown'])} in markdowns that week ({x:.1f}× its average week{extra}). Markdowns are "
                f"store-level and anonymized, so the data cannot show how much went to {pl['dept_name'].lower()} or whether it lifted sales.")
    if intent == "macro":
        return (f"**[Data]** Fuel ${ev['fuel']:.3f} (last year ${ev['fuel_ly']:.3f}), temperature {ev['temp']:.0f}°F (last year {ev['temp_ly']:.0f}°F), "
                f"CPI {ev['cpi']:.1f}, unemployment {ev['unemp']:.1f}%. None is unusual enough to explain a {pct(ev['deviation'])} week.")
    if intent == "sources":
        return "\n".join(f"**[{h['evidence_type']}]** “{h['quote']}” — *{h['doc']}, {h['published']}*" for h in passages) or "No time-aligned passages were found."
    if intent == "confidence":
        checks = "\n".join(f"- {'✓' if c['passed'] else '✗'} {c['name']}: {c['detail']}" for c in (res or {}).get("checks", []))
        return (f"Confidence: **{rep['confidence']}**\n\n**Evaluation**\n{checks}\n\n**Limits**\n" + "\n".join(f"- {l}" for l in LIMITS))
    if intent == "next":
        return "\n".join(f"- {r}" for r in rep["next_steps"])
    if intent == "why":
        return rep["bottom_line"] + "\n\n" + "\n".join(f"- **{f['title']}:** {f['text']}" for f in rep["factors"])
    return ("I can answer questions about: why it happened, how another store did (e.g. \"How did Store 41 do?\"), other stores, "
            "markdowns, fuel and weather, sources, confidence, and next steps.")


def answer_llm(question, intent, lookup, pl, ev, rep, passages, rule_text) -> dict | None:
    if not llm.available():
        return None
    facts = dict(case=dict(store=pl["store"], what=pl.get("dept_name"), week_ending=pl["week_ending"], deviation_pct=pl["deviation_pct"]),
                 verdict=rep["verdict"], confidence=rep["confidence"], bottom_line=rep["bottom_line"],
                 factors=[dict(title=f["title"], text=re.sub(r"\*\*", "", f["text"])) for f in rep["factors"]],
                 lookup=lookup, tool_answer=re.sub(r"\*\*", "", rule_text),
                 passages=[dict(id=h["chunk_id"], source=h["doc"], quote=h["quote"]) for h in passages])
    out = llm.complete_grounded(llm.SYSTEM_CHAT, f"FACTS (JSON):\n{llm.dumps(facts)}\n\nQUESTION: {question}", facts, max_tokens=500)
    return out if out and out.get("text") else None
