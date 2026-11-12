import tempfile
import unittest
from pathlib import Path

import pandas as pd

from candidate_chip_pipeline import (
    score_price_history, fetch_chip_data, DATASETS, normalize_finmind_ticker
)


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

    def test_normalizes_yahoo_tickers_for_finmind(self):
        self.assertEqual(normalize_finmind_ticker("2330.TW"), "2330")
        self.assertEqual(normalize_finmind_ticker("6488.TWO"), "6488")
        self.assertEqual(normalize_finmind_ticker("2330"), "2330")
        with self.assertRaises(ValueError):
            normalize_finmind_ticker("BAD/TICKER")

    def test_api_receives_numeric_ticker_not_yahoo_suffix(self):
        class FakeResponse:
            def raise_for_status(self):
                pass
            def json(self):
                return {"status": 200, "data": [
                    {"date": "2026-11-12", "stock_id": "2330", "buy": 10, "sell": 5}
                ]}
        class FakeSession:
            headers = {}
            def __init__(self):
                self.params = []
            def get(self, url, params, timeout):
                self.params.append(params)
                return FakeResponse()
        with tempfile.TemporaryDirectory() as tmp:
            session = FakeSession()
            candidate = [{"ticker": "2330.TW", "market_date": "2026-11-12"}]
            result = fetch_chip_data(candidate, "fake-token", cache_dir=Path(tmp),
                                     session=session, sleep_seconds=0)
            self.assertEqual(result[0]["status"], "fetched")
            self.assertEqual(session.params[0]["data_id"], "2330")
            self.assertEqual(len(session.params), len(DATASETS))

    def test_uses_cache_without_network_calls(self):
        class NoNetwork:
            headers = {}
            def get(self, *args, **kwargs):
                raise AssertionError("cache hit should not call network")
        with tempfile.TemporaryDirectory() as tmp:
            candidates = [{"ticker": "2330.TW", "market_date": "2026-11-12"}]
            for dataset in DATASETS:
                path = Path(tmp) / f"{dataset}_2330.TW.json"
                path.write_text('{"data":[{"date":"2026-11-12","stock_id":"2330"}]}',
                                encoding="utf-8")
            result = fetch_chip_data(candidates, "fake-token", cache_dir=Path(tmp),
                                     session=NoNetwork(), sleep_seconds=0)
            self.assertEqual([item["status"] for item in result], ["cache", "cache"])


if __name__ == "__main__":
    unittest.main()
