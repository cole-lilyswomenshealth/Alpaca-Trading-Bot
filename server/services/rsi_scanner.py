"""
RSI Scanner for Magnificent 7 Stocks
Monitors 1-minute RSI(8) and places trades automatically
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from services.alpaca_client import AlpacaClient
from services.order_manager import OrderManager

logger = logging.getLogger(__name__)

class RSIScanner:
    def __init__(self):
        self.alpaca = AlpacaClient()
        self.order_manager = OrderManager()
        
        # Magnificent 7 stocks
        self.symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']
        
        # Default RSI settings (can be changed via API)
        self.rsi_period = 8
        self.rsi_buy_threshold = 30
        self.rsi_sell_threshold = 75
        self.timeframe = '1Min'  # 1Min, 5Min, 15Min, 1Hour, 1Day
        
        # Track last signals to avoid duplicate trades
        self.last_signals = {}
        
        # Track last bar timestamp to ensure we only trade on bar close
        self.last_bar_times = {}
    
    def update_settings(self, settings):
        """Update scanner settings"""
        if 'rsi_period' in settings:
            self.rsi_period = int(settings['rsi_period'])
        if 'buy_threshold' in settings:
            self.rsi_buy_threshold = float(settings['buy_threshold'])
        if 'sell_threshold' in settings:
            self.rsi_sell_threshold = float(settings['sell_threshold'])
        if 'timeframe' in settings:
            self.timeframe = settings['timeframe']
        
        logger.info(f"Settings updated: RSI({self.rsi_period}), Buy<{self.rsi_buy_threshold}, Sell>{self.rsi_sell_threshold}, TF={self.timeframe}")
    
    def calculate_rsi(self, prices, period=8):
        """
        Calculate RSI indicator using SMA method (TradingView default when smoothing = SMA)
        This matches TradingView's RSI with: Length=8, Source=Close, Smoothing=SMA
        """
        if len(prices) < period + 1:
            return None
        
        # Calculate price changes
        deltas = np.diff(prices)
        
        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # Use Simple Moving Average (SMA) method - matches TradingView
        # Calculate average of last 'period' gains and losses
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        # Avoid division by zero
        if avg_loss == 0:
            return 100
        
        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def get_market_data(self, symbol):
        """Get bars for RSI calculation - only completed bars"""
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            
            # Map timeframe string to TimeFrame object
            timeframe_map = {
                '1Min': TimeFrame.Minute,
                '5Min': TimeFrame(5, 'Min'),
                '15Min': TimeFrame(15, 'Min'),
                '1Hour': TimeFrame.Hour,
                '1Day': TimeFrame.Day
            }
            
            tf = timeframe_map.get(self.timeframe, TimeFrame.Minute)
            
            # Get enough bars for RSI calculation + buffer
            # For Wilder's smoothing, we need at least period * 3 bars for accuracy
            # For intraday, get last 4 hours of data (240 minutes for 1min bars)
            # For daily, get last 90 days
            if self.timeframe == '1Day':
                end = datetime.now()
                start = end - timedelta(days=90)
            else:
                end = datetime.now()
                # Get 4 hours of data for intraday
                start = end - timedelta(hours=4)
            
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                start=start,
                end=end,
                feed='sip'  # Use SIP feed for real-time data (paid subscription)
            )
            
            bars = self.alpaca.data_client.get_stock_bars(request)
            
            if symbol not in bars.data:
                return None, None
            
            bar_list = bars.data[symbol]
            
            if len(bar_list) < self.rsi_period + 1:
                logger.warning(f"{symbol}: Only {len(bar_list)} bars available, need at least {self.rsi_period + 1}")
                return None, None
            
            # Get the last COMPLETED bar (not the current forming bar)
            # For 1-minute bars, use all bars except potentially forming one
            # But only exclude if we have enough data
            if self.timeframe == '1Min':
                # For 1-minute bars, exclude the last bar if we have plenty of data
                # This ensures we're only using completed bars
                if len(bar_list) > self.rsi_period * 3:
                    completed_bars = bar_list[:-1]
                else:
                    # Not enough data to exclude last bar safely
                    completed_bars = bar_list
            else:
                # For longer timeframes, use all bars
                completed_bars = bar_list
            
            # Ensure we have enough data for Wilder's smoothing
            # Wilder's method needs at least period * 2 for proper warmup
            min_required = self.rsi_period * 2
            if len(completed_bars) < min_required:
                logger.warning(f"{symbol}: Only {len(completed_bars)} completed bars, need at least {min_required} for accurate Wilder's RSI")
                # Still try to calculate, but log warning
            
            # Get the timestamp of the last completed bar
            last_bar_time = completed_bars[-1].timestamp
            
            # Convert to list of close prices
            prices = [bar.close for bar in completed_bars]
            
            logger.info(f"{symbol}: Retrieved {len(prices)} prices for RSI calculation, last bar: {last_bar_time}")
            
            return prices, last_bar_time
            
        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {e}")
            return None, None
    
    def check_signal(self, symbol):
        """Check if there's a buy or sell signal on completed bar"""
        try:
            # Get market data (only completed bars)
            prices, last_bar_time = self.get_market_data(symbol)
            
            if not prices or len(prices) < self.rsi_period + 1:
                logger.warning(f"{symbol}: Not enough data for RSI calculation")
                return None
            
            # Calculate RSI on completed bars
            rsi = self.calculate_rsi(prices, self.rsi_period)
            
            if rsi is None:
                return None
            
            current_price = prices[-1]
            
            # Check if this is a new bar (bar close)
            last_checked = self.last_bar_times.get(symbol)
            is_new_bar = not last_checked or last_bar_time > last_checked
            
            if is_new_bar:
                # Update last bar time
                self.last_bar_times[symbol] = last_bar_time
                logger.info(f"{symbol}: RSI({self.rsi_period}) = {rsi:.2f}, Price = ${current_price:.2f} [Bar Close: {last_bar_time}]")
            else:
                # Same bar, don't log or check for signals
                logger.debug(f"{symbol}: Same bar as before ({last_bar_time}), skipping signal check")
            
            # Check for signals only on new bars
            signal = None
            
            if is_new_bar:
                # BUY signal: RSI crosses under threshold
                if rsi < self.rsi_buy_threshold:
                    # Check if we sent this signal recently
                    last_signal = self.last_signals.get(symbol, {})
                    if last_signal.get('type') != 'buy' or (datetime.now() - last_signal.get('time', datetime.min)).seconds > 300:
                        signal = 'buy'
                        # Check if we have a position (for logging)
                        try:
                            position = self.alpaca.get_position(symbol)
                            logger.info(f"🟢 {symbol}: BUY SIGNAL - RSI {rsi:.2f} < {self.rsi_buy_threshold} (Adding to position: {position.qty} shares)")
                        except:
                            logger.info(f"🟢 {symbol}: BUY SIGNAL - RSI {rsi:.2f} < {self.rsi_buy_threshold} (Opening new position)")
                
                # SELL signal: RSI crosses over threshold
                elif rsi > self.rsi_sell_threshold:
                    # Check if we have a position to sell
                    try:
                        position = self.alpaca.get_position(symbol)
                        # Check if we sent this signal recently
                        last_signal = self.last_signals.get(symbol, {})
                        if last_signal.get('type') != 'sell' or (datetime.now() - last_signal.get('time', datetime.min)).seconds > 300:
                            signal = 'sell'
                            logger.info(f"🔴 {symbol}: SELL SIGNAL - RSI {rsi:.2f} > {self.rsi_sell_threshold} (Closing position: {position.qty} shares)")
                    except:
                        logger.info(f"{symbol}: RSI > {self.rsi_sell_threshold} but no position to sell")
            
            # Always return data (even if no new bar) so symbol appears in results
            return {
                'symbol': symbol,
                'rsi': rsi,
                'price': current_price,
                'signal': signal,
                'bar_time': last_bar_time.isoformat(),
                'is_new_bar': is_new_bar
            }
            
        except Exception as e:
            logger.error(f"Error checking signal for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def execute_signal(self, signal_data):
        """Execute a buy or sell order based on signal"""
        try:
            symbol = signal_data['symbol']
            signal = signal_data['signal']
            
            if not signal:
                return None
            
            # Prepare webhook data
            webhook_data = {
                'symbol': symbol,
                'action': signal,
                'qty': 1,  # Will be adjusted by Fibonacci
                'order_type': 'market'
            }
            
            # Execute order
            result = self.order_manager.execute_webhook_order(webhook_data)
            
            # Track this signal
            self.last_signals[symbol] = {
                'type': signal,
                'time': datetime.now(),
                'rsi': signal_data['rsi']
            }
            
            if result['success']:
                logger.info(f"✅ {symbol}: {signal.upper()} order executed - {result}")
            else:
                logger.error(f"❌ {symbol}: {signal.upper()} order failed - {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            return None
    
    def scan_all(self):
        """Scan all Magnificent 7 stocks"""
        logger.info("=" * 60)
        logger.info(f"RSI SCAN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
        
        results = []
        
        for symbol in self.symbols:
            signal_data = self.check_signal(symbol)
            
            if signal_data:
                results.append(signal_data)
                
                # Execute if there's a signal
                if signal_data['signal']:
                    self.execute_signal(signal_data)
        
        logger.info("=" * 60)
        
        return results
    
    def get_status(self):
        """Get scanner status"""
        return {
            'symbols': self.symbols,
            'rsi_period': self.rsi_period,
            'buy_threshold': self.rsi_buy_threshold,
            'sell_threshold': self.rsi_sell_threshold,
            'timeframe': self.timeframe,
            'last_signals': self.last_signals
        }
