# Data schema

Reference for the files the pipeline produces. Everything is derived from `data/history.csv` (the source of truth); the dashboard reads the copies under `dashboard/assets/`.

| File | Written by | Consumed by |
|------|-----------|-------------|
| `data/history.csv` | `update_history.py`, `backfill_historical.py` | `calculate_metrics.py` |
| `data/master.csv` | `update_history.py` | humans / debugging |
| `data/dashboard.json` | `calculate_metrics.py` | `dashboard/assets/data.json` |
| `data/chart_history.json` | `calculate_metrics.py` | Drilldown charts |
| `data/breadth.json` | `calculate_metrics.py` | Portfolio breadth chart |
| `data/btc_signals.json` | `calculate_metrics.py` | `dashboard/btc.html` |
| `data/market_caps.json` | `crypto_tracker.py` | `calculate_metrics.py` |
| `data/onchain_cache.json` | `calculate_metrics.py` | `calculate_metrics.py` (fallback) |
| `data/metadata.json` | `update_history.py` | humans / debugging |

## Conventions

- **Timeframe keys:** `1d`, `1w`, `1M` (capital M — CCXT's monthly convention). `history.csv` may also contain `Daily`/`Weekly`/`Monthly`; they are normalised on read.
- **Dates:** `YYYY-MM-DD`. A weekly bar is dated by the Monday that starts its week and a monthly bar by the first of the month (Yahoo and the D2X resample alike), so no bar is ever dated in the future; the latest bar of each timeframe is still *open* and is refreshed on every run.
- **`null`:** means "not available", never zero. `NaN`/`inf` are converted to `null` before writing JSON. Every optional field below can be `null`.

## `data/history.csv`

One row per `Date` + `Asset` + `Timeframe` (unique).

| Column | Unit / meaning |
|--------|---------------|
| `Date`, `Asset`, `Timeframe` | key |
| `Price` | close, in the asset's quote currency |
| `EMA21`, `ATR` | price units; 21-period EMA and 14-period Wilder ATR (SMA-seeded, TradingView-compatible) |
| `RSI`, `RSI_Z_Score` | 0–100; z-score of RSI over 20 bars |
| `ATR_Distance` | `(Price − EMA21) / ATR`, in ATR multiples; empty when `ATR = 0` |
| `Pct_Above_EMA` | percent |
| `High`, `Low` | bar high/low, price units |
| `Volume` | the source's volume: USD for Yahoo crypto, shares for stocks and LSE ETFs, `0` for forex and many indices, base-token units for CCXT/GeckoTerminal. Comparable within one asset only |

ADX and Bollinger Bands are **not** stored; they are derived from `Price`/`High`/`Low` in `calculate_metrics.py`, like EMA50 and the 200DMA.

## `data/dashboard.json`

```
{
  "metadata":      { last_updated, assets_count, records_count, date_range: {start, end} },  // end = newest daily bar
  "fear_greed":    { value: 0-100, label, timestamp: "<unix seconds as string>" } | null,
  "btc_dominance": percent | null,
  "altseason":     { score: 0-100, label, alts_outperforming, total } | null,
  "assets": {
    "<ASSET>": {
      "1d" | "1w" | "1M": { "historical": {...}, "current": {...} }
    }
  }
}
```

An asset appears under `assets` only if it has data; a timeframe key is missing when that asset/timeframe has none (e.g. `SCP` has no `1M`). `current` is `null` when the latest row is more than 60 days behind the newest date in the dataset (delisted/renamed tickers) — `DRIFT` is such a case.

### `historical` — distribution of ATR Distance over the asset's whole history

`atr_min`, `atr_max`, `atr_mean`, `atr_std`, `atr_percentile_25/50/75/90`, `sample_size` (bars). Percentile badges and signal tiers are only shown when `sample_size ≥ 30`.

### `current` — the latest bar

| Field | Unit / meaning |
|-------|---------------|
| `date`, `price`, `ema21`, `atr`, `rsi`, `rsi_z_score` | as in `history.csv` |
| `atr_distance` | ATR multiples |
| `pct_above_ema` | percent |
| `regime` | `Ragequit` (< −7), `Capitulation` (−7…−4), `Accumulation` (−4…−2), `Trend` (−2…2), `Distribution` (2…4), `Mania` (4…7), `Blow-off` (> 7); `Unknown` when `atr_distance` is `null` |
| `regime_changed`, `prev_regime` | regime differs from the previous bar |
| `atr_percentile` | 0–100, share of historical bars with a lower ATR Distance |
| `price_change_pct` | percent vs the previous bar |
| `atr_trend` | `expanding` / `compressing` / `flat` (slope of the last 10 ATR values); `null` under 5 bars |
| `adx` | 0–100, 14-period; `null` under 27 valid bars or when the latest bar has no High/Low |
| `bb_pct_b` | Bollinger %B (20, 2σ): 0 = lower band, 1 = upper band, outside 0–1 = beyond the bands; `null` under 20 bars or a flat price |
| `bb_bandwidth` | `(upper − lower) / mid × 100`, percent |
| `ema50`, `ema50_distance` | price units; ATR multiples. `null` under 50 bars |
| `ma200d`, `pct_above_200d` | 200-bar SMA in price units; percent. `null` under 200 bars |
| `vp_poc`, `vp_vah`, `vp_val` | Volume Profile point of control / value-area high / low, price units |
| `vp_position` | `above_vah`, `in_value_area`, `at_poc` (within ±1.5 buckets), `below_val` |
| `vp_dist_from_poc` | `(price − POC) / ATR`, ATR multiples |
| `vp_buckets` | 24 objects `{p, v, is_poc, in_va}`: `p` = bucket midpoint (price units), `v` = volume attributed to the bucket (same unit as `Volume`, see above), `is_poc` / `in_va` = flags. All `vp_*` are `null` without ≥ 20 bars that have volume |
| `market_cap`, `market_cap_rank` | USD; crypto only |
| `alignment` | `aligned-bullish`, `aligned-bearish`, `diverging` — daily vs weekly regime; set on `1d` and `1w` only |
| `rs_vs_btc` | 30-day return ratio asset / BTC; `1d` and crypto only |
| `funding_rate` | percent per 8 h; crypto only. `null` for all assets while the sources are geo-blocked from CI |
| `open_interest_usd` | USD; crypto only, same caveat |

## `data/chart_history.json`

`{ "<ASSET>": { "1d": [bar, …], "1w": [...], "1M": [...] } }` — the last 90 bars, oldest first. Bar keys are abbreviated: `d` date, `a` ATR Distance, `r` RSI, `p` price, `e` EMA21, `e5` EMA50, `m2` 200DMA.

## `data/breadth.json`

Last 60 daily bars of portfolio assets (macro excluded): `dates` plus one equally long array of counts per regime (`ragequit`, `capitulation`, `accumulation`, `trend`, `distribution`, `mania`, `blow-off`).

## `data/btc_signals.json`

`date`, `price`, `price_eur`, then the sections `price_indicators`, `sentiment`, `market_structure`, `mining`, `liquidity`, `on_chain` and `confluence`. Each indicator has a value plus a `signal_*` of `accumulate` / `neutral` / `distribute`; `confluence` holds the vote counts, `phase` and `strength`. A source that could not be fetched yields `null` values and a `neutral`/missing signal. Optional sections need CI secrets (see README).

## `data/market_caps.json`, `data/onchain_cache.json`, `data/metadata.json`

`market_caps.json`: `{ fetched_at, data: { ASSET: { market_cap, market_cap_rank } } }` (CoinGecko, crypto only). `onchain_cache.json`: last successful on-chain values with a fetch date (7-day TTL), used when all live APIs fail. `metadata.json`: `last_updated`, `records_count`, `assets_count` and the file paths of the run.
