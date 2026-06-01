// Dashboard JavaScript
let dashboardData = null;
let chartHistoryData = null;
let chartHistoryPromise = null;   // single in-flight fetch; all callers await this
const charts = {};

// Asset categorisation (mirrors trading_utils/config.py ASSETS list)
const ASSET_CATEGORIES = {
    crypto: new Set(['BTC','ETH','SOL','XLM','REZ','RSR','NEAR','RENDER','ONDO','ACH','BNB','XRP','ADA','NIGHT','D2X','SCP']),
    nasdaq: new Set(['MSTR','XXI','RIOT','MARA','IREN','BMNR','HUT','WULF','HIVE','CLSK','SLNH']),
    lse:    new Set(['MSTY','YMST','MARY','RIOY','IREY','BMNY'])
};

// LSE ETFs are quoted in GBp (pence) by Yahoo Finance
const LSE_ASSETS = ASSET_CATEGORIES.lse;

// Regime display order for the summary strip
const REGIME_ORDER = ['Capitulation','Accumulation','Trend','Distribution','Mania','Unknown'];

// Portfolio filter state
const portfolioFilter = { category: '', regime: null, sort: 'name' };

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
            }
        });
    });
}

// ─── Asset selectors ──────────────────────────────────────────────────────────

function setupAssetSelectors() {
    if (!dashboardData) return;
    const assets = Object.keys(dashboardData.assets).sort();

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
}

// ─── Portfolio rendering ──────────────────────────────────────────────────────

function renderPortfolio() {
    if (!dashboardData) return;

    const container = document.getElementById('portfolio-cards');
    container.innerHTML = '';

    let assets = Object.keys(dashboardData.assets).sort();

    // ── Regime strip ──────────────────────────────────────────────────────────
    const regimeCounts = {};
    assets.forEach(a => {
        const r = dashboardData.assets[a]['1d']?.current?.regime || 'Unknown';
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
            const r = dashboardData.assets[a]['1d']?.current?.regime || 'Unknown';
            return r === portfolioFilter.regime;
        });
    }

    // ── Sort — getRaw returns null for missing values so sentinels apply correctly ──
    const getRaw = (a, field) => dashboardData.assets[a]['1d']?.current?.[field] ?? null;
    if (portfolioFilter.sort === 'atr_asc') {
        assets.sort((a, b) => (getRaw(a, 'atr_distance') ?? Infinity) - (getRaw(b, 'atr_distance') ?? Infinity));
    } else if (portfolioFilter.sort === 'atr_desc') {
        assets.sort((a, b) => (getRaw(b, 'atr_distance') ?? -Infinity) - (getRaw(a, 'atr_distance') ?? -Infinity));
    } else if (portfolioFilter.sort === 'rsi_asc') {
        assets.sort((a, b) => (getRaw(a, 'rsi') ?? Infinity) - (getRaw(b, 'rsi') ?? Infinity));
    }
    // default: name A-Z (already sorted)

    if (assets.length === 0) {
        container.innerHTML = '<div class="loading">No assets match the current filter.</div>';
        return;
    }

    // ── Render cards ──────────────────────────────────────────────────────────
    assets.forEach(asset => {
        const assetData  = dashboardData.assets[asset];
        const dailyData  = assetData['1d']?.current;
        const weeklyData = assetData['1w']?.current;

        if (!dailyData) return;

        const atrDistD = dailyData.atr_distance;
        const atrDistW = weeklyData?.atr_distance;
        const rsi      = dailyData.rsi;
        const regime   = dailyData.regime || 'Unknown';

        const latestDate = dashboardData.metadata?.date_range?.end;
        const isStale = latestDate && dailyData.date
            ? Math.floor((new Date(latestDate) - new Date(dailyData.date)) / 86400000) >= 3
            : false;

        const ea = escapeHtml(asset);
        const er = escapeHtml(regime);
        const card = document.createElement('div');
        card.className = 'asset-card';
        card.dataset.asset = asset;
        card.innerHTML = `
            <div class="asset-card-header">
                <span class="asset-name">${ea}</span>
                <span class="asset-regime ${regimeClass(regime)}">${er}</span>
            </div>
            <div class="asset-metrics">
                <div class="metric">
                    <span class="metric-label">ATR Dist.</span>
                    <span class="metric-value ${signClass(atrDistD)}">
                        ${atrDistD?.toFixed(2) ?? 'N/A'}
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">W-ATR Dist.</span>
                    <span class="metric-value ${signClass(atrDistW)}">
                        ${atrDistW?.toFixed(2) ?? 'N/A'}
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">RSI</span>
                    <span class="metric-value ${rsiClass(rsi)}">${rsi?.toFixed(1) ?? 'N/A'}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Price</span>
                    <span class="metric-value">${formatPrice(asset, dailyData.price)}</span>
                </div>
            </div>
            <div class="asset-card-footer">
                <span class="asset-date${isStale ? ' stale' : ''}">
                    ${isStale ? '&#x26A0; ' : ''}as of ${escapeHtml(dailyData.date ?? '—')}
                </span>
            </div>
        `;
        container.appendChild(card);
    });

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
        const d = assetData['1d']?.current;
        if (d?.atr_distance != null) {
            rankings.push({ asset, atrDistance: d.atr_distance, regime: d.regime || 'Unknown' });
        }
    });
    rankings.sort((a, b) => a.atrDistance - b.atrDistance);

    const oversold = rankings.slice(0, 10).filter(r => r.atrDistance < 0);
    const extended = rankings.slice(-10).reverse().filter(r => r.atrDistance > 0);

    const renderItem = (container, { asset, atrDistance, regime }, cssClass) => {
        const item = document.createElement('div');
        item.className = 'ranking-item';
        item.dataset.asset = asset;
        item.innerHTML = `
            <span class="ranking-asset">${escapeHtml(asset)}</span>
            <span class="asset-regime ${regimeClass(regime)}">${escapeHtml(regime)}</span>
            <span class="ranking-value ${cssClass}">${atrDistance.toFixed(2)}</span>
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
        const range   = atrMax - atrMin || 1;
        const pct     = current.atr_percentile ?? 50;

        const toPos = val => Math.max(0, Math.min(100, ((val - atrMin) / range) * 100));

        // Regime zone positions (thresholds: -4, -2, 2, 4)
        const zones = [
            { name: 'capitulation', from: -Infinity, to: -4 },
            { name: 'accumulation', from: -4,        to: -2 },
            { name: 'trend',        from: -2,         to:  2 },
            { name: 'distribution', from:  2,         to:  4 },
            { name: 'mania',        from:  4,         to:  Infinity }
        ];

        const zoneHtml = zones.map(z => {
            const left  = toPos(Math.max(z.from, atrMin));
            const right = toPos(Math.min(z.to,   atrMax));
            const width = right - left;
            if (width <= 0) return '';
            return `<div class="gauge-zone gauge-zone-${z.name}" style="left:${left.toFixed(1)}%;width:${width.toFixed(1)}%"></div>`;
        }).join('');

        const ticks = [
            { label: 'P25', val: historical.atr_percentile_25 },
            { label: 'P50', val: historical.atr_percentile_50 },
            { label: 'P75', val: historical.atr_percentile_75 },
            { label: 'P90', val: historical.atr_percentile_90 }
        ].filter(t => t.val != null).map(t =>
            `<div class="gauge-tick" style="left:${toPos(t.val).toFixed(1)}%">${t.label}</div>`
        ).join('');

        const gaugeHtml = `
            <div class="percentile-gauge-section">
                <div class="percentile-gauge-label">ATR Distance — historical position</div>
                <div class="gauge-wrap">
                    <div class="gauge-track">
                        ${zoneHtml}
                        ${ticks}
                        ${current.atr_distance != null ? `<div class="gauge-marker" style="left:${toPos(current.atr_distance).toFixed(1)}%"></div>` : ''}
                    </div>
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

        pane.innerHTML += gaugeHtml + metricsHtml;
        dual.appendChild(pane);
    });

    container.appendChild(dual);
}

// ─── Drilldown ────────────────────────────────────────────────────────────────

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
                <span class="summary-value ${signClass(current?.atr_distance)}">${current?.atr_distance?.toFixed(2) ?? 'N/A'}</span>
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
        </div>
    `;

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
