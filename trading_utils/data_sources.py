"""
Data fetching from Binance/CoinEx (via CCXT), Yahoo Finance, and GeckoTerminal.

Fix H1: yfinance requests 730 days of history so RSI Z-score has enough warm-up bars.
Fix M4: CCXT exchange objects are created once and cached at module level.
Fix M3: _with_retry wraps all network calls with exponential backoff.
"""

import time
import warnings
from datetime import datetime, timedelta

import ccxt
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings('ignore', category=FutureWarning, module='yfinance')
warnings.filterwarnings('ignore', category=FutureWarning, module='pandas')

from .config import ASSET_CONFIG, MANUAL_DATA

# Module-level exchange cache (M4) — keyed by exchange id
_exchanges: dict = {}


def _get_exchange(exchange_id: str):
    """Return a cached CCXT exchange instance, creating it on first use."""
    if exchange_id not in _exchanges:
        if exchange_id.startswith('_') or not hasattr(ccxt, exchange_id):
            raise ValueError(f"Unknown or invalid CCXT exchange: '{exchange_id}'")
        exchange_class = getattr(ccxt, exchange_id)
        _exchanges[exchange_id] = exchange_class({'enableRateLimit': True})
    return _exchanges[exchange_id]


def _with_retry(fn, *args, retries=3, backoff=5, **kwargs):
    """Call fn(*args, **kwargs) with initial attempt plus `retries` retries (up to `retries + 1` total attempts) using exponential backoff. With default `retries=3` it will attempt 4 times. The `retries` parameter counts only the additional retry attempts."""
    last_exc = None
    for attempt in range(retries + 1):
        try:
            result = fn(*args, **kwargs)
            if result is not None:
                return result
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    if last_exc:
        raise last_exc
    return None


def fetch_ohlcv_binance(symbol, timeframe, limit=100):
    """Fetch recent OHLCV bars from Binance."""
    def _fetch():
        ohlcv = _get_exchange('binance').fetch_ohlcv(symbol, timeframe, limit=limit)
        if not ohlcv:
            return None
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df

    try:
        return _with_retry(_fetch)
    except Exception as e:
        print(f"Error fetching {symbol} from Binance ({timeframe}): {e}")
        return None


def fetch_ohlcv_ccxt(exchange_id: str, symbol: str, timeframe: str, limit: int = 750):
    """Fetch recent OHLCV bars from any CCXT-supported exchange.

    Uses a 730-day window for daily bars and fetches up to `limit` candles
    (default 750) to provide enough history for indicator warm-up.

    Args:
        exchange_id: CCXT exchange id, e.g. 'coinex'
        symbol:      Market symbol, e.g. 'SCP/USDT'
        timeframe:   '1d' or '1w'
        limit:       Number of candles to fetch

    Returns a DataFrame indexed by UTC timestamp, sorted oldest-first.
    """
    exchange = _get_exchange(exchange_id)

    def _fetch():
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not ohlcv:
            return None
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df

    try:
        return _with_retry(_fetch)
    except Exception as e:
        print(f"Error fetching {symbol} from {exchange_id} ({timeframe}): {e}")
        return None


def fetch_ohlcv_yahoo(symbol, timeframe, limit=100):
    """Fetch recent OHLCV bars from Yahoo Finance (730-day window for indicator warm-up).

    730 days gives ~520 daily bars and ~104 weekly bars — enough for ATR14/EMA21/RSI14
    to fully converge with SMA-seeded initialisation, even for recently-listed assets.
    """
    interval_map = {'1d': '1d', '1w': '1wk', '1M': '1mo'}
    interval = interval_map.get(timeframe, '1d')
    start = datetime.now() - timedelta(days=730)

    def _fetch():
        data = yf.download(symbol, start=start, interval=interval, progress=False, auto_adjust=False)
        if data.empty:
            return None

        # yfinance >= 0.2 returns a (Price, Ticker) MultiIndex for single-ticker
        # downloads. Level 0 holds the price-field names ('Close', 'High', …).
        # droplevel(0) would wrongly discard those labels; get_level_values
        # extracts them explicitly regardless of level ordering.
        if isinstance(data.columns, pd.MultiIndex):
            price_level = 'Price' if 'Price' in data.columns.names else 0
            data.columns = data.columns.get_level_values(price_level)

        data = data.rename(columns={
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
        })
        data = data.reset_index()
        data = data.rename(columns={'Date': 'timestamp', 'Datetime': 'timestamp'})
        data.set_index('timestamp', inplace=True)
        return data

    try:
        result = _with_retry(_fetch)
        if result is None:
            print(f"No data returned for {symbol} ({timeframe})")
        return result
    except Exception as e:
        print(f"Error fetching {symbol} from Yahoo Finance ({timeframe}): {e}")
        return None


def get_manual_data(asset, timeframe):
    """Return a record dict for a manually configured asset."""
    if asset not in MANUAL_DATA or timeframe not in MANUAL_DATA[asset]:
        return None

    data = MANUAL_DATA[asset][timeframe]
    atr = data['atr']
    price, ema21 = data['price'], data['ema21']

    atr_distance = (price - ema21) / atr if atr else None
    pct_above_ema = ((price - ema21) / ema21) * 100
    # Simple normalisation: RSI Z-score proxy for manual data (no historical series)
    rsi_z_score = (data['rsi'] - 50) / 15

    return {
        'Date': datetime.now().strftime('%Y-%m-%d'),
        'Asset': asset,
        'Price': price,
        'EMA21': ema21,
        'ATR': atr,
        'RSI': data['rsi'],
        'RSI_Z_Score': rsi_z_score,
        'ATR_Distance': atr_distance,
        'Pct_Above_EMA': pct_above_ema,
        'Timeframe': timeframe,
    }


_GECKO_BASE = "https://api.geckoterminal.com/api/v2"
_GECKO_HEADERS = {"Accept": "application/json;version=20230302"}


def _fetch_gecko_daily(network: str, pool_address: str, limit: int = 1000) -> pd.DataFrame | None:
    """Fetch raw daily OHLCV from GeckoTerminal (aggregate=1 only supported on free tier)."""
    url = f"{_GECKO_BASE}/networks/{network}/pools/{pool_address}/ohlcv/day"
    params = {"aggregate": 1, "limit": limit, "currency": "usd", "token": "base"}

    def _fetch():
        resp = requests.get(url, headers=_GECKO_HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        ohlcv_list = resp.json()["data"]["attributes"]["ohlcv_list"]
        if not ohlcv_list:
            return None
        df = pd.DataFrame(ohlcv_list, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_localize(None)
        df = df.sort_values("timestamp").set_index("timestamp")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    try:
        return _with_retry(_fetch)
    except Exception as e:
        print(f"Error fetching daily OHLCV for pool {pool_address}: {e}")
        return None


def fetch_ohlcv_geckoterminal(network: str, pool_address: str, timeframe: str, limit: int = 1000):
    """Fetch OHLCV from GeckoTerminal for a DEX pool.

    GeckoTerminal free tier only supports aggregate=1 on the 'day' timeframe.
    Weekly candles are built by resampling daily data (week-ending Sunday,
    matching TradingView's weekly bar convention).

    Args:
        network:      GeckoTerminal network id, e.g. 'solana'
        pool_address: DEX pool/pair address
        timeframe:    '1d' or '1w'
        limit:        max daily candles to fetch (free tier: up to 1000)

    Returns a DataFrame with columns [open, high, low, close, volume]
    indexed by UTC timestamp, sorted oldest-first.
    """
    if timeframe not in ('1d', '1w'):
        print(f"Unsupported timeframe for GeckoTerminal: {timeframe}")
        return None

    df = _fetch_gecko_daily(network, pool_address, limit)
    if df is None or df.empty:
        print(f"No data for pool {pool_address} on {network}")
        return None

    if timeframe == '1w':
        # Resample to weekly (week-ending Sunday) — matches TradingView weekly bars
        df = df.resample('W').agg({
            'open':   'first',
            'high':   'max',
            'low':    'min',
            'close':  'last',
            'volume': 'sum',
        }).dropna(subset=['close'])

    return df


def fetch_ohlcv(asset, timeframe, limit=100):
    """Dispatch fetch to the correct source for a given asset."""
    config = ASSET_CONFIG.get(asset)
    if not config:
        print(f"No config for asset: {asset}")
        return None

    source = config['source']

    if source == 'binance':
        return fetch_ohlcv_binance(config['symbol'], timeframe, limit)
    if source == 'yahoo':
        return fetch_ohlcv_yahoo(config['symbol'], timeframe, limit)
    if source == 'ccxt':
        return fetch_ohlcv_ccxt(config['exchange'], config['symbol'], timeframe, limit)
    if source == 'geckoterminal':
        return fetch_ohlcv_geckoterminal(config['network'], config['pool'], timeframe)
    if source == 'manual':
        return None  # Handled via get_manual_data
    print(f"Unknown data source: {source}")
    return None
