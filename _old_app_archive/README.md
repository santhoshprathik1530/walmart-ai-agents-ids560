# Old app (archived 2026-10-31)

The first Streamlit app (`app.py`) and its agents, for the 3 example payloads (Store 2, Store 7, Store 13): LangGraph
orchestrator, pandas evidence checks, ChromaDB RAG (setup A2), reasoning LLM, 4 code checks. Santhosh retired it on
2026-10-31; the live system is now `app/dashboard.py` + `app/agents/pipeline_v3.py` on the ML team's v3.4 cases.

Kept here so nothing is lost. It no longer runs from this folder (it imported `agents.*` from `app/`). To run it again,
copy `app.py`, `check_payload.py` back into `app/` and the files in `agents/` back into `app/agents/`
(`evaluate_with_old_checks.py` -> `app/agents/evaluate.py`), and add `langgraph>=0.2` to requirements.

Its saved outputs stay in `app/data/` because the older decks read them: `cases.json`, `payloads/`, `agent_outputs.json`.
`README_old_app.md` is the app README as it was.
