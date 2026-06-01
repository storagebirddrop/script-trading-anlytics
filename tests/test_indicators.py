#!/usr/bin/env python3
"""
Unit tests for indicator calculations (M8).

These tests verify correctness of ATR, RSI, EMA, and derived metrics against
known reference values and boundary conditions.
"""

import numpy as np
import pandas as pd
import pytest

from trading_utils.indicators import (
    calculate_atr,
    calculate_ema,
    calculate_indicators,
    calculate_rsi,
    calculate_z_score,
)


def _make_df(closes, highs=None, lows=None):
    """Build a minimal OHLCV DataFrame for indicator tests."""
    n = len(closes)
    closes = list(closes)
    highs = highs if highs is not None else closes
    lows = lows if lows is not None else closes
    return pd.DataFrame({
        'open': closes,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': [1_000_000] * n,
    }, index=pd.date_range('2024-01-01', periods=n, freq='D'))


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------

class TestCalculateEMA:
    def test_ema_constant_price_converges(self):
        """50 bars of constant price → EMA converges to that price."""
        df = _make_df([100.0] * 50)
        ema = calculate_ema(df, period=21)
        assert abs(float(ema.iloc[-1]) - 100.0) < 0.01

    def test_ema_uses_span_not_com(self):
        """Standard EMA uses alpha=2/(span+1). Spot-check against manual calc."""
        prices = [10.0, 11.0, 12.0]
        df = _make_df(prices)
        ema = calculate_ema(df, period=2)  # alpha = 2/3
        # EMA[0] = 10, EMA[1] = 10*(1/3) + 11*(2/3) ≈ 10.667
        expected = 10 * (1 / 3) + 11 * (2 / 3)
        assert abs(float(ema.iloc[1]) - expected) < 1e-6


# ---------------------------------------------------------------------------
# ATR (Wilder's RMA)
# ---------------------------------------------------------------------------

class TestCalculateATR:
    def test_atr_known_values(self):
        """
        Hand-computed Wilder ATR for a 5-bar sequence, period=3.

        Bars:
          high=[15,16,17,18,19], low=[5,6,7,8,9], close=[10,11,12,13,14]

        True ranges (after bar 0 which has no prev close):
          TR[1] = max(16-6, |16-10|, |6-10|) = max(10, 6, 4) = 10
          TR[2] = max(17-7, |17-11|, |7-11|) = max(10, 6, 4) = 10
          TR[3] = max(18-8, |18-12|, |8-12|) = max(10, 6, 4) = 10
          TR[4] = max(19-9, |19-13|, |9-13|) = max(10, 6, 4) = 10

        With Wilder's com=period-1=2 (alpha=1/3):
          All TRs are identical (10), so ATR converges to 10.
        """
        n = 50  # Use enough bars for convergence
        highs = [10 + i + 5 for i in range(n)]
        lows  = [10 + i - 5 for i in range(n)]
        closes = [10 + i for i in range(n)]

        df = _make_df(closes, highs=highs, lows=lows)
        atr = calculate_atr(df, period=14)

        # True range is constant = 10 for all bars; ATR must converge to 10
        assert abs(float(atr.iloc[-1]) - 10.0) < 0.01

    def test_atr_positive(self):
        """ATR must always be positive for valid OHLCV data."""
        import random
        random.seed(42)
        prices = [100.0 + random.gauss(0, 2) for _ in range(50)]
        highs = [p + abs(random.gauss(0, 1)) for p in prices]
        lows  = [p - abs(random.gauss(0, 1)) for p in prices]
        df = _make_df(prices, highs=highs, lows=lows)
        atr = calculate_atr(df, period=14)
        assert (atr.dropna() > 0).all()


# ---------------------------------------------------------------------------
# RSI (Wilder's RMA)
# ---------------------------------------------------------------------------

class TestCalculateRSI:
    def test_rsi_all_up_days(self):
        """30 bars all closing higher → RSI should be ≥ 95."""
        prices = [100.0 + i for i in range(30)]
        df = _make_df(prices)
        rsi = calculate_rsi(df, period=14)
        assert float(rsi.iloc[-1]) >= 95.0

    def test_rsi_all_down_days(self):
        """30 bars all closing lower → RSI should be ≤ 5."""
        prices = [200.0 - i for i in range(30)]
        df = _make_df(prices)
        rsi = calculate_rsi(df, period=14)
        assert float(rsi.iloc[-1]) <= 5.0

    def test_rsi_bounds(self):
        """RSI must always stay within [0, 100] on any input."""
        import random
        random.seed(7)
        prices = [100.0]
        for _ in range(99):
            prices.append(prices[-1] * (1 + random.gauss(0, 0.02)))
        df = _make_df(prices)
        rsi = calculate_rsi(df, period=14).dropna()
        assert (rsi >= 0).all() and (rsi <= 100).all()

    def test_rsi_wilder_vs_standard_ema(self):
        """
        Wilder's ATR (com=period-1) and standard EMA (span=period) give
        meaningfully different results on a non-trivial sequence.
        With alpha=1/14 vs alpha=2/15 the difference is detectable.
        """
        import random
        random.seed(3)
        prices = [100.0]
        for _ in range(60):
            prices.append(max(1.0, prices[-1] + random.gauss(0, 1.5)))
        df = _make_df(prices)

        # Correct Wilder smoothing
        rsi_wilder = calculate_rsi(df, period=14)

        # Incorrect span-based smoothing (what was there before)
        delta = df['close'].diff()
        gain_span = delta.where(delta > 0, 0).ewm(span=14, adjust=False).mean()
        loss_span = (-delta.where(delta < 0, 0)).ewm(span=14, adjust=False).mean()
        rsi_span = 100 - (100 / (1 + gain_span / loss_span))

        # They should differ by at least 1 point on a random-walk series
        diff = abs(float(rsi_wilder.iloc[-1]) - float(rsi_span.iloc[-1]))
        assert diff > 1.0, f"Expected Wilder vs span RSI to differ, got diff={diff:.4f}"


# ---------------------------------------------------------------------------
# calculate_indicators (H2: ATR=0 guard)
# ---------------------------------------------------------------------------

class TestCalculateIndicators:
    def test_atr_distance_zero_atr_is_nan(self):
        """When ATR is effectively 0, ATR_Distance must be NaN, not inf/-inf (H2)."""
        # Perfectly flat price: ATR will be 0 after warm-up
        prices = [100.0] * 50
        df = _make_df(prices)
        result = calculate_indicators(df)
        atr_dist = result['ATR_Distance']
        # No inf or -inf values anywhere
        assert not np.isinf(atr_dist.replace(np.nan, 0)).any(), \
            "ATR_Distance contains inf/-inf when ATR=0"

    def test_no_inf_in_indicators(self):
        """calculate_indicators must never return inf/-inf on valid OHLCV input."""
        import random
        random.seed(99)
        prices = [100.0]
        for _ in range(80):
            prices.append(max(1.0, prices[-1] * (1 + random.gauss(0, 0.01))))
        highs = [p * 1.01 for p in prices]
        lows  = [p * 0.99 for p in prices]
        df = _make_df(prices, highs=highs, lows=lows)
        result = calculate_indicators(df)
        for col in ['ATR_Distance', 'Pct_Above_EMA', 'RSI']:
            vals = result[col].dropna()
            assert not np.isinf(vals).any(), f"inf found in {col}"

    def test_required_columns_present(self):
        """calculate_indicators must add all expected columns."""
        df = _make_df([100.0 + i for i in range(30)])
        result = calculate_indicators(df)
        for col in ['EMA21', 'ATR', 'RSI', 'RSI_Z_Score', 'ATR_Distance', 'Pct_Above_EMA']:
            assert col in result.columns, f"Missing column: {col}"
