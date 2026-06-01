#!/usr/bin/env python3
"""
History Update Script
Reads Excel workbook, validates data, appends to history.csv, updates master.csv.
"""

import pandas as pd
import numpy as np
from datetime import datetime
import json
import sys
import os

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_data import validate_excel, ValidationResult


EXCEL_PATH = 'ATR_Tracker_Dashboard.xlsx'
MASTER_CSV_PATH = 'data/master.csv'
HISTORY_CSV_PATH = 'data/history.csv'
METADATA_JSON_PATH = 'data/metadata.json'


def recalculate_atr_distance(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recalculate ATR Distance: (Price - EMA21) / ATR
    Never trust stored ATR_Distance values.
    """
    df = df.copy()
    
    # Calculate ATR Distance
    df['ATR_Distance'] = (df['Price'] - df['EMA21']) / df['ATR']
    
    # Recalculate Percent Above EMA
    df['Pct_Above_EMA'] = ((df['Price'] - df['EMA21']) / df['EMA21']) * 100
    
    return df


def load_history() -> pd.DataFrame:
    """Load existing history.csv or return empty DataFrame."""
    if os.path.exists(HISTORY_CSV_PATH):
        df = pd.read_csv(HISTORY_CSV_PATH)
        print(f"Loaded existing history: {len(df)} records")
        return df
    else:
        print("No existing history.csv found, will create new file")
        return pd.DataFrame()


def load_master() -> pd.DataFrame:
    """Load existing master.csv or return empty DataFrame."""
    if os.path.exists(MASTER_CSV_PATH):
        df = pd.read_csv(MASTER_CSV_PATH)
        print(f"Loaded existing master: {len(df)} records")
        return df
    else:
        print("No existing master.csv found, will create new file")
        return pd.DataFrame()


def read_excel_data(excel_path: str) -> pd.DataFrame:
    """Read all data from Excel workbook."""
    all_data = []
    
    try:
        xl = pd.ExcelFile(excel_path)
        print(f"Reading Excel file: {excel_path}")
        print(f"Available sheets: {', '.join(xl.sheet_names)}")
        
        for sheet_name in xl.sheet_names:
            print(f"  Reading sheet: {sheet_name}")
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            
            # Normalize column names
            df.columns = df.columns.str.strip()
            
            # Check if this sheet has the expected columns
            if 'Date' in df.columns and 'Asset' in df.columns:
                all_data.append(df)
                print(f"    Added {len(df)} records from {sheet_name}")
            else:
                print(f"    Skipping {sheet_name} (missing required columns)")
        
        if all_data:
            combined = pd.concat(all_data, ignore_index=True)
            print(f"Total records from Excel: {len(combined)}")
            return combined
        else:
            print("No valid data found in Excel sheets")
            return pd.DataFrame()
    
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return pd.DataFrame()


def remove_duplicates(new_data: pd.DataFrame, existing_history: pd.DataFrame) -> pd.DataFrame:
    """
    Remove records that already exist in history based on Date+Asset+Timeframe.
    Returns only new records to append.
    """
    if existing_history.empty:
        return new_data
    
    # Normalize timeframe for comparison
    new_data_norm = new_data.copy()
    new_data_norm['Timeframe'] = new_data_norm['Timeframe'].fillna('').str.lower().replace({'daily': '1d', 'weekly': '1w'})
    
    existing_norm = existing_history.copy()
    existing_norm['Timeframe'] = existing_norm['Timeframe'].fillna('').str.lower().replace({'daily': '1d', 'weekly': '1w'})
    
    # Create composite key
    new_data_norm['composite_key'] = (
        new_data_norm['Date'].fillna('').astype(str) + '|' + 
        new_data_norm['Asset'].fillna('').astype(str) + '|' + 
        new_data_norm['Timeframe'].fillna('').astype(str)
    )
    
    existing_norm['composite_key'] = (
        existing_norm['Date'].fillna('').astype(str) + '|' + 
        existing_norm['Asset'].fillna('').astype(str) + '|' + 
        existing_norm['Timeframe'].fillna('').astype(str)
    )
    
    # Filter out records that already exist
    new_records = new_data_norm[~new_data_norm['composite_key'].isin(existing_norm['composite_key'])]
    
    # Remove the composite key column
    new_records = new_records.drop(columns=['composite_key'])
    
    print(f"Found {len(new_records)} new records to append (skipped {len(new_data) - len(new_records)} duplicates)")
    
    return new_records


def update_master(df: pd.DataFrame) -> pd.DataFrame:
    """
    Update master.csv with the latest snapshot for each Asset+Timeframe combination.
    """
    if df.empty:
        return df
    
    # Sort by date descending to get latest records first
    df_sorted = df.sort_values('Date', ascending=False)
    
    # Get latest record for each Asset+Timeframe
    latest = df_sorted.groupby(['Asset', 'Timeframe']).first().reset_index()
    
    print(f"Updated master with {len(latest)} latest records")
    
    return latest


def save_metadata(record_count: int, asset_count: int):
    """Save metadata.json with update information."""
    metadata = {
        'last_updated': datetime.utcnow().isoformat() + 'Z',
        'records_count': record_count,
        'assets_count': asset_count,
        'history_file': HISTORY_CSV_PATH,
        'master_file': MASTER_CSV_PATH
    }
    
    with open(METADATA_JSON_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Saved metadata to {METADATA_JSON_PATH}")


def main():
    """Main execution function."""
    print("=" * 60)
    print("History Update Script")
    print("=" * 60)
    print()
    
    # Step 1: Read Excel data
    print("Step 1: Reading Excel workbook")
    excel_data = read_excel_data(EXCEL_PATH)
    
    if excel_data.empty:
        print("ERROR: No data found in Excel workbook")
        sys.exit(1)
    
    print()
    
    # Step 2: Validate data
    print("Step 2: Validating data")
    validation_result = validate_dataframe(excel_data)
    print(validation_result.get_report())
    print()
    
    if not validation_result.is_valid:
        print("ERROR: Validation failed. Please fix errors in Excel workbook.")
        sys.exit(1)
    
    # Step 3: Recalculate ATR Distance
    print("Step 3: Recalculating ATR Distance")
    excel_data = recalculate_atr_distance(excel_data)
    print("✓ ATR Distance recalculated")
    print()
    
    # Step 4: Load existing history
    print("Step 4: Loading existing history")
    existing_history = load_history()
    print()
    
    # Step 5: Remove duplicates
    print("Step 5: Removing duplicates")
    new_records = remove_duplicates(excel_data, existing_history)
    print()
    
    # Step 6: Append to history
    print("Step 6: Appending to history.csv")
    if not new_records.empty:
        # Combine existing and new
        updated_history = pd.concat([existing_history, new_records], ignore_index=True)
        # Sort by date
        updated_history = updated_history.sort_values(['Date', 'Asset', 'Timeframe'])
        # Save
        updated_history.to_csv(HISTORY_CSV_PATH, index=False)
        print(f"✓ Saved {len(updated_history)} total records to {HISTORY_CSV_PATH}")
    else:
        print("No new records to append")
        updated_history = existing_history
    print()
    
    # Step 7: Update master
    print("Step 7: Updating master.csv")
    master_data = update_master(updated_history)
    master_data.to_csv(MASTER_CSV_PATH, index=False)
    print(f"✓ Saved {len(master_data)} records to {MASTER_CSV_PATH}")
    print()
    
    # Step 8: Save metadata
    print("Step 8: Saving metadata")
    asset_count = updated_history['Asset'].nunique() if not updated_history.empty else 0
    save_metadata(len(updated_history), asset_count)
    print()
    
    print("=" * 60)
    print("History update completed successfully")
    print("=" * 60)


def validate_dataframe(df: pd.DataFrame):
    """Helper function to validate DataFrame (reusing validate_data logic)."""
    from validate_data import ValidationResult, validate_columns, validate_numeric_fields, validate_atr, validate_rsi, validate_timeframe
    
    result = ValidationResult()
    validate_columns(df, result)
    validate_numeric_fields(df, result)
    validate_atr(df, result)
    validate_rsi(df, result)
    validate_timeframe(df, result)
    return result


if __name__ == "__main__":
    main()
