import tempfile
import unittest
from pathlib import Path

import pandas as pd

from candidate_chip_pipeline import score_price_history, fetch_chip_data, DATASETS


class CandidateChipPipelineTests(unittest.TestCase):
    def test_score_returns_expected_diagnostics(self):
        close = [100 + i for i in range(80)]
        frame = pd.DataFrame({
            "close": close,
            "high": [value + 1 for value in close],
            "low": [value - 1 for value in close],
            "volume": [100000] * 80,
        })
        result = score_price_history(frame)
        self.assertGreater(result["score"], 50)
        self.assertIn("avg_turnover_20d", result)
        self.assertGreater(result["return_20d_pct"], 0)

    def test_rejects_insufficient_history(self):
        frame = pd.DataFrame({"close": [10] * 10, "high": [11] * 10,
                              "low": [9] * 10, "volume": [1000] * 10})
        with self.assertRaises(ValueError):
            score_price_history(frame)

    def test_uses_cache_without_network_calls(self):
        class NoNetwork:
            headers = {}

            def get(self, *args, **kwargs):
                raise AssertionError("cache hit should not call network")
        with tempfile.TemporaryDirectory() as tmp:
            candidates = [{"ticker": "2330", "market_date": "2026-11-12"}]
            for dataset in DATASETS:
                path = Path(tmp) / f"{dataset}_2330.json"
                path.write_text('{"data":[{"date":"2026-11-12","stock_id":"2330"}]}',
                                encoding="utf-8")
            result = fetch_chip_data(candidates, "fake-token", cache_dir=Path(tmp),
                                     session=NoNetwork(), sleep_seconds=0)
            self.assertEqual([item["status"] for item in result], ["cache", "cache"])


if __name__ == "__main__":
    unittest.main()
