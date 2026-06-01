#!/usr/bin/env python3
"""
Unit tests for data validation.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from validate_data import (
    ValidationResult,
    validate_columns,
    validate_numeric_fields,
    validate_atr,
    validate_rsi,
    validate_timeframe,
    validate_duplicates,
    validate_dataframe
)


@pytest.fixture
def valid_df():
    """Create a valid DataFrame for testing."""
    return pd.DataFrame({
        'Date': ['2026-06-01', '2026-06-02', '2026-06-03'],
        'Asset': ['BTC', 'ETH', 'SOL'],
        'Price': [65000.0, 3500.0, 150.0],
        'EMA21': [64000.0, 3450.0, 148.0],
        'ATR': [1000.0, 50.0, 5.0],
        'RSI': [50.0, 55.0, 45.0],
        'RSI_Z_Score': [0.0, 0.5, -0.5],
        'ATR_Distance': [1.0, 1.0, 0.4],
        'Pct_Above_EMA': [1.56, 1.45, 1.35],
        'Timeframe': ['1d', '1d', '1d']
    })


class TestValidationResult:
    """Test ValidationResult class."""
    
    def test_initial_state(self):
        """Test initial state is valid with no errors."""
        result = ValidationResult()
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
    
    def test_add_error(self):
        """Test adding an error marks result as invalid."""
        result = ValidationResult()
        result.add_error("Test error")
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0] == "Test error"
    
    def test_add_warning(self):
        """Test adding a warning does not affect validity."""
        result = ValidationResult()
        result.add_warning("Test warning")
        assert result.is_valid is True
        assert len(result.warnings) == 1
        assert result.warnings[0] == "Test warning"
    
    def test_multiple_errors(self):
        """Test multiple errors are collected."""
        result = ValidationResult()
        result.add_error("Error 1")
        result.add_error("Error 2")
        assert result.is_valid is False
        assert len(result.errors) == 2
    
    def test_get_report_valid(self):
        """Test report for valid result."""
        result = ValidationResult()
        report = result.get_report()
        assert "✓ Validation passed" in report
    
    def test_get_report_invalid(self):
        """Test report for invalid result."""
        result = ValidationResult()
        result.add_error("Test error")
        report = result.get_report()
        assert "✗ Validation failed" in report
        assert "Test error" in report


class TestValidateColumns:
    """Test column validation."""
    
    def test_all_columns_present(self, valid_df):
        """Test validation passes with all required columns."""
        result = ValidationResult()
        validate_columns(valid_df, result)
        assert result.is_valid is True
    
    def test_missing_column(self):
        """Test validation fails with missing column."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0]
            # Missing EMA21, ATR, RSI, Timeframe
        })
        result = ValidationResult()
        validate_columns(df, result)
        assert result.is_valid is False
        assert "Missing required columns" in result.errors[0]
    
    def test_multiple_missing_columns(self):
        """Test validation fails with multiple missing columns."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC']
        })
        result = ValidationResult()
        validate_columns(df, result)
        assert result.is_valid is False
        assert len(result.errors) == 1  # One error message listing all missing


class TestValidateNumericFields:
    """Test numeric field validation."""
    
    def test_valid_numeric_fields(self, valid_df):
        """Test validation passes with valid numeric data."""
        result = ValidationResult()
        validate_numeric_fields(valid_df, result)
        assert result.is_valid is True
    
    def test_non_numeric_price(self):
        """Test validation fails with non-numeric price."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': ['invalid'],  # Non-numeric
            'EMA21': [64000.0],
            'ATR': [1000.0],
            'RSI': [50.0],
            'Timeframe': ['1d']
        })
        result = ValidationResult()
        validate_numeric_fields(df, result)
        assert result.is_valid is False
        assert "Price" in result.errors[0]
    
    def test_nan_allowed(self):
        """Test NaN values are allowed (handled separately)."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [np.nan],  # NaN is allowed
            'ATR': [1000.0],
            'RSI': [50.0],
            'Timeframe': ['1d']
        })
        result = ValidationResult()
        validate_numeric_fields(df, result)
        assert result.is_valid is True


class TestValidateATR:
    """Test ATR validation."""
    
    def test_valid_atr(self, valid_df):
        """Test validation passes with valid ATR (> 0)."""
        result = ValidationResult()
        validate_atr(valid_df, result)
        assert result.is_valid is True
    
    def test_atr_zero(self):
        """Test validation fails with ATR = 0."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [0.0],  # Invalid: must be > 0
            'RSI': [50.0],
            'Timeframe': ['1d']
        })
        result = ValidationResult()
        validate_atr(df, result)
        assert result.is_valid is False
        assert "ATR must be > 0" in result.errors[0]
    
    def test_atr_negative(self):
        """Test validation fails with negative ATR."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [-100.0],  # Invalid: negative
            'RSI': [50.0],
            'Timeframe': ['1d']
        })
        result = ValidationResult()
        validate_atr(df, result)
        assert result.is_valid is False
        assert "ATR must be > 0" in result.errors[0]
    
    def test_atr_nan_allowed(self):
        """Test NaN ATR is allowed (handled separately)."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [np.nan],  # NaN is allowed
            'RSI': [50.0],
            'Timeframe': ['1d']
        })
        result = ValidationResult()
        validate_atr(df, result)
        assert result.is_valid is True


class TestValidateRSI:
    """Test RSI validation."""
    
    def test_valid_rsi(self, valid_df):
        """Test validation passes with valid RSI (0-100)."""
        result = ValidationResult()
        validate_rsi(valid_df, result)
        assert result.is_valid is True
    
    def test_rsi_below_zero(self):
        """Test validation fails with RSI < 0."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [1000.0],
            'RSI': [-10.0],  # Invalid: < 0
            'Timeframe': ['1d']
        })
        result = ValidationResult()
        validate_rsi(df, result)
        assert result.is_valid is False
        assert "RSI must be between 0 and 100" in result.errors[0]
    
    def test_rsi_above_100(self):
        """Test validation fails with RSI > 100."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [1000.0],
            'RSI': [150.0],  # Invalid: > 100
            'Timeframe': ['1d']
        })
        result = ValidationResult()
        validate_rsi(df, result)
        assert result.is_valid is False
        assert "RSI must be between 0 and 100" in result.errors[0]
    
    def test_rsi_boundaries(self):
        """Test RSI at boundaries (0 and 100) are valid."""
        df = pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-02'],
            'Asset': ['BTC', 'ETH'],
            'Price': [65000.0, 3500.0],
            'EMA21': [64000.0, 3450.0],
            'ATR': [1000.0, 50.0],
            'RSI': [0.0, 100.0],  # Boundaries are valid
            'Timeframe': ['1d', '1d']
        })
        result = ValidationResult()
        validate_rsi(df, result)
        assert result.is_valid is True
    
    def test_rsi_nan_allowed(self):
        """Test NaN RSI is allowed (handled separately)."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [1000.0],
            'RSI': [np.nan],  # NaN is allowed
            'Timeframe': ['1d']
        })
        result = ValidationResult()
        validate_rsi(df, result)
        assert result.is_valid is True


class TestValidateTimeframe:
    """Test timeframe validation."""
    
    def test_valid_timeframe_1d(self, valid_df):
        """Test validation passes with '1d' timeframe."""
        result = ValidationResult()
        validate_timeframe(valid_df, result)
        assert result.is_valid is True
    
    def test_valid_timeframe_1w(self):
        """Test validation passes with '1w' timeframe."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [1000.0],
            'RSI': [50.0],
            'Timeframe': ['1w']
        })
        result = ValidationResult()
        validate_timeframe(df, result)
        assert result.is_valid is True
    
    def test_valid_timeframe_daily(self):
        """Test validation passes with 'Daily' timeframe."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [1000.0],
            'RSI': [50.0],
            'Timeframe': ['Daily']
        })
        result = ValidationResult()
        validate_timeframe(df, result)
        assert result.is_valid is True
    
    def test_valid_timeframe_weekly(self):
        """Test validation passes with 'Weekly' timeframe."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [1000.0],
            'RSI': [50.0],
            'Timeframe': ['Weekly']
        })
        result = ValidationResult()
        validate_timeframe(df, result)
        assert result.is_valid is True
    
    def test_invalid_timeframe(self):
        """Test validation fails with invalid timeframe."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [1000.0],
            'RSI': [50.0],
            'Timeframe': ['1h']  # Invalid
        })
        result = ValidationResult()
        validate_timeframe(df, result)
        assert result.is_valid is False
        assert "Timeframe must be" in result.errors[0]


class TestValidateDuplicates:
    """Test duplicate detection."""
    
    def test_no_duplicates(self, valid_df):
        """Test validation passes with no duplicates."""
        result = ValidationResult()
        validate_duplicates(valid_df, result)
        assert result.is_valid is True
    
    def test_duplicates_detected(self):
        """Test validation fails with duplicate Date+Asset+Timeframe."""
        df = pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-01'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 65500.0],
            'EMA21': [64000.0, 64200.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 52.0],
            'Timeframe': ['1d', '1d']  # Duplicate
        })
        result = ValidationResult()
        validate_duplicates(df, result)
        assert result.is_valid is False
        assert "duplicate Date+Asset+Timeframe" in result.errors[0]
    
    def test_different_timeframes_not_duplicate(self):
        """Test different timeframes for same date/asset are not duplicates."""
        df = pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-01'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 65000.0],
            'EMA21': [64000.0, 64000.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 50.0],
            'Timeframe': ['1d', '1w']  # Different timeframes
        })
        result = ValidationResult()
        validate_duplicates(df, result)
        assert result.is_valid is True
    
    def test_case_insensitive_timeframe(self):
        """Test timeframe comparison is case-insensitive."""
        df = pd.DataFrame({
            'Date': ['2026-06-01', '2026-06-01'],
            'Asset': ['BTC', 'BTC'],
            'Price': [65000.0, 65500.0],
            'EMA21': [64000.0, 64200.0],
            'ATR': [1000.0, 1000.0],
            'RSI': [50.0, 52.0],
            'Timeframe': ['1d', 'Daily']  # Should be treated as duplicate
        })
        result = ValidationResult()
        validate_duplicates(df, result)
        assert result.is_valid is False


class TestValidateDataFrame:
    """Test complete DataFrame validation."""
    
    def test_valid_dataframe(self, valid_df):
        """Test validation passes for valid DataFrame."""
        result = validate_dataframe(valid_df)
        assert result.is_valid is True
    
    def test_invalid_dataframe_multiple_errors(self):
        """Test validation fails with multiple errors."""
        df = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [-100.0],  # Invalid ATR
            'RSI': [150.0],  # Invalid RSI
            'Timeframe': ['1h']  # Invalid timeframe
        })
        result = validate_dataframe(df)
        assert result.is_valid is False
        assert len(result.errors) >= 3  # At least 3 errors


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
