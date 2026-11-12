"""Build a point-in-time daily price/chip research panel for the pilot cohort.

Features on date t use only rows dated <= t. Forward returns are outcomes only;
they must never be fed into feature construction or model fitting as predictors.
The cohort is the current top-30 shortlist and is exploratory, not market-wide.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
PRICE_DIR = ROOT / "data" / "tw-share" / "dayK"
CHIP_DIR = ROOT / "data" / "tw-share" / "chip_cache"
OUTPUT_DIR = ROOT / "output"
CANDIDATES = OUTPUT_DIR / "wave_candidates.csv"
INSTITUTIONAL = "TaiwanStockInstitutionalInvestorsBuySell"
MARGIN = "TaiwanStockMarginPurchaseShortSale"
HORIZONS = (1, 3, 5, 10, 20)


def _load_json_rows(path):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return payload.get("data", []) if isinstance(payload, dict) else []
    except (OSError, ValueError):
        return []


def _price_file(ticker, price_dir):
    price_dir = Path(price_dir)
    # Price CSV names follow the ticker stored by the downloader. Support both
    # Yahoo-style suffixes (2330.TW_) and numeric-only prefixes (2330_).
    candidates = [str(ticker)]
    normalized = str(ticker).upper().strip()
    if normalized.endswith(".TW") or normalized.endswith(".TWO"):
        candidates.append(normalized.rsplit(".", 1)[0])
    matches = []
    for candidate in candidates:
        matches.extend(price_dir.glob(f"{candidate}_*.csv"))
    # Deduplicate paths while preserving deterministic order.
    unique = sorted({path.resolve() for path in matches})
    return Path(unique[0]) if unique else None


def _investor_bucket(value):
    name = str(value).strip().lower()
    if "foreign" in name or "外資" in name:
        return "foreign"
    if "investment" in name or "trust" in name or "投信" in name:
        return "trust"
    if "dealer" in name or "自營" in name:
        return "dealer"
    return None


def build_symbol_panel(ticker, name, price_dir=PRICE_DIR, chip_dir=CHIP_DIR):
    price_path = _price_file(ticker, price_dir)
    if price_path is None:
        raise FileNotFoundError(f"price CSV missing for {ticker}")
    price = pd.read_csv(price_path)
    price.columns = [str(c).strip().lower() for c in price.columns]
    date_col = next((c for c in ("date", "datetime") if c in price.columns), None)
    if date_col is None or "close" not in price.columns:
        raise ValueError(f"price CSV for {ticker} needs date and close")
    price["date"] = pd.to_datetime(price[date_col], errors="coerce").dt.normalize()
    price["close"] = pd.to_numeric(price["close"], errors="coerce")
    price = price.dropna(subset=["date", "close"]).query("close > 0")
    price = price.sort_values("date").drop_duplicates("date", keep="last")
    price = price[["date", "close"]].copy()
    price["ticker"] = ticker
    price["name"] = name

    inst_path = Path(chip_dir) / f"{INSTITUTIONAL}_{ticker}.json"
    margin_path = Path(chip_dir) / f"{MARGIN}_{ticker}.json"
    inst = pd.DataFrame(_load_json_rows(inst_path))
    margin = pd.DataFrame(_load_json_rows(margin_path))

    if not inst.empty and {"date", "buy", "sell"}.issubset(inst.columns):
        inst["date"] = pd.to_datetime(inst["date"], errors="coerce").dt.normalize()
        inst["buy"] = pd.to_numeric(inst["buy"], errors="coerce")
        inst["sell"] = pd.to_numeric(inst["sell"], errors="coerce")
        inst = inst.dropna(subset=["date", "buy", "sell"])
        inst["net"] = inst["buy"] - inst["sell"]
        if "name" in inst.columns:
            inst["investor"] = inst["name"].map(_investor_bucket)
        else:
            inst["investor"] = None
        daily = inst.groupby("date")["net"].sum().rename("institutional_net_daily").to_frame()
        for bucket in ("foreign", "trust", "dealer"):
            part = inst[inst["investor"] == bucket].groupby("date")["net"].sum()
            daily[f"{bucket}_net_daily"] = part
        daily = daily.sort_index()
        daily["institutional_net_5d"] = daily["institutional_net_daily"].rolling(5, min_periods=5).sum()
        daily["institutional_net_20d"] = daily["institutional_net_daily"].rolling(20, min_periods=20).sum()
        for bucket in ("foreign", "trust", "dealer"):
            col = f"{bucket}_net_daily"
            daily[col] = daily[col].fillna(0)
            daily[f"{bucket}_net_5d"] = daily[col].rolling(5, min_periods=5).sum()
            daily[f"{bucket}_net_20d"] = daily[col].rolling(20, min_periods=20).sum()
        directions = pd.concat(
            [(daily[f"{b}_net_5d"] > 0).astype("Int64") for b in ("foreign", "trust", "dealer")],
            axis=1,
        )
        daily["institutional_alignment_5d"] = directions.sum(axis=1, min_count=1)
        price = price.merge(daily.reset_index(), on="date", how="left")
    else:
        for col in ("institutional_net_daily", "institutional_net_5d", "institutional_net_20d",
                    "foreign_net_daily", "foreign_net_5d", "foreign_net_20d",
                    "trust_net_daily", "trust_net_5d", "trust_net_20d",
                    "dealer_net_daily", "dealer_net_5d", "dealer_net_20d",
                    "institutional_alignment_5d"):
            price[col] = pd.NA

    if not margin.empty and {"date", "MarginPurchaseTodayBalance"}.issubset(margin.columns):
        margin["date"] = pd.to_datetime(margin["date"], errors="coerce").dt.normalize()
        margin["margin_balance"] = pd.to_numeric(margin["MarginPurchaseTodayBalance"], errors="coerce")
        margin = margin.dropna(subset=["date", "margin_balance"]).sort_values("date")
        margin = margin.groupby("date")["margin_balance"].last().to_frame()
        margin["margin_balance_change_5d"] = margin["margin_balance"].diff(5)
        margin["margin_balance_change_20d"] = margin["margin_balance"].diff(20)
        price = price.merge(margin.reset_index(), on="date", how="left")
    else:
        for col in ("margin_balance", "margin_balance_change_5d", "margin_balance_change_20d"):
            price[col] = pd.NA

    price = price.sort_values("date").reset_index(drop=True)
    price["price_return_20d"] = price["close"].pct_change(20)
    price["ma20_extension"] = price["close"] / price["close"].rolling(20, min_periods=20).mean() - 1
    for horizon in HORIZONS:
        price[f"forward_return_{horizon}d"] = price["close"].shift(-horizon) / price["close"] - 1
    return price


def build_panel(candidates_path=CANDIDATES, price_dir=PRICE_DIR, chip_dir=CHIP_DIR):
    candidates = pd.read_csv(candidates_path, dtype={"ticker": str})
    frames = []
    errors = []
    for row in candidates.to_dict("records"):
        try:
            frames.append(build_symbol_panel(row["ticker"], row.get("name", row["ticker"]), price_dir, chip_dir))
        except Exception as exc:
            errors.append({"ticker": row["ticker"], "error": f"{type(exc).__name__}: {exc}"})
    if errors:
        print("POINT_IN_TIME_PANEL_SYMBOL_ERRORS=" + json.dumps(errors, ensure_ascii=False))
    if not frames:
        raise RuntimeError("no symbol panels could be built; see POINT_IN_TIME_PANEL_SYMBOL_ERRORS above")
    panel = pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "point_in_time_chip_backtest_panel.csv"
    panel.to_csv(out, index=False, encoding="utf-8-sig")
    summary = {
        "cohort": "current daily top-30 candidates; exploratory and selection-biased",
        "symbols_requested": len(candidates),
        "symbols_built": len(frames),
        "symbols_failed": errors,
        "panel_rows": len(panel),
        "date_start": panel["date"].min().date().isoformat(),
        "date_end": panel["date"].max().date().isoformat(),
        "rows_with_institutional_5d": int(panel["institutional_net_5d"].notna().sum()),
        "rows_with_margin_5d": int(panel["margin_balance_change_5d"].notna().sum()),
        "forward_return_columns": [f"forward_return_{h}d" for h in HORIZONS],
        "feature_timing": "features use same-day close data only; forward returns are outcome labels",
        "panel_csv": str(out),
    }
    (OUTPUT_DIR / "point_in_time_chip_backtest_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("POINT_IN_TIME_PANEL=" + json.dumps(summary, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    build_panel()
