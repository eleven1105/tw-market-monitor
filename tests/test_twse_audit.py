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


if __name__ == "__main__":
    unittest.main()
