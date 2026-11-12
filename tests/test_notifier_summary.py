import unittest

import pandas as pd

from notifier import build_taiwan_summary


class TaiwanSummaryTests(unittest.TestCase):
    def test_summary_labels_five_day_returns_not_daily_breadth(self):
        frame = pd.DataFrame({
            "Ticker": ["2330.TW", "2317.TW", "2454.TW"],
            "Week_Close": [5.0, -2.0, 0.0],
        })
        summary = build_taiwan_summary(
            frame, {"current_date": 3, "total": 3}, max_candidates=2
        )
        self.assertIn("近 5 交易日報酬概況（非單日漲跌家數）", summary)
        self.assertIn("上漲 1／下跌 1／持平 1", summary)
        self.assertIn("2330.TW：5.00%", summary)
        self.assertIn("5 日報酬不代表今日漲跌", summary)
        self.assertNotIn("今日上漲家數", summary)

    def test_summary_reports_one_day_breadth_separately(self):
        frame = pd.DataFrame({
            "Ticker": ["2330.TW", "2317.TW", "2454.TW", "2308.TW"],
            "Day_Close": [1.5, -0.5, 0.0, 2.0],
            "Week_Close": [3.0, -1.0, 0.0, 4.0],
        })
        summary = build_taiwan_summary(frame)
        self.assertIn("單日市場廣度（共同最新交易日）", summary)
        self.assertIn("上漲 2／下跌 1／持平 1（樣本 4 檔）", summary)
        self.assertIn("近 5 交易日報酬概況（非單日漲跌家數）", summary)

    def test_empty_frame_returns_explicit_warning(self):
        summary = build_taiwan_summary(pd.DataFrame())
        self.assertIn("分析樣本為空", summary)


if __name__ == "__main__":
    unittest.main()
