'use strict';

let btcData = null;

// ── Formatting helpers ────────────────────────────────────────────────────────

function fmtPrice(v) {
    if (v == null) return 'N/A';
    if (v >= 1000) return '$' + v.toLocaleString('en-US', { maximumFractionDigits: 0 });
    if (v >= 1) return '$' + v.toLocaleString('en-US', { maximumFractionDigits: 2 });
    return '$' + v.toFixed(4);
}

function fmtPct(v, decimals) {
    if (v == null) return 'N/A';
    const d = decimals != null ? decimals : 1;
    return (v >= 0 ? '+' : '') + v.toFixed(d) + '%';
}

function fmtNum(v, decimals) {
    if (v == null) return 'N/A';
    return v.toFixed(decimals != null ? decimals : 2);
}

function fmtLargeNum(v) {
    if (v == null) return 'N/A';
    if (v >= 1e12) return '$' + (v / 1e12).toFixed(2) + 'T';
    if (v >= 1e9)  return '$' + (v / 1e9).toFixed(1) + 'B';
    if (v >= 1e6)  return '$' + (v / 1e6).toFixed(1) + 'M';
    return '$' + v.toLocaleString('en-US', { maximumFractionDigits: 0 });
}

// ── DOM helpers (CSP-safe — no innerHTML for dynamic data) ────────────────────

function signalBadgeEl(signal, customLabel) {
    const LABELS = {
        accumulate: 'Accumulate',
        distribute: 'Distribute',
        neutral:    'Neutral',
        warning:    'Warning',
        na:         'N/A',
        locked:     'Locked',
    };
    const el = document.createElement('span');
    el.className = 'signal-badge signal-badge--' + (signal || 'na');
    el.textContent = customLabel || LABELS[signal] || 'N/A';
    return el;
}

function phaseBadgeClass(phase, strength) {
    const key = (phase + '-' + strength).toLowerCase().replace(/\s+/g, '-');
    const MAP = {
        'accumulation-strong':   'phase-badge--strong-accumulation',
        'accumulation-moderate': 'phase-badge--accumulation',
        'accumulation-weak':     'phase-badge--weak-accumulation',
        'distribution-strong':   'phase-badge--strong-distribution',
        'distribution-moderate': 'phase-badge--distribution',
        'distribution-weak':     'phase-badge--weak-distribution',
        'neutral-mixed':         'phase-badge--mixed',
    };
    return MAP[key] || 'phase-badge--neutral';
}

// ── Confluence banner ─────────────────────────────────────────────────────────

function renderConfluenceBanner(d) {
    const banner = document.getElementById('confluence-banner');
    if (!banner) return;
    const c = d.confluence;

    const stats = document.createElement('div');
    stats.className = 'confluence-stats';

    [
        { key: 'accumulate', label: 'Accumulate', value: c.accumulate_count },
        { key: 'neutral',    label: 'Neutral',    value: c.neutral_count    },
        { key: 'distribute', label: 'Distribute', value: c.distribute_count },
    ].forEach((item, i) => {
        if (i > 0) {
            const div = document.createElement('div');
            div.className = 'conf-divider';
            stats.appendChild(div);
        }
        const stat = document.createElement('div');
        stat.className = 'conf-stat';

        const count = document.createElement('div');
        count.className = 'conf-count conf-count--' + item.key;
        count.textContent = item.value;

        const label = document.createElement('div');
        label.className = 'conf-label';
        label.textContent = item.label;

        stat.appendChild(count);
        stat.appendChild(label);
        stats.appendChild(stat);
    });

    banner.appendChild(stats);

    const badge = document.createElement('span');
    badge.className = 'phase-badge ' + phaseBadgeClass(c.phase, c.strength);
    const strengthLabel = (c.strength && c.strength !== 'mixed' && c.strength !== 'insufficient data')
        ? ' · ' + c.strength.charAt(0).toUpperCase() + c.strength.slice(1)
        : '';
    badge.textContent = c.phase + strengthLabel;
    banner.appendChild(badge);
}

// ── Signal card builder ───────────────────────────────────────────────────────

function renderSignalCard(cfg) {
    const card = document.createElement('div');
    card.className = 'signal-card';
    if (cfg.tooltip) card.title = cfg.tooltip;

    const header = document.createElement('div');
    header.className = 'signal-card-header';

    const name = document.createElement('span');
    name.className = 'signal-name';
    name.textContent = cfg.name;
    header.appendChild(name);
    header.appendChild(signalBadgeEl(cfg.signal || 'na'));
    card.appendChild(header);

    const val = document.createElement('div');
    val.className = 'signal-value signal-value--' + (cfg.signal || 'na');
    val.textContent = cfg.value || 'N/A';
    card.appendChild(val);

    const ctx = document.createElement('div');
    ctx.className = 'signal-context';
    ctx.textContent = cfg.context || '';
    card.appendChild(ctx);

    return card;
}

function renderLockedCard(cfg) {
    const card = document.createElement('div');
    card.className = 'signal-card signal-card--locked';

    const header = document.createElement('div');
    header.className = 'signal-card-header';

    const name = document.createElement('span');
    name.className = 'signal-name';
    name.textContent = cfg.name;
    header.appendChild(name);
    header.appendChild(signalBadgeEl('locked', 'Locked'));
    card.appendChild(header);

    const val = document.createElement('div');
    val.className = 'signal-value signal-value--na';
    val.textContent = '—';
    card.appendChild(val);

    const desc = document.createElement('div');
    desc.className = 'signal-context';
    desc.textContent = cfg.description;
    card.appendChild(desc);

    const lbl = document.createElement('div');
    lbl.className = 'signal-locked-label';
    lbl.textContent = cfg.lockLabel || 'Requires Glassnode API key';
    card.appendChild(lbl);

    return card;
}

function renderSection(title, cards) {
    const section = document.createElement('div');
    section.className = 'signal-section';

    const h = document.createElement('h2');
    h.className = 'signal-section-title';
    h.textContent = title;
    section.appendChild(h);

    const grid = document.createElement('div');
    grid.className = 'signal-grid';
    cards.forEach(c => grid.appendChild(c));
    section.appendChild(grid);

    return section;
}

// ── Build all four sections ───────────────────────────────────────────────────

function buildAllSections(d) {
    const container = document.getElementById('signals-container');
    if (!container) return;

    const pi   = d.price_indicators || {};
    const sent = d.sentiment        || {};
    const mkt  = d.market_structure || {};
    const mine = d.mining           || {};
    const liq  = d.liquidity        || {};

    // ── Price Structure ───────────────────────────────────────────────────────
    const priceCards = [

        renderSignalCard({
            name: '200-Week MA',
            value: pi.ma200w ? fmtPrice(pi.ma200w) : 'N/A',
            context: pi.pct_above_200w != null
                ? (pi.pct_above_200w >= 0
                    ? 'Price is ' + pi.pct_above_200w + '% above 200WMA'
                    : 'Price is ' + Math.abs(pi.pct_above_200w) + '% below 200WMA — historically deep value zone')
                : 'Insufficient weekly history',
            signal: pi.signal_200w,
            tooltip: '200-week SMA of BTC close. Below = long-term value zone; above 3× = historically extreme extension.',
        }),

        renderSignalCard({
            name: '200-Day MA',
            value: pi.ma200d ? fmtPrice(pi.ma200d) : 'N/A',
            context: pi.pct_above_200d != null
                ? (pi.pct_above_200d >= 0
                    ? 'Price is ' + pi.pct_above_200d + '% above 200DMA'
                    : 'Price is ' + Math.abs(pi.pct_above_200d) + '% below 200DMA — cyclical support level')
                : 'Insufficient daily history',
            signal: pi.signal_200d,
            tooltip: '200-day SMA — classic bull/bear dividing line. Below = accumulation zone; above 1.5× = distribution risk.',
        }),

        renderSignalCard({
            name: 'Pi Cycle Top',
            value: pi.pi_cycle_gap_pct != null ? fmtPct(pi.pi_cycle_gap_pct) + ' gap' : 'N/A',
            context: pi.pi_cycle_gap_pct != null
                ? (pi.pi_cycle_gap_pct <= 5
                    ? '111DMA near 350DMA×2 — Pi Cycle top warning'
                    : (pi.pi_cycle_gap_pct > 30
                        ? 'Large gap to 350DMA×2 — safely below top signal'
                        : '111DMA: ' + fmtPrice(pi.pi_cycle_111d) + ' vs 350DMA×2: ' + fmtPrice(pi.pi_cycle_350d_2x)))
                : 'Insufficient data (need 350 daily bars)',
            signal: pi.signal_pi_cycle,
            tooltip: 'When 111DMA crosses 350DMA×2 it has historically marked cycle tops. Gap > 30% = safe; ≤ 5% = top warning.',
        }),

        renderSignalCard({
            name: 'RSI Daily',
            value: pi.rsi_daily != null ? fmtNum(pi.rsi_daily, 1) : 'N/A',
            context: pi.rsi_daily == null ? 'No data'
                : pi.rsi_daily < 30  ? 'Extremely oversold on daily chart'
                : pi.rsi_daily < 40  ? 'Oversold on daily — historically good entries'
                : pi.rsi_daily > 80  ? 'Extremely overbought on daily chart'
                : pi.rsi_daily > 70  ? 'Overbought on daily — distribution zone'
                : 'Neutral daily RSI',
            signal: pi.signal_rsi_d,
            tooltip: '14-period RSI on the daily chart. < 40 = accumulate; > 70 = distribute.',
        }),

        renderSignalCard({
            name: 'RSI Weekly',
            value: pi.rsi_weekly != null ? fmtNum(pi.rsi_weekly, 1) : 'N/A',
            context: pi.rsi_weekly == null ? 'No data'
                : pi.rsi_weekly < 30 ? 'Extremely oversold on weekly — major cycle low signal'
                : pi.rsi_weekly < 40 ? 'Oversold on weekly — significant cycle opportunity'
                : pi.rsi_weekly > 80 ? 'Extremely overbought on weekly — major cycle top signal'
                : pi.rsi_weekly > 70 ? 'Overbought on weekly — scaling-out zone'
                : 'Neutral weekly RSI',
            signal: pi.signal_rsi_w,
            tooltip: 'Weekly RSI carries more weight than daily. < 40 = major accumulation zone; > 70 = cycle distribution.',
        }),

        renderSignalCard({
            name: 'ATR Distance / Regime',
            value: pi.atr_distance != null
                ? fmtNum(pi.atr_distance, 2) + ' · ' + (pi.regime || '')
                : 'N/A',
            context: pi.atr_distance != null
                ? 'Price is ' + Math.abs(pi.atr_distance).toFixed(2) + ' ATRs '
                  + (pi.atr_distance < 0 ? 'below' : 'above') + ' EMA21'
                : 'No data',
            signal: pi.signal_atr,
            tooltip: '(Price − EMA21) ÷ ATR. < −2 = Accumulation; < −4 = Capitulation; > +2 = Distribution; > +4 = Mania.',
        }),
    ];

    // ── Sentiment & Positioning ───────────────────────────────────────────────
    const fgData = sent.fear_greed;
    const sentCards = [

        renderSignalCard({
            name: 'Fear & Greed Index',
            value: fgData ? fgData.value + ' — ' + fgData.label : 'N/A',
            context: !fgData ? 'Data unavailable'
                : fgData.value <= 25 ? 'Extreme Fear: historically aligns with cycle bottoms'
                : fgData.value <= 40 ? 'Fear: negative sentiment — opportunity zone'
                : fgData.value >= 75 ? 'Extreme Greed: historically aligns with cycle tops'
                : fgData.value >= 60 ? 'Greed: caution warranted — reduce exposure'
                : 'Neutral market sentiment',
            signal: sent.signal_fear_greed || (fgData ? 'neutral' : null),
            tooltip: 'Crypto Fear & Greed Index (alternative.me). Composite of volatility, momentum, social signals, dominance, and trends.',
        }),

        renderSignalCard({
            name: 'Funding Rate',
            value: sent.funding_rate != null ? fmtNum(sent.funding_rate, 4) + '% / 8h' : 'N/A',
            context: sent.funding_rate == null ? 'No Binance perpetual data'
                : sent.funding_rate < -0.01 ? 'Negative funding — shorts paying longs; bearish overcrowding relieved'
                : sent.funding_rate > 0.1   ? 'High positive funding — crowded longs; squeeze risk elevated'
                : sent.funding_rate > 0.03  ? 'Elevated funding — market leaning long, monitor for squeeze'
                : 'Neutral funding — balanced leverage positioning',
            signal: sent.signal_funding || (sent.funding_rate != null ? 'neutral' : null),
            tooltip: 'Binance USDT-M perpetual funding rate. Negative = shorts crowded (contrarian bullish); > +0.1%/8h = longs overcrowded (squeeze risk).',
        }),

        renderSignalCard({
            name: 'Open Interest',
            value: sent.open_interest_usd != null ? fmtLargeNum(sent.open_interest_usd) : 'N/A',
            context: sent.open_interest_usd != null
                ? 'Binance USDT-M BTC perpetual — informational'
                : 'Data unavailable',
            signal: sent.signal_oi || (sent.open_interest_usd != null ? 'neutral' : null),
            tooltip: 'Binance USDT-M BTC perpetual open interest in USD. Rising OI at cycle highs with positive funding = distribution risk.',
        }),

        renderSignalCard({
            name: 'BTC Dominance',
            value: mkt.btc_dominance != null ? fmtNum(mkt.btc_dominance, 1) + '%' : 'N/A',
            context: mkt.btc_dominance == null ? 'Data unavailable'
                : mkt.btc_dominance >= 60 ? 'Very high dominance — BTC season; capital concentrated in BTC'
                : mkt.btc_dominance >= 50 ? 'Elevated dominance — BTC outperforming alts'
                : mkt.btc_dominance >= 40 ? 'Moderate dominance — mixed capital flows'
                : 'Low dominance — altcoin season; historically late-cycle for BTC',
            signal: mkt.signal_btcd || 'neutral',
            tooltip: 'BTC market cap as % of total crypto market. Rising = BTC season; falling = late-cycle capital rotation into alts.',
        }),

        renderSignalCard({
            name: 'Altseason Score',
            value: mkt.altseason
                ? mkt.altseason.score + ' — ' + mkt.altseason.label
                : 'N/A',
            context: mkt.altseason
                ? mkt.altseason.alts_outperforming + '/' + mkt.altseason.total
                  + ' alts outperformed BTC over 90 days'
                : 'Insufficient history',
            signal: mkt.signal_alts || (mkt.altseason ? 'neutral' : null),
            tooltip: 'Altcoin Season Index: % of tracked crypto assets outperforming BTC over 90 days. < 25 = BTC season (accumulate BTC); > 75 = alt season (late cycle).',
        }),

        (() => {
            const ef = sent.etf_flows;
            if (ef) {
                const inflow = ef.net_inflow_usd;
                const flow7d = ef.flow_7d_usd;
                const aum    = ef.total_net_assets_usd;
                const parts  = [];
                if (flow7d != null) parts.push('7d: ' + (flow7d >= 0 ? '+' : '') + (flow7d / 1e9).toFixed(2) + 'B');
                if (aum    != null) parts.push('AUM: $' + (aum / 1e9).toFixed(0) + 'B');
                return renderSignalCard({
                    name: 'ETF Net Daily Flows',
                    value: inflow != null
                        ? (inflow >= 0 ? '+' : '') + (inflow / 1e9).toFixed(2) + 'B USD'
                        : 'N/A',
                    context: parts.join(' · ') || (ef.date || 'Data available'),
                    signal: ef.signal,
                    tooltip: 'Net inflows/outflows across all US spot BTC ETFs (SoSoValue). The #1 demand signal post-Jan 2024 — BlackRock IBIT flows directly move spot price. Signal: >$500M = Accumulate, <−$200M = Distribute.',
                });
            }
            return renderLockedCard({
                name: 'ETF Net Daily Flows',
                description: 'Net inflows/outflows across all US spot BTC ETFs (IBIT, FBTC, ARKB, etc). Now the #1 demand signal post-Jan 2024 — BlackRock IBIT flows directly move spot price.',
                lockLabel: 'Requires SoSoValue API key',
            });
        })(),
    ];

    // ── Mining & Liquidity ────────────────────────────────────────────────────
    const hashSig = (() => {
        const s = mine.signal;
        if (!s) return null;
        if (s === 'recovery') return 'accumulate';
        return 'neutral';
    })();

    const stableSig = (() => {
        const s = liq.signal;
        if (!s) return null;
        if (s === 'expanding') return 'accumulate';
        return 'neutral';
    })();

    const miningCards = [

        renderSignalCard({
            name: 'Hash Ribbons',
            value: mine.hashrate_30d_eh != null
                ? fmtNum(mine.hashrate_30d_eh, 0) + ' EH/s (30d) · '
                  + fmtNum(mine.hashrate_60d_eh, 0) + ' (60d)'
                : 'N/A',
            context: !mine.signal ? 'Data unavailable'
                : mine.signal === 'recovery'
                    ? '30DMA crossed above 60DMA — miner capitulation ended; historically a strong buy signal'
                : mine.signal === 'capitulation'
                    ? '30DMA crossed below 60DMA — miner stress; may signal capitulation phase'
                : mine.signal === 'bull'
                    ? '30DMA above 60DMA — healthy mining conditions'
                    : '30DMA below 60DMA — miners under pressure',
            signal: hashSig,
            tooltip: 'Hash Ribbons: 30DMA vs 60DMA of daily BTC network hashrate. Recovery cross (30DMA > 60DMA) has historically been one of the best on-chain buy signals.',
        }),

        renderSignalCard({
            name: 'Stablecoin Supply',
            value: liq.combined_supply_usd != null ? fmtLargeNum(liq.combined_supply_usd) : 'N/A',
            context: (() => {
                if (liq.combined_supply_usd == null) return 'Data unavailable';
                const parts = [];
                if (liq.change_30d_pct != null) {
                    parts.push((liq.change_30d_pct >= 0 ? '+' : '') + liq.change_30d_pct.toFixed(1) + '% (30d)');
                }
                if (liq.dominance_pct != null) {
                    parts.push('Dominance: ' + liq.dominance_pct.toFixed(1) + '% of market');
                }
                if (liq.signal === 'expanding') {
                    parts.push('— growing dry powder, potential deployment ahead');
                } else if (liq.signal === 'contracting') {
                    parts.push('— stablecoins being deployed or redeemed');
                }
                return parts.join(' · ') || 'Data available';
            })(),
            signal: stableSig,
            tooltip: 'Combined USDT + USDC market cap and dominance (% of total crypto market). Expanding supply = dry powder building; high dominance = risk-off positioning.',
        }),

        renderSignalCard({
            name: 'Global M2 (12w Lag)',
            value: liq.global_m2_billion_usd != null
                ? '$' + (liq.global_m2_billion_usd / 1000).toFixed(1) + 'T'
                : 'N/A',
            context: (() => {
                if (liq.signal_global_m2 == null) return 'Requires FRED_API_KEY';
                const lag  = liq.m2_12w_lagged_change_pct;
                const curr = liq.m2_current_change_pct;
                return (lag >= 0 ? '+' : '') + lag.toFixed(1) + '% change (12–24w ago) · '
                     + 'current: ' + (curr >= 0 ? '+' : '') + curr.toFixed(1) + '%';
            })(),
            signal: liq.signal_global_m2 || null,
            tooltip: 'US M2 money supply with 12-week lag (FRED WM2NS). When M2 was expanding 12 weeks ago it historically predicts BTC strength today — the strongest macro leading indicator post-ETF launch.',
        }),
    ];

    // ── On-chain (Glassnode locked) ───────────────────────────────────────────
    const lockedCards = [
        { name: 'MVRV Z-Score',       description: 'Market Value vs Realised Value Z-score. Best standalone on-chain cycle indicator pre-ETF. Degraded post-Jan 2024 as institutions moved BTC off-chain into custodial vehicles.' },
        { name: 'NUPL',               description: 'Net Unrealised Profit/Loss. Shows aggregate emotional state of all BTC holders. < 0 = Capitulation zone; > 0.75 = Euphoria / distribution.' },
        { name: 'RHODL Ratio',        description: 'Realised HODL Ratio — ratio of short-term to long-term holder wealth. Spikes at cycle tops when short-term holders dominate.' },
        { name: 'CVDD',               description: 'Cumulative Value Days Destroyed — historically touches BTC price at every major cycle bottom.' },
        { name: 'Puell Multiple',     description: 'Daily issuance value / 365-day MA. Low = miners underpaid (bottom); high = miners selling into strength (top).' },
        { name: 'aSOPR',              description: 'Adjusted Spent Output Profit Ratio. < 1 = holders spending at a loss (capitulation); bouncing off 1.0 = support confirmation.' },
        { name: 'LTH / STH MVRV Cross', description: 'LTH-MVRV crossing above STH-MVRV signals cycle bottom recovery; the reverse marks distribution by long-term holders.' },
        { name: 'Reserve Risk',       description: 'Confidence of long-term holders vs current price. Low = strong HODLer conviction; high = HODLers distributing into strength.' },
    ].map(cfg => renderLockedCard(cfg));

    container.appendChild(renderSection('Price Structure', priceCards));
    container.appendChild(renderSection('Sentiment & Positioning', sentCards));
    container.appendChild(renderSection('Mining & Liquidity', miningCards));
    container.appendChild(renderSection('On-Chain — Requires Glassnode', lockedCards));
}

// ── Load and render ───────────────────────────────────────────────────────────

async function loadAndRender() {
    const loadingEl = document.getElementById('btc-loading');
    const errorEl   = document.getElementById('btc-error');
    const contentEl = document.getElementById('btc-content');

    try {
        const resp = await fetch('assets/btc_signals.json');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        btcData = await resp.json();

        if (loadingEl) loadingEl.hidden = true;

        const updatedEl = document.getElementById('btc-last-updated');
        if (updatedEl && btcData.date) {
            updatedEl.textContent = 'Data: ' + btcData.date;
        }

        const priceEl = document.getElementById('btc-current-price');
        if (priceEl && btcData.price != null) {
            priceEl.textContent = fmtPrice(btcData.price);
        }

        renderConfluenceBanner(btcData);
        buildAllSections(btcData);

        if (contentEl) contentEl.hidden = false;
    } catch (err) {
        if (loadingEl) loadingEl.hidden = true;
        if (errorEl) {
            errorEl.textContent = 'Failed to load BTC signals data. Please run the pipeline to generate btc_signals.json.';
            errorEl.hidden = false;
        }
        console.error('BTC signals load error:', err);
    }
}

document.addEventListener('DOMContentLoaded', loadAndRender);
