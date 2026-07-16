# Dashboard Enhancement Backlog

## High signal, low effort — frontend only (no pipeline changes)

- [x] **Timeframe toggle on Portfolio cards**
  Cards are locked to daily view. Add a D / W toggle at the top of the Portfolio tab.
  Data already exists in `dashboard.json` for both timeframes — purely a rendering change in `dashboard.js`.

- [x] **ATR Distance sparklines on cards**
  `chart_history.json` already stores 90 bars per asset. Render a small inline sparkline (last ~14 bars of ATR Distance) inside each portfolio card to show direction at a glance without opening Drilldown.

- [x] **Starred / watchlist**
  `localStorage` only — no backend. Up to 10 assets pinnable. Starred assets float to the top of the Portfolio tab. Star button on every card header. Max 10 pinned.

- [x] **Quick search**
  Text input above the filter bar. Filters all portfolio assets live as you type.

- [x] **Market cap sort on Portfolio tab**
  "Market Cap ↓" sort option in the Portfolio filter bar. Ranks by `market_cap_rank` ascending (nulls last).

---

## High signal, moderate effort — pipeline + frontend

- [x] **Multi-timeframe alignment badge**
  `calculate_metrics.py` compares daily and weekly regimes per asset and writes an `alignment` field to `dashboard.json` (`aligned-bullish` | `aligned-bearish` | `diverging`).
  Frontend: small ↑↑/↓↓/↕ badge on portfolio cards; TF Align row in Drilldown summary.

- [x] **Regime transition flag**
  `calculate_metrics.py` compares today's regime with the previous row. Sets `regime_changed: true` and `prev_regime` in the `current` object.
  Frontend: animated yellow pulse dot on cards; "Recent Regime Transitions" section above portfolio cards showing `ASSET: OldRegime → NewRegime` chips.

- [x] **ATR compression metric**
  Linear regression slope over the last 10 ATR bars (relative to mean ATR), stored as `atr_trend` (`expanding` | `compressing` | `flat`) in `dashboard.json`.
  Frontend: coloured icon + label on cards; ATR Trend row in Drilldown summary grid.

---

## Meaningful additions — new data / pipeline work

- [x] **Market breadth history chart**
  `calculate_metrics.py` writes daily counts of portfolio assets per regime to `data/breadth.json`.
  Frontend: stacked bar chart on the Portfolio tab showing 60-day regime distribution history. Hidden when data unavailable.

- [x] **Relative strength vs BTC (crypto assets)**
  `calculate_metrics.py` computes `(asset_return_30d / BTC_return_30d)` for 28 crypto assets and writes as `rs_vs_btc` to `dashboard.json`.
  Frontend: RS/BTC badge on crypto cards (outperforming ↑ / underperforming ↓ with multiplier); RS/BTC row in Drilldown summary.

---

## Tier 1 — High value, moderate effort (build next)

- [x] **Crypto Fear & Greed Index badge**
  Single daily number (0–100) from alternative.me — free, no-auth API. Extreme Fear (< 25) precedes bounces; Extreme Greed (> 75) is a caution signal. Display as a gauge or labelled badge on the Portfolio tab health bar. One `requests.get()` call added to the pipeline, refreshes daily.

- [x] **Funding rates + Open Interest (crypto)**
  CoinGlass free tier: per-asset funding rates and aggregated open interest. High positive funding + rising OI = crowded long = squeeze risk; negative funding + rising OI = short squeeze setup. Two extra fields on crypto cards and a sparkline in Drilldown.

- [x] **BTC Dominance + Altcoin Season Index**
  BTC.D above ~65% suppresses altcoins; falling BTC.D with ETH/BTC strengthening = capital rotation. CMC Altcoin Season Index (free endpoint): % of top-100 alts outperforming BTC over 90 days (>75 = altseason, <25 = BTC season). Add as a persistent macro bar or dedicated row on the Portfolio tab.

- [x] **ADX (Average Directional Index)**
  Measures trend strength independently of direction (0–100; >25 = trending, <20 = ranging). ATR Distance tells you where price is; ADX tells you whether the move has momentum. Low ATR Distance + high ADX = strong oversold trend vs. low + low ADX = sideways drift. Pipeline field + Drilldown metric; optionally an icon on cards. Computable from existing OHLCV data.

- [x] **Bollinger Band position / %B**
  `%B = (Price − Lower Band) / (Upper Band − Lower Band)`. Below 0 = outside lower band (oversold breakout), above 1 = outside upper band. Complements ATR Distance with a volatility-adjusted absolute band. Also exposes BB squeezes (bandwidth at multi-month lows) — reliable pre-signal for large moves. Computable from existing price data.

---

## Tier 2 — Good value, lower effort (quick wins)

- [x] **Price alerts / threshold notifications**
  Browser Notification API alert when an asset crosses a regime boundary or a user-set ATR Distance threshold. Store thresholds in `localStorage`. Entirely client-side, no pipeline changes.

- [x] **Composite signal score**
  Aggregate existing signals (ATR Distance percentile + RSI Z-Score + ADX + VP position + alignment) into a single −10 to +10 score per asset. Shown as a sortable column. Simple weighted formula — reduces cognitive load for "what's the best setup right now."

---

## Tier 3 — High effort, high payoff (discuss before building)

- [ ] **Exchange flow badge (crypto)**
  CoinGlass / CryptoQuant free tiers: net exchange inflows (selling pressure) vs. outflows (accumulation). Simple in / out / neutral badge on crypto cards.
  _Requires API key (CoinGlass/CryptoQuant free tier) — discuss before building._

- ~~**Correlation heatmap (crypto)**~~ _(removed — low-signal, rarely visited; cleaned up in debug/UX pass)_

- [ ] **Social sentiment timeline**
  Twitter/X sentiment via free APIs (CoinyBubble, cfgi.io) correlated with price for individual tokens. Higher integration complexity (rate limits, NLP). Strong signal quality justifies v2 roadmap placement.

- [ ] **Hypothetical portfolio overlay**
  User inputs holdings (asset + weight or $ size) stored in `localStorage`. Dashboard computes weighted-average ATR Distance exposure and displays which regime the combined portfolio sits in, alongside a regime breakdown by allocation. Entirely client-side — no pipeline changes required.

---

- [x] **BTC Cycle Signals page**
  Standalone `dashboard/btc.html` page with 21 signal cards across 4 sections (Price Structure, Sentiment & Positioning, Mining & Liquidity, On-chain locked). Confluence banner shows accumulate/distribute/neutral counts and a phase badge. Pipeline: `generate_btc_signals_json()`, `fetch_hash_ribbons()`, `fetch_stablecoin_trend()` added to `calculate_metrics.py`. Path constant `BTC_SIGNALS_JSON_PATH` in `trading_utils/config.py`. Linked from main dashboard header via `₿ BTC` link.

- [x] **BTC Cycle Signals — Phase 2 (Global M2 + landing page)**
  `fetch_global_m2()` added to `calculate_metrics.py` using FRED `WM2NS` weekly series (free, requires `FRED_API_KEY` secret). M2 fields added to `liquidity` section of `btc_signals.json`; `sig_m2` counted in confluence when key is present (max 13 active signals). Global M2 card added as 3rd card in Mining & Liquidity. ETF Net Daily Flows added as locked card (6th in Sentiment & Positioning). `FRED_API_KEY` wired into CI. `landing.html` updated with 7th feature card and step, CTA updated to "7 views". `btc.html` footer updated.

- [x] **BTC Cycle Signals — ETF Flows (SoSoValue) + funding rate fallback chain**
  `fetch_etf_flows()` implemented using SoSoValue `GET /etfs/summary-history` (requires `SOSOVALUE_API_KEY` secret). ETF Flows card is active when key is set, locked otherwise. Funding rate fallback chain: Binance (451 geo-blocked from GitHub Actions) → Bybit (403) → `_fetch_coingecko_futures()` (`/api/v3/derivatives`, no geo-block, works from CI). `SOSOVALUE_API_KEY` wired into CI.

- [x] **BTC Cycle Signals — Puell Multiple**
  `fetch_puell_multiple(btc_prices)` added to `calculate_metrics.py`. Fetches 2 years of block reward data from mempool.space `/api/v1/mining/blocks/rewards/2y` (free, no auth), joins with BTC price history from `history.csv`, computes 365-day MA of daily miner revenue (USD), derives Puell Multiple. Signal: <0.6 = accumulate, >3.0 = distribute. Added as 4th card in Mining & Liquidity; always counted in confluence.

- [x] **BTC Cycle Signals — On-chain unlock via Coinmetrics Community API**
  `fetch_coinmetrics_onchain()` added to `calculate_metrics.py`. Single call to `community-api.coinmetrics.io` (free, no API key) fetches `CapRealUSD`, `CapMrktCurUSD`, `SOPR`, `CDD`. Derives: MVRV Z-Score (Z < 0 = accumulate, Z ≥ 6 = distribute), NUPL (<0 = accumulate, ≥0.5 = distribute), SOPR signal (<0.98 = accumulate, >1.05 = distribute), CVDD trend (90d MA change). New `on_chain` section added to `btc_signals.json`. On-Chain section on `btc.html` now shows 4 active cards (MVRV Z-Score, NUPL, SOPR, CVDD) + 3 locked (RHODL Ratio, LTH/STH MVRV Cross, Reserve Risk — require Glassnode UTXO age-band data, no free alternative). All 4 on-chain signals counted in confluence unconditionally. `landing.html` and `CLAUDE.md` updated.

---

## Previously completed

- [x] **Timeframe toggle on Portfolio cards**
- [x] **ATR Distance sparklines on cards**
- [x] **Starred / watchlist**
- [x] **Quick search**
- [x] **Market cap sort on Portfolio tab**
- [x] **Multi-timeframe alignment badge**
- [x] **Regime transition flag**
- [x] **ATR compression metric**
- [x] **Market breadth history chart**
- [x] **Relative strength vs BTC (crypto assets)**
- [x] **Crypto Fear & Greed Index badge**
- [x] **Funding rates + Open Interest (crypto)**
- [x] **BTC Dominance + Altcoin Season Index**
- [x] **ADX (Average Directional Index)**
- [x] **Bollinger Band position / %B**
- [x] **Price alerts / threshold notifications**
- [x] **Composite signal score**
- [x] **Debug pass + UX quick wins** _(defaultdict import fix, defensive confluence guard, docstring fix; phase badge first on BTC page; mobile nav labels hidden; badge tooltips; BTC era note; Corr tab removed; 13 new tests)_
- [x] **Hamburger nav for mobile** _(≤520px: ☰ toggle replaces bottom tab bar; slide-up drawer with all 5 tabs; backdrop + Escape to close; body scroll lock)_
- [x] **Novice/Expert card detail toggle** _(filter-bar chip; Novice hides 11 advanced fields and alignment header badge; Expert (default) shows all; persists to `localStorage`)_
- [x] **Ragequit / Blow-off regime tiers** _(7-tier regime system: Ragequit < −7 (deep purple) and Blow-off > +7 (hot pink) added as outer extremes; Capitulation bounded −7..−4, Mania +4..+7; implemented across classify_regime, breadth, signal strength, gauge, chart annotations, sparklines, macro zones, CSS, landing page, BTC tooltip, CLAUDE.md; post-merge review fixed a Drilldown Funding-Rate/OI variable bug and a test-isolation gap)_
- [x] **EUR price on BTC page** _(server-side Frankfurter/ECB rate fetched in CI, stored as `price_eur` in `btc_signals.json`; CSP-safe)_
- [x] **New NASDAQ assets** _(KEEL, BTDR, BTBT, FUFU added to config and dashboard categories)_
- [x] **Rankings tab: Daily/Weekly toggle** _(chip toggle mirroring Portfolio pattern; `rankingsFilter.timeframe` drives `renderRankings()`)_
- [x] **Rankings tab: category filter** _(All/Crypto/NASDAQ/LSE chips; composes with the timeframe toggle)_
