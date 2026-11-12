"""Audit historical price and FinMind chip-cache coverage before backtesting.

This is a data-availability audit only. It does not generate trading signals
or claim performance. It is designed to run against the restored GitHub Actions
caches without making additional API requests.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
PRICE_DIR = ROOT / "data" / "tw-share" / "dayK"
CHIP_DIR = ROOT / "data" / "tw-share" / "chip_cache"
OUTPUT_DIR = ROOT / "output"
DATASETS = (
    "TaiwanStockInstitutionalInvestorsBuySell",
    "TaiwanStockMarginPurchaseShortSale",
)


def date_span(values):
    dates = pd.to_datetime(pd.Series(values), errors="coerce").dropna()
    if dates.empty:
        return None, None, 0
    return dates.min().date().isoformat(), dates.max().date().isoformat(), int(dates.nunique())


def load_price_coverage(price_dir=PRICE_DIR):
    result = {}
    for path in Path(price_dir).glob("*.csv"):
        ticker = path.name.split("_", 1)[0]
        try:
            frame = pd.read_csv(path)
            date_col = next((c for c in frame.columns if str(c).lower() in {"date", "datetime"}), None)
            if date_col is None:
                continue
            start, end, sessions = date_span(frame[date_col])
            result[ticker] = {"price_start": start, "price_end": end,
                              "price_sessions": sessions, "price_rows": len(frame)}
        except Exception as exc:
            result[ticker] = {"price_error": f"{type(exc).__name__}: {exc}"}
    return result


def load_chip_coverage(chip_dir=CHIP_DIR):
    result = {}
    for dataset in DATASETS:
        for path in Path(chip_dir).glob(f"{dataset}_*.json"):
            ticker = path.name[len(dataset) + 1:-5]
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                rows = payload.get("data", [])
                start, end, sessions = date_span(row.get("date") for row in rows)
                item = result.setdefault(ticker, {})
                item[dataset] = {
                    "start": start, "end": end, "sessions": sessions,
                    "rows": len(rows),
                }
            except Exception as exc:
                result.setdefault(ticker, {})[dataset] = {
                    "error": f"{type(exc).__name__}: {exc}"
                }
    return result


def build_coverage_report(price_dir=PRICE_DIR, chip_dir=CHIP_DIR):
    prices = load_price_coverage(price_dir)
    chips = load_chip_coverage(chip_dir)
    tickers = sorted(set(prices) | set(chips))
    rows = []
    for ticker in tickers:
        price = prices.get(ticker, {})
        chip = chips.get(ticker, {})
        inst = chip.get(DATASETS[0], {})
        margin = chip.get(DATASETS[1], {})
        rows.append({
            "ticker": ticker,
            "price_start": price.get("price_start"),
            "price_end": price.get("price_end"),
            "price_sessions": price.get("price_sessions", 0),
            "institutional_start": inst.get("start"),
            "institutional_end": inst.get("end"),
            "institutional_sessions": inst.get("sessions", 0),
            "margin_start": margin.get("start"),
            "margin_end": margin.get("end"),
            "margin_sessions": margin.get("sessions", 0),
            "both_chip_datasets_present": bool(inst.get("rows")) and bool(margin.get("rows")),
        })
    frame = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT_DIR / "historical_chip_coverage.csv", index=False, encoding="utf-8-sig")
    summary = {
        "tickers_audited": len(rows),
        "price_history_symbols": sum(bool(p.get("price_sessions")) for p in prices.values()),
        "institutional_cache_symbols": sum(bool(c.get(DATASETS[0], {}).get("rows")) for c in chips.values()),
        "margin_cache_symbols": sum(bool(c.get(DATASETS[1], {}).get("rows")) for c in chips.values()),
        "both_chip_datasets_symbols": sum(
            bool(c.get(DATASETS[0], {}).get("rows")) and bool(c.get(DATASETS[1], {}).get("rows"))
            for c in chips.values()
        ),
        "chip_start_dates": sorted({
            d for c in chips.values() for d in (
                c.get(DATASETS[0], {}).get("start"), c.get(DATASETS[1], {}).get("start")
            ) if d
        }),
        "chip_end_dates": sorted({
            d for c in chips.values() for d in (
                c.get(DATASETS[0], {}).get("end"), c.get(DATASETS[1], {}).get("end")
            ) if d
        }),
        "report_csv": "output/historical_chip_coverage.csv",
    }
    (OUTPUT_DIR / "historical_chip_coverage_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("HISTORICAL_CHIP_COVERAGE=" + json.dumps(summary, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    build_coverage_report()
