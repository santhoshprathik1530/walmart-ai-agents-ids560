# Sales Exception Assistant: live AI agents (IDS 560 · Team 2)

```bash
cd app
pip install -r requirements.txt
python3 -m agents.ingest        # one time, ~2 min: builds the ChromaDB vector store from ../sources (68 reports, 7,020 chunks, ~6.5 min)
streamlit run app.py
```

Click **Ask agent** on an exception and the agents run for real, streamed live:

| Step | What it does | Code |
|---|---|---|
| Orchestrator | LangGraph graph. Code reads the payload; an **LLM plans**: picks data checks from a menu of 6 and writes 2–4 report search questions; code validates the plan | `agents/graph.py`, `agents/orchestrator.py` |
| Evidence Agent | runs only the chosen pandas checks on the Kaggle sales data (421,570 rows); returns labelled facts | `agents/engine.py` |
| RAG Agent | time + Fed-district filter inside ChromaDB, vector search with the LLM's questions, sentence-level re-rank, 6 passages | `agents/rag.py`, `agents/ingest.py` |
| Reasoning Agent | an **LLM summarizes** the facts and passages: verdict (Likely explained / Likely store issue), confidence, possible factors with cited evidence, next steps | `agents/reasoning.py` |
| Evaluation | 4 checks in code: numbers in the evidence, quotes word for word, every factor cites evidence, answer complete. Pass → shown; fail → **Needs human review** | `agents/evaluate.py` |

Three example cases (`data/cases.json`, payloads in `data/payloads/`): Store 7 Electronics (Extra Trees hand-off), Store 13 Candy & Tobacco
(baseline detector), Store 2 whole store (primary anomaly payload). Any other payload JSON (either format) can be uploaded in the app.

**Model:** `LLM_MODEL=anthropic/claude-haiku-5.5,free` in `app/.env` tries the paid model first and falls back to the free chain ("free"). Leave it out to use only the free models.

**LLM (required):** put `OPENROUTER_API_KEY=...` (a normal key, free models; tries laguna-s-2.1, gemma-4-31b, gemma-4-26b, laguna-xs-2.1 in order) or `ANTHROPIC_API_KEY=...` in `app/.env`. Each run makes two LLM calls (plan, answer). If no model answers (the free models are often rate-limited), the run stops with an error and a "Run the agents again" button.
`python3 -m agents.export_outputs [runs]` runs the three cases and saves `data/agent_outputs.json`, which the deck builder (`deck/builders/build_architecture_v3.py`) reads.
Start the app with `python3 -m streamlit run app.py` so it uses the same Python as the packages.
Phase 2 dashboard (v3.3 cases): `python3 -m streamlit run dashboard.py` (needs `python3 -m agents.pipeline_v3` first).

Department and region names are publicly inferred, not confirmed by Walmart.
