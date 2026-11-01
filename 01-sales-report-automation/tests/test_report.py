import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import report  # noqa: E402
from generate_sample_data import generate  # noqa: E402


def test_number_parsing_handles_symbols_and_commas():
    s = report._to_number(pd.Series(["$59.90", "14,50", " 3 ", "abc"]))
    assert s.tolist()[:3] == [59.90, 14.50, 3.0]
    assert pd.isna(s.iloc[3])


def test_pipeline_cleans_and_reports(tmp_path):
    data_dir = tmp_path / "data"
    generate(data_dir)
    df, qlog = report.build(data_dir)

    issues = {(s, i): n for s, i, n in qlog.issues}
    assert issues[("webshop_export.csv", "Duplicate order lines removed")] == 12
    assert issues[("webshop_export.csv", "Incomplete rows dropped")] == 1
    assert issues[("marketplace_export.csv", "Non-positive quantity (refund/noise) dropped")] == 1
    assert len(df) == 900 + 700
    assert df["sku"].str.match(r"^SKU-\d{4}$").all()
    assert df["date"].notna().all() and (df["qty"] > 0).all()

    out = tmp_path / "report.xlsx"
    report.write_excel(df, qlog, out)
    wb = load_workbook(out)
    assert {"Summary", "Monthly", "Products", "Data Quality", "Clean Data"} <= set(wb.sheetnames)
    assert len(wb["Summary"]._charts) == 2


def test_cli_end_to_end(tmp_path, capsys):
    generate(tmp_path / "in")
    out = tmp_path / "out" / "r.xlsx"
    assert report.main(["--input", str(tmp_path / "in"), "--output", str(out)]) == 0
    assert out.exists() and out.with_suffix(".html").exists()
    assert "Report written" in capsys.readouterr().out


def test_eur_prices_are_converted(tmp_path):
    generate(tmp_path)
    base, _ = report.build(tmp_path, eur_usd=1.0)
    conv, qlog = report.build(tmp_path, eur_usd=2.0)
    mp = lambda d: d[d["source"] == "marketplace_export"]["unit_price"].reset_index(drop=True)
    ws = lambda d: d[d["source"] == "webshop_export"]["unit_price"].reset_index(drop=True)
    assert (mp(conv) - (mp(base) * 2).round(2)).abs().max() < 0.011
    assert ws(conv).equals(ws(base))  # USD source untouched
    assert qlog.removed == 14
