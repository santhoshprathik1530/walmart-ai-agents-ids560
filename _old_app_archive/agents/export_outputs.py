"""Run the agents on the three example cases and save everything the deck quotes:
    python3 -m agents.export_outputs [runs] [retries]

Each case is run `runs` times (default 1; every run makes two LLM calls). If every run of a case stopped because no LLM
answered, the case is tried again after a minute, up to `retries` times (default 0). All errors are kept in the file, so it
shows how often the free models were busy.
"""
import json
import statistics
import sys
import time
from pathlib import Path

from . import engine as E, graph as G, llm, rag

APP = Path(__file__).resolve().parent.parent


def main(runs: int = 1, retries: int = 0):
    d = E.build(*E.load_data())
    rag._store()                                                   # load ChromaDB and the embedding model before timing
    g = G.build_graph(d)
    out = dict(cases={}, llm=dict(available=llm.available(), provider=llm.provider(), chain=llm.model_chain() if llm.available() else []))
    stats = json.loads((APP / "vectorstore" / "stats.json").read_text())
    for c in json.loads((APP / "data" / "cases.json").read_text())["cases"]:
        raw = json.loads((APP / "data" / c["payload"]).read_text())
        results = []
        for attempt in range(retries + 1):
            for _ in range(runs):
                t = time.time()
                final = g.invoke(dict(raw=raw, trace=[]))
                results.append((time.time() - t, final))
            if any(not f.get("error") for _, f in results) or attempt == retries:
                break
            time.sleep(60)
        ok = [(s, f) for s, f in results if not f.get("error")]
        secs, final = (ok or results)[-1]
        pl = final["pl"]
        case = dict(store=pl["store"], grain=pl.get("grain"), week_ending=pl["week_ending"], dept=pl.get("dept"), dept_name=pl["dept_name"],
                    region=pl["region"], actual=pl["actual_sales"], expected=pl["expected_sales"], deviation_pct=pl["deviation_pct"],
                    detected_by=c["detected_by"], runs=len(results), errors=[f["error"] for _, f in results if f.get("error")],
                    seconds=round(secs, 1), ms={tr["agent"]: tr["ms"] for tr in final["trace"]})
        if not final.get("error"):
            rep, res, plan, r = final["report"], final["evaluation"], final["plan"], final["rag"]
            case.update(
                status=rep["verdict"] if res["passed"] else "Needs human review", evaluation=res, report=rep,
                plan=dict(checks=plan["checks"], skipped=[k for k in E.menu(pl) if k not in plan["checks"]], queries=plan["queries"],
                          why=plan["why"], llm=plan["llm"]),
                evidence=final["facts"]["evidence"], rag_stats=r["stats"],
                passages=[dict(id=f"P{i + 1}", **{k: h[k] for k in ("doc", "doc_id", "published", "district", "relation", "score", "quote",
                                                                   "evidence_type")}) for i, h in enumerate(r["passages"])],
                reason_llm=next((tr.get("llm") for tr in final["trace"] if tr["agent"] == "Reasoning Agent"), None))
        out["cases"][c["id"]] = case
    out["vector_store"] = stats
    (APP / "data" / "agent_outputs.json").write_text(json.dumps(out, indent=1, default=float, ensure_ascii=False))
    for k, v in out["cases"].items():
        print(k, v.get("status", "ERROR"), v.get("report", {}).get("confidence"), f"{v['seconds']} s", v["errors"] or "")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1, int(sys.argv[2]) if len(sys.argv) > 2 else 0)
