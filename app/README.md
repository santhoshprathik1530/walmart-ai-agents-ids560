# Forecasting Exception Investigation: AI agents for the ML model's flagged store-weeks (IDS 560 · Team 2)

```bash
cd app
pip install -r requirements.txt
python3 -m agents.ingest            # one time: report index (68 Walmart / Fed / NRF / EIA reports)
python3 -m agents.retrievers        # one time: the section-aware index the agent searches (setup E)
export AGENT_CASE_SET=v4            # the ML model's final package: 127 store-weeks in data/cases_v4/
python3 -m agents.cases_v3          # read the v4 cases -> data/triage_v3_cases_v4.csv, data/triage_v3_depts_v4.csv
python3 -m agents.pipeline_v3 --ranks 1 2 3   # run the agent on these ML ranks -> data/agent_outputs_v3_v4.json
python3 -m streamlit run dashboard.py         # sets AGENT_CASE_SET=v4 itself
```

Saved answers: the Top 20 of the 127 v4 cases (run Nov 2, 2026 with Claude Haiku 5.5: 20 of 20 passed all 7 checks,
evidence 14 Strong / 6 Some). Ranks 21-127 show "Not run yet"; the dashboard can run any of them live (about 30 s).
Without `AGENT_CASE_SET=v4` the agent code reads the older v3.4 set (40 cases, `data/cases_v34/`, `agent_outputs_v3.json`).

| Step | What it does | Code |
|---|---|---|
| Intake | reads the ML case files (v4: Extra Trees + Global MAD, Isolation Forest A/B as supporting signals); one row per flagged department with the ML numbers, publicly inferred department name, region, Fed district, Walmart quarter | `agents/cases_v3.py` |
| Compare stores (code) | the same department at every store and in the region, the store's other departments, all 45 stores that week, outside factors, from the ML model's own forecasts | `agents/support.py` |
| Orchestrator (LLM) | picks the 1-3 departments with the largest gaps, writes 2-4 report search questions | `agents/pipeline_v3.py` |
| RAG (setup E) | section-aware chunks, hybrid vector + BM25 search, time window + Fed district filter, 6 passages | `agents/retrievers.py` |
| Reasoning (LLM) | evidence found (Strong / Some / Little), findings tagged by where they come from, departments, what was not found, next steps | `agents/pipeline_v3.py` |
| Evaluation (code) | 7 checks; a failed check shows "Answer needs a check" | `agents/evaluate.py` |
| Chat | follow-up questions: store lookup + report search + LLM + the same checks | `agents/chat_v3.py` |

The ML model defines the exception: flags, thresholds, priority order and status ("Needs analyst review") come from the
ML files and are never re-judged; the agent only looks for evidence that supports each flag.

**LLM:** `OPENROUTER_API_KEY=...` and `LLM_MODEL=anthropic/claude-haiku-5.5,free` in `app/.env`. Batch runs and evaluation
use only the first model (no fallback); the dashboard's live runs and chat may fall back to the free models.
**Evaluation:** `eval/compare_rag.py` (7 RAG setups), `eval/regrade_sonnet.py` (second grader), `eval/score_agent_v3.py`,
`eval/score_chat_v3.py`; golden Q&A in `eval/golden_qa.json`.
**Deploy:** `../deploy/DEPLOY.md` (Docker on the Oracle Cloud free VM).

The first app (`app.py`, 3 example payloads) was retired on 2026-10-31: see `../_old_app_archive/`.
Department and region names are publicly inferred, not confirmed by Walmart.
