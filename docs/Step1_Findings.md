# Step 1 findings: v3.3 intake, triage and peer stores (code only, no AI)

2026-10-30. Code: `app/agents/cases_v3.py` (`python3 -m agents.cases_v3`, about 3 s).
Inputs: the 40 ML case files (copied to `app/data/cases_v3/`), train.csv, stores.csv, dept/store mapping, fiscal calendar.
Outputs: `app/data/triage_v3_cases.csv` (40 rows), `triage_v3_depts.csv` (302 rows), `triage_v3_peers.csv` (4,220 peer rows).

## What the code does

1. **Links each flagged department** to its name, Walmart merchandise unit, store region / Fed district, fiscal period and holiday week.
   290 of the 302 rows fall in FY2013 Q3 (Aug-Oct 2012), 12 in Q2; 51 are in the Labor Day week (Sep 7).
2. **Peer stores**: same department and week, same store type, size within ±25% (falls back to all stores of that type if fewer than 3).
   Each peer's sales are compared with its own same-season median from earlier years (same ISO week ±1, the ML team's method).
   Check: this method reproduces the ML file's seasonal median for 298 of 302 departments exactly. The other 4 have no history (Store Supplies, dept 94).
3. **One pattern per department** (rules in order):

| Pattern | Rule | Depts | Modeled shortfall |
|---|---|---|---|
| Not enough history to judge | <2 seasonal weeks or <4 recent weeks | 6 | $0.7K |
| Store-only drop | ≥20% below last year **and** ≥20 points worse than peer median | 99 | $199K |
| Drop shared by similar stores | ≥20% below last year, peers similar | 67 | $80K |
| Forecast too high for the season | not 20% below last year; forecast >2x season or 70%+ of stores overpredicted | 89 | $370K |
| Normal seasonal slowdown | not 20% below last year; down vs recent weeks only | 41 | $126K |

4. **One status per case**:
   - Action needed (12): a store-only drop that is ≥$2,000 and ≥10% of the case's flagged shortfall.
   - No action needed (24): ≥70% of the shortfall is in shared / forecast / seasonal patterns.
   - Check before acting (4): everything else.

## Main findings

- **About two thirds (64%) of the flagged dollars are the forecast, not the store.** $496K of $776K is "forecast too high" or "normal seasonal slowdown": sales were in line with last year but Extra Trees expected more, mainly in back-to-school and summer departments (Stationery, kids' apparel, Swimwear, Horticulture).
- **Rank 1 (Store 39, Sep 7) needs no action.** Stationery: $28.0K actual vs $76.6K forecast, but +64% vs the same week in earlier years. Similar stores were +29% (median). All 10 departments are forecast/seasonal.
- **The ranking and "needs action" do not line up.** Of the top 6 cases by shortfall, only rank 2 is a store-only problem.
- **Strongest store-only case: rank 2, Store 28, Aug 31.** Dry Grocery, Frozen Food, Meat and Packaged Deli were 24-33% below last year while 17 similar stores were -5% to +6%. Best peers: Store 39 (+25% Dry Grocery), Store 34, Store 41. Grocery is not seasonal. But the next week the same departments were +25% to +56% vs earlier years (see recovery check below): sales look shifted by a week (short closure, delivery or data timing), not lost.
- **Other clear store-only cases:**
  - Store 21, Aug 3: Pharmacy -41% vs peers -2%; best peer Store 22.
  - Store 10, Aug 31: Stationery -25% vs peers +23%, in back-to-school week; best peer Store 9.
  - Store 4 / Store 2 / Store 27: Optical.
- **Small-dollar noise:** half the store-only departments are under $834 shortfall (Store Supplies, Stamps, Photo Lab). The $2,000 floor keeps them out of "Action needed".

## Recovery check: did it bounce back? (added 2026-10-30)

For every flagged department, the code also looks at the 1-3 weeks after the case week (data runs to Oct 26, 2012) and compares each with the same weeks in earlier years.
- It is **later data**. A manager would not have it on the day, so it never changes the pattern or the status.
- It is shown separately as "Did it bounce back?".

For the 16 departments that make a case "Action needed":

| After the case week | Depts | Examples |
|---|---|---|
| Back to normal | 9 | Store 28 Dry Grocery / Frozen / Meat (+25% to +56% the next week), Store 10 Stationery, Optical at Stores 2 and 4, Store 35 Sporting Goods |
| Mixed | 6 | Store 21 Pharmacy, Store 27 Ladieswear and Optical, Store 4 Lawn & Garden and Furniture, Store 10 Girlswear |
| Still down every week | 1 | Store 11 Cameras (-34% to -38% for three weeks) |

The 12 "Action needed" cases split into two groups:
- **One-week dips:** the manager should ask what happened that week, but nothing is still going on.
- **Ongoing drops:** Store 11 Cameras, and partly Store 21 Pharmacy and Store 27 Ladieswear. These are the "act now" cases.

Walmart filings from other years were not added for this check: they are company-level only and cannot show whether one store department dropped once or keeps dropping.

Columns: `AfterWeeksVsSeasonPct`, `After` in triage_v3_depts.csv; `StoreOnlyAfter` in triage_v3_cases.csv.

## Thresholds to agree on (your call)

These are mine, not the ML team's: 20% drop, 20-point gap vs peers, $2,000 / 10% materiality, 70% explained share, ±25% size band.
They should be listed as assumptions in the JTA (Domain V T-5) and tuned after the teammates label ~10 cases.

## Not done here

- **Per-store ML thresholds:** still waiting on the ML team; the status rules will show them when they arrive.
- **AI explanations, report evidence and recommendations:** later steps (RAG + Reasoning Agent).
