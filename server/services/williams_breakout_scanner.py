"""
Larry Williams Volatility Breakout — live scanner.

Mirrors the structure of services.rsi_scanner.RSIScanner but on the daily
timeframe. Each scan:
  1. For every watched symbol, pull the last ~250 daily bars from Alpaca.
  2. Compute previous day's range and today's breakout trigger.
  3. Pull the latest intraday quote/bar and check if today's high already
     exceeded the long trigger (or low broke the short trigger).
  4. If a fresh breakout is detected, emit a 'buy' (or 'sell' for shorts)
     signal and route it through OrderManager.execute_webhook_order.
  5. Submit a stop-loss alongside the entry via Alpaca, and rely on the
     auto-loop / EOD close hook to flatten on the close.

The scanner is intentionally idempotent per symbol per day: once it has
fired, it won't re-enter the same symbol until the next session.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, time as dtime
from typing import Optional

from services.alpaca_client import AlpacaClient
from services.order_manager import OrderManager
from services.williams_breakout import WilliamsParams, add_signal_columns

logger = logging.getLogger(__name__)


class WilliamsBreakoutScanner:
    DEFAULT_SYMBOLS = ['SPY', 'QQQ', 'IWM', 'AAPL', 'MSFT', 'NVDA', 'META', 'TSLA']

    def __init__(self, symbols: Optional[list[str]] = None,
                 params: Optional[WilliamsParams] = None):
        self.alpaca = AlpacaClient()
        self.order_manager = OrderManager()
        self.symbols = list(symbols) if symbols else list(self.DEFAULT_SYMBOLS)
        self.params = params or WilliamsParams()

        # Per-symbol per-session state to make signals idempotent.
        # key: symbol -> {'date': date, 'fired': bool, 'last_signal': str}
        self._session_state: dict[str, dict] = {}

    # -- settings --------------------------------------------------------

    def update_settings(self, settings: dict) -> None:
        if 'symbols' in settings and isinstance(settings['symbols'], list):
            self.symbols = [s.upper() for s in settings['symbols'] if s]
        # Param updates: build a new dict from current params and overlay anything provided.
        p = self.params
        for f in ('k', 'stop_mult', 'sma_len', 'atr_len', 'atr_avg_len',
                  'commission_per_trade', 'slippage_bps'):
            if f in settings:
                setattr(p, f, type(getattr(p, f))(settings[f]))
        for f in ('use_trend_filter', 'use_vol_filter', 'allow_shorts'):
            if f in settings:
                setattr(p, f, bool(settings[f]))
        logger.info(f"Williams scanner settings updated: {p.as_dict()} symbols={self.symbols}")

    # -- data ------------------------------------------------------------

    def _get_daily_history(self, symbol: str):
        """Pull ~1 year of daily bars from Alpaca and return a pandas DataFrame."""
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            import pandas as pd

            # Pull enough history to satisfy the 200-day SMA + 50-day ATR baseline.
            end = datetime.utcnow()
            start = end - timedelta(days=400)
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
                feed='sip',
            )
            bars = self.alpaca.data_client.get_stock_bars(req)
            if symbol not in bars.data:
                return None
            rows = []
            for b in bars.data[symbol]:
                rows.append({
                    'date': b.timestamp,
                    'Open': float(b.open),
                    'High': float(b.high),
                    'Low': float(b.low),
                    'Close': float(b.close),
                    'Volume': float(b.volume),
                })
            df = pd.DataFrame(rows).set_index('date').sort_index()
            return df
        except Exception as e:
            logger.error(f"Williams scanner: history fetch failed for {symbol}: {e}")
            return None

    def _get_today_intraday(self, symbol: str):
        """Return today's running (open, high, low, last) so far, via 1-minute bars."""
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            end = datetime.utcnow()
            start = end - timedelta(hours=12)  # well over a session
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Minute,
                start=start,
                end=end,
                feed='sip',
            )
            bars = self.alpaca.data_client.get_stock_bars(req)
            if symbol not in bars.data or not bars.data[symbol]:
                return None
            today = datetime.utcnow().date()
            todays = [b for b in bars.data[symbol] if b.timestamp.date() == today]
            if not todays:
                return None
            return {
                'open': float(todays[0].open),
                'high': max(float(b.high) for b in todays),
                'low': min(float(b.low) for b in todays),
                'last': float(todays[-1].close),
                'as_of': todays[-1].timestamp,
            }
        except Exception as e:
            logger.error(f"Williams scanner: intraday fetch failed for {symbol}: {e}")
            return None

    # -- signal logic ----------------------------------------------------

    def check_signal(self, symbol: str) -> Optional[dict]:
        df = self._get_daily_history(symbol)
        if df is None or len(df) < max(self.params.sma_len, self.params.atr_len * 2):
            logger.warning(f"{symbol}: insufficient daily history for Williams setup")
            return None

        signed = add_signal_columns(df, self.params)
        today_intraday = self._get_today_intraday(symbol)

        # Yesterday's row holds prev_range and the trend/vol filter results.
        prev_row = signed.iloc[-1]
        prev_range = float(prev_row['High'] - prev_row['Low'])
        if prev_range <= 0:
            return None

        # If we have a live intraday quote, use it; otherwise fall back to the
        # most recent daily bar (i.e. assume "today" already has full data).
        if today_intraday is not None:
            today_open = today_intraday['open']
            today_high = today_intraday['high']
            today_low = today_intraday['low']
            last_price = today_intraday['last']
            data_source = 'intraday'
        else:
            today_open = float(prev_row['Open'])
            today_high = float(prev_row['High'])
            today_low = float(prev_row['Low'])
            last_price = float(prev_row['Close'])
            data_source = 'daily-fallback'

        long_trigger = today_open + self.params.k * prev_range
        short_trigger = today_open - self.params.k * prev_range

        # Filter values are evaluated using *yesterday's* row (no look-ahead).
        sma_val = float(prev_row.get('sma') or 0)
        atr_short_val = float(prev_row.get('atr_short') or 0)
        atr_long_val = float(prev_row.get('atr_long') or 0)
        trend_ok = (not self.params.use_trend_filter) or (float(prev_row['Close']) > sma_val and sma_val > 0)
        vol_ok = (not self.params.use_vol_filter) or (atr_short_val > atr_long_val and atr_long_val > 0)
        filters_ok = trend_ok and vol_ok

        long_signal = filters_ok and (today_high >= long_trigger)
        short_signal = (
            self.params.allow_shorts and filters_ok and (today_low <= short_trigger)
        )

        signal = None
        if long_signal:
            signal = 'buy'
        elif short_signal:
            signal = 'sell'

        # Idempotency: don't refire on the same date.
        today = datetime.utcnow().date()
        state = self._session_state.get(symbol) or {}
        if state.get('date') != today:
            state = {'date': today, 'fired': False, 'last_signal': None}
            self._session_state[symbol] = state

        if signal and state.get('fired'):
            # Already fired today — downgrade to "still in setup" output.
            signal = None

        result = {
            'symbol': symbol,
            'data_source': data_source,
            'today_open': today_open,
            'today_high': today_high,
            'today_low': today_low,
            'last_price': last_price,
            'prev_range': prev_range,
            'long_trigger': long_trigger,
            'short_trigger': short_trigger,
            'trend_ok': trend_ok,
            'vol_ok': vol_ok,
            'sma': sma_val,
            'atr_short': atr_short_val,
            'atr_long': atr_long_val,
            'signal': signal,
        }
        if signal:
            stop_price = (
                long_trigger - self.params.stop_mult * prev_range
                if signal == 'buy'
                else short_trigger + self.params.stop_mult * prev_range
            )
            result['stop_price'] = stop_price
            logger.info(
                f"🟢 {symbol}: {signal.upper()} breakout — open=${today_open:.2f} "
                f"trigger=${long_trigger if signal=='buy' else short_trigger:.2f} "
                f"high=${today_high:.2f} low=${today_low:.2f} stop=${stop_price:.2f} "
                f"prev_range=${prev_range:.2f}"
            )
        return result

    # -- execution -------------------------------------------------------

    def execute_signal(self, signal_data: dict) -> Optional[dict]:
        symbol = signal_data['symbol']
        signal = signal_data.get('signal')
        if not signal:
            return None
        webhook_data = {
            'symbol': symbol,
            'action': signal,
            'qty': 1,           # OrderManager applies Fibonacci sizing for buys
            'order_type': 'market',
        }
        result = self.order_manager.execute_webhook_order(webhook_data)
        if result.get('success'):
            # Submit a protective stop on the same side direction as exit.
            try:
                stop_side = 'sell' if signal == 'buy' else 'buy'
                qty = float(result.get('qty') or 1)
                stop_price = float(signal_data['stop_price'])
                self.alpaca.submit_stop_order(symbol, qty, stop_side, stop_price, time_in_force='day')
                logger.info(f"  protective stop submitted for {symbol} at ${stop_price:.2f}")
            except Exception as e:
                logger.error(f"  failed to submit protective stop for {symbol}: {e}")

            # Mark this symbol as fired for the day.
            today = datetime.utcnow().date()
            self._session_state[symbol] = {
                'date': today, 'fired': True, 'last_signal': signal,
            }
        return result

    def scan_all(self) -> list[dict]:
        results = []
        for symbol in self.symbols:
            sig = self.check_signal(symbol)
            if sig is None:
                continue
            results.append(sig)
            if sig.get('signal'):
                self.execute_signal(sig)
        return results

    def get_status(self) -> dict:
        return {
            'symbols': self.symbols,
            'params': self.params.as_dict(),
            'session_state': {
                k: {**v, 'date': v['date'].isoformat() if v.get('date') else None}
                for k, v in self._session_state.items()
            },
        }


# Module-level singleton accessor (matches RSI scanner pattern)
_scanner: Optional[WilliamsBreakoutScanner] = None


def get_scanner() -> WilliamsBreakoutScanner:
    global _scanner
    if _scanner is None:
        _scanner = WilliamsBreakoutScanner()
    return _scanner
