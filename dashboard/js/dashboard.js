// Dashboard JavaScript
let dashboardData = null;
let chartHistoryData = null;
let chartHistoryPromise = null;   // single in-flight fetch; all callers await this
const charts = {};

// Asset categorisation (mirrors trading_utils/config.py ASSETS list)
const ASSET_CATEGORIES = {
    crypto: new Set(['BTC','ETH','SOL','XLM','REZ','RSR','NEAR','RENDER','ONDO','ACH','BNB','XRP','ADA','NIGHT','VTHO','LINK','NEO','GAS','DRIFT','SEI','PEAQ','AEVO','EIGEN','W','WOO','JASMY','D2X','SCP']),
    nasdaq: new Set(['MSTR','XXI','RIOT','MARA','IREN','BMNR','HUT','WULF','HIVE','CLSK','SLNH']),
    lse:    new Set(['MSTY','YMST','MARY','RIOY','IREY','BMNY']),
    macro:  new Set(['SPX','NDX','RTY','DJI','DAX','CAC','FTSE','NIK','HSI','ASX','GOLD','SILVER','OIL','NATGAS','COPPER','WHEAT','CORN','DXY','EURUSD','GBPUSD','AUDUSD','NZDUSD','USDCAD','USDCHF','USDJPY']),
};

// Macro subcategory groupings for the Macro tab layout
const MACRO_SUBCATEGORIES = {
    'US Indices':   ['SPX', 'NDX', 'RTY', 'DJI'],
    'EU Indices':   ['DAX', 'CAC', 'FTSE'],
    'APAC Indices': ['NIK', 'HSI', 'ASX'],
    'Commodities':  ['GOLD', 'SILVER', 'OIL', 'NATGAS', 'COPPER', 'WHEAT', 'CORN'],
    'Forex':        ['DXY', 'EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY'],
};

// Forex pairs shown with 4 decimal places (no $ prefix); DXY shown plain without $
const MACRO_FOREX_SYMBOLS = new Set(['EURUSD','GBPUSD','AUDUSD','NZDUSD','USDCAD','USDCHF','USDJPY','DXY']);

// LSE ETFs are quoted in GBp (pence) by Yahoo Finance
const LSE_ASSETS = ASSET_CATEGORIES.lse;

// Regime display order for the summary strip
const REGIME_ORDER = ['Capitulation','Accumulation','Trend','Distribution','Mania','Unknown'];

// Portfolio filter state
const portfolioFilter = { category: '', regime: null, sort: 'name', timeframe: '1d', search: '' };

// ─── Formatting helpers ───────────────────────────────────────────────────────

function formatPrice(asset, price) {
    if (price == null) return 'N/A';
    if (LSE_ASSETS.has(asset)) {
        return `${parseFloat(price.toFixed(2)).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}p`;
    }
    return `$${price.toLocaleString()}`;
}

function rsiClass(rsi) {
    if (rsi == null) return '';
    if (rsi < 30) return 'positive';
    if (rsi > 70) return 'negative';
    return '';
}

function signClass(value) {
    if (value == null) return '';
    return value >= 0 ? 'positive' : 'negative';
}

function regimeClass(regime) {
    const VALID = new Set(['capitulation','accumulation','trend','distribution','mania','unknown']);
    const norm = (regime || 'unknown').toLowerCase();
    return `regime-${VALID.has(norm) ? norm : 'unknown'}`;
}

function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Returns { label, cssClass } signal strength for ranking/panel badges.
// Uses the MORE SEVERE of two independent signals:
//   1. Percentile rank (how rare is this reading historically for this asset)
//   2. Absolute ATR Distance threshold (how far is price stretched right now)
// direction: 'oversold' | 'extended'
function getSignalStrength(atrPercentile, direction, sampleSize, atrDistance) {
    // Severity tiers: 0=mild, 1=regular, 2=deep/high, 3=extreme

    // Percentile-based tier (requires sufficient history)
    let pctTier = 0;
    if (sampleSize != null && sampleSize >= 30 && atrPercentile != null) {
        if (direction === 'oversold') {
            if (atrPercentile <= 5)       pctTier = 3;
            else if (atrPercentile <= 15) pctTier = 2;
            else if (atrPercentile <= 30) pctTier = 1;
        } else {
            if (atrPercentile >= 95)      pctTier = 3;
            else if (atrPercentile >= 85) pctTier = 2;
            else if (atrPercentile >= 70) pctTier = 1;
        }
    }

    // Absolute ATR Distance tier (always applicable, no history required)
    let atrTier = 0;
    if (atrDistance != null) {
        if (direction === 'oversold') {
            if (atrDistance < -4)      atrTier = 3;
            else if (atrDistance < -3) atrTier = 2;
            else if (atrDistance < -2) atrTier = 1;
        } else {
            if (atrDistance > 4)      atrTier = 3;
            else if (atrDistance > 3) atrTier = 2;
            else if (atrDistance > 2) atrTier = 1;
        }
    }

    // Take the more severe signal
    const tier = Math.max(pctTier, atrTier);

    if (direction === 'oversold') {
        if (tier === 3) return { label: 'Extreme Oversold', cssClass: 'signal-extreme-oversold' };
        if (tier === 2) return { label: 'Deep Oversold',    cssClass: 'signal-deep-oversold' };
        if (tier === 1) return { label: 'Oversold',         cssClass: 'signal-oversold' };
        return { label: 'Mild Dip', cssClass: 'signal-oversold' };
    } else {
        if (tier === 3) return { label: 'Extreme Extended', cssClass: 'signal-extreme-extended' };
        if (tier === 2) return { label: 'High Extended',    cssClass: 'signal-high-extended' };
        if (tier === 1) return { label: 'Extended',         cssClass: 'signal-extended' };
        return { label: 'Mild Extension', cssClass: 'signal-extended' };
    }
}

// Returns CSS class for ATR Distance semantic color on cards/summaries.
function getAtrColorClass(atrDistance) {
    if (atrDistance == null) return '';
    if (atrDistance < -4 || atrDistance > 4) return 'atr-extreme';
    if (atrDistance < -2) return 'atr-oversold';
    if (atrDistance > 2)  return 'atr-extended';
    return '';
}

function mcapRankClass(rank) {
    if (!rank) return 'mcap-small';
    if (rank <= 10)  return 'mcap-top10';
    if (rank <= 50)  return 'mcap-top50';
    if (rank <= 200) return 'mcap-top200';
    return 'mcap-small';
}

function formatMarketCap(value) {
    if (value == null) return 'N/A';
    if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
    if (value >= 1e9)  return `$${(value / 1e9).toFixed(1)}B`;
    if (value >= 1e6)  return `$${(value / 1e6).toFixed(0)}M`;
    return `$${Math.round(value).toLocaleString()}`;
}

// Returns { label, cls } for a VP position string, or null if position is unknown.
function vpPositionLabel(pos) {
    const map = {
        above_vah:    { label: '↑ Above VAH', cls: 'vp-above-vah' },
        below_val:    { label: '↓ Below VAL', cls: 'vp-below-val' },
        at_poc:       { label: '● At POC',    cls: 'vp-at-poc'    },
        in_value_area:{ label: 'In VA',        cls: 'vp-in-va'     },
    };
    return map[pos] ?? null;
}

// Returns badge HTML for VP position, or empty string.
function vpBadgeHtml(pos) {
    const info = vpPositionLabel(pos);
    if (!info) return '';
    return `<span class="vp-badge ${escapeHtml(info.cls)}">${escapeHtml(info.label)}</span>`;
}

function alignBadgeClass(alignment) {
    if (alignment === 'aligned-bullish') return 'align-bullish';
    if (alignment === 'aligned-bearish') return 'align-bearish';
    return 'align-diverging';
}

function alignBadgeLabel(alignment) {
    if (alignment === 'aligned-bullish') return '↑↑';
    if (alignment === 'aligned-bearish') return '↓↓';
    return '↕';
}

function atrTrendIcon(trend) {
    if (trend === 'expanding')   return '↑';
    if (trend === 'compressing') return '↓';
    return '─';
}

function rsBadgeHtml(rs) {
    if (rs == null) return 'N/A';
    const outperforming = rs > 1.0;
    const cls   = outperforming ? 'rs-outperforming' : 'rs-underperforming';
    const label = outperforming ? `↑ ${rs.toFixed(2)}×` : `↓ ${rs.toFixed(2)}×`;
    return `<span class="rs-badge ${cls}">${label}</span>`;
}

// Returns { label, cssClass } for a macro zone based on ATR Distance.
// Same thresholds as regime classification but neutral display names.
function macroZoneLabel(atrDistance) {
    if (atrDistance == null) return { label: 'Unknown',          cssClass: 'zone-unknown' };
    if (atrDistance < -4)   return { label: 'Extreme Oversold', cssClass: 'zone-extreme-oversold' };
    if (atrDistance < -2)   return { label: 'Oversold',         cssClass: 'zone-oversold' };
    if (atrDistance <= 2)   return { label: 'Neutral',          cssClass: 'zone-neutral' };
    if (atrDistance <= 4)   return { label: 'Extended',         cssClass: 'zone-extended' };
    return                         { label: 'Extreme Extended', cssClass: 'zone-extreme-extended' };
}

// Builds an inline SVG sparkline for the last 14 bars of ATR Distance values.
// Stroke colour matches the ATR Distance semantic colour of the current value.
function makeSparklineSvg(values, currentAtrDistance) {
    if (!values || values.length < 2) return '';
    const slice = values.slice(-14);
    const min = Math.min(...slice);
    const max = Math.max(...slice);
    const range = max - min || 0.01;
    const W = 100, H = 20;
    const toX = i => (i / (slice.length - 1)) * W;
    const toY = v => H - ((v - min) / range) * (H - 2) - 1;
    const pts = slice.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
    let zeroLine = '';
    if (min <= 0 && max >= 0) {
        const zy = toY(0).toFixed(1);
        zeroLine = `<line x1="0" y1="${zy}" x2="${W}" y2="${zy}" stroke="rgba(160,174,192,0.3)" stroke-width="0.8" stroke-dasharray="2,2"/>`;
    }
    let stroke = '#64748b';
    if (currentAtrDistance != null) {
        if (Math.abs(currentAtrDistance) > 4) stroke = '#ef4444';
        else if (currentAtrDistance < -2)     stroke = '#10b981';
        else if (currentAtrDistance > 2)      stroke = '#f97316';
    }
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${zeroLine}<polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}

// Fills .card-sparkline placeholders using chartHistoryData. No-op if data not yet loaded.
function renderPortfolioSparklines() {
    if (!chartHistoryData) return;
    document.querySelectorAll('.card-sparkline[data-asset]').forEach(el => {
        const asset = el.dataset.asset;
        const tf    = el.dataset.tf;
        const history = chartHistoryData[asset]?.[tf];
        if (!history?.length) return;
        const values = history.map(b => b.atr_distance).filter(v => v != null);
        const currentAtr = dashboardData?.assets[asset]?.[tf]?.current?.atr_distance ?? null;
        el.innerHTML = makeSparklineSvg(values, currentAtr);
    });
}

// ─── Starred / Watchlist ─────────────────────────────────────────────────────

const STARRED_KEY = 'starred_assets';
const MAX_STARRED = 10;

function getStarred() {
    try { return JSON.parse(localStorage.getItem(STARRED_KEY) || '[]'); } catch { return []; }
}

function isStarred(asset) { return getStarred().includes(asset); }

function toggleStar(asset) {
    let starred = getStarred();
    if (starred.includes(asset)) {
        starred = starred.filter(a => a !== asset);
    } else if (starred.length < MAX_STARRED) {
        starred.push(asset);
    }
    localStorage.setItem(STARRED_KEY, JSON.stringify(starred));
}

// ─── Data loading ─────────────────────────────────────────────────────────────

async function loadDashboardData() {
    try {
        const response = await fetch('assets/data.json');
        if (!response.ok) throw new Error('Failed to load dashboard data');
        dashboardData = await response.json();
        const lastUpdated = new Date(dashboardData.metadata.last_updated);
        document.getElementById('lastUpdated').textContent =
            `Last updated: ${lastUpdated.toLocaleString()}`;
        const subtitle = document.querySelector('.header-subtitle');
        if (subtitle && dashboardData.metadata.assets_count) {
            subtitle.textContent =
                `ATR Distance · Regime Classification · ${dashboardData.metadata.assets_count} Assets`;
        }
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        document.getElementById('lastUpdated').textContent = 'Error loading data';
    }
}

async function ensureChartHistory() {
    if (chartHistoryData) return;
    if (!chartHistoryPromise) {
        chartHistoryPromise = fetch('assets/chart_history.json')
            .then(r => { if (!r.ok) throw new Error('chart_history.json not found'); return r.json(); })
            .then(data => { chartHistoryData = data; })
            .catch(e => {
                console.warn('Chart history unavailable:', e.message);
                chartHistoryData = null;
                chartHistoryPromise = null; // allow retry on next visit
            });
    }
    await chartHistoryPromise;
}

// ─── Initialisation ───────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    await loadDashboardData();

    if (!dashboardData) {
        const active = document.querySelector('.tab-content.active') || document.querySelector('.main-content');
        if (active) {
            const err = document.createElement('div');
            err.className = 'error';
            err.textContent = 'Error loading dashboard data. Please refresh.';
            active.innerHTML = '';
            active.appendChild(err);
        }
        document.querySelectorAll('.nav-btn').forEach(btn => btn.disabled = true);
        return;
    }

    // Set up Chart.js global defaults once the library has loaded
    if (typeof Chart !== 'undefined') {
        Chart.defaults.color = '#a0aec0';
        Chart.defaults.borderColor = '#374151';
        Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
        if (typeof ChartAnnotation !== 'undefined') {
            Chart.register(ChartAnnotation);
        }
    }

    setupNavigation();
    setupAssetSelectors();
    setupPortfolioFilters();
    renderPortfolio();
    renderRankings();
    renderHistoricalContext();
    renderMacro();
    await ensureChartHistory();
    renderPortfolioSparklines();
    renderDrilldown();
});

// ─── Navigation ───────────────────────────────────────────────────────────────

function navigateTo(tabId, asset) {
    const navButtons  = document.querySelectorAll('.nav-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    navButtons.forEach(btn => {
        const isTarget = btn.dataset.tab === tabId;
        btn.classList.toggle('active', isTarget);
        btn.setAttribute('aria-selected', isTarget ? 'true' : 'false');
    });

    tabContents.forEach(tab => {
        tab.classList.toggle('active', tab.id === tabId);
    });

    // Move focus to the new tab panel
    const panel = document.getElementById(tabId);
    if (panel) panel.focus({ preventScroll: false });

    if (asset) {
        const sel = document.getElementById('drilldown-asset-select');
        if (sel && tabId === 'drilldown-tab') {
            sel.value = asset;
            renderDrilldown();
        }
    }
}

function setupNavigation() {
    document.querySelectorAll('.nav-btn').forEach(button => {
        button.addEventListener('click', async () => {
            const targetTab = button.dataset.tab;
            navigateTo(targetTab);
            if (targetTab === 'drilldown-tab') {
                await ensureChartHistory();
                renderDrilldown();
            } else if (targetTab === 'macro-tab') {
                renderMacro();
            }
        });
    });
}

// ─── Asset selectors ──────────────────────────────────────────────────────────

function setupAssetSelectors() {
    if (!dashboardData) return;
    // Macro assets are on their own tab; exclude from the Extremes/Drilldown selectors
    const assets = Object.keys(dashboardData.assets).filter(a => !ASSET_CATEGORIES.macro.has(a)).sort();

    const historicalSelect = document.getElementById('asset-select');
    assets.forEach(asset => {
        const opt = document.createElement('option');
        opt.value = opt.textContent = asset;
        historicalSelect.appendChild(opt);
    });
    historicalSelect.addEventListener('change', renderHistoricalContext);

    const drilldownSelect = document.getElementById('drilldown-asset-select');
    assets.forEach(asset => {
        const opt = document.createElement('option');
        opt.value = opt.textContent = asset;
        drilldownSelect.appendChild(opt);
    });
    drilldownSelect.addEventListener('change', renderDrilldown);

    document.getElementById('timeframe-select').addEventListener('change', renderDrilldown);
}

// ─── Portfolio filters ────────────────────────────────────────────────────────

function setupPortfolioFilters() {
    // Category chips
    document.getElementById('filter-category').addEventListener('click', e => {
        const chip = e.target.closest('.chip');
        if (!chip) return;
        document.querySelectorAll('#filter-category .chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        portfolioFilter.category = chip.dataset.value;
        portfolioFilter.regime = null; // reset regime filter when changing category
        // clear regime strip active state
        document.querySelectorAll('.regime-strip .asset-regime').forEach(p => p.classList.remove('active-filter'));
        renderPortfolio();
    });

    // Sort select
    document.getElementById('sort-select').addEventListener('change', e => {
        portfolioFilter.sort = e.target.value;
        renderPortfolio();
    });

    // Timeframe toggle
    document.getElementById('filter-portfolio-timeframe').addEventListener('click', e => {
        const chip = e.target.closest('.chip');
        if (!chip) return;
        document.querySelectorAll('#filter-portfolio-timeframe .chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        portfolioFilter.timeframe = chip.dataset.value;
        portfolioFilter.regime = null;
        document.querySelectorAll('.regime-strip .asset-regime').forEach(p => p.classList.remove('active-filter'));
        renderPortfolio();
    });

    // Search input
    const searchInput = document.getElementById('portfolio-search');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            portfolioFilter.search = searchInput.value.trim().toLowerCase();
            renderPortfolio();
        });
    }
}

// ─── Portfolio health bar ─────────────────────────────────────────────────────

function renderPortfolioHealthBar() {
    if (!dashboardData) return;
    const bar = document.getElementById('portfolio-health-bar');
    if (!bar) return;

    let total = 0, oversoldCount = 0, extendedCount = 0, neutralCount = 0;
    const regimeCounts = {};

    Object.entries(dashboardData.assets).forEach(([asset, ad]) => {
        if (ASSET_CATEGORIES.macro.has(asset)) return;
        const c = ad[portfolioFilter.timeframe]?.current;
        if (!c) return;
        total++;
        const atr = c.atr_distance ?? 0;
        const r = c.regime || 'Unknown';
        regimeCounts[r] = (regimeCounts[r] || 0) + 1;
        if (atr < -2)      oversoldCount++;
        else if (atr > 2)  extendedCount++;
        else               neutralCount++;
    });

    if (total === 0) { bar.innerHTML = ''; return; }

    const oversoldPct = Math.round(100 * oversoldCount / total);
    const extendedPct = Math.round(100 * extendedCount / total);
    const neutralPct  = Math.round(100 * neutralCount  / total);

    const notablePriority = ['Capitulation', 'Mania', 'Accumulation', 'Distribution', 'Trend', 'Unknown'];
    const notableRegime   = notablePriority.find(r => regimeCounts[r] > 0) || 'Trend';
    const notableCount    = regimeCounts[notableRegime] || 0;

    let sentiment;
    if (regimeCounts['Capitulation'] > 0)                                                     sentiment = 'Extreme Fear';
    else if (regimeCounts['Mania'] > 0)                                                       sentiment = 'Extreme Greed';
    else if ((regimeCounts['Accumulation'] || 0) > (regimeCounts['Distribution'] || 0) * 1.5) sentiment = 'Fear Dominates';
    else if ((regimeCounts['Distribution'] || 0) > (regimeCounts['Accumulation'] || 0) * 1.5) sentiment = 'Greed Dominates';
    else if ((regimeCounts['Accumulation'] || 0) > 0 || (regimeCounts['Distribution'] || 0) > 0) sentiment = 'Mixed';
    else                                                                                       sentiment = 'Neutral';

    bar.innerHTML = `
        <div class="health-stat">
            <span class="health-dot health-dot--oversold" aria-hidden="true"></span>
            <span>Oversold: <strong>${oversoldPct}%</strong></span>
            <span class="sr-only">(${oversoldCount} of ${total} assets)</span>
        </div>
        <div class="health-divider" aria-hidden="true"></div>
        <div class="health-stat">
            <span class="health-dot health-dot--neutral" aria-hidden="true"></span>
            <span>Neutral: <strong>${neutralPct}%</strong></span>
        </div>
        <div class="health-divider" aria-hidden="true"></div>
        <div class="health-stat">
            <span class="health-dot health-dot--extended" aria-hidden="true"></span>
            <span>Extended: <strong>${extendedPct}%</strong></span>
        </div>
        <div class="health-divider" aria-hidden="true"></div>
        <div class="health-stat">
            <span>Notable: <strong>${escapeHtml(notableRegime)}</strong> (${notableCount})</span>
        </div>
        <div class="health-sentiment" aria-label="Market sentiment: ${escapeHtml(sentiment)}">${escapeHtml(sentiment)}</div>
    `;
}

// ─── Opportunity / Risk panels ────────────────────────────────────────────────

function renderOpportunityPanels() {
    if (!dashboardData) return;
    const oppItems  = document.getElementById('opportunity-items');
    const riskItems = document.getElementById('risk-items');
    if (!oppItems || !riskItems) return;

    const ranked = [];
    Object.entries(dashboardData.assets).forEach(([symbol, ad]) => {
        if (ASSET_CATEGORIES.macro.has(symbol)) return;
        const c = ad[portfolioFilter.timeframe]?.current;
        const n = ad[portfolioFilter.timeframe]?.historical?.sample_size ?? 0;
        if (c?.atr_distance != null) {
            ranked.push({ symbol, atrDistance: c.atr_distance, atrPercentile: c.atr_percentile, sampleSize: n });
        }
    });
    ranked.sort((a, b) => a.atrDistance - b.atrDistance);

    const top3Oversold = ranked.filter(r => r.atrDistance < 0).slice(0, 3);
    const top3Extended = ranked.filter(r => r.atrDistance > 0).slice(-3).reverse();

    const buildItem = (item, direction) => {
        const { symbol, atrDistance, atrPercentile, sampleSize } = item;
        const sig    = getSignalStrength(atrPercentile, direction, sampleSize, atrDistance);
        const extreme = (direction === 'oversold' && atrDistance < -4) || (direction === 'extended' && atrDistance > 4);
        const atrCls = extreme ? 'panel-item-atr--extreme'
            : direction === 'oversold' ? 'panel-item-atr--oversold'
            : 'panel-item-atr--extended';
        const div = document.createElement('div');
        div.className = 'panel-item';
        div.dataset.asset = symbol;
        div.setAttribute('role', 'button');
        div.setAttribute('tabindex', '0');
        div.setAttribute('aria-label', `${symbol}: ATR Distance ${atrDistance.toFixed(2)}, ${sig.label}. Open drilldown.`);
        div.innerHTML = `
            <span class="panel-item-symbol">${escapeHtml(symbol)}</span>
            <span class="panel-item-atr ${atrCls}" aria-hidden="true">${atrDistance.toFixed(2)}</span>
            <span class="panel-item-signal ${sig.cssClass}" aria-hidden="true">${escapeHtml(sig.label)}</span>
        `;
        return div;
    };

    oppItems.innerHTML  = '';
    riskItems.innerHTML = '';

    if (top3Oversold.length === 0) {
        oppItems.innerHTML = '<div class="ranking-empty">No assets currently oversold</div>';
    } else {
        top3Oversold.forEach(item => oppItems.appendChild(buildItem(item, 'oversold')));
    }

    if (top3Extended.length === 0) {
        riskItems.innerHTML = '<div class="ranking-empty">No assets currently extended</div>';
    } else {
        top3Extended.forEach(item => riskItems.appendChild(buildItem(item, 'extended')));
    }

    const handlePanelNav = container => {
        if (container.dataset.panelNavAttached) return;
        container.addEventListener('click', e => {
            const item = e.target.closest('.panel-item[data-asset]');
            if (item) navigateTo('drilldown-tab', item.dataset.asset);
        });
        container.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') {
                const item = e.target.closest('.panel-item[data-asset]');
                if (item) { e.preventDefault(); navigateTo('drilldown-tab', item.dataset.asset); }
            }
        });
        container.dataset.panelNavAttached = 'true';
    };
    handlePanelNav(oppItems);
    handlePanelNav(riskItems);
}

// ─── Portfolio rendering ──────────────────────────────────────────────────────

function renderTransitionsSection() {
    const section = document.getElementById('transitions-section');
    const list    = document.getElementById('transitions-list');
    if (!section || !list || !dashboardData) return;

    const tf = portfolioFilter.timeframe;
    const transitions = [];
    Object.entries(dashboardData.assets).forEach(([asset, ad]) => {
        if (ASSET_CATEGORIES.macro.has(asset)) return;
        const c = ad[tf]?.current;
        if (c?.regime_changed && c.prev_regime) {
            transitions.push({ asset, from: c.prev_regime, to: c.regime });
        }
    });

    if (transitions.length === 0) {
        section.hidden = true;
        return;
    }

    section.hidden = false;
    list.innerHTML = '';
    transitions.forEach(({ asset, from, to }) => {
        const chip = document.createElement('span');
        chip.className = 'transition-chip';
        chip.dataset.asset = asset;
        chip.innerHTML = `
            <strong>${escapeHtml(asset)}</strong>
            <span class="transition-arrow">${escapeHtml(from)} → ${escapeHtml(to)}</span>
        `;
        chip.addEventListener('click', () => navigateTo('drilldown-tab', asset));
        list.appendChild(chip);
    });
}

function renderBreadthChart() {
    const section = document.getElementById('breadth-section');
    if (!section) return;

    fetch('assets/breadth.json')
        .then(r => { if (!r.ok) throw new Error('breadth.json not found'); return r.json(); })
        .then(data => {
            if (!data?.dates?.length) { section.hidden = true; return; }
            section.hidden = false;
            const id = 'breadth-chart';
            if (charts[id]) { charts[id].destroy(); delete charts[id]; }
            const canvas = document.getElementById(id);
            if (!canvas) return;
            const regimes = ['capitulation','accumulation','trend','distribution','mania'];
            const colors  = [
                'rgba(153,27,27,0.75)',
                'rgba(16,185,129,0.65)',
                'rgba(59,130,246,0.50)',
                'rgba(249,115,22,0.65)',
                'rgba(239,68,68,0.75)',
            ];
            const labels = ['Capitulation','Accumulation','Trend','Distribution','Mania'];
            charts[id] = new Chart(canvas, {
                type: 'bar',
                data: {
                    labels: data.dates,
                    datasets: regimes.map((r, i) => ({
                        label: labels[i],
                        data: data[r] || [],
                        backgroundColor: colors[i],
                        borderWidth: 0,
                        stack: 'breadth',
                    }))
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom', labels: { boxWidth: 10, padding: 10, font: { size: 10 } } },
                        tooltip: { mode: 'index', intersect: false }
                    },
                    scales: {
                        x: { stacked: true, ticks: { maxTicksLimit: 10, maxRotation: 0, font: { size: 9 } }, grid: { display: false } },
                        y: { stacked: true, grid: { color: 'rgba(55,65,81,0.5)' }, ticks: { font: { size: 9 } } }
                    }
                }
            });
            canvas.style.height = '180px';
        })
        .catch(() => { if (section) section.hidden = true; });
}

function renderPortfolio() {
    if (!dashboardData) return;

    renderPortfolioHealthBar();
    renderOpportunityPanels();
    renderTransitionsSection();
    renderBreadthChart();

    const container = document.getElementById('portfolio-cards');
    container.innerHTML = '';

    // Macro assets live on their own tab — exclude from portfolio view entirely
    let assets = Object.keys(dashboardData.assets).filter(a => !ASSET_CATEGORIES.macro.has(a)).sort();

    // ── Regime strip ──────────────────────────────────────────────────────────
    const regimeCounts = {};
    assets.forEach(a => {
        const current = dashboardData.assets[a][portfolioFilter.timeframe]?.current;
        if (!current) return; // no current snapshot — don't inflate Unknown count
        const r = current.regime || 'Unknown';
        regimeCounts[r] = (regimeCounts[r] || 0) + 1;
    });

    const strip = document.getElementById('regime-strip');
    strip.innerHTML = '';
    REGIME_ORDER.filter(r => regimeCounts[r]).forEach(regime => {
        const pill = document.createElement('span');
        pill.className = `asset-regime ${regimeClass(regime)}`;
        if (portfolioFilter.regime === regime) pill.classList.add('active-filter');
        pill.textContent = `${regime} (${regimeCounts[regime]})`;
        pill.addEventListener('click', () => {
            if (portfolioFilter.regime === regime) {
                portfolioFilter.regime = null;
                pill.classList.remove('active-filter');
            } else {
                portfolioFilter.regime = regime;
                document.querySelectorAll('.regime-strip .asset-regime').forEach(p => p.classList.remove('active-filter'));
                pill.classList.add('active-filter');
            }
            renderPortfolio();
        });
        strip.appendChild(pill);
    });

    // ── Apply category + regime filters ──────────────────────────────────────
    if (portfolioFilter.category) {
        const allowed = ASSET_CATEGORIES[portfolioFilter.category];
        assets = assets.filter(a => allowed.has(a));
    }
    if (portfolioFilter.regime) {
        assets = assets.filter(a => {
            const r = dashboardData.assets[a][portfolioFilter.timeframe]?.current?.regime || 'Unknown';
            return r === portfolioFilter.regime;
        });
    }

    // ── Search filter ─────────────────────────────────────────────────────────
    if (portfolioFilter.search) {
        assets = assets.filter(a => a.toLowerCase().includes(portfolioFilter.search));
    }

    // ── Sort — getRaw returns null for missing values so sentinels apply correctly ──
    const getRaw = (a, field) => dashboardData.assets[a][portfolioFilter.timeframe]?.current?.[field] ?? null;
    if (portfolioFilter.sort === 'atr_asc') {
        assets.sort((a, b) => (getRaw(a, 'atr_distance') ?? Infinity) - (getRaw(b, 'atr_distance') ?? Infinity));
    } else if (portfolioFilter.sort === 'atr_desc') {
        assets.sort((a, b) => (getRaw(b, 'atr_distance') ?? -Infinity) - (getRaw(a, 'atr_distance') ?? -Infinity));
    } else if (portfolioFilter.sort === 'rsi_asc') {
        assets.sort((a, b) => (getRaw(a, 'rsi') ?? Infinity) - (getRaw(b, 'rsi') ?? Infinity));
    } else if (portfolioFilter.sort === 'mcap_asc') {
        assets.sort((a, b) => {
            const ra = getRaw(a, 'market_cap_rank');
            const rb = getRaw(b, 'market_cap_rank');
            if (ra == null && rb == null) return 0;
            if (ra == null) return 1;
            if (rb == null) return -1;
            return ra - rb;
        });
    }
    // default: name A-Z (already sorted)

    // ── Float starred assets to the top ───────────────────────────────────────
    const starred = getStarred();
    if (starred.length > 0) {
        const starredSet = new Set(starred);
        assets.sort((a, b) => {
            const aS = starredSet.has(a) ? 0 : 1;
            const bS = starredSet.has(b) ? 0 : 1;
            return aS - bS;
        });
    }

    if (assets.length === 0) {
        container.innerHTML = '<div class="loading">No assets match the current filter.</div>';
        return;
    }

    // ── Render cards ──────────────────────────────────────────────────────────
    const activeTf  = portfolioFilter.timeframe;
    const crossTf   = activeTf === '1d' ? '1w' : '1d';
    const crossLabel = crossTf === '1w' ? 'W' : 'D';

    assets.forEach(asset => {
        const assetData  = dashboardData.assets[asset];
        const primary    = assetData[activeTf]?.current;
        const secondary  = assetData[crossTf]?.current;

        if (!primary) return;

        const atrDistP = primary.atr_distance;
        const atrDistX = secondary?.atr_distance;
        const rsi      = primary.rsi;
        const rsiZ     = primary.rsi_z_score;
        const chg      = primary.price_change_pct;
        const regime   = primary.regime || 'Unknown';

        const latestDate  = dashboardData.metadata?.date_range?.end;
        const staleThreshold = activeTf === '1w' ? 10 : 3;
        const isStale = latestDate && primary.date
            ? Math.floor((new Date(latestDate) - new Date(primary.date)) / 86400000) >= staleThreshold
            : false;

        const sampleSize  = assetData[activeTf]?.historical?.sample_size ?? 0;
        const atrPct      = primary.atr_percentile;
        const atrColorCls = getAtrColorClass(atrDistP);
        const badgeHtml   = (sampleSize > 30 && atrPct != null)
            ? `<span class="metric-percentile-badge" aria-label="${Math.round(atrPct)}th percentile">P${Math.round(atrPct)}%</span>`
            : '';

        const ea = escapeHtml(asset);
        const er = escapeHtml(regime);
        const card = document.createElement('div');
        card.className = 'asset-card';
        card.dataset.asset = asset;
        card.innerHTML = `
            <div class="asset-card-header">
                <span class="asset-name">${ea}</span>
                ${primary.regime_changed ? '<span class="transition-pulse" title="Regime changed"></span>' : ''}
                ${primary.alignment ? `<span class="align-badge ${alignBadgeClass(primary.alignment)}" title="TF Alignment">${alignBadgeLabel(primary.alignment)}</span>` : ''}
                <span class="asset-regime ${regimeClass(regime)}">${er}</span>
                <button class="star-btn${isStarred(asset) ? ' starred' : ''}" data-star="${ea}" title="${isStarred(asset) ? 'Unstar' : 'Star'} ${ea}" aria-label="${isStarred(asset) ? 'Remove from watchlist' : 'Add to watchlist'}" onclick="event.stopPropagation();toggleStar('${ea}');renderPortfolio();">&#9733;</button>
            </div>
            <div class="asset-metrics">
                <div class="metric">
                    <span class="metric-label">ATR Dist.</span>
                    <span class="metric-value ${atrColorCls || signClass(atrDistP)}">
                        ${atrDistP?.toFixed(2) ?? 'N/A'}${badgeHtml}
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">${crossLabel}-ATR Dist.</span>
                    <span class="metric-value ${signClass(atrDistX)}">
                        ${atrDistX?.toFixed(2) ?? 'N/A'}
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">RSI</span>
                    <span class="metric-value ${rsiClass(rsi)}">${rsi?.toFixed(1) ?? 'N/A'}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">RSI Z-Score</span>
                    <span class="metric-value ${signClass(rsiZ)}">${rsiZ?.toFixed(2) ?? 'N/A'}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Price</span>
                    <span class="metric-value">${formatPrice(asset, primary.price)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Chg%</span>
                    <span class="metric-value ${signClass(chg)}">${chg != null ? (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%' : 'N/A'}</span>
                </div>
                ${primary.vp_position ? `
                <div class="metric">
                    <span class="metric-label">VP</span>
                    <span class="metric-value">${vpBadgeHtml(primary.vp_position)}</span>
                </div>` : ''}
                ${primary.market_cap_rank != null ? `
                <div class="metric">
                    <span class="metric-label">MCap</span>
                    <span class="metric-value"><span class="mcap-badge ${mcapRankClass(primary.market_cap_rank)}">#${primary.market_cap_rank}</span></span>
                </div>` : ''}
                ${primary.atr_trend ? `
                <div class="metric">
                    <span class="metric-label">ATR</span>
                    <span class="metric-value"><span class="atr-trend-icon atr-trend-${primary.atr_trend}">${atrTrendIcon(primary.atr_trend)}</span> ${primary.atr_trend}</span>
                </div>` : ''}
                ${primary.rs_vs_btc != null && ASSET_CATEGORIES.crypto.has(asset) ? `
                <div class="metric">
                    <span class="metric-label">RS/BTC</span>
                    <span class="metric-value">${rsBadgeHtml(primary.rs_vs_btc)}</span>
                </div>` : ''}
            </div>
            <div class="card-sparkline" data-asset="${asset}" data-tf="${activeTf}"></div>
            <div class="asset-card-footer">
                <span class="asset-date${isStale ? ' stale' : ''}">
                    ${isStale ? '&#x26A0; ' : ''}as of ${escapeHtml(primary.date ?? '—')}
                </span>
            </div>
        `;
        container.appendChild(card);
    });

    renderPortfolioSparklines();

    // Delegated click → navigate to Drilldown
    container.onclick = e => {
        const card = e.target.closest('.asset-card[data-asset]');
        if (card) navigateTo('drilldown-tab', card.dataset.asset);
    };
}

// ─── Rankings ─────────────────────────────────────────────────────────────────

function renderRankings() {
    if (!dashboardData) return;

    const oversoldContainer = document.getElementById('oversold-list');
    const extendedContainer = document.getElementById('extended-list');
    oversoldContainer.innerHTML = '';
    extendedContainer.innerHTML = '';

    const rankings = [];
    Object.entries(dashboardData.assets).forEach(([asset, assetData]) => {
        if (ASSET_CATEGORIES.macro.has(asset)) return;
        const d = assetData['1d']?.current;
        if (d?.atr_distance != null) {
            rankings.push({
                asset,
                atrDistance:   d.atr_distance,
                regime:        d.regime || 'Unknown',
                atrPercentile: d.atr_percentile ?? null,
                sampleSize:    assetData['1d']?.historical?.sample_size ?? 0
            });
        }
    });
    rankings.sort((a, b) => a.atrDistance - b.atrDistance);

    const oversold = rankings.slice(0, 10).filter(r => r.atrDistance < 0);
    const extended = rankings.slice(-10).reverse().filter(r => r.atrDistance > 0);

    const renderItem = (container, { asset, atrDistance, regime, atrPercentile, sampleSize }, direction) => {
        const sig      = getSignalStrength(atrPercentile, direction, sampleSize, atrDistance);
        const atrCls   = direction === 'oversold' ? 'oversold' : 'extended';
        const pctLabel = (sampleSize > 30 && atrPercentile != null)
            ? `P${Math.round(atrPercentile)}%`
            : '';
        const item = document.createElement('div');
        item.className = 'ranking-item';
        item.dataset.asset = asset;
        item.innerHTML = `
            <span class="ranking-asset">${escapeHtml(asset)}</span>
            <span class="asset-regime ${regimeClass(regime)}">${escapeHtml(regime)}</span>
            ${pctLabel ? `<span class="ranking-percentile" aria-label="${Math.round(atrPercentile)}th percentile">${pctLabel}</span>` : ''}
            <span class="ranking-signal ${sig.cssClass}" aria-label="Signal: ${escapeHtml(sig.label)}">${escapeHtml(sig.label)}</span>
            <span class="ranking-value ${atrCls}">${atrDistance.toFixed(2)}</span>
        `;
        container.appendChild(item);
    };

    oversold.forEach(r => renderItem(oversoldContainer, r, 'oversold'));
    if (oversold.length === 0) {
        oversoldContainer.innerHTML = '<div class="ranking-empty">No assets currently oversold</div>';
    }

    extended.forEach(r => renderItem(extendedContainer, r, 'extended'));
    if (extended.length === 0) {
        extendedContainer.innerHTML = '<div class="ranking-empty">No assets currently extended</div>';
    }

    // Delegated click → Drilldown
    const handleRankingClick = container => {
        container.addEventListener('click', e => {
            const item = e.target.closest('.ranking-item[data-asset]');
            if (item) navigateTo('drilldown-tab', item.dataset.asset);
        });
    };
    handleRankingClick(oversoldContainer);
    handleRankingClick(extendedContainer);
}

// ─── Historical Context ───────────────────────────────────────────────────────

// Returns { frequencyText, actionText } or null if insufficient data.
function buildGaugeInterpretation(current, historical) {
    const pct = current?.atr_percentile;
    const n   = historical?.sample_size;
    if (pct == null || n == null || n < 30) return null;

    const approxCount = Math.round(pct / 100 * n);

    let frequencyText;
    if (pct <= 5) {
        frequencyText = `In ${n.toLocaleString()} bars of history, ATR Distance has been this low or lower only ${approxCount} times (${pct.toFixed(1)}%) — a genuinely rare oversold extreme.`;
    } else if (pct <= 15) {
        frequencyText = `ATR Distance has been this low or lower ${approxCount} times out of ${n.toLocaleString()} bars (${pct.toFixed(1)}%) — a deep oversold reading.`;
    } else if (pct <= 30) {
        frequencyText = `ATR Distance is in the lower ${pct.toFixed(0)}th percentile — below-average but not at an extreme (${approxCount} of ${n.toLocaleString()} bars).`;
    } else if (pct >= 95) {
        const above = Math.round((100 - pct) / 100 * n);
        frequencyText = `ATR Distance has been this high or higher only ${above} times out of ${n.toLocaleString()} bars (${(100 - pct).toFixed(1)}%) — a rare extended extreme.`;
    } else if (pct >= 85) {
        const above = Math.round((100 - pct) / 100 * n);
        frequencyText = `ATR Distance is in the top ${(100 - pct).toFixed(0)}% historically — highly extended (above this level ${above} of ${n.toLocaleString()} bars).`;
    } else if (pct >= 70) {
        frequencyText = `ATR Distance is above the 70th percentile — above-average extension relative to historical norms.`;
    } else {
        frequencyText = `ATR Distance is at the ${pct.toFixed(0)}th percentile — within its normal historical range for this asset.`;
    }

    let actionText = null;
    if (pct <= 10) {
        actionText = 'Mean-reversion setups at this level have historically offered the highest probability of recovery.';
    } else if (pct <= 25) {
        actionText = 'Below-average ATR Distance — worth monitoring for further oversold development.';
    } else if (pct >= 90) {
        actionText = 'Extension at this level has historically preceded consolidation or pullback.';
    } else if (pct >= 75) {
        actionText = 'Elevated extension — maintain caution on new long entries.';
    }

    return { frequencyText, actionText };
}

function renderHistoricalContext() {
    if (!dashboardData) return;

    const selectedAsset = document.getElementById('asset-select').value;
    const container     = document.getElementById('historical-content');
    const assetData     = dashboardData.assets[selectedAsset];

    if (!assetData) return;

    container.innerHTML = '';
    const dual = document.createElement('div');
    dual.className = 'historical-dual';

    ['1d', '1w'].forEach(tf => {
        const pane = document.createElement('div');
        pane.className = 'historical-pane';

        const label = document.createElement('h3');
        label.className = 'pane-label';
        label.textContent = tf === '1d' ? 'Daily (1d)' : 'Weekly (1w)';
        pane.appendChild(label);

        const tfData    = assetData[tf];
        const historical = tfData?.historical;
        const current    = tfData?.current;

        if (!historical || !current || historical.sample_size === 0) {
            const msg = document.createElement('div');
            msg.className = 'insufficient-history';
            msg.textContent = tf === '1w'
                ? 'Insufficient weekly history for this asset.'
                : 'No data available.';
            pane.appendChild(msg);
            dual.appendChild(pane);
            return;
        }

        // ── Percentile gauge ──────────────────────────────────────────────────
        const atrMin  = historical.atr_min;
        const atrMax  = historical.atr_max;
        const pct     = current.atr_percentile ?? 50;

        // Percentile-based positioning: maps ATR Distance values → gauge %
        // using piecewise linear interpolation between known breakpoints.
        // This prevents extreme outliers from compressing the visible range —
        // zone widths now reflect how frequently the asset spends in each regime.
        const knownPts = [
            { pct: 0,   val: atrMin },
            { pct: 25,  val: historical.atr_percentile_25 },
            { pct: 50,  val: historical.atr_percentile_50 },
            { pct: 75,  val: historical.atr_percentile_75 },
            { pct: 90,  val: historical.atr_percentile_90 },
            { pct: 100, val: atrMax }
        ].filter(pt => pt.val != null);

        const toPos = val => {
            if (knownPts.length < 2) {
                // fallback to linear if breakpoints are missing
                const r = atrMax - atrMin || 1;
                return Math.max(0, Math.min(100, ((val - atrMin) / r) * 100));
            }
            if (val <= knownPts[0].val) return 0;
            if (val >= knownPts[knownPts.length - 1].val) return 100;
            for (let i = 0; i < knownPts.length - 1; i++) {
                const lo = knownPts[i], hi = knownPts[i + 1];
                if (val >= lo.val && val <= hi.val) {
                    const t = (val - lo.val) / ((hi.val - lo.val) || 1);
                    return lo.pct + t * (hi.pct - lo.pct);
                }
            }
            return 50;
        };

        // Regime zone positions (thresholds: -4, -2, 2, 4)
        const zones = [
            { name: 'capitulation', from: -Infinity, to: -4 },
            { name: 'accumulation', from: -4,        to: -2 },
            { name: 'trend',        from: -2,         to:  2 },
            { name: 'distribution', from:  2,         to:  4 },
            { name: 'mania',        from:  4,         to:  Infinity }
        ];

        // Gauge track children are appended via DOM API after innerHTML is set,
        // because CSP style-src 'self' (no unsafe-inline) blocks inline style
        // attributes parsed from HTML strings but does NOT restrict
        // element.style.property assignments made via JavaScript.
        const gaugeHtml = `
            <div class="percentile-gauge-section">
                <div class="percentile-gauge-label">ATR Distance — historical position</div>
                <div class="gauge-wrap">
                    <div class="gauge-track"></div>
                </div>
                <div class="gauge-edge-labels">
                    <span>${atrMin.toFixed(2)}</span>
                    <span>${atrMax.toFixed(2)}</span>
                </div>
                <div class="gauge-current-label">
                    Current: ${current.atr_distance?.toFixed(2) ?? 'N/A'} &nbsp;·&nbsp; ${pct.toFixed(0)}th percentile
                </div>
            </div>
        `;

        // ── Metrics grid ──────────────────────────────────────────────────────
        const metricsHtml = `
            <div class="historical-metrics">
                <div class="historical-metric">
                    <div class="historical-metric-label">Regime</div>
                    <div class="historical-metric-value">
                        <span class="asset-regime ${regimeClass(current.regime)}">${current.regime || 'Unknown'}</span>
                    </div>
                </div>
                <div class="historical-metric">
                    <div class="historical-metric-label">RSI</div>
                    <div class="historical-metric-value ${rsiClass(current.rsi)}">${current.rsi?.toFixed(1) ?? 'N/A'}</div>
                    <div class="historical-metric-sub">RSI Z-Score: ${current.rsi_z_score?.toFixed(2) ?? 'N/A'}</div>
                </div>
                <div class="historical-metric">
                    <div class="historical-metric-label">All-time High</div>
                    <div class="historical-metric-value">${historical.atr_max?.toFixed(2) ?? 'N/A'}</div>
                </div>
                <div class="historical-metric">
                    <div class="historical-metric-label">All-time Low</div>
                    <div class="historical-metric-value">${historical.atr_min?.toFixed(2) ?? 'N/A'}</div>
                </div>
                <div class="historical-metric">
                    <div class="historical-metric-label">25th Percentile</div>
                    <div class="historical-metric-value">${historical.atr_percentile_25?.toFixed(2) ?? 'N/A'}</div>
                </div>
                <div class="historical-metric">
                    <div class="historical-metric-label">50th Percentile</div>
                    <div class="historical-metric-value">${historical.atr_percentile_50?.toFixed(2) ?? 'N/A'}</div>
                </div>
                <div class="historical-metric">
                    <div class="historical-metric-label">75th Percentile</div>
                    <div class="historical-metric-value">${historical.atr_percentile_75?.toFixed(2) ?? 'N/A'}</div>
                </div>
                <div class="historical-metric">
                    <div class="historical-metric-label">90th Percentile</div>
                    <div class="historical-metric-value">${historical.atr_percentile_90?.toFixed(2) ?? 'N/A'}</div>
                </div>
                <div class="historical-metric">
                    <div class="historical-metric-label">Sample Size</div>
                    <div class="historical-metric-value">${historical.sample_size?.toLocaleString() ?? 'N/A'}</div>
                    <div class="historical-metric-sub">bars of history</div>
                </div>
                <div class="historical-metric">
                    <div class="historical-metric-label">% Above EMA</div>
                    <div class="historical-metric-value ${signClass(current.pct_above_ema)}">${current.pct_above_ema?.toFixed(1) ?? 'N/A'}%</div>
                </div>
            </div>
        `;

        // Interpretation block
        const interp = buildGaugeInterpretation(current, historical);
        const interpretationHtml = interp ? `
            <div class="gauge-interpretation" role="note">
                <p class="gauge-interpretation-text">${escapeHtml(interp.frequencyText)}</p>
                ${interp.actionText ? `<p class="gauge-interpretation-action">${escapeHtml(interp.actionText)}</p>` : ''}
            </div>
        ` : '';

        pane.innerHTML += gaugeHtml + interpretationHtml + metricsHtml;

        // Populate gauge track via DOM API (not innerHTML) to satisfy CSP style-src.
        const track = pane.querySelector('.gauge-track');
        zones.forEach(z => {
            const left  = toPos(Math.max(z.from, atrMin));
            const right = toPos(Math.min(z.to,   atrMax));
            const width = right - left;
            if (width <= 0) return;
            const el = document.createElement('div');
            el.className = `gauge-zone gauge-zone-${z.name}`;
            el.style.left  = `${left.toFixed(1)}%`;
            el.style.width = `${width.toFixed(1)}%`;
            track.appendChild(el);
        });
        [
            { label: 'P25', val: historical.atr_percentile_25 },
            { label: 'P50', val: historical.atr_percentile_50 },
            { label: 'P75', val: historical.atr_percentile_75 },
            { label: 'P90', val: historical.atr_percentile_90 }
        ].filter(t => t.val != null).forEach(t => {
            const el = document.createElement('div');
            el.className = 'gauge-tick';
            el.style.left = `${toPos(t.val).toFixed(1)}%`;
            el.textContent = t.label;
            track.appendChild(el);
        });
        if (current.atr_distance != null) {
            const el = document.createElement('div');
            el.className = 'gauge-marker';
            el.style.left = `${toPos(current.atr_distance).toFixed(1)}%`;
            track.appendChild(el);
        }

        dual.appendChild(pane);
    });

    container.appendChild(dual);
}

// ─── Drilldown ────────────────────────────────────────────────────────────────

// Returns array of { text, type: 'positive'|'negative'|'neutral' }, capped at 4.
// chartHistory: array of 90 bars [{d, a, r, p, e}] or null.
function generateKeyTakeaways(symbol, timeframeData, assetAllData, chartHistory) {
    const current    = timeframeData?.current;
    const historical = timeframeData?.historical;
    if (!current) return [];

    const takeaways = [];
    const pct    = current.atr_percentile;
    const n      = historical?.sample_size ?? 0;
    const dist   = current.atr_distance;
    const rsi    = current.rsi;
    const rsiZ   = current.rsi_z_score;
    const regime = current.regime || 'Unknown';

    // Insight 1: ATR Distance historical position
    if (n >= 30 && pct != null && dist != null) {
        if (pct <= 5) {
            takeaways.push({ text: `ATR Distance is in the lowest ${pct.toFixed(0)}% of its ${n.toLocaleString()}-bar history — a rare oversold extreme.`, type: 'positive' });
        } else if (pct <= 15) {
            takeaways.push({ text: `ATR Distance at the ${pct.toFixed(0)}th percentile — deep in its historical oversold range.`, type: 'positive' });
        } else if (pct <= 30) {
            takeaways.push({ text: `ATR Distance at the ${pct.toFixed(0)}th percentile — below-average, modest oversold conditions.`, type: 'positive' });
        } else if (pct >= 95) {
            takeaways.push({ text: `ATR Distance is in the top ${(100 - pct).toFixed(0)}% of its ${n.toLocaleString()}-bar history — a rare extended extreme.`, type: 'negative' });
        } else if (pct >= 85) {
            takeaways.push({ text: `ATR Distance at the ${pct.toFixed(0)}th percentile — highly extended historically.`, type: 'negative' });
        } else if (pct >= 70) {
            takeaways.push({ text: `ATR Distance at the ${pct.toFixed(0)}th percentile — above-average extension.`, type: 'negative' });
        } else {
            takeaways.push({ text: `ATR Distance at the ${pct.toFixed(0)}th percentile — within its normal historical range.`, type: 'neutral' });
        }
    } else if (dist != null) {
        if (dist < -4)      takeaways.push({ text: `ATR Distance of ${dist.toFixed(2)} is in Capitulation zone (< −4) — extreme panic level.`, type: 'positive' });
        else if (dist < -2) takeaways.push({ text: `ATR Distance of ${dist.toFixed(2)} is in Accumulation zone (−4 to −2) — oversold.`, type: 'positive' });
        else if (dist > 4)  takeaways.push({ text: `ATR Distance of ${dist.toFixed(2)} is in Mania zone (> +4) — extreme euphoria.`, type: 'negative' });
        else if (dist > 2)  takeaways.push({ text: `ATR Distance of ${dist.toFixed(2)} is in Distribution zone (+2 to +4) — extended.`, type: 'negative' });
        else                takeaways.push({ text: `ATR Distance of ${dist.toFixed(2)} — in Trend zone (fair value range).`, type: 'neutral' });
    }

    // Insight 2: RSI condition
    if (rsi != null) {
        const recentHistory = Array.isArray(chartHistory) ? chartHistory.slice(-7) : [];
        const prevRsiVals   = recentHistory.slice(0, -1).map(r => r.r);
        const wasOversold   = prevRsiVals.some(r => r < 30);
        const wasOverbought = prevRsiVals.some(r => r > 70);

        if (rsi < 30) {
            takeaways.push({ text: `RSI ${rsi.toFixed(1)} is in oversold territory (below 30)${rsiZ != null ? ` — Z-Score ${rsiZ.toFixed(2)}` : ''}.`, type: 'positive' });
        } else if (wasOversold && rsi >= 30) {
            takeaways.push({ text: `RSI recovering from oversold — climbed from below 30 to ${rsi.toFixed(1)} over the last week.`, type: 'positive' });
        } else if (rsi > 70) {
            takeaways.push({ text: `RSI ${rsi.toFixed(1)} is in overbought territory (above 70)${rsiZ != null ? ` — Z-Score ${rsiZ.toFixed(2)}` : ''}.`, type: 'negative' });
        } else if (wasOverbought && rsi <= 70) {
            takeaways.push({ text: `RSI pulling back from overbought — retreated from above 70 to ${rsi.toFixed(1)}.`, type: 'neutral' });
        } else if (rsiZ != null && Math.abs(rsiZ) > 1.5) {
            const dir = rsiZ < 0 ? 'below' : 'above';
            takeaways.push({ text: `RSI Z-Score of ${rsiZ.toFixed(2)} — RSI is ${dir} its 20-period average by more than 1.5 standard deviations.`, type: rsiZ < 0 ? 'positive' : 'negative' });
        }
    }

    // Insight 3: Weekly regime context
    const weekly = assetAllData?.['1w']?.current;
    if (weekly?.regime) {
        const wRegime = weekly.regime;
        const wDist   = weekly.atr_distance;
        if (wRegime === 'Capitulation') {
            takeaways.push({ text: `Weekly regime: Capitulation — higher-timeframe confirms extreme oversold.`, type: 'positive' });
        } else if (wRegime === 'Mania') {
            takeaways.push({ text: `Weekly regime: Mania — higher-timeframe confirms extreme extension.`, type: 'negative' });
        } else if (wRegime === 'Accumulation' && (regime === 'Accumulation' || regime === 'Capitulation')) {
            takeaways.push({ text: `Multi-timeframe alignment: Weekly and Daily both in oversold regimes.`, type: 'positive' });
        } else if (wRegime === 'Distribution' && (regime === 'Distribution' || regime === 'Mania')) {
            takeaways.push({ text: `Multi-timeframe alignment: Weekly and Daily both in extended regimes.`, type: 'negative' });
        } else {
            takeaways.push({ text: `Weekly regime: ${wRegime}${wDist != null ? ` (ATR Distance: ${wDist.toFixed(2)})` : ''}.`, type: 'neutral' });
        }
    }

    // Insight 4: Recent ATR Distance trend direction
    if (Array.isArray(chartHistory) && chartHistory.length >= 5 && dist != null) {
        const last5Atr = chartHistory.slice(-5).map(r => r.a).filter(v => v != null);
        if (last5Atr.length >= 3) {
            const first = last5Atr[0];
            const last  = last5Atr[last5Atr.length - 1];
            const delta = last - first;
            if (dist < 0 && delta > 0.15) {
                takeaways.push({ text: `ATR Distance trending toward zero over the last 5 sessions (${first.toFixed(2)} → ${last.toFixed(2)}) — mean reversion in progress.`, type: 'positive' });
            } else if (dist < 0 && delta < -0.15) {
                takeaways.push({ text: `ATR Distance deepening over the last 5 sessions (${first.toFixed(2)} → ${last.toFixed(2)}) — oversold extending further.`, type: 'negative' });
            } else if (dist > 0 && delta < -0.15) {
                takeaways.push({ text: `ATR Distance retracing over the last 5 sessions (${first.toFixed(2)} → ${last.toFixed(2)}) — extension easing.`, type: 'positive' });
            } else if (dist > 0 && delta > 0.15) {
                takeaways.push({ text: `ATR Distance extending further over the last 5 sessions (${first.toFixed(2)} → ${last.toFixed(2)}) — momentum continues.`, type: 'negative' });
            }
        }
    }

    // Insight 5: Volume Profile position
    const vpPos  = current.vp_position;
    const vpPoc  = current.vp_poc;
    const vpVah  = current.vp_vah;
    const vpVal  = current.vp_val;
    if (vpPos && vpPoc != null) {
        const tfLabel    = timeframeData === assetAllData?.['1w'] ? '52' : '90';
        const pocFmt     = formatPrice(symbol, vpPoc);
        const vahFmt     = formatPrice(symbol, vpVah);
        const valFmt     = formatPrice(symbol, vpVal);
        if (vpPos === 'above_vah')
            takeaways.push({ text: `Price is above the ${tfLabel}-bar Value Area High (VAH: ${vahFmt}) — outside the main volume cluster. Pullback support near VAH.`, type: 'negative' });
        else if (vpPos === 'below_val')
            takeaways.push({ text: `Price is below the ${tfLabel}-bar Value Area Low (VAL: ${valFmt}) — trading below the main volume cluster. Watch for re-entry above VAL.`, type: 'positive' });
        else if (vpPos === 'at_poc')
            takeaways.push({ text: `Price near the ${tfLabel}-bar Point of Control (${pocFmt}) — highest-volume level, key support/resistance zone.`, type: 'neutral' });
        else
            takeaways.push({ text: `Price in the ${tfLabel}-bar Value Area (${valFmt}–${vahFmt}) — consolidating within the main volume cluster.`, type: 'neutral' });
    }

    return takeaways.slice(0, 5);
}

function renderDrilldown() {
    if (!dashboardData) return;

    const selectedAsset     = document.getElementById('drilldown-asset-select').value;
    const selectedTimeframe = document.getElementById('timeframe-select').value;

    const assetData     = dashboardData.assets[selectedAsset];
    if (!assetData) return;
    const timeframeData = assetData[selectedTimeframe];
    if (!timeframeData) return;
    const current = timeframeData.current;

    // ── Summary ───────────────────────────────────────────────────────────────
    const summaryContainer = document.getElementById('drilldown-summary');
    summaryContainer.innerHTML = `
        <div class="drilldown-summary-grid">
            <div class="summary-item">
                <span class="summary-label">Price</span>
                <span class="summary-value">${formatPrice(selectedAsset, current?.price)}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">EMA21</span>
                <span class="summary-value">${formatPrice(selectedAsset, current?.ema21)}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">ATR</span>
                <span class="summary-value">${current?.atr?.toFixed(2) ?? 'N/A'}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">RSI</span>
                <span class="summary-value ${rsiClass(current?.rsi)}">${current?.rsi?.toFixed(1) ?? 'N/A'}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">ATR Distance</span>
                <span class="summary-value ${getAtrColorClass(current?.atr_distance) || signClass(current?.atr_distance)}">${current?.atr_distance?.toFixed(2) ?? 'N/A'}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">% Above EMA</span>
                <span class="summary-value ${signClass(current?.pct_above_ema)}">${current?.pct_above_ema?.toFixed(1) ?? 'N/A'}%</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Regime</span>
                <span class="summary-value"><span class="asset-regime ${regimeClass(current?.regime)}">${escapeHtml(current?.regime ?? 'Unknown')}</span></span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Percentile</span>
                <span class="summary-value">${current?.atr_percentile?.toFixed(0) ?? 'N/A'}th</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">RSI Z-Score</span>
                <span class="summary-value ${signClass(current?.rsi_z_score)}">${current?.rsi_z_score?.toFixed(2) ?? 'N/A'}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Chg% (${selectedTimeframe === '1d' ? 'Day' : 'Week'})</span>
                <span class="summary-value ${signClass(current?.price_change_pct)}">${current?.price_change_pct != null ? (current.price_change_pct >= 0 ? '+' : '') + current.price_change_pct.toFixed(2) + '%' : 'N/A'}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">VP Zone</span>
                <span class="summary-value">${current?.vp_position ? vpBadgeHtml(current.vp_position) : 'N/A'}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">POC</span>
                <span class="summary-value">${formatPrice(selectedAsset, current?.vp_poc)}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">VAH</span>
                <span class="summary-value">${formatPrice(selectedAsset, current?.vp_vah)}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">VAL</span>
                <span class="summary-value">${formatPrice(selectedAsset, current?.vp_val)}</span>
            </div>
            ${current?.market_cap_rank != null ? `
            <div class="summary-item">
                <span class="summary-label">MCap Rank</span>
                <span class="summary-value"><span class="mcap-badge ${mcapRankClass(current.market_cap_rank)}">#${current.market_cap_rank}</span></span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Market Cap</span>
                <span class="summary-value">${formatMarketCap(current.market_cap)}</span>
            </div>` : ''}
            ${current?.alignment ? `
            <div class="summary-item">
                <span class="summary-label">TF Align</span>
                <span class="summary-value"><span class="align-badge ${alignBadgeClass(current.alignment)}">${alignBadgeLabel(current.alignment)} ${escapeHtml(current.alignment.replace('aligned-','').replace('diverging','Diverging'))}</span></span>
            </div>` : ''}
            ${current?.atr_trend ? `
            <div class="summary-item">
                <span class="summary-label">ATR Trend</span>
                <span class="summary-value"><span class="atr-trend-icon atr-trend-${escapeHtml(current.atr_trend)}">${atrTrendIcon(current.atr_trend)}</span> ${escapeHtml(current.atr_trend)}</span>
            </div>` : ''}
            ${current?.regime_changed ? `
            <div class="summary-item">
                <span class="summary-label">Transition</span>
                <span class="summary-value">${escapeHtml(current.prev_regime ?? '?')} → ${escapeHtml(current.regime ?? '?')}</span>
            </div>` : ''}
            ${current?.rs_vs_btc != null ? `
            <div class="summary-item">
                <span class="summary-label">RS/BTC (30d)</span>
                <span class="summary-value">${rsBadgeHtml(current.rs_vs_btc)}</span>
            </div>` : ''}
        </div>
    `;

    // ── Key Takeaways ─────────────────────────────────────────────────────────
    const takeawaysContainer = document.getElementById('drilldown-takeaways');
    if (takeawaysContainer) {
        const chartHistForAsset = chartHistoryData?.[selectedAsset]?.[selectedTimeframe] ?? null;
        const takeaways = generateKeyTakeaways(selectedAsset, timeframeData, assetData, chartHistForAsset);
        if (takeaways.length > 0) {
            const iconMap  = { positive: '▲', negative: '▼', neutral: '●' };
            const ariaMap  = { positive: 'bullish signal', negative: 'bearish signal', neutral: 'neutral observation' };
            takeawaysContainer.innerHTML = `
                <div class="takeaways-panel">
                    <h4 class="takeaways-title">Key Takeaways</h4>
                    <ul class="takeaways-list">
                        ${takeaways.map(t => `
                            <li class="takeaway-item takeaway-item--${t.type}">
                                <span class="takeaway-icon" aria-label="${ariaMap[t.type]}">${iconMap[t.type]}</span>
                                <span class="takeaway-text">${escapeHtml(t.text)}</span>
                            </li>
                        `).join('')}
                    </ul>
                </div>
            `;
        } else {
            takeawaysContainer.innerHTML = '';
        }
    }

    // ── Charts ────────────────────────────────────────────────────────────────
    if (chartHistoryData) {
        const assetHistory = chartHistoryData[selectedAsset];
        const tfHistory    = assetHistory?.[selectedTimeframe] ?? [];
        const wkHistory    = assetHistory?.['1w'] ?? [];

        renderAtrDistanceChart(tfHistory, selectedTimeframe, current?.atr_distance);
        renderRsiChart(tfHistory, selectedTimeframe);
        renderPriceEmaChart(tfHistory, selectedTimeframe);
        renderWeeklyAtrChart(wkHistory);
    } else {
        renderPlaceholderChart('atr-distance-chart',  'ATR Distance History');
        renderPlaceholderChart('rsi-chart',            'RSI History');
        renderPlaceholderChart('price-ema-chart',      'Price vs EMA21');
        renderPlaceholderChart('weekly-atr-chart',     'Weekly ATR Distance');
    }
    renderVolumeProfileChart(current, selectedTimeframe);
}

// ─── Chart helpers ────────────────────────────────────────────────────────────

function destroyChart(id) {
    if (charts[id]) {
        charts[id].destroy();
        delete charts[id];
    }
}


const REGIME_ANNOTATIONS = {
    capitulationZone: {
        type: 'box', yMax: -4,
        backgroundColor: 'rgba(153,27,27,0.12)', borderWidth: 0
    },
    accumulationZone: {
        type: 'box', yMin: -4, yMax: -2,
        backgroundColor: 'rgba(16,185,129,0.10)', borderWidth: 0
    },
    distributionZone: {
        type: 'box', yMin: 2, yMax: 4,
        backgroundColor: 'rgba(249,115,22,0.12)', borderWidth: 0
    },
    maniaZone: {
        type: 'box', yMin: 4,
        backgroundColor: 'rgba(239,68,68,0.12)', borderWidth: 0
    }
};

function renderAtrDistanceChart(history, tf, currentValue) {
    const id = 'atr-distance-chart';
    destroyChart(id);

    if (!history || history.length === 0) {
        renderPlaceholderChart(id, 'ATR Distance History');
        return;
    }

    const container = document.getElementById(id);
    container.innerHTML = '<h4>ATR Distance History</h4>';
    const canvas = document.createElement('canvas');
    container.appendChild(canvas);

    const annotations = { ...REGIME_ANNOTATIONS };
    if (currentValue != null) {
        annotations.currentLine = {
            type: 'line',
            yMin: currentValue, yMax: currentValue,
            borderColor: 'rgba(255,255,255,0.5)',
            borderDash: [4, 4],
            borderWidth: 1
        };
    }

    charts[id] = new Chart(canvas, {
        type: 'line',
        data: {
            labels: history.map(r => r.d),
            datasets: [{
                label: 'ATR Distance',
                data: history.map(r => r.a),
                borderColor: '#3b82f6',
                borderWidth: 1.5,
                pointRadius: 0,
                tension: 0.1,
                fill: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                annotation: { annotations }
            },
            scales: {
                x: { ticks: { maxTicksLimit: 8, maxRotation: 0 } },
                y: { grid: { color: 'rgba(55,65,81,0.5)' } }
            }
        }
    });
}

function renderRsiChart(history, tf) {
    const id = 'rsi-chart';
    destroyChart(id);

    if (!history || history.length === 0) {
        renderPlaceholderChart(id, 'RSI History');
        return;
    }

    const container = document.getElementById(id);
    container.innerHTML = '<h4>RSI History</h4>';
    const canvas = document.createElement('canvas');
    container.appendChild(canvas);

    charts[id] = new Chart(canvas, {
        type: 'line',
        data: {
            labels: history.map(r => r.d),
            datasets: [{
                label: 'RSI',
                data: history.map(r => r.r),
                borderColor: '#8b5cf6',
                borderWidth: 1.5,
                pointRadius: 0,
                tension: 0.1,
                fill: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                annotation: {
                    annotations: {
                        oversoldLine:  { type: 'line', yMin: 30, yMax: 30, borderColor: 'rgba(16,185,129,0.6)',  borderDash: [4,3], borderWidth: 1 },
                        overboughtLine:{ type: 'line', yMin: 70, yMax: 70, borderColor: 'rgba(239,68,68,0.6)',   borderDash: [4,3], borderWidth: 1 },
                        fairValueBand: { type: 'box',  yMin: 30, yMax: 70, backgroundColor: 'rgba(59,130,246,0.05)', borderWidth: 0 }
                    }
                }
            },
            scales: {
                x: { ticks: { maxTicksLimit: 8, maxRotation: 0 } },
                y: { min: 0, max: 100, grid: { color: 'rgba(55,65,81,0.5)' } }
            }
        }
    });
}

function renderPriceEmaChart(history, tf) {
    const id = 'price-ema-chart';
    destroyChart(id);

    if (!history || history.length === 0) {
        renderPlaceholderChart(id, 'Price vs EMA21');
        return;
    }

    const container = document.getElementById(id);
    container.innerHTML = '<h4>Price vs EMA21</h4>';
    const canvas = document.createElement('canvas');
    container.appendChild(canvas);

    charts[id] = new Chart(canvas, {
        type: 'line',
        data: {
            labels: history.map(r => r.d),
            datasets: [
                {
                    label: 'Price',
                    data: history.map(r => r.p),
                    borderColor: '#e0e6ed',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    tension: 0.1,
                    fill: false
                },
                {
                    label: 'EMA21',
                    data: history.map(r => r.e),
                    borderColor: '#3b82f6',
                    borderDash: [4, 3],
                    borderWidth: 1.5,
                    pointRadius: 0,
                    tension: 0.1,
                    fill: false,
                    spanGaps: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: { legend: { labels: { boxWidth: 12, padding: 12 } } },
            scales: {
                x: { ticks: { maxTicksLimit: 8, maxRotation: 0 } },
                y: { grid: { color: 'rgba(55,65,81,0.5)' } }
            }
        }
    });
}

function renderWeeklyAtrChart(history) {
    const id = 'weekly-atr-chart';
    destroyChart(id);

    if (!history || history.length === 0) {
        renderPlaceholderChart(id, 'Weekly ATR Distance', 'Insufficient weekly history for this asset.');
        return;
    }

    const container = document.getElementById(id);
    container.innerHTML = '<h4>Weekly ATR Distance</h4>';
    const canvas = document.createElement('canvas');
    container.appendChild(canvas);

    charts[id] = new Chart(canvas, {
        type: 'line',
        data: {
            labels: history.map(r => r.d),
            datasets: [{
                label: 'Weekly ATR Distance',
                data: history.map(r => r.a),
                borderColor: '#f59e0b',
                borderWidth: 1.5,
                pointRadius: 0,
                tension: 0.1,
                fill: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                annotation: { annotations: REGIME_ANNOTATIONS }
            },
            scales: {
                x: { ticks: { maxTicksLimit: 8, maxRotation: 0 } },
                y: { grid: { color: 'rgba(55,65,81,0.5)' } }
            }
        }
    });
}

function renderPlaceholderChart(chartId, title, message) {
    const container = document.getElementById(chartId);
    if (!container) return;
    container.innerHTML = `
        <h4>${title}</h4>
        <div class="chart-placeholder">
            <div>
                <div style="font-size:2rem;margin-bottom:0.5rem">📊</div>
                <div>${message ?? 'Historical chart data coming soon'}</div>
            </div>
        </div>
    `;
}

// ─── Macro tab ────────────────────────────────────────────────────────────────

function renderMacro() {
    if (!dashboardData) return;
    const container = document.getElementById('macro-content');
    if (!container) return;
    container.innerHTML = '';

    Object.entries(MACRO_SUBCATEGORIES).forEach(([groupName, symbols]) => {
        const group = document.createElement('div');
        group.className = 'macro-group';

        const title = document.createElement('div');
        title.className = 'macro-group-title';
        title.textContent = groupName;
        group.appendChild(title);

        const cards = document.createElement('div');
        cards.className = 'macro-group-cards';

        symbols.forEach(symbol => {
            const assetData = dashboardData.assets[symbol];
            const daily = assetData?.['1d']?.current;
            if (!daily) return;

            const atrDist = daily.atr_distance;
            const zone    = macroZoneLabel(atrDist);
            const chg     = daily.price_change_pct;
            const price   = daily.price;

            // Forex/DXY: plain number (4dp for pairs, 2dp for DXY); indices/commodities: $-formatted
            const priceStr = price == null ? 'N/A'
                : symbol === 'DXY'              ? price.toFixed(2)
                : MACRO_FOREX_SYMBOLS.has(symbol) ? price.toFixed(4)
                : `$${price.toLocaleString()}`;

            const chgStr = chg != null ? (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%' : '';
            const chgCls = chg == null ? '' : chg >= 0 ? 'positive' : 'negative';
            const atrStr = atrDist != null ? atrDist.toFixed(2) : 'N/A';
            const atrCls = getAtrColorClass(atrDist) || signClass(atrDist);

            const card = document.createElement('div');
            card.className = 'macro-card';
            card.dataset.asset = symbol;

            const sym = document.createElement('span');
            sym.className = 'macro-card-symbol';
            sym.textContent = symbol;

            const zoneBadge = document.createElement('span');
            zoneBadge.className = `zone-badge ${zone.cssClass} macro-card-zone`;
            zoneBadge.textContent = zone.label;

            const priceEl = document.createElement('span');
            priceEl.className = 'macro-card-price';
            priceEl.textContent = priceStr;

            const atrEl = document.createElement('span');
            atrEl.className = `macro-card-atr ${atrCls}`;
            atrEl.textContent = atrStr;

            if (chgStr) {
                const chgEl = document.createElement('span');
                chgEl.className = `macro-card-chg ${chgCls}`;
                chgEl.textContent = chgStr;
                card.append(sym, zoneBadge, priceEl, atrEl, chgEl);
            } else {
                card.append(sym, zoneBadge, priceEl, atrEl);
            }

            cards.appendChild(card);
        });

        group.appendChild(cards);
        container.appendChild(group);
    });

    // Click → open Drilldown for the selected macro asset
    container.addEventListener('click', e => {
        const card = e.target.closest('.macro-card[data-asset]');
        if (card) navigateTo('drilldown-tab', card.dataset.asset);
    });
}

function renderVolumeProfileChart(current, tf) {
    const id = 'volume-profile-chart';
    destroyChart(id);
    const container = document.getElementById(id);
    if (!container) return;

    if (!current?.vp_buckets?.length) {
        renderPlaceholderChart(id, 'Volume Profile', 'Volume data not available for this asset.');
        return;
    }

    // Reverse so highest price is at the top of the chart (standard price axis convention)
    const buckets  = [...current.vp_buckets].reverse();
    const labels   = buckets.map(b => b.p.toFixed(4));
    const volumes  = buckets.map(b => b.v);

    // Find bucket closest to current price for highlighting
    const priceIdx = buckets.reduce((best, b, i) =>
        Math.abs(b.p - (current.price ?? 0)) < Math.abs(buckets[best].p - (current.price ?? 0)) ? i : best, 0);

    const colors = buckets.map((b, i) => {
        if (i === priceIdx) return 'rgba(245,158,11,0.85)';   // current price — amber
        if (b.is_poc)       return 'rgba(59,130,246,0.85)';   // POC — blue
        if (b.in_va)        return 'rgba(16,185,129,0.45)';   // Value Area — green tint
        return                     'rgba(100,116,139,0.35)';  // outside VA — muted
    });

    const lookbackLabel = tf === '1w' ? '52-Week' : '90-Day';
    container.innerHTML = `<h4>${lookbackLabel} Volume Profile</h4>`;
    const canvas = document.createElement('canvas');
    container.appendChild(canvas);

    // Legend — built via DOM to satisfy CSP style-src 'self' (no unsafe-inline)
    const legend = document.createElement('div');
    legend.className = 'vp-chart-info';
    [['vp-legend-poc', 'POC'], ['vp-legend-va', 'Value Area'], ['vp-legend-price', 'Current Price']].forEach(([cls, txt]) => {
        const s = document.createElement('span');
        s.className = cls;
        s.textContent = txt;
        legend.appendChild(s);
    });
    container.appendChild(legend);

    charts[id] = new Chart(canvas, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: volumes,
                backgroundColor: colors,
                borderWidth: 0,
                barPercentage: 1.0,
                categoryPercentage: 1.0,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: true,
            plugins: { legend: { display: false } },
            scales: {
                x: {
                    title: { display: true, text: 'Volume', color: 'rgba(160,174,192,0.8)', font: { size: 10 } },
                    grid: { color: 'rgba(55,65,81,0.5)' },
                    ticks: { maxTicksLimit: 5 }
                },
                y: {
                    ticks: { maxTicksLimit: 8, font: { size: 9 } },
                    grid: { display: false }
                }
            }
        }
    });
}
