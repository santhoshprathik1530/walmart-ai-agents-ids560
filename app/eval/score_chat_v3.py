"""Ask the dashboard's chat assistant (agents/chat_v3.py) the 20 golden case questions and score the answers.

    python3 -m eval.score_chat_v3          (~20 LLM calls, about $0.04; cached in eval/results/chat_v3_golden.json)

Correct = every number in the reference answer appears in the chat answer (percent signs, $ and commas ignored).
Also reports how many answers passed the chat's own checks (numbers, quotes, guardrails).
"""
from __future__ import annotations

import json

from agents import chat_v3, llm, pipeline_v3
from agents.pipeline_v3 import OUT as RUN
from eval.compare_rag import EVAL, OUT


def main() -> dict:
    pipeline_v3.MODELS = llm.model_chain()[:1]      # every question on the same model, no fallback
    run = json.loads(RUN.read_text())
    path = OUT / "chat_v3_golden.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    for g in json.loads((EVAL / "golden_qa.json").read_text()):
        if g["type"] != "case" or g["id"] in cache or g["case_id"] not in run:
            continue
        a = chat_v3.answer(run[g["case_id"]], g["question"])
        if not a.get("text"):
            print(g["id"], a.get("error"))
            continue
        need, got = llm._nums(g["answer"]), llm._nums(a["text"])
        cache[g["id"]] = dict(question=g["question"], reference=g["answer"], answer=a["text"], kind=g["tags"]["kind"],
                              correct=need <= got, missing=sorted(need - got), checks_passed=a["passed"], ms=a["ms"], tokens=a["tokens"],
                              model=a["model"])
        path.write_text(json.dumps(cache, indent=1))
    vals = list(cache.values())
    return dict(n=len(vals), correct=sum(v["correct"] for v in vals), checks_passed=sum(v["checks_passed"] for v in vals),
                models=sorted({v.get("model", "not recorded") for v in vals}),
                wrong=[dict(kind=v["kind"], q=v["question"], ref=v["reference"], got=v["answer"], missing=v["missing"])
                       for v in vals if not v["correct"]],
                median_ms=sorted(v["ms"] for v in vals)[len(vals) // 2] if vals else None)


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
