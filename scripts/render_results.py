"""Render the README results from the warehouse: an SVG chart and a table.

Run after `make transform`:

    uv run python scripts/render_results.py

It rewrites docs/rates-and-volatility.svg and the block between the RESULTS
markers in README.md, so it is safe to run again whenever the data changes.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

WAREHOUSE = Path("data/warehouse.duckdb")
CHART = Path("docs/rates-and-volatility.svg")
README = Path("README.md")
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
CURRENCIES = ("EUR", "USD")

WIDTH, HEIGHT, LEFT, RIGHT = 1000, 520, 72, 960
RATE_TOP, RATE_BOTTOM = 92, 272
VOL_TOP, VOL_BOTTOM = 342, 472
SVG_NS = "http://www.w3.org/2000/svg"
FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif'

STYLE = f"""  <style>
    .bg {{ fill: #F7F9F8; }}
    .t {{ font-family: {FONT}; fill: #15302A; }}
    .h {{ font-weight: 700; font-size: 15px; }}
    .s {{ font-size: 12px; fill: #566B65; }}
    .grid {{ stroke: #DCE4E1; stroke-width: 1; }}
    .axis {{ stroke: #9FB1AB; stroke-width: 1; }}
    .line {{ fill: none; stroke-width: 2.2; stroke-linejoin: round; }}
    .EUR {{ stroke: #2F6B55; fill: #2F6B55; }}
    .USD {{ stroke: #B7791F; fill: #B7791F; }}
    polyline.EUR, polyline.USD {{ fill: none; }}
    @media (prefers-color-scheme: dark) {{
      .bg {{ fill: #0F1A17; }}
      .t {{ fill: #E3ECE8; }}
      .s {{ fill: #93A8A1; }}
      .grid {{ stroke: #24342F; }}
      .axis {{ stroke: #3B504A; }}
      .EUR {{ stroke: #7CC4A4; fill: #7CC4A4; }}
      .USD {{ stroke: #E0B060; fill: #E0B060; }}
    }}
  </style>"""

Series = dict[str, list[tuple]]


def text(x: float, y: float, content: str, cls: str, anchor: str = "start") -> str:
    return (
        f'  <text class="t {cls}" x="{x:.1f}" y="{y:.1f}" '
        f'text-anchor="{anchor}">{content}</text>'
    )


def line(x1: float, y1: float, x2: float, y2: float, cls: str) -> str:
    return (
        f'  <line class="{cls}" x1="{x1:.1f}" y1="{y1:.1f}" '
        f'x2="{x2:.1f}" y2="{y2:.1f}"/>'
    )


def load(con: duckdb.DuckDBPyConnection) -> Series:
    rows = con.execute(
        """
        SELECT currency_code, month, month_end_rate, volatility_30d_pct,
               monthly_return_pct
        FROM mart_monthly_volatility
        WHERE currency_code IN ('EUR', 'USD')
        ORDER BY currency_code, month
        """
    ).fetchall()
    series: Series = {code: [] for code in CURRENCIES}
    for code, *values in rows:
        series[code].append(tuple(values))
    return series


def ticks(low: float, high: float, max_ticks: int = 5) -> list[float]:
    step = next(
        (
            s
            for s in (0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5)
            if (high - low) / s <= max_ticks
        ),
        10.0,
    )
    value = (low // step) * step
    out = []
    while value <= high + 1e-9:
        if value >= low - 1e-9:
            out.append(round(value, 4))
        value += step
    return out


def x_positions(months: list[date]) -> dict[date, float]:
    step = (RIGHT - LEFT) / max(len(months) - 1, 1)
    return {month: LEFT + i * step for i, month in enumerate(months)}


def panel(
    series: Series,
    x_of: dict[date, float],
    column: int,
    box: tuple[float, float],
    title: str,
    from_zero: bool,
) -> list[str]:
    top, bottom = box
    values = [
        r[column] for rows in series.values() for r in rows if r[column] is not None
    ]
    low, high = (0.0 if from_zero else min(values)), max(values)
    pad = (high - low) * 0.08
    low, high = (low if from_zero else low - pad), high + pad

    def y_of(value: float) -> float:
        return bottom - (value - low) / (high - low) * (bottom - top)

    out = [text(LEFT, top - 22, title, "h")]
    for tick in ticks(low, high):
        out.append(line(LEFT, y_of(tick), RIGHT, y_of(tick), "grid"))
        out.append(text(LEFT - 10, y_of(tick) + 4, f"{tick:g}", "s", "end"))
    out.append(line(LEFT, bottom, RIGHT, bottom, "axis"))
    for code, rows in series.items():
        points = " ".join(
            f"{x_of[r[0]]:.1f},{y_of(r[column]):.1f}"
            for r in rows
            if r[column] is not None
        )
        out.append(f'  <polyline class="line {code}" points="{points}"/>')
    return out


def render_chart(series: Series) -> str:
    months = sorted({r[0] for rows in series.values() for r in rows})
    x_of = x_positions(months)
    body = [
        f'<svg xmlns="{SVG_NS}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img">',
        "  <title>Month-end EUR and USD rates in PLN, and their volatility</title>",
        STYLE,
        f'  <rect class="bg" width="{WIDTH}" height="{HEIGHT}" rx="14"/>',
    ]
    body += panel(
        series, x_of, 1, (RATE_TOP, RATE_BOTTOM), "Month-end rate, PLN", False
    )
    vol_title = "30-trading-day volatility of daily returns, %"
    body += panel(series, x_of, 2, (VOL_TOP, VOL_BOTTOM), vol_title, True)
    for month, x in x_of.items():
        if month.month == 1:
            body.append(line(x, RATE_TOP, x, VOL_BOTTOM, "grid"))
            body.append(text(x, VOL_BOTTOM + 22, str(month.year), "s", "middle"))
    for i, code in enumerate(CURRENCIES):
        x = RIGHT - 150 + i * 80
        y = RATE_TOP - 33
        body.append(f'  <rect class="{code}" x="{x}" y="{y}" width="22" height="4"/>')
        body.append(text(x + 30, RATE_TOP - 27, code, "s"))
    body.append("</svg>")
    return "\n".join(body) + "\n"


def render_table(series: Series) -> str:
    lines = [
        "| Month | EUR month-end | EUR monthly return | EUR 30-day volatility |",
        "|---|---:|---:|---:|",
    ]
    for month, rate, vol, ret in reversed(series["EUR"][-6:]):
        lines.append(f"| {month:%Y-%m} | {rate:.4f} | {ret:+.2f}% | {vol:.3f}% |")
    return "\n".join(lines)


def main() -> None:
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        series = load(con)
    CHART.parent.mkdir(parents=True, exist_ok=True)
    CHART.write_text(render_chart(series))

    readme = README.read_text()
    if START not in readme or END not in readme:
        raise SystemExit(f"README.md needs the {START} and {END} markers")
    before, rest = readme.split(START, 1)
    _, after = rest.split(END, 1)
    README.write_text(f"{before}{START}\n{render_table(series)}\n{END}{after}")
    print(f"Wrote {CHART} and the results table in {README}")


if __name__ == "__main__":
    main()
