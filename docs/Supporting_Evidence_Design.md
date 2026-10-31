# Supporting-evidence design (2026-10-31)

## The rule (Santhosh)
The ML team trains the model and defines the exception: which store-weeks and departments are flagged, the per-store
thresholds, the priority order and the status ("Analyst review required"). The AI agent does not redefine any of that and
adds no metrics, cutoffs or statuses of its own. Its only job: **find evidence that supports each flag**, if someone
wants to know why it might have happened.

## What the ML team gives (v3.4 case file, e.g. Store 28, week ending Aug 31, 2012)
- Store, week, store type and size; 69 departments forecast, 10 flagged; $73,354 below forecast in the flagged ones.
- How it was detected: Extra Trees forecast, per-store MAD threshold (-24.29% for Store 28), Isolation Forest screen.
- Per flagged department: actual, forecast, gap and % gap, the threshold, the last 4 / 8 weeks, the same season in
  earlier years, the share of other stores where the model was too high, and four exploratory signals.
- Markdowns (store-level), temperature, fuel, CPI, unemployment for that week.
- Conclusion: root cause NOT VERIFIED, ANALYST REVIEW REQUIRED.
- Also: the ML team's forecast and flag for **every** store x department x week (Jul 20 - Oct 26, 2012), in
  `per_store_mad_department_flags.csv`. The v3.4 cases name it as their source.

## What the agent does with it
Uses the store, week, flagged departments and their % below forecast as given, then looks for support:

| Question | How (all from the ML team's own forecasts, or the agreed sources) |
|---|---|
| How did Walmart do that week? | all 45 stores vs the ML forecast; how many stores were below; how this week ranks among the 15 test weeks |
| Was this department down elsewhere? | the same department at every store that week: how many were below the forecast, how many the ML team also flagged, median % |
| ... in the same region? | the same, for the stores in the same EIA fuel region (publicly inferred) |
| Was the whole store down? | how many of the store's departments were below the forecast; the store total vs the forecast |
| Outside factors? | holiday, fuel price, temperature, unemployment vs the 4 weeks before (CPI left out by the sponsor's rule); markdowns (store-level only) |
| What did Walmart and the Fed say? | RAG setup E: Walmart releases, calls, 10-Q/10-K, news releases, Beige Book for the same weeks and the store's Fed district; Walmart's reported U.S. comps for the quarter |
| The ML team's own notes | shown and usable as "the ML team's notes", never as a reason to doubt the flag |

The LLM writes: a summary, 2-6 findings each tagged by where it comes from (all stores / same department / region /
this store / outside / report / ML note), a line per large department, what was looked for and not found, next steps
for the store side, and how much supporting evidence was found (Strong / Some / Little). It may never say the flag is
wrong, that no action is needed, or ask the ML team to review its forecast; a code check enforces that.

## What was removed (it was ours, not the ML team's)
- Our status rule (10% of the gap and $2,000 for "Action needed", 70% explained for "No action needed") and the three
  statuses. Every case now shows the ML team's "Analyst review required".
- Our signal groups and "look at first" ranking, and the check that enforced it.
- Our similar-store comparison (same type, size within 25%) and "a store to learn from".
- "Did it bounce back?" (later weeks, our 20% rule) and our recomputed same-season median.
- "Forecast model" as a type of reason.
- The old `app.py` (moved to `_old_app_archive/`).

## Results (40 v3.4 cases, Claude Haiku 5.5 only, no fallback)
| | |
|---|---|
| Answered | 40 / 40 |
| All 7 checks passed | 39 / 40 (Store 10, Aug 31: put a paraphrase in quotation marks; shown as "Answer needs a check") |
| Evidence found | Strong 35, Some 5, Little 0 |
| Findings per case | 5.3; by source: same department 59, this store 36, report 39, outside 27, all stores 20, region 19, ML note 11 |
| Cases citing a report | 33 / 40 |
| Golden case facts in what the agent was given | 20 / 20 |
| Time / tokens per case | 24 s / 14.8K tokens (about $0.002) |
| Chat, 20 golden case questions | 15/20 contain every reference number (3 named the department without its number, 2 left out "0 flagged"); Sonnet graded 20/20 correct; 20/20 passed the chat's own checks |

Example (Store 28, Dry Grocery, -24.5% vs forecast): 31 of 44 other stores were also below the ML forecast in Dry
Grocery that week (median -4.1%), all 5 other West Coast stores were down 9-12%, Store 28 was the lowest of all 45;
Walmart overall was -2.6% that week (3rd-worst of 15 weeks); a Fed report notes feed prices passing through to grocery.
So the category was soft everywhere, and the size of Store 28's gap points to something local as well.

## Evaluation changes
- Checks: "Status agrees with the rule" and "Looks first where the ML signals point" replaced by "Covers the largest
  flagged department"; the guardrail check also catches doubts about the ML flag.
- Blind labels (`app/eval/labels_sheet.csv`): two teammates now mark the main supporting evidence and its strength
  (not whether the flag is right). No draft answers from code.
- The superseded run with our own status rule is in `app/data/v34_ourrule_archive/`.
