#!/usr/bin/env python3
"""
Multi-Asset ATR Tracker Script
Fetches current OHLCV data from multiple sources (Binance for crypto,
Yahoo Finance for stocks/ETFs), calculates technical indicators, and
writes to both master.csv and ATR_Tracker_Dashboard.xlsx.
"""

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl import load_workbook

warnings.filterwarnings('ignore', category=FutureWarning, module='yfinance')
warnings.filterwarnings('ignore', category=FutureWarning, module='pandas')

from trading_utils import (
    ASSETS,
    ASSET_CONFIG,
    MANUAL_DATA,
    TIMEFRAMES,
    SPREADSHEET_PATH,
    MASTER_CSV_PATH,
    MARKET_CAPS_JSON_PATH,
    calculate_indicators,
    fetch_ohlcv_binance,
    fetch_ohlcv_yahoo,
    fetch_ohlcv_ccxt,
    fetch_ohlcv_geckoterminal,
    get_manual_data,
    fetch_market_caps,
)
from trading_utils.excel_utils import ensure_excel_headers

_PROJECT_ROOT = Path(__file__).resolve().parent
_MASTER_CSV = Path(MASTER_CSV_PATH)
_SPREADSHEET = Path(SPREADSHEET_PATH)

_EXCEL_HEADERS = [
    'Date', 'Asset', 'Timeframe', 'Price', 'EMA21', 'ATR',
    'RSI', 'RSI_Z_Score', 'ATR_Distance', 'Pct_Above_EMA',
    'High', 'Low', 'Volume',
]

_MAX_FAILED_ASSETS = 60  # allow up to 20 assets × 3 timeframes missing (newer tokens + macro may be unavailable)


def get_data(asset, timeframe):
    """Fetch and calculate indicators for the latest bar of an asset."""
    config = ASSET_CONFIG.get(asset)
    if not config:
        print(f"Configuration not found for {asset}")
        return None

    source = config['source']

    if source == 'manual':
        return get_manual_data(asset, timeframe)

    if source == 'binance':
        df = fetch_ohlcv_binance(config['symbol'], timeframe)
    elif source == 'yahoo':
        df = fetch_ohlcv_yahoo(config['symbol'], timeframe)
    elif source == 'ccxt':
        df = fetch_ohlcv_ccxt(config['exchange'], config['symbol'], timeframe)
    elif source == 'geckoterminal':
        df = fetch_ohlcv_geckoterminal(config['network'], config['pool'], timeframe)
    else:
        print(f"Unknown source for {asset}: {source}")
        return None

    if df is None or df.empty:
        return None

    # Yahoo sometimes returns an unfinished latest bar without a close (forex,
    # Asian indices). Use the newest bar that has one; otherwise the NaN row
    # would be stored as a permanent hole in History.
    last_valid = df['close'].last_valid_index()
    if last_valid is None:
        return None
    df = df.loc[:last_valid]

    df = calculate_indicators(df)
    latest = df.iloc[-1]

    return {
        'Date': df.index[-1].strftime('%Y-%m-%d') if hasattr(df.index[-1], 'strftime') else str(df.index[-1]),
        'Asset': asset,
        'Price': float(latest['close']),
        'EMA21': float(latest['EMA21']),
        'ATR': float(latest['ATR']),
        'RSI': float(latest['RSI']),
        'RSI_Z_Score': float(latest['RSI_Z_Score']),
        'ATR_Distance': float(latest['ATR_Distance']) if pd.notna(latest['ATR_Distance']) else None,
        'Pct_Above_EMA': float(latest['Pct_Above_EMA']),
        'Timeframe': timeframe,
        'High':   float(df['high'].iloc[-1])   if 'high'   in df.columns and pd.notna(df['high'].iloc[-1])   else None,
        'Low':    float(df['low'].iloc[-1])    if 'low'    in df.columns and pd.notna(df['low'].iloc[-1])    else None,
        'Volume': float(df['volume'].iloc[-1]) if 'volume' in df.columns and pd.notna(df['volume'].iloc[-1]) else None,
    }


def _excel_row_values(row_data):
    """Cell values for one record, in _EXCEL_HEADERS order."""
    return [row_data.get(header) for header in _EXCEL_HEADERS]


def write_to_excel(records):
    """Write records to ATR_Tracker_Dashboard.xlsx.

    New Date+Asset+Timeframe keys are appended. A key that already exists is
    the still-open bar (a weekly/monthly bar keeps its Date for the whole
    period), so its cells are refreshed instead of left at the first day's
    values. Unfinished bars (no Price) and empty values never overwrite.
    """
    try:
        wb = load_workbook(_SPREADSHEET)
    except FileNotFoundError:
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

    sheet_name = 'Data'
    if sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        repaired = ensure_excel_headers(ws, _EXCEL_HEADERS)
        if repaired:
            print(f"Excel: added {repaired} missing header cell(s) (High/Low/Volume)")
        # Map each existing composite key to its worksheet row
        existing_rows = {}
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            date, asset, timeframe = str(row[0]), str(row[1]), str(row[2])
            existing_rows[f"{date}|{asset}|{timeframe}"] = row_idx
        start_row = ws.max_row + 1
    else:
        ws = wb.create_sheet(title=sheet_name)
        for col, header in enumerate(_EXCEL_HEADERS, 1):
            ws.cell(row=1, column=col, value=header)
        existing_rows = {}
        start_row = 2

    new_count = 0
    updated_count = 0
    for row_data in records:
        key = f"{row_data['Date']}|{row_data['Asset']}|{row_data['Timeframe']}"
        values = _excel_row_values(row_data)
        if key in existing_rows:
            if row_data.get('Price') is None:
                continue
            row_idx = existing_rows[key]
            changed = False
            for col, value in enumerate(values, 1):
                if value is None or col <= 3:
                    continue
                if ws.cell(row=row_idx, column=col).value != value:
                    ws.cell(row=row_idx, column=col, value=value)
                    changed = True
            updated_count += int(changed)
            continue
        for col, value in enumerate(values, 1):
            ws.cell(row=start_row, column=col, value=value)
        existing_rows[key] = start_row
        start_row += 1
        new_count += 1

    wb.save(_SPREADSHEET)
    print(f"Excel: wrote {new_count} new records, refreshed {updated_count} open bars in {_SPREADSHEET}")


_MAX_MISSING_OHLC_SHARE = 0.25  # fail the run if more than this share of records lack High/Low


def find_missing_ohlc(records):
    """Return 'ASSET (tf)' labels for records without High/Low.

    ADX and the Volume Profile depend on High/Low, so a source that silently
    stops returning them degrades the dashboard without any fetch error.
    Manual-source assets never carry OHLC and are skipped.
    """
    missing = []
    for rec in records:
        if ASSET_CONFIG.get(rec['Asset'], {}).get('source') == 'manual':
            continue
        if rec.get('High') is None or rec.get('Low') is None:
            missing.append(f"{rec['Asset']} ({rec['Timeframe']})")
    return missing


def main():
    """Fetch current data for all assets and write to CSV + Excel."""
    all_data = []
    failed = 0

    print(f"Fetching data for {len(ASSETS)} assets across {len(TIMEFRAMES)} timeframes...")

    for asset in ASSETS:
        for timeframe in TIMEFRAMES:
            print(f"Processing {asset} ({timeframe})...")
            data = get_data(asset, timeframe)
            if data:
                all_data.append(data)
            else:
                failed += 1
                print(f"  WARNING: failed to fetch {asset} ({timeframe})")

    missing_ohlc = find_missing_ohlc(all_data)
    if missing_ohlc:
        print(f"WARNING: {len(missing_ohlc)} of {len(all_data)} records have no High/Low: "
              f"{', '.join(missing_ohlc[:10])}{' …' if len(missing_ohlc) > 10 else ''}")
    if all_data and len(missing_ohlc) / len(all_data) > _MAX_MISSING_OHLC_SHARE:
        print(f"ERROR: High/Low missing for more than {_MAX_MISSING_OHLC_SHARE:.0%} of records — "
              f"the data source stopped returning OHLC. Exiting non-zero.")
        sys.exit(1)

    if all_data:
        _MASTER_CSV.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(all_data)
        df.to_csv(_MASTER_CSV, index=False)
        print(f"master.csv: {len(df)} records written to {_MASTER_CSV}")

        write_to_excel(all_data)

    # Fetch and save market cap data from CoinGecko
    market_caps = fetch_market_caps()
    mcap_path = Path(MARKET_CAPS_JSON_PATH)
    mcap_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mcap_path, 'w') as f:
        json.dump({
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'data': market_caps,
        }, f)

    if failed > _MAX_FAILED_ASSETS:
        print(f"ERROR: {failed} assets failed (threshold {_MAX_FAILED_ASSETS}). Exiting non-zero.")
        sys.exit(1)

    return all_data


if __name__ == "__main__":
    main()
