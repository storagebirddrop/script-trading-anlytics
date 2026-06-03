# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A trading analytics pipeline that fetches OHLCV data from Yahoo Finance (crypto, stocks, ETFs, macro), Binance/CCXT (SCP), and GeckoTerminal (D2X), calculates technical indicators, stores historical data, classifies market regimes, and serves an interactive web dashboard via GitHub Actions + Cloudflare Pages.

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
                                          (percentiles, regime classification,
                                           alignment, transitions, ATR trend,
                                           RS/BTC, breadth history)
                                                        ↓
                                          data/dashboard.json
                                          data/chart_history.json
                                          data/breadth.json
                                                        ↓
                                          scripts/build_dashboard.py
                                                        ↓
                                          dashboard/assets/data.json
                                          dashboard/assets/chart_history.json
                                          dashboard/assets/breadth.json → Cloudflare Pages
```

### `trading_utils/` Module

Shared library used by both `crypto_tracker.py` and `backfill_historical.py`. Avoids code duplication.

| Submodule | Contents |
|-----------|----------|
| `trading_utils/config.py` | `ASSETS`, `ASSET_CONFIG`, `MACRO_ASSETS`, `MANUAL_DATA`, all path constants, indicator periods |
| `trading_utils/indicators.py` | `calculate_ema`, `calculate_atr`, `calculate_rsi`, `calculate_adx`, `calculate_bollinger_bands`, `calculate_z_score`, `calculate_indicators`, `calculate_volume_profile` |
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
| `data/breadth.json` | Last 60 days of daily regime counts for portfolio assets (non-macro); used by breadth chart on Portfolio tab |

`history.csv` is the source of truth. `master.csv`, `dashboard.json`, `chart_history.json`, and `breadth.json` are all derived from it.

### Tracked Assets

70 assets across 4 categories (45 trading + 25 macro), both daily (`1d`) and weekly (`1w`) timeframes:

**Trading portfolio (45 assets):**
- **Crypto (28):** BTC, ETH, SOL, XLM, REZ, RSR, NEAR, RENDER, ONDO, ACH, BNB, XRP, ADA, NIGHT, VTHO, LINK, NEO, GAS, DRIFT, SEI, PEAQ, AEVO, EIGEN, W, WOO, JASMY — fetched via Yahoo Finance (symbol format: `BTC-USD`, `LINK-USD`). REZ, ONDO, NIGHT and some newer tokens may not be listed on Yahoo Finance and will fail gracefully. Also includes D2X (Solana via GeckoTerminal) and SCP (CoinEx via CCXT) — all 28 are grouped as "Crypto" in the dashboard UI and `ASSET_CATEGORIES`.
- **NASDAQ stocks (11):** MSTR, XXI, RIOT, MARA, IREN, BMNR, HUT, WULF, HIVE, CLSK, SLNH
- **LSE ETFs (6):** MSTY, YMST, MARY, RIOY, IREY, BMNY — fetched via Yahoo Finance with `.L` suffix. These pay large regular distributions; **always use `auto_adjust=False`** in `yf.download()` calls or historical EMA/ATR will be corrupted each time a dividend is paid.

**Macro assets (25 assets) — appear only on the Macro tab:**
- **US Indices (4):** SPX (`^GSPC`), NDX (`^NDX`), RTY (`^RUT`), DJI (`^DJI`)
- **EU Indices (3):** DAX (`^GDAXI`), CAC (`^FCHI`), FTSE (`^FTSE`)
- **APAC Indices (3):** NIK (`^N225`), HSI (`^HSI`), ASX (`^AXJO`)
- **Commodities (7):** GOLD (`GC=F`), SILVER (`SI=F`), OIL (`CL=F`), NATGAS (`NG=F`), COPPER (`HG=F`), WHEAT (`ZW=F`), CORN (`ZC=F`)
- **Forex (8):** DXY (`DX-Y.NYB`), EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCAD, USDCHF, USDJPY (all `=X` suffix)

Macro assets are tracked identically to trading assets in the pipeline (OHLCV, ATR, RSI, VP) but are separated in the dashboard via `MACRO_ASSETS` in `config.py` and `ASSET_CATEGORIES.macro` in `dashboard.js`. They are excluded from Portfolio cards, Rankings, Opportunity/Risk panels, and the Extremes/Drilldown asset selectors. Natural gas is named `NATGAS` to avoid collision with the `GAS` crypto asset.

### Key Indicators

All calculations live in `trading_utils/indicators.py`.

- **EMA21:** 21-period EMA, SMA-seeded (matches TradingView `ta.ema()`)
- **ATR:** 14-period Average True Range, Wilder's RMA, SMA-seeded (matches TradingView `ta.atr()`)
- **RSI:** 14-period RSI, Wilder's RMA, SMA-seeded (matches TradingView `ta.rsi()`)
- **RSI_Z_Score:** 20-period rolling Z-score of RSI
- **ATR_Distance:** `(Price - EMA21) / ATR` — core metric for regime classification; `NaN` when `ATR = 0`
- **Pct_Above_EMA:** `((Price - EMA21) / EMA21) * 100`
- **ADX:** 14-period Average Directional Index (Wilder's RMA, SMA-seeded). Measures trend strength independently of direction (0–100; >25 = trending, <20 = ranging). Computed from +DM/−DM → +DI/−DI → DX → ADX. First valid at bar `2*(period−1)` = 26. Added to `history.csv` as `ADX` column; written as `adx` in `dashboard.json` `current` objects; shown as a colour-coded badge on portfolio cards and in the Drilldown summary.
- **BB_Pct_B / BB_Bandwidth:** 20-period Bollinger Bands with 2σ. `%B = (close − lower) / (upper − lower)` — 0 = at lower band, 1 = at upper band; outside [0,1] = price beyond the bands. Bandwidth = `(upper − lower) / mid × 100` — percentage width relative to midband; useful for detecting BB squeezes (multi-period lows precede large moves). Uses rolling sample-std (ddof=1). First valid at bar `period − 1` = 19. Written as `bb_pct_b` and `bb_bandwidth` in `dashboard.json`; shown as coloured badge on cards and two rows in the Drilldown summary.
- **price_change_pct** *(derived in `calculate_metrics.py`)*: `(current_price - prev_price) / prev_price × 100` — momentum indicator added to `dashboard.json` `current` objects; displayed as "Chg%" on portfolio cards and in the drilldown summary

All indicators use SMA of the first `period` bars as the seed value, then apply exponential smoothing. This matches TradingView exactly. Do not replace with pandas `ewm(adjust=False)` — that initialisation diverges significantly for short-history assets.

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
ADX_PERIOD              = 14   # ADX period (shared with ATR/RSI)
BB_PERIOD               = 20   # Bollinger Bands period
BB_STD                  = 2.0  # Bollinger Bands standard deviation multiplier
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

- **API retries:** `_with_retry` in `trading_utils/data_sources.py` retries each fetch up to 3 times with exponential backoff (5s, 10s, 20s). If more than 40 (asset, timeframe) pairs fail in `crypto_tracker.py`, it exits with code 1 and the CI job fails visibly. The threshold is 40 to allow for newer crypto tokens and macro assets that may be temporarily unavailable (Yahoo Finance futures contracts roll periodically).
- **Binance pagination:** `backfill_historical.py:fetch_historical_binance` loops with `since` offsets to handle histories longer than 1000 bars.
- **ATR = 0:** `ATR_Distance` is set to `NaN` rather than `inf`/`-inf`.
- **JSON safety:** `_sanitise()` in `calculate_metrics.py` replaces all `NaN`/`inf` with `null` before writing `dashboard.json`.
- **Yahoo Finance dividend adjustment:** All `yf.download()` calls use `auto_adjust=False`. The default (`True`) retroactively rescales every historical close price on each new dividend, corrupting EMA/ATR for income assets (especially LSE ETFs). If you ever add a new `yf.download()` call, always include `auto_adjust=False`.
- **Staleness filter:** `calculate_current_metrics()` skips the `current` snapshot for any asset whose latest row is more than 60 days behind the global dataset maximum. This prevents delisted or renamed tickers from showing stale data on the dashboard.

### Web Dashboard

Client-side vanilla JS app in `dashboard/`. Loads `dashboard/assets/data.json` (copied from `data/dashboard.json`) and `dashboard/assets/chart_history.json` via `fetch()`. Two pages, five tabs. Uses Chart.js (CDN) for charts.

**Pages:**
- `dashboard/landing.html` — static landing page (no JS, no data fetch); explains ATR Distance, regime classification, and the four-step workflow. Linked from the "About" button in the dashboard header.
- `dashboard/index.html` — main single-page app

**Tabs:**
- **Portfolio tab:** Portfolio Health Bar (oversold%/neutral%/extended%/sentiment + **Crypto Fear & Greed Index badge** from alternative.me — colour-coded Extreme Fear → green through Extreme Greed → red; hidden when unavailable), Opportunity panel (top-3 most oversold with signal-strength labels), Risk panel (top-3 most extended), **Recent Regime Transitions** section (animated yellow chips showing assets whose regime changed since the last bar, hidden when none), **Market Breadth 60-Day chart** (stacked bar chart of daily regime counts loaded from `breadth.json`, hidden when unavailable), a live **search input** (filters assets by name), then asset cards with ATR Distance (semantically coloured), inline historical percentile badge (P8%), VP position badge, **multi-timeframe alignment badge** (↑↑ aligned-bullish / ↓↓ aligned-bearish / ↕ diverging), **regime transition pulse** (animated yellow dot when regime changed last bar), **ATR trend icon** (expanding ↑ / compressing ↓ / flat ─), **RS/BTC badge** (crypto only — 30-day return ratio vs BTC, outperforming/underperforming), **Funding Rate badge** (crypto only — colour-coded by squeeze risk; hidden when null), **OI** (crypto only — open interest in USD; hidden when null), **ADX badge** (colour-coded Trending/Neutral/Ranging; hidden when null), **BB %B badge** (Bollinger Band position; hidden when null), **star button** (watchlist, max 10, starred assets float to top via localStorage), and a 14-bar ATR Distance sparkline. Filterable by **timeframe (Daily/Weekly)**, regime, and category. Sort options include **Market Cap ↓** (uses `market_cap_rank`). Macro assets are excluded from this tab.
- **Rankings tab:** top 10 most oversold / most extended assets with historical percentile rank and signal-strength label (Extreme Oversold → Mild Dip / Extreme Extended → Mild Extension). Macro assets excluded.
- **Extremes tab** (formerly "Historical"): percentile gauge showing current ATR Distance position within historical range, with coloured regime zones; contextual interpretation paragraph explaining how frequently the asset has been at this level; metrics grid including RSI Z-Score. Macro assets excluded from selector.
- **Macro tab:** 25 macro assets grouped into 5 sections (US Indices, EU Indices, APAC Indices, Commodities, Forex). Each card shows symbol, zone badge (`macroZoneLabel()`), price, ATR Distance, and Chg%. Clicking any card navigates to the Drilldown for that asset. Zone badges use neutral labels (Neutral/Oversold/Extended) rather than the crypto-flavoured regime names.
- **Drilldown tab:** Key Takeaways panel (up to 5 auto-generated insights: ATR percentile, RSI status, weekly regime alignment, recent ATR trend direction, and VP position), then Chart.js line charts (Price vs EMA21, ATR Distance, RSI, Weekly ATR Distance, Volume Profile horizontal bar chart) plus summary metrics grid (includes VP Zone, POC, VAH, VAL, TF Align, ATR Trend, Transition, RS/BTC, Funding Rate (crypto), Open Interest (crypto), ADX (14), BB %B (20), BB Width rows). Available for all 70 assets including macro.

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
- `alignBadgeClass(alignment)` / `alignBadgeLabel(alignment)` — returns CSS class / label for multi-TF alignment badge (`align-bullish`/`align-bearish`/`align-diverging`)
- `atrTrendIcon(trend)` — returns ↑/↓/─ icon for ATR trend direction
- `rsBadgeHtml(rs)` — returns RS/BTC badge HTML with outperforming/underperforming class and ×multiplier
- `frBadgeHtml(fr)` — returns funding rate badge HTML (5 tiers: negative-strong / negative / neutral / positive / positive-strong); `fr` is the rate as a % per 8h period
- `oiFormatted(usd)` — formats open interest USD as a human-readable string (`$12.5B` / `$450M`)
- `fngCssClass(label)` — maps Fear & Greed label to CSS class (`fng--extreme-fear` through `fng--extreme-greed`)
- `btcDomCssClass(pct)` — maps BTC dominance % to CSS class (`btcd--high/elevated/low/unknown`)
- `altseasonCssClass(label)` — maps altseason label to CSS class (`alts--altseason` through `alts--btcseason`)
- `renderMarketContextBar()` — renders `#market-context-bar` with BTC.D and Altseason index; hidden when both are null
- `adxStrengthHtml(adx)` — returns ADX badge HTML with strength label (Trending >25 / Neutral 20–25 / Ranging <20) and colour class
- `bbPctBHtml(pctB)` — returns BB %B badge HTML; colours: below 0 = green (oversold breakout), 0–0.2 = light green, 0.2–0.8 = neutral, 0.8–1.0 = amber, above 1 = red (overbought breakout)
- `getStarred()` / `isStarred(asset)` / `toggleStar(asset)` — localStorage watchlist (key `starred_assets`, max 10)
- `macroZoneLabel(atrDistance)` — returns `{ label, cssClass }` for a macro zone badge; uses ATR Distance thresholds with neutral display names (Neutral/Oversold/Extended rather than crypto regime names)
- `renderPortfolioHealthBar()` — populates the health summary bar (excludes macro assets)
- `renderOpportunityPanels()` — populates top-3 oversold / extended panels (excludes macro assets)
- `renderTransitionsSection()` — renders or hides the Recent Regime Transitions chips section; hidden when no transitions exist
- `renderBreadthChart()` — fetches `assets/breadth.json` and renders the 60-day stacked bar chart; hides section on fetch failure
- `renderMacro()` — renders the Macro tab with 5 subcategory groups; builds cards via DOM API for CSP compliance
- `buildGaugeInterpretation(current, historical)` — returns plain-language gauge interpretation text
- `generateKeyTakeaways(symbol, tfData, allData, chartHistory)` — generates drilldown insight array (up to 5, including VP)
- `renderVolumeProfileChart(current, tf)` — renders horizontal bar VP chart; CSP-compliant legend via DOM API
- `makeSparklineSvg(values, currentAtrDistance)` — returns inline SVG string for a 14-bar ATR Distance sparkline; stroke colour matches ATR semantics; dashed zero line when range straddles neutral
- `renderPortfolioSparklines()` — fills `.card-sparkline[data-asset]` placeholders using `chartHistoryData`; no-op if data not yet loaded

**Key JS constants:**
- `ASSET_CATEGORIES` — sets for `crypto`, `nasdaq`, `lse`, `macro`; used to filter assets across all tabs
- `MACRO_SUBCATEGORIES` — ordered groupings for the Macro tab layout
- `MACRO_FOREX_SYMBOLS` — set of forex/DXY symbols; controls price display format (4dp plain vs `$`-prefixed)
- `portfolioFilter` — `{ category, regime, sort, timeframe, search }` — portfolio filter/sort state

**New `current` fields in `dashboard.json`** (added by `calculate_metrics.py`):
- `alignment` — `'aligned-bullish'` | `'aligned-bearish'` | `'diverging'` — computed in `generate_dashboard_json()` by comparing daily vs weekly regime; omitted when either timeframe is missing or Unknown
- `regime_changed` — `bool` — true when current regime differs from the previous bar's regime
- `prev_regime` — `str|null` — previous bar's regime name when a transition occurred
- `atr_trend` — `'expanding'` | `'compressing'` | `'flat'` — relative slope of last 10 ATR bars (threshold ±0.01 × mean ATR); null when fewer than 5 ATR bars
- `rs_vs_btc` — `float|null` — 30-day return ratio `(asset / BTC)` for daily crypto assets; null when BTC return is unavailable or zero
- `adx` — `float|null` — 14-period Average Directional Index value; null when fewer than 27 bars of OHLCV exist or when the market shows no directional movement (DX undefined). Displayed as a colour-coded badge: Trending (>25, green), Neutral (20–25, amber), Ranging (<20, grey).
- `bb_pct_b` — `float|null` — Bollinger Band %B (20-period, 2σ). 0 = lower band, 1 = upper band; values outside [0,1] indicate price beyond the bands. Null when fewer than 20 bars or when bandwidth = 0 (flat price).
- `bb_bandwidth` — `float|null` — Bollinger Bandwidth as `(upper − lower) / mid × 100`. Null under the same conditions as `bb_pct_b`.

**Top-level fields in `dashboard.json`** (added by `calculate_metrics.py`):
- `fear_greed` — `{value: int, label: str, timestamp: str}|null` — Crypto Fear & Greed Index fetched from `https://api.alternative.me/fng/?limit=1` (free, no auth). Written by `fetch_fear_greed()`. `null` when the fetch fails. Labels: `Extreme Fear` | `Fear` | `Neutral` | `Greed` | `Extreme Greed`.
- `btc_dominance` — `float|null` — BTC market-cap dominance % from CoinGecko `/api/v3/global` (free, no auth). `null` on failure.
- `altseason` — `{score: int, label: str, alts_outperforming: int, total: int}|null` — Altcoin Season Index computed from `history.csv`. Score = % of tracked crypto assets (excl. BTC) that outperformed BTC over the last 90 days. Labels: `Altcoin Season` | `Leaning Alt` | `Neutral` | `Leaning BTC` | `Bitcoin Season`. `null` when insufficient history. Displayed in the `market-context-bar` above the Portfolio health bar.

**Per-asset `current` fields added by Binance USDT-M futures (crypto assets only, free/no auth):**
- `funding_rate` — `float|null` — Last settled funding rate converted to % per 8h period (e.g. `0.0100` = 0.01%). Fetched from `https://fapi.binance.com/fapi/v1/premiumIndex` via `fetch_binance_futures()`. `null` when asset has no USDT-M perpetual contract on Binance (e.g. D2X, SCP, NIGHT).
- `open_interest_usd` — `float|null` — Open interest in USD (= contracts × mark price). Per-symbol from `/fapi/v1/openInterest`. `null` when OI call fails.

No API key required. Both fields degrade gracefully to `null` on network failure — no pipeline impact.

**New pipeline output** — `data/breadth.json` / `dashboard/assets/breadth.json`:
Written by `generate_breadth_json()` in `calculate_metrics.py`. Covers the last 60 trading days of daily (1d) non-macro assets. Structure: `{ "dates": [...], "capitulation": [...], "accumulation": [...], "trend": [...], "distribution": [...], "mania": [...] }` — each array has one count per date entry. Copied by `build_dashboard.py` alongside `data.json` and `chart_history.json`.

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
