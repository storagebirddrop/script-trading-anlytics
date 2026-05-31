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