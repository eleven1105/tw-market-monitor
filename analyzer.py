# -*- coding: utf-8 -*-
import os
import numpy as np
import pandas as pd
import matplotlib

# Select a headless backend before importing pyplot (GitHub Actions safe).
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from tqdm import tqdm

# 字體設定 (支援中日韓字元，確保簡繁中、日、韓文顯示正常)
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK TC', 'Noto Sans CJK JP', 'Noto Sans CJK KR', 'Microsoft JhengHei', 'Arial Unicode MS', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# 基礎分箱設定
BIN_SIZE = 10.0
X_MIN, X_MAX = -100, 100
BINS = np.arange(X_MIN, X_MAX + 1, BIN_SIZE)

def get_market_url(market_id, ticker):
    """
    智慧連結引擎：根據市場別生成對應的技術線圖連結
    """
    m_id = market_id.lower()
    
    if m_id == "us-share":
        # 🇺🇸 美股連結：StockCharts
        return f"https://stockcharts.com/sc3/ui/?s={ticker}"
    
    elif m_id == "hk-share":
        # 🇭🇰 港股連結：AASTOCKS (補足5位數)
        clean_code = ticker.replace(".HK", "").strip().zfill(5)
        return f"https://www.aastocks.com/tc/stocks/quote/stocktrend.aspx?symbol={clean_code}"

    elif m_id == "cn-share":
        # 🇨🇳 中國 A 股連結：東方財富 (識別 sh/sz)
        prefix = "sh" if ticker.startswith('6') else "sz"
        return f"https://quote.eastmoney.com/{prefix}{ticker}.html"

    elif m_id == "jp-share":
        # 🇯🇵 日本連結：樂天證券 (Rakuten Securities)
        # 格式範例：7203.T
        clean_ticker = ticker if ".T" in ticker.upper() else f"{ticker.split('.')[0]}.T"
        return f"https://www.rakuten-sec.co.jp/web/market/search/quote.html?ric={clean_ticker}"

    elif m_id == "kr-share":
        # 🇰🇷 韓國連結：Naver Finance
        # 邏輯：Naver 僅接受純數字代碼，去除 .KS 或 .KQ
        clean_code = ticker.split('.')[0]
        return f"https://finance.naver.com/item/main.naver?code={clean_code}"

    else:
        # 🇹🇼 台股連結：玩股網
        clean_ticker = ticker.split('.')[0]
        return f"https://www.wantgoo.com/stock/{clean_ticker}/technical-chart"

def build_company_list(arr_pct, codes, names, bins, market_id):
    """
    產出 HTML 格式的分箱清單，支援動態超連結與飆股高亮
    """
    lines = [f"{'報酬區間':<12} | {'家數(比例)':<14} | 公司清單", "-"*80]
    total = len(arr_pct)
    
    def make_link(i):
        url = get_market_url(market_id, codes[i])
        return f'<a href="{url}" style="text-decoration:none; color:#0366d6;">{codes[i]}({names[i]})</a>'

    for lo in range(int(X_MIN), int(X_MAX), int(BIN_SIZE)):
        up = lo + 10
        lab = f"{lo}%~{up}%"
        mask = (arr_pct >= lo) & (arr_pct < up)
        cnt = int(mask.sum())
        if cnt == 0: continue
        
        picked_indices = np.where(mask)[0]
        links = [make_link(idx) for idx in picked_indices]
        lines.append(f"{lab:<12} | {cnt:>4} ({(cnt/total*100):5.1f}%) | {', '.join(links)}")

    # 處理 > 100% 的極端飆股
    extreme_mask = (arr_pct >= 100)
    e_cnt = int(extreme_mask.sum())
    if e_cnt > 0:
        e_picked = np.where(extreme_mask)[0]
        sorted_e = sorted(e_picked, key=lambda idx: arr_pct[idx], reverse=True)
        e_links = []
        for idx in sorted_e:
            url = get_market_url(market_id, codes[idx])
            e_links.append(f'<a href="{url}" style="text-decoration:none; color:red; font-weight:bold;">{codes[idx]}({names[idx]}:{arr_pct[idx]:.0f}%)</a>')
        
        lines.append(f"{' > 100%':<12} | {e_cnt:>4} ({(e_cnt/total*100):5.1f}%) | {', '.join(e_links)}")

    return "\n".join(lines)

def filter_manifest_to_latest_date(manifest):
    """Return one-date cross-sectional universe plus lagging/undated ticker lists."""
    normalized_dates = pd.to_datetime(
        manifest["data_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    valid_dates = normalized_dates.dropna().astype(str)
    if valid_dates.empty:
        raise ValueError("白名單沒有任何有效行情日期")
    # Pandas may retain mixed object values (date strings and NaN); compare
    # normalized strings only after removing missing values.
    latest_date = valid_dates.max()
    fresh_mask = normalized_dates.astype("string").eq(latest_date).fillna(False)
    fresh_manifest = manifest.loc[fresh_mask].copy()
    lagging = manifest.loc[
        normalized_dates.notna() & ~fresh_mask, "ticker"
    ].dropna().astype(str).tolist()
    undated = manifest.loc[
        normalized_dates.isna(), "ticker"
    ].dropna().astype(str).tolist()
    return fresh_manifest, latest_date, lagging, undated


def validate_recent_ohlc(prices, lookback=251, relative_tolerance=1e-8, absolute_tolerance=1e-8):
    """Validate OHLC relationships only in the observations used by 5/20/250-day metrics.

    Yahoo adjusted prices can differ by a few floating-point ulps. A scale-aware
    tolerance avoids rejecting valid bars for representation noise, while
    material violations (for example close below low) remain invalid.
    """
    recent = prices.tail(lookback)
    if recent.empty:
        return False, "empty_recent_window"

    values = recent[["close", "high", "low"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        return False, "non_numeric_or_missing"
    if (values <= 0).any():
        return False, "non_positive_price"

    close = recent["close"].to_numpy(dtype=float)
    high = recent["high"].to_numpy(dtype=float)
    low = recent["low"].to_numpy(dtype=float)
    tolerance = np.maximum.reduce([np.abs(close), np.abs(high), np.abs(low)])
    tolerance = tolerance * relative_tolerance + absolute_tolerance
    bad = (high + tolerance < low) | (high + tolerance < close) | (low - tolerance > close)
    if bad.any():
        idx = int(np.flatnonzero(bad)[0])
        return False, f"inconsistent_high_low_close; recent_row={idx}; high={high[idx]}; low={low[idx]}; close={close[idx]}"
    return True, None



def validate_history_dates(frame, expected_latest_date=None, lookback=251):
    """Validate dated price history and return a chronologically sorted copy."""
    date_column = next(
        (column for column in ("date", "datetime") if column in frame.columns),
        None,
    )
    if date_column is None:
        return False, "missing_date_column", frame

    parsed = pd.to_datetime(frame[date_column], errors="coerce")
    if parsed.tail(lookback).isna().any():
        return False, "missing_or_invalid_recent_date", frame

    valid = parsed.notna()
    if not valid.any():
        return False, "no_valid_trading_dates", frame
    if parsed.loc[valid].duplicated().any():
        return False, "duplicate_trading_date", frame

    latest_date = parsed.loc[valid].max().strftime("%Y-%m-%d")
    if expected_latest_date:
        expected = pd.to_datetime(expected_latest_date, errors="coerce")
        if pd.isna(expected) or latest_date != expected.strftime("%Y-%m-%d"):
            return False, (
                f"latest_date_mismatch; actual={latest_date}; "
                f"manifest={expected_latest_date}"
            ), frame

    normalized = frame.loc[valid].copy()
    normalized["_parsed_date"] = parsed.loc[valid]
    normalized = normalized.sort_values("_parsed_date").drop(columns=["_parsed_date"])
    return True, None, normalized

def run_global_analysis(market_id="tw-share"):
    """
    分析主邏輯：讀取 CSV -> 計算回報率 -> 繪製分布圖 -> 生成文字報表
    """
    market_label = market_id.upper()
    print(f"📊 正在啟動 {market_label} 深度矩陣分析...")
    
    data_path = Path("./data") / market_id / "dayK"
    image_out_dir = Path("./output/images") / market_id
    image_out_dir.mkdir(parents=True, exist_ok=True)
    
    all_files = list(data_path.glob("*.csv"))
    if not all_files:
        print(f"⚠️ 找不到 {market_id} 的 CSV 數據檔案。")
        return [], pd.DataFrame(), {}

    # Taiwan analysis is restricted to this run's successful-download allow-list.
    # Restored CSV cache files outside the allow-list are excluded.
    if market_id == "tw-share":
        manifest_path = Path("./data/tw-share/lists/analysis_universe.csv")
        if not manifest_path.exists():
            print("❌ 缺少本次執行的 analysis_universe.csv，拒絕分析舊快取。")
            return [], pd.DataFrame(), {}
        try:
            manifest = pd.read_csv(manifest_path, dtype={"ticker": str})
            if not {"ticker", "name", "data_date", "manifest_created_at"}.issubset(manifest.columns):
                raise ValueError("manifest 欄位不完整")
            created = pd.to_datetime(manifest["manifest_created_at"], errors="coerce").dropna()
            today = pd.Timestamp.now().date()
            if created.empty or created.dt.date.nunique() != 1 or created.dt.date.iloc[0] != today:
                raise ValueError("manifest 建立日期非本次執行日期")
            # Cross-sectional return distributions must use one common
            # observation date. Lagging and undated symbols remain in the
            # source manifest for audit, but are excluded from this snapshot.
            fresh_manifest, latest_manifest_date, lagging, undated = (
                filter_manifest_to_latest_date(manifest)
            )
            expected_dates = {
                str(row.ticker): str(row.data_date)
                for row in fresh_manifest[["ticker", "data_date"]].itertuples(index=False)
            }
            allowed = set(expected_dates)
            print(
                f"📅 本次共同行情基準日：{latest_manifest_date}；"
                f"納入 {len(allowed)} 檔；"
                f"排除日期落後 {len(lagging)} 檔、無日期 {len(undated)} 檔"
            )
            if lagging:
                print("⚠️ 日期落後排除：" + ", ".join(lagging))
            if undated:
                print("⚠️ 無有效日期排除：" + ", ".join(undated))
        except Exception as exc:
            print(f"❌ 台股白名單驗證失敗，拒絕分析：{exc}")
            return [], pd.DataFrame(), {}
        all_files = [
            path for path in all_files
            if path.name.split("_", 1)[0] in allowed
        ]
        if not all_files:
            print("❌ 本次白名單沒有可分析的 CSV，拒絕使用舊快取。")
            return [], pd.DataFrame(), {}
        print(f"🔒 台股分析白名單：{len(allowed)} 檔；符合 CSV：{len(all_files)} 檔")

    results = []
    skipped = {"insufficient_history": [], "missing_columns": [], "invalid_ohlc": [], "read_or_parse_error": []}
    for f in tqdm(all_files, desc=f"分析 {market_label} 數據"):
        stem = f.name.replace(".csv", "")
        if market_id in ["hk-share", "jp-share", "kr-share"]:
            tkr, nm = stem, stem
        elif "_" in stem:
            tkr, nm = stem.split("_", 1)
        else:
            tkr, nm = stem, stem

        try:
            df = pd.read_csv(f)
            df.columns = [str(col).lower() for col in df.columns]
            if market_id == "tw-share":
                dates_valid, date_reason, df = validate_history_dates(
                    df, expected_latest_date=expected_dates.get(tkr), lookback=251
                )
                if not dates_valid:
                    skipped["read_or_parse_error"].append(f"{tkr}({date_reason})")
                    continue
            required = {"close", "high", "low"}
            if not required.issubset(df.columns):
                skipped["missing_columns"].append(tkr)
                continue
            if len(df) < 6:
                skipped["insufficient_history"].append(f"{tkr}({len(df)} rows; need >=6 for 5-day return)")
                continue

            prices = df[["close", "high", "low"]].apply(pd.to_numeric, errors="coerce")
            valid_ohlc, ohlc_reason = validate_recent_ohlc(prices, lookback=251)
            if not valid_ohlc:
                # Preserve the raw vendor values for diagnosis. Never silently
                # clamp or rewrite OHLC prices because that would fabricate market data.
                recent_row = None
                marker = "recent_row="
                if marker in str(ohlc_reason):
                    try:
                        recent_row = int(str(ohlc_reason).split(marker, 1)[1].split(";", 1)[0])
                    except (TypeError, ValueError):
                        recent_row = None
                detail = str(ohlc_reason)
                if recent_row is not None:
                    recent_start = max(0, len(prices) - 251)
                    source_index = recent_start + recent_row
                    if 0 <= source_index < len(prices):
                        date_col = next(
                            (column for column in ("date", "datetime") if column in df.columns),
                            None,
                        )
                        date_value = df.iloc[source_index][date_col] if date_col else "unknown"
                        detail += (
                            f"; date={date_value}; "
                            f"close={prices.iloc[source_index]['close']}; "
                            f"high={prices.iloc[source_index]['high']}; "
                            f"low={prices.iloc[source_index]['low']}"
                        )
                skipped["invalid_ohlc"].append(f"{tkr}({detail})")
                continue
            # Metrics below use at most the latest 251 closes and latest 250
            # highs/lows. Historical anomalies outside this window cannot
            # affect the reported periods and must not discard the whole stock.
            close = prices["close"].to_numpy(dtype=float)
            high = prices["high"].to_numpy(dtype=float)
            low = prices["low"].to_numpy(dtype=float)

            row = {"Ticker": tkr, "Full_Name": nm}
            periods = [("Week", 5), ("Month", 20), ("Year", 250)]
            for p_name, days in periods:
                if len(close) <= days:
                    continue
                prev_c = close[-(days + 1)]
                if prev_c <= 0:
                    continue
                row[f"{p_name}_High"] = (max(high[-days:]) - prev_c) / prev_c * 100
                row[f"{p_name}_Close"] = (close[-1] - prev_c) / prev_c * 100
                row[f"{p_name}_Low"] = (min(low[-days:]) - prev_c) / prev_c * 100
            results.append(row)
        except Exception as exc:
            skipped["read_or_parse_error"].append(f"{tkr}({type(exc).__name__})")

    if market_id == "tw-share" and skipped["invalid_ohlc"]:
        from twse_audit import audit_twse_symbols

        invalid_tickers = [item.split("(", 1)[0] for item in skipped["invalid_ohlc"]]
        print("🔎 使用 TWSE 官方原始日成交資料查核 OHLC 異常標的（僅診斷，不自動改價）")
        audit_twse_symbols(invalid_tickers, expected_date=latest_manifest_date)

    skipped_total = sum(len(items) for items in skipped.values())
    print(f"🧪 資料品質摘要：候選 {len(all_files)} 檔；有效 {len(results)} 檔；排除 {skipped_total} 檔")
    for reason, items in skipped.items():
        if items:
            print(f"  - {reason}: {len(items)} 檔；代號/原因：{', '.join(items[:30])}")

    df_res = pd.DataFrame(results)
    if df_res.empty: return [], df_res, {}

    # Report the usable cross-sectional coverage of each rolling return period.
    candidate_count = len(all_files)
    for period, days in (("Week", 5), ("Month", 20), ("Year", 250)):
        column = f"{period}_Close"
        available = int(df_res[column].notna().sum()) if column in df_res else 0
        coverage = available / candidate_count * 100 if candidate_count else 0.0
        print(
            f"📈 {days} 交易日資料覆蓋：{available}/{candidate_count} "
            f"({coverage:.1f}%)"
        )

    # --- 繪圖邏輯 ---
    images = []
    color_map = {'High': '#28a745', 'Close': '#007bff', 'Low': '#dc3545'}
    EXTREME_COLOR = '#FF4500' 
    plot_bins = np.append(BINS, X_MAX + BIN_SIZE)

    for p_n, p_z in [('Week', '週'), ('Month', '月'), ('Year', '年')]:
        for t_n, t_z in [('High', '最高-進攻'), ('Close', '收盤-實質'), ('Low', '最低-防禦')]:
            col = f"{p_n}_{t_n}"
            if col not in df_res.columns: continue
            data = df_res[col].dropna()
            
            fig, ax = plt.subplots(figsize=(12, 7))
            clipped_data = np.clip(data.values, X_MIN, X_MAX + BIN_SIZE)
            counts, edges = np.histogram(clipped_data, bins=plot_bins)
            
            ax.bar(edges[:-2], counts[:-1], width=9, align='edge', 
                   color=color_map[t_n], alpha=0.7, edgecolor='white')
            ax.bar(edges[-2], counts[-1], width=9, align='edge', 
                   color=EXTREME_COLOR, alpha=0.9, edgecolor='black', linewidth=1.5)
            
            max_h = counts.max() if len(counts) > 0 else 1
            for i, h in enumerate(counts):
                if h > 0:
                    x_pos = edges[i] + 4.5
                    is_extreme = (i == len(counts) - 1)
                    ax.text(x_pos, h + (max_h * 0.02), f'{int(h)}\n({h/len(data)*100:.1f}%)', 
                            ha='center', va='bottom', fontsize=9, fontweight='bold', 
                            color='red' if is_extreme else 'black')

            ax.set_ylim(0, max_h * 1.4) 
            ax.set_title(f"【{market_label}】{p_z}K {t_z} 報酬分布 (樣本:{len(data)})", fontsize=18, fontweight='bold')
            ax.set_xticks(plot_bins)
            x_labels = [f"{int(x)}%" for x in BINS] + [f">{int(X_MAX)}%"]
            ax.set_xticklabels(x_labels, rotation=45)
            ax.grid(axis='y', linestyle='--', alpha=0.3)
            plt.tight_layout()
            
            img_path = image_out_dir / f"{col.lower()}.png"
            plt.savefig(img_path, dpi=120)
            plt.close()
            images.append({'id': col.lower(), 'path': str(img_path), 'label': f"【{market_label}】{p_z}K {t_z}"})

    text_reports = {}
    for p_n in ['Week', 'Month', 'Year']:
        col = f'{p_n}_High'
        if col in df_res.columns:
            text_reports[p_n] = build_company_list(df_res[col].values, df_res['Ticker'].tolist(), df_res['Full_Name'].tolist(), BINS, market_id)
    
    return images, df_res, text_reports
