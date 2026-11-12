"""Rank a small technical shortlist, then enrich it with cached FinMind chip data.

This is a candidate-research aid, not a trading signal. Missing chip data never
blocks the primary Taiwan price-analysis/reporting pipeline.
"""
import json
import os
import re
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
PRICE_DIR = ROOT / "data" / "tw-share" / "dayK"
UNIVERSE_FILE = ROOT / "data" / "tw-share" / "lists" / "analysis_universe.csv"
CACHE_DIR = ROOT / "data" / "tw-share" / "chip_cache"
OUTPUT_DIR = ROOT / "output"
API_URL = "https://api.finmindtrade.com/api/v4/data"
DATASETS = (
    "TaiwanStockInstitutionalInvestorsBuySell",
    "TaiwanStockMarginPurchaseShortSale",
)
MAX_CANDIDATES = 30
LOOKBACK_CALENDAR_DAYS = 180


def normalize_finmind_ticker(ticker):
    """Convert Yahoo-style symbols (e.g. 2330.TW) to FinMind stock IDs."""
    value = str(ticker).strip().upper()
    if value.endswith(".TW") or value.endswith(".TWO"):
        value = value.rsplit(".", 1)[0]
    if not re.fullmatch(r"[0-9A-Z]+", value):
        raise ValueError(f"unsupported FinMind stock ID: {ticker}")
    return value


def score_price_history(frame):
    """Return a transparent momentum/volume/liquidity score and diagnostics."""
    df = frame.copy()
    df.columns = [str(c).lower() for c in df.columns]
    required = {"close", "high", "low", "volume"}
    if not required.issubset(df.columns):
        raise ValueError("missing required OHLCV columns")
    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close", "high", "low", "volume"])
    df = df[(df["close"] > 0) & (df["volume"] >= 0)]
    if len(df) < 60:
        raise ValueError("insufficient history; need 60 valid rows")

    close = df["close"]
    volume = df["volume"]
    last = float(close.iloc[-1])
    ma20 = float(close.tail(20).mean())
    ma60 = float(close.tail(60).mean())
    ret20 = (last / float(close.iloc[-21]) - 1) * 100
    ret60 = (last / float(close.iloc[-61]) - 1) * 100
    high20 = float(df["high"].tail(20).max())
    high_distance = (last / high20 - 1) * 100 if high20 else 0.0
    vol5 = float(volume.tail(5).mean())
    vol20 = float(volume.tail(20).mean())
    volume_ratio = vol5 / vol20 if vol20 > 0 else 0.0
    turnover20 = float((close.tail(20) * volume.tail(20)).mean())

    # Transparent rule-based score, not a fitted model or claimed win rate.
    score = 0.0
    score += 25 if last > ma20 else 0
    score += 20 if ma20 > ma60 else 0
    score += max(0.0, min(20.0, ret20))
    score += max(0.0, min(15.0, ret60 / 2))
    score += 10 if high_distance >= -5 else (5 if high_distance >= -10 else 0)
    score += 10 if volume_ratio >= 1.2 else (5 if volume_ratio >= 0.8 else 0)
    return {
        "score": round(score, 2),
        "close": round(last, 4),
        "return_20d_pct": round(ret20, 2),
        "return_60d_pct": round(ret60, 2),
        "ma20": round(ma20, 4),
        "ma60": round(ma60, 4),
        "distance_from_20d_high_pct": round(high_distance, 2),
        "volume_ratio_5d_20d": round(volume_ratio, 2),
        "avg_turnover_20d": round(turnover20, 0),
    }


def build_candidate_list(price_dir=PRICE_DIR, universe_file=UNIVERSE_FILE, limit=MAX_CANDIDATES):
    universe = pd.read_csv(universe_file, dtype={"ticker": str})
    names = dict(zip(universe["ticker"].astype(str), universe["name"].astype(str)))
    manifest = pd.read_csv(UNIVERSE_FILE, dtype={"ticker": str})
    latest = pd.to_datetime(manifest["data_date"], errors="coerce").max()
    if pd.isna(latest):
        raise ValueError("analysis universe has no valid market date")
    latest_date = latest.date().isoformat()
    fresh = manifest[manifest["data_date"].astype(str) == latest_date]
    fresh_tickers = set(fresh["ticker"].astype(str))
    rows = []
    for path in sorted(Path(price_dir).glob("*.csv")):
        ticker = path.name.split("_", 1)[0]
        if ticker not in fresh_tickers:
            continue
        try:
            frame = pd.read_csv(path)
            metrics = score_price_history(frame)
            if metrics["avg_turnover_20d"] < 10_000_000:
                continue
            rows.append({"ticker": ticker, "name": names.get(ticker, ticker),
                         "market_date": latest_date, **metrics})
        except Exception as exc:
            print(f"SHORTLIST_SKIP {ticker}: {type(exc).__name__}: {exc}")
    rows.sort(key=lambda item: (item["score"], item["avg_turnover_20d"]), reverse=True)
    return rows[:limit]


def _read_cache(path):
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError):
        return None


def fetch_chip_data(candidates, token, cache_dir=CACHE_DIR, session=None, sleep_seconds=0.25):
    """Fetch at most 2 datasets per candidate; reuse cache through latest market date."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = session or requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})
    today = date.today()
    start_date = (today - timedelta(days=LOOKBACK_CALENDAR_DAYS)).isoformat()
    output = []
    for candidate in candidates:
        ticker = candidate["ticker"]
        finmind_id = normalize_finmind_ticker(ticker)
        target_date = candidate["market_date"]
        for dataset in DATASETS:
            path = cache_dir / f"{dataset}_{ticker}.json"
            cached = _read_cache(path)
            cached_rows = cached.get("data", []) if isinstance(cached, dict) else []
            cached_latest = max((str(row.get("date", "")) for row in cached_rows), default="")
            if cached_latest >= target_date and cached_rows:
                output.append({"ticker": ticker, "dataset": dataset, "status": "cache",
                               "rows": len(cached_rows), "latest_date": cached_latest})
                continue
            params = {"dataset": dataset, "data_id": finmind_id,
                      "start_date": start_date, "end_date": target_date}
            try:
                response = session.get(API_URL, params=params, timeout=30)
                response.raise_for_status()
                payload = response.json()
                if payload.get("status") != 200:
                    raise RuntimeError(f"FinMind status {payload.get('status')}: {payload.get('msg', '')}")
                rows = payload.get("data", [])
                if rows:
                    columns = set(rows[0])
                    required = {"date", "stock_id"}
                    if not required.issubset(columns):
                        raise ValueError(f"missing columns: {sorted(required - columns)}")
                    with path.open("w", encoding="utf-8") as file:
                        json.dump({"dataset": dataset, "ticker": ticker,
                                   "finmind_stock_id": finmind_id,
                                   "fetched_at": today.isoformat(), "data": rows},
                                  file, ensure_ascii=False)
                latest = max((str(row.get("date", "")) for row in rows), default="")
                output.append({"ticker": ticker, "dataset": dataset,
                               "status": "fetched" if rows else "empty",
                               "rows": len(rows), "latest_date": latest})
            except Exception as exc:
                print(f"CHIP_FETCH_ERROR {ticker} {dataset}: {type(exc).__name__}: {exc}")
                output.append({"ticker": ticker, "dataset": dataset, "status": "error",
                               "rows": 0, "latest_date": "", "error": str(exc)})
            time.sleep(sleep_seconds)
    return output


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidates = build_candidate_list()
    candidate_path = OUTPUT_DIR / "wave_candidates.csv"
    pd.DataFrame(candidates).to_csv(candidate_path, index=False, encoding="utf-8-sig")
    print(f"WAVE_CANDIDATES count={len(candidates)} path={candidate_path}")
    token = os.getenv("FINMIND_TOKEN", "").strip()
    if not token:
        print("CHIP_ENRICHMENT_SKIPPED: FINMIND_TOKEN unavailable; price analysis continues")
        return {"candidates": len(candidates), "chip_status": "skipped_no_token"}
    chip_results = fetch_chip_data(candidates, token)
    chip_path = OUTPUT_DIR / "wave_candidate_chip_status.json"
    with chip_path.open("w", encoding="utf-8") as file:
        json.dump(chip_results, file, ensure_ascii=False, indent=2)
    fetched = sum(item["status"] == "fetched" for item in chip_results)
    cached = sum(item["status"] == "cache" for item in chip_results)
    errors = sum(item["status"] == "error" for item in chip_results)
    empty = sum(item["status"] == "empty" for item in chip_results)
    print(f"CHIP_ENRICHMENT candidates={len(candidates)} requests={fetched} cache_hits={cached} empty={empty} errors={errors}")
    return {"candidates": len(candidates), "chip_requests": fetched,
            "cache_hits": cached, "chip_empty": empty, "chip_errors": errors}


if __name__ == "__main__":
    run()
