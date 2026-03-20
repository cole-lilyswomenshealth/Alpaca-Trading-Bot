"""
Multi-Account Order Manager
Manages orders across multiple Alpaca accounts
"""
import logging
from services.alpaca_client import AlpacaClient
from services.position_tracker import PositionTracker
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

logger = logging.getLogger(__name__)

class MultiAccountManager:
    def __init__(self, account_config):
        """
        Initialize manager for specific account
        
        Args:
            account_config: Dictionary with account settings
        """
        self.account_id = account_config.get('name', 'Unknown')
        self.config = account_config
        
        # Create Alpaca client for this account
        self.alpaca_client = self._create_alpaca_client()
        
        # Create position tracker for this account
        self.position_tracker = PositionTracker(
            max_iterations=account_config.get('fibonacci_max_iterations', 8)
        )
        
        # Fibonacci settings
        self.fibonacci_enabled = account_config.get('fibonacci_enabled', True)
        self.fibonacci_base = account_config.get('fibonacci_base', 0.1)
        self.fibonacci_max_iterations = account_config.get('fibonacci_max_iterations', 8)
        
        # Profit protection settings
        self.profit_protection_enabled = account_config.get('profit_protection_enabled', True)
        self.profit_protection_threshold = account_config.get('profit_protection_threshold', 0.05)
        
        logger.info(f"✅ {self.account_id} initialized - Fib base: {self.fibonacci_base}, Max: {self.fibonacci_max_iterations}")
    
    def _create_alpaca_client(self):
        """Create Alpaca client with account-specific credentials"""
        from alpaca.trading.client import TradingClient
        from alpaca.data.historical import StockHistoricalDataClient
        
        # Create trading client
        trading_client = TradingClient(
            self.config['api_key'],
            self.config['secret_key'],
            paper=True  # Always paper for now
        )
        
        # Create data client
        data_client = StockHistoricalDataClient(
            self.config['api_key'],
            self.config['secret_key']
        )
        
        # Create wrapper object
        class AccountAlpacaClient:
            def __init__(self, trading, data):
                self.trading_client = trading
                self.data_client = data
            
            def get_account(self):
                return self.trading_client.get_account()
            
            def get_positions(self):
                return self.trading_client.get_all_positions()
            
            def get_position(self, symbol):
                try:
                    return self.trading_client.get_open_position(symbol)
                except:
                    return None
            
            def submit_market_order(self, symbol, qty, side, time_in_force='gtc'):
                order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
                tif = TimeInForce.GTC if time_in_force.lower() == 'gtc' else TimeInForce.DAY
                
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=order_side,
                    time_in_force=tif
                )
                return self.trading_client.submit_order(order_data)
        
        return AccountAlpacaClient(trading_client, data_client)
    
    def execute_webhook_order(self, data):
        """Execute order for this account"""
        try:
            symbol = data.get('symbol', '').upper()
            action = data.get('action', '').lower()
            qty = float(data.get('quantity', data.get('qty', 1)))
            
            logger.info(f"[{self.account_id}] Processing: {symbol} {action} {qty}")
            
            # Handle sell orders
            if action == 'sell':
                return self._execute_sell(symbol, qty)
            
            # Handle buy orders with Fibonacci
            elif action == 'buy':
                return self._execute_buy(symbol, qty)
            
            else:
                return {'success': False, 'error': f'Unknown action: {action}'}
        
        except Exception as e:
            logger.error(f"[{self.account_id}] Error: {e}")
            return {'success': False, 'error': str(e)}
    
    def _execute_buy(self, symbol, base_qty):
        """Execute buy with Fibonacci sizing"""
        if not self.fibonacci_enabled:
            # No Fibonacci, just buy base quantity
            order = self.alpaca_client.submit_market_order(symbol, base_qty, 'buy')
            return {
                'success': True,
                'account': self.account_id,
                'order_id': order.id,
                'symbol': symbol,
                'qty': base_qty,
                'side': 'buy'
            }
        
        # Get Fibonacci quantity
        fib_qty = self.position_tracker.get_next_quantity(symbol, self.fibonacci_base)
        
        if fib_qty is None:
            return {
                'success': False,
                'account': self.account_id,
                'error': f'Maximum Fibonacci iterations ({self.fibonacci_max_iterations}) reached for {symbol}'
            }
        
        # Execute order
        logger.info(f"[{self.account_id}] Fibonacci buy: {symbol} {fib_qty} shares")
        order = self.alpaca_client.submit_market_order(symbol, fib_qty, 'buy')
        
        # Record buy
        self.position_tracker.record_buy(symbol, fib_qty)
        
        return {
            'success': True,
            'account': self.account_id,
            'order_id': order.id,
            'symbol': symbol,
            'qty': fib_qty,
            'side': 'buy',
            'fibonacci_position': self.position_tracker.get_position_info(symbol)['buy_count']
        }
    
    def _execute_sell(self, symbol, qty):
        """Execute sell order"""
        # Check if we have a position
        position = self.alpaca_client.get_position(symbol)
        
        if not position:
            return {
                'success': False,
                'account': self.account_id,
                'error': f'No position exists for {symbol}'
            }
        
        # Sell the position
        logger.info(f"[{self.account_id}] Selling: {symbol} {qty} shares")
        order = self.alpaca_client.submit_market_order(symbol, qty, 'sell')
        
        # Record sell (resets Fibonacci counter if position fully closed)
        self.position_tracker.record_sell(symbol, qty)
        
        return {
            'success': True,
            'account': self.account_id,
            'order_id': order.id,
            'symbol': symbol,
            'qty': qty,
            'side': 'sell'
        }
    
    def get_account_summary(self):
        """Get account summary"""
        account = self.alpaca_client.get_account()
        return {
            'account_id': self.account_id,
            'equity': float(account.equity),
            'cash': float(account.cash),
            'buying_power': float(account.buying_power),
            'fibonacci_base': self.fibonacci_base,
            'fibonacci_max': self.fibonacci_max_iterations
        }
