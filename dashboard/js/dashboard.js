// Dashboard JavaScript
let dashboardData = null;

// LSE ETFs are quoted in GBp (pence) by Yahoo Finance — display with 'p' prefix instead of '$'
const LSE_ASSETS = new Set(['MSTY', 'YMST', 'MARY', 'RIOY', 'IREY', 'BMNY']);

function formatPrice(asset, price) {
    if (price == null) return 'N/A';
    if (LSE_ASSETS.has(asset)) {
        return `${price.toLocaleString()}p`;
    }
    return `$${price.toLocaleString()}`;
}

// Load dashboard data on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadDashboardData();
    if (!dashboardData) {
        const mainContent = document.querySelector('.tab-content.active') || document.querySelector('.main-content');
        if (mainContent) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error';
            errorDiv.textContent = 'Error loading dashboard data';
            mainContent.innerHTML = '';
            mainContent.appendChild(errorDiv);
        }
        const navButtons = document.querySelectorAll('.nav-btn');
        navButtons.forEach(btn => btn.disabled = true);
        return;
    }
    setupNavigation();
    setupAssetSelectors();
    renderPortfolio();
    renderRankings();
    renderHistoricalContext();
    renderDrilldown();
});

// Load dashboard data from JSON
async function loadDashboardData() {
    try {
        const response = await fetch('assets/data.json');
        if (!response.ok) {
            throw new Error('Failed to load dashboard data');
        }
        dashboardData = await response.json();
        
        // Update last updated timestamp
        const lastUpdated = new Date(dashboardData.metadata.last_updated);
        document.getElementById('lastUpdated').textContent = 
            `Last updated: ${lastUpdated.toLocaleString()}`;
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        document.getElementById('lastUpdated').textContent = 'Error loading data';
    }
}

// Setup bottom navigation
function setupNavigation() {
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    navButtons.forEach(button => {
        button.addEventListener('click', () => {
            const targetTab = button.dataset.tab;
            
            // Update active button
            navButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            
            // Update active tab
            tabContents.forEach(tab => {
                tab.classList.remove('active');
                if (tab.id === targetTab) {
                    tab.classList.add('active');
                }
            });
        });
    });
}

// Setup asset selectors
function setupAssetSelectors() {
    if (!dashboardData) return;
    
    const assets = Object.keys(dashboardData.assets).sort();
    
    // Historical context selector
    const historicalSelect = document.getElementById('asset-select');
    assets.forEach(asset => {
        const option = document.createElement('option');
        option.value = asset;
        option.textContent = asset;
        historicalSelect.appendChild(option);
    });
    
    historicalSelect.addEventListener('change', renderHistoricalContext);
    
    // Drilldown selector
    const drilldownSelect = document.getElementById('drilldown-asset-select');
    assets.forEach(asset => {
        const option = document.createElement('option');
        option.value = asset;
        option.textContent = asset;
        drilldownSelect.appendChild(option);
    });
    
    drilldownSelect.addEventListener('change', renderDrilldown);
    
    // Timeframe selector
    const timeframeSelect = document.getElementById('timeframe-select');
    timeframeSelect.addEventListener('change', renderDrilldown);
}

// Render portfolio overview
function renderPortfolio() {
    if (!dashboardData) return;
    
    const container = document.getElementById('portfolio-cards');
    container.innerHTML = '';
    
    const assets = Object.keys(dashboardData.assets).sort();
    
    assets.forEach(asset => {
        const assetData = dashboardData.assets[asset];
        const dailyData = assetData['1d']?.current;
        const weeklyData = assetData['1w']?.current;
        
        if (!dailyData) return;
        
        const card = document.createElement('div');
        card.className = 'asset-card';
        
        const regimeClass = `regime-${(dailyData.regime || 'trend').toLowerCase()}`;
        
        card.innerHTML = `
            <div class="asset-card-header">
                <span class="asset-name">${asset}</span>
                <span class="asset-regime ${regimeClass}">${dailyData.regime || 'Trend'}</span>
            </div>
            <div class="asset-metrics">
                <div class="metric">
                    <span class="metric-label">Daily ATR</span>
                    <span class="metric-value ${dailyData.atr_distance >= 0 ? 'positive' : 'negative'}">
                        ${dailyData.atr_distance?.toFixed(2) || 'N/A'}
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">Weekly ATR</span>
                    <span class="metric-value ${weeklyData?.atr_distance >= 0 ? 'positive' : 'negative'}">
                        ${weeklyData?.atr_distance?.toFixed(2) || 'N/A'}
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">RSI</span>
                    <span class="metric-value">${dailyData.rsi?.toFixed(1) || 'N/A'}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Price</span>
                    <span class="metric-value">${formatPrice(asset, dailyData.price)}</span>
                </div>
            </div>
        `;
        
        container.appendChild(card);
    });
}

// Render ATR rankings
function renderRankings() {
    if (!dashboardData) return;
    
    const oversoldContainer = document.getElementById('oversold-list');
    const extendedContainer = document.getElementById('extended-list');
    
    oversoldContainer.innerHTML = '';
    extendedContainer.innerHTML = '';
    
    const rankings = [];
    
    Object.entries(dashboardData.assets).forEach(([asset, assetData]) => {
        const dailyData = assetData['1d']?.current;
        if (dailyData?.atr_distance !== null && dailyData?.atr_distance !== undefined) {
            rankings.push({
                asset,
                atrDistance: dailyData.atr_distance
            });
        }
    });
    
    // Sort by ATR Distance
    rankings.sort((a, b) => a.atrDistance - b.atrDistance);
    
    // Most oversold: Capitulation (< -4) + Accumulation (-4..-2)
    const oversold = rankings.slice(0, 10).filter(r => r.atrDistance < 0);
    oversold.forEach(({ asset, atrDistance }) => {
        const item = document.createElement('div');
        item.className = 'ranking-item';
        item.innerHTML = `
            <span class="ranking-asset">${asset}</span>
            <span class="ranking-value oversold">${atrDistance.toFixed(2)}</span>
        `;
        oversoldContainer.appendChild(item);
    });

    // Most extended: Distribution (2..4) + Mania (> 4)
    const extended = rankings.slice(-10).reverse().filter(r => r.atrDistance > 0);
    extended.forEach(({ asset, atrDistance }) => {
        const item = document.createElement('div');
        item.className = 'ranking-item';
        item.innerHTML = `
            <span class="ranking-asset">${asset}</span>
            <span class="ranking-value extended">${atrDistance.toFixed(2)}</span>
        `;
        extendedContainer.appendChild(item);
    });
}

// Render historical context
function renderHistoricalContext() {
    if (!dashboardData) return;
    
    const assetSelect = document.getElementById('asset-select');
    const selectedAsset = assetSelect.value;
    const container = document.getElementById('historical-content');
    
    const assetData = dashboardData.assets[selectedAsset];
    if (!assetData) return;
    
    const dailyData = assetData['1d'];
    const historical = dailyData?.historical;
    const current = dailyData?.current;
    
    if (!historical || !current) {
        container.innerHTML = '<div class="loading">No data available</div>';
        return;
    }
    
    container.innerHTML = `
        <div class="historical-metrics">
            <div class="historical-metric">
                <div class="historical-metric-label">Current ATR Distance</div>
                <div class="historical-metric-value">${current.atr_distance?.toFixed(2) || 'N/A'}</div>
                <div class="historical-metric-sub">Regime: ${current.regime || 'Unknown'}</div>
            </div>
            <div class="historical-metric">
                <div class="historical-metric-label">Historical Max</div>
                <div class="historical-metric-value">${historical.atr_max?.toFixed(2) || 'N/A'}</div>
                <div class="historical-metric-sub">All-time high</div>
            </div>
            <div class="historical-metric">
                <div class="historical-metric-label">Historical Min</div>
                <div class="historical-metric-value">${historical.atr_min?.toFixed(2) || 'N/A'}</div>
                <div class="historical-metric-sub">All-time low</div>
            </div>
            <div class="historical-metric">
                <div class="historical-metric-label">Percentile</div>
                <div class="historical-metric-value">${current.atr_percentile?.toFixed(1) || 'N/A'}%</div>
                <div class="historical-metric-sub">Current vs historical</div>
            </div>
            <div class="historical-metric">
                <div class="historical-metric-label">25th Percentile</div>
                <div class="historical-metric-value">${historical.atr_percentile_25?.toFixed(2) || 'N/A'}</div>
            </div>
            <div class="historical-metric">
                <div class="historical-metric-label">50th Percentile</div>
                <div class="historical-metric-value">${historical.atr_percentile_50?.toFixed(2) || 'N/A'}</div>
            </div>
            <div class="historical-metric">
                <div class="historical-metric-label">75th Percentile</div>
                <div class="historical-metric-value">${historical.atr_percentile_75?.toFixed(2) || 'N/A'}</div>
            </div>
            <div class="historical-metric">
                <div class="historical-metric-label">90th Percentile</div>
                <div class="historical-metric-value">${historical.atr_percentile_90?.toFixed(2) || 'N/A'}</div>
            </div>
        </div>
    `;
}

// Render asset drilldown
function renderDrilldown() {
    if (!dashboardData) return;
    
    const assetSelect = document.getElementById('drilldown-asset-select');
    const timeframeSelect = document.getElementById('timeframe-select');
    const selectedAsset = assetSelect.value;
    const selectedTimeframe = timeframeSelect.value;
    
    const assetData = dashboardData.assets[selectedAsset];
    if (!assetData) return;
    
    const timeframeData = assetData[selectedTimeframe];
    if (!timeframeData) return;
    
    const current = timeframeData.current;

    // Render summary
    const summaryContainer = document.getElementById('drilldown-summary');
    summaryContainer.innerHTML = `
        <div class="drilldown-summary-grid">
            <div class="summary-item">
                <span class="summary-label">Asset</span>
                <span class="summary-value">${selectedAsset}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Timeframe</span>
                <span class="summary-value">${selectedTimeframe === '1d' ? 'Daily' : 'Weekly'}</span>
            </div>
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
                <span class="summary-value">${current?.atr?.toFixed(2) || 'N/A'}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">RSI</span>
                <span class="summary-value">${current?.rsi?.toFixed(1) || 'N/A'}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">ATR Distance</span>
                <span class="summary-value">${current?.atr_distance?.toFixed(2) || 'N/A'}</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Regime</span>
                <span class="summary-value">${current?.regime || 'Unknown'}</span>
            </div>
        </div>
    `;
    
    // Note: Actual historical charts would require loading history.csv data
    // For now, we'll show placeholder charts
    renderPlaceholderChart('price-ema-chart', 'Price vs EMA21');
    renderPlaceholderChart('atr-distance-chart', 'ATR Distance History');
    renderPlaceholderChart('rsi-chart', 'RSI History');
    renderPlaceholderChart('weekly-atr-chart', 'Weekly ATR Distance History');
}

// Render placeholder chart (actual implementation would use history.csv data)
function renderPlaceholderChart(chartId, title) {
    const chartContainer = document.getElementById(chartId);
    if (!chartContainer) return;
    
    chartContainer.innerHTML = `
        <div style="height: 250px; display: flex; align-items: center; justify-content: center; color: var(--text-secondary);">
            <div style="text-align: center;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">📊</div>
                <div>${title}</div>
                <div style="font-size: 0.875rem; margin-top: 0.5rem;">Historical chart data coming soon</div>
            </div>
        </div>
    `;
}
