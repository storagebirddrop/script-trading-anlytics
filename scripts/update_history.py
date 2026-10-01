#!/usr/bin/env python3
"""
History Update Script
Reads Excel workbook, validates data, appends to history.csv, updates master.csv.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from trading_utils import (
    SPREADSHEET_PATH,
    MASTER_CSV_PATH,
    HISTORY_CSV_PATH,
    METADATA_JSON_PATH,
)
from trading_utils.validation import (
    ValidationResult,
    validate_columns,
    validate_numeric_fields,
    validate_atr,
    validate_rsi,
    validate_timeframe,
    validate_key_nulls,
    validate_duplicates,
)

EXCEL_PATH = SPREADSHEET_PATH


def recalculate_atr_distance(df: pd.DataFrame) -> pd.DataFrame:
    """Recalculate ATR_Distance and Pct_Above_EMA from raw columns (H2)."""
    df = df.copy()
    safe_atr = df['ATR'].replace(0, np.nan)
    df['ATR_Distance'] = ((df['Price'] - df['EMA21']) / safe_atr).replace([np.inf, -np.inf], np.nan)
    df['Pct_Above_EMA'] = ((df['Price'] - df['EMA21']) / df['EMA21']) * 100
    return df


# Positional layout of the Excel sheet written by crypto_tracker.py / backfill_historical.py.
EXCEL_COLUMNS = [
    'Date', 'Asset', 'Timeframe', 'Price', 'EMA21', 'ATR',
    'RSI', 'RSI_Z_Score', 'ATR_Distance', 'Pct_Above_EMA',
    'High', 'Low', 'Volume',
]
_OHLCV_COLUMNS = ['High', 'Low', 'Volume']


def name_unnamed_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Give headerless Excel columns their real names by position.

    The workbook predates the High/Low/Volume columns, so its header row only
    has 10 names while the writers fill columns K-M. pandas then reads those
    as 'Unnamed: 10/11/12' and the values never reach History.
    """
    renames = {}
    for pos, name in enumerate(EXCEL_COLUMNS):
        if pos < len(df.columns) and str(df.columns[pos]).startswith('Unnamed'):
            renames[df.columns[pos]] = name
    return df.rename(columns=renames) if renames else df


def merge_legacy_unnamed_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Fold 'Unnamed: 10/11/12' (legacy High/Low/Volume) into the named columns.

    Existing values in High/Low/Volume win; the Unnamed values only fill gaps.
    The Unnamed columns are dropped afterwards.
    """
    df = df.copy()
    for legacy, name in zip(('Unnamed: 10', 'Unnamed: 11', 'Unnamed: 12'), _OHLCV_COLUMNS):
        if legacy in df.columns:
            if name in df.columns:
                df[name] = df[name].fillna(df[legacy])
            else:
                df[name] = df[legacy]
    return df.drop(columns=[c for c in df.columns if str(c).startswith('Unnamed')])


def load_history() -> pd.DataFrame:
    """Load existing history.csv or return empty DataFrame."""
    if os.path.exists(HISTORY_CSV_PATH):
        df = pd.read_csv(HISTORY_CSV_PATH)
        if any(str(c).startswith('Unnamed') for c in df.columns):
            df = merge_legacy_unnamed_columns(df)
            print("Repaired legacy 'Unnamed' columns in history.csv (merged into High/Low/Volume)")
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
        df.columns = df.columns.astype(str).str.strip()
        df = name_unnamed_columns(df)
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
        return series.fillna('').str.lower().replace({'daily': '1d', 'weekly': '1w', 'monthly': '1m'})

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


_BAR_VALUE_COLUMNS = [
    'Price', 'EMA21', 'ATR', 'RSI', 'RSI_Z_Score', 'ATR_Distance', 'Pct_Above_EMA',
    'High', 'Low', 'Volume',
]


RECENT_WINDOW_DAYS = 45  # covers the open weekly (<=7d) and monthly (<=31d) bar


def recent_rows(excel_data: pd.DataFrame, days: int = RECENT_WINDOW_DAYS) -> pd.DataFrame:
    """Keep only Excel rows from the last `days` days (relative to the newest daily bar).

    The workbook keeps every row it was ever given, including ones a later backfill
    replaced in history.csv. Importing "any key history lacks" re-adds those stale
    rows (empty prices, missing High/Low, delisted assets) on every run. The tracker
    only ever writes the latest bar, so nothing recent is lost by this window.
    """
    if excel_data.empty:
        return excel_data
    dates = pd.to_datetime(excel_data['Date'], errors='coerce')
    tf = (
        excel_data['Timeframe'].fillna('').astype(str).str.lower()
        .replace({'daily': '1d', 'weekly': '1w', 'monthly': '1m'})
    )
    reference = dates[tf == '1d'].max() if (tf == '1d').any() else dates.max()
    return excel_data[dates >= reference - pd.Timedelta(days=days)]


def _bar_keys(df: pd.DataFrame) -> pd.Series:
    """Date|Asset|timeframe key per row (Daily/Weekly/Monthly normalised)."""
    tf = (
        df['Timeframe'].fillna('').astype(str).str.lower()
        .replace({'daily': '1d', 'weekly': '1w', 'monthly': '1m'})
    )
    return df['Date'].fillna('').astype(str) + '|' + df['Asset'].fillna('').astype(str) + '|' + tf


def refresh_open_bars(history: pd.DataFrame, excel_data: pd.DataFrame):
    """Refresh the still-open (latest) bar of every Asset+Timeframe from the Excel data.

    A weekly or monthly bar keeps the same Date for the whole period, so the
    duplicate check skips it after the first run and History keeps the first
    day's values until the period ends. The newest Excel row per
    Asset+Timeframe is the open bar; its values replace the stored ones.
    Rows without a Price (an unfinished bar) never overwrite stored values, and
    NaN never overwrites a stored value.

    Returns (history, number_of_rows_updated).
    """
    if history.empty or excel_data.empty:
        return history, 0

    latest = (
        excel_data.sort_values('Date', ascending=True)
        .groupby(['Asset', 'Timeframe'], as_index=False)
        .tail(1)
    )
    latest = latest[latest['Price'].notna()]
    if latest.empty:
        return history, 0

    position = {}
    for pos, key in enumerate(_bar_keys(history)):
        position[key] = pos

    columns = [c for c in _BAR_VALUE_COLUMNS if c in history.columns and c in latest.columns]
    updated = 0
    for key, (_, row) in zip(_bar_keys(latest), latest.iterrows()):
        pos = position.get(key)
        if pos is None:
            continue
        idx = history.index[pos]
        changed = False
        for col in columns:
            new = row[col]
            if pd.isna(new):
                continue
            old = history.at[idx, col]
            if pd.isna(old) or not np.isclose(float(old), float(new), rtol=1e-9, atol=0.0):
                history.at[idx, col] = float(new)
                changed = True
        updated += int(changed)
    return history, updated


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
        'last_updated': datetime.now(timezone.utc).isoformat(),
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
    recent = recent_rows(excel_data)
    print(f"Importing {len(recent)} of {len(excel_data)} Excel rows (last {RECENT_WINDOW_DAYS} days only)")
    new_records = remove_duplicates(recent, existing_history)
    print()

    print("Step 5b: Refreshing open (latest) weekly/monthly/daily bars")
    existing_history, refreshed = refresh_open_bars(existing_history, excel_data)
    print(f"Refreshed {refreshed} open bar(s) with newer values")
    print()

    print("Step 6: Appending to history.csv")
    legacy_repaired = os.path.exists(HISTORY_CSV_PATH) and any(
        str(c).startswith('Unnamed') for c in pd.read_csv(HISTORY_CSV_PATH, nrows=0).columns
    )
    if not new_records.empty or refreshed or legacy_repaired:
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
