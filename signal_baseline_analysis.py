"""Descriptive baseline statistics for the current point-in-time pilot panel.

This is exploratory analysis only: overlapping forward returns, a current top-30
cohort, no transaction costs, and no market-wide or out-of-sample claim.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "output" / "point_in_time_chip_backtest_panel.csv"
OUTPUT = ROOT / "output"
HORIZONS = (1, 3, 5, 10, 20)


def _group_specs(frame):
    specs = []
    specs.append(("baseline", "all_valid", pd.Series(True, index=frame.index)))
    for value in (0, 1, 2, 3):
        specs.append(("institutional_alignment_5d", f"{value}_of_3",
                      frame["institutional_alignment_5d"] == value))
    specs.extend([
        ("institutional_net_5d", "positive", frame["institutional_net_5d"] > 0),
        ("institutional_net_5d", "negative", frame["institutional_net_5d"] < 0),
        ("institutional_net_5d", "zero", frame["institutional_net_5d"] == 0),
        ("price_return_20d", "positive", frame["price_return_20d"] > 0),
        ("price_return_20d", "negative_or_zero", frame["price_return_20d"] <= 0),
        ("margin_balance_change_5d", "rising", frame["margin_balance_change_5d"] > 0),
        ("margin_balance_change_5d", "falling_or_flat", frame["margin_balance_change_5d"] <= 0),
    ])
    momentum_up = frame["price_return_20d"] > 0
    inst_up = frame["institutional_net_5d"] > 0
    specs.extend([
        ("price_momentum_x_institutional_flow", "momentum_up__flow_up", momentum_up & inst_up),
        ("price_momentum_x_institutional_flow", "momentum_up__flow_down_or_flat",
         momentum_up & (frame["institutional_net_5d"] <= 0)),
        ("price_momentum_x_institutional_flow", "momentum_down_or_flat__flow_up",
         (frame["price_return_20d"] <= 0) & inst_up),
        ("price_momentum_x_institutional_flow", "momentum_down_or_flat__flow_down_or_flat",
         (frame["price_return_20d"] <= 0) & (frame["institutional_net_5d"] <= 0)),
    ])
    return specs


def summarize_returns(values):
    values = pd.to_numeric(values, errors="coerce").dropna()
    n = int(values.size)
    if n == 0:
        return {"n": 0, "win_rate": None, "mean_return": None,
                "median_return": None, "mean_ci95_low": None, "mean_ci95_high": None}
    mean = float(values.mean())
    se = float(values.std(ddof=1) / np.sqrt(n)) if n > 1 else None
    return {
        "n": n,
        "win_rate": float((values > 0).mean()),
        "mean_return": mean,
        "median_return": float(values.median()),
        "mean_ci95_low": mean - 1.96 * se if se is not None else None,
        "mean_ci95_high": mean + 1.96 * se if se is not None else None,
    }


def build_baseline_report(panel_path=INPUT):
    frame = pd.read_csv(panel_path)
    required = ["ticker", "date", "institutional_net_5d", "institutional_alignment_5d",
                "margin_balance_change_5d", "price_return_20d"]
    missing = [col for col in required if col not in frame.columns]
    if missing:
        raise ValueError(f"panel missing required columns: {missing}")

    records = []
    for signal, group, mask in _group_specs(frame):
        for horizon in HORIZONS:
            outcome = f"forward_return_{horizon}d"
            selected = frame.loc[mask.fillna(False), [outcome, "ticker"]].dropna(subset=[outcome])
            stats = summarize_returns(selected[outcome])
            records.append({
                "signal": signal, "group": group, "horizon_sessions": horizon,
                **stats,
                "unique_tickers": int(selected["ticker"].nunique()),
            })

    report = pd.DataFrame(records)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT / "signal_baseline_statistics.csv"
    json_path = OUTPUT / "signal_baseline_summary.json"
    report.to_csv(csv_path, index=False, encoding="utf-8-sig")

    summary = {
        "purpose": "descriptive baseline only; not a trading strategy or validated edge",
        "symbols": int(frame["ticker"].nunique()),
        "rows": int(len(frame)),
        "date_start": str(frame["date"].min()),
        "date_end": str(frame["date"].max()),
        "valid_alignment_rows": int(frame["institutional_alignment_5d"].notna().sum()),
        "valid_institutional_net_5d_rows": int(frame["institutional_net_5d"].notna().sum()),
        "valid_margin_change_5d_rows": int(frame["margin_balance_change_5d"].notna().sum()),
        "overlapping_outcomes": True,
        "transaction_costs_included": False,
        "selection_bias_warning": "current top-30 shortlist; not a historical point-in-time universe",
        "confidence_interval_warning": "naive row-level intervals; serial dependence and ticker clustering are not adjusted",
        "report_csv": str(csv_path),
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SIGNAL_BASELINE_SUMMARY=" + json.dumps(summary, ensure_ascii=False))
    return report, summary


if __name__ == "__main__":
    build_baseline_report()
