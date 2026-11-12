"""Backfill up to two years of FinMind chip history for the daily top-30 pilot cohort.

The cohort is intentionally labeled exploratory: selecting today's leaders and
backfilling them does not remove survivorship/selection bias and is not a
market-wide strategy backtest.
"""
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
CANDIDATE_FILE = ROOT / "output" / "wave_candidates.csv"
CACHE_DIR = ROOT / "data" / "tw-share" / "chip_cache"
OUTPUT_DIR = ROOT / "output"
API_URL = "https://api.finmindtrade.com/api/v4/data"
DATASETS = (
    "TaiwanStockInstitutionalInvestorsBuySell",
    "TaiwanStockMarginPurchaseShortSale",
)


def backfill(candidates, token, cache_dir=CACHE_DIR, session=None, sleep_seconds=0.4):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = session or requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})
    results = []
    for candidate in candidates:
        ticker = str(candidate["ticker"])
        stock_id = ticker.rsplit(".", 1)[0]
        end_date = str(candidate["market_date"])
        start_date = (pd.Timestamp(end_date) - pd.Timedelta(days=730)).date().isoformat()
        for dataset in DATASETS:
            path = cache_dir / f"{dataset}_{ticker}.json"
            params = {
                "dataset": dataset, "data_id": stock_id,
                "start_date": start_date, "end_date": end_date,
            }
            try:
                response = session.get(API_URL, params=params, timeout=40)
                response.raise_for_status()
                payload = response.json()
                if payload.get("status") != 200:
                    raise RuntimeError(f"FinMind status {payload.get('status')}: {payload.get('msg', '')}")
                rows = payload.get("data", [])
                if rows:
                    if not {"date", "stock_id"}.issubset(rows[0]):
                        raise ValueError("response missing date/stock_id fields")
                    dates = sorted(str(row["date"]) for row in rows if row.get("date"))
                    # Replace the short cache only with a non-empty, date-bounded
                    # response; retain prior cache if the provider returns no rows.
                    path.write_text(json.dumps({
                        "dataset": dataset, "ticker": ticker,
                        "finmind_stock_id": stock_id,
                        "fetched_at": datetime.now().date().isoformat(),
                        "requested_start_date": start_date,
                        "requested_end_date": end_date,
                        "data": rows,
                    }, ensure_ascii=False), encoding="utf-8")
                    results.append({
                        "ticker": ticker, "dataset": dataset, "status": "fetched",
                        "rows": len(rows), "start_date": dates[0], "end_date": dates[-1],
                        "requested_start_date": start_date, "requested_end_date": end_date,
                    })
                else:
                    results.append({
                        "ticker": ticker, "dataset": dataset, "status": "empty",
                        "rows": 0, "start_date": None, "end_date": None,
                        "requested_start_date": start_date, "requested_end_date": end_date,
                    })
            except Exception as exc:
                results.append({
                    "ticker": ticker, "dataset": dataset, "status": "error",
                    "rows": 0, "error": f"{type(exc).__name__}: {exc}",
                    "requested_start_date": start_date, "requested_end_date": end_date,
                })
            time.sleep(sleep_seconds)
    return results


def main():
    token = os.getenv("FINMIND_TOKEN", "").strip()
    if not token:
        raise SystemExit("FINMIND_TOKEN secret is missing")
    candidates = pd.read_csv(CANDIDATE_FILE, dtype={"ticker": str}).to_dict("records")
    results = backfill(candidates, token)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "historical_chip_backfill_status.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    fetched = sum(item["status"] == "fetched" for item in results)
    errors = sum(item["status"] == "error" for item in results)
    print("HISTORICAL_CHIP_BACKFILL=" + json.dumps({
        "candidate_symbols": len(candidates), "requests": len(results),
        "fetched": fetched, "empty": sum(x["status"] == "empty" for x in results),
        "errors": errors, "status_file": str(path),
        "cohort_note": "today's top-30 pilot cohort; exploratory, not market-wide or survivorship-bias-free",
    }, ensure_ascii=False))
    if errors:
        raise SystemExit(f"{errors} historical chip requests failed")


if __name__ == "__main__":
    main()
