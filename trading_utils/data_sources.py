"""
Data fetching from Binance (via CCXT) and Yahoo Finance.

Fix H1: yfinance requests 180 days of history so RSI Z-score has enough warm-up bars.
Fix M4: CCXT exchange object is created once at module level.
Fix M3: _with_retry wraps all network calls with exponential backoff.
"""

import time
import warnings
from datetime import datetime, timedelta

import ccxt
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore', category=FutureWarning, module='yfinance')
warnings.filterwarnings('ignore', category=FutureWarning, module='pandas')

from .config import ASSET_CONFIG, MANUAL_DATA

# Module-level exchange instance (M4)
_exchange = ccxt.binance({'enableRateLimit': True})


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
        ohlcv = _exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
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


def fetch_ohlcv_yahoo(symbol, timeframe, limit=100):
    """Fetch recent OHLCV bars from Yahoo Finance (180-day window for indicator warm-up)."""
    interval_map = {'1d': '1d', '1w': '1wk', '1M': '1mo'}
    interval = interval_map.get(timeframe, '1d')
    start = datetime.now() - timedelta(days=180)

    def _fetch():
        data = yf.download(symbol, start=start, interval=interval, progress=False)
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


def fetch_ohlcv(asset, timeframe, limit=100):
    """Dispatch fetch to the correct source for a given asset."""
    config = ASSET_CONFIG.get(asset)
    if not config:
        print(f"No config for asset: {asset}")
        return None

    source = config['source']
    symbol = config['symbol']

    if source == 'binance':
        return fetch_ohlcv_binance(symbol, timeframe, limit)
    if source == 'yahoo':
        return fetch_ohlcv_yahoo(symbol, timeframe, limit)
    if source == 'manual':
        return None  # Handled via get_manual_data
    print(f"Unknown data source: {source}")
    return None
