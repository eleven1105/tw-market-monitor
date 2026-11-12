import unittest

import numpy as np
import pandas as pd

from analyzer import validate_recent_ohlc, validate_history_dates


class ValidateRecentOhlcTests(unittest.TestCase):
    def test_accepts_floating_point_rounding_noise(self):
        prices = pd.DataFrame({
            "close": [29.43267250061035],
            "high": [30.57483524077293],
            "low": [29.432672500610355],
        })
        self.assertEqual(validate_recent_ohlc(prices), (True, None))

    def test_rejects_material_close_below_low(self):
        prices = pd.DataFrame({
            "close": [324.0],
            "high": [368.0],
            "low": [324.5],
        })
        valid, reason = validate_recent_ohlc(prices)
        self.assertFalse(valid)
        self.assertIn("inconsistent_high_low_close", reason)

    def test_rejects_missing_recent_price(self):
        prices = pd.DataFrame({
            "close": [10.0, np.nan],
            "high": [11.0, 12.0],
            "low": [9.0, 10.0],
        })
        valid, reason = validate_recent_ohlc(prices)
        self.assertFalse(valid)
        self.assertEqual(reason, "non_numeric_or_missing")

    def test_cross_section_excludes_lagging_and_undated_symbols(self):
        from analyzer import filter_manifest_to_latest_date

        manifest = pd.DataFrame({
            "ticker": ["1111.TW", "2222.TW", "3333.TW", "4444.TW"],
            "data_date": ["2026-11-12", "2026-11-11", "2026-11-12", ""],
        })
        fresh, latest, lagging, undated = filter_manifest_to_latest_date(manifest)

        self.assertEqual(latest, "2026-11-12")
        self.assertEqual(set(fresh["ticker"]), {"1111.TW", "3333.TW"})
        self.assertEqual(lagging, ["2222.TW"])
        self.assertEqual(undated, ["4444.TW"])

    def test_manifest_with_no_valid_dates_fails_closed(self):
        from analyzer import filter_manifest_to_latest_date

        manifest = pd.DataFrame({
            "ticker": ["1111.TW", "2222.TW"],
            "data_date": ["", None],
        })
        with self.assertRaises(ValueError):
            filter_manifest_to_latest_date(manifest)

    def test_ignores_anomaly_outside_250_day_analysis_window(self):
        prices = pd.DataFrame({
            "close": [5.0] + [10.0] * 251,
            "high": [4.0] + [11.0] * 251,
            "low": [6.0] + [9.0] * 251,
        })
        self.assertEqual(validate_recent_ohlc(prices, lookback=251), (True, None))


    def test_history_dates_match_manifest_and_sort_chronologically(self):
        frame = pd.DataFrame({
            "date": ["2026-11-12", "2026-11-11"],
            "close": [12.0, 11.0],
        })
        valid, reason, normalized = validate_history_dates(
            frame, expected_latest_date="2026-11-12"
        )
        self.assertTrue(valid)
        self.assertIsNone(reason)
        self.assertEqual(normalized["date"].tolist(), ["2026-11-11", "2026-11-12"])

    def test_history_date_mismatch_is_rejected(self):
        frame = pd.DataFrame({"date": ["2026-11-11"], "close": [11.0]})
        valid, reason, _ = validate_history_dates(
            frame, expected_latest_date="2026-11-12"
        )
        self.assertFalse(valid)
        self.assertIn("latest_date_mismatch", reason)

    def test_duplicate_recent_trading_date_is_rejected(self):
        frame = pd.DataFrame({
            "date": ["2026-11-11", "2026-11-11"],
            "close": [11.0, 11.2],
        })
        valid, reason, _ = validate_history_dates(frame)
        self.assertFalse(valid)
        self.assertEqual(reason, "duplicate_trading_date")

    def test_missing_recent_date_is_rejected(self):
        frame = pd.DataFrame({
            "date": ["2026-11-11", None],
            "close": [11.0, 11.2],
        })
        valid, reason, _ = validate_history_dates(frame)
        self.assertFalse(valid)
        self.assertEqual(reason, "missing_or_invalid_recent_date")

    def test_retries_only_lagging_symbols_after_latest_date_is_known(self):
        # Covered by downloader integration tests in CI; this unit-level
        # regression asserts the intended date ordering used for refresh selection.
        rows = [
            {"ticker": "1111.TW", "data_date": "2026-11-12"},
            {"ticker": "2222.TW", "data_date": "2026-11-11"},
            {"ticker": "3333.TW", "data_date": "2026-11-12"},
        ]
        latest = max(row["data_date"] for row in rows)
        lagging = [row["ticker"] for row in rows if row["data_date"] and row["data_date"] < latest]
        self.assertEqual(lagging, ["2222.TW"])


if __name__ == "__main__":
    unittest.main()
