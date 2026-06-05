#!/usr/bin/env python3
"""
Metrics Calculation Script
Calculates derived metrics from history.csv and generates dashboard.json.
"""

import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from trading_utils import (
    HISTORY_CSV_PATH, DASHBOARD_JSON_PATH, CHART_HISTORY_JSON_PATH, METADATA_JSON_PATH,
    MARKET_CAPS_JSON_PATH, BTC_SIGNALS_JSON_PATH,
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


def _fetch_bybit_futures() -> Optional[Dict[str, Any]]:
    """Fetch USDT perpetual funding rates and OI from Bybit (fallback for geo-blocked envs).

    Called automatically when Binance returns HTTP 451. Returns None on network
    failure so the caller can chain to the next fallback (CoinGecko).
    """
    _TRACKED = {
        'BTC', 'ETH', 'SOL', 'XLM', 'NEAR', 'BNB', 'XRP', 'ADA', 'LINK', 'NEO',
        'RENDER', 'SEI', 'DRIFT', 'EIGEN', 'W', 'WOO', 'JASMY', 'AEVO', 'GAS',
        'PEAQ', 'RSR', 'ACH', 'ONDO', 'VTHO', 'REZ',
    }
    try:
        resp = requests.get(
            'https://api.bybit.com/v5/market/tickers',
            params={'category': 'linear'},
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json()['result']['list']
    except Exception as e:
        print(f"  Warning: Bybit futures fallback fetch failed: {e}")
        return None  # signal caller to try next fallback

    result: Dict[str, Any] = {}
    for item in items:
        sym = item.get('symbol', '')
        if not sym.endswith('USDT') or '_' in sym:
            continue
        coin = sym[:-4]
        if coin not in _TRACKED:
            continue
        try:
            mark_price = float(item.get('markPrice') or item.get('lastPrice', 0))
            funding_rate = float(item['fundingRate']) * 100  # decimal → % per 8h
            oi_value = float(item.get('openInterestValue') or 0)
            result[coin] = {
                'funding_rate': funding_rate,
                'mark_price': mark_price,
                'open_interest_usd': oi_value if oi_value > 0 else None,
            }
        except (KeyError, ValueError, TypeError):
            pass

    print(f"  Bybit fallback: {len(result)} symbols received")
    return result


def _fetch_coingecko_futures() -> Dict[str, Any]:
    """Fetch perpetual funding rates from CoinGecko /api/v3/derivatives (no auth, no geo-block).

    CoinGecko proxies this data through their CDN so it works from GitHub Actions
    even when Binance (451) and Bybit (403) are both blocked. OI is not available
    via this endpoint, so open_interest_usd is always None.
    """
    _ID_MAP = {
        'bitcoin': 'BTC',
        'ethereum': 'ETH',
        'solana': 'SOL',
        'ripple': 'XRP',
        'cardano': 'ADA',
        'binancecoin': 'BNB',
        'chainlink': 'LINK',
        'stellar': 'XLM',
        'near': 'NEAR',
        'neo': 'NEO',
        'render-token': 'RENDER',
        'sei-network': 'SEI',
        'woo-network': 'WOO',
        'jasmy': 'JASMY',
        'aevo': 'AEVO',
        'drift-protocol': 'DRIFT',
        'eigenlayer': 'EIGEN',
        'wormhole': 'W',
        'gas': 'GAS',
        'reserve-rights-token': 'RSR',
        'alchemy-pay': 'ACH',
        'ondo-finance': 'ONDO',
        'vethor-token': 'VTHO',
        'rezolve-ai': 'REZ',
        'peaq-network': 'PEAQ',
    }
    try:
        resp = requests.get(
            'https://api.coingecko.com/api/v3/derivatives',
            timeout=20,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as e:
        print(f"  Warning: CoinGecko derivatives fallback failed: {e}")
        return {}

    # CoinGecko returns many exchanges/contracts per coin — average perpetuals per index_id
    rates: Dict[str, list] = defaultdict(list)
    for item in items:
        if item.get('contract_type') != 'perpetual':
            continue
        index_id = item.get('index_id', '')
        coin = _ID_MAP.get(index_id)
        if not coin:
            continue
        fr = item.get('funding_rate')
        if fr is not None:
            try:
                rates[coin].append(float(fr) * 100)  # decimal → % per 8h
            except (ValueError, TypeError):
                pass

    result: Dict[str, Any] = {}
    for coin, fr_list in rates.items():
        if fr_list:
            result[coin] = {
                'funding_rate': sum(fr_list) / len(fr_list),
                'open_interest_usd': None,
            }

    print(f"  CoinGecko derivatives fallback: {len(result)} symbols received")
    return result


def fetch_binance_futures() -> Dict[str, Any]:
    """Fetch funding rates and open interest from Binance USDT-M futures (free, no auth).

    Returns a dict keyed by coin symbol (e.g. 'BTC') with:
        {'funding_rate': float (% per 8h period), 'open_interest_usd': float|None}

    Falls back to Bybit when Binance is geo-blocked (HTTP 451 — common on
    GitHub Actions runners). Quarterly/delivery contracts (symbol contains '_')
    are excluded. Returns {} on complete failure.
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
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 451:
            print("  Binance geo-blocked (451) — trying Bybit...")
            bybit_data = _fetch_bybit_futures()
            if bybit_data:
                return bybit_data
            print("  Bybit also blocked — falling back to CoinGecko derivatives...")
            return _fetch_coingecko_futures()
        print(f"  Warning: Binance premiumIndex fetch failed: {e}")
        return {}
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


def fetch_hash_ribbons() -> Optional[Dict[str, Any]]:
    """Fetch Bitcoin hash ribbons from mempool.space (free, no auth).

    Computes 30DMA vs 60DMA of daily network hashrate (EH/s) and detects crosses.
    Signal: 'recovery' (bullish cross), 'bull', 'bear', 'capitulation' (bearish cross).
    """
    try:
        resp = requests.get('https://mempool.space/api/v1/mining/hashrate/6m', timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rates_raw = [r['avgHashrate'] for r in data.get('hashrates', []) if r.get('avgHashrate')]
        if len(rates_raw) < 61:
            return None
        rates_eh = [r / 1e18 for r in rates_raw]

        def _sma(vals: list, n: int) -> float:
            return sum(vals[-n:]) / n

        hr30 = _sma(rates_eh, 30)
        hr60 = _sma(rates_eh, 60)

        if len(rates_eh) >= 62:
            prev30 = sum(rates_eh[-31:-1]) / 30
            prev60 = sum(rates_eh[-61:-1]) / 60
            if hr30 > hr60 and prev30 <= prev60:
                signal = 'recovery'
            elif hr30 < hr60 and prev30 >= prev60:
                signal = 'capitulation'
            elif hr30 > hr60:
                signal = 'bull'
            else:
                signal = 'bear'
        else:
            signal = 'bull' if hr30 > hr60 else 'bear'

        return {
            'hashrate_30d_eh': round(hr30, 2),
            'hashrate_60d_eh': round(hr60, 2),
            'signal': signal,
        }
    except Exception as e:
        print(f"  Warning: Hash ribbons fetch failed: {e}")
        return None


def fetch_stablecoin_trend() -> Optional[Dict[str, Any]]:
    """Fetch USDT + USDC combined supply trend and stablecoin dominance via CoinGecko.

    Returns supply totals, 30-day change %, dominance %, and a directional signal.
    Signal: 'expanding' (supply growing > 2%) | 'contracting' (< -2%) | 'flat'.
    """
    try:
        def _mcaps(coin_id: str) -> list:
            r = requests.get(
                f'https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart',
                params={'vs_currency': 'usd', 'days': '90', 'interval': 'daily'},
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get('market_caps', [])

        usdt_caps = _mcaps('tether')
        usdc_caps = _mcaps('usd-coin')
        if not usdt_caps or not usdc_caps:
            return None

        usdt_now = usdt_caps[-1][1]
        usdc_now = usdc_caps[-1][1]
        combined_now = usdt_now + usdc_now

        idx30 = max(len(usdt_caps) - 31, 0)
        usdt_30d = usdt_caps[idx30][1]
        usdc_30d = usdc_caps[min(idx30, len(usdc_caps) - 1)][1]
        combined_30d = usdt_30d + usdc_30d
        change_pct = (combined_now - combined_30d) / combined_30d * 100 if combined_30d > 0 else None

        global_resp = requests.get('https://api.coingecko.com/api/v3/global', timeout=10)
        global_resp.raise_for_status()
        total_mcap = global_resp.json()['data']['total_market_cap'].get('usd', 0)
        dominance_pct = combined_now / total_mcap * 100 if total_mcap > 0 else None

        if change_pct is not None:
            signal: Optional[str] = 'expanding' if change_pct > 2 else ('contracting' if change_pct < -2 else 'flat')
        else:
            signal = None

        return {
            'usdt_supply_usd': usdt_now,
            'usdc_supply_usd': usdc_now,
            'combined_supply_usd': combined_now,
            'change_30d_pct': round(change_pct, 2) if change_pct is not None else None,
            'dominance_pct': round(dominance_pct, 2) if dominance_pct is not None else None,
            'signal': signal,
        }
    except Exception as e:
        print(f"  Warning: Stablecoin trend fetch failed: {e}")
        return None


def fetch_etf_flows() -> Optional[Dict[str, Any]]:
    """Fetch US spot BTC ETF total daily net flows from SoSoValue.

    Uses /etfs/summary-history with symbol=BTC, country_code=US.
    Returns None when SOSOVALUE_API_KEY env var is not set or fetch fails.
    """
    api_key = os.environ.get('SOSOVALUE_API_KEY')
    if not api_key:
        return None
    try:
        resp = requests.get(
            'https://openapi.sosovalue.com/openapi/v1/etfs/summary-history',
            params={'symbol': 'BTC', 'country_code': 'US', 'limit': 7},
            headers={'x-soso-api-key': api_key},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        # Handle both plain array and {"data": [...]} wrapped response
        rows = payload.get('data', payload) if isinstance(payload, dict) else payload
        if not rows:
            return None
        # Rows are in reverse chronological order (latest first)
        latest = rows[0]
        net_inflow = float(latest['total_net_inflow'])
        date_str   = latest['date']
        flow_7d    = sum(float(r['total_net_inflow']) for r in rows)
        net_assets = float(latest['total_net_assets']) if latest.get('total_net_assets') else None
        cum_inflow = float(latest['cum_net_inflow']) if latest.get('cum_net_inflow') else None

        if net_inflow > 500_000_000:
            signal: str = 'accumulate'
        elif net_inflow < -200_000_000:
            signal = 'distribute'
        else:
            signal = 'neutral'

        print(f"  SoSoValue ETF flows: {net_inflow/1e9:+.2f}B USD (latest {date_str}), "
              f"7d sum: {flow_7d/1e9:+.2f}B, signal: {signal}")
        return {
            'date': date_str,
            'net_inflow_usd': net_inflow,
            'flow_7d_usd': flow_7d,
            'total_net_assets_usd': net_assets,
            'cum_net_inflow_usd': cum_inflow,
            'signal': signal,
        }
    except Exception as e:
        print(f"  Warning: SoSoValue ETF flows fetch failed: {e}")
        return None


def fetch_global_m2() -> Optional[Dict[str, Any]]:
    """Fetch US M2 weekly money supply from FRED (WM2NS series).

    The 12-week lag: M2 from 12 weeks ago predicts BTC direction today.
    Returns None when FRED_API_KEY env var is not set or the fetch fails.
    """
    api_key = os.environ.get('FRED_API_KEY')
    if not api_key:
        return None
    try:
        resp = requests.get(
            'https://api.stlouisfed.org/fred/series/observations',
            params={
                'series_id': 'WM2NS',
                'api_key': api_key,
                'file_type': 'json',
                'sort_order': 'desc',
                'limit': 30,
            },
            timeout=15,
        )
        resp.raise_for_status()
        obs = [o for o in resp.json()['observations'] if o['value'] != '.']
        if len(obs) < 25:
            return None
        m2_now  = float(obs[0]['value'])
        m2_12w  = float(obs[12]['value'])
        m2_24w  = float(obs[24]['value'])
        lagged_change_pct  = (m2_12w - m2_24w) / m2_24w * 100
        current_change_pct = (m2_now - m2_12w) / m2_12w * 100
        if lagged_change_pct > 1.5:
            signal: str = 'accumulate'
        elif lagged_change_pct < -0.5:
            signal = 'distribute'
        else:
            signal = 'neutral'
        print(f"  FRED M2: {m2_now:.1f}B USD, lagged change {lagged_change_pct:.2f}%, signal: {signal}")
        return {
            'm2_billion_usd': round(m2_now, 1),
            'm2_12w_lagged_change_pct': round(lagged_change_pct, 2),
            'm2_current_change_pct': round(current_change_pct, 2),
            'signal': signal,
        }
    except Exception as e:
        print(f"  Warning: FRED M2 fetch failed: {e}")
        return None


def fetch_puell_multiple(btc_prices: pd.Series) -> Optional[Dict[str, Any]]:
    """Compute Puell Multiple from mempool.space block rewards + historical BTC prices.

    Puell Multiple = today's miner revenue (USD) / 365-day MA of daily miner revenue.
    Block rewards (subsidy + fees) come from mempool.space /api/v1/mining/blocks/rewards/2y
    (free, no auth). BTC prices come from history.csv via btc_prices.

    Signal thresholds (empirically calibrated to BTC cycle data):
      < 0.6  → accumulate  (deep miner stress / capitulation)
      0.6–3.0 → neutral
      > 3.0  → distribute  (elevated miner profitability / late cycle)
    """
    try:
        resp = requests.get(
            'https://mempool.space/api/v1/mining/blocks/rewards/2y',
            timeout=15,
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows or len(rows) < 60:
            return None

        records = []
        for row in rows:
            ts = row.get('timestamp')
            # mempool.space uses camelCase; guard against both variants
            avg_r = row.get('avgRewards', row.get('avg_rewards'))
            avg_f = row.get('avgFees', row.get('avg_fees', 0))
            if ts and avg_r is not None:
                date = pd.Timestamp(ts, unit='s').normalize()
                # avgRewards/avgFees are sats per block; ~144 blocks/day
                daily_btc = (float(avg_r) + float(avg_f)) / 1e8 * 144
                records.append({'date': date, 'daily_btc': daily_btc})

        if not records:
            return None

        mpool_df = pd.DataFrame(records).set_index('date').sort_index()

        prices = btc_prices.copy()
        prices.index = pd.to_datetime(prices.index).normalize()
        prices.name = 'price'

        joined = mpool_df.join(prices, how='inner').dropna()
        if len(joined) < 30:
            return None

        joined['revenue_usd'] = joined['daily_btc'] * joined['price']
        ma365 = joined['revenue_usd'].rolling(365, min_periods=60).mean()

        if ma365.empty or pd.isna(ma365.iloc[-1]):
            return None

        current_revenue = float(joined['revenue_usd'].iloc[-1])
        ma_value = float(ma365.iloc[-1])
        puell = current_revenue / ma_value if ma_value > 0 else None
        if puell is None:
            return None

        if puell < 0.6:
            signal = 'accumulate'
        elif puell > 3.0:
            signal = 'distribute'
        else:
            signal = 'neutral'

        print(f"  Puell Multiple: {puell:.3f} (rev ${current_revenue/1e6:.1f}M/day, "
              f"365d MA ${ma_value/1e6:.1f}M), signal: {signal}")
        return {
            'puell_multiple': round(puell, 3),
            'daily_revenue_usd': round(current_revenue),
            'ma_365d_usd': round(ma_value),
            'signal': signal,
        }
    except Exception as e:
        print(f"  Warning: Puell Multiple fetch failed: {e}")
        return None


def fetch_bgeometrics_onchain() -> Optional[Dict[str, Any]]:
    """Fetch MVRV Z-Score, NUPL, SOPR from BGeometrics free API (no auth, 15 req/day)."""
    base = 'https://api.bgeometrics.com/v1'
    token = os.environ.get('BGEOMETRICS_API_KEY')
    headers = {'Authorization': f'Bearer {token}'} if token else {}

    def _fetch(endpoint):
        r = requests.get(f'{base}/{endpoint}/', params={'limit': 365},
                         headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()

    try:
        mvrv_data = _fetch('mvrv')
        nupl_data  = _fetch('nupl')
        sopr_data  = _fetch('sopr')
    except Exception as e:
        print(f'  Warning: BGeometrics fetch failed: {e}')
        return None

    def _latest(payload):
        rows = payload.get('data') or payload.get('values') or []
        if not rows:
            return None
        row = rows[-1]
        val = row[1] if isinstance(row, (list, tuple)) else row.get('value') or row.get('v')
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    mvrv_z = _latest(mvrv_data)
    nupl    = _latest(nupl_data)
    sopr    = _latest(sopr_data)

    if mvrv_z is None and nupl is None and sopr is None:
        return None

    sig_mvrv = 'accumulate' if (mvrv_z or 0) < 0 else ('distribute' if (mvrv_z or 0) >= 6 else 'neutral')
    sig_nupl = ('accumulate' if (nupl or 0) < 0 else ('distribute' if (nupl or 0) >= 0.5 else 'neutral')) if nupl is not None else None
    sig_sopr = ('accumulate' if (sopr or 0) < 0.98 else ('distribute' if (sopr or 0) > 1.05 else 'neutral')) if sopr is not None else None

    print(f'  BGeometrics: MVRV Z={mvrv_z}, NUPL={nupl}, SOPR={sopr}')
    return {
        'mvrv_z_score':  round(mvrv_z, 2) if mvrv_z is not None else None,
        'nupl':          round(nupl, 4)   if nupl   is not None else None,
        'sopr':          round(sopr, 4)   if sopr   is not None else None,
        'signal_mvrv_z': sig_mvrv,
        'signal_nupl':   sig_nupl,
        'signal_sopr':   sig_sopr,
    }


def fetch_bitbo_onchain() -> Optional[Dict[str, Any]]:
    """Fetch MVRV Z-Score + NUPL from Bitbo.io (free API key, 150k req/month).

    Used as fallback when BGeometrics is unavailable and BITBO_API_KEY is set.
    """
    key = os.environ.get('BITBO_API_KEY')
    if not key:
        return None
    base = 'https://charts.bitbo.io/api/v1'
    try:
        mz = requests.get(f'{base}/mvrv-z/', params={'api_key': key, 'latest': 'true'}, timeout=15)
        mz.raise_for_status()
        nu = requests.get(f'{base}/nupl-ratio/', params={'api_key': key, 'latest': 'true'}, timeout=15)
        nu.raise_for_status()
    except Exception as e:
        print(f'  Warning: Bitbo fallback failed: {e}')
        return None

    def _latest_bitbo(resp):
        rows = resp.json().get('data', [])
        if not rows:
            return None
        try:
            return float(rows[-1][1])
        except (IndexError, TypeError, ValueError):
            return None

    mvrv_z = _latest_bitbo(mz)
    nupl   = _latest_bitbo(nu)
    if mvrv_z is None:
        return None

    sig_mvrv = 'accumulate' if mvrv_z < 0 else ('distribute' if mvrv_z >= 6 else 'neutral')
    sig_nupl = ('accumulate' if nupl < 0 else ('distribute' if nupl >= 0.5 else 'neutral')) if nupl is not None else None

    print(f'  Bitbo fallback: MVRV Z={mvrv_z}, NUPL={nupl}')
    return {
        'mvrv_z_score':  round(mvrv_z, 2),
        'nupl':          round(nupl, 4) if nupl is not None else None,
        'sopr':          None,
        'signal_mvrv_z': sig_mvrv,
        'signal_nupl':   sig_nupl,
        'signal_sopr':   None,
    }


def fetch_blockchair_cdd() -> Optional[Dict[str, Any]]:
    """Fetch 90-day daily CDD from Blockchair (free, no key, 1440 req/day).

    Uses the blocks aggregation endpoint to get sum(cdd_total) per day.
    Signal: declining trend (ratio < 0.5) → accumulate (HODLers holding);
            accelerating (ratio > 1.5) → distribute (old coins moving).
    """
    key = os.environ.get('BLOCKCHAIR_API_KEY')
    params: Dict[str, Any] = {'a': 'date,sum(cdd_total)', 's': 'date(desc)', 'limit': 90}
    if key:
        params['key'] = key
    try:
        r = requests.get('https://api.blockchair.com/bitcoin/blocks',
                         params=params, timeout=15)
        r.raise_for_status()
        rows = r.json().get('data', [])
    except Exception as e:
        print(f'  Warning: Blockchair CDD fetch failed: {e}')
        return None

    if not rows:
        return None

    values = []
    for row in rows:
        v = row.get('sum(cdd_total)')
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            pass

    if len(values) < 10:
        return None

    cdd_latest = values[0]
    cdd_90d_avg = sum(values) / len(values)
    trend_ratio = cdd_latest / cdd_90d_avg if cdd_90d_avg else None

    if trend_ratio is None:
        sig: Optional[str] = None
    elif trend_ratio < 0.5:
        sig = 'accumulate'
    elif trend_ratio > 1.5:
        sig = 'distribute'
    else:
        sig = 'neutral'

    print(f'  Blockchair CDD: latest={cdd_latest:.0f}, 90d_avg={cdd_90d_avg:.0f}, ratio={trend_ratio:.2f}')
    return {
        'cdd_latest':         round(cdd_latest),
        'cdd_90d_avg':        round(cdd_90d_avg),
        'cdd_90d_change_pct': round((trend_ratio - 1) * 100, 1) if trend_ratio is not None else None,
        'signal_cvdd':        sig,
    }


def generate_btc_signals_json(history_df: pd.DataFrame, dashboard: Dict[str, Any]) -> Dict[str, Any]:
    """Build btc_signals.json — BTC cycle indicator confluence page data.

    Computes price-based signals from history_df (price structure, VP, RSI, ATR regime)
    and makes additional API calls for market data: hash ribbons and Puell Multiple
    (mempool.space), stablecoin supply (CoinGecko), global M2 when FRED_API_KEY is set
    (FRED), ETF flows when SOSOVALUE_API_KEY is set (SoSoValue), and on-chain metrics
    (Coinmetrics Community API — free, no key).
    """
    btc_asset = dashboard.get('assets', {}).get('BTC', {})
    d_cur: dict = btc_asset.get('1d', {}).get('current', {})
    w_cur: dict = btc_asset.get('1w', {}).get('current', {})
    price = d_cur.get('price')

    norm_series = history_df['Timeframe'].apply(
        lambda t: _norm_timeframe(str(t)) if pd.notna(t) else ''
    )
    btc_daily = (
        history_df[(history_df['Asset'] == 'BTC') & (norm_series == '1d')]
        .sort_values('Date', ascending=True)
        .dropna(subset=['Price'])
    )
    btc_weekly = (
        history_df[(history_df['Asset'] == 'BTC') & (norm_series == '1w')]
        .sort_values('Date', ascending=True)
        .dropna(subset=['Price'])
    )

    # 200WMA / 200DMA
    ma200w = float(btc_weekly['Price'].iloc[-200:].mean()) if len(btc_weekly) >= 200 else None
    ma200d = float(btc_daily['Price'].iloc[-200:].mean()) if len(btc_daily) >= 200 else None
    pct_above_200w = round((price - ma200w) / ma200w * 100, 1) if price and ma200w else None
    pct_above_200d = round((price - ma200d) / ma200d * 100, 1) if price and ma200d else None

    # Pi Cycle Top: 111DMA vs 350DMA×2
    ma111d = float(btc_daily['Price'].iloc[-111:].mean()) if len(btc_daily) >= 111 else None
    ma350d = float(btc_daily['Price'].iloc[-350:].mean()) if len(btc_daily) >= 350 else None
    pi_350d_2x = ma350d * 2 if ma350d else None
    pi_gap_pct = round((ma111d - pi_350d_2x) / pi_350d_2x * 100, 1) if ma111d and pi_350d_2x else None

    # Pull from already-computed dashboard data
    rsi_d = d_cur.get('rsi')
    rsi_w = w_cur.get('rsi')
    atr_dist = d_cur.get('atr_distance')
    regime = d_cur.get('regime')
    vp_pos = d_cur.get('vp_position')
    fr = d_cur.get('funding_rate')
    oi = d_cur.get('open_interest_usd')
    fear_greed = dashboard.get('fear_greed')
    btc_dominance = dashboard.get('btc_dominance')
    altseason = dashboard.get('altseason')

    # Signal helpers
    def _sig_200w(p, ma):
        if p is None or ma is None: return 'neutral'
        return 'accumulate' if p < ma else ('distribute' if p > ma * 3 else 'neutral')

    def _sig_200d(p, ma):
        if p is None or ma is None: return 'neutral'
        return 'accumulate' if p < ma else ('distribute' if p > ma * 1.5 else 'neutral')

    def _sig_pi(gap):
        if gap is None: return 'neutral'
        return 'accumulate' if gap > 30 else ('distribute' if gap <= 5 else 'neutral')

    def _sig_rsi(rsi):
        if rsi is None: return 'neutral'
        return 'accumulate' if rsi < 40 else ('distribute' if rsi > 70 else 'neutral')

    def _sig_regime(r):
        if r in ('Capitulation', 'Accumulation'): return 'accumulate'
        if r in ('Distribution', 'Mania'): return 'distribute'
        return 'neutral'

    def _sig_vp(pos):
        if pos == 'below_val': return 'accumulate'
        if pos == 'above_vah': return 'distribute'
        return 'neutral'

    def _sig_fg(fg):
        if fg is None: return None
        v = fg.get('value', 50)
        return 'accumulate' if v < 25 else ('distribute' if v > 75 else 'neutral')

    def _sig_fr(rate):
        if rate is None: return None
        return 'accumulate' if rate < -0.01 else ('distribute' if rate > 0.1 else 'neutral')

    def _sig_alts(alts):
        if alts is None: return None
        s = alts.get('score', 50)
        return 'accumulate' if s < 25 else ('distribute' if s > 75 else 'neutral')

    def _sig_hash(data):
        if not data or data.get('signal') is None: return None
        return 'accumulate' if data['signal'] == 'recovery' else 'neutral'

    def _sig_stable(data):
        if not data or data.get('signal') is None: return None
        return 'accumulate' if data['signal'] == 'expanding' else 'neutral'

    def _sig_etf(data):
        if not data or data.get('signal') is None: return None
        return data['signal']

    # Fetch new Tier-3 data
    print("  Fetching hash ribbons (mempool.space)...")
    hash_data = fetch_hash_ribbons()
    print("  Fetching Puell Multiple (mempool.space rewards + history prices)...")
    btc_price_series = btc_daily.set_index('Date')['Price']
    puell_data = fetch_puell_multiple(btc_price_series)
    print("  Fetching stablecoin supply trend (CoinGecko)...")
    stable_data = fetch_stablecoin_trend()
    print("  Fetching Global M2 (FRED WM2NS)...")
    m2_data = fetch_global_m2()
    print("  Fetching ETF net flows (SoSoValue)...")
    etf_data = fetch_etf_flows()
    print("  Fetching on-chain metrics (BGeometrics primary, Bitbo fallback)...")
    onchain_data = fetch_bgeometrics_onchain() or fetch_bitbo_onchain()
    print("  Fetching CDD (Blockchair free tier)...")
    cdd_data = fetch_blockchair_cdd()

    sig_200w = _sig_200w(price, ma200w)
    sig_200d = _sig_200d(price, ma200d)
    sig_pi = _sig_pi(pi_gap_pct)
    sig_rsi_d = _sig_rsi(rsi_d)
    sig_rsi_w = _sig_rsi(rsi_w)
    sig_atr = _sig_regime(regime)
    sig_vp = _sig_vp(vp_pos)
    sig_fg = _sig_fg(fear_greed)
    sig_fr = _sig_fr(fr)
    sig_oi = 'neutral' if oi is not None else None
    sig_btcd = 'neutral' if btc_dominance is not None else None
    sig_alts = _sig_alts(altseason)
    sig_hash = _sig_hash(hash_data)
    sig_puell = puell_data['signal'] if puell_data else None
    sig_stable = _sig_stable(stable_data)
    sig_m2 = m2_data['signal'] if m2_data else None
    sig_etf = _sig_etf(etf_data)
    sig_mvrv_z = onchain_data['signal_mvrv_z'] if onchain_data else None
    sig_nupl   = onchain_data['signal_nupl']   if onchain_data else None
    sig_sopr   = onchain_data['signal_sopr']   if onchain_data else None
    sig_cvdd   = cdd_data['signal_cvdd']       if cdd_data    else None

    all_sigs = [
        sig_200w, sig_200d, sig_pi, sig_rsi_d, sig_rsi_w, sig_atr, sig_vp,
        sig_fg, sig_fr, sig_alts, sig_hash, sig_stable,
    ]
    if sig_puell is not None:
        all_sigs.append(sig_puell)
    if sig_m2 is not None:
        all_sigs.append(sig_m2)
    if sig_etf is not None:
        all_sigs.append(sig_etf)
    for sig in (sig_mvrv_z, sig_nupl, sig_sopr, sig_cvdd):
        if sig is not None:
            all_sigs.append(sig)
    active = [s for s in all_sigs if s is not None]
    acc_count = active.count('accumulate')
    dist_count = active.count('distribute')
    neut_count = active.count('neutral')

    if acc_count > dist_count:
        phase = 'Accumulation'
        strength = 'strong' if acc_count >= 7 else ('moderate' if acc_count >= 5 else 'weak')
    elif dist_count > acc_count:
        phase = 'Distribution'
        strength = 'strong' if dist_count >= 7 else ('moderate' if dist_count >= 5 else 'weak')
    else:
        phase = 'Neutral'
        strength = 'mixed' if active else 'insufficient data'

    result: Dict[str, Any] = {
        'date': str(datetime.now(timezone.utc).date()),
        'price': price,
        'price_indicators': {
            'ma200w': round(ma200w, 2) if ma200w else None,
            'pct_above_200w': pct_above_200w,
            'signal_200w': sig_200w,
            'ma200d': round(ma200d, 2) if ma200d else None,
            'pct_above_200d': pct_above_200d,
            'signal_200d': sig_200d,
            'pi_cycle_111d': round(ma111d, 2) if ma111d else None,
            'pi_cycle_350d_2x': round(pi_350d_2x, 2) if pi_350d_2x else None,
            'pi_cycle_gap_pct': pi_gap_pct,
            'signal_pi_cycle': sig_pi,
            'rsi_daily': rsi_d,
            'signal_rsi_d': sig_rsi_d,
            'rsi_weekly': rsi_w,
            'signal_rsi_w': sig_rsi_w,
            'atr_distance': atr_dist,
            'regime': regime,
            'signal_atr': sig_atr,
            'vp_position': vp_pos,
            'signal_vp': sig_vp,
        },
        'sentiment': {
            'fear_greed': fear_greed,
            'signal_fear_greed': sig_fg,
            'funding_rate': fr,
            'signal_funding': sig_fr,
            'open_interest_usd': oi,
            'signal_oi': sig_oi,
            'etf_flows': etf_data,
            'signal_etf': sig_etf,
        },
        'market_structure': {
            'btc_dominance': btc_dominance,
            'signal_btcd': sig_btcd,
            'altseason': altseason,
            'signal_alts': sig_alts,
        },
        'mining': {
            **(hash_data or {'hashrate_30d_eh': None, 'hashrate_60d_eh': None, 'signal': None}),
            'puell_multiple': puell_data['puell_multiple'] if puell_data else None,
            'puell_daily_revenue_usd': puell_data['daily_revenue_usd'] if puell_data else None,
            'puell_ma_365d_usd': puell_data['ma_365d_usd'] if puell_data else None,
            'signal_puell': sig_puell,
        },
        'liquidity': {
            **(stable_data or {
                'usdt_supply_usd': None, 'usdc_supply_usd': None,
                'combined_supply_usd': None, 'change_30d_pct': None,
                'dominance_pct': None, 'signal': None,
            }),
            'global_m2_billion_usd': m2_data['m2_billion_usd'] if m2_data else None,
            'm2_12w_lagged_change_pct': m2_data['m2_12w_lagged_change_pct'] if m2_data else None,
            'm2_current_change_pct': m2_data['m2_current_change_pct'] if m2_data else None,
            'signal_global_m2': sig_m2,
        },
        'on_chain': {
            'mvrv_z_score':       (onchain_data or {}).get('mvrv_z_score'),
            'nupl':               (onchain_data or {}).get('nupl'),
            'sopr':               (onchain_data or {}).get('sopr'),
            'signal_mvrv_z':      (onchain_data or {}).get('signal_mvrv_z'),
            'signal_nupl':        (onchain_data or {}).get('signal_nupl'),
            'signal_sopr':        (onchain_data or {}).get('signal_sopr'),
            'cdd_latest':         (cdd_data or {}).get('cdd_latest'),
            'cdd_90d_avg':        (cdd_data or {}).get('cdd_90d_avg'),
            'cdd_90d_change_pct': (cdd_data or {}).get('cdd_90d_change_pct'),
            'signal_cvdd':        (cdd_data or {}).get('signal_cvdd'),
        },
        'confluence': {
            'accumulate_count': acc_count,
            'distribute_count': dist_count,
            'neutral_count': neut_count,
            'phase': phase,
            'strength': strength,
        },
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

    print("Generating btc_signals.json (BTC cycle indicators)...")
    btc_signals = generate_btc_signals_json(history_df, dashboard)
    with open(BTC_SIGNALS_JSON_PATH, 'w') as f:
        json.dump(btc_signals, f, separators=(',', ':'))
    conf = btc_signals['confluence']
    print(f"✓ Saved btc_signals.json — phase: {conf['phase']} ({conf['strength']}), "
          f"acc={conf['accumulate_count']} dist={conf['distribute_count']} neut={conf['neutral_count']}")
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
