"""Static stakeholder page. No pipeline jargon on the page."""

from __future__ import annotations

import json
from datetime import date
from html import escape

import duckdb

from rba_copilot.headline import build_headline
from rba_copilot.paths import REPORTS, SITE, TIDY

PALETTE = {
    "cash": "#16324f",
    "headline": "#9c341f",
    "trimmed": "#8a5a12",
    "jobs": "#0f6e56",
    "energy": "#9c341f",
    "ai": "#16324f",
    "capacity": "#0f6e56",
    "labour": "#8a5a12",
}


def _pretty(iso: str | None) -> str:
    if not iso:
        return ""
    moment = date.fromisoformat(iso[:10])
    return moment.strftime("%-d %B %Y")


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _pct(value: float, digits: int = 2) -> str:
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return text


def _chart(series: list[dict], width: int = 860, height: int = 340, y_min: float | None = None, y_max: float | None = None, band: tuple[float, float] | None = None, y_format=None) -> str:
    """One SVG line chart. series items have name, color, and points of {x, y}."""
    y_format = y_format or (lambda value: f"{value:.1f}")
    points = [point for item in series for point in item["points"] if point["y"] is not None]
    if not points:
        return ""
    labels = []
    for point in points:
        if point["x"] not in labels:
            labels.append(point["x"])
    ys = [point["y"] for point in points]
    if band:
        ys.extend(band)
    low = min(ys) if y_min is None else y_min
    high = max(ys) if y_max is None else y_max
    if high == low:
        high += 1
    pad_l, pad_r, pad_t, pad_b = 52, 108, 18, 36
    inner_w = width - pad_l - pad_r
    inner_h = height - pad_t - pad_b

    def x_of(label: str) -> float:
        return pad_l + labels.index(label) / max(len(labels) - 1, 1) * inner_w

    def y_of(value: float) -> float:
        return pad_t + (high - value) / (high - low) * inner_h

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fffdf8"></rect>',
    ]
    if band:
        y1, y2 = y_of(band[1]), y_of(band[0])
        parts.append(
            f'<rect x="{pad_l}" y="{y2:.1f}" width="{inner_w}" height="{max(y1 - y2, 0):.1f}" fill="#d7e6dc"></rect>'
        )
        parts.append(
            f'<text x="{pad_l + 8}" y="{y2 + 16:.1f}" fill="#0f6e56" font-size="12">Target 2–3%</text>'
        )
    for tick in (low, (low + high) / 2, high):
        y = y_of(tick)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + inner_w}" y2="{y:.1f}" stroke="#eadfce"></line>')
        parts.append(
            f'<text x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" fill="#5c6670" font-size="12">{escape(y_format(tick))}</text>'
        )
    for index, label in enumerate(labels):
        if index % max(len(labels) // 6, 1) != 0 and index != len(labels) - 1:
            continue
        parts.append(
            f'<text x="{x_of(label):.1f}" y="{height - 12}" text-anchor="middle" fill="#5c6670" font-size="12">{escape(label)}</text>'
        )
    for item in series:
        usable = [point for point in item["points"] if point["y"] is not None]
        if not usable:
            continue
        path = " ".join(
            f'{"M" if index == 0 else "L"} {x_of(point["x"]):.1f} {y_of(point["y"]):.1f}'
            for index, point in enumerate(usable)
        )
        parts.append(f'<path d="{path}" fill="none" stroke="{item["color"]}" stroke-width="2.5"></path>')
        last = usable[-1]
        parts.append(f'<circle cx="{x_of(last["x"]):.1f}" cy="{y_of(last["y"]):.1f}" r="3.5" fill="{item["color"]}"></circle>')
        parts.append(
            f'<text x="{x_of(last["x"]) + 8:.1f}" y="{y_of(last["y"]) + 4:.1f}" fill="{item["color"]}" font-size="13" font-weight="600">{escape(item["name"])}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _search_payload() -> list[dict]:
    path = (TIDY / "chunks.parquet").as_posix().replace("'", "''")
    connection = duckdb.connect()
    cursor = connection.execute(
        f"""
        SELECT chunk_id, doc_date::varchar, title, url, section, chunk_text
        FROM read_parquet('{path}')
        ORDER BY doc_date, chunk_id
        """
    )
    rows = [
        {
            "id": row[0],
            "date": str(row[1])[:10],
            "title": row[2],
            "url": row[3],
            "section": row[4],
            "text": row[5],
        }
        for row in cursor.fetchall()
    ]
    connection.close()
    return rows


def _answers() -> list[dict]:
    path = REPORTS / "answers.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def render(headline: dict) -> str:
    kpis = headline["kpis"]
    hero = _chart(
        [
            {
                "name": "Cash rate",
                "color": PALETTE["cash"],
                "points": [{"x": row["month"], "y": row["cash_rate"]} for row in headline["series"]["hero"]],
            },
            {
                "name": "Prices",
                "color": PALETTE["headline"],
                "points": [{"x": row["month"], "y": row["headline_inflation"]} for row in headline["series"]["hero"]],
            },
            {
                "name": "Underlying",
                "color": PALETTE["trimmed"],
                "points": [{"x": row["month"], "y": row["trimmed_mean"]} for row in headline["series"]["hero"]],
            },
        ],
        y_min=0,
        y_max=8,
        band=(2, 3),
        y_format=lambda value: f"{value:.0f}%",
    )
    repay = _chart(
        [
            {
                "name": "Monthly repayment",
                "color": PALETTE["cash"],
                "points": [{"x": row["month"], "y": row["repayment"]} for row in headline["series"]["repayments"]],
            }
        ],
        y_format=lambda value: f"${value:,.0f}",
    )
    theme_names = [
        ("energy", "Energy", PALETTE["energy"]),
        ("ai_investment", "AI investment", PALETTE["ai"]),
        ("capacity", "Capacity", PALETTE["capacity"]),
        ("labour_market", "Jobs", PALETTE["labour"]),
    ]
    theme_series = []
    for key, label, color in theme_names:
        theme_series.append(
            {
                "name": label,
                "color": color,
                "points": [
                    {"x": row["month_start"][:7], "y": round(row["share"] * 100, 1)}
                    for row in headline["series"]["themes"]
                    if row["theme"] == key
                ],
            }
        )
    themes = _chart(theme_series, y_min=0, y_max=100, y_format=lambda value: f"{value:.0f}%")
    jobs = _chart(
        [
            {
                "name": "Unemployment",
                "color": PALETTE["jobs"],
                "points": [
                    {"x": row["month"], "y": row["unemployment"]} for row in headline["series"]["unemployment"]
                ],
            }
        ],
        y_min=3,
        y_max=6,
        y_format=lambda value: f"{value:.1f}%",
    )
    quote_html = []
    for answer in _answers():
        citation = answer.get("citation")
        if not citation:
            continue
        quote_html.append(
            f"""
            <article class="quote">
              <h3>{escape(answer['question'])}</h3>
              <blockquote>“{escape(citation['quote'])}”</blockquote>
              <p class="cite"><a href="{escape(citation['url'])}">{escape(citation['title'])}</a>
              · {_pretty(citation['doc_date'])}</p>
            </article>
            """
        )
    quotes = "\n".join(quote_html) or "<p>Quoted passages will appear here after the document search is built.</p>"
    share = kpis["repayment_share_of_one_wage"] * 100
    html = f"""<!DOCTYPE html>
<html lang="en-AU">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Five hikes in 2026? What it costs your mortgage</title>
  <style>
    :root {{
      --paper: #f3efe6;
      --ink: #1c2430;
      --muted: #5c6670;
      --navy: #16324f;
      --card: #fffdf8;
      --line: #e4dccb;
      --pressure: #9c341f;
      --watch: #8a5a12;
      --calm: #0f6e56;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: "Iowan Old Style", Palatino, Georgia, serif;
      line-height: 1.45;
    }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 28px 20px 64px; }}
    header.banner {{
      background: var(--navy);
      color: #f7f3ea;
      padding: 36px 20px 32px;
    }}
    header.banner .wrap {{ max-width: 1080px; margin: 0 auto; }}
    .eyebrow {{ letter-spacing: 0.04em; text-transform: uppercase; font-family: "Avenir Next", "Segoe UI", sans-serif; font-size: 0.78rem; margin: 0 0 10px; color: #d5c4a1; }}
    h1 {{ font-size: clamp(2rem, 4vw, 3.2rem); line-height: 1.05; margin: 0 0 12px; font-weight: 650; }}
    .lede {{ font-size: 1.15rem; max-width: 42rem; margin: 0; color: #f3efe6; }}
    .asof {{ font-family: "Avenir Next", "Segoe UI", sans-serif; color: var(--muted); font-size: 0.92rem; margin: 18px 0 0; }}
    .kpis {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-top: 16px; }}
    .card {{ background: var(--card); border: 1px solid var(--line); border-top: 4px solid var(--navy); border-radius: 12px; padding: 14px 14px 16px; box-shadow: 0 8px 24px rgba(22, 50, 79, 0.06); }}
    .card.pressure {{ border-top-color: var(--pressure); }}
    .card.watch {{ border-top-color: var(--watch); }}
    .card.calm {{ border-top-color: var(--calm); }}
    .card h2 {{ font-family: "Avenir Next", "Segoe UI", sans-serif; font-size: 0.78rem; letter-spacing: 0.03em; text-transform: uppercase; color: var(--muted); margin: 0 0 6px; font-weight: 600; }}
    .card .value {{ font-size: 1.8rem; margin: 0; color: var(--navy); }}
    .card p {{ margin: 8px 0 0; font-size: 0.95rem; }}
    section {{ margin-top: 28px; }}
    h2.section {{ font-size: 1.55rem; margin: 0 0 8px; }}
    .insight {{ margin: 0 0 12px; max-width: 46rem; }}
    .panel {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 12px 12px 4px; }}
    .chart {{ width: 100%; height: auto; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    .means {{ background: #16324f; color: #f7f3ea; border-radius: 14px; padding: 22px 22px 8px; }}
    .means h2, .means p {{ color: #f7f3ea; }}
    .quote {{ border-top: 1px solid var(--line); padding: 14px 0; }}
    .quote h3 {{ font-size: 1.05rem; margin: 0 0 8px; }}
    blockquote {{ margin: 0; font-size: 1.05rem; }}
    .cite {{ font-family: "Avenir Next", "Segoe UI", sans-serif; color: var(--muted); font-size: 0.9rem; }}
    a {{ color: var(--navy); }}
    .means a {{ color: #f0d48a; }}
    input {{ width: 100%; padding: 12px 14px; border-radius: 10px; border: 1px solid var(--line); font-size: 1rem; font-family: inherit; }}
    #hits p {{ margin: 10px 0; }}
    footer {{ margin-top: 36px; font-family: "Avenir Next", "Segoe UI", sans-serif; color: var(--muted); font-size: 0.88rem; }}
    .advice {{ border: 1px solid #e2c2a4; background: #fff6ee; border-radius: 12px; padding: 12px 14px; }}
    @media (max-width: 900px) {{
      .kpis, .grid-2 {{ grid-template-columns: 1fr; }}
      .kpis {{ margin-top: 16px; }}
    }}
  </style>
</head>
<body>
  <header class="banner">
    <div class="wrap">
      <p class="eyebrow">Next Reserve Bank decision · {escape(headline['next_decision'])}</p>
      <h1>Five hikes in 2026? What it costs your mortgage</h1>
      <p class="lede">The cash rate is {_pct(kpis['cash_rate'])}%. Four rises this year have already shown up in the average variable mortgage rate. Here is the extra monthly cost, and what the Reserve Bank has said in its own words.</p>
    </div>
  </header>
  <main>
    <p class="asof">Figures checked {escape(headline['as_of_melbourne'])}. Melbourne time.</p>
    <section class="kpis">
      <article class="card pressure">
        <h2>Cash rate</h2>
        <p class="value">{_pct(kpis['cash_rate'])}%</p>
        <p>Four rises in 2026, 1.00 percentage point in total. The latest reading is {_pretty(kpis['cash_rate_date'])}.</p>
      </article>
      <article class="card pressure">
        <h2>$600,000 loan, since January</h2>
        <p class="value">{_money(kpis['extra_repayment_600k'])}</p>
        <p>More each month. The average variable rate borrowers are paying went from {_pct(kpis['housing_rate_january'])}% in January to {_pct(kpis['housing_rate'])}% in August.</p>
      </article>
      <article class="card pressure">
        <h2>Inflation versus the target</h2>
        <p class="value">{_pct(kpis['cpi_yoy'])}%</p>
        <p>Prices were this much higher than a year earlier in September. Underlying inflation was {_pct(kpis['trimmed_mean_yoy'])}%. The target is 2 to 3%.</p>
      </article>
      <article class="card watch">
        <h2>Cash rate above underlying inflation</h2>
        <p class="value">{_pct(kpis['real_cash_rate'])} pts</p>
        <p>The cash rate minus September’s underlying inflation. Policy is sitting above the pace of underlying prices.</p>
      </article>
      <article class="card watch">
        <h2>Unemployment</h2>
        <p class="value">{_pct(kpis['unemployment'])}%</p>
        <p>In September, up from {_pct(kpis['unemployment_january'])}% in January. The jobs market has loosened, and it is still tight enough for the Bank to worry about prices.</p>
      </article>
    </section>

    <section>
      <h2 class="section">The cash rate has risen back above inflation</h2>
      <p class="insight">The shaded band is the 2 to 3% inflation target. Prices and underlying inflation are both still above it. The cash rate is the Reserve Bank’s overnight target, not the rate on your loan.</p>
      <div class="panel">{hero}</div>
    </section>

    <section class="grid-2">
      <div>
        <h2 class="section">A $600,000 loan costs about {_money(kpis['repayment_600k'])} a month</h2>
        <p class="insight">That is a 30-year principal-and-interest comparison at the average variable rate people are actually paying. It is about {_money(kpis['extra_repayment_600k'])} more than in January. Another 0.25 percentage points, if a lender passes it on in full, is about {_money(kpis['step_25bp_600k'])} more on $600,000, or {_money(kpis['step_25bp_100k'])} per $100,000.</p>
        <div class="panel">{repay}</div>
      </div>
      <div>
        <h2 class="section">Unemployment has drifted up</h2>
        <p class="insight">From {_pct(kpis['unemployment_january'])}% in January to {_pct(kpis['unemployment'])}% in September. The Bank has said the jobs market is easier than it was, and still a bit tight.</p>
        <div class="panel">{jobs}</div>
      </div>
    </section>

    <section>
      <h2 class="section">What the Reserve Bank keeps coming back to</h2>
      <p class="insight">Share of its 2025–2026 passages that mention each subject. Energy, spare capacity and jobs dominate. Artificial intelligence and the investment boom around it show up more often through 2026.</p>
      <div class="panel">{themes}</div>
    </section>

    <section>
      <h2 class="section">What the Reserve Bank is saying</h2>
      <p class="insight">These are sentences from Reserve Bank documents, not a rewritten summary. Each one links to the page it came from.</p>
      {quotes}
    </section>

    <section class="means">
      <h2>What this means for you</h2>
      <p>The September cash-rate rise is not in the August mortgage figure yet. The published average variable rate had already risen 0.70 percentage points by August, close to the 0.75 points of cash-rate rises up to May. A further quarter of a point fully passed on is about {_money(kpis['step_25bp_600k'])} a month on a $600,000 loan.</p>
      <p>That August repayment is about {share:.0f}% of one full-time adult’s ordinary-time pay (${kpis['weekly_earnings']:,.0f} a week in the first half of 2026). A two-income household would see a smaller share. People without a mortgage are not in this illustration. Across the whole economy, scheduled housing repayments were {_pct(kpis['scheduled_repayments_to_income'])}% of household disposable income in the March quarter, the latest ratio the Reserve Bank has published.</p>
      <p>The four major banks have said they expect the cash rate to rise to 4.85% on 3 November. That is their forecast, reported by <a href="https://www.savings.com.au/news/all-big-four-banks-back-november-rate-hike">Savings.com.au</a> in late October 2026. It is not a Reserve Bank decision. If you are weighing a fixed rate against a variable rate, the practical question is whether another {_money(kpis['step_25bp_600k'])} a month on a $600,000 balance is something you can absorb if your lender passes on one more rise.</p>
    </section>

    <section>
      <h2 class="section">Look up a phrase in the Reserve Bank’s own words</h2>
      <p class="insight">This searches the same saved documents. Nothing is sent to a server.</p>
      <input id="q" type="search" placeholder="Try inflation, wages, oil, or productivity" aria-label="Search Reserve Bank passages">
      <div id="hits"></div>
    </section>

    <section class="advice">
      <strong>This is not financial advice.</strong>
      The loan figures are a standard 30-year comparison so households can see the size of a rate change. They are not your repayment, not a quote, and not a recommendation to fix, refinance, or wait.
    </section>

    <footer>
      <p>Sources, all free and CC BY 4.0. Reserve Bank of Australia statistical tables F1, F1.1, F5 (RBA and APRA series only), F6, G1, H5 and E13. Source: RBA. Monthly CPI and average weekly earnings: Australian Bureau of Statistics Data API. Reserve Bank decisions, minutes and Statement on Monetary Policy chapters, 2025–2026. Snapshot prepared {escape(headline['as_of_melbourne'])}.</p>
      <p>Canstar, ASX and FENICS series are in some raw Reserve Bank files and are not used. The September cash-rate rise took effect on 30 September; the housing-rate table used here runs to August.</p>
    </footer>
  </main>
  <script>
    const box = document.getElementById('q');
    const hits = document.getElementById('hits');
    let chunks = [];
    fetch('chunks.json').then(r => r.json()).then(data => {{ chunks = data; }});
    function score(text, terms) {{
      const hay = text.toLowerCase();
      return terms.reduce((sum, term) => sum + (hay.includes(term) ? 1 : 0), 0);
    }}
    box.addEventListener('input', () => {{
      const terms = box.value.toLowerCase().match(/[a-z]{{3,}}/g) || [];
      hits.innerHTML = '';
      if (!terms.length) return;
      const ranked = chunks.map(chunk => ({{ chunk, s: score(chunk.section + ' ' + chunk.text, terms) }}))
        .filter(item => item.s > 0)
        .sort((a, b) => b.s - a.s)
        .slice(0, 5);
      hits.innerHTML = ranked.map(item => {{
        const c = item.chunk;
        return '<p><a href="' + c.url + '">' + c.title + '</a> · ' + c.date + '<br>' + c.text.slice(0, 280) + '…</p>';
      }}).join('') || '<p>No matching passage in the saved documents.</p>';
    }});
  </script>
</body>
</html>
"""
    return html


def build_site() -> None:
    headline = build_headline()
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(render(headline), encoding="utf-8")
    (SITE / "chunks.json").write_text(json.dumps(_search_payload()), encoding="utf-8")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    print(f"wrote {SITE / 'index.html'}")


def main() -> None:
    build_site()


if __name__ == "__main__":
    main()
