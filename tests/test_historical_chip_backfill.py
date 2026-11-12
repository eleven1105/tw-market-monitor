import tempfile
import unittest
from pathlib import Path

from historical_chip_backfill import backfill, DATASETS


class HistoricalChipBackfillTests(unittest.TestCase):
    def test_requests_two_year_window_and_writes_each_dataset(self):
        class Response:
            def raise_for_status(self): pass
            def json(self):
                return {"status": 200, "data": [
                    {"date": "2024-11-12", "stock_id": "2330", "buy": 100, "sell": 50}
                ]}
        class Session:
            headers = {}
            def __init__(self): self.params = []
            def get(self, url, params, timeout):
                self.params.append(params)
                return Response()
        with tempfile.TemporaryDirectory() as tmp:
            session = Session()
            result = backfill(
                [{"ticker": "2330.TW", "market_date": "2026-11-12"}],
                "test-token", cache_dir=Path(tmp), session=session, sleep_seconds=0
            )
            self.assertEqual(len(session.params), 2)
            self.assertEqual(session.params[0]["start_date"], "2024-11-12")
            self.assertEqual(session.params[0]["end_date"], "2026-11-12")
            self.assertEqual([r["status"] for r in result], ["fetched", "fetched"])
            for dataset in DATASETS:
                self.assertTrue((Path(tmp) / f"{dataset}_2330.TW.json").exists())

    def test_empty_response_does_not_create_false_cache(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"status": 200, "data": []}
        class Session:
            headers = {}
            def get(self, *args, **kwargs): return Response()
        with tempfile.TemporaryDirectory() as tmp:
            result = backfill(
                [{"ticker": "2330.TW", "market_date": "2026-11-12"}],
                "test-token", cache_dir=Path(tmp), session=Session(), sleep_seconds=0
            )
            self.assertTrue(all(r["status"] == "empty" for r in result))
            self.assertEqual(list(Path(tmp).glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
