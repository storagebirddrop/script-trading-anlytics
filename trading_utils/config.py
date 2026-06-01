"""
Configuration constants shared across all scripts.
"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

ASSETS = [
    # Crypto assets (Binance)
    'BTC', 'ETH', 'SOL', 'XLM', 'REZ', 'RSR', 'NEAR', 'RENDER', 'ONDO', 'ACH', 'BNB', 'XRP',
    # NASDAQ stocks (Yahoo Finance)
    'MSTR', 'XXI', 'RIOT', 'MARA', 'IREN', 'BMNR', 'HUT', 'WULF', 'HIVE', 'CLSK', 'SLNH',
    # LSE ETFs (Yahoo Finance with .L suffix)
    'MSTY', 'YMST', 'MARY', 'RIOY', 'IREY', 'BMNY'
]

TIMEFRAMES = ['1d', '1w']

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

# Manual data — update from TradingView / Birdeye
# Format: {asset: {timeframe: {price, ema21, atr, rsi}}}
MANUAL_DATA = {}

# Indicator parameters
EMA_PERIOD = 21
ATR_PERIOD = 14
RSI_PERIOD = 14
Z_SCORE_PERIOD = 20

# File paths (absolute, anchored to project root)
SPREADSHEET_PATH = str(_PROJECT_ROOT / 'ATR_Tracker_Dashboard.xlsx')
MASTER_CSV_PATH = str(_PROJECT_ROOT / 'data' / 'master.csv')
HISTORY_CSV_PATH = str(_PROJECT_ROOT / 'data' / 'history.csv')
DASHBOARD_JSON_PATH = str(_PROJECT_ROOT / 'data' / 'dashboard.json')
