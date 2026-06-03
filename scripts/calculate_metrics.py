#!/usr/bin/env python3
"""
Metrics Calculation Script
Calculates derived metrics from history.csv and generates dashboard.json.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from trading_utils import (
    HISTORY_CSV_PATH, DASHBOARD_JSON_PATH, CHART_HISTORY_JSON_PATH, METADATA_JSON_PATH,
    MARKET_CAPS_JSON_PATH, CORRELATION_JSON_PATH,
    calculate_volume_profile, VP_LOOKBACK_BARS, VP_LOOKBACK_BARS_WEEKLY,
    MACRO_ASSETS,
)


def _norm_timeframe(tf: str) -> str:
    """Normalise timeframe string to canonical form ('1d' / '1w')."""
    t = tf.lower()
    if t == 'daily':
        return '1d'
    if t == 'weekly':
        return '1w'
    return t


def _sanitise(obj):
    """Recursively replace float/numpy NaN / inf with None so json.dump produces valid JSON."""
    if isinstance(obj, dict):
        return {k: _sanitise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitise(v) for v in obj]
    if isinstance(obj, (float, np.floating)) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def classify_regime(atr_distance: float) -> str:
    """
    Classify market regime from ATR Distance:
      < -4   → Capitulation   (Panic / Capitulation)
      -4..-2 → Accumulation   (Oversold)
      -2..2  → Trend          (Balanced / Fair Value)
      2..4   → Distribution   (Extended)
      > 4    → Mania          (Euphoric / Blow-off)
    """
    if pd.isna(atr_distance):
        return 'Unknown'
    if atr_distance < -4:
        return 'Capitulation'
    if atr_distance < -2:
        return 'Accumulation'
    if atr_distance <= 2:
        return 'Trend'
    if atr_distance <= 4:
        return 'Distribution'
    return 'Mania'


def calculate_historical_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate historical ATR Distance statistics for each asset+timeframe."""
    metrics: Dict[str, Any] = {}

    for (asset, timeframe), group in df.groupby(['Asset', 'Timeframe']):
        if pd.isna(timeframe):
            continue

        tf_norm = _norm_timeframe(str(timeframe))
        metrics.setdefault(asset, {}).setdefault(tf_norm, {})

        atr_distances = group['ATR_Distance'].replace([np.inf, -np.inf], np.nan).dropna()

        if len(atr_distances) > 0:
            std = atr_distances.std()
            metrics[asset][tf_norm]['historical'] = {
                'atr_max': float(atr_distances.max()),
                'atr_min': float(atr_distances.min()),
                'atr_mean': float(atr_distances.mean()),
                'atr_std': float(std) if pd.notna(std) else None,
                'atr_percentile_25': float(atr_distances.quantile(0.25)),
                'atr_percentile_50': float(atr_distances.quantile(0.50)),
                'atr_percentile_75': float(atr_distances.quantile(0.75)),
                'atr_percentile_90': float(atr_distances.quantile(0.90)),
                'sample_size': len(atr_distances),
            }
        else:
            metrics[asset][tf_norm]['historical'] = {
                'atr_max': None, 'atr_min': None, 'atr_mean': None,
                'atr_std': None, 'atr_percentile_25': None,
                'atr_percentile_50': None, 'atr_percentile_75': None,
                'atr_percentile_90': None, 'sample_size': 0,
            }

    return metrics


def _load_market_caps() -> dict:
    """Load market_caps.json if present; return {} otherwise."""
    try:
        with open(MARKET_CAPS_JSON_PATH) as f:
            return json.load(f).get('data', {})
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return {}


def _compute_30d_returns(history_df: pd.DataFrame) -> dict:
    """Compute 30-day price returns per (asset, timeframe)."""
    returns: dict = {}
    for (asset, tf), group in history_df.groupby(['Asset', 'Timeframe']):
        if pd.isna(tf):
            continue
        tf_norm = _norm_timeframe(str(tf))
        group = group.sort_values('Date', ascending=True).dropna(subset=['Price'])
        if len(group) < 2:
            continue
        latest_date = pd.Timestamp(group['Date'].iloc[-1])
        target_date = latest_date - pd.Timedelta(days=30)
        past = group[pd.to_datetime(group['Date']) <= target_date]
        if len(past) == 0:
            continue
        curr_price = float(group['Price'].iloc[-1])
        past_price = float(past['Price'].iloc[-1])
        if past_price > 0:
            returns.setdefault(asset, {})[tf_norm] = (curr_price - past_price) / past_price
    return returns


def calculate_current_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate current snapshot metrics for each asset+timeframe."""
    metrics: Dict[str, Any] = {}
    market_caps = _load_market_caps()

    # Precompute normalised timeframe column once — avoids O(n²) recomputation per asset
    norm_series = df['Timeframe'].apply(
        lambda t: _norm_timeframe(str(t)) if pd.notna(t) else ''
    )

    latest = df.sort_values('Date', ascending=False).groupby(['Asset', 'Timeframe']).first()
    global_latest_date = pd.Timestamp(df['Date'].max())

    for (asset, timeframe), row in latest.iterrows():
        if pd.isna(timeframe):
            continue

        # Skip entries whose most-recent data is more than 60 days behind the global
        # latest date — these are tickers that stopped refreshing (e.g. delisted / renamed).
        row_date = pd.Timestamp(str(row['Date']))
        if (global_latest_date - row_date).days > 60:
            continue

        tf_norm = _norm_timeframe(str(timeframe))
        metrics.setdefault(asset, {}).setdefault(tf_norm, {})

        atr_distance = row.get('ATR_Distance')
        regime = classify_regime(atr_distance)

        asset_data = df[(df['Asset'] == asset) & (norm_series == tf_norm)]
        atr_distances = asset_data['ATR_Distance'].replace([np.inf, -np.inf], np.nan).dropna()

        if len(atr_distances) > 0 and pd.notna(atr_distance):
            percentile = float((atr_distances < float(atr_distance)).sum() / len(atr_distances) * 100)
        else:
            percentile = None

        # Price momentum: % change vs the previous bar
        _prices = asset_data[['Date', 'Price']].dropna(subset=['Price']).sort_values('Date', ascending=True)
        if len(_prices) >= 2:
            _curr_p = float(_prices.iloc[-1]['Price'])
            _prev_p = float(_prices.iloc[-2]['Price'])
            price_change_pct: float | None = (_curr_p - _prev_p) / _prev_p * 100 if _prev_p != 0 else None
        else:
            price_change_pct = None

        # Volume Profile — requires High, Low, Volume columns in history
        vp = None
        if {'High', 'Low', 'Volume'}.issubset(asset_data.columns):
            vp_df = asset_data.rename(columns={
                'Price': 'close', 'High': 'high', 'Low': 'low', 'Volume': 'volume'
            })
            lookback = VP_LOOKBACK_BARS_WEEKLY if tf_norm == '1w' else VP_LOOKBACK_BARS
            vp = calculate_volume_profile(vp_df, lookback_bars=lookback)

        # Regime transition — compare current regime to the previous bar
        sorted_data = asset_data.sort_values('Date', ascending=True)
        regime_changed = False
        prev_regime = None
        if len(sorted_data) >= 2:
            prev_atr_d = sorted_data.iloc[-2].get('ATR_Distance')
            if pd.notna(prev_atr_d):
                prev_regime = classify_regime(float(prev_atr_d))
                regime_changed = bool(prev_regime != regime)

        # ATR compression — slope of last 10 ATR bars (relative to mean ATR)
        atr_series = sorted_data['ATR'].dropna().values
        atr_trend = None
        if len(atr_series) >= 5:
            last10 = atr_series[-10:]
            if len(last10) >= 5:
                x = np.arange(len(last10), dtype=float)
                slope = float(np.polyfit(x, last10.astype(float), 1)[0])
                mean_atr = float(last10.mean())
                rel_slope = slope / mean_atr if mean_atr > 0 else 0.0
                if rel_slope > 0.01:
                    atr_trend = 'expanding'
                elif rel_slope < -0.01:
                    atr_trend = 'compressing'
                else:
                    atr_trend = 'flat'

        metrics[asset][tf_norm]['current'] = {
            'date': str(row['Date']),
            'price': float(row['Price']) if pd.notna(row['Price']) else None,
            'ema21': float(row['EMA21']) if pd.notna(row['EMA21']) else None,
            'atr': float(row['ATR']) if pd.notna(row['ATR']) else None,
            'rsi': float(row['RSI']) if pd.notna(row['RSI']) else None,
            'rsi_z_score': float(row['RSI_Z_Score']) if pd.notna(row.get('RSI_Z_Score')) else None,
            'atr_distance': float(atr_distance) if pd.notna(atr_distance) else None,
            'pct_above_ema': float(row['Pct_Above_EMA']) if pd.notna(row.get('Pct_Above_EMA')) else None,
            'adx': float(row['ADX']) if 'ADX' in row.index and pd.notna(row.get('ADX')) else None,
            'bb_pct_b':    float(row['BB_Pct_B'])    if 'BB_Pct_B'    in row.index and pd.notna(row.get('BB_Pct_B'))    else None,
            'bb_bandwidth': float(row['BB_Bandwidth']) if 'BB_Bandwidth' in row.index and pd.notna(row.get('BB_Bandwidth')) else None,
            'regime': regime,
            'atr_percentile': percentile,
            'price_change_pct': price_change_pct,
            'vp_poc':           vp['poc']           if vp else None,
            'vp_vah':           vp['vah']           if vp else None,
            'vp_val':           vp['val']           if vp else None,
            'vp_position':      vp['position']      if vp else None,
            'vp_dist_from_poc': vp['dist_from_poc'] if vp else None,
            'vp_buckets':       vp['buckets']       if vp else None,
            'market_cap':       market_caps.get(asset, {}).get('market_cap'),
            'market_cap_rank':  market_caps.get(asset, {}).get('market_cap_rank'),
            'regime_changed':   regime_changed,
            'prev_regime':      prev_regime,
            'atr_trend':        atr_trend,
        }

    return metrics


def generate_chart_history(df: pd.DataFrame, n_bars: int = 90) -> Dict[str, Any]:
    """
    Build chart_history.json — last N bars of ATR Distance, RSI, Price and EMA21
    per asset+timeframe, for use by the Drilldown charts in the dashboard.

    Output structure::

        {
            "BTC": {
                "1d": [{"d": "2026-03-01", "a": -1.23, "r": 45.1, "p": 68000, "e": 67500}, ...],
                "1w": [...]
            },
            ...
        }

    Keys are abbreviated to minimise JSON payload size.
    """
    result: Dict[str, Any] = {}

    for (asset, timeframe), group in df.groupby(['Asset', 'Timeframe']):
        if pd.isna(timeframe):
            continue

        tf_norm = _norm_timeframe(str(timeframe))
        group = group.sort_values('Date', ascending=True)

        # Restrict to rows that have a valid ATR_Distance
        valid = group.dropna(subset=['ATR_Distance'])
        tail = valid.tail(n_bars)

        bars = []
        for _, row in tail.iterrows():
            atr_d = row.get('ATR_Distance')
            rsi   = row.get('RSI')
            price = row.get('Price')
            ema   = row.get('EMA21')
            bars.append({
                'd': str(row['Date'])[:10],
                'a': round(float(atr_d), 4) if pd.notna(atr_d) else None,
                'r': round(float(rsi), 2)   if pd.notna(rsi)   else None,
                'p': round(float(price), 4) if pd.notna(price) else None,
                'e': round(float(ema), 4)   if pd.notna(ema)   else None,
            })

        bucket = result.setdefault(asset, {}).setdefault(tf_norm, [])
        bucket.extend(bars)

    # Deduplicate by date (last writer wins) and re-cap at n_bars, sorted ascending
    for asset_buckets in result.values():
        for tf in list(asset_buckets.keys()):
            seen: Dict[str, Any] = {}
            for bar in sorted(asset_buckets[tf], key=lambda b: b['d']):
                seen[bar['d']] = bar
            asset_buckets[tf] = list(seen.values())[-n_bars:]

    return result


def fetch_binance_futures() -> Dict[str, Any]:
    """Fetch funding rates and open interest from Binance USDT-M futures (free, no auth).

    Returns a dict keyed by coin symbol (e.g. 'BTC') with:
        {'funding_rate': float (% per 8h period), 'open_interest_usd': float|None}

    Only covers assets with active USDT-M perpetual contracts on Binance.
    Quarterly/delivery contracts (symbol contains '_') are excluded.
    Returns {} on any network failure.
    """
    _TRACKED = {
        'BTC', 'ETH', 'SOL', 'XLM', 'NEAR', 'BNB', 'XRP', 'ADA', 'LINK', 'NEO',
        'RENDER', 'SEI', 'DRIFT', 'EIGEN', 'W', 'WOO', 'JASMY', 'AEVO', 'GAS',
        'PEAQ', 'RSR', 'ACH', 'ONDO', 'VTHO', 'REZ', 'NIGHT', 'SCP', 'D2X',
    }
    try:
        resp = requests.get('https://fapi.binance.com/fapi/v1/premiumIndex', timeout=15)
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        print(f"  Warning: Binance premiumIndex fetch failed: {e}")
        return {}

    result: Dict[str, Any] = {}
    for item in items:
        sym = item.get('symbol', '')
        if not sym.endswith('USDT') or '_' in sym:
            continue
        coin = sym[:-4]
        if coin not in _TRACKED:
            continue
        try:
            result[coin] = {
                'funding_rate': float(item['lastFundingRate']) * 100,
                'mark_price': float(item['markPrice']),
                'open_interest_usd': None,
            }
        except (KeyError, ValueError, TypeError):
            pass

    for coin, data in result.items():
        try:
            oi_resp = requests.get(
                'https://fapi.binance.com/fapi/v1/openInterest',
                params={'symbol': f'{coin}USDT'},
                timeout=10,
            )
            oi_resp.raise_for_status()
            oi_contracts = float(oi_resp.json()['openInterest'])
            data['open_interest_usd'] = oi_contracts * data['mark_price']
        except Exception:
            pass

    return result


def fetch_btc_dominance() -> Optional[float]:
    """Fetch BTC market-cap dominance % from CoinGecko (free, no auth).

    Returns a float such as 52.3 (meaning 52.3%) or None on failure.
    """
    try:
        resp = requests.get('https://api.coingecko.com/api/v3/global', timeout=10)
        resp.raise_for_status()
        pct = resp.json()['data']['market_cap_percentage']['btc']
        return float(pct)
    except Exception as e:
        print(f"  Warning: BTC dominance fetch failed: {e}")
        return None


def calculate_altseason_index(history_df: pd.DataFrame, lookback_days: int = 90) -> Optional[Dict[str, Any]]:
    """Compute Altcoin Season Index from history.csv (no external API).

    Methodology mirrors the CMC index: percentage of tracked crypto assets
    (excluding BTC) that outperformed BTC over the last lookback_days days
    using daily (1d) price data.

    Returns {'score': int, 'label': str, 'alts_outperforming': int, 'total': int}
    or None when insufficient data.
    """
    _CRYPTO_EXCL_BTC = {
        'ETH', 'SOL', 'XLM', 'REZ', 'RSR', 'NEAR', 'RENDER', 'ONDO', 'ACH',
        'BNB', 'XRP', 'ADA', 'NIGHT', 'VTHO', 'LINK', 'NEO', 'GAS', 'DRIFT',
        'SEI', 'PEAQ', 'AEVO', 'EIGEN', 'W', 'WOO', 'JASMY', 'D2X', 'SCP',
    }
    norm_series = history_df['Timeframe'].apply(
        lambda t: _norm_timeframe(str(t)) if pd.notna(t) else ''
    )
    df1d = history_df[norm_series == '1d'].copy()
    df1d['Date'] = pd.to_datetime(df1d['Date'])

    def _return_over_window(asset: str) -> Optional[float]:
        g = df1d[df1d['Asset'] == asset].sort_values('Date').dropna(subset=['Price'])
        if len(g) < 2:
            return None
        latest = g['Date'].iloc[-1]
        cutoff = latest - pd.Timedelta(days=lookback_days)
        past = g[g['Date'] <= cutoff]
        if len(past) == 0:
            return None
        curr = float(g['Price'].iloc[-1])
        prev = float(past['Price'].iloc[-1])
        return (curr - prev) / prev if prev > 0 else None

    btc_ret = _return_over_window('BTC')
    if btc_ret is None:
        return None

    outperforming = 0
    total = 0
    for asset in _CRYPTO_EXCL_BTC:
        ret = _return_over_window(asset)
        if ret is None:
            continue
        total += 1
        if ret > btc_ret:
            outperforming += 1

    if total == 0:
        return None

    score = round(100 * outperforming / total)
    if score >= 75:
        label = 'Altcoin Season'
    elif score >= 55:
        label = 'Leaning Alt'
    elif score >= 45:
        label = 'Neutral'
    elif score >= 25:
        label = 'Leaning BTC'
    else:
        label = 'Bitcoin Season'

    return {'score': score, 'label': label, 'alts_outperforming': outperforming, 'total': total}


def fetch_fear_greed() -> Optional[Dict[str, Any]]:
    """Fetch latest Crypto Fear & Greed Index from alternative.me (free, no auth)."""
    try:
        resp = requests.get('https://api.alternative.me/fng/?limit=1', timeout=10)
        resp.raise_for_status()
        entry = resp.json()['data'][0]
        return {
            'value': int(entry['value']),
            'label': entry['value_classification'],
            'timestamp': entry['timestamp'],
        }
    except Exception as e:
        print(f"  Warning: Fear & Greed fetch failed: {e}")
        return None


def generate_dashboard_json(history_df: pd.DataFrame) -> Dict[str, Any]:
    """Build the complete dashboard.json payload."""
    print("Calculating historical metrics...")
    historical_metrics = calculate_historical_metrics(history_df)

    print("Calculating current metrics...")
    current_metrics = calculate_current_metrics(history_df)

    assets_data: Dict[str, Any] = {}
    for asset in set(list(historical_metrics) + list(current_metrics)):
        assets_data[asset] = {}
        timeframes = set()
        if asset in historical_metrics:
            timeframes.update(historical_metrics[asset])
        if asset in current_metrics:
            timeframes.update(current_metrics[asset])

        for tf in timeframes:
            assets_data[asset][tf] = {}
            if asset in historical_metrics and tf in historical_metrics[asset]:
                assets_data[asset][tf]['historical'] = historical_metrics[asset][tf]['historical']
            if asset in current_metrics and tf in current_metrics[asset]:
                assets_data[asset][tf]['current'] = current_metrics[asset][tf]['current']

    # ── Multi-timeframe alignment badge ─────────────────────────────────────────
    _oversold_regimes  = {'Capitulation', 'Accumulation'}
    _extended_regimes  = {'Distribution', 'Mania'}
    for asset, tfs in assets_data.items():
        c1d = tfs.get('1d', {}).get('current')
        c1w = tfs.get('1w', {}).get('current')
        if c1d and c1w:
            r1d = c1d.get('regime')
            r1w = c1w.get('regime')
            if r1d and r1w and r1d != 'Unknown' and r1w != 'Unknown':
                if r1d in _oversold_regimes and r1w in _oversold_regimes:
                    alignment = 'aligned-bullish'
                elif r1d in _extended_regimes and r1w in _extended_regimes:
                    alignment = 'aligned-bearish'
                else:
                    alignment = 'diverging'
                c1d['alignment'] = alignment
                c1w['alignment'] = alignment

    # ── Relative Strength vs BTC (crypto daily) ──────────────────────────────────
    # Crypto assets (matches ASSET_CATEGORIES.crypto in dashboard.js)
    _CRYPTO_ASSETS = {
        'BTC', 'ETH', 'SOL', 'XLM', 'REZ', 'RSR', 'NEAR', 'RENDER', 'ONDO', 'ACH',
        'BNB', 'XRP', 'ADA', 'NIGHT', 'VTHO', 'LINK', 'NEO', 'GAS', 'DRIFT', 'SEI',
        'PEAQ', 'AEVO', 'EIGEN', 'W', 'WOO', 'JASMY', 'D2X', 'SCP',
    }
    _returns_30d = _compute_30d_returns(history_df)
    _btc_ret = _returns_30d.get('BTC', {}).get('1d')
    for asset in _CRYPTO_ASSETS:
        c1d = assets_data.get(asset, {}).get('1d', {}).get('current')
        if c1d is None:
            continue
        if _btc_ret and _btc_ret != 0:
            asset_ret = _returns_30d.get(asset, {}).get('1d')
            c1d['rs_vs_btc'] = float(asset_ret / _btc_ret) if asset_ret is not None else None
        else:
            c1d['rs_vs_btc'] = None

    # ── Funding Rate + Open Interest (crypto, both timeframes) ──────────────────
    print("Fetching Binance futures funding rates / open interest...")
    binance_futures = fetch_binance_futures()
    if binance_futures:
        print(f"  Binance futures: {len(binance_futures)} symbols received")
    for asset in _CRYPTO_ASSETS:
        bf = binance_futures.get(asset)
        for tf in ('1d', '1w'):
            c = assets_data.get(asset, {}).get(tf, {}).get('current')
            if c is None:
                continue
            c['funding_rate'] = bf['funding_rate'] if bf else None
            c['open_interest_usd'] = bf['open_interest_usd'] if bf else None

    print("Fetching BTC dominance...")
    btc_dominance = fetch_btc_dominance()
    if btc_dominance is not None:
        print(f"  BTC dominance: {btc_dominance:.1f}%")

    print("Calculating Altcoin Season Index...")
    altseason = calculate_altseason_index(history_df)
    if altseason:
        print(f"  Altseason: {altseason['score']} ({altseason['label']}) — {altseason['alts_outperforming']}/{altseason['total']} alts outperforming BTC")

    print("Fetching Fear & Greed Index...")
    fear_greed = fetch_fear_greed()
    if fear_greed:
        print(f"  Fear & Greed: {fear_greed['value']} ({fear_greed['label']})")

    dashboard = {
        'metadata': {
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'assets_count': int(history_df['Asset'].nunique()),
            'records_count': int(len(history_df)),
            'date_range': {
                'start': str(history_df['Date'].min()),
                'end': str(history_df['Date'].max()),
            },
        },
        'btc_dominance': btc_dominance,
        'altseason': altseason,
        'fear_greed': fear_greed,
        'assets': assets_data,
    }

    # H5: sanitise all NaN/inf before JSON serialisation
    return _sanitise(dashboard)


def generate_breadth_json(history_df: pd.DataFrame, n_days: int = 60) -> Dict[str, Any]:
    """
    Build breadth.json — daily count of portfolio (non-macro) assets per regime.
    Only uses daily (1d) timeframe. Covers the last n_days calendar days.
    Output: {"dates": [...], "capitulation": [...], "accumulation": [...], ...}
    """
    norm_series = history_df['Timeframe'].apply(
        lambda t: _norm_timeframe(str(t)) if pd.notna(t) else ''
    )
    df = history_df[(norm_series == '1d') & (~history_df['Asset'].isin(MACRO_ASSETS))].copy()
    df['regime_norm'] = df['ATR_Distance'].apply(
        lambda x: classify_regime(float(x)).lower() if pd.notna(x) else 'unknown'
    )
    df['Date'] = pd.to_datetime(df['Date'])
    grouped = df.groupby('Date')['regime_norm'].value_counts().unstack(fill_value=0)
    grouped = grouped.sort_index().tail(n_days)

    regimes = ['capitulation', 'accumulation', 'trend', 'distribution', 'mania']
    result: Dict[str, Any] = {
        'dates': [str(d)[:10] for d in grouped.index.tolist()],
    }
    for r in regimes:
        col = grouped[r] if r in grouped.columns else pd.Series([0] * len(grouped))
        result[r] = [int(v) for v in col.values]

    return _sanitise(result)


def generate_correlation_json(history_df: pd.DataFrame, lookback_days: int = 90) -> Dict[str, Any]:
    """
    Build correlation.json — rolling Pearson correlation matrix for 28 crypto assets.
    Uses daily (1d) closing prices over the last lookback_days calendar days.
    Output: {date, lookback_days, assets:[...], matrix:[[float|null]...]}
    """
    _CRYPTO_ASSETS_ORDERED = [
        'BTC', 'ETH', 'SOL', 'XLM', 'REZ', 'RSR', 'NEAR', 'RENDER', 'ONDO', 'ACH',
        'BNB', 'XRP', 'ADA', 'NIGHT', 'VTHO', 'LINK', 'NEO', 'GAS', 'DRIFT', 'SEI',
        'PEAQ', 'AEVO', 'EIGEN', 'W', 'WOO', 'JASMY', 'D2X', 'SCP',
    ]
    norm_series = history_df['Timeframe'].apply(
        lambda t: _norm_timeframe(str(t)) if pd.notna(t) else ''
    )
    df = history_df[
        (norm_series == '1d') & (history_df['Asset'].isin(_CRYPTO_ASSETS_ORDERED))
    ].copy()
    df['Date'] = pd.to_datetime(df['Date'])
    latest_date = df['Date'].max()
    cutoff = latest_date - pd.Timedelta(days=lookback_days)
    df = df[(df['Date'] >= cutoff) & (df['Date'] <= latest_date)]

    pivot = df.pivot_table(index='Date', columns='Asset', values='Price', aggfunc='last')
    # Reindex to fixed asset order; missing assets get all-NaN columns → null in output
    pivot = pivot.reindex(columns=_CRYPTO_ASSETS_ORDERED)
    # Only include assets that have at least 30 non-NaN rows
    valid_assets = [a for a in _CRYPTO_ASSETS_ORDERED if pivot[a].notna().sum() >= 30]
    pivot = pivot[valid_assets]

    corr = pivot.corr(method='pearson')
    matrix = [[None if pd.isna(v) else round(float(v), 4) for v in row] for row in corr.values]

    result: Dict[str, Any] = {
        'date': str(latest_date.date()),
        'lookback_days': lookback_days,
        'assets': valid_assets,
        'matrix': matrix,
    }
    return _sanitise(result)


def main():
    """Main execution function."""
    print("=" * 60)
    print("Metrics Calculation Script")
    print("=" * 60)
    print()

    if not os.path.exists(HISTORY_CSV_PATH):
        print(f"ERROR: {HISTORY_CSV_PATH} not found")
        print("Please run update_history.py first to generate history.csv")
        sys.exit(1)

    print(f"Loading {HISTORY_CSV_PATH}...")
    history_df = pd.read_csv(HISTORY_CSV_PATH)
    print(f"Loaded {len(history_df)} records")
    print(f"Assets: {history_df['Asset'].nunique()}")
    print(f"Date range: {history_df['Date'].min()} to {history_df['Date'].max()}")
    print()

    required_columns = ['Date', 'Asset', 'Price', 'EMA21', 'ATR', 'RSI', 'ATR_Distance', 'Timeframe']
    missing = [c for c in required_columns if c not in history_df.columns]
    if missing:
        print(f"ERROR: Missing required columns: {', '.join(missing)}")
        sys.exit(1)

    print("Generating dashboard.json...")
    dashboard = generate_dashboard_json(history_df)

    with open(DASHBOARD_JSON_PATH, 'w') as f:
        json.dump(dashboard, f, indent=2)
    print(f"✓ Saved dashboard.json to {DASHBOARD_JSON_PATH}")
    print()

    print("Generating chart_history.json (last 90 bars per asset/timeframe)...")
    chart_history = generate_chart_history(history_df, n_bars=90)

    with open(CHART_HISTORY_JSON_PATH, 'w') as f:
        json.dump(chart_history, f, separators=(',', ':'))  # compact — no indent
    print(f"✓ Saved chart_history.json to {CHART_HISTORY_JSON_PATH}")
    print()

    print("Generating breadth.json (daily regime counts)...")
    breadth_path = str(Path(HISTORY_CSV_PATH).parent / 'breadth.json')
    breadth = generate_breadth_json(history_df)
    with open(breadth_path, 'w') as f:
        json.dump(breadth, f, separators=(',', ':'))
    print(f"✓ Saved breadth.json to {breadth_path}")
    print()

    print("Generating correlation.json (90-day crypto correlation matrix)...")
    corr = generate_correlation_json(history_df)
    with open(CORRELATION_JSON_PATH, 'w') as f:
        json.dump(corr, f, separators=(',', ':'))
    print(f"✓ Saved correlation.json to {CORRELATION_JSON_PATH} ({len(corr['assets'])} assets)")
    print()

    print("=" * 60)
    print("Metrics calculation completed successfully")
    print("=" * 60)
    print(f"Assets processed: {dashboard['metadata']['assets_count']}")
    print(f"Total records: {dashboard['metadata']['records_count']}")
    print(f"Date range: {dashboard['metadata']['date_range']['start']} to {dashboard['metadata']['date_range']['end']}")
    print()


if __name__ == "__main__":
    main()
