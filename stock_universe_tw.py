# -*- coding: utf-8 -*-
"""Validated TWSE-listed ordinary-share universe.

The TWSE C_public.jsp?strMode=2 page is the official listed-securities
classification table. We accept only rows whose CFI code is ESVUFR
(ordinary shares); malformed or unexpectedly small responses fail closed.
"""
from datetime import datetime
from io import StringIO
from pathlib import Path
import re

import pandas as pd
import requests

TWSE_LIST_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
MIN_EXPECTED_STOCKS = 500


def fetch_listed_common_stocks():
    response = requests.get(
        TWSE_LIST_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    response.encoding = "big5"
    tables = pd.read_html(StringIO(response.text), header=None)
    if not tables:
        raise ValueError("TWSE listed-securities page returned no tables")

    # Locate the table/header by labels, rather than assuming the first table
    # has a fixed shape. The first field combines ticker and Chinese name.
    raw = max(tables, key=len).copy()
    header_index = None
    cfi_index = None
    for idx, row in raw.iterrows():
        values = [str(v).strip().lower() for v in row.tolist()]
        cfi_matches = [i for i, value in enumerate(values) if "cficode" in value]
        code_name_matches = [
            i for i, value in enumerate(values)
            if "有價證券代號及名稱" in value or "證券代號及名稱" in value
        ]
        if cfi_matches and code_name_matches:
            header_index = idx
            cfi_index = cfi_matches[0]
            code_name_index = code_name_matches[0]
            break
    if header_index is None:
        # Some TWSE responses have a title row and no explicit header row.
        # The official C_public table's stable layout places the combined
        # code/name in column 0 and CFI code in column 5.
        code_name_index, cfi_index = 0, 5
        if raw.shape[1] <= cfi_index:
            raise ValueError(f"Unexpected TWSE table shape: {raw.shape}")
        data = raw
    else:
        data = raw.iloc[header_index + 1:]

    records = []
    for _, row in data.iterrows():
        if len(row) <= max(code_name_index, cfi_index):
            continue
        code_name = str(row.iloc[code_name_index]).strip()
        cfi_code = str(row.iloc[cfi_index]).strip().upper()
        if cfi_code != "ESVUFR":
            continue
        match = re.match(r"^\s*(\d{4})\s+(.+?)\s*$", code_name)
        if not match:
            continue
        code, name = match.group(1), match.group(2)
        records.append({
            "ticker": f"{code}.TW",
            "code": code,
            "name": name,
            "cfi_code": cfi_code,
            "source": "TWSE_C_public_strMode_2",
        })

    result = pd.DataFrame(records).drop_duplicates(subset=["ticker"])
    if len(result) < MIN_EXPECTED_STOCKS:
        raise ValueError(
            f"TWSE ordinary-share universe unexpectedly small: {len(result)}"
        )
    result = result.sort_values("code").reset_index(drop=True)
    result["retrieved_at"] = datetime.now().astimezone().isoformat()
    return result


def save_universe(frame, path):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False, encoding="utf-8-sig")
    return output
