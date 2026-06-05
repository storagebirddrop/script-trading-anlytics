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

- [x] **Correlation heatmap (crypto)**
  Rolling 90-day Pearson correlation matrix for the 28 crypto assets (`df.corr()` — computation is trivial). 28×28 colour-coded grid with hover tooltips showing the coefficient. Useful for identifying uncorrelated setups and rotation opportunities.
  _Note: the grid rendering and tab placement are the main design decisions._

- [ ] **Social sentiment timeline**
  Twitter/X sentiment via free APIs (CoinyBubble, cfgi.io) correlated with price for individual tokens. Higher integration complexity (rate limits, NLP). Strong signal quality justifies v2 roadmap placement.

- [ ] **Hypothetical portfolio overlay**
  User inputs holdings (asset + weight or $ size) stored in `localStorage`. Dashboard computes weighted-average ATR Distance exposure and displays which regime the combined portfolio sits in, alongside a regime breakdown by allocation. Entirely client-side — no pipeline changes required.

---

- [x] **BTC Cycle Signals page**
  Standalone `dashboard/btc.html` page with 21 signal cards across 4 sections (Price Structure, Sentiment & Positioning, Mining & Liquidity, On-chain locked). Confluence banner shows accumulate/distribute/neutral counts and a phase badge. Pipeline: `generate_btc_signals_json()`, `fetch_hash_ribbons()`, `fetch_stablecoin_trend()` added to `calculate_metrics.py`. Path constant `BTC_SIGNALS_JSON_PATH` in `trading_utils/config.py`. Linked from main dashboard header via `₿ BTC` link.

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
- [x] **Correlation heatmap (crypto)**
