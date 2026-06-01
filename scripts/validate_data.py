#!/usr/bin/env python3
"""
Data Validation Script — CLI wrapper around trading_utils.validation.
Validates trading data from an Excel workbook or CSV file.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from trading_utils.validation import ValidationResult, validate_dataframe  # noqa: F401 (re-exported for importers)


def validate_csv(file_path: str) -> ValidationResult:
    try:
        df = pd.read_csv(file_path)
        print(f"Loaded CSV: {file_path}")
        return validate_dataframe(df)
    except Exception as e:
        result = ValidationResult()
        result.add_error(f"Failed to read CSV file: {e}")
        return result


def validate_excel(file_path: str, sheet_name: str = None) -> ValidationResult:
    try:
        if sheet_name:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            print(f"Loaded Excel sheet '{sheet_name}': {file_path}")
            return validate_dataframe(df)

        xl = pd.ExcelFile(file_path)
        print(f"Loaded Excel file: {file_path} — sheets: {', '.join(xl.sheet_names)}")
        result = ValidationResult()
        for sheet in xl.sheet_names:
            print(f"\nValidating sheet: {sheet}")
            sheet_result = validate_dataframe(pd.read_excel(file_path, sheet_name=sheet))
            result.errors.extend(sheet_result.errors)
            result.warnings.extend(sheet_result.warnings)
            if not sheet_result.is_valid:
                result.is_valid = False
        return result
    except Exception as e:
        result = ValidationResult()
        result.add_error(f"Failed to read Excel file: {e}")
        return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Validate trading data')
    parser.add_argument('file', help='Path to CSV or Excel file')
    parser.add_argument('--sheet', help='Excel sheet name (optional)')
    parser.add_argument('--type', choices=['csv', 'excel'],
                        help='File type (auto-detected if not specified)')
    args = parser.parse_args()

    if args.type is None:
        if args.file.endswith('.csv'):
            args.type = 'csv'
        elif args.file.endswith(('.xlsx', '.xls')):
            args.type = 'excel'
        else:
            print("Error: Cannot auto-detect file type. Please specify --type")
            sys.exit(1)

    result = validate_csv(args.file) if args.type == 'csv' else validate_excel(args.file, args.sheet)

    print()
    print("=" * 60)
    print(result.get_report())
    print("=" * 60)
    sys.exit(0 if result.is_valid else 1)


if __name__ == "__main__":
    main()
