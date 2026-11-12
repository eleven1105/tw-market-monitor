import unittest
from unittest.mock import Mock, patch
from datetime import date

from twse_audit import _parse_twse_date, _parse_price, fetch_official_month_bars


class TwseAuditTests(unittest.TestCase):
    def test_parses_roc_date(self):
        self.assertEqual(_parse_twse_date("115/11/12"), date(2026, 11, 12))

    def test_parses_iso_timestamp_with_timezone(self):
        self.assertEqual(
            _parse_twse_date("2026-11-12 00:00:00+08:00"),
            date(2026, 11, 12),
        )

    def test_parses_price_and_empty_markers(self):
        self.assertEqual(_parse_price("1,234.50"), 1234.5)
        self.assertIsNone(_parse_price("--"))

    @patch("twse_audit.requests.get")
    def test_fetches_and_normalizes_official_month_bar(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "stat": "OK",
            "fields": ["日期", "開盤價", "最高價", "最低價", "收盤價"],
            "data": [["115/11/12", "100.00", "105.00", "99.00", "103.00"]],
        }
        get.return_value = response

        result = fetch_official_month_bars("1538.TW", month_date=date(2026, 11, 12))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["bars"][0], {
            "date": "2026-11-12",
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 103.0,
        })
        self.assertEqual(get.call_args.kwargs["params"]["stockNo"], "1538")
        self.assertEqual(get.call_args.kwargs["params"]["date"], "20261101")

    def test_reconciles_low_only_when_high_and_close_match_official(self):
        from twse_audit import reconcile_official_low

        official = {"high": 242.5, "low": 224.0, "close": 224.0}
        self.assertEqual(
            reconcile_official_low(242.5, 226.0, 224.0, official),
            224.0,
        )

    def test_does_not_reconcile_when_high_or_close_differs(self):
        from twse_audit import reconcile_official_low

        official = {"high": 242.5, "low": 224.0, "close": 224.0}
        self.assertIsNone(reconcile_official_low(241.0, 226.0, 224.0, official))
        self.assertIsNone(reconcile_official_low(242.5, 226.0, 223.0, official))

    @patch("twse_audit.fetch_official_month_bars")
    def test_audit_fetches_month_of_exact_flagged_bar(self, fetch_month):
        fetch_month.side_effect = [
            {"status": "ok", "bars": [
                {"date": "2026-10-15", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5}
            ]},
            {"status": "ok", "bars": [
                {"date": "2026-11-12", "open": 10.5, "high": 12.0, "low": 10.0, "close": 11.5}
            ]},
        ]
        from twse_audit import audit_twse_symbols

        from contextlib import redirect_stdout
        from io import StringIO

        output = StringIO()
        with redirect_stdout(output):
            result = audit_twse_symbols(
                ["1234.TW"],
                expected_date="2026-11-12",
                target_bars={"1234.TW": {
                    "date": "2026-10-15",
                    "open": 8.2,
                    "close": 8.0,
                    "high": 9.0,
                    "low": 8.5,
                }},
            )
        self.assertEqual(result["1234.TW"]["target"]["date"], "2026-10-15")
        self.assertIn("本機 Yahoo OHLC=8.2/9.0/8.5/8.0", output.getvalue())
        self.assertIn("TWSE 原始 OHLC=10.0/11.0/9.0/10.5", output.getvalue())
        self.assertEqual(fetch_month.call_count, 2)

    def test_classifies_vendor_lag_when_official_bar_exists_but_local_is_missing(self):
        from twse_audit import classify_market_data_status
        result = classify_market_data_status({'date': '2026-11-12'}, None)
        self.assertEqual(result['classification'], 'vendor_bar_missing_or_stale')

    def test_classifies_incomplete_local_ohlc_without_weakening_validation(self):
        from twse_audit import classify_market_data_status
        result = classify_market_data_status(
            {'date': '2026-11-12'},
            {'date': '2026-11-12', 'open': None, 'high': 10, 'low': 9, 'close': 9.5},
        )
        self.assertEqual(result['classification'], 'vendor_bar_incomplete')

    def test_missing_official_bar_is_unknown_without_exchange_evidence(self):
        from twse_audit import classify_market_data_status
        result = classify_market_data_status(None, {'date': '2026-11-12'})
        self.assertEqual(result['classification'], 'unknown_no_official_bar')

    def test_suspension_requires_explicit_exchange_confirmation(self):
        from twse_audit import classify_market_data_status
        result = classify_market_data_status(None, exchange_suspended=True)
        self.assertEqual(result['classification'], 'confirmed_suspension')

    def test_zero_volume_requires_confirmed_open_session(self):
        from twse_audit import classify_market_data_status
        local = {'date': '2026-11-12', 'volume': 0}
        unknown = classify_market_data_status(None, local)
        no_trade = classify_market_data_status(None, local, exchange_open=True)
        self.assertEqual(unknown['classification'], 'unknown_no_official_bar')
        self.assertEqual(no_trade['classification'], 'zero_volume_no_trade')

if __name__ == "__main__":
    unittest.main()
