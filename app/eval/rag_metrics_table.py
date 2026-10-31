"""One table of every metric for the 7 RAG setups (for the JTA document and the write-up).

    python3 -m eval.rag_metrics_table      -> eval/results/rag_metrics_table.csv  (no LLM calls)

Reads rag_comparison.csv / rag_items.csv (retrieval, answer grades), grader_comparison.json (Sonnet re-grade) and
ragas_summary.csv (RAGAS). Adds nDCG@10: 1 / log2(rank + 1) of the first passage that holds the golden quote, 0 if it is
not in the top 10, averaged over the 34 answerable questions.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from agents.retrievers import VARIANTS
from eval.compare_rag import OUT

CHUNKING = {"fixed": "Fixed ~900 characters, 150 overlap", "section": "Section-aware ~800 characters, header line"}


def main() -> pd.DataFrame:
    comp = pd.read_csv(OUT / "rag_comparison.csv").set_index("variant")
    items = pd.read_csv(OUT / "rag_items.csv")
    ndcg = items.assign(g=lambda d: np.where(d.first_hit_rank.notna() & (d.first_hit_rank <= 10),
                                             1 / np.log2(d.first_hit_rank.fillna(1) + 1), 0)).groupby("variant").g.mean()
    son = json.loads((OUT / "grader_comparison.json").read_text())
    ragas = pd.read_csv(OUT / "ragas_summary.csv").set_index("setup") if (OUT / "ragas_summary.csv").exists() else pd.DataFrame()
    rows = []
    for v, cfg in VARIANTS.items():
        c = comp.loc[v]
        r = ragas.loc[v] if v in ragas.index else {}
        rows.append({
            "Setup": v, "Description": cfg["label"].replace(" (current core)", "").replace(" (current app)", " (first app)"),
            "Chunking": CHUNKING[cfg["chunks"]], "Chunks": int(c.chunks),
            "Search": {"dense": "Vector", "bm25": "Keyword (BM25)", "hybrid": "Hybrid (vector + BM25, RRF)"}[cfg["method"]],
            "Filter": "Time + Fed district" if cfg["filter"] else "-", "Reranker": "Cross-encoder" if cfg["rerank"] else "-",
            "Hit@1": round(c.hit1, 3), "Hit@5 (Recall@5)": round(c.hit5, 3), "MRR@10": round(c.mrr, 3), "nDCG@10": round(ndcg[v], 3),
            "Search ms": round(c.ms),
            "Answer correct (Haiku grade)": round(c.correct, 3), "Faithful (Haiku grade)": round(c.faithful, 3),
            "Answer correct (Sonnet grade)": son[v]["sonnet_correct"] / 100 if v in son else None,
            "Unanswerable refused": c.refused_unanswerable,
            **{f"RAGAS {k.replace('_', ' ')}": (round(float(r[k]), 3) if len(r) and k in r else None)
               for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall", "answer_correctness")},
        })
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "rag_metrics_table.csv", index=False)
    return df


if __name__ == "__main__":
    print(main().T.to_string())
