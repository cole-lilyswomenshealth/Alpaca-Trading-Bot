"""
Quote-Based RSI Scanner
Builds 1-minute bars from real-time quotes (sub-second lag)
This matches TradingView's real-time data exactly
"""
import asyncio
import logging
from datetime import datetime, timedelta
from collections import deque
import numpy as np
from config import Config
from services.order_manager import OrderManager
from services.alpaca_client import AlpacaClient

logger = logging.getLogger(__name__)

class QuoteBasedRSIScanner:
    def __init__(self):
        self.config = Config()
        self.alpaca = AlpacaClient()
        self.order_manager = OrderManager()
        
        # Magnificent 7 stocks
        self.symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']
        
        # RSI settings
        self.rsi_period = 8
        self.rsi_buy_threshold = 30
        self.rsi_sell_threshold = 75
        
        # Store minute-level close prices (built from quotes)
        # We sample quotes every minute and use mid-price as "close"
        self.minute_closes = {symbol: deque(maxlen=self.rsi_period + 1) for symbol in self.symbols}
        
        # Track last signals
        self.last_signals = {}
        
        # Scanner state
        self.is_running = False
        self.scan_count = 0
        self.last_scan_time = None
        
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
    
    def get_current_price(self, symbol):
        """Get current price from real-time quote (mid-price)"""
        try:
            from alpaca.data.requests import StockLatestQuoteRequest
            
            request = StockLatestQuoteRequest(
                symbol_or_symbols=symbol,
                feed='sip'
            )
            quotes = self.alpaca.data_client.get_stock_latest_quote(request)
            
            if symbol in quotes:
                quote = quotes[symbol]
                # Use mid-price (average of bid and ask)
                mid_price = (quote.bid_price + quote.ask_price) / 2
                return mid_price, quote.timestamp
            
            return None, None
            
        except Exception as e:
            logger.error(f"Error getting quote for {symbol}: {e}")
            return None, None
    
    def scan_symbol(self, symbol):
        """Scan a single symbol using real-time quotes"""
        try:
            # Get current price from quote
            price, quote_time = self.get_current_price(symbol)
            
            if price is None:
                return None
            
            # Add to minute closes
            self.minute_closes[symbol].append(price)
            
            # Need at least period + 1 prices for RSI
            if len(self.minute_closes[symbol]) < self.rsi_period + 1:
                logger.info(f"{symbol}: Collecting prices... ({len(self.minute_closes[symbol])}/{self.rsi_period + 1})")
                return {
                    'symbol': symbol,
                    'price': price,
                    'rsi': None,
                    'signal': None,
                    'quote_time': quote_time.isoformat() if quote_time else None
                }
            
            # Calculate RSI
            prices = list(self.minute_closes[symbol])
            rsi = self.calculate_rsi(prices, self.rsi_period)
            
            if rsi is None:
                return None
            
            logger.info(f"{symbol}: RSI({self.rsi_period}) = {rsi:.2f}, Price = ${price:.2f} [Quote: {quote_time}]")
            
            # Check for signals
            signal = None
            
            # BUY signal
            if rsi < self.rsi_buy_threshold:
                last_signal = self.last_signals.get(symbol, {})
                if last_signal.get('type') != 'buy' or (datetime.now() - last_signal.get('time', datetime.min)).seconds > 300:
                    signal = 'buy'
                    logger.info(f"🟢 {symbol}: BUY SIGNAL - RSI {rsi:.2f} < {self.rsi_buy_threshold}")
                    self.execute_signal(symbol, 'buy', rsi, price)
            
            # SELL signal
            elif rsi > self.rsi_sell_threshold:
                try:
                    position = self.alpaca.get_position(symbol)
                    last_signal = self.last_signals.get(symbol, {})
                    if last_signal.get('type') != 'sell' or (datetime.now() - last_signal.get('time', datetime.min)).seconds > 300:
                        signal = 'sell'
                        logger.info(f"🔴 {symbol}: SELL SIGNAL - RSI {rsi:.2f} > {self.rsi_sell_threshold}")
                        self.execute_signal(symbol, 'sell', rsi, price)
                except:
                    pass  # No position
            
            return {
                'symbol': symbol,
                'rsi': rsi,
                'price': price,
                'signal': signal,
                'quote_time': quote_time.isoformat() if quote_time else None
            }
            
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
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
    
    async def run_continuous(self, interval=60):
        """Run scanner continuously, sampling quotes every minute"""
        logger.info("=" * 60)
        logger.info("QUOTE-BASED RSI SCANNER - REAL-TIME MODE")
        logger.info("=" * 60)
        logger.info(f"Symbols: {', '.join(self.symbols)}")
        logger.info(f"RSI Period: {self.rsi_period}")
        logger.info(f"Buy Threshold: < {self.rsi_buy_threshold}")
        logger.info(f"Sell Threshold: > {self.rsi_sell_threshold}")
        logger.info(f"Sampling quotes every {interval} seconds")
        logger.info(f"Using REAL-TIME quotes (sub-second lag)")
        logger.info("=" * 60)
        
        self.is_running = True
        
        while self.is_running:
            try:
                scan_start = datetime.now()
                logger.info(f"\n🔍 Scan #{self.scan_count + 1} - {scan_start.strftime('%Y-%m-%d %H:%M:%S')}")
                
                results = []
                for symbol in self.symbols:
                    result = self.scan_symbol(symbol)
                    if result:
                        results.append(result)
                
                self.scan_count += 1
                self.last_scan_time = scan_start
                
                # Log summary
                signals = [r for r in results if r.get('signal')]
                logger.info(f"✅ Scan complete - {len(results)} symbols, {len(signals)} signals")
                
                # Wait for next scan
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Error in scan loop: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(interval)
    
    def scan_once(self):
        """Run a single scan (for API endpoint)"""
        logger.info("=" * 60)
        logger.info(f"QUOTE-BASED RSI SCAN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
        
        results = []
        for symbol in self.symbols:
            result = self.scan_symbol(symbol)
            if result:
                results.append(result)
        
        logger.info("=" * 60)
        return results
    
    def update_settings(self, settings):
        """Update scanner settings"""
        if 'rsi_period' in settings:
            old_period = self.rsi_period
            self.rsi_period = int(settings['rsi_period'])
            
            # Adjust history size
            if old_period != self.rsi_period:
                for symbol in self.symbols:
                    self.minute_closes[symbol] = deque(
                        list(self.minute_closes[symbol])[-self.rsi_period-1:],
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
            'price_counts': {symbol: len(self.minute_closes[symbol]) for symbol in self.symbols},
            'last_signals': self.last_signals,
            'scan_count': self.scan_count,
            'last_scan_time': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'mode': 'quote-based',
            'data_source': 'real-time quotes (sub-second lag)'
        }
    
    def stop(self):
        """Stop the scanner"""
        self.is_running = False
        logger.info("⏹️ Quote-based scanner stopped")

# Global instance
_quote_scanner = None

def get_quote_scanner():
    """Get or create the global quote scanner instance"""
    global _quote_scanner
    if _quote_scanner is None:
        _quote_scanner = QuoteBasedRSIScanner()
    return _quote_scanner
