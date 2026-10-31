# Step 5: the agent on all 40 v3.3 cases

> **Update 2026-10-31:** the agent no longer uses our own status rule (Action needed / Check before acting / No action needed, 10% / $2,000 / 70%), similar-store peers, signal groups or the recovery check. The ML team defines the exception; the agent only finds evidence that supports each flag. See `Supporting_Evidence_Design.md`. The parts below that use those are kept as history.


> **Update 2026-10-30:** the agent now runs on the ML team's v3.4 cases (per-store thresholds). New results are in [Switch_to_v34.md](Switch_to_v34.md); the numbers below are for v3.3.


2026-10-30. Built and run. Outputs: `app/data/agent_outputs_v3.json`. Summary: `app/eval/results/agent_v3_summary.json` and `agent_v3_cases.csv`.
- Re-run: `cd app && python3 -m agents.pipeline_v3 --force`. This takes about 15 min and costs about $0.11.
- Re-score: `python3 -m eval.score_agent_v3`.

## The flow per case (`app/agents/pipeline_v3.py`)

1. **Intake (code).** Reads the case JSON and the step 1 triage, and turns them into labelled facts:
   - one item per flagged department, with:
     - name and merch unit;
     - actual vs model expected;
     - same weeks in earlier years ($ and %) and the last 4 weeks;
     - similar stores' median and the gap;
     - the 3 similar stores doing best;
     - the share of other stores where the model was also too high;
     - the pattern, and whether it counts for the status;
     - for store-only drops, the later weeks, marked "not used for the status";
   - store-level markdowns, fuel and temperature vs the 4 weeks before (no CPI, per the rule);
   - the case itself: week, Walmart quarter, holiday week, region, Fed district, ML rank.
2. **Orchestrator (LLM).** Picks the 1–3 departments that matter most and writes 2–4 search questions.
3. **RAG (code, setup E from step 4).** Searches with the store's Fed district and only reports from the case week and the 3 weeks before. At least one Walmart passage and one local Beige Book passage are kept; 6 passages go to the reasoning step.
4. **Reasoning (LLM).** Writes:
   - what happened, naming the departments, the week, the Walmart quarter and any holiday;
   - 2–5 possible factors, each tagged **data**, **report** or **model**, with its evidence ids;
   - departments to check, each with why and an action;
   - a similar store to learn from;
   - what is not the cause, a bottom line, next steps, and the data that would confirm a cause.

   It follows the ML file's 7 guardrails.
5. **Evaluation (code, 7 checks).** The first four are unchanged:
   1. numbers match the evidence;
   2. quotes are word for word;
   3. every factor cites real evidence;
   4. the answer is complete.

   Three checks are **new**:

   5. **Guardrails respected:** no "verified or confirmed cause", no "lost sales", no markdown causing a drop, no score read as a probability.
   6. **Every factor is tagged:** a report factor cites a passage, and a data or model factor cites a sales fact.
   7. **Status agrees with the data:** the LLM's status must match the code rule. If it doesn't, a person decides.

   If all 7 pass, the manager sees the status. If any fails, the case shows **Check before acting**.

## Results

| | Run 1 (status rule described loosely) | Run 2 (team's rule given exactly) |
|---|---|---|
| Cases answered | 40/40 | 40/40 |
| All 7 checks passed | 23 | **39** |
| LLM status = code rule | 25/40 | **39/40** |
| Numbers, quotes, citations, tags | 39–40 of 40 each | 40/40 each |
| Guardrails respected | 37 | 40 |
| Factors per case | 5.3 (some had 10–16) | 4.1 |
| Cases that use a report | 38 | 37 |
| Time / cost per case | ~20 s | ~18 s, about $0.003 (10K tokens) |

Shown to the manager (run 2, after re-scoring):
- 24 No action needed
- 11 Action needed
- 5 Check before acting: the code's 4 mixed or unclear cases, plus the 1 case where the LLM disagreed with the rule

Total cost of both runs: about $0.22.

**What run 1 taught us.** Described only loosely, the LLM was more cautious than the code rule. It set 12 cases to "Check before acting" because of small store-only drops, some as small as $209. Run 2 gives it the team's exact rule: a store-only drop counts at ≥10% of the gap and ≥$2,000. Smaller store-only drops now go under "departments to check" instead of changing the status. The one case where it still disagrees is Store 10, Aug 10: Girlswear was 22% of the gap ($9,760, store-only), and the LLM still said "Check before acting". The check caught it, so that case goes to a person.

**What I fixed in the checks between runs:**
- The quote check now also accepts a sales fact quoted word for word.
- The guardrail check no longer flags hedged sentences such as "a possible explanation rather than a confirmed one".
- The status rule, including its "$2,000", is now part of the facts.

These checks were re-run in code on the saved answers, with no new LLM calls.

**Golden set:**
- All 20 exact case questions (C01–C20) have their answer numbers in the facts the agent receives. This was 16/20 before I added the earlier-year dollar figures and the one-decimal chain rates. These questions get used by the chat in step 6.
- The status agrees with the 10 judgment drafts 9/10 times. Those drafts are the code triage, so this is not a real accuracy figure until the two teammates' blind labels are in.

**Which reports get cited** (report-tagged factors, run 2):
- Aug 29 Beige Book: 15
- Q2 FY13 earnings call: 15
- Oct 10 Beige Book: 10
- Jul 18 back-to-school news release: 6
- Others: 4

The agent says each time that these describe Walmart or the district as a whole, not this store.

## Example (Store 28, week ending Aug 31, 2012, Action needed)

- Four grocery departments (Dry Grocery, Frozen Food, Meat, Packaged Deli) were 24–33% below the same weeks in earlier years. Similar stores' medians were between −5% and +6%.
- Actions: check stock and on-shelf availability, and local competitor prices.
- Learn from Store 39, which was up in all three main grocery departments.
- Report factors:
  - Walmart's Q2 call on electronics deflation, used for the small Cameras drop;
  - the Oct 10 Beige Book on rising gasoline prices in the San Francisco District, alongside local fuel at $4.09 vs $3.91.

  Both are stated to be company-wide or district-wide.
- Markdowns are stated to be store-level only.

## Limits

- The status is a code rule with my thresholds. The LLM explains it; it does not decide it.
- A report can only give context, because no report talks about one store.
- The guardrail check works by pattern-matching words. It catches the common wordings, not every possible one.
- The dashboard (step 6) is not built yet. The legacy app (`app.py`, `rag.py`) still runs the old 3 payloads with the old search.
