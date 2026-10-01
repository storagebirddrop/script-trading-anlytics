# Multi-Asset ATR Tracker

Automated pipeline that fetches daily, weekly, and monthly OHLCV data from Yahoo Finance, Binance (CCXT), and GeckoTerminal, calculates technical indicators, accumulates historical data, and serves an interactive web dashboard via Cloudflare Pages.

**📖 [User Guide](docs/USER_GUIDE.md)** — in-depth, screenshot-illustrated manual explaining every metric and how to read, use, and interpret it.

## Features

- **Data sources:** Yahoo Finance (crypto + NASDAQ + LSE ETFs + macro), Binance/CCXT (SCP), GeckoTerminal (D2X); manual fallback for assets without API access
- **Indicators:** EMA21, EMA50 + EMA50 Distance, 200-day SMA proximity, ATR (14-period, Wilder's smoothing), RSI (14-period, Wilder's smoothing), RSI Z-score (20-period), ATR Distance, % Above EMA, ADX (14-period, Wilder's smoothing — trend strength 0–100; >25 trending, <20 ranging), Bollinger Bands %B + Bandwidth (20-period, 2σ — position within bands and squeeze detection)
- **Volume Profile:** fixed-lookback price-by-volume distribution (POC, VAH, VAL, position classification) stored in `dashboard.json` and rendered as a horizontal bar chart in the Drilldown tab
- **Timeframes:** Daily (`1d`), Weekly (`1w`), and Monthly (`1M` — capital M, matching CCXT's convention). `rs_vs_btc` is daily-only and the multi-timeframe alignment badge compares daily vs weekly only by design
- **Regime classification** based on ATR Distance thresholds (seven tiers: Ragequit → Capitulation → Accumulation → Trend → Distribution → Mania → Blow-off)
- **74 tracked assets** across crypto, NASDAQ stocks, LSE ETFs, and macro (indices, commodities, forex)
- **Crypto Fear & Greed Index** badge on the Portfolio health bar — fetched daily from alternative.me (free, no auth); colour-coded from Extreme Fear (green) to Extreme Greed (red)
- **Funding rates + Open Interest** — Binance USDT-M futures API (free, no auth) with Bybit and CoinGecko fallbacks; per-asset funding rate badge (colour-coded by squeeze risk) and OI on crypto cards and in Drilldown. **Currently `null` for every asset in CI** because the runners are geo-blocked (see limitations below)
- **BTC Dominance + Altcoin Season Index** — BTC.D from CoinGecko (free); Altseason score (0–100) self-computed from `history.csv` (% of tracked cryptos outperforming BTC over 90d); displayed in the market context bar above the Portfolio health bar
- **Composite signal score** — −10 to +10 per asset, aggregating ATR percentile (×4), RSI Z-Score (×3), VP position (×2), and TF alignment (×1); colour-coded badge on cards and in Drilldown; sortable column ("Score ↓")
- **Price alerts** — browser Notification API; per-asset ATR Distance threshold and regime-change alerts stored in `localStorage`; crossing-based so they fire once on breach, not on every page load
- **BTC Cycle Signals** — standalone page (`dashboard/btc.html`) aggregating ~20 BTC cycle indicators into an accumulate/neutral/distribute confluence view; data in `data/btc_signals.json` (see [Data sources and limitations](#data-sources-and-limitations))
- **Automated daily pipeline** via GitHub Actions

## Assets

| Category | Symbols |
|----------|---------|
| Crypto (28) | BTC, ETH, SOL, XLM, REZ, RSR, NEAR, RENDER, ONDO, ACH, BNB, XRP, ADA, NIGHT, VTHO, LINK, NEO, GAS, DRIFT, SEI, PEAQ, AEVO, EIGEN, W, WOO, JASMY, D2X, SCP |
| NASDAQ stocks (15) | MSTR, XXI, RIOT, MARA, IREN, BMNR, HUT, WULF, HIVE, CLSK, SLNH, KEEL, BTDR, BTBT, FUFU |
| LSE ETFs (6) | MSTY, YMST, MARY, RIOY, IREY, BMNY |
| US Indices (4) | SPX, NDX, RTY, DJI |
| EU Indices (3) | DAX, CAC, FTSE |
| APAC Indices (3) | NIK, HSI, ASX |
| Commodities (7) | GOLD, SILVER, OIL, NATGAS, COPPER, WHEAT, CORN |
| Forex (8) | DXY, EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCAD, USDCHF, USDJPY |

Most crypto assets are fetched via Yahoo Finance (`BTC-USD` format). D2X is fetched via GeckoTerminal (Solana pool). SCP is fetched via CCXT/CoinEx. REZ, ONDO, NIGHT may not be listed on Yahoo Finance and will fail gracefully.

**Known exception — DRIFT:** `DRIFT-USD` currently returns no data from Yahoo Finance on any timeframe. It stays in `ASSETS` so it appears automatically if Yahoo lists it, but it has no `current` entry and is not rendered. It also counts as 3 failed (asset, timeframe) pairs against the CI threshold. It has no rows in `history.csv`, so the dashboard header (`metadata.assets_count`, the number of assets with data) shows 73 of the 74 configured assets.

Macro assets (indices, commodities, forex) are all fetched via Yahoo Finance using standard futures/index/forex tickers (e.g. `^GSPC`, `GC=F`, `EURUSD=X`). They appear on the dedicated **Macro tab** and are excluded from the Portfolio, Rankings, and Opportunity/Risk panels. Natural gas is named `NATGAS` to avoid collision with the `GAS` crypto asset.

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

### Backfill (full history, from 2010)

```bash
python backfill_historical.py
```

`START_DATE` is 2010-01-01, which predates every tracked asset, so each source returns its full available history (monthly bars therefore go back as far as the source allows). Re-run this after any change to ATR, RSI, or Volume Profile calculations to regenerate `data/history.csv` with corrected values. Also run after adding new assets to populate their full history. Can also be triggered via GitHub Actions when running locally isn't practical: **Actions → Backfill Historical Data → Run workflow**.

## Configuration

All shared configuration lives in `trading_utils/config.py`:

- `ASSETS` — list of all 74 asset names to track
- `TIMEFRAMES` — `['1d', '1w', '1M']`
- `ASSET_CONFIG` — maps each asset to its data source and symbol
- `MACRO_ASSETS` — set of the 25 macro asset names; used by the dashboard to separate them from the trading portfolio
- `MANUAL_DATA` — manual price/indicator values for assets without API access
- `EMA_PERIOD`, `ATR_PERIOD`, `RSI_PERIOD`, `Z_SCORE_PERIOD` — indicator periods
- `VP_LOOKBACK_BARS_BY_TF` (`1d`: 90, `1w`: 52, `1M`: 24) and `VP_N_BUCKETS` (24) — Volume Profile parameters

## Adding New Assets

**Yahoo Finance (stocks, ETFs, indices, commodities, forex):**

1. Add the asset name to `ASSETS` in `trading_utils/config.py`
2. Add an entry to `ASSET_CONFIG`:
   ```python
   'MSTR':   {'source': 'yahoo', 'symbol': 'MSTR'},
   'BTC':    {'source': 'yahoo', 'symbol': 'BTC-USD'},
   'MSTY':   {'source': 'yahoo', 'symbol': 'MSTY.L'},   # LSE: append .L
   'SPX':    {'source': 'yahoo', 'symbol': '^GSPC'},     # index: prefix ^
   'GOLD':   {'source': 'yahoo', 'symbol': 'GC=F'},      # futures: append =F
   'EURUSD': {'source': 'yahoo', 'symbol': 'EURUSD=X'},  # forex: append =X
   ```
3. If the asset is a macro asset (index/commodity/forex), also add it to `MACRO_ASSETS` in `config.py`, `ASSET_CATEGORIES.macro` and the relevant group in `MACRO_SUBCATEGORIES` in `dashboard/js/dashboard.js`

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
| `data/chart_history.json` | Last 90 bars of ATR Distance, RSI, Price, EMA21, EMA50, 200DMA per asset+timeframe |
| `data/breadth.json` | Last 60 days of daily regime counts (portfolio assets) — market breadth chart |
| `data/btc_signals.json` | BTC cycle indicator confluence data consumed by `btc.html` |
| `data/onchain_cache.json` | Last-good on-chain values (7-day TTL) used when the free on-chain APIs fail |
| `data/metadata.json` | Pipeline run metadata (last updated, asset count) |
| `data/market_caps.json` | CoinGecko market cap and rank data for crypto assets |

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

## Data sources and limitations

**Sources.** Prices come from Yahoo Finance via the `yfinance` library — an *unofficial* scraper of an undocumented interface, not an official API. It can change or break without notice, is subject to Yahoo's own terms of use, and is intended here for personal/research use. Other sources: GeckoTerminal (D2X), CoinEx via CCXT (SCP), CoinGecko (market caps, BTC dominance, stablecoin supply), alternative.me (Fear & Greed), mempool.space, FRED, SoSoValue, BGeometrics/Bitbo/CoinMetrics and Blockchair (BTC page).

**Where the market-context numbers live.** The top-level fields of `data/dashboard.json`: `fear_greed` (alternative.me), `btc_dominance` (CoinGecko), `altseason` (computed from `history.csv`: % of tracked cryptos beating BTC over 90 days). Each is `null` when its source is unavailable. The full structure of `dashboard.json` is described in [`docs/DATA_SCHEMA.md`](docs/DATA_SCHEMA.md).

**BTC Cycle Signals (`dashboard/btc.html`).** The page does not call any API itself: `calculate_metrics.py` gathers the signals in CI and writes `data/btc_signals.json`, which the page loads. Signal groups: price structure (from `history.csv`), sentiment and positioning (Fear & Greed, funding, OI, BTC dominance, altseason, ETF flows), mining and liquidity (hash ribbons and Puell multiple via mempool.space, stablecoin supply via CoinGecko, global M2 via FRED), and on-chain (MVRV Z-score, NUPL, SOPR via BGeometrics, with Bitbo and CoinMetrics v4 as fallbacks; coin-days-destroyed via Blockchair). Optional CI secrets: `FRED_API_KEY`, `SOSOVALUE_API_KEY`, `BGEOMETRICS_API_KEY`, `BITBO_API_KEY`, `BLOCKCHAIR_API_KEY`, `COINMETRICS_API_KEY`. Three cards (RHODL ratio, LTH/STH MVRV cross, Reserve Risk) stay locked: they need UTXO age-band data that is only available from Glassnode's paid tier.

**Known data limitations.**

- **Funding rate / open interest are `null` everywhere in CI.** Binance returns HTTP 451 to GitHub-hosted runners, Bybit returns 403, and the CoinGecko derivatives fallback returns no per-symbol data. The fields and badges exist but stay empty until a reachable source is configured.
- **SCP has no monthly data** — CoinEx does not offer monthly candles. **D2X has about 2.7 years of monthly history** — GeckoTerminal's free tier returns ~1,000 daily candles in a single call and monthly bars are resampled from those. **DRIFT has no data at all** (see above).
- **Thin history.** Percentile badges and signal tiers need at least 30 bars, so recently listed assets show none on the monthly timeframe (a new asset needs ~2.5 years of monthly bars). The Volume Profile needs at least 20 bars with volume.
- **Timeframe scope.** `rs_vs_btc` is computed for the daily timeframe only, and the alignment badge compares daily with weekly only — both are `null` for `1M` by design.
- **Open bars.** The latest weekly and monthly bar is still open. It is refreshed on every daily run, so it reflects the most recent fetch; a weekly price can differ slightly from the latest daily close depending on fetch timing.
- **Unfinished bars.** Yahoo sometimes returns an unfinished latest bar without a close (seen for forex and Asian indices). The tracker ignores it and uses the newest bar that has a close, so no empty rows are stored; the backfill does the same. The Excel workbook keeps every row it ever received, so `update_history.py` imports only rows that are finished (have a Price), not dated in the future, and from the last 45 days — otherwise a backfill's cleaned rows would be overwritten by stale workbook rows on the next run.

## Disclaimer

This project is for information and research only and is **not financial advice**. Indicators describe where price sits relative to its own history; they do not predict returns, and extreme readings can become more extreme. Data comes from unofficial third-party sources, may be delayed, incomplete, or wrong, and is provided without any warranty. Do your own research before making any decision.

## Notes

- LSE ETFs require the `.L` suffix for Yahoo Finance (e.g., `MSTY.L`)
- All `yf.download()` calls use `auto_adjust=False` — required for LSE ETFs to prevent dividend payments from corrupting historical EMA/ATR values
- If more than 60 (asset, timeframe) pairs fail, or High/Low is missing for more than 25% of the fetched records, the CI job exits non-zero (threshold accounts for newer crypto tokens and macro assets that may be temporarily unavailable)
- The pipeline is idempotent — re-running does not create duplicate rows in `history.csv`
- `data/history.csv` is the source of truth; all other data files are derived from it
- Volume Profile uses daily OHLCV bar ranges (uniform volume distribution within H/L) — coarser than TradingView's tick-based VPVR but sufficient as a support/resistance zone signal
- `NATGAS` is the symbol for natural gas futures (Yahoo: `NG=F`); the name avoids collision with the `GAS` crypto asset (Ethereum GAS token)
