"""Orchestrator: a LangGraph state graph that runs the agents.

    intake -> plan (LLM) ->  evidence  --\\
                         \\-> rag       ---> reason (LLM) -> evaluate -> dashboard
    follow-up:  route -> tool -> answer

`intake` normalizes the payload (code). `plan` is the orchestrator's LLM: it picks Evidence Agent checks from a menu and writes
the RAG search questions. Evidence and RAG are separate graph nodes after plan, so LangGraph runs them in parallel. `reason` is
the LLM summarizer; `evaluate` checks its answer in code. If an LLM step gets no usable answer the graph stops with `error`.
Every node appends a trace entry (what it did, key numbers, milliseconds) that the Streamlit app streams live.
"""
from __future__ import annotations

import operator
import time
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from . import chat, evaluate as evaluation, llm, orchestrator, rag, reasoning
from .engine import ensure_checks, evidence_facts, menu, payload_from_handoff, payload_kind, run_checks, signals


class State(TypedDict, total=False):
    raw: dict
    pl: dict
    kind: str
    sig: dict
    plan: dict
    ev: dict
    rag: dict
    facts: dict
    report: dict
    evaluation: dict
    error: str
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


def _llm_line(m: dict) -> str:
    return f"LLM {m['model']} · {m['ms'] / 1000:.1f} s · {m['tokens_in']} in / {m['tokens_out']} out tokens"


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
        p = orchestrator.plan(pl, sig)
        if p.get("error"):
            return dict(sig=sig, error=p["error"], trace=[_t("Orchestrator", t0, [p["error"]])])
        p["districts"] = ["National"] + rag.allowed_districts(pl.get("fed_district"))
        n = len(menu(pl))
        lines = [f"Chose {len(p['checks'])} of {n} checks: {', '.join(p['checks'])}",
                 f"{len(p['queries'])} search questions: " + " | ".join(q["text"] for q in p["queries"]),
                 f"Report filter (from the payload): week {pl['week_ending']} · {', '.join(p['districts'])}"]
        if p["why"]:
            lines.append(f"Why: {p['why']}")
        lines.append(_llm_line(p["llm"]))
        return dict(sig=sig, plan=p, trace=[_t("Orchestrator", t0, lines, dict(checks=len(p["checks"]), queries=len(p["queries"])),
                                               llm=p["llm"])])

    def after_plan(s: State):
        return END if s.get("error") else ["evidence", "rag"]

    def evidence(s: State):
        t0 = time.time()
        pl = s["pl"]
        ev = run_checks(d, pl, s["plan"]["checks"])
        lines = [f"{f['label']}: {f['value']}" for f in evidence_facts(pl, ev)][:6]
        return dict(ev=ev, trace=[_t("Evidence Agent", t0, [f"Ran {len(ev['checks_run'])} checks on {n_rows:,} sales rows (pandas)"] + lines,
                                     dict(rows=n_rows, checks=len(ev["checks_run"])))])

    def rag_node(s: State):
        t0 = time.time()
        r = rag.retrieve(s["pl"], s["sig"], queries=s["plan"]["queries"])
        st = r["stats"]
        return dict(rag=r, trace=[_t("RAG Agent", t0, [
            f"{st['chunks_in_store']:,} chunks → {st['chunks_after_filter']:,} after time + region filter ({st['reports_after_filter']} of {st['reports_in_store']} reports)",
            f"{st['queries']} queries → {st['candidates']} candidates → re-ranked → {st['returned']} passages"], st)])

    def reason(s: State):
        t0 = time.time()
        out = reasoning.summarize(s["pl"], s["ev"], s["rag"]["passages"])
        if out.get("error"):
            return dict(facts=out["facts"], error=out["error"], trace=[_t("Reasoning Agent", t0, [out["error"]])])
        rep = out["report"]
        return dict(facts=out["facts"], report=rep, trace=[_t("Reasoning Agent", t0, [
            f"Verdict: {rep['verdict']} · confidence {rep['confidence']} · {len(rep['factors'])} possible factors",
            _llm_line(out["llm"])], dict(factors=len(rep["factors"])), llm=out["llm"])])

    def after_reason(s: State):
        return END if s.get("error") else "evaluate"

    def evaluate(s: State):
        t0 = time.time()
        res = evaluation.evaluate(s["report"], s["facts"])
        head = "All 4 checks passed → shown on the dashboard" if res["passed"] else "Failed → Needs human review"
        return dict(evaluation=res, trace=[_t("Evaluation", t0, [head] + [f"{'✓' if c['passed'] else '✗'} {c['name']}: {c['detail']}"
                                                                         for c in res["checks"]], dict(passed=res["passed"]))])

    g = StateGraph(State)
    for name, fn in [("intake", intake), ("plan", plan), ("evidence", evidence), ("rag", rag_node), ("reason", reason),
                     ("evaluate", evaluate)]:
        g.add_node(name, fn)
    g.add_edge(START, "intake")
    g.add_edge("intake", "plan")
    g.add_conditional_edges("plan", after_plan, ["evidence", "rag", END])
    g.add_edge("evidence", "reason")
    g.add_edge("rag", "reason")
    g.add_conditional_edges("reason", after_reason, ["evaluate", END])
    g.add_edge("evaluate", END)
    return g.compile()


def build_followup_graph(d, case: dict):
    """Follow-up graph for one finished investigation (`case` holds pl, ev, passages, report)."""
    pl, ev, rep, passages = case["pl"], case["ev"], case["report"], case["rag"]["passages"]
    res = case.get("evaluation")

    def route(s: ChatState):
        t0 = time.time()
        intent, arg = chat.route(s["question"])
        return dict(intent=intent, arg=arg, trace=[_t("Orchestrator", t0, [f"Routed to: {intent}" + (f" (Store {arg})" if arg else "")])])

    def tool(s: ChatState):
        t0 = time.time()
        look = chat.run_tool(d, pl, s["intent"], s["arg"])
        extra = ensure_checks(d, pl, ev, chat.needed_checks(pl, s["intent"]))
        if s["intent"] == "lookup_store":
            lines = [f"Looked up Store {s['arg']}: {'found' if look else 'no data'}"]
        elif extra:
            lines = [f"Ran checks the plan had skipped: {', '.join(extra)}"]
        else:
            lines = ["Used the evidence already gathered"]
        return dict(lookup=look, trace=[_t("Evidence Agent", t0, lines)])

    def answer(s: ChatState):
        t0 = time.time()
        text = chat.answer_rules(s["intent"], s["arg"], s["lookup"], pl, ev, rep, passages, res)
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
