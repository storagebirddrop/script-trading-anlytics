"""
Data validation logic shared between scripts/validate_data.py and scripts/update_history.py.
"""

import pandas as pd


class ValidationResult:
    """Container for validation results."""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.is_valid = True

    def add_error(self, message: str):
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str):
        self.warnings.append(message)

    def get_report(self) -> str:
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
    required = ['Date', 'Asset', 'Price', 'EMA21', 'ATR', 'RSI', 'Timeframe']
    missing = [c for c in required if c not in df.columns]
    if missing:
        result.add_error(f"Missing required columns: {', '.join(missing)}")
    else:
        print(f"✓ All required columns present: {', '.join(required)}")


def validate_key_nulls(df: pd.DataFrame, result: ValidationResult):
    for col in ['Date', 'Asset', 'Timeframe']:
        if col not in df.columns:
            continue
        null_count = df[col].isna().sum()
        if null_count > 0:
            result.add_error(f"Column '{col}' contains {null_count} null/NaN value(s)")
        else:
            print(f"✓ Column '{col}' has no null values")


def validate_numeric_fields(df: pd.DataFrame, result: ValidationResult):
    for col in ['Price', 'EMA21', 'ATR', 'RSI']:
        if col not in df.columns:
            continue
        coerced = pd.to_numeric(df[col], errors='coerce')
        bad = df[coerced.isna() & df[col].notna()]
        if len(bad) > 0:
            result.add_error(f"Column '{col}' contains non-numeric values in {len(bad)} row(s)")
        else:
            print(f"✓ Column '{col}' contains valid numeric data")


def validate_atr(df: pd.DataFrame, result: ValidationResult):
    if 'ATR' not in df.columns:
        return
    invalid = df[(df['ATR'] <= 0) & df['ATR'].notna()]
    if len(invalid) > 0:
        result.add_error(f"ATR must be > 0, found {len(invalid)} invalid value(s)")
        for idx, row in invalid.head(3).iterrows():
            result.add_error(f"  Row {idx}: Asset={row.get('Asset', 'N/A')}, ATR={row['ATR']}")
    else:
        print("✓ All ATR values are > 0")


def validate_rsi(df: pd.DataFrame, result: ValidationResult):
    if 'RSI' not in df.columns:
        return
    invalid = df[((df['RSI'] < 0) | (df['RSI'] > 100)) & df['RSI'].notna()]
    if len(invalid) > 0:
        result.add_error(f"RSI must be between 0 and 100, found {len(invalid)} invalid value(s)")
        for idx, row in invalid.head(3).iterrows():
            result.add_error(f"  Row {idx}: Asset={row.get('Asset', 'N/A')}, RSI={row['RSI']}")
    else:
        print("✓ All RSI values are between 0 and 100")


def validate_timeframe(df: pd.DataFrame, result: ValidationResult):
    if 'Timeframe' not in df.columns:
        return
    valid = {'1d', '1w', 'Daily', 'Weekly'}
    invalid = df[~df['Timeframe'].isin(valid) & df['Timeframe'].notna()]
    if len(invalid) > 0:
        result.add_error(
            f"Timeframe must be one of {valid}, found {len(invalid)} invalid value(s): "
            f"{', '.join(map(str, invalid['Timeframe'].unique()))}"
        )
    else:
        print("✓ All Timeframe values are valid")


def validate_duplicates(df: pd.DataFrame, result: ValidationResult):
    required_cols = ['Date', 'Asset', 'Timeframe']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        result.add_warning(f"Cannot check duplicates: missing columns {', '.join(missing)}")
        return

    missing_mask = df[required_cols].isna().any(axis=1)
    if missing_mask.any():
        result.add_warning(
            f"{missing_mask.sum()} row(s) with missing Date/Asset/Timeframe excluded from duplicate check"
        )

    df_norm = df.copy()
    df_norm['Timeframe'] = (
        df_norm['Timeframe'].fillna('').str.lower()
        .replace({'daily': '1d', 'weekly': '1w'})
    )
    df_clean = df_norm[~df[required_cols].isna().any(axis=1)]
    dupes = df_clean[df_clean.duplicated(subset=required_cols, keep=False)]
    if len(dupes) > 0:
        result.add_error(f"Found {len(dupes)} duplicate Date+Asset+Timeframe record(s)")
        for idx, row in dupes.head(5).iterrows():
            result.add_error(
                f"  Duplicate: Date={row['Date']}, Asset={row['Asset']}, Timeframe={row['Timeframe']}"
            )
    else:
        print("✓ No duplicate Date+Asset+Timeframe records found")


def validate_dataframe(df: pd.DataFrame) -> ValidationResult:
    """Run all validation checks on a DataFrame."""
    result = ValidationResult()
    print(f"Running validation checks on {len(df)} records...")
    validate_columns(df, result)
    validate_key_nulls(df, result)
    validate_numeric_fields(df, result)
    validate_atr(df, result)
    validate_rsi(df, result)
    validate_timeframe(df, result)
    validate_duplicates(df, result)
    return result
