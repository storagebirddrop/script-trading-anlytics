"""
Configuration constants shared across all scripts.
"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

ASSETS = [
    # Crypto assets (Yahoo Finance)
    'BTC', 'ETH', 'SOL', 'XLM', 'REZ', 'RSR', 'NEAR', 'RENDER', 'ONDO', 'ACH', 'BNB', 'XRP',
    'ADA', 'NIGHT',
    # NASDAQ stocks (Yahoo Finance)
    'MSTR', 'XXI', 'RIOT', 'MARA', 'IREN', 'BMNR', 'HUT', 'WULF', 'HIVE', 'CLSK', 'SLNH',
    # LSE ETFs (Yahoo Finance with .L suffix)
    'MSTY', 'YMST', 'MARY', 'RIOY', 'IREY', 'BMNY',
    # Solana DEX assets (GeckoTerminal)
    'D2X',
    # CEX-listed altcoins (CCXT)
    'SCP',
]

TIMEFRAMES = ['1d', '1w']

ASSET_CONFIG = {
    # Crypto assets — Yahoo Finance avoids Binance geo-restrictions on CI runners.
    # REZ, ONDO, RENDER/RNDR may not be available on Yahoo Finance; they will fail
    # gracefully and can be added to MANUAL_DATA if needed.
    'BTC':    {'source': 'yahoo', 'symbol': 'BTC-USD'},
    'ETH':    {'source': 'yahoo', 'symbol': 'ETH-USD'},
    'SOL':    {'source': 'yahoo', 'symbol': 'SOL-USD'},
    'XLM':    {'source': 'yahoo', 'symbol': 'XLM-USD'},
    'REZ':    {'source': 'yahoo', 'symbol': 'REZ-USD'},
    'RSR':    {'source': 'yahoo', 'symbol': 'RSR-USD'},
    'NEAR':   {'source': 'yahoo', 'symbol': 'NEAR-USD'},
    'RENDER': {'source': 'yahoo', 'symbol': 'RNDR-USD'},
    'ONDO':   {'source': 'yahoo', 'symbol': 'ONDO-USD'},
    'ACH':    {'source': 'yahoo', 'symbol': 'ACH-USD'},
    'BNB':    {'source': 'yahoo', 'symbol': 'BNB-USD'},
    'XRP':    {'source': 'yahoo', 'symbol': 'XRP-USD'},
    'ADA':   {'source': 'yahoo', 'symbol': 'ADA-USD'},
    'NIGHT': {'source': 'yahoo', 'symbol': 'NIGHT-USD'},
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
    # Solana DEX assets (GeckoTerminal) — pool address of most liquid pair
    'D2X': {'source': 'geckoterminal', 'network': 'solana', 'pool': '7cftYyBzNWFWB6JDa2wKZZqjZMZXMhtLWpUzG4xbDezf'},  # Orca D2X/SOL
    # CEX-listed altcoins (CCXT) — ScPrime listed on CoinEx with full history
    'SCP': {'source': 'ccxt', 'exchange': 'coinex', 'symbol': 'SCP/USDT'},
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
METADATA_JSON_PATH = str(_PROJECT_ROOT / 'data' / 'metadata.json')
