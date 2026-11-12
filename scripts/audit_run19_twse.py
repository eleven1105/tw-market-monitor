# -*- coding: utf-8 -*-
"""One-off read-only audit of the exact Taiwan market-data anomalies from Run #19."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from twse_audit import audit_twse_symbols

EXPECTED_DATE = "2026-11-12"

TARGET_BARS = {
    "1310.TW": {
        "date": EXPECTED_DATE,
        "high": 8.229999542236328,
        "low": 8.029999732971191,
        "close": 8.010000228881836,
    },
    "1808.TW": {
        "date": EXPECTED_DATE,
        "high": None,
        "low": None,
        "close": None,
    },
    "5284.TW": {
        "date": EXPECTED_DATE,
        "high": 242.5,
        "low": 226.0,
        "close": 224.0,
    },
    "6698.TW": {
        "date": EXPECTED_DATE,
        "high": 31.649999618530277,
        "low": 30.100000381469727,
        "close": 30.049999237060547,
    },
    "6933.TW": {
        "date": EXPECTED_DATE,
        "high": 368.0,
        "low": 324.5,
        "close": 324.0,
    },
}

LAGGING_TICKERS = ["1538.TW", "1589.TW", "3714.TW", "5906.TW"]


if __name__ == "__main__":
    print("=== Run #19 exact-date official TWSE audit ===")
    print("Yahoo OHLC is compared with raw TWSE daily bars; no local data is modified.")
    print("\n--- Five OHLC-rejected symbols ---")
    audit_twse_symbols(
        TARGET_BARS.keys(),
        expected_date=EXPECTED_DATE,
        target_bars=TARGET_BARS,
    )
    print("\n--- Four lagging-date symbols ---")
    audit_twse_symbols(LAGGING_TICKERS, expected_date=EXPECTED_DATE)
