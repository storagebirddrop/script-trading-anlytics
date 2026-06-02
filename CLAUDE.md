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

Run backfill after any change to the ATR or RSI calculation to regenerate `history.csv` with corrected values. Can also be triggered via GitHub Actions: **Actions → Backfill Historical Data → Run workflow** (use this when running locally is not possible, e.g. in a remote environment without external network access).

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
                                          data/chart_history.json
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
| `trading_utils/indicators.py` | `calculate_ema`, `calculate_atr`, `calculate_rsi`, `calculate_z_score`, `calculate_indicators`, `calculate_volume_profile` |
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

45 assets across 3 categories, both daily (`1d`) and weekly (`1w`) timeframes:
- **Crypto (28):** BTC, ETH, SOL, XLM, REZ, RSR, NEAR, RENDER, ONDO, ACH, BNB, XRP, ADA, NIGHT, VTHO, LINK, NEO, GAS, DRIFT, SEI, PEAQ, AEVO, EIGEN, W, WOO, JASMY — fetched via Yahoo Finance (symbol format: `BTC-USD`, `LINK-USD`). REZ, ONDO, NIGHT and some newer tokens may not be listed on Yahoo Finance and will fail gracefully. Also includes D2X (Solana via GeckoTerminal) and SCP (CoinEx via CCXT) — all 28 are grouped as "Crypto" in the dashboard UI and `ASSET_CATEGORIES`.
- **NASDAQ stocks (11):** MSTR, XXI, RIOT, MARA, IREN, BMNR, HUT, WULF, HIVE, CLSK, SLNH
- **LSE ETFs (6):** MSTY, YMST, MARY, RIOY, IREY, BMNY — fetched via Yahoo Finance with `.L` suffix. These pay large regular distributions; **always use `auto_adjust=False`** in `yf.download()` calls or historical EMA/ATR will be corrupted each time a dividend is paid.

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

### Volume Profile (VP)

Computed by `calculate_volume_profile()` in `trading_utils/indicators.py`. Called from `scripts/calculate_metrics.py` when `history.csv` contains `High`, `Low`, `Volume` columns (added by `crypto_tracker.py` and `backfill_historical.py`).

**Algorithm** (per asset+timeframe snapshot, using last `VP_LOOKBACK_BARS` rows):
1. Determine full price range: `min(low)` → `max(high)` across all bars
2. Divide into `VP_N_BUCKETS = 24` equal-width price buckets
3. Distribute each bar's volume proportionally across overlapping buckets (`overlap / bar_range`)
4. **POC** = bucket with highest volume; price = bucket midpoint
5. **Value Area** = expand outward from POC absorbing highest adjacent bucket until ≥ 70% of total volume is captured; **VAH** = top of uppermost included bucket, **VAL** = bottom of lowermost
6. **Position** classification: `above_vah` | `below_val` | `at_poc` (within ±1.5 bucket widths) | `in_value_area`
7. **dist_from_poc** = `(price − POC) / ATR` — distance in ATR units
8. Returns `None` if: fewer than 20 bars with non-zero volume, or total volume = 0

**Config constants** (in `trading_utils/config.py`):
```python
VP_LOOKBACK_BARS        = 90   # daily lookback (~4 months)
VP_LOOKBACK_BARS_WEEKLY = 52   # weekly lookback (~1 year)
VP_N_BUCKETS            = 24   # price distribution buckets
```

**Output fields** added to each `current` object in `dashboard.json`:
- `vp_poc`, `vp_vah`, `vp_val` — key price levels
- `vp_position` — one of the 4 position strings above
- `vp_dist_from_poc` — ATR-normalised distance from POC
- `vp_buckets` — list of 24 `{p, v, is_poc, in_va}` dicts for the VP chart

All fields are `null` when `High`/`Low`/`Volume` columns are absent from `history.csv` (backward-compatible with pre-backfill data).

**Known limitations:**
- Daily bars distribute volume uniformly across H/L range — coarser than TradingView's tick-based VPVR
- Weekly VP uses 52-bar lookback (~1 year); daily uses 90-bar (~4 months) — different windows by design
- Assets with < 20 bars of non-zero volume return `null` VP fields; badges are hidden on cards
- LSE ETF volume is share count, not monetary — valid for relative distribution within an asset, not cross-asset comparisons

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

Client-side vanilla JS app in `dashboard/`. Loads `dashboard/assets/data.json` (copied from `data/dashboard.json`) and `dashboard/assets/chart_history.json` via `fetch()`. Five pages, four tabs. Uses Chart.js (CDN) for charts.

**Pages:**
- `dashboard/landing.html` — static landing page (no JS, no data fetch); explains ATR Distance, regime classification, and the four-step workflow. Linked from the "About" button in the dashboard header.
- `dashboard/index.html` — main single-page app

**Tabs:**
- **Portfolio tab:** Portfolio Health Bar (oversold%/neutral%/extended%/sentiment), Opportunity panel (top-3 most oversold with signal-strength labels), Risk panel (top-3 most extended), then asset cards with ATR Distance (semantically coloured: green=oversold, orange=extended, red=extreme), inline historical percentile badge (P8%), and VP position badge when data is available; filterable by regime and category
- **Rankings tab:** top 10 most oversold / most extended assets with historical percentile rank and signal-strength label (Extreme Oversold → Mild Dip / Extreme Extended → Mild Extension)
- **Extremes tab** (formerly "Historical"): percentile gauge showing current ATR Distance position within historical range, with coloured regime zones; contextual interpretation paragraph explaining how frequently the asset has been at this level; metrics grid including RSI Z-Score
- **Drilldown tab:** Key Takeaways panel (up to 5 auto-generated insights: ATR percentile, RSI status, weekly regime alignment, recent ATR trend direction, and VP position), then Chart.js line charts (Price vs EMA21, ATR Distance, RSI, Weekly ATR Distance, Volume Profile horizontal bar chart) plus summary metrics grid (includes VP Zone, POC, VAH, VAL rows)

**Signal strength tiers** (used in Opportunity/Risk panels and Rankings):
Uses the **more severe** of two independent signals — whichever gives the stronger label wins:
1. Percentile rank (how historically rare is this reading for this specific asset)
2. Absolute ATR Distance threshold (how far is price stretched in universal terms)

Each call specifies a `direction` ('oversold' or 'extended'), so tiers form two non-overlapping sets:

**Oversold direction** (negative ATR Distance assets):
| Tier | Percentile condition | ATR Distance condition |
|---|---|---|
| Extreme Oversold | P ≤ 5% | dist < −4 |
| Deep Oversold | P ≤ 15% | dist < −3 |
| Oversold | P ≤ 30% | dist < −2 |
| Mild Dip | neither threshold met | (fallback — no strong signal) |

**Extended direction** (positive ATR Distance assets):
| Tier | Percentile condition | ATR Distance condition |
|---|---|---|
| Extreme Extended | P ≥ 95% | dist > +4 |
| High Extended | P ≥ 85% | dist > +3 |
| Extended | P ≥ 70% | dist > +2 |
| Mild Extension | neither threshold met | (fallback — no strong signal) |

Within each direction the more severe of the two signals (percentile vs ATR Distance) determines the tier. Percentile tiers require `sample_size ≥ 30`; assets with thin history fall back to ATR Distance tiers only.

Example: YMST at ATR Distance −3.35 (P16%) → ATR tier = Deep Oversold, pct tier = Oversold → label = **Deep Oversold**. BTC at −2.39 (P4%) → ATR tier = Oversold, pct tier = Extreme Oversold → label = **Extreme Oversold**.

**Extremes tab gauge — percentile-based positioning:**
The gauge x-axis represents the empirical distribution, not a linear ATR Distance scale. `toPos()` uses piecewise linear interpolation between the known P0/P25/P50/P75/P90/P100 breakpoints:
- Tick marks at P25/P50/P75/P90 are positioned at 25%/50%/75%/90% of the gauge width; this percentile-based layout makes regime zone widths proportional to how often the asset occupies each zone — a wide Trend zone indicates the asset rarely reaches extremes
- Extreme outliers (e.g. a single mania spike) no longer compress the rest of the gauge
- Falls back to linear scaling if percentile breakpoints are missing

**CSP constraint — gauge DOM construction:**
`dashboard/_headers` enforces `style-src 'self'` (no `unsafe-inline`), which blocks inline `style` attributes parsed from HTML strings (e.g. via `innerHTML`). The gauge zone, tick, and marker elements are therefore created with `document.createElement` and positioned via `element.style.left`/`element.style.width` in JavaScript — DOM property assignments are governed by `script-src`, not `style-src`, so they are not restricted. Do not revert to injecting `style="left:X%"` inside template literals assigned to `innerHTML`; the CSP will silently ignore those attributes and the marker will appear stuck at 0%.

**Key JS functions in `dashboard/js/dashboard.js`:**
- `getSignalStrength(pct, direction, sampleSize, atrDistance)` — returns `{ label, cssClass }` using max-severity of percentile and ATR Distance tiers
- `getAtrColorClass(atrDistance)` — returns semantic CSS class for ATR Distance coloring
- `vpPositionLabel(pos)` — returns `{ label, cls }` for a VP position string
- `vpBadgeHtml(pos)` — returns badge `<span>` HTML for a VP position (empty string if null)
- `renderPortfolioHealthBar()` — populates the health summary bar
- `renderOpportunityPanels()` — populates top-3 oversold / extended panels
- `buildGaugeInterpretation(current, historical)` — returns plain-language gauge interpretation text
- `generateKeyTakeaways(symbol, tfData, allData, chartHistory)` — generates drilldown insight array (up to 5, including VP)
- `renderVolumeProfileChart(current, tf)` — renders horizontal bar VP chart; CSP-compliant legend via DOM API

### CI/CD

`.github/workflows/crypto-tracker.yml` runs daily at 09:00 UTC and on manual dispatch. It executes the full pipeline in sequence, commits updated data files back to `master`, and deploys the `dashboard/` directory to Cloudflare Pages.

`.github/workflows/backfill.yml` — manual-dispatch-only workflow that runs `backfill_historical.py` followed by `calculate_metrics.py` and `build_dashboard.py`. Use this after adding new assets or changing indicator calculations when a full history regeneration is needed and running locally isn't practical (e.g. in a remote environment with restricted network access).

## Data Validation Rules

`scripts/validate_data.py` enforces:
- All required columns present, no nulls in `Date`, `Asset`, `Timeframe`
- ATR > 0, RSI in [0, 100]
- Timeframe values in `{1d, 1w, Daily, Weekly}`
- No duplicate `(Date, Asset, Timeframe)` combinations

`ValidationResult` accumulates errors and warnings and is used by both `update_history.py` and the test suite. A validation failure in `update_history.py` stops the pipeline with exit code 1.
