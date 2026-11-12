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


if __name__ == "__main__":
    unittest.main()
