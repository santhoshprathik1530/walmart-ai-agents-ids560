"""Orchestrator: a LangGraph state graph that runs the agents.

    intake -> plan ->  evidence  --\\
                   \\-> rag       ---> reason
    follow-up:  route -> tool -> answer

`plan` (the orchestrator) normalizes the payload, computes cheap signals (calendar, fuel, weather) and sends one task to each
agent. Evidence and RAG are separate graph nodes in the same step, so LangGraph runs them in parallel. Every node appends a
trace entry (what it did, key numbers, milliseconds) that the Streamlit app streams live and the deck quotes.
"""
from __future__ import annotations

import operator
import time
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from . import chat, llm, rag, reasoning
from .engine import evidence_agent, evidence_agent_store, payload_from_handoff, payload_kind, signals


class State(TypedDict, total=False):
    raw: dict
    pl: dict
    kind: str
    sig: dict
    plan: dict
    ev: dict
    rag: dict
    report: dict
    explanation: dict | None
    llm_try: dict | None
    trace: Annotated[list, operator.add]


class ChatState(TypedDict, total=False):
    question: str
    intent: str
    arg: int | None
    lookup: dict | None
    answer: dict
    trace: Annotated[list, operator.add]


def _t(agent: str, t0: float, lines: list[str], numbers: dict | None = None, **extra) -> dict:
    return dict(agent=agent, ms=round((time.time() - t0) * 1000), lines=lines, numbers=numbers or {}, **extra)


def build_graph(d, n_scan: int | None = None):
    """Compile the investigation graph for a loaded Data object."""
    n_rows = n_scan or len(d.tr)

    def intake(s: State):
        t0 = time.time()
        kind = payload_kind(s["raw"])
        pl = payload_from_handoff(d, s["raw"])
        what = "whole store" if pl.get("grain") == "store_week" else f"Dept {pl['dept']} {pl['dept_name']}"
        return dict(pl=pl, kind=kind, trace=[_t("Anomaly payload", t0, [
            f"Format: {dict(department_week='Extra Trees hand-off (store × dept × week)', store_week='primary anomaly payload (store × week)', internal='baseline detector (store × dept × week)')[kind]}",
            f"Store {pl['store']} · {what} · week ending {pl['week_ending']} · {pl['fiscal_period']}"],
            dict(deviation_pct=pl["deviation_pct"]))])

    def plan(s: State):
        t0 = time.time()
        pl = s["pl"]
        sig = signals(d, pl)
        queries = rag.build_queries(pl, sig)
        plan_ = dict(evidence=dict(checks=6 if pl.get("grain") != "store_week" else 6, grain=pl.get("grain")),
                     rag=dict(queries=queries, districts=["National"] + rag.allowed_districts(pl.get("fed_district"))))
        return dict(sig=sig, plan=plan_, trace=[_t("Orchestrator", t0, [
            "Two tasks sent in parallel: Evidence Agent (sales data) and RAG Agent (reports).",
            f"Signals: {', '.join(sig['calendar_flags']) or 'no calendar effect'}; fuel {sig['fuel']:.2f}; temp {sig['temp']:.0f}°F",
            f"RAG plan: {len(queries)} queries · districts {', '.join(plan_['rag']['districts'])}"], dict(queries=len(queries)))])

    def evidence(s: State):
        t0 = time.time()
        pl = s["pl"]
        ev = evidence_agent_store(d, pl) if pl.get("grain") == "store_week" else evidence_agent(d, pl)
        if pl.get("grain") == "store_week":
            lines = [f"Baseline {ev['baseline_avg']/1e6:.2f}M includes Christmas: {ev['christmas_in_baseline']}",
                     f"vs. same week last year {ev['yoy']*100:+.1f}% · all {ev['n_stores']} stores median {ev['chain_median_drop']*100:+.1f}%",
                     f"{len(ev['top'])} top shortfall departments, {ev['peak_share']*100:.0f}% December-peak"]
        else:
            lines = [f"Dept {ev['dept_quarter_yoy']*100:+.1f}% this quarter, down {ev['weeks_down']} of {ev['weeks_total']} weeks",
                     f"Chain {ev['chain_dept_quarter_yoy']*100:+.1f}% · peers in region: {len(ev['peers_q'])} stores",
                     f"Store total {ev['store_week_yoy']*100:+.1f}% vs. last year that week"]
        return dict(ev=ev, trace=[_t("Evidence Agent", t0, lines + [f"Scanned {n_rows:,} sales rows (pandas)"], dict(rows=n_rows, checks=6))])

    def rag_node(s: State):
        t0 = time.time()
        r = rag.retrieve(s["pl"], s["sig"], queries=s["plan"]["rag"]["queries"])
        st = r["stats"]
        return dict(rag=r, trace=[_t("RAG Agent", t0, [
            f"{st['chunks_in_store']:,} chunks → {st['chunks_after_filter']:,} after time + region filter ({st['reports_after_filter']} of {st['reports_in_store']} reports)",
            f"{st['queries']} queries → {st['candidates']} candidates → re-ranked → {st['returned']} passages"], st)])

    def reason(s: State):
        t0 = time.time()
        pl, ev, passages = s["pl"], s["ev"], s["rag"]["passages"]
        rep = reasoning.reason(pl, ev, passages)
        expl = reasoning.llm_explain(pl, ev, rep, passages)
        lines = [f"Verdict: {rep['verdict']} · confidence {rep['confidence']}",
                 f"{len([f for f in rep['factors'] if f['kind'] == 'factor'])} possible factors, {len(rep['quotes'])} quotes available"]
        extra = {}
        if expl and expl.get("text"):
            lines.append(f"LLM ({expl['model']}) wrote the explanation in {expl['ms'] / 1000:.1f} s ({expl['input_tokens']} in / {expl['output_tokens']} out tokens); every number and quote checked")
            extra = dict(llm=dict(model=expl["model"], ms=expl["ms"], tokens_in=expl["input_tokens"], tokens_out=expl["output_tokens"]))
        elif expl and expl.get("problems"):
            lines.append(f"LLM text rejected ({'; '.join(expl['problems'][:2])}); rule-based text used")
        else:
            lines.append("Rule-based text (no LLM key set)" if not llm.available() else "Rule-based text (LLM call failed)")
        return dict(report=rep, explanation=expl if expl and expl.get("text") else None, llm_try=expl,
                    trace=[_t("Reasoning Agent", t0, lines, dict(factors=len(rep["factors"])), **extra)])

    g = StateGraph(State)
    for name, fn in [("intake", intake), ("plan", plan), ("evidence", evidence), ("rag", rag_node), ("reason", reason)]:
        g.add_node(name, fn)
    g.add_edge(START, "intake")
    g.add_edge("intake", "plan")
    g.add_edge("plan", "evidence")
    g.add_edge("plan", "rag")
    g.add_edge("evidence", "reason")
    g.add_edge("rag", "reason")
    g.add_edge("reason", END)
    return g.compile()


def build_followup_graph(d, case: dict):
    """Follow-up graph for one finished investigation (`case` holds pl, ev, passages, report)."""
    pl, ev, rep, passages = case["pl"], case["ev"], case["report"], case["rag"]["passages"]

    def route(s: ChatState):
        t0 = time.time()
        intent, arg = chat.route(s["question"])
        return dict(intent=intent, arg=arg, trace=[_t("Orchestrator", t0, [f"Routed to: {intent}" + (f" (Store {arg})" if arg else "")])])

    def tool(s: ChatState):
        t0 = time.time()
        look = chat.run_tool(d, pl, s["intent"], s["arg"])
        return dict(lookup=look, trace=[_t("Evidence Agent", t0, [f"Looked up Store {s['arg']}: {'found' if look else 'no data'}"] if s["intent"] == "lookup_store"
                                           else ["Used the evidence already gathered"])])

    def answer(s: ChatState):
        t0 = time.time()
        text = chat.answer_rules(s["intent"], s["arg"], s["lookup"], pl, ev, rep, passages)
        out = chat.answer_llm(s["question"], s["intent"], s["lookup"], pl, ev, rep, passages, text)
        final = dict(text=out["text"], by=f"LLM ({out['model']})", tokens=(out["input_tokens"], out["output_tokens"])) if out else dict(text=text, by="rules")
        return dict(answer=final, trace=[_t("Reasoning Agent", t0, [f"Answer written by {final['by']}"])])

    g = StateGraph(ChatState)
    g.add_node("route", route)
    g.add_node("tool", tool)
    g.add_node("answer", answer)
    g.add_edge(START, "route")
    g.add_edge("route", "tool")
    g.add_edge("tool", "answer")
    g.add_edge("answer", END)
    return g.compile()


def investigate(d, raw: dict) -> dict:
    """Run the whole graph and return the final state (no streaming)."""
    return build_graph(d).invoke(dict(raw=raw, trace=[]))
