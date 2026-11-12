import json
import os
import sys
import time
from datetime import date, timedelta

import requests

API_URL = "https://api.finmindtrade.com/api/v4/data"
DATASETS = {
    "TaiwanStockInstitutionalInvestorsBuySell": {"required": {"date", "stock_id", "buy", "sell", "name"}},
    "TaiwanStockMarginPurchaseShortSale": {"required": {"date", "stock_id", "MarginPurchaseTodayBalance", "ShortSaleTodayBalance"}},
}
# Representative listed common stocks across large-cap, electronics, and smaller-cap profiles.
SAMPLES = ["2330", "2317", "2454", "2382", "6698", "1808"]


def main():
    token = os.getenv("FINMIND_TOKEN", "").strip()
    if not token:
        raise SystemExit("FINMIND_TOKEN secret is missing")

    end_date = date.today()
    start_date = end_date - timedelta(days=180)
    headers = {"Authorization": f"Bearer {token}"}
    session = requests.Session()
    session.headers.update(headers)
    results = []
    failures = []

    for dataset, spec in DATASETS.items():
        for ticker in SAMPLES:
            params = {
                "dataset": dataset,
                "data_id": ticker,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            try:
                response = session.get(API_URL, params=params, timeout=30)
                response.raise_for_status()
                payload = response.json()
                if payload.get("status") != 200:
                    raise RuntimeError(f"API status={payload.get('status')}: {payload.get('msg', 'unknown')}")
                rows = payload.get("data", [])
                if rows:
                    columns = set(rows[0].keys())
                    missing = sorted(spec["required"] - columns)
                    if missing:
                        raise RuntimeError(f"missing required columns: {missing}")
                    dates = sorted({str(row.get("date", "")) for row in rows if row.get("date")})
                    latest = dates[-1] if dates else None
                else:
                    latest = None
                results.append({
                    "dataset": dataset,
                    "ticker": ticker,
                    "row_count": len(rows),
                    "latest_date": latest,
                    "schema_ok": bool(rows),
                    "empty": not bool(rows),
                })
                print(f"{dataset} {ticker}: rows={len(rows)} latest={latest or 'NONE'}")
            except Exception as exc:
                failures.append({"dataset": dataset, "ticker": ticker, "error": str(exc)})
                print(f"ERROR {dataset} {ticker}: {exc}")
            time.sleep(1.2)

    nonempty = sum(1 for item in results if item["row_count"] > 0)
    summary = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "samples": SAMPLES,
        "datasets": list(DATASETS),
        "requests": len(results) + len(failures),
        "nonempty_responses": nonempty,
        "empty_responses": sum(1 for item in results if item["empty"]),
        "failures": failures,
        "results": results,
    }
    os.makedirs("output", exist_ok=True)
    with open("output/finmind_chip_probe.json", "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
    print("CHIP_PROBE_SUMMARY=" + json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False))

    if failures or nonempty == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
