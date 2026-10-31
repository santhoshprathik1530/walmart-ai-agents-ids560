"""Score the Phase 2 agent run (data/agent_outputs_v3.json) for the write-up.

    python3 -m eval.score_agent_v3

- the 7 evaluation checks: pass rate per check and per case
- how much supporting evidence the agent found (Strong / Some / Little) and where it came from (finding scopes)
- cases that use a report; models used (a batch run pins one)
- golden case items (C01-C20): are the numbers of the reference answer in the facts the agent was given?
- golden judgment items: compared once the blind labels are in (none yet)
- cost and time per case
Writes eval/results/agent_v3_summary.json and agent_v3_cases.csv.
"""
from __future__ import annotations

import json
from collections import Counter

import pandas as pd

from agents import llm
from agents.pipeline_v3 import OUT as RUN, SCOPES
from eval.compare_rag import EVAL, OUT


def main() -> dict:
    run = json.loads(RUN.read_text())
    ok = {k: v for k, v in run.items() if "report" in v}
    rows = []
    for cid, x in ok.items():
        rep, ev = x["report"], x["evaluation"]
        rows.append(dict(case_id=cid, rank=int(x["case"]["ml_priority_rank"].split()[0]), store=x["case"]["store"],
                         week=x["case"]["week_ending"], model=x["llm"]["model"], evidence_found=rep["evidence_found"],
                         shown=x["shown_status"], passed=ev["passed"],
                         failed=", ".join(c["name"] for c in ev["checks"] if not c["passed"]),
                         findings=len(rep["findings"]), **{f"n_{t}": sum(f["scope"] == t for f in rep["findings"]) for t in SCOPES},
                         departments=len(rep["departments"]), passages=len(x["rag"]["passages"]), seconds=x["seconds"],
                         tokens=x["llm"]["tokens_in"] + x["llm"]["tokens_out"] + x["plan"]["llm"]["tokens_in"] + x["plan"]["llm"]["tokens_out"]))
    df = pd.DataFrame(rows).sort_values("rank")
    df.to_csv(OUT / "agent_v3_cases.csv", index=False)
    checks = Counter()
    for x in ok.values():
        for c in x["evaluation"]["checks"]:
            checks[c["name"]] += c["passed"]

    gold = json.loads((EVAL / "golden_qa.json").read_text())
    cov = []
    for g in gold:
        if g["type"] == "case" and g["case_id"] in ok:
            x = ok[g["case_id"]]
            have = llm._nums(llm.dumps(dict(case=x["case"], evidence=x["evidence"])))
            need = llm._nums(g["answer"])
            cov.append(dict(id=g["id"], kind=g["tags"]["kind"], covered=need <= have, missing=sorted(need - have)))
    labelled = [g for g in gold if g["type"] == "judgment" and g["answer"]]
    summary = dict(
        cases=len(run), answered=len(ok), errors=[k for k, v in run.items() if "report" not in v],
        all_checks_passed=int(df.passed.sum()), check_pass=dict(checks),
        models=df.model.value_counts().to_dict(), shown_status=df.shown.value_counts().to_dict(),
        evidence_found=df.evidence_found.value_counts().to_dict(),
        findings_per_case=round(df.findings.mean(), 1), finding_scopes={t: int(df[f"n_{t}"].sum()) for t in SCOPES},
        cases_citing_a_report=int((df.n_report > 0).sum()),
        golden_case_facts_covered=f"{sum(c['covered'] for c in cov)}/{len(cov)}",
        golden_case_facts_missing=[c for c in cov if not c["covered"]],
        golden_judgments_labelled=f"{len(labelled)} of {sum(g['type'] == 'judgment' for g in gold)} (blind labels pending)",
        seconds_per_case=round(df.seconds.median(), 1), tokens_per_case=round(df.tokens.mean()))
    (OUT / "agent_v3_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str))
