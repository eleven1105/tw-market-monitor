# -*- coding: utf-8 -*-
import os
import time
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import yfinance as yf
from tqdm import tqdm

from stock_universe_tw import fetch_listed_common_stocks, save_universe

MARKET_CODE = "tw-share"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / MARKET_CODE / "dayK"
LIST_DIR = BASE_DIR / "data" / MARKET_CODE / "lists"
UNIVERSE_PATH = LIST_DIR / "listed_common_stocks.csv"
ANALYSIS_UNIVERSE_PATH = LIST_DIR / "analysis_universe.csv"
MAX_WORKERS = 3

DATA_DIR.mkdir(parents=True, exist_ok=True)
LIST_DIR.mkdir(parents=True, exist_ok=True)


def log(msg):
    print(f"{pd.Timestamp.now():%H:%M:%S}: {msg}")


def get_full_stock_list():
    """Return only validated TWSE-listed common stocks."""
    frame = fetch_listed_common_stocks()
    save_universe(frame, UNIVERSE_PATH)
    return frame


def download_stock_data(row):
    ticker, name = row["ticker"], row["name"]
    safe_name = "".join(
        c for c in str(name) if c.isalnum() or c in (" ", "_", "-")
    ).strip()
    output = DATA_DIR / f"{ticker}_{safe_name}.csv"

    try:
        # A same-day cache is accepted; older cache files are never analysis inputs
        # unless the ticker is explicitly written to today's analysis manifest.
        if output.exists():
            modified = datetime.fromtimestamp(output.stat().st_mtime).date()
            if modified == datetime.now().date() and output.stat().st_size > 1000:
                return {"status": "exists", "ticker": ticker, "name": name}

        time.sleep(random.uniform(0.5, 1.2))
        ticker_obj = yf.Ticker(ticker)
        for attempt in range(2):
            try:
                history = ticker_obj.history(period="2y", timeout=20)
                if history is not None and not history.empty:
                    history = history.reset_index()
                    history.columns = [str(c).lower() for c in history.columns]
                    required = {"close", "high", "low"}
                    if not required.issubset(history.columns):
                        return {"status": "error", "ticker": ticker, "name": name}
                    history.to_csv(output, index=False, encoding="utf-8-sig")
                    return {"status": "success", "ticker": ticker, "name": name}
                if attempt == 1:
                    return {"status": "empty", "ticker": ticker, "name": name}
            except Exception:
                if attempt == 1:
                    return {"status": "error", "ticker": ticker, "name": name}
                time.sleep(random.uniform(3, 7))
    except Exception as exc:
        log(f"下載 {ticker} 失敗：{exc}")
        return {"status": "error", "ticker": ticker, "name": name}


def main():
    # Remove any restored/cached manifest first. A failed run must not analyze
    # yesterday's ticker list or stale CSVs as if they were today's observations.
    ANALYSIS_UNIVERSE_PATH.unlink(missing_ok=True)

    try:
        universe = get_full_stock_list()
    except Exception as exc:
        log(f"❌ TWSE 上市普通股清單驗證失敗，停止台股分析：{exc}")
        return {"total": 0, "success": 0, "fail": 0, "universe_error": str(exc)}

    rows = universe[["ticker", "name"]].to_dict("records")
    log(f"🚀 僅下載證交所上市普通股，共 {len(rows)} 檔")

    stats = {"success": 0, "exists": 0, "empty": 0, "error": 0}
    valid_rows = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(download_stock_data, row) for row in rows]
        progress = tqdm(total=len(futures), desc="上市普通股下載")
        for future in as_completed(futures):
            result = future.result()
            stats[result["status"]] += 1
            if result["status"] in ("success", "exists"):
                valid_rows.append({
                    "ticker": result["ticker"],
                    "name": result["name"],
                })
            progress.update(1)
        progress.close()

    # This manifest is the strict allow-list consumed by analyzer.py.
    if valid_rows:
        valid_frame = pd.DataFrame(valid_rows).drop_duplicates("ticker")
        valid_frame["data_date"] = datetime.now().date().isoformat()
        save_universe(valid_frame, ANALYSIS_UNIVERSE_PATH)

    report = {
        "total": len(rows),
        "success": stats["success"] + stats["exists"],
        "fail": stats["error"] + stats["empty"],
    }
    log(f"📊 台股下載完成：{report}；明細：{stats}")
    return report


if __name__ == "__main__":
    main()
