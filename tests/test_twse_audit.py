import unittest
from unittest.mock import Mock, patch
from datetime import date

from twse_audit import _parse_twse_date, _parse_price, fetch_official_month_bars


class TwseAuditTests(unittest.TestCase):
    def test_parses_roc_date(self):
        self.assertEqual(_parse_twse_date("115/11/12"), date(2026, 11, 12))

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

        result = audit_twse_symbols(
            ["1234.TW"],
            expected_date="2026-11-12",
            target_bars={"1234.TW": {"date": "2026-10-15", "close": 8.0, "high": 9.0, "low": 8.5}},
        )
        self.assertEqual(result["1234.TW"]["target"]["date"], "2026-10-15")
        self.assertEqual(fetch_month.call_count, 2)


if __name__ == "__main__":
    unittest.main()
