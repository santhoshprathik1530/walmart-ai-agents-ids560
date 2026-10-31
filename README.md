# Walmart AI Agents & Exception Detection (IDS 560, Team 2)

The ML team's model (Isolation Forest + Extra Trees, per-store MAD thresholds, v3.4) flags store-weeks where departments sold
below its forecast. This repository is the **AI agent and RAG** part: for each flag, the agent looks for evidence that
supports it, in the sales data and in public Walmart and Federal Reserve reports, and shows it to a store manager or analyst
in a Streamlit dashboard. The ML team defines the exception; the agent never re-judges it.

For each flagged store-week the agent checks:
- **Walmart overall that week**: all 45 stores against the ML forecast
- **The same department at every store**, and at the stores in the same region
- **The store's other departments** that week
- **Outside factors**: holiday, fuel price, temperature, unemployment, markdowns (store-level)
- **Reports**: Walmart earnings releases, call transcripts, 10-K / 10-Q, news releases, Fed Beige Books, NRF, EIA,
  searched for the same weeks and the store's Fed district (RAG setup E)

Then an LLM (Claude Haiku 5.5) writes the findings, each tagged with where it comes from, and 7 code checks test every
answer (numbers, quotes, citations, completeness, guardrails, tags, coverage) before it is shown.

## Folders
| Folder | What is in it |
|---|---|
| `app/` | the live system: `dashboard.py`, `agents/` (pipeline, RAG, evidence, checks, chat), `eval/` (golden Q&A, RAG comparison, RAGAS, graders), `data/` (ML case files v3.4, mapping tables, agent outputs). `app/README.md` has the details |
| `sources/` | the AI agent knowledge sources (68 public reports) and `MANIFEST.csv` with every URL |
| `docs/` | step-by-step write-ups (findings, golden Q&A, RAG comparison, agent run, dashboard, v3.4 switch) and the JTA |
| `deck/` | presentation decks and the scripts that build them |
| `_old_app_archive/`, `_backup_rules_version/`, `ui_demo/` | earlier versions, kept for reference |

## Run it
```bash
cd app
pip install -r requirements.txt
# 1. Kaggle data (not included: Kaggle's rules don't allow re-sharing). From
#    https://www.kaggle.com/c/walmart-recruiting-store-sales-forecasting/data put train.csv, features.csv, stores.csv in app/data/
# 2. LLM key: create app/.env with
#    OPENROUTER_API_KEY=...
#    LLM_MODEL=anthropic/claude-haiku-5.5,free
python3 -m agents.ingest            # builds the report index (a few minutes)
python3 -m agents.cases_v3          # reads the ML team's 40 v3.4 cases
python3 -m agents.pipeline_v3       # runs the agent on all 40 (saved answers are already in app/data/agent_outputs_v3.json)
python3 -m streamlit run dashboard.py
```

## Evaluation (app/eval)
- **RAG setups**: 7 setups (fixed vs section-aware chunks; vector, BM25, hybrid search; time + district filter; reranker)
  on 37 golden report questions: Hit@1, Hit@5, MRR, nDCG, RAGAS (faithfulness, answer relevancy, context precision,
  context recall, answer correctness), and answers graded by Haiku and by Sonnet. Winner: setup E (section chunks + hybrid
  search + time/district filter), right passage in the top 5 for 88% of questions vs 35% for the first version.
- **Agent**: 7 code checks on each of the 40 answers; chat tested on 20 golden case questions.
- **People**: two teammates blind-label 10 cases (`app/eval/labels_sheet.csv`).

Department and region names are publicly inferred, not confirmed by Walmart. Reports describe Walmart or a Fed district as
a whole, never one store. This is a class project, not affiliated with Walmart.
