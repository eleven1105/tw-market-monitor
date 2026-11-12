import unittest

from downloader_tw import select_lagging_rows


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
        self.assertEqual(select_lagging_rows(rows), [])


if __name__ == "__main__":
    unittest.main()
