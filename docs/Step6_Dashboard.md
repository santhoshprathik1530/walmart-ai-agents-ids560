# Step 6: store manager dashboard + chat

> **Update 2026-10-31:** the agent no longer uses our own status rule (Action needed / Check before acting / No action needed, 10% / $2,000 / 70%), similar-store peers, signal groups or the recovery check. The ML team defines the exception; the agent only finds evidence that supports each flag. See `Supporting_Evidence_Design.md`. The parts below that use those are kept as history.


> **Update 2026-10-30:** the dashboard now shows the v3.4 cases and each store's threshold. Tiles now read 12 / 4 / 40 / $913.4K. See [Switch_to_v34.md](Switch_to_v34.md).


2026-10-30. Built and tested in the browser. New file `app/dashboard.py`; the old `app.py` is kept for the 3 legacy payloads.

Run (from `app/`): `python3 -m streamlit run dashboard.py`.
- This needs `data/agent_outputs_v3.json` from step 5. Only the chat calls the LLM.
- In this repo it is also the `store-dashboard` entry in `.claude/launch.json` (port 8502).

## Home page: is there an exception?

- **Header:** True Blue band with the official Walmart Spark, on a white page.
- **Tiles:** need action (11), to check before acting (5), flagged store-weeks (40 across 18 stores), and the total below the model's expectation ($775.4K, marked as an estimate).
- **Filters:** Store, Region, Week ending, Category (merch unit of the flagged departments), Status. Sort by: action first, ML priority, most below model, newest week.
- **List:** one card per store-week, 10 per page. Each card shows:
  - the status pill (icon + label, never colour alone);
  - store, week, region, Walmart quarter, holiday week and ML rank;
  - the biggest department gap and the number of departments flagged;
  - dollars below the model;
  - the assistant's bottom line;
  - a **Find out why** button.
- **Region chart:** "Where are the flagged weeks?" (dollars below the model by region) sits in an expander, to keep the page clean.

## Case page: the five manager questions, in order

1. **Is there an exception?**
   - Status banner with a plain meaning. When a check failed, it says why, e.g. "the assistant and the team's rule disagree on the status".
   - Tiles: departments flagged, dollars below the model, departments that dropped more than similar stores, confidence.
2. **What is it?**
   - "What happened" in plain words.
   - A chart per department (top 8): actual vs model expected vs the same weeks in earlier years. The colours passed the colour-blind palette check, and each series also has its own marker shape.
   - A full table on request.
3. **Why did it happen?** Possible factors, each tagged **Sales data**, **Walmart / Fed report** or **Forecast model**, plus "Not the cause". The report quotes are behind "Show the report quotes", with report name, date, district and a link.
4. **What can I do now?** Departments to check, each with why and an action; next steps; the data that would confirm a cause; the bottom line.
5. **Is another store doing better?** The assistant's "learn from" store, then a department picker with:
   - a chart of every similar store (same type, size ±25%), this week vs its own earlier years, with this store highlighted;
   - **Did it bounce back?** The 3 weeks after, vs earlier years (Back to normal / Mixed / Still down), labelled "not used to set the status";
   - the best 3 similar stores.
6. **Ask a follow-up question.** Chat with 3 suggested questions, built from the case:
   - how the best similar store did;
   - what Walmart said about this category;
   - what to check first.

   History is kept per case. Each answer shows "✓ numbers and quotes checked" or "⚠ could not verify …", plus its sources.

"How the assistant checked this answer" lists the 7 checks, the search questions, the report filter, the model and the run time.

## Live runs (added 2026-10-30)

- **Add a new case from the ML team** (home page): upload one or more case files in the v3.3 JSON format. The assistant:
  1. checks the file: required parts present, a known store, a Friday week in the sales data;
  2. runs the same code triage as the other 40 (similar stores, later weeks);
  3. runs the full agent, showing each step live;
  4. opens the case.

  It takes about 20 seconds and $0.003 per case. A file with the same case id as an existing case replaces it.
- **↻ Run the assistant again** (case page): re-runs that one case now and clears its chat.
- **Where it is saved:**
  - uploaded files: `app/data/cases_v3_uploaded/`;
  - live answers: `app/data/agent_outputs_v3_live.json`, which takes priority over the batch file;
  - "How the assistant checked this answer" shows "run live on <time>" or "batch run".
- A case that is uploaded but not finished shows **New** or **Try again**, with a "Run the assistant" button.
- **Tested:**
  - Upload and live run in Python, using a copy of the rank 40 file: 7/7 checks passed.
  - "Run again" in the browser on Store 31, Aug 3: about 20 s, with the live caption shown.
  - The browser tools here can't pick a file, so the upload button itself was not clicked in the browser.
  - Afterwards, the test upload and live answers were removed, so the app is back to the 40 batch answers.
- **Fixed in passing:** "What happened" and "learn from" used to drop dollar signs (Streamlit read `$…$` as maths).

## Chat assistant (`app/agents/chat_v3.py`)

- If the question names another store, code looks up that store's sales in the case's departments that same week, compared with its own earlier years.
- The question is also searched in the reports (setup E, same week window and Fed district as the case).
- The LLM answers in 2–4 sentences from those facts only.
- The answer is then checked in code for numbers, quotes and guardrails, the same way as the main answer.
- Cost: about $0.002 and 2–5 s per question.

**Golden test** (`python3 -m eval.score_chat_v3`, the 20 exact case questions):
- Every number in the reference appears in the answer for **17/20**.
- None of the 20 answers had a wrong number. Two of the three misses are rounding: the chat said −23.9% and +3.4% where the reference rounds to −24% and +3%. The third left out the percentage and department number.
- All 20 answers passed the chat's own checks.

## Tested in the browser

- Home page and tiles.
- The Status filter: "Check before acting" leaves 5 store-weeks.
- Store 28 case page, all six sections.
- The Store 10, Aug 10 review banner.
- A chat question naming Store 41: it used the store lookup and passed the checks.
- No server errors.

## Not done / next

- Upload has no size or count limit beyond Streamlit's; each case costs an LLM run.

- Light mode only, because the app is set to a white page.
- No login or store-level access: every manager sees all 40 cases.
- The chat's "learn from" only compares stores' numbers. The data cannot show what the better store did differently.
- The deck and the JTA report are not updated yet (step 7).
