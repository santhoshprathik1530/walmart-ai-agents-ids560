"""Step 1 of the RAGAS evaluation: write, for each RAG setup and golden report question, the question, the 5 retrieved
passages (search is deterministic, so they are exactly what the answer was written from), the saved answer and the
reference answer.

    python3 -m eval.ragas_export          -> eval/results/ragas_input.json   (no LLM calls)

Then run step 2 in the separate evaluation environment (RAGAS needs its own LangChain versions):
    ../.venv_eval/bin/python eval/ragas_eval.py
"""
from __future__ import annotations

import json

from agents.retrievers import VARIANTS, search
from eval.compare_rag import OUT, context, items


def main() -> list[dict]:
    qs = items()
    rows = []
    for v in VARIANTS:
        path = OUT / f"rag_answers_{v}.json"
        if not path.exists():
            print(f"{v}: no saved answers, skipped")
            continue
        ans = json.loads(path.read_text())
        for it in qs:
            if it["id"] not in ans:
                continue
            res = search(it["question"], v, 5, context(it))
            rows.append(dict(setup=v, id=it["id"], unanswerable=bool(it.get("unanswerable")), user_input=it["question"],
                             retrieved_contexts=[r["text"] for r in res], response=ans[it["id"]]["answer"],
                             reference=it["answer"]))
    (OUT / "ragas_input.json").write_text(json.dumps(rows, indent=1))
    print(f"{len(rows)} rows for {len({r['setup'] for r in rows})} setups")
    return rows


if __name__ == "__main__":
    main()
