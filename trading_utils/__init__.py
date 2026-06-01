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
)

from .validation import ValidationResult, validate_dataframe

from .indicators import (
    calculate_ema,
    calculate_atr,
    calculate_rsi,
    calculate_z_score,
    calculate_indicators
)

from .data_sources import (
    fetch_ohlcv_binance,
    fetch_ohlcv_yahoo,
    fetch_ohlcv_ccxt,
    fetch_ohlcv_geckoterminal,
    fetch_ohlcv,
    get_manual_data
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
    # Validation
    'ValidationResult',
    'validate_dataframe',
    # Indicators
    'calculate_ema',
    'calculate_atr',
    'calculate_rsi',
    'calculate_z_score',
    'calculate_indicators',
    # Data sources
    'fetch_ohlcv_binance',
    'fetch_ohlcv_yahoo',
    'fetch_ohlcv_ccxt',
    'fetch_ohlcv_geckoterminal',
    'fetch_ohlcv',
    'get_manual_data'
]
