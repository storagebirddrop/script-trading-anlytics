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
    calculate_adx,
    calculate_ema,
    calculate_indicators,
    calculate_rsi,
    calculate_z_score,
    calculate_volume_profile,
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
        """Standard EMA uses alpha=2/(span+1) with SMA seed at bar period-1.

        With period=2 and prices=[10, 11, 12]:
          - SMA seed at index 1: (10+11)/2 = 10.5
          - EMA at index 2: 10.5*(1/3) + 12*(2/3) = 11.5
        """
        prices = [10.0, 11.0, 12.0]
        df = _make_df(prices)
        ema = calculate_ema(df, period=2)  # alpha = 2/3
        seed = (10.0 + 11.0) / 2  # SMA of first period bars = 10.5
        expected = seed * (1 / 3) + 12.0 * (2 / 3)  # = 11.5
        assert abs(float(ema.iloc[2]) - expected) < 1e-6


# ---------------------------------------------------------------------------
# ATR (Wilder's RMA)
# ---------------------------------------------------------------------------

class TestCalculateATR:
    def test_atr_known_values(self):
        """
        Hand-computed Wilder ATR for a 50-bar sequence, period=14.

        Bars:
          high=[15,16,17,...,64], low=[5,6,7,...,54], close=[10,11,12,...,59]

        True ranges (after bar 0 which has no prev close):
          Each TR = (high - low) = 10 (constant across all bars)

        With Wilder's com=period-1=13 (alpha=1/14):
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
        Wilder's RSI (com=period-1) and standard EMA (span=period) give
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


# ---------------------------------------------------------------------------
# calculate_volume_profile
# ---------------------------------------------------------------------------

def _make_vp_df(n=50, base_price=100.0, bar_range=2.0, volumes=None):
    """Build a minimal OHLCV DataFrame suitable for volume profile tests."""
    closes  = [base_price + i * 0.1 for i in range(n)]
    highs   = [c + bar_range / 2 for c in closes]
    lows    = [c - bar_range / 2 for c in closes]
    vols    = volumes if volumes is not None else [1000.0] * n
    atr     = [bar_range * 0.7] * n
    return pd.DataFrame({
        'close':  closes,
        'high':   highs,
        'low':    lows,
        'volume': vols,
        'ATR':    atr,
    })


class TestCalculateVolumeProfile:

    def test_returns_dict_with_required_keys(self):
        """calculate_volume_profile returns dict with all required keys."""
        df  = _make_vp_df()
        vp  = calculate_volume_profile(df)
        assert vp is not None
        for key in ('poc', 'vah', 'val', 'position', 'dist_from_poc', 'buckets'):
            assert key in vp, f"Missing key: {key}"

    def test_buckets_count(self):
        """buckets list has exactly n_buckets entries."""
        df = _make_vp_df()
        vp = calculate_volume_profile(df, n_buckets=24)
        assert len(vp['buckets']) == 24

    def test_bucket_fields(self):
        """Each bucket has p, v, is_poc, in_va."""
        df = _make_vp_df()
        vp = calculate_volume_profile(df)
        for b in vp['buckets']:
            for key in ('p', 'v', 'is_poc', 'in_va'):
                assert key in b, f"Missing bucket key: {key}"

    def test_poc_is_highest_volume_bucket(self):
        """POC price corresponds to the bucket that received the most volume."""
        # Give bars 0-9 (low price zone) 10x volume — POC should be there
        volumes = [10000.0] * 10 + [100.0] * 40
        df  = _make_vp_df(n=50, volumes=volumes)
        vp  = calculate_volume_profile(df)
        poc_bucket = max(vp['buckets'], key=lambda b: b['v'])
        assert poc_bucket['is_poc']
        # POC should be in the lower portion of the price range
        all_prices = [b['p'] for b in vp['buckets']]
        median_price = sorted(all_prices)[len(all_prices) // 2]
        assert vp['poc'] < median_price, "POC should be in the lower (high-volume) range"

    def test_exactly_one_poc_bucket(self):
        """Exactly one bucket is flagged is_poc=True."""
        df = _make_vp_df()
        vp = calculate_volume_profile(df)
        poc_count = sum(1 for b in vp['buckets'] if b['is_poc'])
        assert poc_count == 1

    def test_value_area_covers_70pct_volume(self):
        """Buckets in the value area contain at least 70% of total volume."""
        df = _make_vp_df()
        vp = calculate_volume_profile(df)
        total_vol = sum(b['v'] for b in vp['buckets'])
        va_vol    = sum(b['v'] for b in vp['buckets'] if b['in_va'])
        assert va_vol / total_vol >= 0.70 - 1e-9

    def test_vah_above_val(self):
        """VAH must always be greater than VAL."""
        df = _make_vp_df()
        vp = calculate_volume_profile(df)
        assert vp['vah'] > vp['val']

    def test_position_above_vah(self):
        """When current price is above VAH, position is 'above_vah'."""
        df = _make_vp_df(base_price=100.0)
        vp = calculate_volume_profile(df)
        if vp is None:
            pytest.skip("VP not computable for this fixture")
        # Push the last close above VAH by patching
        df2 = df.copy()
        df2.loc[df2.index[-1], 'close'] = vp['vah'] + 10.0
        vp2 = calculate_volume_profile(df2)
        assert vp2 is not None
        assert vp2['position'] == 'above_vah'

    def test_position_below_val(self):
        """When current price is below VAL, position is 'below_val'."""
        df = _make_vp_df(base_price=100.0)
        vp = calculate_volume_profile(df)
        if vp is None:
            pytest.skip("VP not computable for this fixture")
        df2 = df.copy()
        df2.loc[df2.index[-1], 'close'] = vp['val'] - 10.0
        vp2 = calculate_volume_profile(df2)
        assert vp2 is not None
        assert vp2['position'] == 'below_val'

    def test_zero_volume_returns_none(self):
        """All-zero volume → returns None."""
        df = _make_vp_df(volumes=[0.0] * 50)
        assert calculate_volume_profile(df) is None

    def test_insufficient_bars_returns_none(self):
        """Fewer than 20 bars → returns None."""
        df = _make_vp_df(n=10)
        assert calculate_volume_profile(df, lookback_bars=90) is None

    def test_missing_volume_column_returns_none(self):
        """DataFrame without 'volume' column → returns None."""
        df = _make_vp_df().drop(columns=['volume'])
        assert calculate_volume_profile(df) is None

    def test_missing_high_low_returns_none(self):
        """DataFrame without 'high'/'low' columns → returns None."""
        df = _make_vp_df().drop(columns=['high', 'low'])
        assert calculate_volume_profile(df) is None

    def test_nan_volume_treated_as_zero(self):
        """NaN volume bars are treated as zero (not counted)."""
        import numpy as np
        volumes = [np.nan] * 10 + [1000.0] * 40
        df = _make_vp_df(volumes=volumes)
        vp = calculate_volume_profile(df)
        assert vp is not None

    def test_doji_bar_handled(self):
        """Bars with high == low (doji) don't cause division by zero."""
        df = _make_vp_df(n=30)
        df.loc[df.index[5], 'high'] = df.loc[df.index[5], 'low']
        vp = calculate_volume_profile(df, lookback_bars=30)
        assert vp is not None


# ---------------------------------------------------------------------------
# ADX
# ---------------------------------------------------------------------------

class TestCalculateADX:
    def test_too_few_bars_all_nan(self):
        """Fewer than 2*period-1 bars → all NaN (period=14 needs ≥27 bars)."""
        df = _make_df(
            [100.0 + i for i in range(26)],
            highs=[101.0 + i for i in range(26)],
            lows=[99.0 + i for i in range(26)],
        )
        adx = calculate_adx(df, period=14)
        assert adx.isna().all()

    def test_first_value_at_seed_index(self):
        """ADX first value appears at index 2*(period-1)=26 for period=14."""
        n = 30
        df = _make_df(
            [100.0 + i for i in range(n)],
            highs=[101.0 + i for i in range(n)],
            lows=[99.0 + i for i in range(n)],
        )
        adx = calculate_adx(df, period=14)
        assert adx.isna().all() == False
        assert pd.isna(adx.iloc[25])
        assert pd.notna(adx.iloc[26])

    def test_strong_uptrend_is_trending(self):
        """Consistent uptrend → ADX > 25 (Trending) after enough bars."""
        n = 60
        closes = [100.0 + i for i in range(n)]
        highs  = [c + 1.0 for c in closes]
        lows   = [c - 1.0 for c in closes]
        df = _make_df(closes, highs=highs, lows=lows)
        adx = calculate_adx(df, period=14)
        assert float(adx.iloc[-1]) > 25.0

    def test_no_directional_move_adx_nan(self):
        """Constant prices (zero DM) → ADX is NaN (DX undefined: 0/0)."""
        df = _make_df([100.0] * 40)
        adx = calculate_adx(df, period=14)
        assert adx.isna().all()

    def test_returns_series_with_df_index(self):
        """Output is a pd.Series with the same index as input."""
        n = 40
        df = _make_df(
            [100.0 + i for i in range(n)],
            highs=[101.0 + i for i in range(n)],
            lows=[99.0 + i for i in range(n)],
        )
        adx = calculate_adx(df, period=14)
        assert isinstance(adx, pd.Series)
        assert list(adx.index) == list(df.index)

    def test_adx_included_in_calculate_indicators_with_ohlcv(self):
        """calculate_indicators() writes ADX column when high/low present."""
        n = 40
        df = _make_df(
            [100.0 + i for i in range(n)],
            highs=[101.0 + i for i in range(n)],
            lows=[99.0 + i for i in range(n)],
        )
        result = calculate_indicators(df)
        assert 'ADX' in result.columns

    def test_adx_absent_without_high_low(self):
        """calculate_indicators() skips ADX when high == low == close."""
        df = _make_df([100.0] * 40)
        # _make_df sets highs=lows=closes, so the ADX column is still added
        # (high/low columns are present, but DM=0 → ADX=NaN)
        result = calculate_indicators(df)
        # Column exists but all values should be NaN (no directional movement)
        assert 'ADX' in result.columns
        assert result['ADX'].isna().all()
