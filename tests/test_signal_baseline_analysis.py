import unittest
import pandas as pd

from signal_baseline_analysis import summarize_returns


class SignalBaselineAnalysisTests(unittest.TestCase):
    def test_summarize_returns(self):
        stats = summarize_returns(pd.Series([0.10, -0.05, 0.02, None]))
        self.assertEqual(stats["n"], 3)
        self.assertAlmostEqual(stats["win_rate"], 2 / 3)
        self.assertAlmostEqual(stats["mean_return"], 0.07 / 3)

    def test_empty_returns(self):
        stats = summarize_returns(pd.Series([None, float("nan")]))
        self.assertEqual(stats["n"], 0)
        self.assertIsNone(stats["mean_return"])


if __name__ == "__main__":
    unittest.main()
