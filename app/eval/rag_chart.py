"""Chart for step 4: eval/results/rag_comparison.html (self-contained, light + dark). Run after eval.compare_rag.

    python3 -m eval.rag_chart
"""
from __future__ import annotations

import ast
import html
import json

import pandas as pd

from eval.compare_rag import OUT

CHOSEN = "E"
ROW, BAR, LEFT, W = 34, 18, 300, 300


def panel(df: pd.DataFrame, col: str, ci: str | None, title: str) -> str:
    h = ROW * len(df) + 30
    out = [f'<figure><figcaption>{title}</figcaption><svg viewBox="0 0 {LEFT + W + 60} {h}" role="img" aria-label="{title}">']
    for t in (0, .25, .5, .75, 1):
        x = LEFT + t * W
        out.append(f'<line class="grid" x1="{x}" x2="{x}" y1="0" y2="{h - 22}"/><text class="tick" x="{x}" y="{h - 6}">{t:.0%}</text>'
                   if col != "mrr" else
                   f'<line class="grid" x1="{x}" x2="{x}" y1="0" y2="{h - 22}"/><text class="tick" x="{x}" y="{h - 6}">{t:.2f}</text>')
    for i, r in enumerate(df.itertuples()):
        y = i * ROW + (ROW - BAR) / 2
        v = getattr(r, col)
        w = max(v * W, 1)
        cls = "bar chosen" if r.variant == CHOSEN else "bar"
        tip = html.escape(f"{r.variant}: {r.label}\n{col.upper()} {v:.2f}" + (f" (95% CI {getattr(r, ci)[0]:.2f} to {getattr(r, ci)[1]:.2f})" if ci else ""))
        out.append(f'<g><title>{tip}</title><text class="lab" x="{LEFT - 10}" y="{y + BAR / 2 + 4}">{html.escape(r.variant)} · '
                   f'{html.escape(r.label)}</text>'
                   f'<path class="{cls}" d="M{LEFT},{y} h{w - 4} a4,4 0 0 1 4,4 v{BAR - 8} a4,4 0 0 1 -4,4 h{-(w - 4)} z"/>')
        if ci:
            lo, hi = getattr(r, ci)
            out.append(f'<line class="ci" x1="{LEFT + lo * W}" x2="{LEFT + hi * W}" y1="{y + BAR / 2}" y2="{y + BAR / 2}"/>')
        out.append(f'<text class="val" x="{LEFT + (max(v, getattr(r, ci)[1]) if ci else v) * W + 8}" y="{y + BAR / 2 + 4}">'
                   f'{v:.0%}</text></g>' if col != "mrr" else
                   f'<text class="val" x="{LEFT + (max(v, getattr(r, ci)[1]) if ci else v) * W + 8}" y="{y + BAR / 2 + 4}">{v:.2f}</text></g>')
    return "\n".join(out) + "</svg></figure>"


def table(df: pd.DataFrame) -> str:
    cols = [("variant", "Variant"), ("label", "Setup"), ("hit1", "Hit@1"), ("hit5", "Hit@5"), ("mrr", "MRR"),
            ("correct", "Answer correct"), ("faithful", "Faithful"), ("refused_unanswerable", "Said 'not in sources'"),
            ("ms", "Search ms")]
    cols = [c for c in cols if c[0] in df]
    fmt = lambda c, v: "–" if pd.isna(v) else f"{v:.0%}" if c in ("hit1", "hit5", "correct", "faithful") else \
        f"{v:.2f}" if c == "mrr" else f"{v:,.0f}" if c == "ms" else html.escape(str(v))
    head = "".join(f"<th>{n}</th>" for _, n in cols)
    body = "".join("<tr>" + "".join(f"<td>{fmt(c, getattr(r, c))}</td>" for c, _ in cols) + "</tr>" for r in df.itertuples())
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build() -> str:
    df = pd.DataFrame(json.loads((OUT / "rag_comparison.json").read_text()))
    for c in ("hit5_ci", "mrr_ci"):
        df[c] = df[c].apply(lambda x: tuple(x) if isinstance(x, list) else ast.literal_eval(x))
    n = int(df.n.iloc[0])
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RAG Variant Comparison</title><style>
:root{{--bg:#fff;--ink:#1a1a1a;--ink2:#555;--muted:#777;--grid:#e6e6e6;--bar:#a9c3f5;--chosen:#0053e2;--ci:#1a1a1a}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#16181d;--ink:#f2f2f2;--ink2:#c4c4c4;--muted:#9a9a9a;--grid:#2c2f36;--bar:#3a5a96;--chosen:#6f9bff;--ci:#f2f2f2}}}}
:root[data-theme="dark"]{{--bg:#16181d;--ink:#f2f2f2;--ink2:#c4c4c4;--muted:#9a9a9a;--grid:#2c2f36;--bar:#3a5a96;--chosen:#6f9bff;--ci:#f2f2f2}}
body{{background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;padding:24px 16px}}
main{{max-width:760px;margin:auto}} h1{{font-size:22px;margin:0 0 4px}} p{{color:var(--ink2);margin:0 0 18px}}
figure{{margin:0 0 26px}} figcaption{{font-weight:600;margin-bottom:6px}} svg{{width:100%;height:auto;overflow:visible}}
.grid{{stroke:var(--grid);stroke-width:1}} .tick{{fill:var(--muted);font-size:11px;text-anchor:middle}}
.lab{{fill:var(--ink2);font-size:12px;text-anchor:end}} .val{{fill:var(--ink);font-size:12px;font-weight:600}}
.bar{{fill:var(--bar)}} .bar.chosen{{fill:var(--chosen)}} .ci{{stroke:var(--ci);stroke-width:1.5;opacity:.55}}
g:hover .bar{{opacity:.85}} table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid)}}
th{{color:var(--ink2);font-weight:600}} .wrap{{overflow-x:auto}}
</style></head><body><main>
<h1>Which retrieval setup finds the right report passage?</h1>
<p>{n} golden report questions, each with a verbatim evidence sentence. A hit means a returned chunk holds that sentence.
Dark blue = recommended setup (E). Lines show 95% bootstrap intervals; with {n} questions, differences under ~15 points are not reliable.</p>
{panel(df, "hit5", "hit5_ci", "Right passage in the top 5 (Hit@5)")}
{panel(df, "mrr", "mrr_ci", "How high the right passage ranks (MRR, 1 = always first)")}
<div class="wrap">{table(df)}</div>
</main></body></html>"""
    (OUT / "rag_comparison.html").write_text(page)
    return str(OUT / "rag_comparison.html")


if __name__ == "__main__":
    print(build())
