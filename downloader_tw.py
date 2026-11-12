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


def _latest_csv_date(path):
    """Return the latest actual market-data date stored in a CSV, never file mtime."""
    try:
        frame = pd.read_csv(path, usecols=lambda col: str(col).lower() in {"date", "datetime"})
        if frame.empty or len(frame.columns) == 0:
            return None
        values = pd.to_datetime(frame.iloc[:, 0], errors="coerce").dropna()
        return values.max().date() if not values.empty else None
    except Exception:
        return None


def download_stock_data(row):
    ticker, name = row["ticker"], row["name"]
    safe_name = "".join(
        c for c in str(name) if c.isalnum() or c in (" ", "_", "-")
    ).strip()
    output = DATA_DIR / f"{ticker}_{safe_name}.csv"

    try:
        # Validate the actual last market-data date. GitHub cache restore can
        # reset file mtimes, so mtime alone must never certify fresh price data.
        if output.exists() and output.stat().st_size > 1000:
            latest_date = _latest_csv_date(output)
            age_days = (datetime.now().date() - latest_date).days if latest_date else 999
            if latest_date and 0 <= age_days <= 5:
                return {
                    "status": "exists", "ticker": ticker, "name": name,
                    "latest_data_date": latest_date.isoformat(),
                }

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
                    latest_date = pd.to_datetime(history["date"], errors="coerce").dropna().max()
                    return {
                        "status": "success", "ticker": ticker, "name": name,
                        "latest_data_date": latest_date.date().isoformat(),
                    }
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
                latest_data_date = result.get("latest_data_date") or _latest_csv_date(
                    DATA_DIR / f"{result['ticker']}_{''.join(c for c in str(result['name']) if c.isalnum() or c in (' ', '_', '-')).strip()}.csv"
                )
                normalized_date = (
                    pd.to_datetime(latest_data_date, errors="coerce").date().isoformat()
                    if latest_data_date is not None and pd.notna(pd.to_datetime(latest_data_date, errors="coerce"))
                    else ""
                )
                valid_rows.append({
                    "ticker": result["ticker"],
                    "name": result["name"],
                    "latest_data_date": normalized_date,
                })
            progress.update(1)
        progress.close()

    # This manifest is the strict allow-list consumed by analyzer.py.
    if valid_rows:
        valid_frame = pd.DataFrame(valid_rows).drop_duplicates("ticker")
        valid_frame["manifest_created_at"] = datetime.now().isoformat(timespec="seconds")
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
