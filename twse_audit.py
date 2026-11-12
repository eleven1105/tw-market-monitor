# -*- coding: utf-8 -*-
"""Read-only checks against the Taiwan Stock Exchange official monthly daily-bar API."""
from datetime import date, datetime
import requests

TWSE_STOCK_DAY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"


def _parse_twse_date(value):
    raw = str(value).strip()
    if not raw:
        return None
    # Local CSV timestamps may include time and a UTC offset, e.g.
    # 2026-11-12 00:00:00+08:00. Normalize these before parsing ROC dates.
    try:
        iso_value = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(iso_value).date()
    except ValueError:
        pass

    parts = raw.replace("-", "/").split("/")
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


def audit_twse_symbols(tickers, expected_date=None, target_bars=None):
    """Compare exact flagged dates with TWSE raw bars; diagnostics only, never rewrite prices."""
    results = {}
    target_bars = target_bars or {}
    for ticker in sorted(set(str(item).split("(", 1)[0] for item in tickers if item)):
        try:
            target = target_bars.get(ticker) or {}
            dates_to_fetch = []
            for value in (expected_date, target.get("date")):
                parsed = _parse_twse_date(value) if value else None
                if parsed and (parsed.year, parsed.month) not in {
                    (d.year, d.month) for d in dates_to_fetch
                }:
                    dates_to_fetch.append(parsed)
            if not dates_to_fetch:
                dates_to_fetch = [date.today().replace(day=1)]

            bars_by_date = {}
            statuses = []
            for month_date in dates_to_fetch:
                result = fetch_official_month_bars(ticker, month_date=month_date)
                if result.get("status") != "ok":
                    statuses.append(result)
                    continue
                for bar in result["bars"]:
                    bars_by_date[bar["date"]] = bar

            latest = max(bars_by_date.values(), key=lambda bar: bar["date"]) if bars_by_date else None
            expected_bar = bars_by_date.get(str(expected_date)) if expected_date else None
            target_date = target.get("date")
            target_bar = bars_by_date.get(str(target_date)) if target_date else None
            if latest is None:
                status = statuses[0] if statuses else {"status": "empty"}
                print(f"🔎 TWSE 官方行情查核 {ticker}: {status.get('status')} ({status.get('message', '')})")
                results[ticker] = status
                continue

            print(
                f"🔎 TWSE 官方行情查核 {ticker}: 最新日期={latest['date']}；"
                f"官方原始 OHLC={latest['open']}/{latest['high']}/{latest['low']}/{latest['close']}；"
                f"共同基準日 {expected_date} "
                f"{'有資料' if expected_bar else '無資料'}"
            )
            if target_date:
                print(
                    f"🔬 異常日精確比對 {ticker} {target_date}: "
                    f"本機 Yahoo OHLC={target.get('open')}/{target.get('high')}/"
                    f"{target.get('low')}/{target.get('close')}；"
                    f"TWSE 原始 OHLC="
                    f"{target_bar['open']}/{target_bar['high']}/{target_bar['low']}/{target_bar['close']}"
                    if target_bar else
                    f"🔬 異常日精確比對 {ticker} {target_date}: TWSE 該月無該日資料"
                )
            results[ticker] = {
                "status": "ok",
                "latest": latest,
                "expected": expected_bar,
                "target": target_bar,
                "target_local": target,
                "unavailable_months": statuses,
            }
        except Exception as exc:
            print(f"⚠️ TWSE 官方行情查核 {ticker} 失敗：{type(exc).__name__}: {exc}")
            results[ticker] = {"status": "error", "message": str(exc)}
    return results
