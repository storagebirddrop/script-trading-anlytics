#!/usr/bin/env python3
"""
Multi-Asset ATR Tracker Script
Fetches OHLCV data from multiple sources (Binance for crypto, Yahoo Finance for stocks/ETFs),
calculates technical indicators, and writes to Excel spreadsheet.
"""

import ccxt
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import openpyxl
from openpyxl import load_workbook
import warnings

warnings.filterwarnings('ignore')

# Configuration
ASSETS = [
    # Crypto assets (Binance)
    'BTC', 'ETH', 'SOL', 'XLM', 'REZ', 'RSR', 'NEAR', 'RENDER', 'ONDO', 'ACH', 'BNB', 'XRP',
    # NASDAQ stocks (Yahoo Finance)
    'MSTR', 'XXI', 'RIOT', 'MARA', 'IREN', 'BMNR', 'HUT', 'WULF', 'HIVE', 'CLSK', 'SLNH',
    # LSE ETFs (Yahoo Finance with .L suffix)
    'MSTY', 'YMST', 'MARY', 'RIOY', 'IREY', 'BMNY',
    # Manually inserted assets (Solana tokens)
    'SCP', 'D2X'
]
TIMEFRAMES = ['1d', '1w']  # Daily and Weekly
SPREADSHEET_PATH = 'ATR_Tracker_Dashboard.xlsx'
MASTER_CSV_PATH = 'data/master.csv'
HISTORY_CSV_PATH = 'data/history.csv'

# Asset mappings with data source and symbol
ASSET_CONFIG = {
    # Crypto assets (Binance)
    'BTC': {'source': 'binance', 'symbol': 'BTC/USDT'},
    'ETH': {'source': 'binance', 'symbol': 'ETH/USDT'},
    'SOL': {'source': 'binance', 'symbol': 'SOL/USDT'},
    'XLM': {'source': 'binance', 'symbol': 'XLM/USDT'},
    'REZ': {'source': 'binance', 'symbol': 'REZ/USDT'},
    'RSR': {'source': 'binance', 'symbol': 'RSR/USDT'},
    'NEAR': {'source': 'binance', 'symbol': 'NEAR/USDT'},
    'RENDER': {'source': 'binance', 'symbol': 'RNDR/USDT'},  # RENDER is RNDR on Binance
    'ONDO': {'source': 'binance', 'symbol': 'ONDO/USDT'},
    'ACH': {'source': 'binance', 'symbol': 'ACH/USDT'},
    'BNB': {'source': 'binance', 'symbol': 'BNB/USDT'},
    'XRP': {'source': 'binance', 'symbol': 'XRP/USDT'},
    # NASDAQ stocks (Yahoo Finance)
    'MSTR': {'source': 'yahoo', 'symbol': 'MSTR'},
    'XXI': {'source': 'yahoo', 'symbol': 'XXI'},
    'RIOT': {'source': 'yahoo', 'symbol': 'RIOT'},
    'MARA': {'source': 'yahoo', 'symbol': 'MARA'},
    'IREN': {'source': 'yahoo', 'symbol': 'IREN'},
    'BMNR': {'source': 'yahoo', 'symbol': 'BMNR'},
    'HUT': {'source': 'yahoo', 'symbol': 'HUT'},
    'WULF': {'source': 'yahoo', 'symbol': 'WULF'},
    'HIVE': {'source': 'yahoo', 'symbol': 'HIVE'},
    'CLSK': {'source': 'yahoo', 'symbol': 'CLSK'},
    'SLNH': {'source': 'yahoo', 'symbol': 'SLNH'},
    # LSE ETFs (Yahoo Finance with .L suffix)
    'MSTY': {'source': 'yahoo', 'symbol': 'MSTY.L'},
    'YMST': {'source': 'yahoo', 'symbol': 'YMST.L'},
    'MARY': {'source': 'yahoo', 'symbol': 'MARY.L'},
    'RIOY': {'source': 'yahoo', 'symbol': 'RIOY.L'},
    'IREY': {'source': 'yahoo', 'symbol': 'IREY.L'},
    'BMNY': {'source': 'yahoo', 'symbol': 'BMNY.L'},
    # Manually inserted assets (Solana tokens - data from TradingView/Birdeye)
    'SCP': {'source': 'manual'},
    'D2X': {'source': 'manual'},
}

# Manual data configuration - update these values from TradingView or Birdeye
# Format: {asset: {timeframe: {price, ema21, atr, rsi}}}
MANUAL_DATA = {
    'SCP': {
        '1d': {'price': 0.0079, 'ema21': 0.0082, 'atr': 0.0003, 'rsi': 45.0},
        '1w': {'price': 0.0079, 'ema21': 0.0080, 'atr': 0.0004, 'rsi': 50.0},
    },
    'D2X': {
        '1d': {'price': 0.0018, 'ema21': 0.0017, 'atr': 0.0001, 'rsi': 55.0},
        '1w': {'price': 0.0018, 'ema21': 0.0016, 'atr': 0.0002, 'rsi': 60.0},
    },
}

# Indicator parameters
EMA_PERIOD = 21
ATR_PERIOD = 14
RSI_PERIOD = 14
Z_SCORE_PERIOD = 20


def fetch_ohlcv_binance(symbol, timeframe, limit=100):
    """Fetch OHLCV data from Binance for crypto assets."""
    exchange = ccxt.binance({
        'enableRateLimit': True,
    })
    
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        print(f"Error fetching {symbol} from Binance ({timeframe}): {e}")
        return None


def fetch_ohlcv_yahoo(symbol, timeframe, limit=100):
    """Fetch OHLCV data from Yahoo Finance for stocks/ETFs."""
    # Map timeframes to Yahoo Finance intervals
    interval_map = {
        '1d': '1d',
        '1w': '1wk',
        '1M': '1mo'
    }
    interval = interval_map.get(timeframe, '1d')
    
    # Map timeframes to Yahoo Finance periods
    period_map = {
        '1d': '3mo',
        '1w': '1y',
        '1M': '2y'
    }
    period = period_map.get(timeframe, '3mo')
    
    try:
        data = yf.download(symbol, period=period, interval=interval, progress=False)
        if data.empty:
            print(f"No data returned for {symbol} ({timeframe})")
            return None
        
        # Rename columns to match our format
        data = data.rename(columns={
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        })
        
        # Reset index to make timestamp a column
        data = data.reset_index()
        data = data.rename(columns={'Date': 'timestamp'})
        data.set_index('timestamp', inplace=True)
        
        return data
    except Exception as e:
        print(f"Error fetching {symbol} from Yahoo Finance ({timeframe}): {e}")
        return None


def fetch_ohlcv(source, symbol, timeframe, limit=100):
    """Fetch OHLCV data from specified source."""
    if source == 'binance':
        return fetch_ohlcv_binance(symbol, timeframe, limit)
    elif source == 'yahoo':
        return fetch_ohlcv_yahoo(symbol, timeframe, limit)
    elif source == 'manual':
        return None  # Manual data handled separately
    else:
        print(f"Unknown data source: {source}")
        return None


def get_manual_data(asset, timeframe):
    """Get manually inserted data for an asset."""
    if asset not in MANUAL_DATA:
        print(f"No manual data configured for {asset}")
        return None
    
    if timeframe not in MANUAL_DATA[asset]:
        print(f"No manual data for {asset} timeframe {timeframe}")
        return None
    
    data = MANUAL_DATA[asset][timeframe]
    
    # Calculate derived metrics
    atr_distance = data['price'] - (data['price'] - data['atr'])
    pct_above_ema = ((data['price'] - data['ema21']) / data['ema21']) * 100
    
    # Calculate RSI Z-score (using a simple approximation since we don't have historical data)
    # For manual data, we'll use the RSI value itself as a proxy or calculate based on recent values
    rsi_z_score = (data['rsi'] - 50) / 15  # Simple normalization
    
    return {
        'Date': datetime.now().strftime('%Y-%m-%d'),
        'Asset': asset,
        'Price': data['price'],
        'EMA21': data['ema21'],
        'ATR': data['atr'],
        'RSI': data['rsi'],
        'RSI_Z_Score': rsi_z_score,
        'ATR_Distance': atr_distance,
        'Pct_Above_EMA': pct_above_ema,
        'Timeframe': timeframe
    }


def calculate_ema(df, period):
    """Calculate Exponential Moving Average."""
    return df['close'].ewm(span=period, adjust=False).mean()


def calculate_atr(df, period):
    """Calculate Average True Range."""
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    
    return atr


def calculate_rsi(df, period):
    """Calculate Relative Strength Index."""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_z_score(series, period):
    """Calculate Z-score of a series."""
    rolling_mean = series.rolling(window=period).mean()
    rolling_std = series.rolling(window=period).std()
    z_score = (series - rolling_mean) / rolling_std
    return z_score


def calculate_indicators(df):
    """Calculate all technical indicators."""
    df = df.copy()
    
    # Ensure we're working with Series, not DataFrames
    close = df['close'].squeeze() if isinstance(df['close'], pd.DataFrame) else df['close']
    
    # Calculate indicators
    df['EMA21'] = calculate_ema(df, EMA_PERIOD)
    df['ATR'] = calculate_atr(df, ATR_PERIOD)
    df['RSI'] = calculate_rsi(df, RSI_PERIOD)
    df['RSI_Z_Score'] = calculate_z_score(df['RSI'], Z_SCORE_PERIOD)
    
    # Calculate derived metrics - ensure Series operations
    atr_series = df['ATR'].squeeze() if isinstance(df['ATR'], pd.DataFrame) else df['ATR']
    ema_series = df['EMA21'].squeeze() if isinstance(df['EMA21'], pd.DataFrame) else df['EMA21']
    
    df['ATR_Distance'] = (close - ema_series) / atr_series
    df['Pct_Above_EMA'] = ((close - ema_series) / ema_series) * 100
    
    return df


def get_latest_data(asset, timeframe):
    """Fetch and calculate indicators for an asset."""
    config = ASSET_CONFIG.get(asset)
    if not config:
        print(f"Configuration not found for {asset}")
        return None
    
    source = config['source']
    
    # Handle manual data separately
    if source == 'manual':
        return get_manual_data(asset, timeframe)
    
    symbol = config['symbol']
    
    df = fetch_ohlcv(source, symbol, timeframe)
    if df is None or df.empty:
        return None
    
    df = calculate_indicators(df)
    
    # Get the latest row with all indicators calculated
    latest = df.iloc[-1]
    
    # Ensure values are scalars, not Series
    def to_scalar(val):
        if isinstance(val, (pd.Series, pd.DataFrame)):
            return float(val.iloc[0] if isinstance(val, pd.Series) else val.iloc[0, 0])
        return float(val)
    
    return {
        'Date': latest.name.strftime('%Y-%m-%d') if hasattr(latest.name, 'strftime') else str(latest.name),
        'Asset': asset,
        'Price': to_scalar(latest['close']),
        'EMA21': to_scalar(latest['EMA21']),
        'ATR': to_scalar(latest['ATR']),
        'RSI': to_scalar(latest['RSI']),
        'RSI_Z_Score': to_scalar(latest['RSI_Z_Score']),
        'ATR_Distance': to_scalar(latest['ATR_Distance']),
        'Pct_Above_EMA': to_scalar(latest['Pct_Above_EMA']),
        'Timeframe': timeframe
    }


def write_to_master_csv(data):
    """Write data to master.csv (latest snapshot)."""
    df = pd.DataFrame(data)
    df = df.sort_values(['Asset', 'Timeframe', 'Date'])
    df.to_csv(MASTER_CSV_PATH, index=False)
    print(f"Data written to {MASTER_CSV_PATH}")


def append_to_history_csv(data):
    """Append data to history.csv (historical snapshots)."""
    df = pd.DataFrame(data)
    
    # Check if file exists
    try:
        existing_df = pd.read_csv(HISTORY_CSV_PATH)
        # Combine and remove duplicates
        combined_df = pd.concat([existing_df, df], ignore_index=True)
        combined_df = combined_df.drop_duplicates(subset=['Date', 'Asset', 'Timeframe'], keep='last')
        combined_df = combined_df.sort_values(['Date', 'Asset', 'Timeframe'])
        combined_df.to_csv(HISTORY_CSV_PATH, index=False)
        print(f"Data appended to {HISTORY_CSV_PATH} (total rows: {len(combined_df)})")
    except FileNotFoundError:
        # Create new file
        df = df.sort_values(['Date', 'Asset', 'Timeframe'])
        df.to_csv(HISTORY_CSV_PATH, index=False)
        print(f"Data written to {HISTORY_CSV_PATH} (total rows: {len(df)})")


def write_to_spreadsheet(data):
    """Write data to CSV files (primary) and Excel spreadsheet (secondary)."""
    # Write to CSV files (primary data source)
    write_to_master_csv(data)
    append_to_history_csv(data)
    
    # Write to Excel spreadsheet (secondary, for GitHub Pages)
    try:
        # Load existing workbook
        wb = load_workbook(SPREADSHEET_PATH)
    except FileNotFoundError:
        # Create new workbook if file doesn't exist
        wb = openpyxl.Workbook()
        # Remove default sheet
        wb.remove(wb.active)
    
    # Write all data to single Data sheet
    if data:
        write_to_sheet(wb, 'Data', data)
    
    # Save workbook
    wb.save(SPREADSHEET_PATH)
    print(f"Data written to Excel spreadsheet (secondary)")
    
    return 'Data'


def write_to_sheet(wb, sheet_name, data):
    """Write data to a specific sheet, creating it if it doesn't exist."""
    headers = ['Date', 'Asset', 'Timeframe', 'Price', 'EMA21', 'ATR', 'RSI', 'RSI_Z_Score', 'ATR_Distance', 'Pct_Above_EMA']
    
    if sheet_name in wb.sheetnames:
        # Sheet exists, append data
        ws = wb[sheet_name]
        start_row = ws.max_row + 1
    else:
        # Sheet doesn't exist, create it
        ws = wb.create_sheet(title=sheet_name)
        # Write headers
        for col_num, header in enumerate(headers, 1):
            ws.cell(row=1, column=col_num, value=header)
        start_row = 2
    
    # Write data
    for row_num, row_data in enumerate(data, start_row):
        ws.cell(row=row_num, column=1, value=row_data['Date'])
        ws.cell(row=row_num, column=2, value=row_data['Asset'])
        ws.cell(row=row_num, column=3, value=row_data['Timeframe'])
        ws.cell(row=row_num, column=4, value=row_data['Price'])
        ws.cell(row=row_num, column=5, value=row_data['EMA21'])
        ws.cell(row=row_num, column=6, value=row_data['ATR'])
        ws.cell(row=row_num, column=7, value=row_data['RSI'])
        ws.cell(row=row_num, column=8, value=row_data['RSI_Z_Score'])
        ws.cell(row=row_num, column=9, value=row_data['ATR_Distance'])
        ws.cell(row=row_num, column=10, value=row_data['Pct_Above_EMA'])
    
    print(f"  {sheet_name}: Added {len(data)} records (total rows: {ws.max_row})")


def main():
    """Main function to orchestrate the data fetching and writing."""
    print("Starting Multi-Asset ATR Tracker...")
    print(f"Total Assets: {len(ASSETS)}")
    print(f"Timeframes: {', '.join(TIMEFRAMES)}")
    print()
    
    all_data = []
    
    for asset in ASSETS:
        print(f"Processing {asset}...")
        for timeframe in TIMEFRAMES:
            data = get_latest_data(asset, timeframe)
            if data:
                all_data.append(data)
                print(f"  {timeframe}: Price=${data['Price']:.2f}, RSI={data['RSI']:.2f}")
            else:
                print(f"  {timeframe}: Failed to fetch data")
    
    if all_data:
        print(f"\nWriting {len(all_data)} records to spreadsheet...")
        sheet_name = write_to_spreadsheet(all_data)
        print(f"Done! Data written to sheet: {sheet_name}")
    else:
        print("No data to write.")


if __name__ == '__main__':
    main()
