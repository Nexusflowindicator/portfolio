"""Sales Report Automation

Turns messy multi-channel sales exports into a clean, client-ready Excel
report (KPIs, monthly trend, product and country breakdowns, charts) plus a
short HTML summary that can be pasted into an e-mail.

Usage:
    python report.py --input sample_data --output output/sales_report.xlsx
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

log = logging.getLogger("sales_report")

# Map every known source column name to one canonical schema.
COLUMN_MAP = {
    "order id": "order_id", "order_number": "order_id",
    "order date": "date", "date": "date",
    "sku": "sku", "item_sku": "sku",
    "qty": "qty", "quantity": "qty",
    "unit price": "unit_price", "price_eur": "unit_price",
    "country": "country", "ship_country": "country",
}
PRODUCT_NAMES = {
    "SKU-1001": "Wireless Earbuds", "SKU-1002": "Smart Watch", "SKU-1003": "Phone Case",
    "SKU-1004": "USB-C Charger 65W", "SKU-1005": "Bluetooth Speaker", "SKU-1006": "Laptop Stand",
}  # in a client project this comes from their product catalogue
REQUIRED = ["order_id", "date", "sku", "qty", "unit_price", "country"]


@dataclass
class QualityLog:
    issues: list[tuple[str, str, int]] = field(default_factory=list)

    def add(self, source: str, issue: str, count: int) -> None:
        if count:
            self.issues.append((source, issue, int(count)))
            log.info("%s: %s (%d)", source, issue, count)

    @property
    def removed(self) -> int:
        return sum(n for _, issue, n in self.issues if "dropped" in issue or "removed" in issue)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.issues, columns=["Source", "Issue", "Rows"])


def _to_number(s: pd.Series) -> pd.Series:
    cleaned = (
        s.astype(str).str.strip()
        .str.replace(r"[^\d,.\-]", "", regex=True)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def load_source(path: Path, qlog: QualityLog, eur_usd: float = 1.08) -> pd.DataFrame:
    sep = ";" if path.read_text(encoding="utf-8").splitlines()[0].count(";") > 0 else ","
    raw = pd.read_csv(path, sep=sep, dtype=str)
    raw.columns = [c.strip().lower() for c in raw.columns]
    in_eur = "price_eur" in raw.columns
    df = raw.rename(columns=COLUMN_MAP)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    df = df[REQUIRED].copy()

    dayfirst = df["date"].dropna().astype(str).str.contains(r"^\d{2}\.\d{2}\.\d{4}$").mean() > 0.5
    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=dayfirst,
                                format="%d.%m.%Y" if dayfirst else "%Y-%m-%d")
    df["sku"] = df["sku"].str.strip().str.upper()
    df["country"] = df["country"].str.strip().str.upper()
    df["qty"] = _to_number(df["qty"])
    df["unit_price"] = _to_number(df["unit_price"])
    if in_eur:  # normalise everything to USD so channels are comparable
        df["unit_price"] = (df["unit_price"] * eur_usd).round(2)
        qlog.add(path.name, f"Prices converted EUR to USD @ {eur_usd}", len(df))
    df["source"] = path.stem

    bad = df[REQUIRED].isna().any(axis=1)
    qlog.add(path.name, "Incomplete rows dropped", bad.sum())
    df = df[~bad]
    neg = df["qty"] <= 0
    qlog.add(path.name, "Non-positive quantity (refund/noise) dropped", neg.sum())
    df = df[~neg]
    dup = df.duplicated(subset=["order_id", "sku"])
    qlog.add(path.name, "Duplicate order lines removed", dup.sum())
    df = df[~dup]
    df["qty"] = df["qty"].astype(int)
    df["revenue"] = (df["qty"] * df["unit_price"]).round(2)
    return df


def build(input_dir: Path, eur_usd: float = 1.08) -> tuple[pd.DataFrame, QualityLog]:
    qlog = QualityLog()
    files = sorted(input_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {input_dir}")
    data = pd.concat([load_source(f, qlog, eur_usd) for f in files], ignore_index=True)
    return data, qlog


def kpis(df: pd.DataFrame) -> dict[str, float]:
    orders = df["order_id"].nunique()
    revenue = df["revenue"].sum()
    return {
        "Total revenue": round(revenue, 2),
        "Orders": orders,
        "Units sold": int(df["qty"].sum()),
        "Average order value": round(revenue / orders, 2) if orders else 0.0,
        "Products": df["sku"].nunique(),
        "Countries": df["country"].nunique(),
    }


def summaries(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    monthly = (df.assign(Month=df["date"].dt.to_period("M").astype(str))
                 .groupby("Month").agg(Revenue=("revenue", "sum"), Orders=("order_id", "nunique"))
                 .round(2).reset_index())
    product = (df.groupby("sku").agg(Units=("qty", "sum"), Revenue=("revenue", "sum"))
                 .sort_values("Revenue", ascending=False).round(2).reset_index()
                 .rename(columns={"sku": "SKU"}))
    product.insert(1, "Product", product["SKU"].map(PRODUCT_NAMES).fillna(""))
    country = (df.groupby("country").agg(Revenue=("revenue", "sum"), Orders=("order_id", "nunique"))
                 .sort_values("Revenue", ascending=False).round(2).reset_index()
                 .rename(columns={"country": "Country"}))
    channel = (df.groupby("source").agg(Revenue=("revenue", "sum"), Orders=("order_id", "nunique"))
                 .round(2).reset_index().rename(columns={"source": "Channel"}))
    return {"Monthly": monthly, "Products": product, "Countries": country, "Channels": channel}


HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")


def _style_sheet(ws) -> None:
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")
    for col in ws.columns:
        width = max(len(str(c.value or "")) for c in col) + 3
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(width, 40)
    ws.freeze_panes = "A2"


def write_excel(df: pd.DataFrame, qlog: QualityLog, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tables = summaries(df)
    k = pd.DataFrame(list(kpis(df).items()), columns=["KPI", "Value"])
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        k.to_excel(xw, sheet_name="Summary", index=False)
        for name, t in tables.items():
            t.to_excel(xw, sheet_name=name, index=False)
        qlog.frame().to_excel(xw, sheet_name="Data Quality", index=False)
        clean = df.assign(date=df["date"].dt.date)
        clean.to_excel(xw, sheet_name="Clean Data", index=False)

    wb = load_workbook(out)
    for ws in wb.worksheets:
        _style_sheet(ws)

    m = wb["Monthly"]
    line = LineChart(); line.title = "Monthly revenue"; line.height, line.width = 8, 16
    line.add_data(Reference(m, min_col=2, min_row=1, max_row=m.max_row), titles_from_data=True)
    line.set_categories(Reference(m, min_col=1, min_row=2, max_row=m.max_row))
    wb["Summary"].add_chart(line, "D2")

    p = wb["Products"]
    bar = BarChart(); bar.title = "Revenue by product"; bar.height, bar.width = 8, 16
    bar.add_data(Reference(p, min_col=4, min_row=1, max_row=p.max_row), titles_from_data=True)
    bar.set_categories(Reference(p, min_col=2, min_row=2, max_row=p.max_row))
    wb["Summary"].add_chart(bar, "D19")
    money = '"$"#,##0.00'
    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        for col in ws.iter_cols(min_row=1, max_row=1):
            if col[0].value in ("Revenue", "revenue", "unit_price"):
                for c in ws[col[0].column_letter][1:]:
                    c.number_format = money
    s = wb["Summary"]
    for r in range(2, s.max_row + 1):
        label = s.cell(r, 1).value
        s.cell(r, 2).number_format = money if label in ("Total revenue", "Average order value") else "#,##0"
    line.smooth = False
    for ser in line.series:
        ser.smooth = False
    wb.save(out)


def write_html_summary(df: pd.DataFrame, qlog: QualityLog, out: Path) -> None:
    k = kpis(df)
    top = summaries(df)["Products"].head(3)
    items = "".join(f"<li><b>{r.Product}</b>: ${r.Revenue:,.2f} ({r.Units} units)</li>" for r in top.itertuples())
    rows = "".join(f"<tr><td>{n}</td><td style='text-align:right'>{v:,}</td></tr>" for n, v in k.items())
    removed = qlog.removed
    out.write_text(
        f"""<!doctype html><html><body style="font-family:Arial,sans-serif;max-width:640px">
<h2>Sales report: {df['date'].min():%b %d} to {df['date'].max():%b %d, %Y}</h2>
<table cellpadding="6" style="border-collapse:collapse">{rows}</table>
<h3>Top products</h3><ul>{items}</ul>
<p style="color:#666">{removed} problematic rows were cleaned automatically. See the "Data Quality" sheet.</p>
</body></html>""",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=Path("sample_data"))
    ap.add_argument("--output", type=Path, default=Path("output/sales_report.xlsx"))
    ap.add_argument("--eur-usd", type=float, default=1.08, help="FX rate for EUR-priced sources")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    df, qlog = build(args.input, args.eur_usd)
    write_excel(df, qlog, args.output)
    write_html_summary(df, qlog, args.output.with_suffix(".html"))
    k = kpis(df)
    print(f"Report written to {args.output}")
    print(f"Revenue ${k['Total revenue']:,.2f} | {k['Orders']} orders | AOV ${k['Average order value']:,.2f}")
    print(f"Cleaned {qlog.removed} problematic rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
