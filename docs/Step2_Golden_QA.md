# Step 2: golden Q&A set (ground truth for RAG and agent evaluation)

2026-10-30. Draft for review by Santhosh + one teammate. Build: `cd app && python3 -m eval.build_golden` (needs step 1's triage tables).

## The idea in one paragraph

We write questions whose correct answer we can check ourselves. For each one we store the reference answer and, for report questions, the exact sentence in the source that proves it. Any RAG setup is then scored on two things:
- **Retrieval**: did a retrieved chunk contain that sentence?
- **Answer**: did it give that answer?

Because we store the sentence, not a chunk id, the same set works for every chunking method we compare in step 4.

## What is in it (77 items, `app/eval/golden_qa.json`)

| Type | Count | Where the answer comes from | How it is scored |
|---|---|---|---|
| Report facts | 34 | Hand-picked sentences from FY13 Q2/Q3 Walmart releases and calls, the Jul / Aug / Oct 2012 Beige Books (8 districts covering our stores), and (added in step 3) the FY13 Q3 10-Q and 3 news releases | Retrieval Hit@5 and MRR on the quote; answer correctness |
| Unanswerable | 3 | Facts that are **not** in the sources (store-level stockouts, optical sales, Texas comps) | Agent must say "not in the sources" instead of making something up |
| Case facts | 20 | Computed from the v3.3 case files and step 1 triage: largest dept, expected vs actual, vs last year, peers, markdowns, fiscal quarter and holiday link | Exact number match |
| Judgment | 20 | 10 cases x 2 questions: what should the manager do, main factor. Draft = code triage | Agent vs agreed human label; teammate agreement (Cohen's kappa) |

- **Report questions are tied to our cases.** They cover the topics the triage raised: back to school (Stationery, kids' apparel), electronics deflation, generic drugs in pharmacy (Store 21), West Coast grocery (Store 28), fuel, Labor Day, the warm October, the drought, and layaway timing.
- **Check run:** all 34 answerable report items have their quote found word for word in the cleaned source text.
- **Judgment cases** (ranks 1, 2, 6, 7, 8, 12, 15, 19, 21, 25) mix clear store problems, clear forecast/season cases, Labor Day week and back-to-school week.

## What reviewers do

1. **`app/eval/golden_qa_review.csv`** (Santhosh + one teammate): read each question and reference answer. Put Y/N in `reviewer_ok`, and a correction in `reviewer_fix` if needed. Report rows show the quote and source document, so each check takes about 30 seconds.
2. **`app/eval/labels_sheet.csv`** (two teammates, each on their own, without looking at the draft answers): read each case brief and pick a status, a main factor and the department to check first. I then compute agreement:
   - **Labels agree** -> that label becomes the ground truth.
   - **Labels disagree** -> the two discuss and settle it.
3. I put the agreed answers back into `golden_qa.json` (`review_status: approved`).

## First look at the current RAG (preview of step 4)

The current vector search, with no date or district filter, found the right sentence in its top 5 for only **5 of 30** report questions (MRR 0.11).
- The app adds date and district filters, so the real number is higher.
- But this shows why step 4 (better chunking, keyword + vector hybrid search, filters, a reranker) is worth doing.

## Your decisions

- Is 73 enough? It is enough for a class project comparison. Each extra report question costs about 5 minutes to write and check.
- The 20 judgment drafts come from my thresholds. Teammates must label blind, or we only measure agreement with my own rules.
