# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A trading analytics pipeline that fetches OHLCV data from Binance (crypto) and Yahoo Finance (stocks/ETFs), calculates technical indicators, stores historical data, classifies market regimes, and serves an interactive web dashboard via GitHub Actions + Cloudflare Pages.

## Common Commands

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Run the full data pipeline (in order):**
```bash
python crypto_tracker.py                                          # Fetch current OHLCV → master.csv + Excel
python scripts/validate_data.py ATR_Tracker_Dashboard.xlsx        # Validate Excel output
python scripts/update_history.py                                  # Append to history.csv, deduplicate
python scripts/calculate_metrics.py                               # Generate dashboard.json
python scripts/build_dashboard.py                                 # Copy assets to dashboard/
```

**Backfill historical data (Jan 2024 to present):**
```bash
python backfill_historical.py
```

Run backfill after any change to the ATR or RSI calculation to regenerate `history.csv` with corrected values.

**Run tests:**
```bash
pytest                              # All tests
pytest tests/test_indicators.py    # Indicator arithmetic (ATR, RSI, EMA correctness)
pytest tests/test_metrics.py       # Regime classification
pytest tests/test_validation.py    # Data validation rules
pytest tests/test_integration.py   # End-to-end pipeline
```

## Architecture

### Data Flow

```
Binance API (CCXT) ──┐
Yahoo Finance ────────┼──→ crypto_tracker.py ──→ data/master.csv
Manual input ─────────┘                      └──→ ATR_Tracker_Dashboard.xlsx
                                                        ↓
                                          scripts/validate_data.py
                                                        ↓
                                          scripts/update_history.py
                                          (deduplicates on Date+Asset+Timeframe)
                                                        ↓
                                          data/history.csv
                                                        ↓
                                          scripts/calculate_metrics.py
                                          (percentiles, regime classification)
                                                        ↓
                                          data/dashboard.json
                                                        ↓
                                          scripts/build_dashboard.py
                                                        ↓
                                          dashboard/assets/data.json → Cloudflare Pages
```

### `trading_utils/` Module

Shared library used by both `crypto_tracker.py` and `backfill_historical.py`. Avoids code duplication.

| Submodule | Contents |
|-----------|----------|
| `trading_utils/config.py` | `ASSETS`, `ASSET_CONFIG`, `MANUAL_DATA`, all path constants, indicator periods |
| `trading_utils/indicators.py` | `calculate_ema`, `calculate_atr`, `calculate_rsi`, `calculate_z_score`, `calculate_indicators` |
| `trading_utils/data_sources.py` | `fetch_ohlcv_binance`, `fetch_ohlcv_yahoo`, `fetch_ohlcv`, `get_manual_data`, `_with_retry` |

**Adding or changing assets/config:** edit `trading_utils/config.py` only — both scripts will pick it up automatically.

**Adding new indicator logic:** edit `trading_utils/indicators.py`. Both the daily tracker and the backfill will use the updated calculation. Remember to re-run `backfill_historical.py` after any indicator change so `history.csv` is regenerated with the correct values.

### Storage Files

| File | Purpose |
|------|---------|
| `ATR_Tracker_Dashboard.xlsx` | Excel workbook (single `Data` sheet) written by both `crypto_tracker.py` and `backfill_historical.py` |
| `data/master.csv` | Latest snapshot per Asset+Timeframe — derived from history |
| `data/history.csv` | Full historical accumulation (authoritative record) |
| `data/dashboard.json` | Computed metrics consumed by the web UI |
| `data/chart_history.json` | Last 90 bars of ATR Distance, RSI, Price, EMA21 per asset+timeframe; used by Drilldown charts |

`history.csv` is the source of truth. `master.csv`, `dashboard.json`, and `chart_history.json` are all derived from it.

### Tracked Assets

33 assets across 4 categories, both daily (`1d`) and weekly (`1w`) timeframes:
- **Crypto (14):** BTC, ETH, SOL, XLM, REZ, RSR, NEAR, RENDER, ONDO, ACH, BNB, XRP, ADA, NIGHT — fetched via Yahoo Finance (symbol format: `BTC-USD`, `RENDER-USD`). REZ, ONDO, NIGHT may not be listed on Yahoo Finance and will fail gracefully.
- **NASDAQ stocks (11):** MSTR, XXI, RIOT, MARA, IREN, BMNR, HUT, WULF, HIVE, CLSK, SLNH
- **LSE ETFs (6):** MSTY, YMST, MARY, RIOY, IREY, BMNY — fetched via Yahoo Finance with `.L` suffix. These pay large regular distributions; **always use `auto_adjust=False`** in `yf.download()` calls or historical EMA/ATR will be corrupted each time a dividend is paid.
- **DEX / CEX (2):** D2X (Solana via GeckoTerminal), SCP (CoinEx via CCXT)

### Key Indicators

All calculations live in `trading_utils/indicators.py`.

- **EMA21:** 21-period EMA, SMA-seeded (matches TradingView `ta.ema()`)
- **ATR:** 14-period Average True Range, Wilder's RMA, SMA-seeded (matches TradingView `ta.atr()`)
- **RSI:** 14-period RSI, Wilder's RMA, SMA-seeded (matches TradingView `ta.rsi()`)
- **RSI_Z_Score:** 20-period rolling Z-score of RSI
- **ATR_Distance:** `(Price - EMA21) / ATR` — core metric for regime classification; `NaN` when `ATR = 0`
- **Pct_Above_EMA:** `((Price - EMA21) / EMA21) * 100`
- **price_change_pct** *(derived in `calculate_metrics.py`)*: `(current_price - prev_price) / prev_price × 100` — momentum indicator added to `dashboard.json` `current` objects; displayed as "Chg%" on portfolio cards and in the drilldown summary

All three indicators use SMA of the first `period` bars as the seed value, then apply exponential smoothing. This matches TradingView exactly. Do not replace with pandas `ewm(adjust=False)` — that initialisation diverges significantly for short-history assets.

### Regime Classification (ATR_Distance thresholds)

| Regime | Condition | Sentiment |
|--------|-----------|-----------|
| Capitulation | ATR_Distance < -4 | Panic / Capitulation |
| Accumulation | -4 ≤ ATR_Distance < -2 | Oversold |
| Trend | -2 ≤ ATR_Distance ≤ 2 | Balanced / Fair Value |
| Distribution | 2 < ATR_Distance ≤ 4 | Extended |
| Mania | ATR_Distance > 4 | Euphoric / Blow-off |

### Resilience Behaviour

- **API retries:** `_with_retry` in `trading_utils/data_sources.py` retries each fetch up to 3 times with exponential backoff (5s, 10s, 20s). If more than 8 (asset, timeframe) pairs fail in `crypto_tracker.py`, it exits with code 1 and the CI job fails visibly. The threshold is 8 (not 3) to allow for up to 4 assets that may be unlisted on Yahoo Finance.
- **Binance pagination:** `backfill_historical.py:fetch_historical_binance` loops with `since` offsets to handle histories longer than 1000 bars.
- **ATR = 0:** `ATR_Distance` is set to `NaN` rather than `inf`/`-inf`.
- **JSON safety:** `_sanitise()` in `calculate_metrics.py` replaces all `NaN`/`inf` with `null` before writing `dashboard.json`.
- **Yahoo Finance dividend adjustment:** All `yf.download()` calls use `auto_adjust=False`. The default (`True`) retroactively rescales every historical close price on each new dividend, corrupting EMA/ATR for income assets (especially LSE ETFs). If you ever add a new `yf.download()` call, always include `auto_adjust=False`.
- **Staleness filter:** `calculate_current_metrics()` skips the `current` snapshot for any asset whose latest row is more than 60 days behind the global dataset maximum. This prevents delisted or renamed tickers from showing stale data on the dashboard.

### Web Dashboard

Client-side vanilla JS app in `dashboard/`. Loads `dashboard/assets/data.json` (copied from `data/dashboard.json`) and `dashboard/assets/chart_history.json` via `fetch()`. Four tabs: Portfolio, Rankings, Historical, Drilldown. Uses Chart.js (CDN) for charts.

- **Portfolio tab:** asset cards showing ATR Distance (daily + weekly), RSI, RSI Z-Score, Price, and Chg%; filterable by regime and category
- **Rankings tab:** top 10 most oversold / most extended assets by ATR Distance
- **Historical tab:** percentile gauge showing current ATR Distance position within historical range, with coloured regime zones; metrics grid including RSI Z-Score
- **Drilldown tab:** Chart.js line charts (ATR Distance, RSI, Price vs EMA21, Weekly ATR Distance) plus summary metrics grid

### CI/CD

`.github/workflows/crypto-tracker.yml` runs daily at 09:00 UTC and on manual dispatch. It executes the full pipeline in sequence, commits updated data files back to `master`, and deploys the `dashboard/` directory to Cloudflare Pages.

## Data Validation Rules

`scripts/validate_data.py` enforces:
- All required columns present, no nulls in `Date`, `Asset`, `Timeframe`
- ATR > 0, RSI in [0, 100]
- Timeframe values in `{1d, 1w, Daily, Weekly}`
- No duplicate `(Date, Asset, Timeframe)` combinations

`ValidationResult` accumulates errors and warnings and is used by both `update_history.py` and the test suite. A validation failure in `update_history.py` stops the pipeline with exit code 1.
