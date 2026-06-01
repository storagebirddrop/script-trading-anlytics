#!/usr/bin/env python3
"""
Unit tests for metrics calculation.
"""

import pytest
import pandas as pd
import numpy as np
from calculate_metrics import (
    classify_regime,
    calculate_historical_metrics,
    calculate_current_metrics,
    generate_dashboard_json
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
    
    def test_accumulation_regime(self):
        """Test ATR Distance < -2 classifies as Accumulation."""
        assert classify_regime(-2.5) == 'Accumulation'
        assert classify_regime(-3.0) == 'Accumulation'
        assert classify_regime(-10.0) == 'Accumulation'
    
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
    
    def test_extended_regime_lower_bound(self):
        """Test ATR Distance > 2 classifies as Extended."""
        assert classify_regime(2.1) == 'Extended'
    
    def test_extended_regime_middle(self):
        """Test ATR Distance between 2 and 4 classifies as Extended."""
        assert classify_regime(3.0) == 'Extended'
    
    def test_extended_regime_upper_bound(self):
        """Test ATR Distance = 4 classifies as Extended."""
        assert classify_regime(4.0) == 'Extended'
    
    def test_euphoria_regime(self):
        """Test ATR Distance > 4 classifies as Euphoria."""
        assert classify_regime(4.1) == 'Euphoria'
        assert classify_regime(5.0) == 'Euphoria'
        assert classify_regime(10.0) == 'Euphoria'
    
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
