"""
Technical indicator calculations.

All three indicators (EMA, ATR, RSI) use SMA-seeded initialisation to match
TradingView's behaviour exactly:
  - EMA:  seed = SMA(close, period) at bar `period-1`, then standard EMA
  - ATR:  seed = SMA(TR,    period) at bar `period-1`, then Wilder's RMA
  - RSI:  seed = SMA(gain/loss, period) at bar `period`, then Wilder's RMA

Without SMA seeding, pandas ewm() assigns full exponential weight from bar 0,
causing ATR/EMA to diverge significantly on short-history assets (e.g. new ETFs
with only 20-30 weekly bars).
"""

import numpy as np
import pandas as pd

from .config import EMA_PERIOD, ATR_PERIOD, RSI_PERIOD, Z_SCORE_PERIOD


def calculate_ema(df, period=EMA_PERIOD):
    """EMA with SMA seed — matches TradingView ta.ema()."""
    src = df['close'].to_numpy(dtype=float)
    out = np.full(len(src), np.nan)
    if len(src) < period:
        return pd.Series(out, index=df.index)
    alpha = 2.0 / (period + 1.0)
    out[period - 1] = src[:period].mean()
    for i in range(period, len(src)):
        out[i] = out[i - 1] + alpha * (src[i] - out[i - 1])
    return pd.Series(out, index=df.index)


def calculate_atr(df, period=ATR_PERIOD):
    """ATR (Wilder's RMA) with SMA seed — matches TradingView ta.atr()."""
    high  = df['high'].to_numpy(dtype=float)
    low   = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)

    prev_close = np.empty_like(close)
    prev_close[0] = np.nan
    prev_close[1:] = close[:-1]

    tr = np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low  - prev_close),
    ])
    tr[0] = high[0] - low[0]  # no previous close for first bar

    out = np.full(len(tr), np.nan)
    if len(tr) < period:
        return pd.Series(out, index=df.index)
    out[period - 1] = tr[:period].mean()
    for i in range(period, len(tr)):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return pd.Series(out, index=df.index)


def calculate_rsi(df, period=RSI_PERIOD):
    """RSI with SMA-seeded Wilder's smoothing — matches TradingView ta.rsi()."""
    close = df['close'].to_numpy(dtype=float)
    delta = np.empty_like(close)
    delta[0] = np.nan
    delta[1:] = np.diff(close)

    gain = np.where(delta > 0,  delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    avg_gain = np.full(len(close), np.nan)
    avg_loss = np.full(len(close), np.nan)

    if len(close) <= period:
        return pd.Series(np.full(len(close), np.nan), index=df.index)

    # Seed at index `period`: SMA of the first `period` changes (bars 1..period)
    avg_gain[period] = gain[1:period + 1].mean()
    avg_loss[period] = loss[1:period + 1].mean()
    for i in range(period + 1, len(close)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period

    with np.errstate(divide='ignore', invalid='ignore'):
        rs = np.where(avg_loss == 0, np.inf, avg_gain / avg_loss)
    rsi = np.where(avg_loss == 0, 100.0, 100.0 - 100.0 / (1.0 + rs))
    rsi = np.where(np.isnan(avg_gain), np.nan, rsi)

    return pd.Series(rsi, index=df.index)


def calculate_z_score(series, period=Z_SCORE_PERIOD):
    """Rolling Z-score of a series."""
    rolling_mean = series.rolling(window=period).mean()
    rolling_std  = series.rolling(window=period).std()
    return (series - rolling_mean) / rolling_std


def calculate_indicators(df):
    """Calculate all technical indicators and derived metrics."""
    df = df.copy()

    df['EMA21'] = calculate_ema(df, EMA_PERIOD)
    df['ATR']   = calculate_atr(df, ATR_PERIOD)
    df['RSI']   = calculate_rsi(df, RSI_PERIOD)
    df['RSI_Z_Score'] = calculate_z_score(df['RSI'], Z_SCORE_PERIOD)

    close      = df['close'].squeeze()  if isinstance(df['close'],  pd.DataFrame) else df['close']
    atr_series = df['ATR'].squeeze()    if isinstance(df['ATR'],    pd.DataFrame) else df['ATR']
    ema_series = df['EMA21'].squeeze()  if isinstance(df['EMA21'],  pd.DataFrame) else df['EMA21']

    safe_atr = atr_series.replace(0, np.nan)
    df['ATR_Distance'] = ((close - ema_series) / safe_atr).replace([np.inf, -np.inf], np.nan)
    df['Pct_Above_EMA'] = ((close - ema_series) / ema_series) * 100

    return df
