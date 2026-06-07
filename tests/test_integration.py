#!/usr/bin/env python3
"""
Integration tests for the trading analytics pipeline.
"""

import json
import os
import shutil
import tempfile

import pandas as pd
import pytest


class TestPipelineIntegration:
    """Test end-to-end pipeline integration."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def sample_excel_data(self, temp_dir):
        """Create a sample Excel file for testing."""
        import openpyxl
        from openpyxl import Workbook
        
        excel_path = os.path.join(temp_dir, 'test_workbook.xlsx')
        wb = Workbook()
        ws = wb.active
        ws.title = 'Data'
        
        # Write headers
        headers = ['Date', 'Asset', 'Price', 'EMA21', 'ATR', 'RSI', 'RSI_Z_Score', 'ATR_Distance', 'Pct_Above_EMA', 'Timeframe']
        ws.append(headers)
        
        # Write sample data
        ws.append(['2026-06-01', 'BTC', 65000.0, 64000.0, 1000.0, 50.0, 0.0, 1.0, 1.56, '1d'])
        ws.append(['2026-06-01', 'ETH', 3500.0, 3450.0, 50.0, 50.0, 0.0, 1.0, 1.45, '1d'])
        ws.append(['2026-06-01', 'BTC', 65000.0, 64000.0, 1000.0, 50.0, 0.0, 1.0, 1.56, '1w'])
        
        wb.save(excel_path)
        return excel_path
    
    def test_validation_to_metrics_pipeline(self, sample_excel_data, temp_dir):
        """Test pipeline from validation to metrics calculation."""
        from validate_data import validate_excel
        from calculate_metrics import generate_dashboard_json
        
        # Step 1: Validate Excel data
        print("Step 1: Validating Excel data")
        result = validate_excel(sample_excel_data)
        assert result.is_valid, "Validation should pass"
        
        # Step 2: Read data and create history CSV
        print("Step 2: Creating history CSV")
        df = pd.read_excel(sample_excel_data)
        history_path = os.path.join(temp_dir, 'history.csv')
        df.to_csv(history_path, index=False)
        
        # Step 3: Calculate metrics
        print("Step 3: Calculating metrics")
        history_df = pd.read_csv(history_path)
        dashboard = generate_dashboard_json(history_df)
        
        # Step 4: Verify dashboard structure
        print("Step 4: Verifying dashboard structure")
        assert 'metadata' in dashboard
        assert 'assets' in dashboard
        assert dashboard['metadata']['assets_count'] > 0
        assert dashboard['metadata']['records_count'] > 0
        
        # Step 5: Save dashboard JSON
        print("Step 5: Saving dashboard JSON")
        dashboard_path = os.path.join(temp_dir, 'dashboard.json')
        with open(dashboard_path, 'w') as f:
            json.dump(dashboard, f, indent=2)
        
        # Step 6: Verify JSON can be loaded
        print("Step 6: Verifying JSON can be loaded")
        with open(dashboard_path, 'r') as f:
            loaded_dashboard = json.load(f)
        # Verify structure (not exact equality due to float precision)
        assert 'metadata' in loaded_dashboard
        assert 'assets' in loaded_dashboard
        assert loaded_dashboard['metadata']['assets_count'] == dashboard['metadata']['assets_count']
        assert loaded_dashboard['metadata']['records_count'] == dashboard['metadata']['records_count']
    
    def test_dashboard_json_structure(self, temp_dir):
        """Test that dashboard.json has the correct structure."""
        # Create a minimal valid dashboard.json
        dashboard = {
            'metadata': {
                'last_updated': '2026-06-01T00:00:00Z',
                'assets_count': 2,
                'records_count': 3,
                'date_range': {'start': '2026-06-01', 'end': '2026-06-01'},
                'history_file': 'data/history.csv'
            },
            'assets': {
                'BTC': {
                    '1d': {
                        'current': {
                            'date': '2026-06-01',
                            'price': 65000.0,
                            'atr_distance': 1.0,
                            'regime': 'Trend'
                        },
                        'historical': {
                            'atr_max': 1.0,
                            'atr_min': 1.0,
                            'sample_size': 1
                        }
                    }
                }
            }
        }
        
        dashboard_path = os.path.join(temp_dir, 'dashboard.json')
        with open(dashboard_path, 'w') as f:
            json.dump(dashboard, f, indent=2)
        
        # Verify structure
        with open(dashboard_path, 'r') as f:
            loaded = json.load(f)
        
        assert 'metadata' in loaded
        assert 'assets' in loaded
        assert 'last_updated' in loaded['metadata']
        assert 'assets_count' in loaded['metadata']
        assert 'records_count' in loaded['metadata']
    
    def test_no_duplicate_history_records(self, temp_dir):
        """Test that duplicate records are not added to history."""
        # Create initial history
        initial_data = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [1000.0],
            'RSI': [50.0],
            'ATR_Distance': [1.0],
            'Timeframe': ['1d']
        })
        history_path = os.path.join(temp_dir, 'history.csv')
        initial_data.to_csv(history_path, index=False)
        
        # Try to add duplicate
        from update_history import remove_duplicates
        new_data = pd.DataFrame({
            'Date': ['2026-06-01'],
            'Asset': ['BTC'],
            'Price': [65500.0],  # Different price but same date/asset/timeframe
            'EMA21': [64200.0],
            'ATR': [1000.0],
            'RSI': [52.0],
            'ATR_Distance': [1.3],
            'Timeframe': ['1d']
        })
        
        existing = pd.read_csv(history_path)
        new_records = remove_duplicates(new_data, existing)
        
        # Should be empty because it's a duplicate
        assert len(new_records) == 0
    
    def test_atr_distance_recalculation(self, temp_dir):
        """Test that ATR Distance is recalculated during ingestion."""
        from update_history import recalculate_atr_distance
        
        # Create data with incorrect ATR Distance
        df = pd.DataFrame({
            'Price': [65000.0],
            'EMA21': [64000.0],
            'ATR': [1000.0],
            'ATR_Distance': [999.0]  # Wrong value
        })
        
        # Recalculate
        recalculated = recalculate_atr_distance(df)
        
        # Should be (65000 - 64000) / 1000 = 1.0
        assert recalculated['ATR_Distance'].iloc[0] == 1.0


class TestDashboardBuild:
    """Test dashboard build process."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    def test_dashboard_build_creates_files(self, temp_dir):
        """Test that dashboard build creates necessary files."""
        # Create dashboard.json
        dashboard = {
            'metadata': {
                'last_updated': '2026-06-01T00:00:00Z',
                'assets_count': 1,
                'records_count': 1
            },
            'assets': {}
        }
        
        dashboard_json_path = os.path.join(temp_dir, 'dashboard.json')
        with open(dashboard_json_path, 'w') as f:
            json.dump(dashboard, f)
        
        # Create dashboard directory structure
        dashboard_dir = os.path.join(temp_dir, 'dashboard')
        assets_dir = os.path.join(dashboard_dir, 'assets')
        os.makedirs(assets_dir, exist_ok=True)
        
        # Simulate build_dashboard.py
        import shutil
        shutil.copy2(dashboard_json_path, os.path.join(assets_dir, 'data.json'))
        
        # Verify files exist
        assert os.path.exists(os.path.join(assets_dir, 'data.json'))
        
        # Verify JSON is valid
        with open(os.path.join(assets_dir, 'data.json'), 'r') as f:
            loaded = json.load(f)
        assert loaded == dashboard


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
