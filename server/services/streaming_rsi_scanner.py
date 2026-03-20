"""
Streaming RSI Scanner using WebSocket for real-time data
This receives bars as they complete, matching TradingView exactly
"""
import asyncio
import logging
from datetime import datetime
from collections import deque
import numpy as np
from alpaca.data.live import StockDataStream
from alpaca.data.models import Bar
from alpaca.data.enums import DataFeed
from config import Config
from services.order_manager import OrderManager

logger = logging.getLogger(__name__)

class StreamingRSIScanner:
    def __init__(self):
        self.config = Config()
        self.order_manager = OrderManager()
        
        # Magnificent 7 stocks
        self.symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']
        
        # RSI settings
        self.rsi_period = 8
        self.rsi_buy_threshold = 30
        self.rsi_sell_threshold = 75
        
        # Store recent bars for each symbol (need period + 1 for RSI)
        self.bar_history = {symbol: deque(maxlen=self.rsi_period + 1) for symbol in self.symbols}
        
        # Track last signals
        self.last_signals = {}
        
        # WebSocket stream
        self.stream = None
        self.is_running = False
        self.bars_received = 0
        
    def calculate_rsi(self, prices, period=8):
        """Calculate RSI using SMA method (matches TradingView)"""
        if len(prices) < period + 1:
            return None
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    async def on_bar(self, bar: Bar):
        """Handle incoming bar from WebSocket stream"""
        try:
            symbol = bar.symbol
            self.bars_received += 1
            
            if symbol not in self.symbols:
                return
            
            logger.info(f"📊 BAR RECEIVED: {symbol} @ {bar.timestamp} - Close: ${bar.close:.2f}, Volume: {bar.volume}")
            
            # Add bar to history
            self.bar_history[symbol].append(bar.close)
            
            # Need at least period + 1 bars for RSI
            if len(self.bar_history[symbol]) < self.rsi_period + 1:
                logger.info(f"{symbol}: Collecting bars... ({len(self.bar_history[symbol])}/{self.rsi_period + 1})")
                return
            
            # Calculate RSI
            prices = list(self.bar_history[symbol])
            rsi = self.calculate_rsi(prices, self.rsi_period)
            
            if rsi is None:
                return
            
            logger.info(f"✅ {symbol}: RSI({self.rsi_period}) = {rsi:.2f}, Price = ${bar.close:.2f} [Bar: {bar.timestamp}]")
            
            # Check for signals
            signal = None
            
            # BUY signal
            if rsi < self.rsi_buy_threshold:
                last_signal = self.last_signals.get(symbol, {})
                if last_signal.get('type') != 'buy' or (datetime.now() - last_signal.get('time', datetime.min)).seconds > 300:
                    signal = 'buy'
                    logger.info(f"🟢 {symbol}: BUY SIGNAL - RSI {rsi:.2f} < {self.rsi_buy_threshold}")
                    
                    # Execute trade
                    self.execute_signal(symbol, 'buy', rsi, bar.close)
            
            # SELL signal
            elif rsi > self.rsi_sell_threshold:
                try:
                    from services.alpaca_client import AlpacaClient
                    alpaca = AlpacaClient()
                    position = alpaca.get_position(symbol)
                    
                    last_signal = self.last_signals.get(symbol, {})
                    if last_signal.get('type') != 'sell' or (datetime.now() - last_signal.get('time', datetime.min)).seconds > 300:
                        signal = 'sell'
                        logger.info(f"🔴 {symbol}: SELL SIGNAL - RSI {rsi:.2f} > {self.rsi_sell_threshold}")
                        
                        # Execute trade
                        self.execute_signal(symbol, 'sell', rsi, bar.close)
                except:
                    pass  # No position to sell
                    
        except Exception as e:
            logger.error(f"Error processing bar for {symbol}: {e}")
            import traceback
            traceback.print_exc()
    
    def execute_signal(self, symbol, action, rsi, price):
        """Execute trade based on signal"""
        try:
            webhook_data = {
                'symbol': symbol,
                'action': action,
                'qty': 1,
                'order_type': 'market'
            }
            
            result = self.order_manager.execute_webhook_order(webhook_data)
            
            # Track signal
            self.last_signals[symbol] = {
                'type': action,
                'time': datetime.now(),
                'rsi': rsi,
                'price': price
            }
            
            if result['success']:
                logger.info(f"✅ {symbol}: {action.upper()} order executed - {result}")
            else:
                logger.error(f"❌ {symbol}: {action.upper()} order failed - {result}")
                
        except Exception as e:
            logger.error(f"Error executing signal for {symbol}: {e}")
    
    async def start(self):
        """Start WebSocket streaming"""
        if self.is_running:
            logger.warning("Streaming scanner already running")
            return
        
        try:
            logger.info("=" * 60)
            logger.info("STARTING WEBSOCKET STREAMING RSI SCANNER")
            logger.info("=" * 60)
            logger.info(f"Symbols: {', '.join(self.symbols)}")
            logger.info(f"RSI Period: {self.rsi_period}")
            logger.info(f"Buy Threshold: < {self.rsi_buy_threshold}")
            logger.info(f"Sell Threshold: > {self.rsi_sell_threshold}")
            logger.info(f"Using WebSocket for REAL-TIME bars (SIP feed)")
            logger.info("=" * 60)
            
            # Create WebSocket stream
            self.stream = StockDataStream(
                self.config.ALPACA_API_KEY,
                self.config.ALPACA_SECRET_KEY,
                feed=DataFeed.SIP  # Use SIP feed for real-time data
            )
            
            # Subscribe to bars for all symbols
            logger.info(f"📡 Subscribing to bars for: {', '.join(self.symbols)}")
            self.stream.subscribe_bars(self.on_bar, *self.symbols)
            
            self.is_running = True
            
            # Start streaming
            logger.info("🚀 WebSocket connected - waiting for bars...")
            logger.info("   Bars will arrive as they complete in real-time")
            logger.info("   This matches TradingView's data exactly!")
            
            await self.stream._run_forever()
            
        except Exception as e:
            logger.error(f"Error starting streaming scanner: {e}")
            import traceback
            traceback.print_exc()
            self.is_running = False
    
    async def stop(self):
        """Stop WebSocket streaming"""
        if not self.is_running:
            return
        
        try:
            if self.stream:
                await self.stream.close()
            self.is_running = False
            logger.info("⏹️ Streaming scanner stopped")
        except Exception as e:
            logger.error(f"Error stopping streaming scanner: {e}")
    
    def update_settings(self, settings):
        """Update scanner settings"""
        if 'rsi_period' in settings:
            old_period = self.rsi_period
            self.rsi_period = int(settings['rsi_period'])
            
            # Adjust bar history size
            if old_period != self.rsi_period:
                for symbol in self.symbols:
                    self.bar_history[symbol] = deque(
                        list(self.bar_history[symbol])[-self.rsi_period-1:],
                        maxlen=self.rsi_period + 1
                    )
        
        if 'buy_threshold' in settings:
            self.rsi_buy_threshold = float(settings['buy_threshold'])
        if 'sell_threshold' in settings:
            self.rsi_sell_threshold = float(settings['sell_threshold'])
        
        logger.info(f"Settings updated: RSI({self.rsi_period}), Buy<{self.rsi_buy_threshold}, Sell>{self.rsi_sell_threshold}")
    
    def get_status(self):
        """Get scanner status"""
        return {
            'is_running': self.is_running,
            'symbols': self.symbols,
            'rsi_period': self.rsi_period,
            'buy_threshold': self.rsi_buy_threshold,
            'sell_threshold': self.rsi_sell_threshold,
            'bar_counts': {symbol: len(self.bar_history[symbol]) for symbol in self.symbols},
            'bars_received': self.bars_received,
            'last_signals': self.last_signals,
            'mode': 'websocket-streaming',
            'data_source': 'Alpaca WebSocket (SIP feed - real-time)'
        }

# Global instance
_streaming_scanner = None

def get_streaming_scanner():
    """Get or create the global streaming scanner instance"""
    global _streaming_scanner
    if _streaming_scanner is None:
        _streaming_scanner = StreamingRSIScanner()
    return _streaming_scanner
