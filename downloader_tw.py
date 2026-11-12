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
from twse_audit import audit_twse_symbols

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


def latest_observed_date(valid_rows):
    """Return the freshest non-empty market date observed in this batch."""
    dated_rows = [row["data_date"] for row in valid_rows if row.get("data_date")]
    return max(dated_rows) if dated_rows else None


def should_replace_history(cached_latest, fetched_latest):
    """Never overwrite a newer local history with an older vendor response."""
    return fetched_latest is not None and (
        cached_latest is None or fetched_latest >= cached_latest
    )


def select_lagging_rows(valid_rows):
    """Select cached symbols behind the freshest date observed in this batch."""
    latest_date = latest_observed_date(valid_rows)
    if latest_date is None:
        return []
    return [
        row for row in valid_rows
        if row.get("data_date") and row["data_date"] < latest_date
    ]



def build_download_report(total, stats, valid_rows):
    """Separate locally available history from rows matching the latest market date."""
    latest_date = latest_observed_date(valid_rows)
    current_date_count = sum(
        1 for row in valid_rows if latest_date and row.get("data_date") == latest_date
    )
    available_count = stats["success"] + stats["exists"] + stats["stale"]
    return {
        "total": total,
        "success": available_count,
        "fail": stats["error"] + stats["empty"],
        "latest_data_date": latest_date,
        "current_date": current_date_count,
        "stale_date": max(0, len(valid_rows) - current_date_count),
        "stale_refresh": stats.get("stale_refresh", 0),
    }

def download_stock_data(row, force_refresh=False):
    ticker, name = row["ticker"], row["name"]
    safe_name = "".join(
        c for c in str(name) if c.isalnum() or c in (" ", "_", "-")
    ).strip()
    output = DATA_DIR / f"{ticker}_{safe_name}.csv"

    try:
        # Preserve the newest cached history if a vendor refresh returns an older snapshot.
        cached_latest = _latest_csv_date(output) if output.exists() else None
        # Validate the actual last market-data date. GitHub cache restore can
        # reset file mtimes, so mtime alone must never certify fresh price data.
        if not force_refresh and output.exists() and output.stat().st_size > 1000:
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
                    latest_date = pd.to_datetime(history["date"], errors="coerce").dropna().max()
                    if pd.isna(latest_date):
                        return {"status": "error", "ticker": ticker, "name": name}
                    fetched_date = latest_date.date()
                    if not should_replace_history(cached_latest, fetched_date):
                        return {
                            "status": "stale", "ticker": ticker, "name": name,
                            "latest_data_date": fetched_date.isoformat(),
                            "cached_data_date": cached_latest.isoformat(),
                        }
                    history.to_csv(output, index=False, encoding="utf-8-sig")
                    return {
                        "status": "success", "ticker": ticker, "name": name,
                        "latest_data_date": fetched_date.isoformat(),
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

    stats = {"success": 0, "exists": 0, "empty": 0, "error": 0, "stale": 0, "stale_refresh": 0}
    valid_rows = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(download_stock_data, row) for row in rows]
        progress = tqdm(total=len(futures), desc="上市普通股下載")
        for future in as_completed(futures):
            result = future.result()
            stats[result["status"]] += 1
            if result["status"] in ("success", "exists", "stale"):
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
                    "data_date": normalized_date,
                })
            progress.update(1)
        progress.close()

    # A restored cache can be one trading day behind even when its calendar age
    # is small. Once the batch establishes the freshest observed market date,
    # selectively refresh only lagging symbols instead of accepting stale bars.
    if valid_rows:
        latest_observed = latest_observed_date(valid_rows)
        lagging_rows = select_lagging_rows(valid_rows)
        if lagging_rows:
            log(
                f"🔄 發現 {len(lagging_rows)} 檔行情落後最新日期 {latest_observed}，"
                "啟動定向強制更新"
            )
            refreshed = 0
            for old_row in lagging_rows:
                result = download_stock_data(old_row, force_refresh=True)
                fetched_date = result.get("latest_data_date")
                if result["status"] == "success" and fetched_date:
                    if fetched_date > old_row["data_date"]:
                        old_row["data_date"] = fetched_date
                        stats["success"] += 1
                        stats["exists"] = max(0, stats["exists"] - 1)
                    if fetched_date >= latest_observed:
                        refreshed += 1
                    else:
                        stats["stale_refresh"] += 1
                        log(
                            f"⚠️ {old_row['ticker']} 已更新至 {fetched_date}，"
                            f"但仍落後共同基準日 {latest_observed}，暫不納入共同截面"
                        )
                else:
                    stats["stale_refresh"] += 1
                    log(
                        f"⚠️ {old_row['ticker']} 定向更新未取得較新行情；"
                        f"來源回傳 {fetched_date or result['status']}，"
                        f"保留原始檔並由分析白名單排除"
                    )
            log(f"🔄 定向更新達標：{refreshed}/{len(lagging_rows)} 檔")
            still_lagging = [row["ticker"] for row in lagging_rows if row["data_date"] < latest_observed]
            if still_lagging:
                log("🔎 改以 TWSE 官方原始日成交資料查核落後標的")
                audit_twse_symbols(still_lagging, expected_date=latest_observed)

    # This manifest is the strict allow-list consumed by analyzer.py.
    if valid_rows:
        valid_frame = pd.DataFrame(valid_rows).drop_duplicates("ticker")
        valid_frame["manifest_created_at"] = datetime.now().isoformat(timespec="seconds")
        save_universe(valid_frame, ANALYSIS_UNIVERSE_PATH)
        date_counts = valid_frame["data_date"].replace("", pd.NA).value_counts()
        if not date_counts.empty:
            latest_universe_date = max(date_counts.index)
            print(
                "📅 行情日期覆蓋："
                f"最新 {latest_universe_date}；"
                f"最舊 {date_counts.index.min()}；"
                f"不同日期 {len(date_counts)} 種；"
                f"各日期檔數 {date_counts.sort_index().to_dict()}"
            )
            lagged = valid_frame[
                valid_frame["data_date"].ne(latest_universe_date)
                & valid_frame["data_date"].ne("")
            ]
            if not lagged.empty:
                print(
                    "⚠️ 行情日期落後於全體最新日期的標的："
                    + ", ".join(
                        f"{row.ticker}({row.data_date})"
                        for row in lagged.itertuples(index=False)
                    )
                )
        missing_dates = int(valid_frame["data_date"].eq("").sum())
        if missing_dates:
            log(f"⚠️ 白名單中有 {missing_dates} 檔缺少行情日期，後續需排除")

    report = build_download_report(len(rows), stats, valid_rows)
    log(f"📊 台股下載完成：{report}；明細：{stats}")
    return report


if __name__ == "__main__":
    main()
