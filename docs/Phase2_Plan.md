# Phase 2 plan: AI agent on the ML team's v3.3 exceptions

Draft for Santhosh, 2026-10-30. Content only; nothing is built yet.

## 1. What the new ML output looks like

Input: `walmart_rag_cases_v3_3.zip` (Downloads), 40 JSON files, one per store-week, ranked 1-40.

| | Old payloads (3 cases) | New v3.3 (40 cases) |
|---|---|---|
| Unit | one store or one store x dept | one store-week, with 3-16 flagged departments inside (302 dept rows) |
| Model | Extra Trees vs 4-week baseline | Isolation Forest screen, then Extra Trees residuals with a Global MAD filter |
| Period | Jan / Apr / Aug 2012 | evaluation window 2012-07-20 to 2012-10-26 only (11 weeks, 18 stores) |
| Priority | none | `priority_rank` = sum of flagged dept shortfalls |
| Extra | - | markdowns (MarkDown1-5), 4/8-week and prior-year history per dept, cross-store overprediction rate, 4 diagnostic signals, guardrails, candidate hypotheses |

Things the data already says (before any AI):
- Signals across the 302 flagged dept rows: recent decline 220, prior-year seasonal decline 166, chain-wide overprediction (70%+ of stores) 153, forecast overprediction 57.
- Most-flagged departments are seasonal: 36 Outerwear & Swimwear (27), 56 Horticulture (18), 31 Accessories, 3 Stationery (back to school). In Aug-Sep these fall off their summer peak, so many flags are likely "forecast too high for end of season", not a store problem.
- Rank 1 (Store 39, Sep 7, after Labor Day): Stationery expected $76.6K, actual $28.0K, but last year's same week was $17.0K, so actual is *above* last year.
- All 40 cases have markdowns recorded. The JSON forbids claiming markdown causality.
- **No per-store threshold is in the files.** The text says "Global MAD". See question Q1.
- `retrieved_documents` is empty: the ML team expects our agent to fill it.

## 2. Agent flow for the new cases (changes to app/)

1. **Intake** reads v3.3 directly (new loader; old 3 payloads kept as legacy).
2. **Triage per department** (code): label each flagged dept with one primary pattern from its signals:
   - *End-of-season / seasonal forecast gap* (seasonal decline + chain-wide overprediction)
   - *Chain-wide drop* (most stores down the same week)
   - *Store-only drop* (store down, peers fine) -> the ones a manager must act on
   - *Data or model issue* (forecast > 2x seasonal baseline, too little history)
3. **Orchestrator LLM** picks checks and writes search questions per case (same design as now), plus the 5 `questions_for_agent` from the JSON.
4. **Evidence Agent** adds: peer stores (same dept, same week, same type/size, how they did vs their own baseline), department and fiscal-period linking (dept -> merch unit -> Walmart quarter -> what Walmart said about that unit that quarter).
5. **RAG Agent** retrieves time-aligned report passages (Q2/Q3 FY13 releases and calls, Jul/Aug/Oct 2012 Beige Books, EIA).
6. **Reasoning Agent** writes: what happened, contributing factors (each tagged *data* / *report* / *model estimate*), evidence, recommendation, confidence. Follows the JSON guardrails; never says "verified cause".
7. **Evaluation**: current 4 code checks + 2 new ones (guardrails respected, every factor tagged).
8. Batch run on all 40 cases, cached to `data/agent_outputs_v3.json` so the dashboard opens instantly (~40 x $0.002 = about $0.10 with Haiku).

## 3. Ground truth Q&A and RAG comparison (points 6 and 7)

How ground truth works, simply: we write questions whose correct answer we can find ourselves in the sources, note the answer and *which passage* holds it, then score each RAG setup on whether it finds that passage and gives that answer.

Golden set (target ~60 questions, in `eval/golden_qa.csv`):
- ~25 report questions ("What did Walmart say about apparel comps in Q2 FY13?") -> answer + source file + page/section.
- ~20 case questions from the 40 exceptions ("Which department has the largest shortfall at Store 39 on Sep 7?") -> answer computed from the JSON / train.csv (exact, no judgment).
- ~15 judgment questions on ~10 cases (main factor, act or not) -> labelled by two teammates independently (the human eval already planned), agreement measured.
- Drafted by me from the sources, checked by you or a teammate. Never generated and accepted by the LLM alone.

RAG variants to compare (same golden set, same LLM):

| Variant | Chunking | Retrieval |
|---|---|---|
| A (current) | fixed size | dense (MiniLM in Chroma) |
| B | fixed size | BM25 keyword |
| C | fixed size | hybrid dense + BM25 |
| D | section/paragraph-aware chunks with document+date header | hybrid |
| E | D | hybrid + time/department metadata filter (only reports near the case week) |
| F | D | E + reranker (cross-encoder) |

Metrics: retrieval Hit@5 and MRR (did the right passage come back), answer correctness (exact for numbers, LLM-judge + spot-check for text), faithfulness (claims backed by retrieved text), latency and cost. Output: one comparison table + chart for the deck; winning variant becomes the app default.

## 4. New dashboard (Streamlit, Walmart theme, rebuilt from scratch)

For a store manager. Five questions, five parts of the case page:

1. **Is there an exception?** Home: tiles (open exceptions, $ shortfall, stores affected), ranked list by priority with filters Store / Region / Week / Category, status chips (Action needed / Check before acting / No action needed).
2. **What is it?** Case page header: store, week, departments flagged, expected vs actual chart per dept with last year and 4-week lines.
3. **Why did it happen?** Plain-language factors with evidence tags and "Show the report quotes".
4. **What can I do now?** 2-4 concrete actions (check stock in Swimwear, confirm markdown timing, compare with Store X).
5. **Is another store doing better?** "Stores doing better" panel: same dept, same week, similar store type/size, ranked by vs-baseline; the top one is suggested as the store to learn from.

Plus a **chat assistant** on every case (Streamlit chat): answers follow-ups using the case data + RAG, cites sources, can run a skipped check, keeps history per case. Same evaluation checks on chat answers.

Theme: True Blue #0053E2 header with the official Spark, Spark Yellow #FFC220 accents, white background, Bogle-like sans font (Bogle itself is Walmart-licensed, so a close open font).

## 5. More RAG sources (point 10), within the agreed list

Already have 59 reports (8 Walmart types, 24 Beige Books, 3 NRF, 10 EIA). For the Jul-Oct 2012 window, candidates:
- Walmart 10-Q filings FY13 Q1-Q3 (Walmart-original, quarterly segment and category detail).
- Walmart Q2 FY13 and Q3 FY13 earnings presentation slides / CFO commentary (Walmart IR).
- Walmart Oct 2012 Investment Community Meeting transcript (Walmart IR).
- Walmart corporate newsroom releases Jul-Oct 2012 (back-to-school, layaway, price events).
- Beige Book district pages (already in full reports; could split by district for better retrieval).
- NRF 2012 back-to-school survey (NRF, but a different report than the agreed holiday forecast -> needs your OK).

## 6. JTA capture (point 5)

Add `docs/JTA_log.md`: each week I log what was done against the CAP domains (III Data, IV Methodology, V Model Building, VI Deployment), with evidence links (files, metrics, screenshots). Mapping already visible:
- III T-1/T-2: knowledge sources + MANIFEST, v3.3 intake. T-3: payload validation (check_payload, reconciles flags). T-4: dept-season and peer relationships. T-5: triage findings above.
- IV T-1/T-3/T-4: RAG variant comparison; T-2: Streamlit, ChromaDB, OpenRouter/Claude.
- V T-1: agent architecture; T-1a/T-2: batch run + evaluation checks; T-3: chunking/retrieval tuning; T-4: agents + ML handoff; T-5: assumptions/limits (no ground-truth labels, mappings inferred).
- VI T-1: teammate labels vs agent; T-2: deck/report; T-3/T-4: dashboard requirements and app.
At the end this fills the JTA template (`IDS 560 - Job_Task_Analysis-Template- Fall 26.docx`).

## Decisions (Santhosh, 2026-10-30)

- Thresholds: ask the ML team for the per-store thresholds (and FINAL_hybrid_all_cases.csv, FINAL_hybrid_flagged_departments.csv, historical_et_predictions.csv). Message draft:
  > Hi team, the v3.3 case JSONs say "Global MAD" and don't include a threshold per store. Could you share the per-store threshold table and the three CSVs the JSONs reference (FINAL_hybrid_all_cases, FINAL_hybrid_flagged_departments, historical_et_predictions)? We want to show each store's threshold on the dashboard and compare peer stores' expected vs actual.
- New sources approved: Walmart 10-Q FY13 Q1-Q3, Walmart IR slides + Oct 2012 investment community meeting, Walmart newsroom Jul-Oct 2012. NRF back-to-school: not approved.
- Peer stores: same dept, same week, same store type and similar size band, ranked by change vs own baseline (train.csv).
- Golden Q&A: I draft, Santhosh + one teammate review.
- 2026-10-30: Step 7 (filling the JTA template, updating the deck) is not needed; docs/JTA_log.md stays as the record.
- 2026-10-30: Walmart-issued releases copied from PR Newswire (marked "SOURCE Wal-Mart Stores, Inc.") are OK as sources when Walmart's newsroom no longer hosts them; MANIFEST labels them "Walmart (issued via PR Newswire)".

## 7. Order of work

1. v3.3 intake + triage + peer stores (code, no LLM) -> review findings with you.
2. Golden Q&A draft -> you review.
3. New sources (after your OK) -> re-ingest.
4. RAG variants + comparison table.
5. Agent run on all 40 cases with winning RAG.
6. New dashboard + chat.
7. JTA log throughout; deck update last.
