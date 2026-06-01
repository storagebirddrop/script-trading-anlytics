#!/usr/bin/env python3
"""
Historical Data Backfill Script
Fetches historical OHLCV data from January 1, 2024 to present for all assets,
calculates indicators, and writes to CSV files and the Excel workbook.
"""

import warnings
from datetime import datetime
from pathlib import Path

import ccxt
import openpyxl
import pandas as pd
import yfinance as yf
from openpyxl import load_workbook

warnings.filterwarnings('ignore', category=FutureWarning, module='yfinance')
warnings.filterwarnings('ignore', category=FutureWarning, module='pandas')

from trading_utils import (
    ASSETS,
    ASSET_CONFIG,
    SPREADSHEET_PATH,
    MASTER_CSV_PATH,
    HISTORY_CSV_PATH,
    calculate_indicators,
    fetch_ohlcv_geckoterminal,
)

_PROJECT_ROOT = Path(__file__).resolve().parent
_MASTER_CSV = Path(MASTER_CSV_PATH)
_HISTORY_CSV = Path(HISTORY_CSV_PATH)
_SPREADSHEET = Path(SPREADSHEET_PATH)

START_DATE = datetime(2010, 1, 1)  # Yahoo Finance returns data from listing date if earlier
END_DATE = datetime.now()

_EXCEL_HEADERS = [
    'Date', 'Asset', 'Timeframe', 'Price', 'EMA21', 'ATR',
    'RSI', 'RSI_Z_Score', 'ATR_Distance', 'Pct_Above_EMA',
]


def fetch_historical_binance(symbol, start_date, end_date, timeframe='1d'):
    """Fetch historical OHLCV from Binance with pagination (M5)."""
    exchange = ccxt.binance({'enableRateLimit': True})
    since = int(start_date.timestamp() * 1000)
    all_ohlcv = []

    try:
        while True:
            batch = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not batch:
                break
            all_ohlcv.extend(batch)
            last_ts = batch[-1][0]
            since = last_ts + 1
            if datetime.fromtimestamp(last_ts / 1000) >= end_date:
                break

        if not all_ohlcv:
            return None

        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        return df
    except Exception as e:
        print(f"Error fetching {symbol} from Binance: {e}")
        return None


def fetch_historical_yahoo(symbol, start_date, end_date, timeframe='1d'):
    """Fetch historical OHLCV from Yahoo Finance."""
    interval_map = {'1d': '1d', '1w': '1wk'}
    interval = interval_map.get(timeframe, '1d')

    try:
        data = yf.download(symbol, start=start_date, end=end_date, interval=interval, progress=False)
        if data.empty:
            print(f"No data returned for {symbol}")
            return None

        # yfinance >= 0.2 returns a (Price, Ticker) MultiIndex for single-ticker downloads.
        if isinstance(data.columns, pd.MultiIndex):
            price_level = 'Price' if 'Price' in data.columns.names else 0
            data.columns = data.columns.get_level_values(price_level)

        data = data.rename(columns={
            'Open': 'open', 'High': 'high', 'Low': 'low',
            'Close': 'close', 'Volume': 'volume',
        })
        data = data.reset_index()
        data = data.rename(columns={'Date': 'timestamp', 'Datetime': 'timestamp'})
        data.set_index('timestamp', inplace=True)
        return data
    except Exception as e:
        print(f"Error fetching {symbol} from Yahoo Finance: {e}")
        return None


def get_historical_data(asset, start_date, end_date, timeframe):
    """Fetch and calculate indicators for an asset over a date range."""
    config = ASSET_CONFIG.get(asset)
    if not config:
        print(f"Configuration not found for {asset}")
        return None

    source = config['source']

    if source == 'binance':
        df = fetch_historical_binance(config['symbol'], start_date, end_date, timeframe)
    elif source == 'yahoo':
        df = fetch_historical_yahoo(config['symbol'], start_date, end_date, timeframe)
    elif source == 'geckoterminal':
        # GeckoTerminal returns all available history in one call; filter to requested range
        df = fetch_ohlcv_geckoterminal(config['network'], config['pool'], timeframe)
        if df is not None and not df.empty:
            df = df[(df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(end_date))]
    else:
        return None

    if df is None or df.empty:
        return None

    df = calculate_indicators(df)

    data = []
    for idx, row in df.iterrows():
        def to_scalar(val):
            if isinstance(val, (pd.Series, pd.DataFrame)):
                val = val.iloc[0] if isinstance(val, pd.Series) else val.iloc[0, 0]
            if pd.isna(val):
                return None
            return float(val)

        data.append({
            'Date': idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx),
            'Asset': asset,
            'Price': to_scalar(row['close']),
            'EMA21': to_scalar(row['EMA21']),
            'ATR': to_scalar(row['ATR']),
            'RSI': to_scalar(row['RSI']),
            'RSI_Z_Score': to_scalar(row['RSI_Z_Score']),
            'ATR_Distance': to_scalar(row['ATR_Distance']),
            'Pct_Above_EMA': to_scalar(row['Pct_Above_EMA']),
            'Timeframe': timeframe,
        })

    return data


def write_to_sheet(wb, sheet_name, data):
    """Write records to an Excel sheet, skipping any existing Date+Asset+Timeframe keys (C5)."""
    if sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        # Build set of keys already in the sheet
        existing_keys = set()
        for row in ws.iter_rows(min_row=2, values_only=True):
            existing_keys.add(f"{row[0]}|{row[1]}|{row[2]}")
        start_row = ws.max_row + 1
    else:
        ws = wb.create_sheet(title=sheet_name)
        for col, header in enumerate(_EXCEL_HEADERS, 1):
            ws.cell(row=1, column=col, value=header)
        existing_keys = set()
        start_row = 2

    new_count = 0
    for row_data in data:
        key = f"{row_data['Date']}|{row_data['Asset']}|{row_data['Timeframe']}"
        if key in existing_keys:
            continue
        ws.cell(row=start_row, column=1, value=row_data['Date'])
        ws.cell(row=start_row, column=2, value=row_data['Asset'])
        ws.cell(row=start_row, column=3, value=row_data['Timeframe'])
        ws.cell(row=start_row, column=4, value=row_data['Price'])
        ws.cell(row=start_row, column=5, value=row_data['EMA21'])
        ws.cell(row=start_row, column=6, value=row_data['ATR'])
        ws.cell(row=start_row, column=7, value=row_data['RSI'])
        ws.cell(row=start_row, column=8, value=row_data['RSI_Z_Score'])
        ws.cell(row=start_row, column=9, value=row_data['ATR_Distance'])
        ws.cell(row=start_row, column=10, value=row_data['Pct_Above_EMA'])
        existing_keys.add(key)
        start_row += 1
        new_count += 1

    print(f"  {sheet_name}: wrote {new_count} new records (sheet total rows: {ws.max_row})")


def main():
    """Backfill historical data for all assets."""
    print("Starting Historical Data Backfill...")
    print(f"Date range: {START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}")
    print(f"Total assets: {len(ASSETS)}")
    print()

    all_data = []

    for asset in ASSETS:
        print(f"Processing {asset}...")
        for timeframe in ['1d', '1w']:
            records = get_historical_data(asset, START_DATE, END_DATE, timeframe)
            if records:
                all_data.extend(records)
                print(f"  {timeframe}: {len(records)} records")
            else:
                print(f"  {timeframe}: failed to fetch data")

    print(f"\nTotal records fetched: {len(all_data)}")

    all_data.sort(key=lambda x: x['Date'])

    # Write CSV files
    _MASTER_CSV.parent.mkdir(parents=True, exist_ok=True)

    master_df = pd.DataFrame(all_data).sort_values(['Asset', 'Timeframe', 'Date'])
    master_df.to_csv(_MASTER_CSV, index=False)
    print(f"Written {len(master_df)} records to {_MASTER_CSV}")

    history_df = pd.DataFrame(all_data).sort_values(['Date', 'Asset', 'Timeframe'])
    history_df.to_csv(_HISTORY_CSV, index=False)
    print(f"Written {len(history_df)} records to {_HISTORY_CSV}")

    # Write Excel workbook
    try:
        wb = load_workbook(_SPREADSHEET)
    except FileNotFoundError:
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

    if all_data:
        write_to_sheet(wb, 'Data', all_data)

    wb.save(_SPREADSHEET)
    print(f"Excel workbook saved to {_SPREADSHEET}")
    print("\nBackfill complete!")


if __name__ == '__main__':
    main()
