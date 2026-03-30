from services.alpaca_client import AlpacaClient
from services.risk_manager import RiskManager
from services.position_tracker import PositionTracker
from services.supabase_client import SupabaseClient
from config import Config
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class OrderManager:
    def __init__(self):
        self.alpaca = AlpacaClient()
        self.risk_manager = RiskManager(self.alpaca)
        self.position_tracker = PositionTracker()
        self.supabase = SupabaseClient()
        self.config = Config()
        
        # Log if Supabase is connected
        if self.supabase.is_connected():
            logger.info("✅ Supabase connected - trades will be saved to database")
        else:
            logger.warning("⚠️ Supabase not connected - using local storage only")
    
    def _format_crypto_symbol(self, symbol):
        """Convert crypto symbols to Alpaca format (e.g., BTCUSD -> BTC/USD)"""
        crypto_pairs = {
            'BTCUSD': 'BTC/USD',
            'ETHUSD': 'ETH/USD',
            'BCHUSD': 'BCH/USD',
            'LTCUSD': 'LTC/USD',
            'DOGEUSD': 'DOGE/USD',
            'AVAXUSD': 'AVAX/USD',
            'UNIUSD': 'UNI/USD',
            'LINKUSD': 'LINK/USD',
            'AAVEUSD': 'AAVE/USD',
            'SHIBUSDT': 'SHIB/USD',
            'MATICUSD': 'MATIC/USD',
            'SOLUSD': 'SOL/USD',
            'ADAUSD': 'ADA/USD',
            'DOTUSD': 'DOT/USD',
            'XLMUSD': 'XLM/USD',
            'ATOMUSD': 'ATOM/USD',
            'ALGOUSD': 'ALGO/USD',
            'GRTUSD': 'GRT/USD',
            'COMPUSD': 'COMP/USD',
            'YFIUSD': 'YFI/USD',
            'CETH': 'ETH/USD'  # CETH maps to ETH/USD
        }
        
        # If already has slash, return as is
        if '/' in symbol:
            return symbol
        
        # Check if it's a known crypto pair
        return crypto_pairs.get(symbol, symbol)
    
    def execute_webhook_order(self, webhook_data):
        """Execute order from webhook data with profit protection"""
        try:
            # Parse webhook data
            symbol = webhook_data.get('symbol', '').upper()
            symbol = self._format_crypto_symbol(symbol)  # Format crypto symbols
            action = webhook_data.get('action', '').lower()
            
            # Support both 'qty' and 'quantity' parameters
            qty = webhook_data.get('qty') or webhook_data.get('quantity', 0)
            qty = float(qty) if qty else 0
            
            order_type = webhook_data.get('order_type', 'market').lower()
            price = webhook_data.get('price')
            
            # Debug logging
            print(f"DEBUG: Original symbol: {webhook_data.get('symbol')}")
            print(f"DEBUG: Formatted symbol: {symbol}")
            print(f"DEBUG: Action: {action}, Qty: {qty}, Type: {order_type}")
            
            # Validate inputs
            if not symbol:
                return {'success': False, 'error': 'Symbol is required'}
            
            if action not in ['buy', 'sell']:
                return {'success': False, 'error': 'Action must be buy or sell'}
            
            if qty <= 0:
                return {'success': False, 'error': 'Quantity must be greater than 0'}
            
            # FIBONACCI POSITION SIZING: For BUY orders, use Fibonacci sequence
            if action == 'buy':
                # Check if Fibonacci sizing is enabled in config
                use_fibonacci = self.config.FIBONACCI_ENABLED
                
                if use_fibonacci:
                    # Get Fibonacci parameters from config
                    base_qty = self.config.FIBONACCI_BASE
                    
                    # Check for symbol-specific base override
                    if symbol in self.config.FIBONACCI_SYMBOL_BASES:
                        base_qty = self.config.FIBONACCI_SYMBOL_BASES[symbol]
                        print(f"SYMBOL-SPECIFIC BASE: {symbol} uses base {base_qty} (default is {self.config.FIBONACCI_BASE})")
                    
                    max_iterations = self.config.FIBONACCI_MAX_ITERATIONS
                    
                    # CRITICAL: Check if position actually exists in Alpaca
                    # If no position exists, reset the Fibonacci counter to start fresh
                    try:
                        position = self.alpaca.get_position(symbol)
                        # Position exists, continue with current counter
                        print(f"EXISTING POSITION FOUND: {symbol} - {position.qty} shares")
                    except:
                        # No position exists - reset counter to start fresh
                        current_count = self.position_tracker.get_buy_count(symbol)
                        if current_count > 0:
                            print(f"NO POSITION EXISTS: {symbol} - Resetting Fibonacci counter from {current_count} to 0")
                            self.position_tracker.record_sell(symbol)  # Reset counter
                        else:
                            print(f"NO POSITION EXISTS: {symbol} - Starting fresh (counter already at 0)")
                    
                    # Get the next Fibonacci quantity
                    fibonacci_qty = self.position_tracker.get_next_quantity(symbol, base_qty, max_iterations)
                    
                    # Check if max iterations reached
                    if fibonacci_qty is None:
                        return {
                            'success': False,
                            'error': 'FIBONACCI LIMIT REACHED',
                            'details': {
                                'symbol': symbol,
                                'buy_count': self.position_tracker.get_buy_count(symbol),
                                'max_iterations': max_iterations,
                                'message': f'Maximum {max_iterations} buy orders reached. Close position to reset.'
                            }
                        }
                    
                    print(f"FIBONACCI SIZING ENABLED (from config):")
                    print(f"  Base quantity: {base_qty}")
                    print(f"  Max iterations: {max_iterations}")
                    print(f"  Fibonacci quantity: {fibonacci_qty}")
                    
                    qty = fibonacci_qty
                else:
                    print(f"FIBONACCI DISABLED: Using provided quantity {qty}")
            
            # PROFIT PROTECTION: Check if this is a SELL order
            if action == 'sell':
                try:
                    position = None
                    original_symbol = webhook_data.get('symbol', '').upper()
                    
                    # Try multiple symbol formats (crypto can be BTCUSD or BTC/USD)
                    symbols_to_try = [symbol]
                    if original_symbol != symbol:
                        symbols_to_try.append(original_symbol)
                    # Also try without slash if it has one, or with slash if it doesn't
                    if '/' in symbol:
                        symbols_to_try.append(symbol.replace('/', ''))
                    elif len(symbol) > 4 and symbol.endswith('USD'):
                        symbols_to_try.append(symbol[:-3] + '/' + symbol[-3:])
                    
                    for try_symbol in symbols_to_try:
                        try:
                            position = self.alpaca.get_position(try_symbol)
                            if position:
                                symbol = try_symbol
                                print(f"Found position with symbol: {try_symbol}")
                                break
                        except:
                            continue
                    
                    if position:
                        unrealized_pl = float(position.unrealized_pl)
                        unrealized_plpc = float(position.unrealized_plpc) * 100  # Convert to percentage
                        
                        print(f"PROFIT CHECK: {symbol} - Unrealized P&L: ${unrealized_pl:.2f} ({unrealized_plpc:.2f}%)")
                        
                        # Check if profit protection is enabled
                        if self.config.PROFIT_PROTECTION_ENABLED:
                            threshold = self.config.PROFIT_PROTECTION_THRESHOLD  # Minimum % profit required
                            
                            # If position is NOT profitable enough, reject the sell
                            if unrealized_plpc <= threshold:
                                return {
                                    'success': False,
                                    'error': f'PROFIT PROTECTION: Position not at {threshold}% profit (currently {unrealized_plpc:.2f}%)',
                                    'details': {
                                        'symbol': symbol,
                                        'unrealized_pl': unrealized_pl,
                                        'unrealized_plpc': unrealized_plpc,
                                        'threshold': threshold,
                                        'message': f'Sell order blocked - need {threshold}% profit, currently at {unrealized_plpc:.2f}%'
                                    }
                                }
                        
                        # Position is profitable enough - sell entire position
                        print(f"PROFIT CHECK PASSED: Selling entire position of {position.qty} shares")
                        qty = abs(float(position.qty))  # Sell entire position
                        
                    else:
                        # No position exists - can't sell
                        return {
                            'success': False,
                            'error': 'No position exists for this symbol',
                            'details': {'symbol': symbol}
                        }
                        
                except Exception as pos_error:
                    # If we can't get position, log but continue (might be closing a position that just filled)
                    print(f"Warning: Could not check position for {symbol}: {pos_error}")
            
            # Convert price to float if provided
            if price:
                price = float(price)
            
            # Validate against risk rules
            is_valid, errors = self.risk_manager.validate_order(
                symbol, qty, action, order_type, price
            )
            
            if not is_valid:
                return {
                    'success': False,
                    'error': 'Risk validation failed',
                    'details': errors
                }
            
            # Execute order based on type
            if order_type == 'market':
                # Crypto and fractional shares require 'gtc' or 'ioc' time_in_force
                # Alpaca crypto only supports 'gtc' and 'ioc'
                is_crypto = '/' in symbol  # Crypto symbols have slash (e.g., BTC/USD)
                if is_crypto:
                    tif = 'gtc'  # Crypto requires gtc or ioc
                else:
                    # Fractional shares (any decimal) require 'day' time_in_force
                    is_fractional = qty != int(qty)  # Check if quantity has decimal
                    tif = 'day' if is_fractional else webhook_data.get('time_in_force', 'gtc')
                order = self.alpaca.submit_market_order(symbol, qty, action, tif)
            elif order_type == 'limit':
                if not price:
                    return {'success': False, 'error': 'Limit price required for limit orders'}
                order = self.alpaca.submit_limit_order(symbol, qty, action, price)
            elif order_type == 'stop':
                if not price:
                    return {'success': False, 'error': 'Stop price required for stop orders'}
                order = self.alpaca.submit_stop_order(symbol, qty, action, price)
            else:
                return {'success': False, 'error': f'Unsupported order type: {order_type}'}
            
            # Save trade to Supabase
            if self.supabase.is_connected():
                try:
                    # Get current price for the trade
                    trade_price = price if price else None
                    if not trade_price:
                        try:
                            # Try to get latest price
                            position = self.alpaca.get_position(symbol)
                            trade_price = float(position.current_price)
                        except:
                            trade_price = 0
                    
                    # Save trade with 'webhook' source
                    self.supabase.save_trade(
                        symbol=symbol,
                        side=action,
                        quantity=int(qty),
                        price=trade_price,
                        order_id=order.id,
                        source='webhook'  # Mark as webhook trade
                    )
                    
                    # Track position in Supabase
                    if action == 'buy':
                        # Check if position exists
                        existing_pos = self.supabase.get_position_by_symbol(symbol)
                        if existing_pos and existing_pos['status'] == 'open':
                            # Update existing position (add to it)
                            new_qty = existing_pos['quantity'] + int(qty)
                            new_cost = (existing_pos['entry_price'] * existing_pos['quantity']) + (trade_price * qty)
                            new_avg_price = new_cost / new_qty
                            
                            self.supabase.update_position(
                                existing_pos['id'],
                                quantity=new_qty,
                                entry_price=new_avg_price
                            )
                        else:
                            # Create new position with 'webhook' source
                            self.supabase.save_position(
                                symbol=symbol,
                                entry_price=trade_price,
                                quantity=int(qty),
                                source='webhook'  # Mark as webhook position
                            )
                    
                    elif action == 'sell':
                        # Close position
                        existing_pos = self.supabase.get_position_by_symbol(symbol)
                        if existing_pos and existing_pos['status'] == 'open':
                            # Calculate P&L
                            pnl = (trade_price - existing_pos['entry_price']) * qty
                            
                            if int(qty) >= existing_pos['quantity']:
                                # Closing entire position
                                self.supabase.close_position(
                                    existing_pos['id'],
                                    close_price=trade_price,
                                    pnl=pnl
                                )
                            else:
                                # Partial close - reduce quantity
                                new_qty = existing_pos['quantity'] - int(qty)
                                self.supabase.update_position(
                                    existing_pos['id'],
                                    quantity=new_qty
                                )
                    
                    logger.info(f"Webhook trade and position saved to Supabase: {symbol} {action} {qty}")
                except Exception as e:
                    logger.error(f"Failed to save to Supabase: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Record the order in position tracker
            if action == 'buy':
                self.position_tracker.record_buy(symbol, qty, price)
            elif action == 'sell':
                # Only reset Fibonacci counter if position is fully closed
                # Check if position still exists after this sell
                try:
                    remaining_position = self.alpaca.get_position(symbol)
                    # Position still exists, don't reset counter yet
                    print(f"POSITION STILL OPEN: {symbol} - {remaining_position.qty} shares remaining")
                except:
                    # Position doesn't exist = fully closed, reset counter
                    self.position_tracker.record_sell(symbol)
                    print(f"POSITION FULLY CLOSED: {symbol} - Fibonacci counter reset")
            
            return {
                'success': True,
                'order_id': order.id,
                'symbol': order.symbol,
                'qty': float(order.qty),
                'side': order.side.value,
                'type': order.type.value,
                'status': order.status.value,
                'submitted_at': order.submitted_at.isoformat() if order.submitted_at else None,
                'fibonacci_position': self.position_tracker.get_buy_count(symbol) if action == 'buy' else None
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_account_summary(self):
        """Get account summary with positions"""
        try:
            account = self.alpaca.get_account()
            positions = self.alpaca.get_positions()
            
            positions_data = []
            for pos in positions:
                positions_data.append({
                    'symbol': pos.symbol,
                    'qty': float(pos.qty),
                    'avg_entry_price': float(pos.avg_entry_price),
                    'current_price': float(pos.current_price),
                    'market_value': float(pos.market_value),
                    'cost_basis': float(pos.cost_basis),
                    'unrealized_pl': float(pos.unrealized_pl),
                    'unrealized_plpc': float(pos.unrealized_plpc),
                    'side': pos.side.value
                })
            
            return {
                'success': True,
                'account': {
                    'equity': float(account.equity),
                    'cash': float(account.cash),
                    'buying_power': float(account.buying_power),
                    'portfolio_value': float(account.portfolio_value),
                    'last_equity': float(account.last_equity),
                    'status': account.status,
                    'pattern_day_trader': account.pattern_day_trader,
                    'trading_blocked': account.trading_blocked,
                    'account_blocked': account.account_blocked
                },
                'positions': positions_data,
                'total_positions': len(positions_data)
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_order_history(self, limit=50):
        """Get recent order history"""
        try:
            orders = self.alpaca.get_orders(status='all', limit=limit)
            
            orders_data = []
            for order in orders:
                orders_data.append({
                    'id': order.id,
                    'symbol': order.symbol,
                    'qty': float(order.qty),
                    'filled_qty': float(order.filled_qty) if order.filled_qty else 0,
                    'side': order.side.value,
                    'type': order.type.value,
                    'status': order.status.value,
                    'limit_price': float(order.limit_price) if order.limit_price else None,
                    'stop_price': float(order.stop_price) if order.stop_price else None,
                    'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None,
                    'submitted_at': order.submitted_at.isoformat() if order.submitted_at else None,
                    'filled_at': order.filled_at.isoformat() if order.filled_at else None
                })
            
            return {
                'success': True,
                'orders': orders_data
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
