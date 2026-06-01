#!/usr/bin/env python3
"""
Metrics Calculation Script
Calculates derived metrics from history.csv and generates dashboard.json.
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Anchor all paths to project root (M2)
HISTORY_CSV_PATH = str(_PROJECT_ROOT / 'data' / 'history.csv')
DASHBOARD_JSON_PATH = str(_PROJECT_ROOT / 'data' / 'dashboard.json')
METADATA_JSON_PATH = str(_PROJECT_ROOT / 'data' / 'metadata.json')


def _norm_timeframe(tf: str) -> str:
    """Normalise timeframe string to canonical form ('1d' / '1w')."""
    t = tf.lower()
    if t == 'daily':
        return '1d'
    if t == 'weekly':
        return '1w'
    return t


def _sanitise(obj):
    """Recursively replace float NaN / inf with None so json.dump produces valid JSON (H5)."""
    if isinstance(obj, dict):
        return {k: _sanitise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitise(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def classify_regime(atr_distance: float) -> str:
    """
    Classify market regime from ATR Distance:
      < -2   → Accumulation
      -2..2  → Trend
      2..4   → Extended
      > 4    → Euphoria
    """
    if pd.isna(atr_distance):
        return 'Unknown'
    if atr_distance < -2:
        return 'Accumulation'
    if atr_distance <= 2:
        return 'Trend'
    if atr_distance <= 4:
        return 'Extended'
    return 'Euphoria'


def calculate_historical_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate historical ATR Distance statistics for each asset+timeframe."""
    metrics: Dict[str, Any] = {}

    for (asset, timeframe), group in df.groupby(['Asset', 'Timeframe']):
        if pd.isna(timeframe):
            continue

        tf_norm = _norm_timeframe(str(timeframe))
        metrics.setdefault(asset, {}).setdefault(tf_norm, {})

        atr_distances = group['ATR_Distance'].replace([np.inf, -np.inf], np.nan).dropna()

        if len(atr_distances) > 0:
            std = atr_distances.std()
            metrics[asset][tf_norm]['historical'] = {
                'atr_max': float(atr_distances.max()),
                'atr_min': float(atr_distances.min()),
                'atr_mean': float(atr_distances.mean()),
                'atr_std': float(std) if pd.notna(std) else None,
                'atr_percentile_25': float(atr_distances.quantile(0.25)),
                'atr_percentile_50': float(atr_distances.quantile(0.50)),
                'atr_percentile_75': float(atr_distances.quantile(0.75)),
                'atr_percentile_90': float(atr_distances.quantile(0.90)),
                'sample_size': len(atr_distances),
            }
        else:
            metrics[asset][tf_norm]['historical'] = {
                'atr_max': None, 'atr_min': None, 'atr_mean': None,
                'atr_std': None, 'atr_percentile_25': None,
                'atr_percentile_50': None, 'atr_percentile_75': None,
                'atr_percentile_90': None, 'sample_size': 0,
            }

    return metrics


def calculate_current_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate current snapshot metrics for each asset+timeframe."""
    metrics: Dict[str, Any] = {}

    latest = df.sort_values('Date', ascending=False).groupby(['Asset', 'Timeframe']).first()

    for (asset, timeframe), row in latest.iterrows():
        if pd.isna(timeframe):
            continue

        tf_norm = _norm_timeframe(str(timeframe))
        metrics.setdefault(asset, {}).setdefault(tf_norm, {})

        atr_distance = row.get('ATR_Distance')
        regime = classify_regime(atr_distance)

        # M7: normalise timeframe when filtering historical data for percentile calc
        norm_series = df['Timeframe'].apply(lambda t: _norm_timeframe(str(t)) if pd.notna(t) else '')
        asset_data = df[(df['Asset'] == asset) & (norm_series == tf_norm)]
        atr_distances = asset_data['ATR_Distance'].replace([np.inf, -np.inf], np.nan).dropna()

        if len(atr_distances) > 0 and pd.notna(atr_distance):
            percentile = float((atr_distances < float(atr_distance)).sum() / len(atr_distances) * 100)
        else:
            percentile = None

        metrics[asset][tf_norm]['current'] = {
            'date': row['Date'],
            'price': float(row['Price']) if pd.notna(row['Price']) else None,
            'ema21': float(row['EMA21']) if pd.notna(row['EMA21']) else None,
            'atr': float(row['ATR']) if pd.notna(row['ATR']) else None,
            'rsi': float(row['RSI']) if pd.notna(row['RSI']) else None,
            'rsi_z_score': float(row['RSI_Z_Score']) if pd.notna(row.get('RSI_Z_Score')) else None,
            'atr_distance': float(atr_distance) if pd.notna(atr_distance) else None,
            'pct_above_ema': float(row['Pct_Above_EMA']) if pd.notna(row.get('Pct_Above_EMA')) else None,
            'regime': regime,
            'atr_percentile': percentile,
        }

    return metrics


def generate_dashboard_json(history_df: pd.DataFrame) -> Dict[str, Any]:
    """Build the complete dashboard.json payload."""
    print("Calculating historical metrics...")
    historical_metrics = calculate_historical_metrics(history_df)

    print("Calculating current metrics...")
    current_metrics = calculate_current_metrics(history_df)

    assets_data: Dict[str, Any] = {}
    for asset in set(list(historical_metrics) + list(current_metrics)):
        assets_data[asset] = {}
        timeframes = set()
        if asset in historical_metrics:
            timeframes.update(historical_metrics[asset])
        if asset in current_metrics:
            timeframes.update(current_metrics[asset])

        for tf in timeframes:
            assets_data[asset][tf] = {}
            if asset in historical_metrics and tf in historical_metrics[asset]:
                assets_data[asset][tf]['historical'] = historical_metrics[asset][tf]['historical']
            if asset in current_metrics and tf in current_metrics[asset]:
                assets_data[asset][tf]['current'] = current_metrics[asset][tf]['current']

    dashboard = {
        'metadata': {
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'assets_count': int(history_df['Asset'].nunique()),
            'records_count': int(len(history_df)),
            'date_range': {
                'start': history_df['Date'].min(),
                'end': history_df['Date'].max(),
            },
            'history_file': HISTORY_CSV_PATH,
        },
        'assets': assets_data,
    }

    # H5: sanitise all NaN/inf before JSON serialisation
    return _sanitise(dashboard)


def main():
    """Main execution function."""
    print("=" * 60)
    print("Metrics Calculation Script")
    print("=" * 60)
    print()

    if not os.path.exists(HISTORY_CSV_PATH):
        print(f"ERROR: {HISTORY_CSV_PATH} not found")
        print("Please run update_history.py first to generate history.csv")
        sys.exit(1)

    print(f"Loading {HISTORY_CSV_PATH}...")
    history_df = pd.read_csv(HISTORY_CSV_PATH)
    print(f"Loaded {len(history_df)} records")
    print(f"Assets: {history_df['Asset'].nunique()}")
    print(f"Date range: {history_df['Date'].min()} to {history_df['Date'].max()}")
    print()

    required_columns = ['Date', 'Asset', 'Price', 'EMA21', 'ATR', 'RSI', 'ATR_Distance', 'Timeframe']
    missing = [c for c in required_columns if c not in history_df.columns]
    if missing:
        print(f"ERROR: Missing required columns: {', '.join(missing)}")
        sys.exit(1)

    print("Generating dashboard.json...")
    dashboard = generate_dashboard_json(history_df)

    with open(DASHBOARD_JSON_PATH, 'w') as f:
        json.dump(dashboard, f, indent=2)
    print(f"✓ Saved dashboard.json to {DASHBOARD_JSON_PATH}")
    print()

    print("=" * 60)
    print("Metrics calculation completed successfully")
    print("=" * 60)
    print(f"Assets processed: {dashboard['metadata']['assets_count']}")
    print(f"Total records: {dashboard['metadata']['records_count']}")
    print(f"Date range: {dashboard['metadata']['date_range']['start']} to {dashboard['metadata']['date_range']['end']}")
    print()


if __name__ == "__main__":
    main()
