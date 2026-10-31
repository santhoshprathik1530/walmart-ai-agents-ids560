"""Run the agents on the three example cases and save everything the deck quotes: python3 -m agents.export_outputs"""
import json
import statistics
import time
from pathlib import Path

from . import engine as E, graph as G, llm

APP = Path(__file__).resolve().parent.parent
RUNS = 3


def main():
    d = E.build(*E.load_data())
    g = G.build_graph(d)
    out = dict(cases={}, llm=dict(available=llm.available(), provider=llm.provider(), chain=llm.model_chain() if llm.available() else []))
    tries = []
    stats = json.loads((APP / "vectorstore" / "stats.json").read_text())
    for c in json.loads((APP / "data" / "cases.json").read_text())["cases"]:
        raw = json.loads((APP / "data" / c["payload"]).read_text())
        g.invoke(dict(raw=raw, trace=[]))                       # warm-up (model load, caches)
        times, per_agent, final = [], {}, None
        for _ in range(RUNS):
            t = time.time()
            final = g.invoke(dict(raw=raw, trace=[]))
            times.append(time.time() - t)
            for tr in final["trace"]:
                per_agent.setdefault(tr["agent"], []).append(tr["ms"])
            lt = final.get("llm_try")
            tries.append(dict(status="accepted" if final.get("explanation") else ("rejected" if lt else "no answer"),
                              model=(lt or {}).get("model"), ms=(lt or {}).get("ms"), tin=(lt or {}).get("input_tokens"), tout=(lt or {}).get("output_tokens")))
        rep, pl, rag = final["report"], final["pl"], final["rag"]
        out["cases"][c["id"]] = dict(
            store=pl["store"], grain=pl.get("grain"), week_ending=pl["week_ending"], dept=pl.get("dept"), dept_name=pl["dept_name"],
            region=pl["region"], actual=pl["actual_sales"], expected=pl["expected_sales"], deviation_pct=pl["deviation_pct"],
            detected_by=c["detected_by"], verdict=rep["verdict"], status=rep["status"], confidence=rep["confidence"],
            factors=rep["factors"], bottom_line=rep["bottom_line"], review=rep["review"], limitations=rep["limitations"],
            rag_stats=rag["stats"], queries=[dict(name=q["name"], text=q["text"], hits=q["hits"], ms=q["ms"]) for q in rag["queries"]],
            passages=[{k: h[k] for k in ("doc", "doc_id", "published", "district", "relation", "score", "quote", "evidence_type")} for h in rag["passages"]],
            explanation=(final.get("explanation") or {}).get("text"), explanation_model=(final.get("explanation") or {}).get("model"),
            seconds_median=round(statistics.median(times), 2), ms_median={k: round(statistics.median(v)) for k, v in per_agent.items()})
    ok = [x for x in tries if x["status"] == "accepted"]
    out["llm"].update(runs=len(tries), accepted=len(ok), rejected=sum(x["status"] == "rejected" for x in tries),
                      no_answer=sum(x["status"] == "no answer" for x in tries),
                      models=sorted({x["model"] for x in ok}), ms_median=round(statistics.median(x["ms"] for x in ok)) if ok else None,
                      tokens_in_median=round(statistics.median(x["tin"] for x in ok)) if ok else None,
                      tokens_out_median=round(statistics.median(x["tout"] for x in ok)) if ok else None)
    out["vector_store"] = stats
    (APP / "data" / "agent_outputs.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({k: dict(v["ms_median"], total_s=v["seconds_median"]) for k, v in out["cases"].items()}, indent=1))
    print(json.dumps(out["llm"], indent=1))


if __name__ == "__main__":
    main()
