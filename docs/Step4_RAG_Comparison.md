# Step 4: comparing retrieval setups (chunking + search)

2026-10-30. Built and run. Chart + table: `app/eval/results/rag_comparison.html`.
Re-run: `cd app && python3 -m eval.compare_rag --answers A2 E F && python3 -m eval.rag_chart`.

## What was compared

All setups use the same 68 reports and the same embedding model (all-MiniLM-L6-v2). The answering LLM (Claude Haiku) and the prompt are also the same across setups.

| | Chunking | Search | Filter | Reranker |
|---|---|---|---|---|
| A | fixed ~900 chars, 150 overlap (current ingest, 7,020 chunks) | vector | - | - |
| A2 | same as A | vector | time window + Fed district | - (this is the core of the current app) |
| B | same as A | keyword (BM25) | - | - |
| C | same as A | hybrid: vector + BM25, fused by rank | - | - |
| D | **section-aware**: paragraphs never cut, headings start a chunk, header line "report · published date · district · section" (7,829 chunks) | hybrid | - | - |
| E | same as D | hybrid | time window + Fed district | - |
| F | same as D | hybrid | time window + Fed district | cross-encoder (ms-marco-MiniLM-L-6, re-sorts the top 30) |

- **Time window:** only reports that cover, or were published in, the weeks of the 40 v3.3 cases (Jun 29 to Oct 26, 2012).
- **Fed district filter:** Beige Book text only from National plus the store's district. Walmart reports always pass.
- **Department filter:** the chunks carry no department label, so department terms stay in the question rather than a filter.

## Results (34 answerable report questions + 3 unanswerable)

| | Right passage in top 5 (Hit@5) | Right passage first (Hit@1) | MRR | Answer correct* | Faithful to passages* | Said "not in the sources" for the 3 unanswerable | Search time per query |
|---|---|---|---|---|---|---|---|
| A | 21% | 9% | 0.16 | | | | 0.11 s |
| A2 (current app) | 35% | 18% | 0.26 | 64% | 97% | 3/3 | 0.14 s |
| B | 21% | 12% | 0.18 | | | | 0.01 s |
| C | 35% | 15% | 0.22 | | | | 0.14 s |
| D | 68% | 29% | 0.45 | | | | 0.13 s |
| **E (recommended)** | **88%** | 44% | 0.60 | **88%** | **100%** | 3/3 | 0.15 s |
| F | 88% | **65%** | **0.76** | 84% | 100% | 3/3 | 1.2 s |

\*The LLM answers from the top 5 chunks only, and a second LLM call grades the answer against the reference (1 / 0.5 / 0). Answers were run for A2, E and F only, which cost about $0.08 in total. One F grade was set by hand because the grader's reply was cut off twice: the answer declined a question it should have answered, so it was graded wrong. A2 has 36 graded answers, because the model gave an empty reply to one question three times.

95% bootstrap intervals for Hit@5:
- A2: 21–53%
- D: 53–82%
- E and F: 76–97%

## What it means

1. **Chunking was the biggest gain (35% → 68%).** Fixed chunks cut sentences away from their context and sometimes glued prose onto tables. The noise filter then threw the whole chunk away. For example, the Q3 sentences on ticket (+1.4%) and traffic (+0.1%) were in no fixed chunk at all. Section chunks keep paragraphs whole. Their header also carries the report date and district, which the questions name ("July 18 Beige Book, Dallas District").
2. **Hybrid search alone did not help on fixed chunks (A2 ≈ C).** Keyword search helps once the chunks are clean (D).
3. **Filters add about 20 points (D → E).** Most wrong hits are the same topic from the wrong year or district, for example the 2011 Beige Book.
4. **The reranker puts the right passage first more often (Hit@1 44% → 65%), but finds no new passages (Hit@5 is the same).** Answers were no better (84% vs 88%; that gap is grader noise on 1–2 questions), and each query takes about 8x longer.
5. **No setup made things up.** All of them said "not in the sources" for the 3 unanswerable questions (Store 28 stockout, optical sales, Texas comps).

**Recommendation: E becomes the app default.** It ties with F on finding passages and on answers, is 8x faster, and needs no extra model. F stays available as an option (`search(..., variant="F")`) if we want the best quote shown first.

## Still missed by E (useful for the deck)

- **R15 (drought and food prices):** the word "risk" in the question pulls in the 10-Q's "market risk" section. The question and the source use different words.
- **W01 (10-Q segment net sales +3.6%):** the call transcript gives the same fact in other words. The answer was half right, even though the "right" 10-Q chunk was not found.
- **W04 (immunizations release):** found only with the reranker.

## Limits (say these on the slide)

- **34 questions is small.** Differences under about 15 points between setups are not reliable. The gaps between A2, D and E are larger than that.
- **The golden questions are my draft.** Santhosh + a teammate have not reviewed them yet (`golden_qa_review.csv`).
- **The grader is the same model family as the answerer.** Only the "numbers match" check (80% for E) is fully code-based.
- **We did not test whether the header or the paragraph splitting does more of the work in D.** Separating them would need a second 9-minute embedding run.

## Files

- `app/agents/retrievers.py`: section chunker, BM25, hybrid fusion, filters, reranker, `search(question, variant, k, ctx)`. Index cache in `app/vectorstore/variants/` (rebuilt automatically when missing).
- `app/models/ms-marco-MiniLM-L-6-v2/`: reranker (23 MB, ONNX, from Hugging Face Xenova).
- `app/eval/compare_rag.py`, `app/eval/rag_chart.py`.
- `app/eval/results/`:
  - `rag_comparison.csv/.json/.html`
  - `rag_items.csv` (rank per question per setup)
  - `rag_answers*.json/.csv` (every answer, with the grader's reason)

The app itself (`rag.py`) is not switched to E yet. That is part of step 5.

## Update 2026-10-31: standard metrics (nDCG, RAGAS) and a second grader
All 7 setups now have answers (Haiku, same prompt) and every metric is in one table:
`app/eval/results/rag_metrics_table.csv` (built by `eval/rag_metrics_table.py`; also in the JTA answers document).

| | A | A2 | B | C | D | **E** | F |
|---|---|---|---|---|---|---|---|
| Chunks | 7,020 | 7,020 | 7,020 | 7,020 | 7,829 | 7,829 | 7,829 |
| nDCG@10 | 0.20 | 0.30 | 0.23 | 0.26 | 0.55 | 0.68 | 0.80 |
| RAGAS context recall | 0.22 | 0.46 | 0.27 | 0.37 | 0.67 | **0.90** | 0.91 |
| RAGAS context precision | 0.29 | 0.35 | 0.25 | 0.35 | 0.55 | 0.63 | 0.77 |
| RAGAS answer correctness | 0.24 | 0.34 | 0.23 | 0.31 | 0.53 | **0.68** | 0.67 |
| RAGAS answer relevancy | 0.27 | 0.40 | 0.25 | 0.38 | 0.63 | **0.73** | 0.71 |
| Answer correct, Haiku grade | 53% | 64% | 33% | 44% | 74% | **88%** | 84% |
| Answer correct, Sonnet grade | | 44% | | | | **87%** | 88% |

RAGAS 0.4.3, judge Claude Haiku 5.5 (Santhosh's choice for cost), embeddings all-MiniLM-L6-v2. RAGAS faithfulness (~0.5
for every setup) is understated: the judge saw each passage without its report/date/district line. The re-run with that
line (`ragas_export.py` now adds it) stopped when the OpenRouter credit ran out ($35 used). Sonnet re-grade: E 87% vs
Haiku 88%, so Haiku was not going easy on E; it was on A2 (44% vs 64%), whose refusals Haiku counted as correct.
