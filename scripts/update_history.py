#!/usr/bin/env python3
"""
History Update Script
Reads Excel workbook, validates data, appends to history.csv, updates master.csv.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Anchor all paths to project root (M2)
EXCEL_PATH = str(_PROJECT_ROOT / 'ATR_Tracker_Dashboard.xlsx')
MASTER_CSV_PATH = str(_PROJECT_ROOT / 'data' / 'master.csv')
HISTORY_CSV_PATH = str(_PROJECT_ROOT / 'data' / 'history.csv')
METADATA_JSON_PATH = str(_PROJECT_ROOT / 'data' / 'metadata.json')

# Add scripts directory to path for validate_data import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_data import (
    ValidationResult,
    validate_columns,
    validate_numeric_fields,
    validate_atr,
    validate_rsi,
    validate_timeframe,
    validate_key_nulls,
    validate_duplicates,
)


def recalculate_atr_distance(df: pd.DataFrame) -> pd.DataFrame:
    """Recalculate ATR_Distance and Pct_Above_EMA from raw columns (H2)."""
    df = df.copy()
    safe_atr = df['ATR'].replace(0, np.nan)
    df['ATR_Distance'] = ((df['Price'] - df['EMA21']) / safe_atr).replace([np.inf, -np.inf], np.nan)
    df['Pct_Above_EMA'] = ((df['Price'] - df['EMA21']) / df['EMA21']) * 100
    return df


def load_history() -> pd.DataFrame:
    """Load existing history.csv or return empty DataFrame."""
    if os.path.exists(HISTORY_CSV_PATH):
        df = pd.read_csv(HISTORY_CSV_PATH)
        print(f"Loaded existing history: {len(df)} records")
        return df
    print("No existing history.csv found, will create new file")
    return pd.DataFrame()


def read_excel_data(excel_path: str) -> pd.DataFrame:
    """Read the 'Data' sheet from the Excel workbook written by crypto_tracker.py."""
    try:
        xl = pd.ExcelFile(excel_path)
        print(f"Reading Excel file: {excel_path}")
        print(f"Available sheets: {', '.join(xl.sheet_names)}")

        if 'Data' not in xl.sheet_names:
            print("ERROR: 'Data' sheet not found in Excel workbook")
            return pd.DataFrame()

        df = pd.read_excel(excel_path, sheet_name='Data')
        df.columns = df.columns.str.strip()
        print(f"Read {len(df)} records from Data sheet")
        return df

    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return pd.DataFrame()


def remove_duplicates(new_data: pd.DataFrame, existing_history: pd.DataFrame) -> pd.DataFrame:
    """
    Return only records from new_data that are not already in existing_history,
    keyed on Date+Asset+Timeframe (case-insensitive, Daily/Weekly normalised).

    Fixes:
      C4 — intra-batch duplicates are dropped before cross-batch comparison.
      H4 — original Timeframe values are preserved in the returned records.
    """
    # Normalise a copy for key comparison only
    def _norm_tf(series):
        return series.fillna('').str.lower().replace({'daily': '1d', 'weekly': '1w'})

    new_norm = new_data.copy()
    new_norm['_tf'] = _norm_tf(new_norm['Timeframe'])

    # C4: drop intra-batch duplicates before cross-batch check
    new_norm = new_norm.drop_duplicates(subset=['Date', 'Asset', '_tf'])

    new_norm['_key'] = (
        new_norm['Date'].fillna('').astype(str) + '|' +
        new_norm['Asset'].fillna('').astype(str) + '|' +
        new_norm['_tf'].astype(str)
    )

    if not existing_history.empty:
        ex_norm = existing_history.copy()
        ex_norm['_tf'] = _norm_tf(ex_norm['Timeframe'])
        ex_norm['_key'] = (
            ex_norm['Date'].fillna('').astype(str) + '|' +
            ex_norm['Asset'].fillna('').astype(str) + '|' +
            ex_norm['_tf'].astype(str)
        )
        mask = ~new_norm['_key'].isin(ex_norm['_key'])
    else:
        mask = pd.Series([True] * len(new_norm), index=new_norm.index)

    # H4: return rows from the *original* new_data using the surviving index,
    # so original Timeframe values are preserved (not the normalised ones).
    surviving_index = new_norm[mask].index
    new_records = new_data.loc[surviving_index]

    skipped = len(new_data) - len(new_records)
    print(f"Found {len(new_records)} new records to append (skipped {skipped} duplicates)")
    return new_records


def update_master(df: pd.DataFrame) -> pd.DataFrame:
    """Return the latest row per Asset+Timeframe combination."""
    if df.empty:
        return df
    latest = (
        df.sort_values('Date', ascending=False)
        .groupby(['Asset', 'Timeframe'])
        .first()
        .reset_index()
    )
    print(f"Updated master with {len(latest)} latest records")
    return latest


def save_metadata(record_count: int, asset_count: int):
    """Write metadata.json."""
    metadata = {
        'last_updated': datetime.utcnow().isoformat() + 'Z',
        'records_count': record_count,
        'assets_count': asset_count,
        'history_file': HISTORY_CSV_PATH,
        'master_file': MASTER_CSV_PATH,
    }
    with open(METADATA_JSON_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved metadata to {METADATA_JSON_PATH}")


def validate_dataframe(df: pd.DataFrame) -> ValidationResult:
    """Full validation including null-key and duplicate checks (H3)."""
    result = ValidationResult()
    validate_columns(df, result)
    validate_numeric_fields(df, result)
    validate_atr(df, result)
    validate_rsi(df, result)
    validate_timeframe(df, result)
    validate_key_nulls(df, result)
    validate_duplicates(df, result)
    return result


def main():
    """Main execution function."""
    print("=" * 60)
    print("History Update Script")
    print("=" * 60)
    print()

    print("Step 1: Reading Excel workbook")
    excel_data = read_excel_data(EXCEL_PATH)
    if excel_data.empty:
        print("ERROR: No data found in Excel workbook")
        sys.exit(1)
    print()

    print("Step 2: Validating data")
    validation_result = validate_dataframe(excel_data)
    print(validation_result.get_report())
    print()
    if not validation_result.is_valid:
        print("ERROR: Validation failed. Please fix errors in Excel workbook.")
        sys.exit(1)

    print("Step 3: Recalculating ATR Distance")
    excel_data = recalculate_atr_distance(excel_data)
    print("✓ ATR Distance recalculated")
    print()

    print("Step 4: Loading existing history")
    existing_history = load_history()
    print()

    print("Step 5: Removing duplicates")
    new_records = remove_duplicates(excel_data, existing_history)
    print()

    print("Step 6: Appending to history.csv")
    if not new_records.empty:
        updated_history = pd.concat([existing_history, new_records], ignore_index=True)
        updated_history = updated_history.sort_values(['Date', 'Asset', 'Timeframe'])
        updated_history.to_csv(HISTORY_CSV_PATH, index=False)
        print(f"✓ Saved {len(updated_history)} total records to {HISTORY_CSV_PATH}")
    else:
        print("No new records to append")
        updated_history = existing_history
    print()

    print("Step 7: Updating master.csv")
    master_data = update_master(updated_history)
    master_data.to_csv(MASTER_CSV_PATH, index=False)
    print(f"✓ Saved {len(master_data)} records to {MASTER_CSV_PATH}")
    print()

    print("Step 8: Saving metadata")
    asset_count = updated_history['Asset'].nunique() if not updated_history.empty else 0
    save_metadata(len(updated_history), asset_count)
    print()

    print("=" * 60)
    print("History update completed successfully")
    print("=" * 60)


if __name__ == "__main__":
    main()
