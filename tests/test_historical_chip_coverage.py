import json
import tempfile
import unittest
from pathlib import Path

from historical_chip_coverage import build_coverage_report, DATASETS


class HistoricalChipCoverageTests(unittest.TestCase):
    def test_reports_actual_price_and_chip_date_spans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prices = root / "prices"
            chips = root / "chips"
            prices.mkdir()
            chips.mkdir()
            (prices / "2330.TW_TSMC.csv").write_text(
                "Date,Close\n2026-01-02,100\n2026-01-05,101\n", encoding="utf-8"
            )
            for dataset in DATASETS:
                rows = [
                    {"date": "2026-01-02", "stock_id": "2330"},
                    {"date": "2026-01-05", "stock_id": "2330"},
                ]
                (chips / f"{dataset}_2330.TW.json").write_text(
                    json.dumps({"data": rows}), encoding="utf-8"
                )
            summary = build_coverage_report(prices, chips)
            self.assertEqual(summary["tickers_audited"], 1)
            self.assertEqual(summary["both_chip_datasets_symbols"], 1)
            self.assertEqual(summary["chip_start_dates"], ["2026-01-02"])
            self.assertEqual(summary["chip_end_dates"], ["2026-01-05"])


if __name__ == "__main__":
    unittest.main()
