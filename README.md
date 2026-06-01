# Multi-Asset ATR Tracker

Automated pipeline that fetches daily and weekly OHLCV data from Binance (crypto) and Yahoo Finance (stocks/ETFs), calculates technical indicators, accumulates historical data, and serves an interactive web dashboard via Cloudflare Pages.

## Features

- **Data sources:** Binance (no API key required) and Yahoo Finance; manual fallback for assets without API access
- **Indicators:** EMA21, ATR (14-period, Wilder's smoothing), RSI (14-period, Wilder's smoothing), RSI Z-score (20-period), ATR Distance, % Above EMA
- **Timeframes:** Daily (`1d`) and Weekly (`1w`)
- **Regime classification** based on ATR Distance thresholds
- **29 tracked assets** across crypto, NASDAQ stocks, and LSE ETFs
- **Automated daily pipeline** via GitHub Actions

## Assets

| Category | Symbols |
|----------|---------|
| Crypto (Binance) | BTC, ETH, SOL, XLM, REZ, RSR, NEAR, RENDER, ONDO, ACH, BNB, XRP |
| NASDAQ stocks | MSTR, XXI, RIOT, MARA, IREN, BMNR, HUT, WULF, HIVE, CLSK, SLNH |
| LSE ETFs | MSTY, YMST, MARY, RIOY, IREY, BMNY |

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Daily tracker (current data only)

```bash
python crypto_tracker.py
```

Writes to `data/master.csv` and `ATR_Tracker_Dashboard.xlsx`.

### Full pipeline

```bash
python crypto_tracker.py
python scripts/validate_data.py ATR_Tracker_Dashboard.xlsx
python scripts/update_history.py
python scripts/calculate_metrics.py
python scripts/build_dashboard.py
```

### Backfill (Jan 2024 to present)

```bash
python backfill_historical.py
```

Re-run this after any change to ATR or RSI calculation to regenerate `data/history.csv` with corrected values.

## Configuration

All shared configuration lives in `trading_utils/config.py`:

- `ASSETS` — list of asset names to track
- `ASSET_CONFIG` — maps each asset to its data source and symbol
- `MANUAL_DATA` — manual price/indicator values for assets without API access
- `EMA_PERIOD`, `ATR_PERIOD`, `RSI_PERIOD`, `Z_SCORE_PERIOD` — indicator parameters

## Adding New Assets

**Binance or Yahoo Finance:**

1. Add the asset name to `ASSETS` in `trading_utils/config.py`
2. Add an entry to `ASSET_CONFIG`:
   ```python
   'MSTR': {'source': 'yahoo', 'symbol': 'MSTR'},
   'BTC':  {'source': 'binance', 'symbol': 'BTC/USDT'},
   'MSTY': {'source': 'yahoo', 'symbol': 'MSTY.L'},  # LSE: append .L
   ```

**Manual assets (no API):**

1. Add to `ASSETS` and `ASSET_CONFIG` with `'source': 'manual'`
2. Add values to `MANUAL_DATA`:
   ```python
   MANUAL_DATA = {
       'MYTOKEN': {
           '1d': {'price': 0.0079, 'ema21': 0.0082, 'atr': 0.0003, 'rsi': 45.0},
           '1w': {'price': 0.0079, 'ema21': 0.0080, 'atr': 0.0004, 'rsi': 50.0},
       },
   }
   ```
3. Update values from TradingView or Birdeye before each run

## Data Files

| File | Description |
|------|-------------|
| `ATR_Tracker_Dashboard.xlsx` | Excel workbook (single `Data` sheet); written by tracker and backfill |
| `data/history.csv` | Full historical accumulation — authoritative source |
| `data/master.csv` | Latest row per Asset+Timeframe — derived from history |
| `data/dashboard.json` | Processed metrics for the web dashboard |

## GitHub Actions

The workflow (`.github/workflows/crypto-tracker.yml`) runs daily at 09:00 UTC and on manual dispatch:

1. Fetch current OHLCV data (`crypto_tracker.py`)
2. Validate Excel output (`validate_data.py`)
3. Append to history CSV (`update_history.py`)
4. Calculate metrics and regime classification (`calculate_metrics.py`)
5. Build dashboard assets (`build_dashboard.py`)
6. Commit data files and deploy to Cloudflare Pages

## Notes

- LSE ETFs require the `.L` suffix for Yahoo Finance (e.g., `MSTY.L`)
- Assets unavailable from the API are skipped with a warning; if more than 3 fail, the CI job exits non-zero
- The pipeline is idempotent — re-running does not create duplicate rows in `history.csv`
- `data/history.csv` is the source of truth; all other data files are derived from it
