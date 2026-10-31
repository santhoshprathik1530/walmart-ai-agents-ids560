# Walmart AI Agents & Exception Detection (IDS 560, Team 2)

Owner of this section: Santhosh Kasam. Sponsor: Anjali Garg.
The ML team's Extra Trees model detects sales anomalies (store x dept x week). The AI agent's job is to give
POSSIBLE FACTORS for each anomaly using the sales data plus time-aligned public Walmart / Fed reports.

## Rules (from Santhosh / sponsor)
- Use ONLY Walmart-original sources and the originally agreed public sources (earnings releases, call transcripts,
  10-K, Fed Beige Book, NRF holiday forecast, EIA fuel). NO third-party/competitor sources, no CPI analysis for now.
- On early slides do not say "RAG"; say "AI agent knowledge sources".
- Keep it simple. Streamlit UI is for a store user: plain white background, no clutter. Current app.py (2026-10-12): Walmart
  colours, flagged weeks as cards with 'Find out why'; answer = verdict banner, 'Why it happened', 'What to do next', questions;
  report quotes / checks / trace behind two 'Show ...' expanders. Reasoning prompt asks for store-manager wording (no ids/jargon).
  Main page built for scale: blue header band with the official Walmart Spark (app/assets/walmart_spark.svg, from
  brandcenter.walmart.com spark-primary.zip; Spark Yellow on True Blue; never redraw it or put it next to the wordmark), filters
  Store / Region / Week / Category (merch unit) chosen by Santhosh (no city in data), tiles, sortable paginated list, region chart.
- Department/region mappings are publicly inferred (High/Medium/Unresolved); keep provenance clear; don't rely on
  internal Walmart knowledge to validate them.
- Content first, approval, then build when he says "just give me content".
- The ML team defines the exception (Santhosh, 2026-10-31): flags, per-store thresholds, priority order and status
  ("Analyst review required") come straight from the ML files. The agent never re-judges a flag and adds no metrics,
  cutoffs or statuses of its own; its only job is to find evidence that supports each flag (data comparisons using the ML
  team's own forecasts + the approved reports). Next steps never ask the ML team to review its forecast.

## Folders
- app/ : the live system (README.md has the run commands). Old app.py + its agents (LangGraph, 3 payloads) retired
  2026-10-31 -> ../_old_app_archive/. Live: dashboard.py (`python3 -m streamlit run dashboard.py`, launch.json
  'store-dashboard' port 8502, run with /opt/homebrew/bin/python3) on the ML team's v3.4 cases.
  Pipeline (agents/pipeline_v3.py): intake (cases_v3.py, ML numbers only) + evidence from the ML team's own forecasts
  (support.py, data/ml_v33_complete/per_store_mad_experiment/per_store_mad_department_flags.csv: all 45 stores x depts x
  Jul 20-Oct 26 2012; Walmart overall that week, same dept at every store and in the same EIA region, the store's other
  depts, outside factors) -> orchestrator LLM (search questions) -> RAG setup E (retrievers.py) -> reasoning LLM (findings
  tagged walmart/department/region/store/outside/report/ml_note, per-department support, not found, next steps,
  evidence_found Strong/Some/Little) -> evaluate.evaluate_v3, 7 code checks (incl. guardrails: no doubt cast on the ML flag)
  -> data/agent_outputs_v3.json. Failed check = "Answer needs a check". Batch runs pin one model (Haiku, no fallback).
  chat_v3.py = follow-ups. OPENROUTER_API_KEY + LLM_MODEL=anthropic/claude-haiku-5.5,free in app/.env.
  data/: Kaggle CSVs (not shared publicly), mapping tables, cases_v34/ (current), cases_v3/ + v33_archive/ (v3.3),
  v34_ourrule_archive/ (the 2026-10-30 run with our own status rule, superseded), ml_v34/, ml_v33_complete/.
- sources/ : original AI agent knowledge sources (Walmart releases/calls/10-K/10-Q/newsroom, Beige Books, NRF, EIA) + MANIFEST.csv. Input to agents.ingest.
- docs/ : Phase 2 (started 2026-10-30). Phase2_Plan.md (plan + Santhosh's decisions), Step1_Findings.md, JTA_log.md (log CAP
  domain tasks as we go; fills the IDS 560 JTA template at the end). New ML input = v3.3: 40 ranked store-week cases
  (Isolation Forest + Extra Trees Global MAD, Jul-Oct 2012); since 2026-10-30 v3.4 (per-store MAD thresholds, same 40
  store-weeks, 362 depts) in app/data/cases_v34/ (docs/Switch_to_v34.md). 2026-10-31 redesign to "supporting evidence
  only": docs/Supporting_Evidence_Design.md.
  app/eval/: golden Q&A (report_qa.json, build_golden.py -> golden_qa.json; 57 report+case items approved by Santhosh
  2026-10-31; 20 judgment items wait for the blind labels in labels_sheet.csv: main supporting evidence + strength).
  Step 4: retrievers.py has 7 RAG setups, compare_rag.py scores them; winner E (Hit@5 88%); regrade_sonnet.py re-grades
  the saved answers with Sonnet 5.5 (E 87% vs Haiku 88%; old setup A2 44% vs 64%); RAGAS (ragas 0.4.3 in ../.venv_eval, judge Haiku) via ragas_export.py + ragas_eval.py; all metrics in eval/results/rag_metrics_table.csv. OpenRouter credit ran out 2026-10-31 ($35 used): top up before more LLM runs. Step 7 (deck) dropped.
  JTA: docs/IDS 560 - JTA - AI Agents and RAG (Team 2).docx (Domains III-VI) and the all-domain answers doc.
- deck/ : 'AI Agents - Walmart Stakeholder Deck.pptx' = CURRENT deck for Walmart stakeholders (8 slides, white, Walmart colours:
  why an agent, knowledge sources, 5 architecture slides, evaluation; builders/build_walmart_deck.py). Santhosh wants it simple and
  clean: no footers, few labels, explanations in speaker notes.
  'AI Agents - Architecture v3 (LLM Orchestrator and Reasoning).pptx' = the 5 architecture slides in the old cream style
  (builders/build_architecture_v3.py reads app/data/agent_outputs.json, Store 7 case; re-export first, then rebuild).
  'AI Agents - Architecture v2 ...pptx' = same 5 slides for the old rule-based design (superseded).
  'AI Agents - Architecture, RAG, Evidence, Reasoning, Evaluation.pptx' = diagram-style slides (builders/build_agent_diagrams.py; the Evaluation
  slide still shows the removed second layer). 'Midterm Presentation (AI agent section updated).pptx' = older card-style version of the section (stale).

## Key cases (the 3 payloads of the retired old app; deck slides still quote them)
- Store 2, whole store, week ending 2012-01-06 (primary payload): $1.80M vs 4-wk baseline $2.46M (-26.7%). Agent verdict: Likely explained,
  post-Christmas baseline (+2.4% vs same week last year; all 45 stores median -25.3%). Conflicts with deck slides 29-32 wording (see notes to Santhosh).
- Store 7, Dept 72 Electronics, Colorado, week ending 2012-08-24: expected $45,010 vs actual $33,958 (-24.6%).
  Electronics Q3 FY13 -12.7% at the store vs chain -0.5%; Walmart reports cite entertainment/electronics deflation.
  Conclusion: mostly store-local (stock/product/local competition).
- Store 13, Dept 1 Candy & Tobacco, week ending 2012-04-20: expected $166,023 vs actual $30,201 (-81.8%);
  Easter timing shift (Apr 8 2012 vs Apr 24 2011), chain also -73% that week -> holiday-timing artifact.

## Evaluation
Retrieval: Hit@1/5, MRR on 37 golden report questions (code). Answers: correct/faithful graded by Haiku and by Sonnet.
Agent: 7 code checks on every answer (grounding, not whether the reason is right). Chat: reference numbers present +
Sonnet grade. People: two teammates blind-label 10 cases (main supporting evidence, strength) - not run yet.

## Dataset
Kaggle Walmart Recruiting Store Sales Forecasting: 45 stores, 81 depts, 2010-02-05 to 2012-10-26, Friday week-endings,
Walmart fiscal year ends Jan 31.
