# Store Sales Assistant: AI agents for the ML team's flagged store-weeks (IDS 560 · Team 2)

```bash
cd app
pip install -r requirements.txt
python3 -m agents.ingest            # one time: report index (68 Walmart / Fed / NRF / EIA reports)
python3 -m agents.cases_v3          # triage the ML team's v3.4 cases (data/cases_v34/) -> data/triage_v3_*.csv
python3 -m agents.pipeline_v3       # run the assistant on all 40 cases -> data/agent_outputs_v3.json
python3 -m streamlit run dashboard.py
```

| Step | What it does | Code |
|---|---|---|
| Intake + triage | reads the ML case files; groups each flagged department by the ML team's four signals; picks the departments to look at first; similar stores; later weeks | `agents/cases_v3.py` |
| Orchestrator (LLM) | picks the departments to research, writes 2-4 report search questions | `agents/pipeline_v3.py` |
| RAG (setup E) | section-aware chunks, hybrid vector + BM25 search, time window + Fed district filter, 6 passages | `agents/retrievers.py` |
| Reasoning (LLM) | what happened, possible factors tagged sales data / report / forecast model, departments to check, next steps | `agents/pipeline_v3.py` |
| Evaluation (code) | 7 checks; a failed check shows "Answer needs a check" | `agents/evaluate.py` |
| Chat | follow-up questions: store lookup + report search + LLM + the same checks | `agents/chat_v3.py` |

Status follows the ML files: every case is "Analyst review required" (root cause not verified), in the ML priority order.

**LLM:** `OPENROUTER_API_KEY=...` and `LLM_MODEL=anthropic/claude-haiku-5.5,free` in `app/.env`. Batch runs and evaluation
use only the first model (no fallback); the dashboard's live runs may fall back to the free models.
**Evaluation:** `eval/compare_rag.py` (7 RAG setups), `eval/regrade_sonnet.py` (second grader), `eval/score_agent_v3.py`,
`eval/score_chat_v3.py`; golden Q&A in `eval/golden_qa.json`.

The first app (`app.py`, 3 example payloads) was retired on 2026-10-31: see `../_old_app_archive/`.
Department and region names are publicly inferred, not confirmed by Walmart.
