"""Generate realistic, intentionally messy sales exports from two channels.

The goal is to mimic what clients actually send: different column names,
date formats, currency symbols, duplicate rows, stray whitespace and blanks.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

PRODUCTS = {
    "SKU-1001": ("Wireless Earbuds", 59.90),
    "SKU-1002": ("Smart Watch", 149.00),
    "SKU-1003": ("Phone Case", 14.50),
    "SKU-1004": ("USB-C Charger 65W", 34.99),
    "SKU-1005": ("Bluetooth Speaker", 79.00),
    "SKU-1006": ("Laptop Stand", 42.00),
}
COUNTRIES = ["US", "DE", "UK", "FR", "NL", "HU", "CA"]


def _rows(rng: random.Random, start: date, days: int, n: int):
    for i in range(n):
        d = start + timedelta(days=rng.randrange(days))
        sku = rng.choice(list(PRODUCTS))
        qty = rng.choices([1, 1, 1, 2, 2, 3, 5], k=1)[0]
        price = PRODUCTS[sku][1]
        discount = rng.choice([0, 0, 0, 0.1, 0.15])
        yield i, d, sku, qty, round(price * (1 - discount), 2), rng.choice(COUNTRIES)


def generate(out_dir: Path, seed: int = 42) -> list[Path]:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    start = date(2026, 1, 1)

    # Channel A: webshop export (ISO dates, dot decimals, '$' prefix)
    a = out_dir / "webshop_export.csv"
    with a.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Order ID", "Order Date", "SKU", "Product Name", "Qty", "Unit Price", "Country"])
        rows = list(_rows(rng, start, 270, 900))
        for i, d, sku, qty, price, c in rows:
            w.writerow([f"WS-{10000+i}", d.isoformat(), sku, f"  {PRODUCTS[sku][0]} ", qty, f"${price}", c])
        for r in rows[:12]:  # duplicated rows, a classic export bug
            i, d, sku, qty, price, c = r
            w.writerow([f"WS-{10000+i}", d.isoformat(), sku, PRODUCTS[sku][0], qty, f"${price}", c])
        w.writerow(["WS-BROKEN", "", "SKU-1003", "Phone Case", "", "$14.50", "US"])  # incomplete row

    # Channel B: marketplace export (EU dates, comma decimals, ';' separator)
    b = out_dir / "marketplace_export.csv"
    with b.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["order_number", "date", "item_sku", "quantity", "price_eur", "ship_country"])
        for i, d, sku, qty, price, c in _rows(rng, start, 270, 700):
            w.writerow([f"MP{70000+i}", d.strftime("%d.%m.%Y"), sku.lower(), qty, f"{price:.2f}".replace(".", ","), c.lower()])
        w.writerow(["MP-NEG", "15.03.2026", "sku-1001", "-1", "59,90", "de"])  # refund noise
    return [a, b]


if __name__ == "__main__":
    for p in generate(Path(__file__).parent / "sample_data"):
        print(f"wrote {p}")
