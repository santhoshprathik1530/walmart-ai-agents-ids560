"""Step 2 of the RAGAS evaluation: score every RAG setup with the standard RAGAS metrics (ragas 0.4.3).

    ../.venv_eval/bin/python eval/ragas_eval.py      (run from app/; reads eval/results/ragas_input.json from ragas_export.py)

Metrics (each 0-1, higher is better; https://docs.ragas.io):
  faithfulness        share of the answer's claims that the retrieved passages support
  answer_relevancy    how directly the answer addresses the question (a question generated back from the answer,
                      compared with the real one by embedding similarity; 1 generation, since OpenRouter returns one)
  context_precision   whether the passages that are useful for the reference answer are ranked at the top
  context_recall      share of the reference answer's claims that the retrieved passages contain
  answer_correctness  agreement of the answer with the reference (claim overlap + embedding similarity)
The 3 unanswerable questions are left out (there is no reference to recall); they are scored separately as refusals.

Judge: Claude Haiku 5.5 through OpenRouter (chosen by Santhosh for cost). Haiku also wrote the answers, so the
answer-side metrics may be a little generous; the passage-side metrics (context precision / recall) judge the search,
not Haiku's own text. Embeddings: all-MiniLM-L6-v2 (the same ONNX model the report index uses), run locally.
Writes eval/results/ragas_scores.csv (per question) and ragas_summary.csv (per setup). Cached per row.

Note (2026-10-31): the saved scores come from a run where each passage was given WITHOUT its "[n] report (date,
district)" line, so faithfulness is understated (~0.5 everywhere). ragas_export.py now adds the line; the re-run with it
stopped when the OpenRouter credit ran out. To redo: top up, delete ragas_scores.json, run ragas_export then this script.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd
from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI
from ragas import EvaluationDataset, RunConfig, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import answer_correctness, answer_relevancy, context_precision, context_recall, faithfulness
from tokenizers import Tokenizer

APP = Path(__file__).resolve().parent.parent
OUT = APP / "eval" / "results"
JUDGE = "anthropic/claude-haiku-5.5"
MINILM = Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2" / "onnx"
METRICS = [faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness]
answer_relevancy.strictness = 1    # OpenRouter returns one generation per call, so 1 question generated back per answer


def _key() -> str:
    for line in (APP / ".env").read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    return os.environ["OPENROUTER_API_KEY"]


class MiniLM(Embeddings):
    """all-MiniLM-L6-v2 (ONNX), mean-pooled and normalised: the report index's own embedding model."""

    def __init__(self):
        self.tok = Tokenizer.from_file(str(MINILM / "tokenizer.json"))
        self.tok.enable_truncation(256)
        self.tok.enable_padding(pad_id=0, pad_token="[PAD]")
        self.sess = ort.InferenceSession(str(MINILM / "model.onnx"), providers=["CPUExecutionProvider"])

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        enc = self.tok.encode_batch(texts)
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        out = self.sess.run(None, dict(input_ids=ids, attention_mask=mask, token_type_ids=np.zeros_like(ids)))[0]
        v = (out * mask[..., None]).sum(1) / mask.sum(1, keepdims=True)
        return (v / np.linalg.norm(v, axis=1, keepdims=True)).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def main():
    rows = [r for r in json.loads((OUT / "ragas_input.json").read_text()) if not r["unanswerable"]]
    cache_path = OUT / "ragas_scores.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    llm = LangchainLLMWrapper(ChatOpenAI(model=JUDGE, base_url="https://openrouter.ai/api/v1", api_key=_key(),
                                         temperature=0, max_tokens=3000, timeout=120))
    emb = LangchainEmbeddingsWrapper(MiniLM())
    for setup in dict.fromkeys(r["setup"] for r in rows):
        todo = [r for r in rows if r["setup"] == setup and f"{setup}|{r['id']}" not in cache]
        if not todo:
            continue
        ds = EvaluationDataset.from_list([{k: r[k] for k in ("user_input", "retrieved_contexts", "response", "reference")}
                                          for r in todo])
        res = evaluate(ds, metrics=METRICS, llm=llm, embeddings=emb, show_progress=False,
                       run_config=RunConfig(max_workers=8, timeout=180, max_retries=3))
        for r, sc in zip(todo, res.to_pandas().to_dict("records")):
            cache[f"{setup}|{r['id']}"] = {m.name: (None if pd.isna(sc.get(m.name)) else float(sc[m.name])) for m in METRICS}
        cache_path.write_text(json.dumps(cache, indent=1))
        print(setup, "done", flush=True)
    df = pd.DataFrame([dict(setup=k.split("|")[0], id=k.split("|")[1], **v) for k, v in cache.items()])
    df.to_csv(OUT / "ragas_scores.csv", index=False)
    summary = df.groupby("setup", sort=False)[[m.name for m in METRICS]].mean().round(3)
    summary["n"] = df.groupby("setup", sort=False).size()
    summary["missing_scores"] = df.groupby("setup", sort=False)[[m.name for m in METRICS]].apply(lambda g: int(g.isna().sum().sum()))
    summary.to_csv(OUT / "ragas_summary.csv")
    print(summary.to_string())


if __name__ == "__main__":
    main()
