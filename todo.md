# Dashboard Enhancement Backlog

## High signal, low effort — frontend only (no pipeline changes)

- [x] **Timeframe toggle on Portfolio cards**
  Cards are locked to daily view. Add a D / W toggle at the top of the Portfolio tab.
  Data already exists in `dashboard.json` for both timeframes — purely a rendering change in `dashboard.js`.

- [ ] **ATR Distance sparklines on cards**
  `chart_history.json` already stores 90 bars per asset. Render a small inline sparkline (last ~14 bars of ATR Distance) inside each portfolio card to show direction at a glance without opening Drilldown.

- [ ] **Starred / watchlist**
  `localStorage` only — no backend. Let the user pin up to 10 assets. Pinned assets float to the top of the Portfolio tab and get a dedicated row in Rankings.

- [ ] **Quick search**
  Text input above the filter bar. Filters all 70 assets live as you type. Useful when all categories are visible and you want one asset fast.

---

## High signal, moderate effort — pipeline + frontend

- [ ] **Multi-timeframe alignment badge**
  In `calculate_metrics.py`, compare daily and weekly regimes per asset and write an `alignment` field to `dashboard.json` (values: `aligned-bullish` | `aligned-bearish` | `diverging`).
  Frontend: small coloured dot on portfolio cards; Key Takeaways note in Drilldown.

- [ ] **Regime transition flag**
  In `calculate_metrics.py`, compare today's regime with the previous row. If changed, set `regime_changed: true` (and record `prev_regime`) in the `current` object.
  Frontend: subtle pulse indicator on cards; a "Recent Transitions" section above the portfolio cards listing assets that crossed a regime boundary in the last 1–3 days.

- [ ] **ATR compression metric**
  Compute the slope of ATR over the last 10 bars (rising = expansion, falling = compression/squeeze, flat = neutral). Store as `atr_trend` in `dashboard.json`.
  Frontend: small icon on cards and a row in the Drilldown summary grid. Compression often precedes a breakout — useful pre-signal.

---

## Meaningful additions — new data / pipeline work

- [ ] **Market breadth history chart**
  In `calculate_metrics.py`, write daily counts of assets per regime to `data/breadth.json`.
  Frontend: area chart on the Portfolio tab showing oversold% / neutral% / extended% over the last 60 days. Gives temporal context the static health bar can't provide (e.g. "oversold peak was 3 weeks ago, now recovering").

- [ ] **Relative strength vs BTC (crypto assets)**
  In `calculate_metrics.py`, compute `(asset_return_30d / BTC_return_30d)` for crypto assets and write as `rs_vs_btc`.
  Frontend: small RS badge on crypto cards (outperforming / underperforming). Useful for rotation decisions within the crypto sleeve.

- [ ] **Market cap sort on Portfolio tab**
  `data/market_caps.json` is already populated via CoinGecko. Expose "Market Cap ↓" as a sort option in the Portfolio filter bar. Lets you see where large-caps sit in the regime distribution vs smaller-caps instantly.

---

## Bigger scope — discuss before building

- [ ] **Correlation heatmap (crypto)**
  `history.csv` has daily returns for all assets. Compute a rolling 90-day correlation matrix for the 28 crypto assets. New tab or panel. Useful for position sizing and diversification decisions.
  _Note: computation is light; the 28×28 colour grid rendering needs design work._

- [ ] **Hypothetical portfolio overlay**
  User inputs holdings (asset + weight or $ size) stored in `localStorage`. Dashboard computes weighted-average ATR Distance exposure and displays which regime the combined portfolio sits in, alongside a regime breakdown by allocation.
  _Entirely client-side — no backend or pipeline changes required._
