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
    'MSTY', 'YMST', 'MARY', 'RIOY', 'IREY', 'BMNY'
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
    'RENDER': {'source': 'binance', 'symbol': 'RENDER/USDT'},
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
}

# Manual data configuration - update these values from TradingView or Birdeye
# Format: {asset: {timeframe: {price, ema21, atr, rsi}}}
MANUAL_DATA = {}

# Indicator parameters
EMA_PERIOD = 21
ATR_PERIOD = 14
RSI_PERIOD = 14
Z_SCORE_PERIOD = 20

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
    """Calculate Relative Strength Index using Wilder's smoothing."""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(span=period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=period, adjust=False).mean()
    
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
    
    # Calculate indicators
    df['EMA21'] = calculate_ema(df, EMA_PERIOD)
    df['ATR'] = calculate_atr(df, ATR_PERIOD)
    df['RSI'] = calculate_rsi(df, RSI_PERIOD)
    df['RSI_Z_Score'] = calculate_z_score(df['RSI'], Z_SCORE_PERIOD)
    
    # Calculate derived metrics
    close = df['close'].squeeze() if isinstance(df['close'], pd.DataFrame) else df['close']
    atr_series = df['ATR'].squeeze() if isinstance(df['ATR'], pd.DataFrame) else df['ATR']
    ema_series = df['EMA21'].squeeze() if isinstance(df['EMA21'], pd.DataFrame) else df['EMA21']
    
    df['ATR_Distance'] = (close - ema_series) / atr_series
    df['Pct_Above_EMA'] = ((close - ema_series) / ema_series) * 100
    
    return df

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
    
    try:
        data = yf.download(symbol, interval=interval, progress=False)
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
    atr_distance = (data['price'] - data['ema21']) / data['atr']  # Corrected Formula
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

def get_data(asset, timeframe):
    """Fetch and calculate indicators for current data."""
    config = ASSET_CONFIG.get(asset)
    if not config:
        print(f"Configuration not found for {asset}")
        return None
    
    source = config['source']
    symbol = config['symbol']
    
    if source == 'manual':
        return get_manual_data(asset, timeframe)
    
    df = fetch_ohlcv(source, symbol, timeframe)
    if df is None or df.empty:
        return None
    
    df = calculate_indicators(df)
    
    # Get the latest row
    latest_row = df.iloc[-1]
    
    return {
        'Date': df.index[-1].strftime('%Y-%m-%d') if hasattr(df.index[-1], 'strftime') else str(df.index[-1]),
        'Asset': asset,
        'Price': float(latest_row['close']),
        'EMA21': float(latest_row['EMA21']),
        'ATR': float(latest_row['ATR']),
        'RSI': float(latest_row['RSI']),
        'RSI_Z_Score': float(latest_row['RSI_Z_Score']),
        'ATR_Distance': float(latest_row['ATR_Distance']),
        'Pct_Above_EMA': float(latest_row['Pct_Above_EMA']),
        'Timeframe': timeframe
    }

def main():
    """Main execution function."""
    all_data = []
    
    print(f"Fetching data for {len(ASSETS)} assets across {len(TIMEFRAMES)} timeframes...")
    
    for asset in ASSETS:
        for timeframe in TIMEFRAMES:
            print(f"Processing {asset} ({timeframe})...")
            data = get_data(asset, timeframe)
            if data:
                all_data.append(data)
    
    # Save to master CSV
    if all_data:
        df = pd.DataFrame(all_data)
        df.to_csv(MASTER_CSV_PATH, index=False)
        print(f"Data saved to {MASTER_CSV_PATH}")
        print(f"Total records: {len(df)}")
    
    return all_data

if __name__ == "__main__":
    main()