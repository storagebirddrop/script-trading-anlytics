#!/usr/bin/env python3
"""
Metrics Calculation Script
Calculates derived metrics from history.csv and generates dashboard.json.
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime
from typing import Dict, Any
import sys
import os

HISTORY_CSV_PATH = 'data/history.csv'
DASHBOARD_JSON_PATH = 'data/dashboard.json'
METADATA_JSON_PATH = 'data/metadata.json'


def classify_regime(atr_distance: float) -> str:
    """
    Classify regime based on ATR Distance.
    
    ATR Distance < -2: Accumulation
    -2 to 2: Trend
    2 to 4: Extended
    > 4: Euphoria
    """
    if pd.isna(atr_distance):
        return 'Unknown'
    
    if atr_distance < -2:
        return 'Accumulation'
    elif atr_distance <= 2:
        return 'Trend'
    elif atr_distance <= 4:
        return 'Extended'
    else:
        return 'Euphoria'


def calculate_historical_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate historical metrics for each asset and timeframe.
    """
    metrics = {}
    
    # Group by asset and timeframe
    for (asset, timeframe), group in df.groupby(['Asset', 'Timeframe']):
        # Guard against NaN timeframe
        if pd.isna(timeframe):
            continue
        
        # Normalize timeframe
        timeframe_norm = timeframe.lower()
        if timeframe_norm == 'daily':
            timeframe_norm = '1d'
        elif timeframe_norm == 'weekly':
            timeframe_norm = '1w'
        
        if asset not in metrics:
            metrics[asset] = {}
        
        if timeframe_norm not in metrics[asset]:
            metrics[asset][timeframe_norm] = {}
        
        # Calculate historical ATR Distance metrics
        atr_distances = group['ATR_Distance'].dropna()
        
        if len(atr_distances) > 0:
            metrics[asset][timeframe_norm]['historical'] = {
                'atr_max': float(atr_distances.max()),
                'atr_min': float(atr_distances.min()),
                'atr_mean': float(atr_distances.mean()),
                'atr_std': float(atr_distances.std()),
                'atr_percentile_25': float(atr_distances.quantile(0.25)),
                'atr_percentile_50': float(atr_distances.quantile(0.50)),
                'atr_percentile_75': float(atr_distances.quantile(0.75)),
                'atr_percentile_90': float(atr_distances.quantile(0.90)),
                'sample_size': len(atr_distances)
            }
        else:
            metrics[asset][timeframe_norm]['historical'] = {
                'atr_max': None,
                'atr_min': None,
                'atr_mean': None,
                'atr_std': None,
                'atr_percentile_25': None,
                'atr_percentile_50': None,
                'atr_percentile_75': None,
                'atr_percentile_90': None,
                'sample_size': 0
            }
    
    return metrics


def calculate_current_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate current metrics for each asset and timeframe.
    """
    metrics = {}
    
    # Get latest record for each asset+timeframe
    latest = df.sort_values('Date', ascending=False).groupby(['Asset', 'Timeframe']).first()
    
    for (asset, timeframe), row in latest.iterrows():
        # Guard against NaN timeframe
        if pd.isna(timeframe):
            continue
        
        # Normalize timeframe
        timeframe_norm = timeframe.lower()
        if timeframe_norm == 'daily':
            timeframe_norm = '1d'
        elif timeframe_norm == 'weekly':
            timeframe_norm = '1w'
        
        if asset not in metrics:
            metrics[asset] = {}
        
        if timeframe_norm not in metrics[asset]:
            metrics[asset][timeframe_norm] = {}
        
        # Calculate regime
        atr_distance = row.get('ATR_Distance')
        regime = classify_regime(atr_distance)
        
        # Calculate percentile of current ATR Distance
        # Need to get all historical data for this asset+timeframe
        asset_data = df[(df['Asset'] == asset) & (df['Timeframe'] == timeframe)]
        atr_distances = asset_data['ATR_Distance'].dropna()
        
        if len(atr_distances) > 0 and not pd.isna(atr_distance):
            percentile = (atr_distances < atr_distance).sum() / len(atr_distances) * 100
        else:
            percentile = None
        
        metrics[asset][timeframe_norm]['current'] = {
            'date': row['Date'],
            'price': float(row['Price']) if pd.notna(row['Price']) else None,
            'ema21': float(row['EMA21']) if pd.notna(row['EMA21']) else None,
            'atr': float(row['ATR']) if pd.notna(row['ATR']) else None,
            'rsi': float(row['RSI']) if pd.notna(row['RSI']) else None,
            'rsi_z_score': float(row['RSI_Z_Score']) if pd.notna(row.get('RSI_Z_Score')) else None,
            'atr_distance': float(atr_distance) if pd.notna(atr_distance) else None,
            'pct_above_ema': float(row['Pct_Above_EMA']) if pd.notna(row.get('Pct_Above_EMA')) else None,
            'regime': regime,
            'atr_percentile': percentile
        }
    
    return metrics


def calculate_rsi_z_score_history(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate RSI Z-score history for each asset and timeframe.
    This is already in the data, but we can recalculate if needed.
    """
    # RSI Z-Score is already calculated in the data
    # This function is a placeholder for future enhancement
    return {}


def generate_dashboard_json(history_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Generate the complete dashboard.json structure.
    """
    print("Calculating historical metrics...")
    historical_metrics = calculate_historical_metrics(history_df)
    
    print("Calculating current metrics...")
    current_metrics = calculate_current_metrics(history_df)
    
    # Merge historical and current metrics
    assets_data = {}
    for asset in set(list(historical_metrics.keys()) + list(current_metrics.keys())):
        assets_data[asset] = {}
        
        # Get all timeframes for this asset
        timeframes = set()
        if asset in historical_metrics:
            timeframes.update(historical_metrics[asset].keys())
        if asset in current_metrics:
            timeframes.update(current_metrics[asset].keys())
        
        for timeframe in timeframes:
            assets_data[asset][timeframe] = {}
            
            # Add historical data
            if asset in historical_metrics and timeframe in historical_metrics[asset]:
                assets_data[asset][timeframe]['historical'] = historical_metrics[asset][timeframe]['historical']
            
            # Add current data
            if asset in current_metrics and timeframe in current_metrics[asset]:
                assets_data[asset][timeframe]['current'] = current_metrics[asset][timeframe]['current']
    
    # Calculate overall statistics
    total_records = len(history_df)
    unique_assets = history_df['Asset'].nunique()
    date_range = {
        'start': history_df['Date'].min(),
        'end': history_df['Date'].max()
    }
    
    # Create dashboard structure
    dashboard = {
        'metadata': {
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'assets_count': unique_assets,
            'records_count': total_records,
            'date_range': date_range,
            'history_file': HISTORY_CSV_PATH
        },
        'assets': assets_data
    }
    
    return dashboard


def main():
    """Main execution function."""
    print("=" * 60)
    print("Metrics Calculation Script")
    print("=" * 60)
    print()
    
    # Check if history.csv exists
    if not os.path.exists(HISTORY_CSV_PATH):
        print(f"ERROR: {HISTORY_CSV_PATH} not found")
        print("Please run update_history.py first to generate history.csv")
        sys.exit(1)
    
    # Load history.csv
    print(f"Loading {HISTORY_CSV_PATH}...")
    history_df = pd.read_csv(HISTORY_CSV_PATH)
    print(f"Loaded {len(history_df)} records")
    print(f"Assets: {history_df['Asset'].nunique()}")
    print(f"Date range: {history_df['Date'].min()} to {history_df['Date'].max()}")
    print()
    
    # Check required columns
    required_columns = ['Date', 'Asset', 'Price', 'EMA21', 'ATR', 'RSI', 'ATR_Distance', 'Timeframe']
    missing_columns = [col for col in required_columns if col not in history_df.columns]
    if missing_columns:
        print(f"ERROR: Missing required columns: {', '.join(missing_columns)}")
        sys.exit(1)
    
    # Generate dashboard.json
    print("Generating dashboard.json...")
    dashboard = generate_dashboard_json(history_df)
    
    # Save dashboard.json
    with open(DASHBOARD_JSON_PATH, 'w') as f:
        json.dump(dashboard, f, indent=2)
    
    print(f"✓ Saved dashboard.json to {DASHBOARD_JSON_PATH}")
    print()
    
    # Print summary
    print("=" * 60)
    print("Metrics calculation completed successfully")
    print("=" * 60)
    print(f"Assets processed: {dashboard['metadata']['assets_count']}")
    print(f"Total records: {dashboard['metadata']['records_count']}")
    print(f"Date range: {dashboard['metadata']['date_range']['start']} to {dashboard['metadata']['date_range']['end']}")
    print()


if __name__ == "__main__":
    main()
