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

## Bigger scope — discuss before building

- [ ] **Correlation heatmap (crypto)**
  `history.csv` has daily returns for all assets. Compute a rolling 90-day correlation matrix for the 28 crypto assets. New tab or panel. Useful for position sizing and diversification decisions.
  _Note: computation is light; the 28×28 colour grid rendering needs design work._

- [ ] **Hypothetical portfolio overlay**
  User inputs holdings (asset + weight or $ size) stored in `localStorage`. Dashboard computes weighted-average ATR Distance exposure and displays which regime the combined portfolio sits in, alongside a regime breakdown by allocation.
  _Entirely client-side — no backend or pipeline changes required._
