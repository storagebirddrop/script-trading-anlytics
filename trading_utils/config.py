"""
Configuration constants shared across all scripts.
"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

ASSETS = [
    # Crypto assets (Yahoo Finance)
    'BTC', 'ETH', 'SOL', 'XLM', 'REZ', 'RSR', 'NEAR', 'RENDER', 'ONDO', 'ACH', 'BNB', 'XRP',
    'ADA', 'NIGHT',
    'VTHO', 'LINK', 'NEO', 'GAS', 'DRIFT', 'SEI', 'PEAQ', 'AEVO', 'EIGEN', 'W', 'WOO', 'JASMY',
    # NASDAQ stocks (Yahoo Finance)
    'MSTR', 'XXI', 'RIOT', 'MARA', 'IREN', 'BMNR', 'HUT', 'WULF', 'HIVE', 'CLSK', 'SLNH',
    'KEEL', 'BTDR', 'BTBT', 'FUFU',
    # LSE ETFs (Yahoo Finance with .L suffix)
    'MSTY', 'YMST', 'MARY', 'RIOY', 'IREY', 'BMNY',
    # Solana DEX assets (GeckoTerminal)
    'D2X',
    # CEX-listed altcoins (CCXT)
    'SCP',
    # Macro — indices, commodities, forex (Yahoo Finance)
    'SPX', 'NDX', 'RTY', 'DJI',
    'DAX', 'CAC', 'FTSE',
    'NIK', 'HSI', 'ASX',
    'GOLD', 'SILVER', 'OIL', 'NATGAS', 'COPPER', 'WHEAT', 'CORN',
    'DXY', 'EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY',
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
    'RENDER': {'source': 'yahoo', 'symbol': 'RENDER-USD'},
    'ONDO':   {'source': 'yahoo', 'symbol': 'ONDO-USD'},
    'ACH':    {'source': 'yahoo', 'symbol': 'ACH-USD'},
    'BNB':    {'source': 'yahoo', 'symbol': 'BNB-USD'},
    'XRP':    {'source': 'yahoo', 'symbol': 'XRP-USD'},
    'ADA':   {'source': 'yahoo', 'symbol': 'ADA-USD'},
    'NIGHT': {'source': 'yahoo', 'symbol': 'NIGHT-USD'},
    'VTHO':  {'source': 'yahoo', 'symbol': 'VTHO-USD'},
    'LINK':  {'source': 'yahoo', 'symbol': 'LINK-USD'},
    'NEO':   {'source': 'yahoo', 'symbol': 'NEO-USD'},
    'GAS':   {'source': 'yahoo', 'symbol': 'GAS-USD'},
    'DRIFT': {'source': 'yahoo', 'symbol': 'DRIFT-USD'},
    'SEI':   {'source': 'yahoo', 'symbol': 'SEI-USD'},
    'PEAQ':  {'source': 'yahoo', 'symbol': 'PEAQ-USD'},
    'AEVO':  {'source': 'yahoo', 'symbol': 'AEVO-USD'},
    'EIGEN': {'source': 'yahoo', 'symbol': 'EIGEN-USD'},
    'W':     {'source': 'yahoo', 'symbol': 'W-USD'},
    'WOO':   {'source': 'yahoo', 'symbol': 'WOO-USD'},
    'JASMY': {'source': 'yahoo', 'symbol': 'JASMY-USD'},
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
    'KEEL': {'source': 'yahoo', 'symbol': 'KEEL'},
    'BTDR': {'source': 'yahoo', 'symbol': 'BTDR'},
    'BTBT': {'source': 'yahoo', 'symbol': 'BTBT'},
    'FUFU': {'source': 'yahoo', 'symbol': 'FUFU'},
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
    # Macro — US indices (Yahoo Finance)
    'SPX':    {'source': 'yahoo', 'symbol': '^GSPC'},
    'NDX':    {'source': 'yahoo', 'symbol': '^NDX'},
    'RTY':    {'source': 'yahoo', 'symbol': '^RUT'},
    'DJI':    {'source': 'yahoo', 'symbol': '^DJI'},
    # Macro — EU indices (Yahoo Finance)
    'DAX':    {'source': 'yahoo', 'symbol': '^GDAXI'},
    'CAC':    {'source': 'yahoo', 'symbol': '^FCHI'},
    'FTSE':   {'source': 'yahoo', 'symbol': '^FTSE'},
    # Macro — APAC indices (Yahoo Finance)
    'NIK':    {'source': 'yahoo', 'symbol': '^N225'},
    'HSI':    {'source': 'yahoo', 'symbol': '^HSI'},
    'ASX':    {'source': 'yahoo', 'symbol': '^AXJO'},
    # Macro — commodities (Yahoo Finance futures)
    'GOLD':   {'source': 'yahoo', 'symbol': 'GC=F'},
    'SILVER': {'source': 'yahoo', 'symbol': 'SI=F'},
    'OIL':    {'source': 'yahoo', 'symbol': 'CL=F'},
    'NATGAS': {'source': 'yahoo', 'symbol': 'NG=F'},   # named NATGAS; GAS is already a crypto asset
    'COPPER': {'source': 'yahoo', 'symbol': 'HG=F'},
    'WHEAT':  {'source': 'yahoo', 'symbol': 'ZW=F'},
    'CORN':   {'source': 'yahoo', 'symbol': 'ZC=F'},
    # Macro — forex / dollar index (Yahoo Finance)
    'DXY':    {'source': 'yahoo', 'symbol': 'DX-Y.NYB'},
    'EURUSD': {'source': 'yahoo', 'symbol': 'EURUSD=X'},
    'GBPUSD': {'source': 'yahoo', 'symbol': 'GBPUSD=X'},
    'AUDUSD': {'source': 'yahoo', 'symbol': 'AUDUSD=X'},
    'NZDUSD': {'source': 'yahoo', 'symbol': 'NZDUSD=X'},
    'USDCAD': {'source': 'yahoo', 'symbol': 'USDCAD=X'},
    'USDCHF': {'source': 'yahoo', 'symbol': 'USDCHF=X'},
    'USDJPY': {'source': 'yahoo', 'symbol': 'USDJPY=X'},
}

# Manual data — update from TradingView / Birdeye
# Format: {asset: {timeframe: {price, ema21, atr, rsi}}}
MANUAL_DATA = {}

# Macro assets set — used by dashboard to separate these from the trading portfolio
MACRO_ASSETS = {
    'SPX', 'NDX', 'RTY', 'DJI',
    'DAX', 'CAC', 'FTSE',
    'NIK', 'HSI', 'ASX',
    'GOLD', 'SILVER', 'OIL', 'NATGAS', 'COPPER', 'WHEAT', 'CORN',
    'DXY', 'EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY',
}

# Indicator parameters
EMA_PERIOD = 21
ATR_PERIOD = 14
RSI_PERIOD = 14
ADX_PERIOD = 14
BB_PERIOD  = 20
BB_STD     = 2.0
Z_SCORE_PERIOD = 20

# Volume Profile parameters
VP_LOOKBACK_BARS        = 90   # daily lookback (~4 months)
VP_LOOKBACK_BARS_WEEKLY = 52   # weekly lookback (~1 year)
VP_N_BUCKETS            = 24   # price distribution buckets

# CoinGecko IDs for market cap / rank lookups (crypto only; None = not listed)
COINGECKO_IDS = {
    'BTC':    'bitcoin',
    'ETH':    'ethereum',
    'SOL':    'solana',
    'XLM':    'stellar',
    'REZ':    'renzo-protocol',
    'RSR':    'reserve-rights-token',
    'NEAR':   'near',
    'RENDER': 'render-token',
    'ONDO':   'ondo-finance',
    'ACH':    'alchemy-pay',
    'BNB':    'binancecoin',
    'XRP':    'ripple',
    'ADA':    'cardano',
    'NIGHT':  'midnight-3',
    'VTHO':   'vethor-token',
    'LINK':   'chainlink',
    'NEO':    'neo',
    'GAS':    'gas',
    'DRIFT':  'drift-protocol',
    'SEI':    'sei-network',
    'PEAQ':   'peaq',
    'AEVO':   'aevo',
    'EIGEN':  'eigenlayer',
    'W':      'wormhole',  # Yahoo Finance W-USD = Wormhole; distinct from W (Wayfair NASDAQ)
    'WOO':    'woo-network',
    'JASMY':  'jasmycoin',
    'D2X':    'd2',
    'SCP':    'siaprime-coin',
}

# File paths (absolute, anchored to project root)
SPREADSHEET_PATH = str(_PROJECT_ROOT / 'ATR_Tracker_Dashboard.xlsx')
MASTER_CSV_PATH = str(_PROJECT_ROOT / 'data' / 'master.csv')
HISTORY_CSV_PATH = str(_PROJECT_ROOT / 'data' / 'history.csv')
DASHBOARD_JSON_PATH = str(_PROJECT_ROOT / 'data' / 'dashboard.json')
CHART_HISTORY_JSON_PATH = str(_PROJECT_ROOT / 'data' / 'chart_history.json')
METADATA_JSON_PATH = str(_PROJECT_ROOT / 'data' / 'metadata.json')
MARKET_CAPS_JSON_PATH = str(_PROJECT_ROOT / 'data' / 'market_caps.json')
BTC_SIGNALS_JSON_PATH = str(_PROJECT_ROOT / 'data' / 'btc_signals.json')
