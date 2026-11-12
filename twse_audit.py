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



def reconcile_official_low(local_high, local_low, local_close, official_bar, tolerance=1e-4):
    """Return an official low only when local high and close independently match TWSE.

    This narrowly repairs a bad low field; it never replaces an entire OHLC bar or
    mixes raw exchange prices into a differently adjusted vendor series.
    """
    try:
        high = float(local_high)
        low = float(local_low)
        close = float(local_close)
        official_high = float(official_bar["high"])
        official_low = float(official_bar["low"])
        official_close = float(official_bar["close"])
    except (KeyError, TypeError, ValueError):
        return None

    if not all(map(lambda value: value > 0, (
        high, low, close, official_high, official_low, official_close
    ))):
        return None
    if not (official_high >= official_close >= official_low):
        return None
    if abs(high - official_high) > tolerance or abs(close - official_close) > tolerance:
        return None
    if close >= low or low <= official_low:
        return None
    return official_low


def classify_market_data_status(official_bar, local_bar=None, official_source_status='ok', exchange_suspended=False, exchange_open=False):
    """Classify an exact-date gap; never infer suspension from a missing bar."""
    if official_source_status != 'ok':
        return {'classification': 'official_source_unavailable', 'reason': 'TWSE source status: ' + str(official_source_status)}
    if official_bar is not None:
        if local_bar is None:
            return {'classification': 'vendor_bar_missing_or_stale', 'reason': 'TWSE exact-date bar exists but local vendor bar is absent'}
        if str(local_bar.get('date', '')) != str(official_bar.get('date', '')):
            return {'classification': 'vendor_bar_missing_or_stale', 'reason': 'local and official bar dates differ'}
        try:
            complete = all(local_bar.get(k) is not None and float(local_bar[k]) > 0 for k in ('open', 'high', 'low', 'close'))
        except (TypeError, ValueError):
            complete = False
        if not complete:
            return {'classification': 'vendor_bar_incomplete', 'reason': 'local exact-date OHLC has missing or non-positive values'}
        return {'classification': 'official_and_vendor_bar_present', 'reason': 'both exact-date bars exist; price reconciliation remains separate'}
    if exchange_suspended:
        return {'classification': 'confirmed_suspension', 'reason': 'suspension explicitly confirmed by an authoritative notice'}
    if exchange_open and local_bar is not None:
        try:
            volume = float(local_bar.get('volume'))
        except (TypeError, ValueError):
            volume = None
        if volume == 0:
            return {'classification': 'zero_volume_no_trade', 'reason': 'exchange open and record explicitly reports zero volume'}
    return {'classification': 'unknown_no_official_bar', 'reason': 'no official bar and no authoritative suspension/no-trade evidence'}

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
            target_classification = None
            if target_date:
                target_classification = classify_market_data_status(
                    official_bar=target_bar,
                    local_bar=target,
                    official_source_status="ok",
                    exchange_suspended=bool(target.get("exchange_suspended", False)),
                    exchange_open=bool(target.get("exchange_open", False)),
                )
                print(f"🧭 行情狀態分類 {ticker} {target_date}: {target_classification['classification']} ({target_classification['reason']})")
            results[ticker] = {
                "status": "ok",
                "latest": latest,
                "expected": expected_bar,
                "target": target_bar,
                "target_local": target,
                "target_classification": target_classification,
                "unavailable_months": statuses,
            }
        except Exception as exc:
            print(f"⚠️ TWSE 官方行情查核 {ticker} 失敗：{type(exc).__name__}: {exc}")
            results[ticker] = {"status": "error", "message": str(exc)}
    return results
