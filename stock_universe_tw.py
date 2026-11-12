# -*- coding: utf-8 -*-
"""Validated TWSE-listed common-stock universe.

Only the TWSE ISIN listed-stock classification is accepted. No OTC, ETF,
warrant, depositary receipt, or market-code guessing fallback is used.
"""
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

TWSE_LIST_URL = (
    "https://isin.twse.com.tw/isin/class_main.jsp"
    "?market=1&issuetype=1&Page=1&chklike=Y"
)
EXCLUDED_NAME_MARKERS = (
    "特別股", "存託憑證", "受益證券", "指數股票型基金",
    "交換交易基金", "認購權證", "認售權證", "認股權證",
)


def fetch_listed_common_stocks():
    """Fetch and validate listed common stocks; fail closed on source issues."""
    response = requests.get(
        TWSE_LIST_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    if not tables:
        raise ValueError("TWSE ISIN returned no tables")

    frame = tables[0]
    required = {"有價證券代號", "有價證券名稱"}
    if not required.issubset(frame.columns):
        missing = ", ".join(sorted(required - set(frame.columns)))
        raise ValueError(f"TWSE ISIN schema changed; missing: {missing}")

    records = []
    for _, row in frame.iterrows():
        code = str(row["有價證券代號"]).strip()
        name = str(row["有價證券名稱"]).strip()
        if not (code.isdigit() and len(code) == 4 and name and name != "nan"):
            continue
        if any(marker in name for marker in EXCLUDED_NAME_MARKERS):
            continue
        records.append({
            "ticker": f"{code}.TW",
            "code": code,
            "name": name,
            "source": "TWSE_ISIN_market1_issuetype1",
        })

    result = pd.DataFrame(records).drop_duplicates(subset=["ticker"])
    # A collapsed or malformed response must never be treated as a valid pool.
    if len(result) < 500:
        raise ValueError(
            f"TWSE listed-stock universe unexpectedly small: {len(result)}"
        )
    result = result.sort_values("code").reset_index(drop=True)
    result["retrieved_at"] = datetime.now().astimezone().isoformat()
    return result


def save_universe(frame, path):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False, encoding="utf-8-sig")
    return output
