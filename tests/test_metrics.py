#!/usr/bin/env python3
"""
Unit tests for metrics calculation.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
import json
import os
import calculate_metrics as _cm
from calculate_metrics import (
    classify_regime,
    calculate_historical_metrics,
    calculate_current_metrics,
    generate_dashboard_json,
    generate_chart_history,
    fetch_fear_greed,
    fetch_binance_futures,
    fetch_btc_dominance,
    calculate_altseason_index,
    fetch_bgeometrics_onchain,
    fetch_bitbo_onchain,
    fetch_coinmetrics_v4_onchain,
    fetch_blockchair_cdd,
    _load_onchain_cache,
    _save_onchain_cache,
)


@pytest.fixture
def sample_history_df():
    """Create a sample history DataFrame for testing."""
    return pd.DataFrame({
        'Date': ['2026-06-01', '2026-06-02', '2026-06-03', '2026-06-04', '2026-06-05',
                 '2026-06-01', '2026-06-02', '2026-06-03', '2026-06-04', '2026-06-05'],
        'Asset': ['BTC', 'BTC', 'BTC', 'BTC', 'BTC',
                  'ETH', 'ETH', 'ETH', 'ETH', 'ETH'],
        'Price': [65000.0, 65500.0, 66000.0, 64500.0, 64000.0,
                  3500.0, 3550.0, 3600.0, 3450.0, 3400.0],
        'EMA21': [64000.0, 64200.0, 64400.0, 63800.0, 63600.0,
                  3450.0, 3460.0, 3470.0, 3440.0, 3430.0],
        'ATR': [1000.0, 1000.0, 1000.0, 1000.0, 1000.0,
                50.0, 50.0, 50.0, 50.0, 50.0],
        'RSI': [50.0, 55.0, 60.0, 45.0, 40.0,
                50.0, 55.0, 60.0, 45.0, 40.0],
        'RSI_Z_Score': [0.0, 0.5, 1.0, -0.5, -1.0,
                       0.0, 0.5, 1.0, -0.5, -1.0],
        'ATR_Distance': [1.0, 1.3, 1.6, 0.7, 0.4,
                         1.0, 1.8, 2.6, 0.2, -0.6],
        'Pct_Above_EMA': [1.56, 2.02, 2.48, 1.10, 0.63,
                          1.45, 2.60, 3.75, 0.29, -0.87],
        'Timeframe': ['1d', '1d', '1d', '1d', '1d',
                      '1d', '1d', '1d', '1d', '1d']
    })


class TestClassifyRegime:
    """Test regime classification."""
    
    def test_capitulation_regime(self):
        """Test ATR Distance < -4 classifies as Capitulation."""
        assert classify_regime(-4.1) == 'Capitulation'
        assert classify_regime(-5.0) == 'Capitulation'
        assert classify_regime(-10.0) == 'Capitulation'

    def test_accumulation_regime(self):
        """Test -4 <= ATR Distance < -2 classifies as Accumulation."""
        assert classify_regime(-2.5) == 'Accumulation'
        assert classify_regime(-3.0) == 'Accumulation'
        assert classify_regime(-4.0) == 'Accumulation'

    def test_trend_regime_lower_bound(self):
        """Test ATR Distance = -2 classifies as Trend."""
        assert classify_regime(-2.0) == 'Trend'

    def test_trend_regime_middle(self):
        """Test ATR Distance between -2 and 2 classifies as Trend."""
        assert classify_regime(0.0) == 'Trend'
        assert classify_regime(1.0) == 'Trend'
        assert classify_regime(-1.0) == 'Trend'

    def test_trend_regime_upper_bound(self):
        """Test ATR Distance = 2 classifies as Trend."""
        assert classify_regime(2.0) == 'Trend'

    def test_distribution_regime(self):
        """Test 2 < ATR Distance <= 4 classifies as Distribution."""
        assert classify_regime(2.1) == 'Distribution'
        assert classify_regime(3.0) == 'Distribution'
        assert classify_regime(4.0) == 'Distribution'

    def test_mania_regime(self):
        """Test ATR Distance > 4 classifies as Mania."""
        assert classify_regime(4.1) == 'Mania'
        assert classify_regime(5.0) == 'Mania'
        assert classify_regime(10.0) == 'Mania'

    def test_nan_regime(self):
        """Test NaN ATR Distance classifies as Unknown."""
        assert classify_regime(np.nan) == 'Unknown'
        assert classify_regime(None) == 'Unknown'


class TestCalculateHistoricalMetrics:
    """Test historical metrics calculation."""
    
    def test_calculate_historical_metrics(self, sample_history_df):
        """Test historical metrics are calculated correctly."""
        metrics = calculate_historical_metrics(sample_history_df)
        
        # Check that assets are present
        assert 'BTC' in metrics
        assert 'ETH' in metrics
        
        # Check that timeframes are present
        assert '1d' in metrics['BTC']
        assert '1d' in metrics['ETH']
        
        # Check historical metrics structure
        btc_hist = metrics['BTC']['1d']['historical']
        assert 'atr_max' in btc_hist
        assert 'atr_min' in btc_hist
        assert 'atr_mean' in btc_hist
        assert 'atr_std' in btc_hist
        assert 'atr_percentile_25' in btc_hist
        assert 'atr_percentile_50' in btc_hist
        assert 'atr_percentile_75' in btc_hist
        assert 'atr_percentile_90' in btc_hist
        assert 'sample_size' in btc_hist
        
        # Check sample size
        assert btc_hist['sample_size'] == 5
    
    def test_atr_distance_max_min(self, sample_history_df):
        """Test ATR Distance max and min are calculated correctly."""
        metrics = calculate_historical_metrics(sample_history_df)
        
        btc_hist = metrics['BTC']['1d']['historical']
        assert btc_hist['atr_max'] == 1.6  # Max ATR Distance for BTC
        assert btc_hist['atr_min'] == 0.4  # Min ATR Distance for BTC
    
    def test_empty_dataframe(self):
        """Test handling of empty DataFrame."""
        df = pd.DataFrame({
            'Date': [],
            'Asset': [],
            'Price': [],
            'EMA21': [],
            'ATR': [],
            'RSI': [],
            'RSI_Z_Score': [],
            'ATR_Distance': [],
            'Pct_Above_EMA': [],
            'Timeframe': []
        })
        
        metrics = calculate_historical_metrics(df)
        assert len(metrics) == 0
    
    def test_nan_atr_distance_handling(self):
        """Test handling of NaN ATR Distance values."""
        df = pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-02'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 65500.0],
            'EMA21': [64000.0, 64200.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 55.0],
            'RSI_Z_Score': [0.0, 0.5],
            'ATR_Distance': [1.0, np.nan],
            'Pct_Above_EMA': [1.56, 2.02],
            'Timeframe': ['1d', '1d']
        })
        
        metrics = calculate_historical_metrics(df)
        btc_hist = metrics['BTC']['1d']['historical']
        assert btc_hist['sample_size'] == 1  # Only non-NaN value counted


class TestCalculateCurrentMetrics:
    """Test current metrics calculation."""
    
    def test_calculate_current_metrics(self, sample_history_df):
        """Test current metrics are calculated correctly."""
        metrics = calculate_current_metrics(sample_history_df)
        
        # Check that assets are present
        assert 'BTC' in metrics
        assert 'ETH' in metrics
        
        # Check that timeframes are present
        assert '1d' in metrics['BTC']
        assert '1d' in metrics['ETH']
        
        # Check current metrics structure
        btc_current = metrics['BTC']['1d']['current']
        assert 'date' in btc_current
        assert 'price' in btc_current
        assert 'ema21' in btc_current
        assert 'atr' in btc_current
        assert 'rsi' in btc_current
        assert 'atr_distance' in btc_current
        assert 'regime' in btc_current
        assert 'atr_percentile' in btc_current
    
    def test_latest_record_selected(self, sample_history_df):
        """Test that the latest record is selected for current metrics."""
        metrics = calculate_current_metrics(sample_history_df)
        
        btc_current = metrics['BTC']['1d']['current']
        # The latest date for BTC is 2026-06-05
        assert btc_current['date'] == '2026-06-05'
        assert btc_current['price'] == 64000.0
    
    def test_regime_classification(self, sample_history_df):
        """Test regime is classified correctly based on ATR Distance."""
        metrics = calculate_current_metrics(sample_history_df)
        
        # BTC latest ATR Distance is 0.4, which is Trend
        assert metrics['BTC']['1d']['current']['regime'] == 'Trend'
    
    def test_atr_percentile_calculation(self, sample_history_df):
        """Test ATR Distance percentile is calculated correctly."""
        metrics = calculate_current_metrics(sample_history_df)

        btc_current = metrics['BTC']['1d']['current']
        # BTC ATR Distances: [1.0, 1.3, 1.6, 0.7, 0.4]
        # Latest is 0.4, which is the minimum (0th percentile)
        assert btc_current['atr_percentile'] == 0.0

    def test_price_change_pct_present(self, sample_history_df):
        """price_change_pct field must be present in current snapshot."""
        metrics = calculate_current_metrics(sample_history_df)
        assert 'price_change_pct' in metrics['BTC']['1d']['current']

    def test_price_change_pct_value(self, sample_history_df):
        """price_change_pct is (current - prev) / prev * 100."""
        metrics = calculate_current_metrics(sample_history_df)
        btc_current = metrics['BTC']['1d']['current']
        # BTC prices in order: 65000, 65500, 66000, 64500, 64000
        # latest=64000, prev=64500 → (64000-64500)/64500*100
        expected = (64000.0 - 64500.0) / 64500.0 * 100
        assert btc_current['price_change_pct'] == pytest.approx(expected, rel=1e-6)

    def test_price_change_pct_none_for_single_row(self):
        """price_change_pct is None when only one data point is available."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [1000.0],
            'RSI': [50.0],
            'RSI_Z_Score': [0.0],
            'ATR_Distance': [1.0],
            'Pct_Above_EMA': [1.56],
            'Timeframe': ['1d'],
        })
        metrics = calculate_current_metrics(df)
        assert metrics['BTC']['1d']['current']['price_change_pct'] is None

    def test_staleness_filter_excludes_old_assets(self):
        """Assets whose latest row is >60 days behind the global max are excluded."""
        fresh_dates = ['2026-06-01', '2026-06-02', '2026-06-03']
        stale_dates = ['2026-03-01', '2026-03-02', '2026-03-03']  # 91 days behind

        df = pd.DataFrame({
            'Date': fresh_dates + stale_dates,
            'Asset': ['BTC'] * 3 + ['STALE'] * 3,
            'Price': [65000.0] * 3 + [100.0] * 3,
            'EMA21': [64000.0] * 3 + [99.0] * 3,
            'ATR': [1000.0] * 3 + [2.0] * 3,
            'RSI': [50.0] * 6,
            'RSI_Z_Score': [0.0] * 6,
            'ATR_Distance': [1.0] * 6,
            'Pct_Above_EMA': [1.56] * 6,
            'Timeframe': ['1d'] * 6,
        })
        metrics = calculate_current_metrics(df)
        assert 'BTC' in metrics
        assert 'STALE' not in metrics

    def test_staleness_filter_keeps_recent_assets(self):
        """Assets within 60 days of the global max are retained."""
        df = pd.DataFrame({
            'Date': ['2026-06-01', '2026-04-10'],  # 52 days apart
            'Asset': ['BTC', 'ETH'],
            'Price': [65000.0, 3500.0],
            'EMA21': [64000.0, 3450.0],
            'ATR': [1000.0, 50.0],
            'RSI': [50.0, 50.0],
            'RSI_Z_Score': [0.0, 0.0],
            'ATR_Distance': [1.0, 0.5],
            'Pct_Above_EMA': [1.56, 1.45],
            'Timeframe': ['1d', '1d'],
        })
        metrics = calculate_current_metrics(df)
        assert 'BTC' in metrics
        assert 'ETH' in metrics

    def test_vp_none_when_volume_column_absent(self, sample_history_df):
        """VP fields are None when High/Low/Volume columns are absent (backward compat)."""
        metrics = calculate_current_metrics(sample_history_df)
        current = metrics['BTC']['1d']['current']
        for field in ('vp_poc', 'vp_vah', 'vp_val', 'vp_position', 'vp_dist_from_poc', 'vp_buckets'):
            assert current[field] is None, f"Expected {field} to be None without volume data"

    def test_vp_fields_present_when_volume_available(self):
        """VP fields are populated when High, Low, Volume columns are present."""
        n = 50
        closes  = [100.0 + i * 0.5 for i in range(n)]
        highs   = [c + 1.0 for c in closes]
        lows    = [c - 1.0 for c in closes]
        dates   = [f'2026-0{(i // 28) + 1}-{(i % 28) + 1:02d}' for i in range(n)]
        df = pd.DataFrame({
            'Date':         dates,
            'Asset':        ['BTC'] * n,
            'Price':        closes,
            'EMA21':        [c - 0.5 for c in closes],
            'ATR':          [1.4] * n,
            'RSI':          [50.0] * n,
            'RSI_Z_Score':  [0.0] * n,
            'ATR_Distance': [0.5] * n,
            'Pct_Above_EMA':[0.5] * n,
            'Timeframe':    ['1d'] * n,
            'High':         highs,
            'Low':          lows,
            'Volume':       [100000.0] * n,
        })
        metrics = calculate_current_metrics(df)
        current = metrics['BTC']['1d']['current']
        assert current['vp_position'] is not None
        assert current['vp_poc'] is not None
        assert current['vp_vah'] is not None
        assert current['vp_val'] is not None
        assert current['vp_buckets'] is not None
        assert len(current['vp_buckets']) == 24


class TestGenerateDashboardJson:
    """Test dashboard JSON generation."""
    
    def test_generate_dashboard_json(self, sample_history_df):
        """Test dashboard JSON is generated with correct structure."""
        dashboard = generate_dashboard_json(sample_history_df)
        
        # Check metadata
        assert 'metadata' in dashboard
        assert 'last_updated' in dashboard['metadata']
        assert 'assets_count' in dashboard['metadata']
        assert 'records_count' in dashboard['metadata']
        assert 'date_range' in dashboard['metadata']
        
        # Check assets
        assert 'assets' in dashboard
        assert 'BTC' in dashboard['assets']
        assert 'ETH' in dashboard['assets']
        
        # Check asset structure
        btc_data = dashboard['assets']['BTC']['1d']
        assert 'current' in btc_data
        assert 'historical' in btc_data
    
    def test_metadata_values(self, sample_history_df):
        """Test metadata values are correct."""
        dashboard = generate_dashboard_json(sample_history_df)
        
        assert dashboard['metadata']['assets_count'] == 2
        assert dashboard['metadata']['records_count'] == 10
        assert dashboard['metadata']['date_range']['start'] == '2026-06-01'
        assert dashboard['metadata']['date_range']['end'] == '2026-06-05'
    
    def test_complete_data_structure(self, sample_history_df):
        """Test complete data structure includes all required fields."""
        dashboard = generate_dashboard_json(sample_history_df)
        
        # Check BTC daily data
        btc_daily = dashboard['assets']['BTC']['1d']
        
        # Check current data
        assert 'date' in btc_daily['current']
        assert 'price' in btc_daily['current']
        assert 'ema21' in btc_daily['current']
        assert 'atr' in btc_daily['current']
        assert 'rsi' in btc_daily['current']
        assert 'atr_distance' in btc_daily['current']
        assert 'regime' in btc_daily['current']
        assert 'atr_percentile' in btc_daily['current']
        
        # Check historical data
        assert 'atr_max' in btc_daily['historical']
        assert 'atr_min' in btc_daily['historical']
        assert 'atr_mean' in btc_daily['historical']
        assert 'atr_std' in btc_daily['historical']
        assert 'atr_percentile_25' in btc_daily['historical']
        assert 'atr_percentile_50' in btc_daily['historical']
        assert 'atr_percentile_75' in btc_daily['historical']
        assert 'atr_percentile_90' in btc_daily['historical']
        assert 'sample_size' in btc_daily['historical']


class TestMultipleTimeframes:
    """Test handling of multiple timeframes."""

    def test_multiple_timeframes(self):
        """Test metrics calculation with multiple timeframes."""
        df = pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-01'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 65000.0],
            'EMA21': [64000.0, 64000.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 50.0],
            'ATR_Distance': [1.0, 1.0],
            'Timeframe': ['1d', '1w']
        })

        metrics = calculate_historical_metrics(df)
        assert '1d' in metrics['BTC']
        assert '1w' in metrics['BTC']


class TestFetchFearGreed:
    """Tests for the Fear & Greed Index fetch helper."""

    def _mock_response(self, value, classification):
        mock = MagicMock()
        mock.json.return_value = {
            'data': [{'value': str(value), 'value_classification': classification, 'timestamp': '1748908800'}]
        }
        return mock

    def test_successful_fetch_returns_dict(self):
        with patch('calculate_metrics.requests.get') as mock_get:
            mock_get.return_value = self._mock_response(25, 'Fear')
            result = fetch_fear_greed()
        assert result == {'value': 25, 'label': 'Fear', 'timestamp': '1748908800'}

    def test_value_cast_to_int(self):
        with patch('calculate_metrics.requests.get') as mock_get:
            mock_get.return_value = self._mock_response('72', 'Greed')
            result = fetch_fear_greed()
        assert isinstance(result['value'], int)
        assert result['value'] == 72

    def test_all_classifications_parsed(self):
        labels = ['Extreme Fear', 'Fear', 'Neutral', 'Greed', 'Extreme Greed']
        for label in labels:
            with patch('calculate_metrics.requests.get') as mock_get:
                mock_get.return_value = self._mock_response(50, label)
                result = fetch_fear_greed()
            assert result['label'] == label

    def test_network_error_returns_none(self):
        with patch('calculate_metrics.requests.get', side_effect=Exception('timeout')):
            result = fetch_fear_greed()
        assert result is None

    def test_malformed_response_returns_none(self):
        mock = MagicMock()
        mock.json.return_value = {'data': []}  # empty data list
        with patch('calculate_metrics.requests.get', return_value=mock):
            result = fetch_fear_greed()
        assert result is None

    def test_http_error_returns_none(self):
        import requests as req
        mock = MagicMock()
        mock.raise_for_status.side_effect = req.exceptions.HTTPError('429')
        with patch('calculate_metrics.requests.get', return_value=mock):
            result = fetch_fear_greed()
        assert result is None


class TestFearGreedInDashboard:
    """Tests that fear_greed key flows correctly into dashboard.json."""

    @pytest.fixture
    def minimal_df(self):
        return pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-02'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 64000.0],
            'EMA21': [64000.0, 63600.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 45.0],
            'RSI_Z_Score': [0.0, -0.5],
            'ATR_Distance': [1.0, 0.4],
            'Pct_Above_EMA': [1.56, 0.63],
            'Timeframe': ['1d', '1d'],
        })

    def test_fear_greed_key_present_when_fetch_succeeds(self, minimal_df):
        mock_fg = {'value': 42, 'label': 'Fear', 'timestamp': '1748908800'}
        with patch('calculate_metrics.fetch_fear_greed', return_value=mock_fg):
            dashboard = generate_dashboard_json(minimal_df)
        assert 'fear_greed' in dashboard
        assert dashboard['fear_greed']['value'] == 42
        assert dashboard['fear_greed']['label'] == 'Fear'

    def test_fear_greed_key_none_when_fetch_fails(self, minimal_df):
        with patch('calculate_metrics.fetch_fear_greed', return_value=None):
            dashboard = generate_dashboard_json(minimal_df)
        assert 'fear_greed' in dashboard
        assert dashboard['fear_greed'] is None

    def test_fear_greed_does_not_affect_assets(self, minimal_df):
        mock_fg = {'value': 80, 'label': 'Extreme Greed', 'timestamp': '1748908800'}
        with patch('calculate_metrics.fetch_fear_greed', return_value=mock_fg):
            dashboard = generate_dashboard_json(minimal_df)
        assert 'BTC' in dashboard['assets']


class TestGenerateChartHistory:
    """Test chart history JSON generation."""

    def test_output_structure(self, sample_history_df):
        """Chart history produces asset → timeframe → list of bars."""
        result = generate_chart_history(sample_history_df)
        assert 'BTC' in result
        assert '1d' in result['BTC']
        assert isinstance(result['BTC']['1d'], list)

    def test_bar_fields(self, sample_history_df):
        """Each bar must have the five abbreviated keys d/a/r/p/e."""
        result = generate_chart_history(sample_history_df)
        bar = result['BTC']['1d'][0]
        for key in ('d', 'a', 'r', 'p', 'e'):
            assert key in bar, f"Missing key '{key}' in bar"

    def test_bar_count_capped_at_n_bars(self):
        """Bars are capped at n_bars even when more data is present."""
        df = pd.DataFrame({
            'Date': [f'2026-0{i // 28 + 1}-{i % 28 + 1:02d}' for i in range(200)],
            'Asset': ['BTC'] * 200,
            'Price': [60000.0] * 200,
            'EMA21': [59000.0] * 200,
            'ATR': [1000.0] * 200,
            'RSI': [50.0] * 200,
            'RSI_Z_Score': [0.0] * 200,
            'ATR_Distance': [1.0] * 200,
            'Pct_Above_EMA': [1.0] * 200,
            'Timeframe': ['1d'] * 200,
        })
        result = generate_chart_history(df, n_bars=50)
        assert len(result['BTC']['1d']) <= 50

    def test_null_atr_distance_excluded(self):
        """Bars with null ATR_Distance are excluded from the output."""
        import numpy as np
        df = pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-02', '2026-06-03'],
            'Asset': ['BTC', 'BTC', 'BTC'],
            'Price': [65000.0, 65500.0, 66000.0],
            'EMA21': [64000.0, 64200.0, 64400.0],
            'ATR': [1000.0, 1000.0, 1000.0],
            'RSI': [50.0, 55.0, 60.0],
            'RSI_Z_Score': [0.0, 0.5, 1.0],
            'ATR_Distance': [1.0, np.nan, 1.6],
            'Pct_Above_EMA': [1.56, 2.02, 2.48],
            'Timeframe': ['1d', '1d', '1d'],
        })
        result = generate_chart_history(df)
        assert len(result['BTC']['1d']) == 2  # null row excluded

    def test_date_format(self, sample_history_df):
        """Date field is a 10-character ISO string (YYYY-MM-DD)."""
        result = generate_chart_history(sample_history_df)
        for bar in result['BTC']['1d']:
            assert len(bar['d']) == 10
            assert bar['d'].count('-') == 2


class TestFetchBinanceFutures:
    """Tests for fetch_binance_futures() — Binance USDT-M futures, no auth required."""

    def _premium_mock(self, entries):
        """Build a mock premiumIndex response. entries: list of (symbol, lastFundingRate, markPrice)."""
        mock = MagicMock()
        mock.json.return_value = [
            {'symbol': sym, 'lastFundingRate': str(fr), 'markPrice': str(mp)}
            for sym, fr, mp in entries
        ]
        return mock

    def _oi_mock(self, oi_contracts):
        mock = MagicMock()
        mock.json.return_value = {'openInterest': str(oi_contracts), 'symbol': 'BTCUSDT'}
        return mock

    def test_successful_fetch_returns_coin_keyed_dict(self):
        def side_effect(url, **kwargs):
            if 'premiumIndex' in url:
                return self._premium_mock([('BTCUSDT', 0.0001, 43000.0), ('ETHUSDT', -0.0002, 2500.0)])
            return self._oi_mock(1000.0)
        with patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_binance_futures()
        assert 'BTC' in result
        assert 'ETH' in result

    def test_funding_rate_converted_to_percent(self):
        def side_effect(url, **kwargs):
            if 'premiumIndex' in url:
                return self._premium_mock([('BTCUSDT', 0.0001, 43000.0)])
            return self._oi_mock(100.0)
        with patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_binance_futures()
        assert result['BTC']['funding_rate'] == pytest.approx(0.01)  # 0.0001 × 100 = 0.01%

    def test_negative_funding_rate_preserved(self):
        def side_effect(url, **kwargs):
            if 'premiumIndex' in url:
                return self._premium_mock([('ETHUSDT', -0.0003, 2500.0)])
            return self._oi_mock(500.0)
        with patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_binance_futures()
        assert result['ETH']['funding_rate'] == pytest.approx(-0.03)

    def test_quarterly_contracts_excluded(self):
        def side_effect(url, **kwargs):
            if 'premiumIndex' in url:
                return self._premium_mock([
                    ('BTCUSDT', 0.0001, 43000.0),
                    ('BTCUSDT_240329', 0.0002, 43100.0),  # delivery contract — skip
                ])
            return self._oi_mock(100.0)
        with patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_binance_futures()
        assert 'BTC' in result
        # Delivery contract should not create a separate entry
        assert 'BTCUSDT_240329' not in result

    def test_oi_calculated_as_contracts_times_price(self):
        mark_price = 43000.0
        oi_contracts = 1000.0
        def side_effect(url, **kwargs):
            if 'premiumIndex' in url:
                return self._premium_mock([('BTCUSDT', 0.0001, mark_price)])
            return self._oi_mock(oi_contracts)
        with patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_binance_futures()
        assert result['BTC']['open_interest_usd'] == pytest.approx(oi_contracts * mark_price)

    def test_premiumindex_network_error_returns_empty(self):
        with patch('calculate_metrics.requests.get', side_effect=Exception('timeout')):
            result = fetch_binance_futures()
        assert result == {}

    def test_oi_failure_leaves_oi_as_none(self):
        import requests as req
        def side_effect(url, **kwargs):
            if 'premiumIndex' in url:
                return self._premium_mock([('BTCUSDT', 0.0001, 43000.0)])
            mock = MagicMock()
            mock.raise_for_status.side_effect = req.exceptions.HTTPError('429')
            return mock
        with patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_binance_futures()
        assert result['BTC']['funding_rate'] == pytest.approx(0.01)
        assert result['BTC']['open_interest_usd'] is None

    def test_untracked_symbols_ignored(self):
        def side_effect(url, **kwargs):
            if 'premiumIndex' in url:
                return self._premium_mock([
                    ('BTCUSDT', 0.0001, 43000.0),
                    ('DOGEUSDT', 0.0001, 0.1),  # DOGE not in our tracked set
                ])
            return self._oi_mock(100.0)
        with patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_binance_futures()
        assert 'BTC' in result
        assert 'DOGE' not in result


class TestBinanceFuturesInDashboard:
    """Tests that funding_rate and open_interest_usd flow into dashboard.json."""

    @pytest.fixture
    def btc_df(self):
        return pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-02'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 64000.0],
            'EMA21': [64000.0, 63600.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 45.0],
            'RSI_Z_Score': [0.0, -0.5],
            'ATR_Distance': [1.0, 0.4],
            'Pct_Above_EMA': [1.56, 0.63],
            'Timeframe': ['1d', '1d'],
        })

    def test_funding_rate_injected_when_binance_succeeds(self, btc_df):
        mock_bf = {'BTC': {'funding_rate': 0.0125, 'open_interest_usd': 28_000_000_000}}
        with patch('calculate_metrics.fetch_binance_futures', return_value=mock_bf), \
             patch('calculate_metrics.fetch_fear_greed', return_value=None):
            dashboard = generate_dashboard_json(btc_df)
        assert dashboard['assets']['BTC']['1d']['current']['funding_rate'] == pytest.approx(0.0125)

    def test_open_interest_injected_when_binance_succeeds(self, btc_df):
        mock_bf = {'BTC': {'funding_rate': 0.0100, 'open_interest_usd': 28_000_000_000}}
        with patch('calculate_metrics.fetch_binance_futures', return_value=mock_bf), \
             patch('calculate_metrics.fetch_fear_greed', return_value=None):
            dashboard = generate_dashboard_json(btc_df)
        assert dashboard['assets']['BTC']['1d']['current']['open_interest_usd'] == pytest.approx(28_000_000_000)

    def test_fields_null_when_binance_returns_empty(self, btc_df):
        with patch('calculate_metrics.fetch_binance_futures', return_value={}), \
             patch('calculate_metrics.fetch_fear_greed', return_value=None):
            dashboard = generate_dashboard_json(btc_df)
        current = dashboard['assets']['BTC']['1d']['current']
        assert current['funding_rate'] is None
        assert current['open_interest_usd'] is None

    def test_fields_null_when_symbol_absent(self, btc_df):
        mock_bf = {'ETH': {'funding_rate': 0.01, 'open_interest_usd': 1e9}}
        with patch('calculate_metrics.fetch_binance_futures', return_value=mock_bf), \
             patch('calculate_metrics.fetch_fear_greed', return_value=None):
            dashboard = generate_dashboard_json(btc_df)
        current = dashboard['assets']['BTC']['1d']['current']
        assert current['funding_rate'] is None
        assert current['open_interest_usd'] is None

    def test_injected_into_both_timeframes(self):
        df = pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-01'],
            'Asset': ['BTC', 'BTC'],
            'Price': [64000.0, 64000.0],
            'EMA21': [63600.0, 63600.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [45.0, 45.0],
            'RSI_Z_Score': [-0.5, -0.5],
            'ATR_Distance': [0.4, 0.4],
            'Pct_Above_EMA': [0.63, 0.63],
            'Timeframe': ['1d', '1w'],
        })
        mock_bf = {'BTC': {'funding_rate': 0.0200, 'open_interest_usd': 5e9}}
        with patch('calculate_metrics.fetch_binance_futures', return_value=mock_bf), \
             patch('calculate_metrics.fetch_fear_greed', return_value=None):
            dashboard = generate_dashboard_json(df)
        assert dashboard['assets']['BTC']['1d']['current']['funding_rate'] == pytest.approx(0.0200)
        assert dashboard['assets']['BTC']['1w']['current']['funding_rate'] == pytest.approx(0.0200)


class TestFetchBtcDominance:
    """Tests for fetch_btc_dominance()."""

    def _mock_resp(self, btc_pct):
        mock = MagicMock()
        mock.json.return_value = {'data': {'market_cap_percentage': {'btc': btc_pct, 'eth': 17.0}}}
        return mock

    def test_returns_float_on_success(self):
        with patch('calculate_metrics.requests.get', return_value=self._mock_resp(52.3)):
            result = fetch_btc_dominance()
        assert result == pytest.approx(52.3)

    def test_returns_none_on_network_error(self):
        with patch('calculate_metrics.requests.get', side_effect=Exception('timeout')):
            result = fetch_btc_dominance()
        assert result is None

    def test_returns_none_on_missing_key(self):
        mock = MagicMock()
        mock.json.return_value = {'data': {}}  # missing market_cap_percentage
        with patch('calculate_metrics.requests.get', return_value=mock):
            result = fetch_btc_dominance()
        assert result is None

    def test_returns_none_on_http_error(self):
        import requests as req
        mock = MagicMock()
        mock.raise_for_status.side_effect = req.exceptions.HTTPError('429')
        with patch('calculate_metrics.requests.get', return_value=mock):
            result = fetch_btc_dominance()
        assert result is None


class TestCalculateAltseasonIndex:
    """Tests for calculate_altseason_index()."""

    def _make_df(self, asset_prices):
        """asset_prices: {asset: (price_90d_ago, price_now)}"""
        rows = []
        base_date = pd.Timestamp('2026-03-01')
        now_date  = pd.Timestamp('2026-06-01')
        for asset, (old_p, new_p) in asset_prices.items():
            rows.append({'Date': base_date, 'Asset': asset, 'Price': old_p, 'Timeframe': '1d'})
            rows.append({'Date': now_date,  'Asset': asset, 'Price': new_p, 'Timeframe': '1d'})
        return pd.DataFrame(rows)

    def test_all_alts_outperform_btc_gives_100(self):
        # BTC: +10%; ETH, SOL: +50% each
        df = self._make_df({'BTC': (100, 110), 'ETH': (100, 150), 'SOL': (100, 150)})
        result = calculate_altseason_index(df)
        assert result is not None
        assert result['score'] == 100
        assert result['label'] == 'Altcoin Season'

    def test_no_alts_outperform_btc_gives_0(self):
        # BTC: +50%; ETH, SOL: +10% each
        df = self._make_df({'BTC': (100, 150), 'ETH': (100, 110), 'SOL': (100, 110)})
        result = calculate_altseason_index(df)
        assert result is not None
        assert result['score'] == 0
        assert result['label'] == 'Bitcoin Season'

    def test_half_outperforming_gives_50(self):
        df = self._make_df({
            'BTC': (100, 120),   # +20%
            'ETH': (100, 130),   # +30% — outperforms
            'SOL': (100, 110),   # +10% — underperforms
        })
        result = calculate_altseason_index(df)
        assert result is not None
        assert result['score'] == 50

    def test_returns_none_when_no_btc_data(self):
        df = self._make_df({'ETH': (100, 150), 'SOL': (100, 130)})
        result = calculate_altseason_index(df)
        assert result is None

    def test_returns_none_when_no_alts_have_data(self):
        df = self._make_df({'BTC': (100, 120)})
        result = calculate_altseason_index(df)
        assert result is None

    def test_alts_count_in_result(self):
        df = self._make_df({'BTC': (100, 120), 'ETH': (100, 130), 'SOL': (100, 110)})
        result = calculate_altseason_index(df)
        assert result['alts_outperforming'] == 1
        assert result['total'] == 2

    def test_weekly_timeframe_ignored(self):
        rows = [
            {'Date': '2026-03-01', 'Asset': 'BTC', 'Price': 100, 'Timeframe': '1d'},
            {'Date': '2026-06-01', 'Asset': 'BTC', 'Price': 120, 'Timeframe': '1d'},
            {'Date': '2026-03-01', 'Asset': 'ETH', 'Price': 100, 'Timeframe': '1w'},
            {'Date': '2026-06-01', 'Asset': 'ETH', 'Price': 150, 'Timeframe': '1w'},
        ]
        result = calculate_altseason_index(pd.DataFrame(rows))
        # ETH only has weekly data; should be excluded, total = 0 → None
        assert result is None


class TestMarketContextInDashboard:
    """Tests that btc_dominance and altseason flow into dashboard.json."""

    @pytest.fixture
    def minimal_df(self):
        return pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-02'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 64000.0],
            'EMA21': [64000.0, 63600.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 45.0],
            'RSI_Z_Score': [0.0, -0.5],
            'ATR_Distance': [1.0, 0.4],
            'Pct_Above_EMA': [1.56, 0.63],
            'Timeframe': ['1d', '1d'],
        })

    def test_btc_dominance_present_on_success(self, minimal_df):
        with patch('calculate_metrics.fetch_btc_dominance', return_value=52.3), \
             patch('calculate_metrics.calculate_altseason_index', return_value=None), \
             patch('calculate_metrics.fetch_binance_futures', return_value={}), \
             patch('calculate_metrics.fetch_fear_greed', return_value=None):
            dash = generate_dashboard_json(minimal_df)
        assert dash['btc_dominance'] == pytest.approx(52.3)

    def test_btc_dominance_null_on_failure(self, minimal_df):
        with patch('calculate_metrics.fetch_btc_dominance', return_value=None), \
             patch('calculate_metrics.calculate_altseason_index', return_value=None), \
             patch('calculate_metrics.fetch_binance_futures', return_value={}), \
             patch('calculate_metrics.fetch_fear_greed', return_value=None):
            dash = generate_dashboard_json(minimal_df)
        assert dash['btc_dominance'] is None

    def test_altseason_present_in_dashboard(self, minimal_df):
        mock_alts = {'score': 72, 'label': 'Leaning Alt', 'alts_outperforming': 18, 'total': 25}
        with patch('calculate_metrics.fetch_btc_dominance', return_value=None), \
             patch('calculate_metrics.calculate_altseason_index', return_value=mock_alts), \
             patch('calculate_metrics.fetch_binance_futures', return_value={}), \
             patch('calculate_metrics.fetch_fear_greed', return_value=None):
            dash = generate_dashboard_json(minimal_df)
        assert dash['altseason']['score'] == 72
        assert dash['altseason']['label'] == 'Leaning Alt'


class TestBBInCurrentSnapshot:
    """bb_pct_b and bb_bandwidth are written into dashboard.json current snapshot."""

    @pytest.fixture
    def df_with_bb(self):
        return pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-02'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 64000.0],
            'EMA21': [64000.0, 63600.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 45.0],
            'RSI_Z_Score': [0.0, -0.5],
            'ATR_Distance': [1.0, 0.4],
            'Pct_Above_EMA': [1.56, 0.63],
            'BB_Pct_B': [0.75, 0.32],
            'BB_Bandwidth': [8.5, 7.9],
            'Timeframe': ['1d', '1d'],
        })

    def test_bb_pct_b_in_snapshot(self, df_with_bb):
        """current snapshot includes bb_pct_b when column is present."""
        metrics = calculate_current_metrics(df_with_bb)
        assert 'bb_pct_b' in metrics['BTC']['1d']['current']
        assert metrics['BTC']['1d']['current']['bb_pct_b'] == pytest.approx(0.32)

    def test_bb_bandwidth_in_snapshot(self, df_with_bb):
        """current snapshot includes bb_bandwidth when column is present."""
        metrics = calculate_current_metrics(df_with_bb)
        assert 'bb_bandwidth' in metrics['BTC']['1d']['current']
        assert metrics['BTC']['1d']['current']['bb_bandwidth'] == pytest.approx(7.9)

    def test_bb_null_when_column_missing(self):
        """current snapshot sets bb fields to None when columns absent."""
        df = pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-02'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 64000.0],
            'EMA21': [64000.0, 63600.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 45.0],
            'RSI_Z_Score': [0.0, -0.5],
            'ATR_Distance': [1.0, 0.4],
            'Pct_Above_EMA': [1.56, 0.63],
            'Timeframe': ['1d', '1d'],
        })
        metrics = calculate_current_metrics(df)
        assert metrics['BTC']['1d']['current']['bb_pct_b'] is None
        assert metrics['BTC']['1d']['current']['bb_bandwidth'] is None


class TestADXInCurrentSnapshot:
    """ADX field is written into dashboard.json current snapshot."""

    @pytest.fixture
    def df_with_adx(self):
        return pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-02'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 64000.0],
            'EMA21': [64000.0, 63600.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 45.0],
            'RSI_Z_Score': [0.0, -0.5],
            'ATR_Distance': [1.0, 0.4],
            'Pct_Above_EMA': [1.56, 0.63],
            'ADX': [30.5, 28.1],
            'Timeframe': ['1d', '1d'],
        })

    @pytest.fixture
    def df_without_adx(self):
        return pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-02'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 64000.0],
            'EMA21': [64000.0, 63600.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 45.0],
            'RSI_Z_Score': [0.0, -0.5],
            'ATR_Distance': [1.0, 0.4],
            'Pct_Above_EMA': [1.56, 0.63],
            'Timeframe': ['1d', '1d'],
        })

    def test_adx_present_in_snapshot_when_column_exists(self, df_with_adx):
        """current snapshot includes adx float when ADX column is present."""
        metrics = calculate_current_metrics(df_with_adx)
        assert 'adx' in metrics['BTC']['1d']['current']
        assert metrics['BTC']['1d']['current']['adx'] == pytest.approx(28.1)

    def test_adx_null_when_column_missing(self, df_without_adx):
        """current snapshot sets adx=None when ADX column is absent."""
        metrics = calculate_current_metrics(df_without_adx)
        assert metrics['BTC']['1d']['current']['adx'] is None

    def test_adx_null_when_nan(self):
        """current snapshot sets adx=None when ADX value is NaN."""
        df = pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-02'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 64000.0],
            'EMA21': [64000.0, 63600.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 45.0],
            'RSI_Z_Score': [0.0, -0.5],
            'ATR_Distance': [1.0, 0.4],
            'Pct_Above_EMA': [1.56, 0.63],
            'ADX': [float('nan'), float('nan')],
            'Timeframe': ['1d', '1d'],
        })
        metrics = calculate_current_metrics(df)
        assert metrics['BTC']['1d']['current']['adx'] is None


class TestEMA50And200DMAInCurrentSnapshot:
    """ema50_distance and pct_above_200d are written into dashboard.json current snapshot."""

    def _make_df(self, n_bars: int, price: float = 100.0) -> 'pd.DataFrame':
        """Build a minimal history DataFrame with n_bars of constant price data."""
        import pandas as pd
        from datetime import date, timedelta
        base = date(2024, 1, 1)
        dates = [str(base + timedelta(days=i)) for i in range(n_bars)]
        return pd.DataFrame({
            'Date': dates,
            'Asset': ['BTC'] * n_bars,
            'Price': [price] * n_bars,
            'EMA21': [price] * n_bars,
            'ATR': [1000.0] * n_bars,
            'RSI': [50.0] * n_bars,
            'RSI_Z_Score': [0.0] * n_bars,
            'ATR_Distance': [0.0] * n_bars,
            'Pct_Above_EMA': [0.0] * n_bars,
            'Timeframe': ['1d'] * n_bars,
        })

    def test_ema50_distance_present_when_enough_history(self):
        """ema50_distance is non-null when asset has >= 50 bars."""
        df = self._make_df(60)
        metrics = calculate_current_metrics(df)
        assert metrics['BTC']['1d']['current']['ema50_distance'] is not None

    def test_ema50_distance_null_when_fewer_than_50_bars(self):
        """ema50_distance is None when asset has < 50 bars."""
        df = self._make_df(40)
        metrics = calculate_current_metrics(df)
        assert metrics['BTC']['1d']['current']['ema50_distance'] is None

    def test_pct_above_200d_present_when_enough_history(self):
        """pct_above_200d is non-null when asset has >= 200 bars."""
        df = self._make_df(210)
        metrics = calculate_current_metrics(df)
        assert metrics['BTC']['1d']['current']['pct_above_200d'] is not None

    def test_pct_above_200d_null_when_fewer_than_200_bars(self):
        """pct_above_200d is None when asset has < 200 bars."""
        df = self._make_df(150)
        metrics = calculate_current_metrics(df)
        assert metrics['BTC']['1d']['current']['pct_above_200d'] is None


class TestFetchBgeometricsOnchain:
    """Tests for fetch_bgeometrics_onchain()."""

    def _mock_resp(self, value):
        mock = MagicMock()
        mock.json.return_value = {'data': [['2026-06-04', str(value)]]}
        return mock

    def _mock_resp_multi(self, latest_value, old_value, n_rows=35):
        """Return n_rows of data; rows[-1]=latest_value, rows[-31]=old_value."""
        from datetime import date, timedelta
        base = date(2026, 6, 4)
        rows = [['2025-01-01', str(old_value)]] * n_rows
        rows[-1] = [str(base), str(latest_value)]
        rows[-(31)] = [str(base - timedelta(days=30)), str(old_value)]
        mock = MagicMock()
        mock.json.return_value = {'data': rows}
        return mock

    def test_success_returns_all_fields(self):
        def side_effect(url, **kwargs):
            if 'mvrv' in url:  return self._mock_resp(2.5)
            if 'nupl' in url:  return self._mock_resp(0.3)
            if 'sopr' in url:  return self._mock_resp(1.01)
            return self._mock_resp(0)
        with patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_bgeometrics_onchain()
        assert result is not None
        for key in ('mvrv_z_score', 'nupl', 'sopr', 'nupl_30d_change',
                    'signal_mvrv_z', 'signal_nupl', 'signal_sopr'):
            assert key in result

    def test_nupl_30d_change_computed_when_history_available(self):
        def side_effect(url, **kwargs):
            if 'mvrv' in url:  return self._mock_resp(2.0)
            if 'nupl' in url:  return self._mock_resp_multi(0.3, 0.1)
            if 'sopr' in url:  return self._mock_resp(1.01)
            return self._mock_resp(0)
        with patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_bgeometrics_onchain()
        assert result['nupl_30d_change'] == pytest.approx(0.2, abs=0.01)

    def test_accumulate_when_mvrv_z_negative(self):
        def side_effect(url, **kwargs):
            if 'mvrv' in url:  return self._mock_resp(-0.5)
            if 'nupl' in url:  return self._mock_resp(0.1)
            if 'sopr' in url:  return self._mock_resp(1.01)
            return self._mock_resp(0)
        with patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_bgeometrics_onchain()
        assert result['signal_mvrv_z'] == 'accumulate'

    def test_distribute_when_nupl_high(self):
        def side_effect(url, **kwargs):
            if 'mvrv' in url:  return self._mock_resp(3.0)
            if 'nupl' in url:  return self._mock_resp(0.6)
            if 'sopr' in url:  return self._mock_resp(1.01)
            return self._mock_resp(0)
        with patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_bgeometrics_onchain()
        assert result['signal_nupl'] == 'distribute'

    def test_neutral_sopr(self):
        def side_effect(url, **kwargs):
            if 'mvrv' in url:  return self._mock_resp(2.0)
            if 'nupl' in url:  return self._mock_resp(0.3)
            if 'sopr' in url:  return self._mock_resp(0.99)
            return self._mock_resp(0)
        with patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_bgeometrics_onchain()
        assert result['signal_sopr'] == 'neutral'

    def test_network_error_returns_none(self):
        with patch('calculate_metrics.requests.get', side_effect=Exception('timeout')):
            result = fetch_bgeometrics_onchain()
        assert result is None

    def test_http_403_returns_none(self):
        import requests as req
        mock = MagicMock()
        mock.raise_for_status.side_effect = req.exceptions.HTTPError('403')
        with patch('calculate_metrics.requests.get', return_value=mock):
            result = fetch_bgeometrics_onchain()
        assert result is None


class TestSupplyCrossSignal:
    """signal_supply_cross and supply_cross_occurred derived from NUPL in generate_btc_signals_json()."""

    def _history_df(self):
        import pandas as pd
        n = 30
        dates = pd.date_range(end='2026-06-05', periods=n, freq='D').strftime('%Y-%m-%d').tolist()
        return pd.DataFrame({
            'Date':         dates * 2,
            'Asset':        ['BTC'] * n * 2,
            'Timeframe':    ['1d'] * n + ['1w'] * n,
            'Price':        [60000.0] * n * 2,
            'EMA21':        [58000.0] * n * 2,
            'ATR':          [1500.0]  * n * 2,
            'RSI':          [50.0]    * n * 2,
            'RSI_Z_Score':  [0.0]     * n * 2,
            'ATR_Distance': [1.33]    * n * 2,
            'Pct_Above_EMA':[3.44]    * n * 2,
        })

    def _patch_all_fetchers(self, **overrides):
        defaults = {
            'calculate_metrics.fetch_hash_ribbons':        None,
            'calculate_metrics.fetch_stablecoin_trend':    None,
            'calculate_metrics.fetch_global_m2':           None,
            'calculate_metrics.fetch_etf_flows':           None,
            'calculate_metrics.fetch_binance_futures':     {},
            'calculate_metrics.fetch_bgeometrics_onchain':    None,
            'calculate_metrics.fetch_bitbo_onchain':           None,
            'calculate_metrics.fetch_coinmetrics_v4_onchain': None,
            'calculate_metrics.fetch_blockchair_cdd':          None,
            'calculate_metrics.fetch_puell_multiple':          None,
            'calculate_metrics._load_onchain_cache':           (None, None),
        }
        defaults.update(overrides)
        return [patch(k, return_value=v) for k, v in defaults.items()]

    def _run(self, onchain_ret):
        from calculate_metrics import generate_btc_signals_json, generate_dashboard_json
        hdf = self._history_df()
        dash = generate_dashboard_json(hdf)
        patches = self._patch_all_fetchers(**{
            'calculate_metrics.fetch_bgeometrics_onchain': onchain_ret,
        })
        for p in patches: p.start()
        try:
            result = generate_btc_signals_json(hdf, dash)
        finally:
            for p in patches: p.stop()
        return result['on_chain']

    def _onchain(self, nupl, nupl_30d_change=None):
        return {'mvrv_z_score': 2.0, 'nupl': nupl, 'nupl_30d_change': nupl_30d_change,
                'sopr': 1.01, 'signal_mvrv_z': 'neutral',
                'signal_nupl': 'neutral', 'signal_sopr': 'neutral'}

    def test_cross_occurred_when_nupl_negative(self):
        onc = self._run(self._onchain(-0.05))
        assert onc['supply_cross_occurred'] is True
        assert onc['signal_supply_cross'] == 'accumulate'

    def test_cross_not_occurred_when_nupl_positive(self):
        onc = self._run(self._onchain(0.15))
        assert onc['supply_cross_occurred'] is False
        assert onc['signal_supply_cross'] == 'neutral'

    def test_distribute_signal_when_nupl_high(self):
        onc = self._run(self._onchain(0.6))
        assert onc['signal_supply_cross'] == 'distribute'

    def test_nupl_30d_change_propagated(self):
        onc = self._run(self._onchain(0.3, nupl_30d_change=0.2))
        assert onc['nupl_30d_change'] == pytest.approx(0.2)

    def test_supply_cross_none_when_no_onchain_data(self):
        onc = self._run(None)  # BGeometrics returns None
        assert onc['supply_cross_occurred'] is None
        assert onc['signal_supply_cross'] is None


class TestFetchBitboOnchain:
    """Tests for fetch_bitbo_onchain()."""

    def _mock_resp(self, value):
        mock = MagicMock()
        mock.json.return_value = {'data': [['2026-06-04', str(value)]]}
        return mock

    def test_returns_none_without_api_key(self):
        with patch.dict('os.environ', {}, clear=True):
            result = fetch_bitbo_onchain()
        assert result is None

    def test_success_returns_mvrv_nupl(self):
        def side_effect(url, **kwargs):
            if 'mvrv-z' in url:   return self._mock_resp(3.1)
            if 'nupl-ratio' in url: return self._mock_resp(0.35)
            return self._mock_resp(0)
        with patch.dict('os.environ', {'BITBO_API_KEY': 'test-key'}), \
             patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_bitbo_onchain()
        assert result is not None
        assert result['mvrv_z_score'] == pytest.approx(3.1)
        assert result['signal_mvrv_z'] == 'neutral'
        assert result['sopr'] is None

    def test_distribute_when_mvrv_z_high(self):
        def side_effect(url, **kwargs):
            if 'mvrv-z' in url:   return self._mock_resp(7.2)
            if 'nupl-ratio' in url: return self._mock_resp(0.55)
            return self._mock_resp(0)
        with patch.dict('os.environ', {'BITBO_API_KEY': 'test-key'}), \
             patch('calculate_metrics.requests.get', side_effect=side_effect):
            result = fetch_bitbo_onchain()
        assert result['signal_mvrv_z'] == 'distribute'
        assert result['signal_nupl'] == 'distribute'

    def test_network_error_returns_none(self):
        with patch.dict('os.environ', {'BITBO_API_KEY': 'test-key'}), \
             patch('calculate_metrics.requests.get', side_effect=Exception('timeout')):
            result = fetch_bitbo_onchain()
        assert result is None

    def test_http_403_returns_none(self):
        import requests as req
        mock = MagicMock()
        mock.raise_for_status.side_effect = req.exceptions.HTTPError('403')
        with patch.dict('os.environ', {'BITBO_API_KEY': 'test-key'}), \
             patch('calculate_metrics.requests.get', return_value=mock):
            result = fetch_bitbo_onchain()
        assert result is None


class TestFetchCoinmetricsV4Onchain:
    """Tests for fetch_coinmetrics_v4_onchain()."""

    def _mock_resp(self, mkt, real, sopr):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            'data': [
                {'CapMrktCurUSD': str(mkt), 'CapRealUSD': str(real), 'SoprEntEth': str(sopr)}
            ]
        }
        return resp

    def test_success_returns_mvrv_and_sopr(self):
        resp = self._mock_resp(mkt=2e12, real=1e12, sopr=1.02)
        with patch('calculate_metrics.requests.get', return_value=resp):
            result = fetch_coinmetrics_v4_onchain()
        assert result is not None
        assert result['mvrv_z_score'] == pytest.approx(2.0, abs=0.01)
        assert result['sopr'] == pytest.approx(1.02, abs=0.001)
        assert result['nupl'] is None
        assert result['signal_nupl'] is None

    def test_accumulate_signal_when_mvrv_below_1(self):
        resp = self._mock_resp(mkt=0.8e12, real=1e12, sopr=0.97)
        with patch('calculate_metrics.requests.get', return_value=resp):
            result = fetch_coinmetrics_v4_onchain()
        assert result['signal_mvrv_z'] == 'accumulate'
        assert result['signal_sopr'] == 'accumulate'

    def test_distribute_signal_when_mvrv_above_3(self):
        resp = self._mock_resp(mkt=4e12, real=1e12, sopr=1.10)
        with patch('calculate_metrics.requests.get', return_value=resp):
            result = fetch_coinmetrics_v4_onchain()
        assert result['signal_mvrv_z'] == 'distribute'
        assert result['signal_sopr'] == 'distribute'

    def test_returns_none_when_realised_cap_zero(self):
        resp = self._mock_resp(mkt=2e12, real=0, sopr=1.0)
        with patch('calculate_metrics.requests.get', return_value=resp):
            result = fetch_coinmetrics_v4_onchain()
        assert result is None

    def test_returns_none_on_empty_data(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {'data': []}
        with patch('calculate_metrics.requests.get', return_value=resp):
            result = fetch_coinmetrics_v4_onchain()
        assert result is None

    def test_returns_none_on_http_403(self):
        resp = MagicMock()
        resp.status_code = 403
        resp.raise_for_status.side_effect = Exception('403 Forbidden')
        with patch('calculate_metrics.requests.get', return_value=resp):
            result = fetch_coinmetrics_v4_onchain()
        assert result is None


class TestFetchBlockchairCdd:
    """Tests for fetch_blockchair_cdd()."""

    def _make_rows(self, values):
        """values: list of daily CDD totals, newest first (index 0 = most recent)."""
        from datetime import date, timedelta
        base = date(2026, 6, 4)
        return [
            {'date': str(base - timedelta(days=i)), 'sum(cdd_total)': v}
            for i, v in enumerate(values)
        ]

    def _mock_resp(self, values):
        mock = MagicMock()
        mock.json.return_value = {'data': self._make_rows(values)}
        return mock

    def test_success_returns_all_fields(self):
        values = [100_000.0] * 90  # 90 rows, newest first
        with patch('calculate_metrics.requests.get', return_value=self._mock_resp(values)):
            result = fetch_blockchair_cdd()
        assert result is not None
        for key in ('cdd_latest', 'cdd_90d_avg', 'cdd_90d_change_pct', 'signal_cvdd'):
            assert key in result

    def test_neutral_when_at_avg(self):
        values = [100_000.0] * 90  # all equal → ratio = 1.0 → neutral
        with patch('calculate_metrics.requests.get', return_value=self._mock_resp(values)):
            result = fetch_blockchair_cdd()
        assert result['signal_cvdd'] == 'neutral'
        assert result['cdd_90d_change_pct'] == pytest.approx(0.0)

    def test_accumulate_when_ratio_below_0_5(self):
        # Latest (newest = index 0) is 40% of average → ratio 0.4 → accumulate
        avg = 100_000.0
        values = [avg * 0.4] + [avg] * 89  # newest first
        with patch('calculate_metrics.requests.get', return_value=self._mock_resp(values)):
            result = fetch_blockchair_cdd()
        assert result['signal_cvdd'] == 'accumulate'

    def test_distribute_when_ratio_above_1_5(self):
        # Latest (newest = index 0) is 170% of average → ratio ~1.7 → distribute
        avg = 100_000.0
        values = [avg * 1.7] + [avg] * 89  # newest first
        with patch('calculate_metrics.requests.get', return_value=self._mock_resp(values)):
            result = fetch_blockchair_cdd()
        assert result['signal_cvdd'] == 'distribute'

    def test_returns_none_when_fewer_than_10_rows(self):
        values = [100_000.0] * 5
        with patch('calculate_metrics.requests.get', return_value=self._mock_resp(values)):
            result = fetch_blockchair_cdd()
        assert result is None

    def test_returns_none_on_network_error(self):
        with patch('calculate_metrics.requests.get', side_effect=Exception('timeout')):
            result = fetch_blockchair_cdd()
        assert result is None

    def test_returns_none_on_http_403(self):
        import requests as req
        mock = MagicMock()
        mock.raise_for_status.side_effect = req.exceptions.HTTPError('403')
        with patch('calculate_metrics.requests.get', return_value=mock):
            result = fetch_blockchair_cdd()
        assert result is None


class TestFetchPuellMultiple:
    """Tests for fetch_puell_multiple()."""

    def _btc_prices(self, n=400, price=60000.0):
        """Build a pd.Series of BTC prices indexed by date (aligned with _make_mempool_rows)."""
        import pandas as pd
        dates = pd.date_range(start='2024-01-01', periods=n, freq='D')
        return pd.Series([price] * n, index=dates, name='Price')

    def _make_mempool_rows(self, n, avg_rewards=3125 * 1e8, avg_fees=0):
        """Build n fake mempool.space block reward rows."""
        import pandas as pd
        base_ts = int(pd.Timestamp('2024-01-01').timestamp())
        return [
            {
                'timestamp': base_ts + i * 86400,
                'avgRewards': avg_rewards,
                'avgFees':    avg_fees,
            }
            for i in range(n)
        ]

    def _mock_resp(self, rows):
        mock = MagicMock()
        mock.json.return_value = rows
        return mock

    def test_success_returns_all_fields(self):
        from calculate_metrics import fetch_puell_multiple
        rows = self._make_mempool_rows(400)
        with patch('calculate_metrics.requests.get', return_value=self._mock_resp(rows)):
            result = fetch_puell_multiple(self._btc_prices())
        assert result is not None
        for key in ('puell_multiple', 'daily_revenue_usd', 'ma_365d_usd', 'signal'):
            assert key in result
        assert result['puell_multiple'] > 0
        assert result['signal'] in ('accumulate', 'neutral', 'distribute')

    def test_insufficient_rows_returns_none(self):
        from calculate_metrics import fetch_puell_multiple
        rows = self._make_mempool_rows(30)
        with patch('calculate_metrics.requests.get', return_value=self._mock_resp(rows)):
            result = fetch_puell_multiple(self._btc_prices())
        assert result is None

    def test_no_price_overlap_returns_none(self):
        """Returns None when joined DataFrame has fewer than 30 rows."""
        import pandas as pd
        from calculate_metrics import fetch_puell_multiple
        rows = self._make_mempool_rows(400)
        # Provide prices from a completely non-overlapping date range
        far_future_dates = pd.date_range(start='2030-01-01', periods=400, freq='D')
        prices = pd.Series([60000.0] * 400, index=far_future_dates)
        with patch('calculate_metrics.requests.get', return_value=self._mock_resp(rows)):
            result = fetch_puell_multiple(prices)
        assert result is None

    def test_network_error_returns_none(self):
        from calculate_metrics import fetch_puell_multiple
        with patch('calculate_metrics.requests.get', side_effect=Exception('timeout')):
            result = fetch_puell_multiple(self._btc_prices())
        assert result is None

    def test_accumulate_signal_low_puell(self):
        """signal is 'accumulate' when Puell < 0.6."""
        from calculate_metrics import fetch_puell_multiple
        # Low rewards today → low Puell; high MA from historical rows
        # Use tiny rewards for today (last row) and normal for the rest
        rows = self._make_mempool_rows(399, avg_rewards=3125 * 1e8)
        rows.append({
            'timestamp': rows[-1]['timestamp'] + 86400,
            'avgRewards': 10,  # almost zero — produces very small Puell
            'avgFees': 0,
        })
        with patch('calculate_metrics.requests.get', return_value=self._mock_resp(rows)):
            result = fetch_puell_multiple(self._btc_prices(400))
        assert result is not None
        assert result['signal'] == 'accumulate'


class TestGenerateBtcSignalsJsonConfluence:
    """Tests for generate_btc_signals_json() confluence logic."""

    def _history_df(self):
        """Minimal history DataFrame with 30 BTC daily rows."""
        import pandas as pd
        n = 30
        dates = pd.date_range(end='2026-06-05', periods=n, freq='D').strftime('%Y-%m-%d').tolist()
        return pd.DataFrame({
            'Date':         dates * 2,
            'Asset':        ['BTC'] * n + ['BTC'] * n,
            'Timeframe':    ['1d'] * n + ['1w'] * n,
            'Price':        [60000.0] * n * 2,
            'EMA21':        [58000.0] * n * 2,
            'ATR':          [1500.0]  * n * 2,
            'RSI':          [50.0]    * n * 2,
            'RSI_Z_Score':  [0.0]     * n * 2,
            'ATR_Distance': [1.33]    * n * 2,
            'Pct_Above_EMA':[3.44]    * n * 2,
        })

    def _dashboard(self, history_df):
        """Minimal dashboard dict derived from history_df."""
        from calculate_metrics import generate_dashboard_json
        return generate_dashboard_json(history_df)

    def _patch_all_fetchers(self, **overrides):
        """Context manager that patches all external fetchers to return None."""
        defaults = {
            'calculate_metrics.fetch_hash_ribbons':        None,
            'calculate_metrics.fetch_stablecoin_trend':    None,
            'calculate_metrics.fetch_global_m2':           None,
            'calculate_metrics.fetch_etf_flows':           None,
            'calculate_metrics.fetch_binance_futures':     {},
            'calculate_metrics.fetch_bgeometrics_onchain': None,
            'calculate_metrics.fetch_bitbo_onchain':       None,
            'calculate_metrics.fetch_blockchair_cdd':      None,
            'calculate_metrics.fetch_puell_multiple':      None,
            'calculate_metrics._load_onchain_cache':       (None, None),
        }
        defaults.update(overrides)
        patches = [patch(k, return_value=v) for k, v in defaults.items()]
        return patches

    def _apply_patches(self, patches):
        for p in patches:
            p.start()
        return patches

    def _stop_patches(self, patches):
        for p in patches:
            p.stop()

    def test_on_chain_section_always_present(self):
        """on_chain section is always present even when Coinmetrics fails (returns None)."""
        from calculate_metrics import generate_btc_signals_json
        hdf = self._history_df()
        dash = self._dashboard(hdf)
        patches = self._apply_patches(self._patch_all_fetchers())
        try:
            result = generate_btc_signals_json(hdf, dash)
        finally:
            self._stop_patches(patches)
        assert 'on_chain' in result
        assert result['on_chain']['mvrv_z_score'] is None

    def test_confluence_section_present(self):
        """confluence section is always present with required keys."""
        from calculate_metrics import generate_btc_signals_json
        hdf = self._history_df()
        dash = self._dashboard(hdf)
        patches = self._apply_patches(self._patch_all_fetchers())
        try:
            result = generate_btc_signals_json(hdf, dash)
        finally:
            self._stop_patches(patches)
        conf = result['confluence']
        for key in ('accumulate_count', 'distribute_count', 'neutral_count', 'phase', 'strength'):
            assert key in conf

    def test_accumulation_phase_when_acc_dominates(self):
        """phase is 'Accumulation' when accumulate_count > distribute_count."""
        from calculate_metrics import generate_btc_signals_json
        hdf = self._history_df()
        # Use very negative ATR Distance → accumulate signals
        hdf['ATR_Distance'] = -3.5
        dash = self._dashboard(hdf)
        bgeom = {
            'mvrv_z_score': -1.5, 'nupl': -0.4, 'sopr': 0.96,
            'signal_mvrv_z': 'accumulate', 'signal_nupl': 'accumulate', 'signal_sopr': 'accumulate',
        }
        cdd = {
            'cdd_latest': int(1e8), 'cdd_90d_avg': int(2e8),
            'cdd_90d_change_pct': -50.0, 'signal_cvdd': 'accumulate',
        }
        patches = self._apply_patches(self._patch_all_fetchers(
            **{
                'calculate_metrics.fetch_bgeometrics_onchain': bgeom,
                'calculate_metrics.fetch_blockchair_cdd': cdd,
            }
        ))
        try:
            result = generate_btc_signals_json(hdf, dash)
        finally:
            self._stop_patches(patches)
        assert result['confluence']['phase'] == 'Accumulation'


class TestOnchainCache:
    """Tests for _load_onchain_cache / _save_onchain_cache and their integration."""

    def test_save_and_load_roundtrip(self, tmp_path):
        bg = {'mvrv_z_score': 1.5, 'nupl': 0.3, 'sopr': 1.01, 'signal_mvrv_z': 'neutral'}
        cdd = {'cdd_latest': 1000, 'cdd_90d_avg': 2000, 'cdd_90d_change_pct': -50.0, 'signal_cvdd': 'accumulate'}
        cache_file = str(tmp_path / 'onchain_cache.json')
        with patch.object(_cm, '_ONCHAIN_CACHE_PATH', cache_file):
            _save_onchain_cache(bg, cdd)
            loaded_bg, loaded_cdd = _load_onchain_cache()
        assert loaded_bg == bg
        assert loaded_cdd == cdd

    def test_stale_cache_not_used(self, tmp_path):
        cache_file = str(tmp_path / 'onchain_cache.json')
        stale_cache = {
            'fetched_at': '2020-01-01',
            'bgeometrics': {'mvrv_z_score': 9.9},
            'cdd': {'signal_cvdd': 'distribute'},
        }
        with open(cache_file, 'w') as f:
            json.dump(stale_cache, f)
        with patch.object(_cm, '_ONCHAIN_CACHE_PATH', cache_file):
            loaded_bg, loaded_cdd = _load_onchain_cache()
        assert loaded_bg is None
        assert loaded_cdd is None

    def test_missing_cache_returns_none(self, tmp_path):
        cache_file = str(tmp_path / 'nonexistent_cache.json')
        with patch.object(_cm, '_ONCHAIN_CACHE_PATH', cache_file):
            loaded_bg, loaded_cdd = _load_onchain_cache()
        assert loaded_bg is None
        assert loaded_cdd is None

    def test_cache_used_when_all_apis_fail(self, tmp_path):
        """When BGeometrics, Bitbo, and Blockchair all return None, cached data fills the gap."""
        from calculate_metrics import generate_btc_signals_json
        cache_file = str(tmp_path / 'onchain_cache.json')
        cached_bg = {'mvrv_z_score': 2.1, 'nupl': 0.42, 'nupl_30d_change': 0.05,
                     'sopr': 1.02, 'signal_mvrv_z': 'neutral', 'signal_nupl': 'neutral',
                     'signal_sopr': 'neutral'}
        cached_cdd = {'cdd_latest': 500, 'cdd_90d_avg': 1000,
                      'cdd_90d_change_pct': -50.0, 'signal_cvdd': 'accumulate'}
        with open(cache_file, 'w') as f:
            import datetime
            json.dump({'fetched_at': datetime.date.today().isoformat(),
                       'bgeometrics': cached_bg, 'cdd': cached_cdd}, f)

        # Build a minimal BTC history DF with enough rows for generate_btc_signals_json
        dates = pd.date_range('2022-01-01', periods=250, freq='D')
        hdf = pd.DataFrame({
            'Date': list(dates) * 2,
            'Asset': ['BTC'] * 250 + ['BTC'] * 250,
            'Timeframe': ['1d'] * 250 + ['1w'] * 250,
            'Price': [30000.0 + i * 10 for i in range(250)] * 2,
            'EMA21': [29500.0 + i * 10 for i in range(250)] * 2,
            'ATR': [500.0] * 500,
            'RSI': [50.0] * 500,
        })
        dash = {'assets': {}, 'fear_greed': None, 'btc_dominance': None, 'altseason': None}

        none_resp = MagicMock()
        none_resp.return_value = None

        patches = [
            patch('calculate_metrics.fetch_bgeometrics_onchain', return_value=None),
            patch('calculate_metrics.fetch_bitbo_onchain', return_value=None),
            patch('calculate_metrics.fetch_coinmetrics_v4_onchain', return_value=None),
            patch('calculate_metrics.fetch_blockchair_cdd', return_value=None),
            patch('calculate_metrics.fetch_hash_ribbons', return_value=None),
            patch('calculate_metrics.fetch_puell_multiple', return_value=None),
            patch('calculate_metrics.fetch_stablecoin_trend', return_value=None),
            patch('calculate_metrics.fetch_global_m2', return_value=None),
            patch('calculate_metrics.fetch_etf_flows', return_value=None),
            patch('calculate_metrics.fetch_fear_greed', return_value=None),
            patch('calculate_metrics.fetch_binance_futures', return_value={}),
            patch('calculate_metrics.fetch_btc_dominance', return_value=None),
            patch.object(_cm, '_ONCHAIN_CACHE_PATH', cache_file),
        ]
        started = [p.start() for p in patches]
        try:
            result = generate_btc_signals_json(hdf, dash)
        finally:
            for p in patches:
                p.stop()

        assert result['on_chain']['mvrv_z_score'] == 2.1
        assert result['on_chain']['nupl'] == 0.42
        assert result['on_chain']['signal_cvdd'] == 'accumulate'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
