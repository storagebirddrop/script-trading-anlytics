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

`history.csv` is the source of truth. `master.csv` and `dashboard.json` are both derived from it.

### Tracked Assets

29 assets across 3 categories, both daily (`1d`) and weekly (`1w`) timeframes:
- **Crypto (12):** BTC, ETH, SOL, XLM, REZ, RSR, NEAR, RENDER, ONDO, ACH, BNB, XRP — fetched via Yahoo Finance (symbol format: `BTC-USD`; RENDER uses `RNDR-USD`). REZ and ONDO may not be listed on Yahoo Finance and will fail gracefully.
- **NASDAQ stocks (11):** MSTR, XXI, RIOT, MARA, IREN, BMNR, HUT, WULF, HIVE, CLSK, SLNH
- **LSE ETFs (6):** MSTY, YMST, MARY, RIOY, IREY, BMNY — fetched via Yahoo Finance with `.L` suffix

### Key Indicators

All calculations live in `trading_utils/indicators.py`.

- **EMA21:** 21-period EMA using standard smoothing (`alpha = 2/22`)
- **ATR:** 14-period Average True Range using **Wilder's smoothing** (`com=13`, `alpha = 1/14`)
- **RSI:** 14-period RSI using **Wilder's smoothing** (`com=13`, `alpha = 1/14`)
- **RSI_Z_Score:** 20-period rolling Z-score of RSI
- **ATR_Distance:** `(Price - EMA21) / ATR` — core metric for regime classification; `NaN` when `ATR = 0`
- **Pct_Above_EMA:** `((Price - EMA21) / EMA21) * 100`

EMA uses `ewm(span=period)` (standard). ATR and RSI use `ewm(com=period-1)` (Wilder's RMA). These are different smoothing methods — do not change them to match each other.

### Regime Classification (ATR_Distance thresholds)

| Regime | Condition |
|--------|-----------|
| Accumulation | ATR_Distance < -2 |
| Trend | -2 ≤ ATR_Distance ≤ 2 |
| Extended | 2 < ATR_Distance ≤ 4 |
| Euphoria | ATR_Distance > 4 |

### Resilience Behaviour

- **API retries:** `_with_retry` in `trading_utils/data_sources.py` retries each fetch up to 3 times with exponential backoff (5s, 10s, 20s). If more than 8 (asset, timeframe) pairs fail in `crypto_tracker.py`, it exits with code 1 and the CI job fails visibly. The threshold is 8 (not 3) to allow for up to 4 assets that may be unlisted on Yahoo Finance.
- **Binance pagination:** `backfill_historical.py:fetch_historical_binance` loops with `since` offsets to handle histories longer than 1000 bars.
- **ATR = 0:** `ATR_Distance` is set to `NaN` rather than `inf`/`-inf`.
- **JSON safety:** `_sanitise()` in `calculate_metrics.py` replaces all `NaN`/`inf` with `null` before writing `dashboard.json`.

### Web Dashboard

Client-side vanilla JS app in `dashboard/`. Loads `dashboard/assets/data.json` (copied from `data/dashboard.json`) via `fetch()`. Four tabs: Portfolio, Rankings, Historical, Drilldown. Uses Plotly for charts.

### CI/CD

`.github/workflows/crypto-tracker.yml` runs daily at 09:00 UTC and on manual dispatch. It executes the full pipeline in sequence, commits updated data files back to `master`, and deploys the `dashboard/` directory to Cloudflare Pages.

## Data Validation Rules

`scripts/validate_data.py` enforces:
- All required columns present, no nulls in `Date`, `Asset`, `Timeframe`
- ATR > 0, RSI in [0, 100]
- Timeframe values in `{1d, 1w, Daily, Weekly}`
- No duplicate `(Date, Asset, Timeframe)` combinations

`ValidationResult` accumulates errors and warnings and is used by both `update_history.py` and the test suite. A validation failure in `update_history.py` stops the pipeline with exit code 1.
