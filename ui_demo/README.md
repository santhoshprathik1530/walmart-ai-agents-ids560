# Store Sales Assistant: dashboard UI demo

Just the screens, nothing behind them. The answers are recorded from real runs of our AI agents and saved in `data/demo_data.json`,
so there is no backend, no AI key and no internet needed.

## Run it

You need Python 3.9 or newer.

```bash
cd ui_demo
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 -m streamlit run app.py
```

It opens at http://localhost:8501. If you see an error about `width="stretch"` or `on_dismiss`, update Streamlit: `pip install -U streamlit`.

## What to try

- Use the filters (Store, Region, Week, Category), the sort menu and **Reset**.
- Click **Find out why** on a week. A short progress animation plays, then the answer appears:
  verdict banner, why it happened, what to do next, and the sources.
- In the answer, click the suggested questions to see follow-up answers, and open
  **Show the report quotes** and **Show how the answer was checked**.

## Notes

- Three example weeks are loaded: Store 2 (whole store), Store 7 (Electronics), Store 13 (Candy & Tobacco).
  The filters list all 45 stores so the page looks the same when more weeks are added.
- Typed follow-up questions get a "demo only" reply; the four suggested questions have recorded answers.
- The Walmart Spark logo in `assets/` is the official one from brandcenter.walmart.com. Don't edit it.
- Region and department names are publicly inferred, not confirmed by Walmart.
