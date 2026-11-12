import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from point_in_time_chip_panel import build_symbol_panel, INSTITUTIONAL, MARGIN


class PointInTimePanelTests(unittest.TestCase):
    def test_features_and_forward_returns_are_date_aligned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prices = root / "prices"; chips = root / "chips"
            prices.mkdir(); chips.mkdir()
            pd.DataFrame({
                "Date": pd.date_range("2026-01-01", periods=25, freq="B", tz="Asia/Taipei"),
                "Close": list(range(100, 125)),
            }).to_csv(prices / "2330_test.csv", index=False)
            dates = pd.date_range("2026-01-01", periods=25, freq="B")
            inst = []
            for d in dates:
                for label in ("Foreign_Investor", "Investment_Trust", "Dealer_self"):
                    inst.append({"date": d.date().isoformat(), "stock_id": "2330",
                                 "name": label, "buy": 100, "sell": 50})
            margin = [{"date": d.date().isoformat(), "stock_id": "2330",
                       "MarginPurchaseTodayBalance": 1000 + i}
                      for i, d in enumerate(dates)]
            (chips / f"{INSTITUTIONAL}_2330.TW.json").write_text(
                json.dumps({"data": inst}), encoding="utf-8")
            (chips / f"{MARGIN}_2330.TW.json").write_text(
                json.dumps({"data": margin}), encoding="utf-8")
            panel = build_symbol_panel("2330.TW", "test", prices, chips)
            self.assertEqual(len(panel), 25)
            self.assertAlmostEqual(panel.loc[20, "institutional_net_5d"], 750)
            self.assertTrue(pd.isna(panel.loc[3, "institutional_alignment_5d"]))
            self.assertEqual(panel.loc[4, "institutional_alignment_5d"], 3)
            self.assertAlmostEqual(panel.loc[20, "margin_balance_change_5d"], 5)
            self.assertAlmostEqual(panel.loc[0, "forward_return_1d"], 0.01)
            self.assertTrue(pd.isna(panel.loc[24, "forward_return_1d"]))

    def test_missing_chip_cache_does_not_drop_price_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prices = root / "prices"; chips = root / "chips"
            prices.mkdir(); chips.mkdir()
            pd.DataFrame({"Date": pd.date_range("2026-01-01", periods=3, freq="B"),
                          "Close": [10, 11, 12]}).to_csv(prices / "2317.TW_test.csv", index=False)
            panel = build_symbol_panel("2317.TW", "test", prices, chips)
            self.assertEqual(len(panel), 3)
            self.assertTrue(panel["institutional_net_5d"].isna().all())

    def test_missing_chip_session_does_not_shorten_rolling_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prices = root / "prices"; chips = root / "chips"
            prices.mkdir(); chips.mkdir()
            dates = pd.date_range("2026-01-01", periods=13, freq="B", tz="Asia/Taipei")
            pd.DataFrame({"Date": dates, "Close": list(range(100, 113))}).to_csv(
                prices / "2330_test.csv", index=False
            )
            inst = []
            margin = []
            for i, d in enumerate(dates):
                if i == 6:
                    continue  # Simulate a missing institutional/margin trading date.
                for label in ("Foreign_Investor", "Investment_Trust", "Dealer_self"):
                    inst.append({"date": d.date().isoformat(), "stock_id": "2330",
                                 "name": label, "buy": 100, "sell": 50})
                margin.append({"date": d.date().isoformat(), "stock_id": "2330",
                               "MarginPurchaseTodayBalance": 1000 + i})
            (chips / f"{INSTITUTIONAL}_2330.TW.json").write_text(
                json.dumps({"data": inst}), encoding="utf-8")
            (chips / f"{MARGIN}_2330.TW.json").write_text(
                json.dumps({"data": margin}), encoding="utf-8")
            panel = build_symbol_panel("2330.TW", "test", prices, chips)
            # At session 8, the five-session window includes missing session 7.
            self.assertTrue(pd.isna(panel.loc[7, "institutional_net_5d"]))
            self.assertTrue(pd.isna(panel.loc[7, "margin_balance_change_5d"]))
            # Once five consecutive observed sessions are available again, value returns.
            self.assertTrue(pd.notna(panel.loc[11, "institutional_net_5d"]))
            self.assertTrue(pd.notna(panel.loc[12, "margin_balance_change_5d"]))


if __name__ == "__main__":
    unittest.main()
