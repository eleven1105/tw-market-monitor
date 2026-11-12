import unittest
import pandas as pd

from nonoverlap_robustness import nonoverlap_sample


class NonOverlapRobustnessTests(unittest.TestCase):
    def test_samples_one_row_per_horizon_per_ticker_and_offset(self):
        frame = pd.DataFrame({
            "ticker": ["2330.TW"] * 45 + ["2317.TW"] * 45,
            "date": list(pd.date_range("2026-01-01", periods=45, freq="B")) * 2,
            "forward_return_20d": [0.01] * 90,
        })
        mask = pd.Series([True] * len(frame))
        sample = nonoverlap_sample(frame, mask, horizon=20, offset=3)
        self.assertEqual(len(sample), 6)
        self.assertEqual(sample.groupby("ticker").size().to_dict(), {"2317.TW": 3, "2330.TW": 3})


if __name__ == "__main__":
    unittest.main()
