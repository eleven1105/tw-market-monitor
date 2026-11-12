"""Rank a technical shortlist and enrich it with recent FinMind chip-flow data.

Scores are transparent research heuristics, not probabilities or trading signals.
Missing chip data remains explicitly unavailable and never blocks price reporting.
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
INSTITUTIONAL = "TaiwanStockInstitutionalInvestorsBuySell"
MARGIN = "TaiwanStockMarginPurchaseShortSale"
DATASETS = (INSTITUTIONAL, MARGIN)
MAX_CANDIDATES = 30
LOOKBACK_CALENDAR_DAYS = 180


def normalize_finmind_ticker(ticker):
    value = str(ticker).strip().upper()
    if value.endswith(".TW") or value.endswith(".TWO"):
        value = value.rsplit(".", 1)[0]
    if not re.fullmatch(r"[0-9A-Z]+", value):
        raise ValueError(f"unsupported FinMind stock ID: {ticker}")
    return value


def score_price_history(frame):
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

    close, volume = df["close"], df["volume"]
    last = float(close.iloc[-1])
    ma20, ma60 = float(close.tail(20).mean()), float(close.tail(60).mean())
    ret20 = (last / float(close.iloc[-21]) - 1) * 100
    ret60 = (last / float(close.iloc[-61]) - 1) * 100
    high20 = float(df["high"].tail(20).max())
    high_distance = (last / high20 - 1) * 100 if high20 else 0.0
    vol5, vol20 = float(volume.tail(5).mean()), float(volume.tail(20).mean())
    volume_ratio = vol5 / vol20 if vol20 > 0 else 0.0
    turnover20 = float((close.tail(20) * volume.tail(20)).mean())

    score = 0.0
    score += 25 if last > ma20 else 0
    score += 20 if ma20 > ma60 else 0
    score += max(0.0, min(20.0, ret20))
    score += max(0.0, min(15.0, ret60 / 2))
    score += 10 if high_distance >= -5 else (5 if high_distance >= -10 else 0)
    score += 10 if volume_ratio >= 1.2 else (5 if volume_ratio >= 0.8 else 0)
    # Penalize chasing: strong recent extension and stretched distance from MA20.
    chase_penalty = min(15.0, max(0.0, ret20 - 20.0) * 0.5)
    ma20_extension = (last / ma20 - 1) * 100 if ma20 else 0.0
    chase_penalty += min(10.0, max(0.0, ma20_extension - 12.0) * 0.5)
    score = max(0.0, score - chase_penalty)
    return {
        "technical_score": round(score, 2),
        "close": round(last, 4),
        "return_20d_pct": round(ret20, 2),
        "return_60d_pct": round(ret60, 2),
        "ma20": round(ma20, 4),
        "ma60": round(ma60, 4),
        "ma20_extension_pct": round(ma20_extension, 2),
        "distance_from_20d_high_pct": round(high_distance, 2),
        "volume_ratio_5d_20d": round(volume_ratio, 2),
        "avg_turnover_20d": round(turnover20, 0),
        "chase_penalty": round(chase_penalty, 2),
    }


def build_candidate_list(price_dir=PRICE_DIR, universe_file=UNIVERSE_FILE, limit=MAX_CANDIDATES):
    universe = pd.read_csv(universe_file, dtype={"ticker": str})
    names = dict(zip(universe["ticker"].astype(str), universe["name"].astype(str)))
    manifest = pd.read_csv(universe_file, dtype={"ticker": str})
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
            metrics = score_price_history(pd.read_csv(path))
            if metrics["avg_turnover_20d"] < 10_000_000:
                continue
            rows.append({"ticker": ticker, "name": names.get(ticker, ticker),
                         "market_date": latest_date, **metrics})
        except Exception as exc:
            print(f"SHORTLIST_SKIP {ticker}: {type(exc).__name__}: {exc}")
    rows.sort(key=lambda item: (item["technical_score"], item["avg_turnover_20d"]), reverse=True)
    return rows[:limit]


def _read_cache(path):
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError):
        return None


def fetch_chip_data(candidates, token, cache_dir=CACHE_DIR, session=None, sleep_seconds=0.25):
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
                    if not {"date", "stock_id"}.issubset(columns):
                        raise ValueError(f"missing columns: {sorted({'date', 'stock_id'} - columns)}")
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


def _load_dataset_rows(ticker, dataset, cache_dir=CACHE_DIR):
    cached = _read_cache(Path(cache_dir) / f"{dataset}_{ticker}.json")
    return cached.get("data", []) if isinstance(cached, dict) else []


def _investor_group(value):
    name = str(value).strip().lower()
    if "foreign" in name:
        return "foreign"
    if "investment" in name or "trust" in name:
        return "trust"
    if "dealer" in name:
        return "dealer"
    return None


def score_chip_history(institutional_rows, margin_rows, target_date):
    """Summarize total and per-investor 5/20-session flows plus margin changes."""
    result = {
        "chip_score": None, "institutional_net_5d": None,
        "institutional_net_20d": None, "institutional_positive_days_5d": None,
        "foreign_net_5d": None, "foreign_net_20d": None,
        "trust_net_5d": None, "trust_net_20d": None,
        "dealer_net_5d": None, "dealer_net_20d": None,
        "institutional_alignment_5d": None,
        "margin_balance_change_5d": None, "margin_balance_change_20d": None,
        "chip_data_status": "unavailable",
    }
    inst = pd.DataFrame(institutional_rows)
    margin = pd.DataFrame(margin_rows)
    if inst.empty or margin.empty:
        return result
    required_inst = {"date", "buy", "sell", "name"}
    required_margin = {"date", "MarginPurchaseTodayBalance"}
    if not required_inst.issubset(inst.columns) or not required_margin.issubset(margin.columns):
        result["chip_data_status"] = "schema_incomplete"
        return result

    inst["date"] = pd.to_datetime(inst["date"], errors="coerce")
    for col in ("buy", "sell"):
        inst[col] = pd.to_numeric(inst[col], errors="coerce")
    inst = inst.dropna(subset=["date", "buy", "sell"])
    inst = inst[inst["date"] <= pd.Timestamp(target_date)].copy()
    if inst.empty:
        return result
    inst["net"] = inst["buy"] - inst["sell"]
    inst["investor_group"] = inst["name"].map(_investor_group)
    daily = inst.groupby("date")["net"].sum().sort_index()
    last5, last20 = daily.tail(5), daily.tail(20)
    net5, net20 = float(last5.sum()), float(last20.sum())
    positive_days = int((last5 > 0).sum())

    category_nets = {}
    for group in ("foreign", "trust", "dealer"):
        subset = inst[inst["investor_group"] == group]
        grouped = subset.groupby("date")["net"].sum().sort_index()
        category_nets[group] = (
            float(grouped.tail(5).sum()) if not grouped.empty else None,
            float(grouped.tail(20).sum()) if not grouped.empty else None,
        )
    observed_directions = [v[0] for v in category_nets.values() if v[0] is not None]
    alignment = (sum(value > 0 for value in observed_directions)
                 if observed_directions else None)

    margin["date"] = pd.to_datetime(margin["date"], errors="coerce")
    margin["MarginPurchaseTodayBalance"] = pd.to_numeric(
        margin["MarginPurchaseTodayBalance"], errors="coerce")
    margin = margin.dropna(subset=["date", "MarginPurchaseTodayBalance"])
    margin = margin[margin["date"] <= pd.Timestamp(target_date)].sort_values("date")
    if margin.empty:
        return result
    margin_daily = margin.groupby("date")["MarginPurchaseTodayBalance"].last().sort_index()
    change5 = (float(margin_daily.iloc[-1] - margin_daily.iloc[-6])
               if len(margin_daily) >= 6 else None)
    change20 = (float(margin_daily.iloc[-1] - margin_daily.iloc[-21])
                if len(margin_daily) >= 21 else None)

    # Equal category voting prevents a single large institution type from
    # hiding disagreement. Only observed categories contribute to alignment.
    available_groups = len(observed_directions)
    alignment_points = (20.0 * alignment / available_groups
                        if available_groups else 10.0)
    inst5_points = 30 if net5 > 0 else (15 if net5 == 0 else 0)
    inst20_points = 30 if net20 > 0 else (15 if net20 == 0 else 0)
    consistency_points = 15 * positive_days / max(1, len(last5))
    margin_points = 5 if change5 is not None and change5 > 0 else 10
    chip_score = min(100.0, inst5_points + inst20_points + consistency_points + alignment_points + margin_points)

    result.update({
        "chip_score": round(chip_score, 2),
        "institutional_net_5d": round(net5, 2),
        "institutional_net_20d": round(net20, 2),
        "institutional_positive_days_5d": positive_days,
        "foreign_net_5d": round(category_nets["foreign"][0], 2) if category_nets["foreign"][0] is not None else None,
        "foreign_net_20d": round(category_nets["foreign"][1], 2) if category_nets["foreign"][1] is not None else None,
        "trust_net_5d": round(category_nets["trust"][0], 2) if category_nets["trust"][0] is not None else None,
        "trust_net_20d": round(category_nets["trust"][1], 2) if category_nets["trust"][1] is not None else None,
        "dealer_net_5d": round(category_nets["dealer"][0], 2) if category_nets["dealer"][0] is not None else None,
        "dealer_net_20d": round(category_nets["dealer"][1], 2) if category_nets["dealer"][1] is not None else None,
        "institutional_alignment_5d": f"{alignment}/{available_groups}" if available_groups else None,
        "margin_balance_change_5d": round(change5, 2) if change5 is not None else None,
        "margin_balance_change_20d": round(change20, 2) if change20 is not None else None,
        "chip_data_status": "available",
    })
    return result


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidates = build_candidate_list()
    token = os.getenv("FINMIND_TOKEN", "").strip()
    candidate_path = OUTPUT_DIR / "wave_candidates.csv"
    pd.DataFrame(candidates).to_csv(candidate_path, index=False, encoding="utf-8-sig")
    print(f"WAVE_CANDIDATES count={len(candidates)} path={candidate_path}")
    if not token:
        print("CHIP_ENRICHMENT_SKIPPED: FINMIND_TOKEN unavailable; price analysis continues")
        return {"candidates": len(candidates), "chip_status": "skipped_no_token"}

    chip_results = fetch_chip_data(candidates, token)
    chip_status_path = OUTPUT_DIR / "wave_candidate_chip_status.json"
    with chip_status_path.open("w", encoding="utf-8") as file:
        json.dump(chip_results, file, ensure_ascii=False, indent=2)

    enriched = []
    for candidate in candidates:
        inst = _load_dataset_rows(candidate["ticker"], INSTITUTIONAL)
        margin = _load_dataset_rows(candidate["ticker"], MARGIN)
        chip_metrics = score_chip_history(inst, margin, candidate["market_date"])
        combined = dict(candidate)
        combined.update(chip_metrics)
        combined["combined_research_score"] = round(
            candidate["technical_score"] * 0.65 +
            (chip_metrics["chip_score"] if chip_metrics["chip_score"] is not None else 50.0) * 0.35, 2)
        enriched.append(combined)
    enriched.sort(key=lambda item: item["combined_research_score"], reverse=True)
    enriched_path = OUTPUT_DIR / "wave_candidates_enriched.csv"
    pd.DataFrame(enriched).to_csv(enriched_path, index=False, encoding="utf-8-sig")
    available = sum(item["chip_data_status"] == "available" for item in enriched)
    print(f"CHIP_SCORE_SUMMARY available={available} unavailable={len(enriched)-available}")
    print(f"WAVE_ENRICHED_REPORT path={enriched_path}")
    return {"candidates": len(candidates), "chip_status_rows": len(chip_results),
            "chip_available": available, "chip_unavailable": len(enriched)-available}


if __name__ == "__main__":
    run()
