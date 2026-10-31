"""Second grader: re-grade the saved RAG answers (and the chat answers) with Claude Sonnet 5.5 instead of Haiku.

    python3 -m eval.regrade_sonnet            (~130 Sonnet calls, about $0.50; cached in eval/results/*_sonnet*.json)

Why: the answers were written by Claude Haiku 5.5 and first graded by Haiku too, so the grader could go easy on its own
style. The answers are NOT re-written: the same saved answers (rag_answers_<setup>.json, chat_v3_golden.json) are graded
again with the same grading prompt and the same passages (search is deterministic, so the passages are rebuilt exactly).
Only the grader changes, so any difference is the grader's. Reports Sonnet's scores and how often the two graders agree.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from agents import llm
from agents.retrievers import search
from eval.compare_rag import EVAL, JUDGE_SYS, OUT, _passages, context, items

SONNET = ["anthropic/claude-sonnet-5.5"]
SETUPS = ["A2", "E", "F"]
CHAT_SYS = ("You grade a store-dashboard chat assistant. Reply with JSON only: {\"correct\": 1 or 0.5 or 0, \"why\": \"at most 20 "
            "words\"}. correct = 1 if the candidate gives the same facts and numbers as the reference (small rounding is fine, "
            "e.g. 30.2% vs 30%; naming a department without its number is fine), 0.5 if partly, 0 if wrong or missing.")


def grade(system: str, user: str) -> dict:
    for _ in range(2):                                       # one retry if the reply is cut off or not JSON
        j = llm.complete(system, user, 600, models=SONNET)
        try:
            return dict(json.loads(re.search(r"\{.*\}", j["text"], re.S).group(0)), model=j["model"])
        except Exception:
            continue
    return dict(correct=None, faithful=None, why=f"no usable reply ({llm.last_error})")


def rag() -> pd.DataFrame:
    qs = {it["id"]: it for it in items()}
    rows = []
    for v in SETUPS:
        path = OUT / f"rag_answers_{v}_sonnet.json"
        cache = json.loads(path.read_text()) if path.exists() else {}
        haiku = json.loads((OUT / f"rag_answers_{v}.json").read_text())
        for qid, h in haiku.items():
            it = qs[qid]
            if cache.get(qid, {}).get("correct") is None:
                ctx = _passages(search(it["question"], v, 5, context(it)))
                ref = "UNANSWERABLE (not in the sources)" if it.get("unanswerable") else it["answer"]
                cache[qid] = grade(JUDGE_SYS, f"Question: {it['question']}\nReference answer: {ref}\n"
                                              f"Candidate answer: {h['answer']}\n\nPassages:\n{ctx}")
                path.write_text(json.dumps(cache, indent=1))
            s = cache[qid]
            rows.append(dict(setup=v, id=qid, unanswerable=h["unanswerable"], haiku_correct=h["correct"],
                             sonnet_correct=s.get("correct"), haiku_faithful=h["faithful"], sonnet_faithful=s.get("faithful"),
                             sonnet_why=s.get("why")))
    return pd.DataFrame(rows)


def chat() -> pd.DataFrame:
    path = OUT / "chat_v3_golden_sonnet.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    src = json.loads((OUT / "chat_v3_golden.json").read_text())
    for qid, c in src.items():
        if cache.get(qid, {}).get("correct") is None:
            cache[qid] = grade(CHAT_SYS, f"Question: {c['question']}\nReference answer: {c['reference']}\nCandidate answer: {c['answer']}")
            path.write_text(json.dumps(cache, indent=1))
    return pd.DataFrame([dict(id=k, code_number_match=src[k]["correct"], sonnet_correct=v.get("correct"), why=v.get("why"))
                         for k, v in cache.items() if k in src])


def summary(r: pd.DataFrame, c: pd.DataFrame) -> dict:
    out = {}
    for v, g in r.groupby("setup", sort=False):
        a = g[~g.unanswerable]
        f = lambda col: round(pd.to_numeric(col, errors="coerce").mean() * 100)
        out[v] = dict(haiku_correct=f(a.haiku_correct), sonnet_correct=f(a.sonnet_correct),
                      haiku_faithful=f(g.haiku_faithful), sonnet_faithful=f(g.sonnet_faithful),
                      sonnet_refused_unanswerable=f"{int(pd.to_numeric(g[g.unanswerable].sonnet_correct).sum())}/{int(g.unanswerable.sum())}",
                      graders_agree=f"{int((g.haiku_correct.astype(float) == g.sonnet_correct.astype(float)).sum())}/{len(g)}")
    out["chat"] = dict(n=len(c), code_number_match=int(c.code_number_match.sum()),
                       sonnet_correct=float(pd.to_numeric(c.sonnet_correct).sum()),
                       sonnet_full_marks=int((pd.to_numeric(c.sonnet_correct) == 1).sum()))
    return out


if __name__ == "__main__":
    r = rag()
    r.to_csv(OUT / "rag_grades_haiku_vs_sonnet.csv", index=False)
    c = chat() if (OUT / "chat_v3_golden.json").exists() else pd.DataFrame(columns=["id", "code_number_match", "sonnet_correct"])
    c.to_csv(OUT / "chat_grades_sonnet.csv", index=False)
    s = summary(r, c)
    (OUT / "grader_comparison.json").write_text(json.dumps(s, indent=1))
    print(json.dumps(s, indent=1))
    print(r[r.haiku_correct.astype(float) != r.sonnet_correct.astype(float)][["setup", "id", "haiku_correct", "sonnet_correct", "sonnet_why"]]
          .to_string(index=False))
