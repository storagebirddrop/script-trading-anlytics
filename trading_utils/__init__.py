"""
Trading Utilities Module
Shared utilities for the crypto tracker project.
"""

from .config import (
    ASSETS,
    ASSET_CONFIG,
    MANUAL_DATA,
    TIMEFRAMES,
    SPREADSHEET_PATH,
    MASTER_CSV_PATH,
    HISTORY_CSV_PATH,
    DASHBOARD_JSON_PATH,
    CHART_HISTORY_JSON_PATH,
    METADATA_JSON_PATH,
    EMA_PERIOD,
    ATR_PERIOD,
    RSI_PERIOD,
    Z_SCORE_PERIOD,
    VP_LOOKBACK_BARS,
    VP_LOOKBACK_BARS_WEEKLY,
    VP_N_BUCKETS,
    COINGECKO_IDS,
    MARKET_CAPS_JSON_PATH,
    MACRO_ASSETS,
)

from .validation import ValidationResult, validate_dataframe

from .indicators import (
    calculate_ema,
    calculate_atr,
    calculate_rsi,
    calculate_z_score,
    calculate_indicators,
    calculate_volume_profile,
)

from .data_sources import (
    fetch_ohlcv_binance,
    fetch_ohlcv_yahoo,
    fetch_ohlcv_ccxt,
    fetch_ohlcv_geckoterminal,
    fetch_ohlcv,
    get_manual_data,
    fetch_market_caps,
)

__all__ = [
    # Configuration
    'ASSETS',
    'ASSET_CONFIG',
    'MANUAL_DATA',
    'TIMEFRAMES',
    'SPREADSHEET_PATH',
    'MASTER_CSV_PATH',
    'HISTORY_CSV_PATH',
    'DASHBOARD_JSON_PATH',
    'CHART_HISTORY_JSON_PATH',
    'METADATA_JSON_PATH',
    'EMA_PERIOD',
    'ATR_PERIOD',
    'RSI_PERIOD',
    'Z_SCORE_PERIOD',
    'VP_LOOKBACK_BARS',
    'VP_LOOKBACK_BARS_WEEKLY',
    'VP_N_BUCKETS',
    'COINGECKO_IDS',
    'MARKET_CAPS_JSON_PATH',
    'MACRO_ASSETS',
    # Validation
    'ValidationResult',
    'validate_dataframe',
    # Indicators
    'calculate_ema',
    'calculate_atr',
    'calculate_rsi',
    'calculate_z_score',
    'calculate_indicators',
    'calculate_volume_profile',
    # Data sources
    'fetch_ohlcv_binance',
    'fetch_ohlcv_yahoo',
    'fetch_ohlcv_ccxt',
    'fetch_ohlcv_geckoterminal',
    'fetch_ohlcv',
    'get_manual_data',
    'fetch_market_caps',
]
