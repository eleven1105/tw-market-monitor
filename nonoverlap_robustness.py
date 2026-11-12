"""Sensitivity check using non-overlapping 20-session outcome samples.

For each ticker, select one of 20 possible calendar offsets and then take every
20th trading session. Outcomes within a given offset do not overlap per ticker.
Offsets are sensitivity views of the same panel, not 20 independent experiments.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from signal_baseline_analysis import _group_specs

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "output" / "point_in_time_chip_backtest_panel.csv"
OUTPUT = ROOT / "output"
HORIZON = 20


def nonoverlap_sample(frame, mask, horizon=HORIZON, offset=0):
    pieces = []
    work = frame.copy()
    work["_signal"] = mask.fillna(False).to_numpy()
    for _, ticker_frame in work.groupby("ticker", sort=True):
        ticker_frame = ticker_frame.sort_values("date").reset_index(drop=True)
        selected = ticker_frame.index % horizon == offset
        selected &= ticker_frame["_signal"]
        pieces.append(ticker_frame.loc[selected, ["ticker", "forward_return_20d"]])
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(
        columns=["ticker", "forward_return_20d"]
    )


def _stats(sample):
    values = pd.to_numeric(sample["forward_return_20d"], errors="coerce").dropna()
    if values.empty:
        return {"n": 0, "unique_tickers": 0, "win_rate": None, "mean_return": None,
                "median_return": None}
    return {
        "n": int(len(values)),
        "unique_tickers": int(sample.loc[values.index, "ticker"].nunique()),
        "win_rate": float((values > 0).mean()),
        "mean_return": float(values.mean()),
        "median_return": float(values.median()),
    }


def build_nonoverlap_report(panel_path=INPUT):
    frame = pd.read_csv(panel_path)
    frame["date"] = pd.to_datetime(frame["date"])
    detail = []
    for signal, group, mask in _group_specs(frame):
        for offset in range(HORIZON):
            sample = nonoverlap_sample(frame, mask, HORIZON, offset)
            detail.append({
                "signal": signal, "group": group, "horizon_sessions": HORIZON,
                "offset": offset, **_stats(sample),
            })
    detail_frame = pd.DataFrame(detail)
    summaries = []
    for (signal, group), part in detail_frame.groupby(["signal", "group"], sort=False):
        valid = part.dropna(subset=["mean_return", "win_rate"])
        summaries.append({
            "signal": signal, "group": group, "horizon_sessions": HORIZON,
            "offsets_tested": int(len(valid)),
            "mean_return_across_offsets": float(valid["mean_return"].mean()) if len(valid) else None,
            "mean_return_min_offset": float(valid["mean_return"].min()) if len(valid) else None,
            "mean_return_max_offset": float(valid["mean_return"].max()) if len(valid) else None,
            "win_rate_across_offsets": float(valid["win_rate"].mean()) if len(valid) else None,
            "win_rate_min_offset": float(valid["win_rate"].min()) if len(valid) else None,
            "win_rate_max_offset": float(valid["win_rate"].max()) if len(valid) else None,
            "min_unique_tickers": int(valid["unique_tickers"].min()) if len(valid) else 0,
        })
    summary_frame = pd.DataFrame(summaries)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    detail_path = OUTPUT / "nonoverlap_20d_offset_statistics.csv"
    summary_path = OUTPUT / "nonoverlap_20d_robustness_summary.csv"
    detail_frame.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary_frame.to_csv(summary_path, index=False, encoding="utf-8-sig")
    metadata = {
        "purpose": "20-session non-overlapping outcome sensitivity across 20 possible start offsets",
        "symbols": int(frame["ticker"].nunique()),
        "rows": int(len(frame)),
        "horizon_sessions": HORIZON,
        "offsets": HORIZON,
        "transaction_costs_included": False,
        "selection_bias_warning": "current top-30 shortlist; not a historical point-in-time universe",
        "interpretation_warning": "offsets overlap across sensitivity views and are not independent replications",
        "detail_csv": str(detail_path),
        "summary_csv": str(summary_path),
    }
    (OUTPUT / "nonoverlap_20d_robustness_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("NONOVERLAP_ROBUSTNESS=" + json.dumps(metadata, ensure_ascii=False))
    return detail_frame, summary_frame, metadata


if __name__ == "__main__":
    build_nonoverlap_report()
