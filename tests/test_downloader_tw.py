import unittest

from downloader_tw import build_download_report, latest_observed_date, select_lagging_rows, should_replace_history


class SelectLaggingRowsTests(unittest.TestCase):
    def test_selects_only_rows_behind_latest_observed_date(self):
        rows = [
            {"ticker": "1111.TW", "data_date": "2026-11-12"},
            {"ticker": "2222.TW", "data_date": "2026-11-11"},
            {"ticker": "3333.TW", "data_date": "2026-11-12"},
        ]
        self.assertEqual(
            [row["ticker"] for row in select_lagging_rows(rows)],
            ["2222.TW"],
        )

    def test_ignores_undated_rows_without_crashing(self):
        rows = [
            {"ticker": "1111.TW", "data_date": ""},
            {"ticker": "2222.TW", "data_date": None},
        ]
        self.assertIsNone(latest_observed_date(rows))
        self.assertEqual(select_lagging_rows(rows), [])

    def test_does_not_replace_newer_cached_history_with_older_vendor_data(self):
        from datetime import date

        self.assertFalse(should_replace_history(date(2026, 11, 12), date(2026, 11, 11)))
        self.assertTrue(should_replace_history(date(2026, 11, 11), date(2026, 11, 12)))
        self.assertTrue(should_replace_history(None, date(2026, 11, 12)))
        self.assertFalse(should_replace_history(date(2026, 11, 12), None))

    def test_download_report_separates_available_from_current_date(self):
        stats = {"success": 2, "exists": 6, "stale": 0, "error": 0, "empty": 0, "stale_refresh": 2}
        rows = [
            {"ticker": "1111.TW", "data_date": "2026-11-12"},
            {"ticker": "2222.TW", "data_date": "2026-11-12"},
            {"ticker": "3333.TW", "data_date": "2026-11-11"},
        ]
        report = build_download_report(9, stats, rows)
        self.assertEqual(report["success"], 8)
        self.assertEqual(report["current_date"], 2)
        self.assertEqual(report["stale_date"], 1)
        self.assertEqual(report["latest_data_date"], "2026-11-12")

    def test_latest_observed_date_is_available_for_refresh_log(self):
        rows = [
            {"ticker": "1111.TW", "data_date": "2026-11-12"},
            {"ticker": "2222.TW", "data_date": "2026-11-11"},
        ]
        self.assertEqual(latest_observed_date(rows), "2026-11-12")


if __name__ == "__main__":
    unittest.main()
