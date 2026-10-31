"""Evidence that may support an ML flag, built only from the ML team's own numbers and the agreed data (no thresholds,
groupings or forecasts of ours). For a flagged store-week and department it answers:

  walmart_week()     How did all 45 stores do that week against the ML forecast?   (and how that week ranks among the 15)
  store_week()       How did all of this store's departments do that week?
  dept_everywhere()  How did the same department do at every store that week?   (below forecast / flagged by the ML team)
  dept_region()      ... and at the stores in the same region (EIA fuel region, publicly inferred)?
  outside()          Outside factors that week: holiday, fuel price, temperature, unemployment vs the 4 weeks before,
                     markdowns (store-level), Walmart's reported U.S. comp sales for the quarter

Sources: ML_DEPT is the ML team's department-week file for the test weeks Jul 20 - Oct 26, 2012 (all 45 stores, the
Extra Trees forecast and the per-store MAD flag; the v3.4 cases name it as their department source). features.csv is
the Kaggle store-week file (EIA-style fuel price, temperature, unemployment; CPI is left out by the sponsor's rule).
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from .cases_v3 import DATA, lookups

ML_DEPT = DATA / "ml_v33_complete" / "per_store_mad_experiment" / "per_store_mad_department_flags.csv"


@lru_cache(maxsize=1)
def ml() -> pd.DataFrame:
    d = pd.read_csv(ML_DEPT, usecols=["Store", "Dept", "Date", "Actual", "Expected", "Per_Store_MAD_Flag"])
    return d.rename(columns={"Per_Store_MAD_Flag": "Flag"}).assign(Pct=lambda x: (x.Actual / x.Expected - 1) * 100)


@lru_cache(maxsize=1)
def features() -> pd.DataFrame:
    return pd.read_csv(DATA / "features.csv").set_index(["Store", "Date"]).sort_index()


def covered(date: str) -> bool:
    return date in set(ml().Date)


@lru_cache(maxsize=1)
def _weeks() -> pd.DataFrame:
    w = ml().groupby("Date").agg(Actual=("Actual", "sum"), Expected=("Expected", "sum"), Flags=("Flag", "sum"))
    w["Pct"] = (w.Actual / w.Expected - 1) * 100
    s = ml().groupby(["Date", "Store"])[["Actual", "Expected"]].sum()
    w["StoresBelow"] = (s.Actual < s.Expected).groupby("Date").sum()
    w["StoresFlagged"] = ml()[ml().Flag].groupby("Date").Store.nunique()
    return w.fillna({"StoresFlagged": 0})


def walmart_week(date: str) -> dict:
    w = _weeks()
    r = w.loc[date]
    return dict(actual=r.Actual, expected=r.Expected, pct=r.Pct, stores_below=int(r.StoresBelow), stores=45,
                stores_flagged=int(r.StoresFlagged), dept_flags=int(r.Flags),
                rank_low=int((w.Pct < r.Pct).sum()) + 1, weeks=len(w), median_week_pct=w.Pct.median())


def store_week(store: int, date: str) -> dict:
    g = ml()[(ml().Store == store) & (ml().Date == date)]
    return dict(depts=len(g), below=int((g.Actual < g.Expected).sum()), flagged=int(g.Flag.sum()),
                actual=g.Actual.sum(), expected=g.Expected.sum(), pct=(g.Actual.sum() / g.Expected.sum() - 1) * 100)


def dept_everywhere(dept: int, date: str, store: int) -> pd.DataFrame:
    """Every store's result in this department that week (ML forecast and flag); this store marked."""
    g = ml()[(ml().Dept == dept) & (ml().Date == date)].copy()
    _, sm, _ = lookups()
    g["Region"] = g.Store.map(sm.Region)
    g["This"] = g.Store == store
    return g.sort_values("Pct")


def dept_summary(dept: int, date: str, store: int) -> dict:
    g = dept_everywhere(dept, date, store)
    others = g[~g.This]
    me = g[g.This]
    reg = others[others.Region == lookups()[1].Region.get(store)]
    return dict(stores=len(others), below=int((others.Actual < others.Expected).sum()), flagged=int(others.Flag.sum()),
                median_pct=others.Pct.median(), all_pct=(others.Actual.sum() / others.Expected.sum() - 1) * 100,
                this_pct=float(me.Pct.iloc[0]) if len(me) else float("nan"),
                rank_low=int((others.Pct < (me.Pct.iloc[0] if len(me) else 0)).sum()) + 1,
                region=lookups()[1].Region.get(store), region_stores=len(reg),
                region_below=int((reg.Actual < reg.Expected).sum()), region_flagged=int(reg.Flag.sum()),
                region_list="; ".join(f"Store {int(s)} {p:+.1f}%{' (flagged)' if f else ''}"
                                      for s, p, f in zip(reg.Store, reg.Pct, reg.Flag)))


def outside(store: int, date: str) -> dict:
    f = features().loc[store]
    dates = list(f.index)
    i = dates.index(date)
    before = f.iloc[max(0, i - 4):i]
    out = {}
    for k in ("Fuel_Price", "Temperature", "Unemployment"):
        cur, prev = f.iloc[i][k], before[k].median()
        if cur == cur:
            out[k] = dict(current=float(cur), prior_4_week_median=float(prev))
    _, _, cal = lookups()
    c = cal.loc[date]
    out["holiday"] = c.HolidayWeek if isinstance(c.HolidayWeek, str) else "none"
    out["quarter"] = c.FiscalPeriod
    out["reported_comp"] = c.ReportedComp if isinstance(c.ReportedComp, str) or c.ReportedComp == c.ReportedComp else None
    return out
