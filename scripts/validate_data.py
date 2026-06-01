#!/usr/bin/env python3
"""
Data Validation Script
Validates trading data from Excel workbook or CSV files.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import sys


class ValidationResult:
    """Container for validation results."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.is_valid = True
    
    def add_error(self, message: str):
        """Add an error message."""
        self.errors.append(message)
        self.is_valid = False
    
    def add_warning(self, message: str):
        """Add a warning message."""
        self.warnings.append(message)
    
    def get_report(self) -> str:
        """Generate a human-readable report."""
        report = []
        
        if self.is_valid:
            report.append("✓ Validation passed")
        else:
            report.append(f"✗ Validation failed: {len(self.errors)} error(s)")
        
        if self.errors:
            report.append("\nErrors:")
            for error in self.errors:
                report.append(f"  - {error}")
        
        if self.warnings:
            report.append("\nWarnings:")
            for warning in self.warnings:
                report.append(f"  - {warning}")
        
        return "\n".join(report)


def validate_columns(df: pd.DataFrame, result: ValidationResult):
    """Validate required columns exist."""
    required_columns = ['Date', 'Asset', 'Price', 'EMA21', 'ATR', 'RSI', 'Timeframe']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        result.add_error(f"Missing required columns: {', '.join(missing_columns)}")
    else:
        print(f"✓ All required columns present: {', '.join(required_columns)}")


def validate_numeric_fields(df: pd.DataFrame, result: ValidationResult):
    """Validate that numeric fields contain numeric data."""
    numeric_columns = ['Price', 'EMA21', 'ATR', 'RSI']
    
    for col in numeric_columns:
        if col not in df.columns:
            continue
        
        # Check for non-numeric values
        non_numeric = df[~df[col].apply(lambda x: pd.api.types.is_numeric_dtype(type(x)) or pd.isna(x))]
        
        if len(non_numeric) > 0:
            result.add_error(f"Column '{col}' contains non-numeric values in {len(non_numeric)} row(s)")
        else:
            print(f"✓ Column '{col}' contains valid numeric data")


def validate_atr(df: pd.DataFrame, result: ValidationResult):
    """Validate ATR values are greater than 0."""
    if 'ATR' not in df.columns:
        return
    
    invalid_atr = df[(df['ATR'] <= 0) & (df['ATR'].notna())]
    
    if len(invalid_atr) > 0:
        result.add_error(f"ATR must be > 0, found {len(invalid_atr)} invalid value(s)")
        # Show first few examples
        for idx, row in invalid_atr.head(3).iterrows():
            result.add_error(f"  Row {idx}: Asset={row.get('Asset', 'N/A')}, ATR={row['ATR']}")
    else:
        print("✓ All ATR values are > 0")


def validate_rsi(df: pd.DataFrame, result: ValidationResult):
    """Validate RSI values are between 0 and 100."""
    if 'RSI' not in df.columns:
        return
    
    invalid_rsi = df[((df['RSI'] < 0) | (df['RSI'] > 100)) & (df['RSI'].notna())]
    
    if len(invalid_rsi) > 0:
        result.add_error(f"RSI must be between 0 and 100, found {len(invalid_rsi)} invalid value(s)")
        # Show first few examples
        for idx, row in invalid_rsi.head(3).iterrows():
            result.add_error(f"  Row {idx}: Asset={row.get('Asset', 'N/A')}, RSI={row['RSI']}")
    else:
        print("✓ All RSI values are between 0 and 100")


def validate_timeframe(df: pd.DataFrame, result: ValidationResult):
    """Validate Timeframe values are '1d' or '1w'."""
    if 'Timeframe' not in df.columns:
        return
    
    valid_timeframes = ['1d', '1w', 'Daily', 'Weekly']
    invalid_timeframe = df[~df['Timeframe'].isin(valid_timeframes) & (df['Timeframe'].notna())]
    
    if len(invalid_timeframe) > 0:
        result.add_error(f"Timeframe must be '1d', '1w', 'Daily', or 'Weekly', found {len(invalid_timeframe)} invalid value(s)")
        # Show unique invalid values
        unique_invalid = invalid_timeframe['Timeframe'].unique()
        result.add_error(f"  Invalid values: {', '.join(map(str, unique_invalid))}")
    else:
        print("✓ All Timeframe values are valid")


def validate_duplicates(df: pd.DataFrame, result: ValidationResult):
    """Check for duplicate Date+Asset+Timeframe records."""
    required_cols = ['Date', 'Asset', 'Timeframe']
    missing = [col for col in required_cols if col not in df.columns]
    
    if missing:
        result.add_warning(f"Cannot check duplicates: missing columns {', '.join(missing)}")
        return
    
    # Normalize timeframe to lowercase for comparison
    df_normalized = df.copy()
    df_normalized['Timeframe'] = df_normalized['Timeframe'].str.lower().replace({'daily': '1d', 'weekly': '1w'})
    
    duplicates = df_normalized[df_normalized.duplicated(subset=required_cols, keep=False)]
    
    if len(duplicates) > 0:
        result.add_error(f"Found {len(duplicates)} duplicate Date+Asset+Timeframe record(s)")
        # Show first few examples
        for idx, row in duplicates.head(5).iterrows():
            result.add_error(f"  Duplicate: Date={row['Date']}, Asset={row['Asset']}, Timeframe={row['Timeframe']}")
    else:
        print("✓ No duplicate Date+Asset+Timeframe records found")


def validate_dataframe(df: pd.DataFrame) -> ValidationResult:
    """Run all validation checks on a DataFrame."""
    result = ValidationResult()
    
    print("Running validation checks...")
    print(f"Total records: {len(df)}")
    print()
    
    validate_columns(df, result)
    validate_numeric_fields(df, result)
    validate_atr(df, result)
    validate_rsi(df, result)
    validate_timeframe(df, result)
    validate_duplicates(df, result)
    
    return result


def validate_csv(file_path: str) -> ValidationResult:
    """Validate a CSV file."""
    try:
        df = pd.read_csv(file_path)
        print(f"Loaded CSV: {file_path}")
        return validate_dataframe(df)
    except Exception as e:
        result = ValidationResult()
        result.add_error(f"Failed to read CSV file: {e}")
        return result


def validate_excel(file_path: str, sheet_name: str = None) -> ValidationResult:
    """Validate an Excel workbook."""
    try:
        if sheet_name:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            print(f"Loaded Excel sheet '{sheet_name}': {file_path}")
        else:
            # Validate all sheets
            xl = pd.ExcelFile(file_path)
            print(f"Loaded Excel file: {file_path}")
            print(f"Sheets: {', '.join(xl.sheet_names)}")
            
            result = ValidationResult()
            for sheet in xl.sheet_names:
                print(f"\nValidating sheet: {sheet}")
                sheet_result = validate_dataframe(pd.read_excel(file_path, sheet_name=sheet))
                result.errors.extend(sheet_result.errors)
                result.warnings.extend(sheet_result.warnings)
                if not sheet_result.is_valid:
                    result.is_valid = False
            
            return result
        
        return validate_dataframe(df)
    except Exception as e:
        result = ValidationResult()
        result.add_error(f"Failed to read Excel file: {e}")
        return result


def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Validate trading data')
    parser.add_argument('file', help='Path to CSV or Excel file')
    parser.add_argument('--sheet', help='Excel sheet name (optional)')
    parser.add_argument('--type', choices=['csv', 'excel'], help='File type (auto-detected if not specified)')
    
    args = parser.parse_args()
    
    # Auto-detect file type
    if args.type is None:
        if args.file.endswith('.csv'):
            args.type = 'csv'
        elif args.file.endswith(('.xlsx', '.xls')):
            args.type = 'excel'
        else:
            print("Error: Cannot auto-detect file type. Please specify --type")
            sys.exit(1)
    
    # Run validation
    if args.type == 'csv':
        result = validate_csv(args.file)
    else:
        result = validate_excel(args.file, args.sheet)
    
    # Print report
    print()
    print("=" * 60)
    print(result.get_report())
    print("=" * 60)
    
    # Exit with appropriate code
    sys.exit(0 if result.is_valid else 1)


if __name__ == "__main__":
    main()
