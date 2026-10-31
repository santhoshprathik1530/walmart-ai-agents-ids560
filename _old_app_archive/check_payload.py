"""Recompute the numbers in store2_primary_anomaly.json from the Kaggle files.
Run: python3 app/check_payload.py"""
import json
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
P = json.loads((DATA / "payloads" / "store2_primary_anomaly.json").read_text())
store, wk = P["metadata"]["store_id"], pd.Timestamp(P["metadata"]["date"])

tr = pd.read_csv(DATA / "train.csv", parse_dates=["Date"])
ft = pd.read_csv(DATA / "features.csv", parse_dates=["Date"])
chain = tr.groupby("Date").Weekly_Sales.sum()
s = tr[tr.Store == store].groupby("Date").Weekly_Sales.sum()
prior = s[s.index < wk]
ly = wk - pd.Timedelta(weeks=52)

def row(label, claimed, actual):
    ok = "OK  " if abs(claimed - actual) <= max(0.01 * abs(actual), 0.01) else "DIFF"
    print(f"{ok} {label:<42} payload={claimed:>14,.2f}  recomputed={actual:>14,.2f}")

q = P["quantitative_exception"]
row("actual weekly sales", q["actual_weekly_sales"], s[wk])
row("4-wk trailing MA", q["expected_baseline_4wk_ma"], prior.tail(4).mean())
row("8-wk trailing MA", q["expected_baseline_8wk_ma"], prior.tail(8).mean())
row("deviation % vs 4-wk MA", q["sales_deviation_pct"], (s[wk] / prior.tail(4).mean() - 1) * 100)

f = ft[(ft.Store == store) & (ft.Date == wk)].iloc[0]
md = P["promotional_allocation"]["channel_breakdown"]
row("markdown total", P["promotional_allocation"]["total_markdown_spend"], sum(f[k] for k in md))
m = P["internal_macro_features"]
row("fuel price", m["fuel_price"], f.Fuel_Price)
row("CPI", m["cpi"], f.CPI)
row("unemployment", m["unemployment"], f.Unemployment)
row("temperature", m["temperature_f"], f.Temperature)

d = tr[tr.Store == store].pivot_table(index="Date", columns="Dept", values="Weekly_Sales")
print()
for key in ("top_shortfall_departments", "top_buffer_departments"):
    for r in P[key]:
        dep = r["dept_id"]
        row(f"dept {dep} actual / 4-wk MA expected", r["expected_sales"], d[dep][d.index < wk].tail(4).mean())
print("\n--- context the payload does not use ---")
print(f"Store {store} vs same week last year ({ly.date()}):      {(s[wk] / s[ly] - 1) * 100:+.1f}%")
print(f"Store {store} same-week drop last year (Jan 7 2011):    {(s[ly] / s[s.index < ly].tail(4).mean() - 1) * 100:+.1f}%")
print(f"Whole chain this week vs its 4-wk MA:             {(chain[wk] / chain[chain.index < wk].tail(4).mean() - 1) * 100:+.1f}%")
st = tr.groupby(["Store", "Date"]).Weekly_Sales.sum().unstack(0)
drops = (st.loc[wk] / st[st.index < wk].tail(4).mean() - 1) * 100
print(f"All 45 stores vs 4-wk MA: median {drops.median():+.1f}%, store {store} rank {int(drops.rank()[store])} of 45 (1 = worst)")
print("Prior 4 weeks used as baseline:", {str(k.date()): round(v) for k, v in prior.tail(4).items()})
