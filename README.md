# Multi-Asset ATR Tracker

Automated pipeline that fetches daily and weekly OHLCV data from Yahoo Finance, Binance (CCXT), and GeckoTerminal, calculates technical indicators, accumulates historical data, and serves an interactive web dashboard via Cloudflare Pages.

## Features

- **Data sources:** Yahoo Finance (crypto + NASDAQ + LSE ETFs), Binance/CCXT (SCP), GeckoTerminal (D2X); manual fallback for assets without API access
- **Indicators:** EMA21, ATR (14-period, Wilder's smoothing), RSI (14-period, Wilder's smoothing), RSI Z-score (20-period), ATR Distance, % Above EMA
- **Volume Profile:** fixed-lookback price-by-volume distribution (POC, VAH, VAL, position classification) stored in `dashboard.json` and rendered as a horizontal bar chart in the Drilldown tab
- **Timeframes:** Daily (`1d`) and Weekly (`1w`)
- **Regime classification** based on ATR Distance thresholds (Capitulation → Accumulation → Trend → Distribution → Mania)
- **45 tracked assets** across crypto, NASDAQ stocks, and LSE ETFs
- **Automated daily pipeline** via GitHub Actions

## Assets

| Category | Symbols |
|----------|---------|
| Crypto (28) | BTC, ETH, SOL, XLM, REZ, RSR, NEAR, RENDER, ONDO, ACH, BNB, XRP, ADA, NIGHT, VTHO, LINK, NEO, GAS, DRIFT, SEI, PEAQ, AEVO, EIGEN, W, WOO, JASMY, D2X, SCP |
| NASDAQ stocks (11) | MSTR, XXI, RIOT, MARA, IREN, BMNR, HUT, WULF, HIVE, CLSK, SLNH |
| LSE ETFs (6) | MSTY, YMST, MARY, RIOY, IREY, BMNY |

Most crypto assets are fetched via Yahoo Finance (`BTC-USD` format). D2X is fetched via GeckoTerminal (Solana pool). SCP is fetched via CCXT/CoinEx. REZ, ONDO, NIGHT may not be listed on Yahoo Finance and will fail gracefully.

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
python scripts/validate_data.py ATR_Tracker_Dashboard.xlsx --sheet Data
python scripts/update_history.py
python scripts/calculate_metrics.py
python scripts/build_dashboard.py
```

### Backfill (Jan 2024 to present)

```bash
python backfill_historical.py
```

Re-run this after any change to ATR, RSI, or Volume Profile calculations to regenerate `data/history.csv` with corrected values. Can also be triggered via GitHub Actions when running locally isn't practical: **Actions → Backfill Historical Data → Run workflow**.

## Configuration

All shared configuration lives in `trading_utils/config.py`:

- `ASSETS` — list of asset names to track
- `ASSET_CONFIG` — maps each asset to its data source and symbol
- `MANUAL_DATA` — manual price/indicator values for assets without API access
- `EMA_PERIOD`, `ATR_PERIOD`, `RSI_PERIOD`, `Z_SCORE_PERIOD` — indicator periods
- `VP_LOOKBACK_BARS` (90), `VP_LOOKBACK_BARS_WEEKLY` (52), `VP_N_BUCKETS` (24) — Volume Profile parameters

## Adding New Assets

**Yahoo Finance or Binance:**

1. Add the asset name to `ASSETS` in `trading_utils/config.py`
2. Add an entry to `ASSET_CONFIG`:
   ```python
   'MSTR': {'source': 'yahoo', 'symbol': 'MSTR'},
   'BTC':  {'source': 'yahoo', 'symbol': 'BTC-USD'},
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

After adding assets, run the backfill to populate their full history.

## Data Files

| File | Description |
|------|-------------|
| `ATR_Tracker_Dashboard.xlsx` | Excel workbook (single `Data` sheet); written by tracker and backfill |
| `data/history.csv` | Full historical accumulation — authoritative source; includes `High`, `Low`, `Volume` columns |
| `data/master.csv` | Latest row per Asset+Timeframe — derived from history |
| `data/dashboard.json` | Processed metrics for the web dashboard, including VP fields |
| `data/chart_history.json` | Last 90 bars of ATR Distance, RSI, Price, EMA21 per asset+timeframe |
| `data/metadata.json` | Pipeline run metadata (last updated, asset count) |

## GitHub Actions

Two workflows live in `.github/workflows/`:

**`crypto-tracker.yml`** — runs daily at 09:00 UTC and on manual dispatch:
1. Fetch current OHLCV data (`crypto_tracker.py`)
2. Validate Excel output (`validate_data.py`)
3. Append to history CSV (`update_history.py`)
4. Calculate metrics and regime classification (`calculate_metrics.py`)
5. Build dashboard assets (`build_dashboard.py`)
6. Commit data files and deploy to Cloudflare Pages

**`backfill.yml`** — manual dispatch only:
1. Re-fetch full OHLCV history for all assets (`backfill_historical.py`)
2. Recalculate all metrics (`calculate_metrics.py`)
3. Rebuild dashboard assets (`build_dashboard.py`)
4. Commit and push

Use the backfill workflow after adding new assets or changing indicator calculations, or after any schema change to `history.csv`.

## Notes

- LSE ETFs require the `.L` suffix for Yahoo Finance (e.g., `MSTY.L`)
- All `yf.download()` calls use `auto_adjust=False` — required for LSE ETFs to prevent dividend payments from corrupting historical EMA/ATR values
- If more than 8 (asset, timeframe) pairs fail, the CI job exits non-zero (allows up to 4 assets × 2 timeframes that may be unlisted on Yahoo Finance)
- The pipeline is idempotent — re-running does not create duplicate rows in `history.csv`
- `data/history.csv` is the source of truth; all other data files are derived from it
- Volume Profile uses daily OHLCV bar ranges (uniform volume distribution within H/L) — coarser than TradingView's tick-based VPVR but sufficient as a support/resistance zone signal
