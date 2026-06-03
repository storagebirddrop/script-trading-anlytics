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

from .config import EMA_PERIOD, ATR_PERIOD, RSI_PERIOD, ADX_PERIOD, Z_SCORE_PERIOD, VP_LOOKBACK_BARS, VP_N_BUCKETS


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


def calculate_adx(df, period=ADX_PERIOD):
    """ADX (Wilder's RMA, SMA-seeded) — trend strength 0–100, direction-neutral."""
    high  = df['high'].to_numpy(dtype=float)
    low   = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    n = len(high)

    out = np.full(n, np.nan)
    if n < 2 * period - 1:
        return pd.Series(out, index=df.index)

    prev_close = np.empty_like(close)
    prev_close[0] = np.nan
    prev_close[1:] = close[:-1]
    tr = np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low - prev_close),
    ])
    tr[0] = high[0] - low[0]

    up_move   = np.zeros(n)
    down_move = np.zeros(n)
    for i in range(1, n):
        um = high[i] - high[i - 1]
        dm = low[i - 1] - low[i]
        up_move[i]   = um if (um > dm and um > 0.0) else 0.0
        down_move[i] = dm if (dm > um and dm > 0.0) else 0.0

    def _rma(arr):
        s = np.full(n, np.nan)
        s[period - 1] = arr[:period].mean()
        for i in range(period, n):
            s[i] = (s[i - 1] * (period - 1) + arr[i]) / period
        return s

    atr_s = _rma(tr)
    pdm_s = _rma(up_move)
    ndm_s = _rma(down_move)

    with np.errstate(divide='ignore', invalid='ignore'):
        pdi     = np.where(atr_s > 0, 100.0 * pdm_s / atr_s, np.nan)
        ndi     = np.where(atr_s > 0, 100.0 * ndm_s / atr_s, np.nan)
        di_sum  = pdi + ndi
        di_diff = np.abs(pdi - ndi)
        dx      = np.where(di_sum > 0, 100.0 * di_diff / di_sum, np.nan)

    # ADX = RMA of DX; seed spans DX[period-1 .. 2*(period-1)]
    seed_idx = 2 * (period - 1)
    if seed_idx >= n:
        return pd.Series(out, index=df.index)

    dx_window = dx[period - 1:seed_idx + 1]
    dx_valid  = dx_window[~np.isnan(dx_window)]
    out[seed_idx] = float(dx_valid.mean()) if len(dx_valid) > 0 else np.nan
    for i in range(seed_idx + 1, n):
        out[i] = (out[i - 1] * (period - 1) + dx[i]) / period

    return pd.Series(out, index=df.index)


def calculate_volume_profile(df, lookback_bars=VP_LOOKBACK_BARS, n_buckets=VP_N_BUCKETS):
    """
    Compute a fixed-lookback Volume Profile from OHLCV history.

    Uses the last `lookback_bars` rows. Volume is distributed uniformly across
    each bar's high-low range (standard daily-bar approximation). Returns None
    when volume data is absent or insufficient.

    Returns a dict with keys:
      poc, vah, val, position, dist_from_poc, buckets
    where buckets is a list of n_buckets dicts {p, v, is_poc, in_va}.
    """
    required = {'high', 'low', 'close', 'volume'}
    if not required.issubset(df.columns):
        return None

    tail = df.tail(lookback_bars).copy()
    tail['volume'] = pd.to_numeric(tail['volume'], errors='coerce').fillna(0.0)

    if len(tail) < 20 or tail['volume'].sum() == 0:
        return None

    price_low  = float(tail['low'].min())
    price_high = float(tail['high'].max())
    if price_high <= price_low:
        return None

    bucket_size = (price_high - price_low) / n_buckets
    buckets = np.zeros(n_buckets)

    for _, row in tail.iterrows():
        vol      = float(row['volume'])
        if vol <= 0:
            continue
        bar_low  = float(row['low'])
        bar_high = float(row['high'])
        bar_range = bar_high - bar_low

        if bar_range <= 0:
            # Doji — assign all volume to the nearest bucket
            idx = min(int((bar_low - price_low) / bucket_size), n_buckets - 1)
            buckets[idx] += vol
        else:
            for b in range(n_buckets):
                b_low  = price_low + b * bucket_size
                b_high = b_low + bucket_size
                overlap = min(bar_high, b_high) - max(bar_low, b_low)
                if overlap > 0:
                    buckets[b] += vol * overlap / bar_range

    if buckets.sum() == 0:
        return None

    poc_idx   = int(np.argmax(buckets))
    poc_price = price_low + (poc_idx + 0.5) * bucket_size

    # Value Area: expand from POC until ≥ 70% of volume is enclosed
    target    = buckets.sum() * 0.70
    va_set    = {poc_idx}
    accumulated = buckets[poc_idx]
    lo_idx, hi_idx = poc_idx, poc_idx

    while accumulated < target:
        can_lo = lo_idx - 1 if lo_idx > 0 else None
        can_hi = hi_idx + 1 if hi_idx < n_buckets - 1 else None
        vol_lo = buckets[can_lo] if can_lo is not None else -1.0
        vol_hi = buckets[can_hi] if can_hi is not None else -1.0
        if vol_lo < 0 and vol_hi < 0:
            break
        if vol_lo >= vol_hi:
            lo_idx = can_lo
            va_set.add(lo_idx)
            accumulated += vol_lo
        else:
            hi_idx = can_hi
            va_set.add(hi_idx)
            accumulated += vol_hi

    val_price = price_low + lo_idx * bucket_size
    vah_price = price_low + (hi_idx + 1) * bucket_size

    current_price = float(tail['close'].iloc[-1])
    if current_price > vah_price:
        position = 'above_vah'
    elif current_price < val_price:
        position = 'below_val'
    elif abs(current_price - poc_price) <= bucket_size * 1.5:
        position = 'at_poc'
    else:
        position = 'in_value_area'

    atr_col = tail['ATR'] if 'ATR' in tail.columns else None
    current_atr = float(atr_col.iloc[-1]) if atr_col is not None and pd.notna(atr_col.iloc[-1]) else None
    dist_from_poc = round((current_price - poc_price) / current_atr, 4) if current_atr and current_atr > 0 else None

    bucket_list = [
        {
            'p':      round(price_low + (i + 0.5) * bucket_size, 6),
            'v':      round(float(buckets[i]), 2),
            'is_poc': i == poc_idx,
            'in_va':  i in va_set,
        }
        for i in range(n_buckets)
    ]

    return {
        'poc':          round(poc_price, 6),
        'vah':          round(vah_price, 6),
        'val':          round(val_price, 6),
        'position':     position,
        'dist_from_poc':dist_from_poc,
        'buckets':      bucket_list,
    }


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

    if 'high' in df.columns and 'low' in df.columns:
        df['ADX'] = calculate_adx(df, ADX_PERIOD)

    return df
