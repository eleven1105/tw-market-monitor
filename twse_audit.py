# -*- coding: utf-8 -*-
"""Read-only checks against the Taiwan Stock Exchange official monthly daily-bar API."""
from datetime import date
import requests

TWSE_STOCK_DAY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"


def _parse_twse_date(value):
    parts = str(value).strip().replace("-", "/").split("/")
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(part) for part in parts)
        if year < 1911:
            year += 1911
        return date(year, month, day)
    except (TypeError, ValueError):
        return None


def _parse_price(value):
    raw = str(value).strip().replace(",", "")
    if raw in {"", "--", "---", "X", "nan", "None"}:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def fetch_official_month_bars(ticker, month_date=None, timeout=15):
    """Fetch one symbol's official TWSE daily bars for the month; never alters local data."""
    stock_no = str(ticker).split(".", 1)[0]
    month_date = month_date or date.today()
    query_date = month_date.strftime("%Y%m01")
    response = requests.get(
        TWSE_STOCK_DAY_URL,
        params={"response": "json", "date": query_date, "stockNo": stock_no},
        headers={"User-Agent": "Mozilla/5.0 (compatible; TaiwanMarketDataQuality/1.0)"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("stat") != "OK":
        return {"status": "unavailable", "message": payload.get("stat", "unknown")}
    fields = payload.get("fields") or []
    rows = payload.get("data") or []
    indexes = {str(name).strip(): i for i, name in enumerate(fields)}
    aliases = {
        "date": ("日期", "Date"),
        "open": ("開盤價", "OpeningPrice"),
        "high": ("最高價", "HighestPrice"),
        "low": ("最低價", "LowestPrice"),
        "close": ("收盤價", "ClosingPrice"),
    }
    positions = {}
    for key, names in aliases.items():
        positions[key] = next((indexes[name] for name in names if name in indexes), None)
    if any(position is None for position in positions.values()):
        return {"status": "invalid_schema", "message": "required TWSE fields missing"}
    bars = []
    for row in rows:
        try:
            parsed_date = _parse_twse_date(row[positions["date"]])
            if parsed_date is None:
                continue
            bars.append({
                "date": parsed_date.isoformat(),
                "open": _parse_price(row[positions["open"]]),
                "high": _parse_price(row[positions["high"]]),
                "low": _parse_price(row[positions["low"]]),
                "close": _parse_price(row[positions["close"]]),
            })
        except (IndexError, TypeError):
            continue
    return {"status": "ok", "bars": bars}


def audit_twse_symbols(tickers, expected_date=None):
    """Print official raw OHLC/date observations for a small diagnostic ticker set."""
    results = {}
    for ticker in sorted(set(str(item).split("(", 1)[0] for item in tickers if item)):
        try:
            result = fetch_official_month_bars(ticker)
            if result.get("status") != "ok":
                print(f"🔎 TWSE 官方行情查核 {ticker}: {result.get('status')} ({result.get('message', '')})")
                results[ticker] = result
                continue
            bars = result["bars"]
            latest = max(bars, key=lambda bar: bar["date"]) if bars else None
            target = next((bar for bar in bars if bar["date"] == str(expected_date)), None) if expected_date else None
            if latest is None:
                print(f"🔎 TWSE 官方行情查核 {ticker}: 本月無有效日成交資料")
            else:
                print(
                    f"🔎 TWSE 官方行情查核 {ticker}: 最新日期={latest['date']}；"
                    f"最新原始 OHLC={latest['open']}/{latest['high']}/{latest['low']}/{latest['close']}；"
                    f"基準日 {expected_date} {'有資料' if target else '無資料'}"
                )
            results[ticker] = {"status": "ok", "latest": latest, "target": target}
        except Exception as exc:
            print(f"⚠️ TWSE 官方行情查核 {ticker} 失敗：{type(exc).__name__}: {exc}")
            results[ticker] = {"status": "error", "message": str(exc)}
    return results
