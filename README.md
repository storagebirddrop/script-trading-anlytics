# Multi-Asset ATR Tracker

Automated script that fetches OHLCV data from multiple sources (Binance for crypto, Yahoo Finance for stocks/ETFs, manual input for Solana tokens), calculates technical indicators, and updates an Excel spreadsheet with historical data accumulation.

## Features

- Fetches OHLCV data from multiple sources:
  - Binance for crypto assets (no API key required)
  - Yahoo Finance for stocks and ETFs
  - Manual input for assets without API access (e.g., Solana DEX tokens)
- Calculates technical indicators:
  - EMA21 (Exponential Moving Average)
  - ATR (Average True Range, 14-period)
  - RSI (Relative Strength Index, 14-period)
  - RSI Z-score (20-period)
  - ATR Distance
  - % Above EMA
- Supports multiple asset classes:
  - Crypto: BTC, ETH, SOL, XLM, REZ, RSR, NEAR, RENDER, ONDO, ACH, BNB, XRP
  - NASDAQ stocks: MSTR, XXI, RIOT, MARA, IREN, BMNR, HUT, WULF, HIVE, CLSK, SLNH
  - LSE ETFs: MSTY, YMST, MARY, RIOY, IREY, BMNY
- Runs on both daily and weekly timeframes
- **Accumulates historical data** in Daily_Data and Weekly_Data sheets for 12-24 month analysis

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Manual Run

```bash
python crypto_tracker.py
```

### GitHub Actions

The workflow is configured to:
- Run daily at 9:00 AM UTC
- Allow manual triggering via GitHub Actions UI

The workflow will:
1. Install dependencies
2. Run the crypto tracker script
3. Commit and push the updated spreadsheet to the repository

## Spreadsheet Format

Each new sheet contains the following columns:

| Date | Asset | Price | EMA21 | ATR | RSI | ATR Distance | % Above EMA | Timeframe |
|------|-------|-------|-------|-----|-----|--------------|-------------|-----------|

## Configuration

Edit the following constants in `crypto_tracker.py`:

- `ASSETS`: List of assets to track (crypto, stocks, ETFs, manual)
- `TIMEFRAMES`: Timeframes to fetch (e.g., '1d', '1w')
- `SPREADSHEET_PATH`: Path to the Excel file
- `ASSET_CONFIG`: Mapping of asset names to data source and symbol
- `MANUAL_DATA`: Manual data input for assets without API access
- Indicator periods: `EMA_PERIOD`, `ATR_PERIOD`, `RSI_PERIOD`, `Z_SCORE_PERIOD`

## Adding New Assets

### Automated Assets (Binance/Yahoo Finance)

1. Add the asset name to the `ASSETS` list
2. Add an entry to `ASSET_CONFIG` with:
   - `source`: 'binance' for crypto, 'yahoo' for stocks/ETFs
   - `symbol`: The trading symbol (e.g., 'BTC/USDT' for Binance, 'AAPL' for Yahoo Finance)
   - For LSE stocks, append '.L' to the symbol (e.g., 'MSTY.L')

### Manual Assets

1. Add the asset name to the `ASSETS` list
2. Add an entry to `ASSET_CONFIG` with:
   - `source`: 'manual'
3. Add data to `MANUAL_DATA` dictionary:
   ```python
   'ASSET_NAME': {
       '1d': {'price': 0.0079, 'ema21': 0.0082, 'atr': 0.0003, 'rsi': 45.0},
       '1w': {'price': 0.0079, 'ema21': 0.0080, 'atr': 0.0004, 'rsi': 50.0},
   },
   ```
4. Update values from TradingView, Birdeye, or other sources before each run

## Notes

- RENDER is mapped to RNDR on Binance
- LSE ETFs use the '.L' suffix for Yahoo Finance
- Some assets may not be available and will be skipped with a warning
- The script preserves existing sheets and graphs in the spreadsheet
- Weekly timeframe for some newer ETFs may return NaN for indicators due to insufficient historical data
