"""
Technical indicator calculations.

Fix C1: ATR and RSI use Wilder's smoothing (com=period-1, alpha=1/period),
not standard EMA smoothing (span=period, alpha=2/(period+1)).
Fix H2: ATR_Distance guards against ATR=0 to prevent inf/-inf values.
"""

import pandas as pd
import numpy as np

from .config import EMA_PERIOD, ATR_PERIOD, RSI_PERIOD, Z_SCORE_PERIOD


def calculate_ema(df, period=EMA_PERIOD):
    """Calculate Exponential Moving Average (standard alpha = 2/(period+1))."""
    return df['close'].ewm(span=period, adjust=False).mean()


def calculate_atr(df, period=ATR_PERIOD):
    """Calculate Average True Range using Wilder's smoothing (alpha = 1/period)."""
    high = df['high']
    low = df['low']
    close = df['close']

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # Wilder's RMA: com = period - 1  →  alpha = 1/(1 + com) = 1/period
    atr = tr.ewm(com=period - 1, adjust=False).mean()

    return atr


def calculate_rsi(df, period=RSI_PERIOD):
    """Calculate RSI using Wilder's smoothing (alpha = 1/period)."""
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(com=period - 1, adjust=False).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_z_score(series, period=Z_SCORE_PERIOD):
    """Calculate rolling Z-score of a series."""
    rolling_mean = series.rolling(window=period).mean()
    rolling_std = series.rolling(window=period).std()
    return (series - rolling_mean) / rolling_std


def calculate_indicators(df):
    """Calculate all technical indicators and derived metrics."""
    df = df.copy()

    df['EMA21'] = calculate_ema(df, EMA_PERIOD)
    df['ATR'] = calculate_atr(df, ATR_PERIOD)
    df['RSI'] = calculate_rsi(df, RSI_PERIOD)
    df['RSI_Z_Score'] = calculate_z_score(df['RSI'], Z_SCORE_PERIOD)

    close = df['close'].squeeze() if isinstance(df['close'], pd.DataFrame) else df['close']
    atr_series = df['ATR'].squeeze() if isinstance(df['ATR'], pd.DataFrame) else df['ATR']
    ema_series = df['EMA21'].squeeze() if isinstance(df['EMA21'], pd.DataFrame) else df['EMA21']

    # Guard against ATR=0 to prevent inf/-inf in ATR_Distance (H2)
    safe_atr = atr_series.replace(0, np.nan)
    df['ATR_Distance'] = ((close - ema_series) / safe_atr).replace([np.inf, -np.inf], np.nan)
    df['Pct_Above_EMA'] = ((close - ema_series) / ema_series) * 100

    return df
