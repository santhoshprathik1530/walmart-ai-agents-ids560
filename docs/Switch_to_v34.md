# Switch from v3.3 to the ML team's v3.4 cases (per-store thresholds)

2026-10-30. Santhosh chose v3.4. Everything has been re-run on v3.4.

## Where the files came from

- **Requested from the ML team and now in the project:**
  - per-store thresholds;
  - `FINAL_hybrid_all_cases.csv`;
  - `FINAL_hybrid_flagged_departments.csv`;
  - `historical_et_predictions.csv`.
- **Source zips (Downloads):**
  - `Walmart V3.3 (complete)…zip` → `app/data/ml_v33_complete/` (all v3.3 CSVs plus `per_store_mad_experiment/`);
  - `rag_cases_v3_4_per_store…zip` → `app/data/cases_v34/` (40 case files) and `app/data/ml_v34/` (thresholds, all cases, flagged departments, v3.3-vs-v3.4 comparison).
- **The old v3.3 outputs are kept** in `app/data/v33_archive/`: triage, agent answers, golden set, and the eval results with the RAG comparison.

## What v3.4 changes

- **One threshold per store** (per-store MAD) instead of one Global MAD of −22.4%. Across the 45 stores the thresholds run from −17.7% to −29.3%; for our 18 stores, from −17.7% (Store 4) to −24.3% (Store 28). The ML file is `ml_v34/V34_per_store_mad_thresholds.csv`.
- **Same 40 store-weeks.** 32 of them have a new rank.
- **More flagged departments:** 362 instead of 302. 298 are in both versions, 64 are new, and 4 dropped out. The total below the model went from $775K to $913K.
- **A new file layout.** It also drops the guardrails and the questions for the agent.

## How the code reads v3.4

`cases_v3.from_v34()` turns each v3.4 file into the layout the rest of the code already reads.
- **Used exactly as the ML team gives them:** actual, expected, gap, residual, the store threshold, the 4- and 8-week medians, the share of other stores where the model was too high, the signals, and the markdowns.
- **Recomputed from `train.csv` / `features.csv`:**
  - the "same weeks in earlier years" median (same ISO week ±1, which reproduced v3.3 exactly), so this store and its similar stores are measured the same way. v3.4 uses a different window, and its figure is kept as `ml_same_season_median`;
  - fuel, temperature and MarkDown1 vs the 4 weeks before.
- **Rules and questions:** the v3.3 guardrails and questions are kept as constants, and v3.4's own caution is added.
- **Case ids** are written as `Store_28_2012-08-31`, as before. The ML team's `STORE_28_…` id is kept as `original_case_id`.
- **Uploads:** the dashboard accepts files in both the v3.3 and v3.4 formats.

## Results on v3.4

| | v3.3 run 2 | v3.4 |
|---|---|---|
| Triage status (Action / Check / No action) | 12 / 4 / 24 | 12 / 4 / 24 (2 cases changed: Store 27 Sep 28 Check → No action, Store 28 Sep 21 No action → Check) |
| Flagged dollars that look like forecast or season | 64% | 68% (forecast too high 46%, seasonal 22%) |
| All 7 checks passed | 39/40 | 39/40 (Store 24 Aug 31 used a number it calculated itself; its status is Check before acting anyway) |
| LLM status = code rule | 39/40 | **40/40** |
| Cases that use a report | 37 | 36 |
| Time / tokens per case | 18 s / 10K | 19 s / 12K |
| Chat on the 20 golden case questions, strict number match | 17/20 | 15/20. No wrong numbers. Three answers named the department without its number (the prompt says "no ids"), and two rounded differently. |

Shown to managers now: 24 No action needed, 12 Action needed, 4 Check before acting.

The golden set was rebuilt. The 37 report questions are unchanged, so the step 4 RAG comparison still holds. 22 case and judgment items have new answers, and the review and label sheets were regenerated. Nobody had filled them in yet.

The new information is shown to the manager and given to the agent:
- the store threshold, in the case header and the department table;
- "vs the store's limit" for each department.

Cost of the v3.4 run plus the chat re-test: about $0.16.
