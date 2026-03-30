from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from config import Config
from services.order_manager import OrderManager
from services.risk_manager import RiskManager
from services.alpaca_client import AlpacaClient
from services.options_trader import OptionsTrader
import logging
import os
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

from services.portfolio_analytics import PortfolioAnalytics
from services.rsi_scanner import RSIScanner

# Initialize services
order_manager = OrderManager()
alpaca_client = AlpacaClient()
risk_manager = RiskManager(alpaca_client)
portfolio_analytics = PortfolioAnalytics(alpaca_client)
options_trader = OptionsTrader(alpaca_client)
rsi_scanner = RSIScanner()

# Auto Profit Taker
from services.auto_profit_taker import get_auto_profit_taker
auto_profit_taker = get_auto_profit_taker(alpaca_client)

# In-memory webhook log storage
webhook_logs = []

@app.route('/deploy', methods=['POST'])
def auto_deploy():
    """Auto-deploy: pull latest code from GitHub and restart"""
    try:
        import subprocess
        # Pull latest from GitHub
        result = subprocess.run(
            ['git', 'pull', 'origin', 'main'],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, timeout=30
        )
        logger.info(f"Git pull: {result.stdout}")
        if result.returncode != 0:
            logger.error(f"Git pull error: {result.stderr}")
            return jsonify({'success': False, 'error': result.stderr}), 500

        # Restart the service (systemd will bring it back up)
        subprocess.Popen(['sudo', 'systemctl', 'restart', 'trading-bot'])
        return jsonify({'success': True, 'message': 'Deploying...', 'git': result.stdout.strip()})
    except Exception as e:
        logger.error(f"Deploy error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'paper_trading': Config().is_paper_trading
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView webhook endpoint"""
    webhook_log = {
        'timestamp': datetime.now().isoformat(),
        'payload': None,
        'response': None,
        'status': 'error',
        'source': request.headers.get('User-Agent', 'Unknown')
    }
    
    try:
        # Get webhook data
        data = request.json
        webhook_log['payload'] = data
        logger.info(f"Received webhook: {data}")
        
        symbol = data.get('symbol', '') if data else ''
        action = data.get('action', '') if data else ''
        qty = data.get('qty') or data.get('quantity', 0) if data else 0
        
        # Check if this is an options trade
        if data.get('asset_type') == 'option' or data.get('option_direction'):
            underlying = data.get('symbol', 'SPY')
            direction = data.get('option_direction', 'call')
            qty = int(data.get('qty', 1))
            side = data.get('side', 'buy')
            std_devs = float(data.get('std_devs', 2.5))
            
            order = options_trader.trade_0dte_option(underlying, direction, qty, side, std_devs)
            
            if order:
                result = {
                    'success': True,
                    'order_id': order.id,
                    'symbol': order.symbol,
                    'qty': float(order.qty),
                    'side': order.side.value,
                    'type': 'option',
                    'status': order.status.value
                }
            else:
                result = {'success': False, 'error': 'Failed to place option order'}
        else:
            result = order_manager.execute_webhook_order(data)
        
        webhook_log['response'] = result
        
        if result['success']:
            webhook_log['status'] = 'success'
            logger.info(f"Order executed successfully: {result}")
            webhook_logs.append(webhook_log)
            # Log to Supabase
            safe_result = {}
            for k,v in result.items():
                try:
                    safe_result[k] = str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                except:
                    safe_result[k] = str(v)
            _log_webhook_to_supabase(data, symbol, action, qty, 'success', safe_result, None, request.remote_addr)
            return jsonify(result), 200
        else:
            status = 'blocked' if 'PROFIT PROTECTION' in str(result.get('error', '')) else 'error'
            webhook_log['status'] = status
            logger.error(f"Order execution failed: {result}")
            webhook_logs.append(webhook_log)
            _log_webhook_to_supabase(data, symbol, action, qty, status, result, str(result.get('error', '')), request.remote_addr)
            return jsonify(result), 400
            
    except Exception as e:
        webhook_log['response'] = {'error': str(e)}
        webhook_log['status'] = 'error'
        logger.error(f"Webhook error: {str(e)}")
        webhook_logs.append(webhook_log)
        _log_webhook_to_supabase(data if 'data' in dir() else {}, symbol if 'symbol' in dir() else '', '', 0, 'error', None, str(e), request.remote_addr)
        return jsonify({'error': str(e)}), 500

def _log_webhook_to_supabase(payload, symbol, action, qty, status, response, error_msg, source_ip):
    """Helper to log webhook to Supabase without breaking the request"""
    try:
        if order_manager.supabase.is_connected():
            order_manager.supabase.log_webhook(payload, symbol, action, qty, status, response, error_msg, source_ip)
            logger.info(f"Webhook logged to Supabase: {symbol} {action} {status}")
        else:
            logger.warning("Supabase not connected - webhook not logged to DB")
    except Exception as e:
        logger.error(f"Failed to log webhook to Supabase: {e}")
        import traceback
        traceback.print_exc()

@app.route('/debug', methods=['GET'])
def debug_config():
    """Debug endpoint to check configuration"""
    try:
        import os
        from dotenv import load_dotenv
        
        # Force reload environment
        load_dotenv(override=True)
        
        # Get values directly from environment
        api_key = os.getenv('ALPACA_API_KEY')
        secret_key = os.getenv('ALPACA_SECRET_KEY')
        base_url = os.getenv('ALPACA_BASE_URL')
        
        # Also check Config class
        config = Config()
        
        return jsonify({
            'env_api_key': api_key,
            'env_secret_key': secret_key[:10] + '...' if secret_key else None,
            'env_base_url': base_url,
            'config_api_key': config.ALPACA_API_KEY,
            'config_secret_key': config.ALPACA_SECRET_KEY[:10] + '...' if config.ALPACA_SECRET_KEY else None,
            'config_base_url': config.ALPACA_BASE_URL,
            'is_paper': config.is_paper_trading,
            'trading_enabled': config.TRADING_ENABLED
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/account', methods=['GET'])
def get_account():
    """Get account summary"""
    try:
        result = order_manager.get_account_summary()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting account: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/positions', methods=['GET'])
def get_positions():
    """Get all positions"""
    try:
        positions = alpaca_client.get_positions()
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
        
        return jsonify({'success': True, 'positions': positions_data})
    except Exception as e:
        logger.error(f"Error getting positions: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders', methods=['GET'])
def get_orders():
    """Get order history, optionally filtered to today's orders only"""
    try:
        limit = request.args.get('limit', 50, type=int)
        status = request.args.get('status', 'all')
        today_only = request.args.get('today', 'false').lower() == 'true'
        
        if today_only:
            # Use Alpaca's 'after' filter to only get today's orders
            from datetime import timezone, timedelta
            now = datetime.now(timezone.utc)
            # Start of today in US/Eastern (market timezone)
            import zoneinfo
            try:
                eastern = zoneinfo.ZoneInfo('America/New_York')
            except Exception:
                import pytz
                eastern = pytz.timezone('America/New_York')
            
            now_eastern = datetime.now(eastern)
            start_of_today = now_eastern.replace(hour=0, minute=0, second=0, microsecond=0)
            
            orders = alpaca_client.get_orders(status='all', limit=limit, after=start_of_today)
            
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
            
            return jsonify({
                'success': True,
                'orders': orders_data,
                'date_filter': start_of_today.isoformat()
            })
        else:
            result = order_manager.get_order_history(limit=limit)
            return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting orders: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders/<order_id>', methods=['DELETE'])
def cancel_order(order_id):
    """Cancel specific order"""
    try:
        alpaca_client.cancel_order(order_id)
        return jsonify({'success': True, 'message': 'Order cancelled'})
    except Exception as e:
        logger.error(f"Error cancelling order: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/positions/<symbol>', methods=['DELETE'])
def close_position(symbol):
    """Close specific position"""
    try:
        alpaca_client.close_position(symbol.upper())
        return jsonify({'success': True, 'message': f'Position {symbol} closed'})
    except Exception as e:
        logger.error(f"Error closing position: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/risk-status', methods=['GET'])
def get_risk_status():
    """Get risk management status"""
    try:
        status = risk_manager.get_risk_status()
        return jsonify({'success': True, 'risk_status': status})
    except Exception as e:
        logger.error(f"Error getting risk status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/order', methods=['POST'])
def manual_order():
    """Manual order submission"""
    try:
        data = request.json
        result = order_manager.execute_webhook_order(data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error submitting manual order: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio-analytics', methods=['GET'])
def get_portfolio_analytics():
    """Get advanced portfolio analytics"""
    try:
        # Get account data
        account = alpaca_client.get_account()
        account_data = {
            'equity': float(account.equity),
            'cash': float(account.cash),
            'buying_power': float(account.buying_power)
        }
        
        # Get order history
        orders = alpaca_client.get_orders(status='all', limit=500)
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
                'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None,
                'submitted_at': order.submitted_at.isoformat() if order.submitted_at else None,
                'filled_at': order.filled_at.isoformat() if order.filled_at else None
            })
        
        # Calculate analytics (no exclusions - back to normal)
        analytics = portfolio_analytics.calculate_all_metrics(orders_data, account_data)
        
        return jsonify({'success': True, 'analytics': analytics})
    except Exception as e:
        logger.error(f"Error calculating portfolio analytics: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/connections', methods=['GET'])
def get_connections():
    """Get API connection status"""
    try:
        connections = {
            'alpaca': {
                'url': Config().ALPACA_BASE_URL,
                'status': 'connected',
                'lastCheck': datetime.now().isoformat(),
                'responseTime': 150
            },
            'marketData': {
                'url': 'https://data.alpaca.markets',
                'status': 'connected',
                'lastCheck': datetime.now().isoformat(),
                'responseTime': 200
            },
            'webhook': {
                'url': f'http://localhost:{Config().PORT}/webhook',
                'status': 'active',
                'lastCheck': datetime.now().isoformat(),
                'responseTime': 50
            }
        }
        return jsonify({'success': True, 'connections': connections})
    except Exception as e:
        logger.error(f"Error getting connections: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/webhooks', methods=['GET'])
def get_webhook_logs():
    """Get webhook logs from Supabase"""
    try:
        from services.supabase_client import SupabaseClient
        sb = SupabaseClient()
        
        if sb.is_connected():
            logs = sb.get_webhook_log(limit=50)
            if logs:
                webhooks = []
                for log in logs:
                    webhooks.append({
                        'timestamp': log.get('received_at'),
                        'payload': log.get('payload'),
                        'symbol': log.get('symbol'),
                        'action': log.get('action'),
                        'status': log.get('status'),
                        'response': log.get('response'),
                        'error': log.get('error_message'),
                    })
                return jsonify({'success': True, 'webhooks': webhooks, 'total': len(webhooks), 'source': 'supabase'})
        
        # Fallback to in-memory
        recent_logs = webhook_logs[-50:][::-1]
        return jsonify({
            'success': True, 
            'webhooks': recent_logs,
            'total': len(webhook_logs),
            'source': 'memory'
        })
    except Exception as e:
        logger.error(f"Error getting webhook logs: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/closed-positions', methods=['GET'])
def get_closed_positions():
    """Get closed positions from Supabase (accurate tracking)"""
    try:
        limit = request.args.get('limit', 100, type=int)
        source = request.args.get('source', 'all')  # 'all', 'webhook', or 'manual'
        
        # Try to get from Supabase first
        from services.supabase_client import SupabaseClient
        supabase = SupabaseClient()
        
        if supabase.is_connected():
            # Get closed positions from Supabase
            try:
                query = supabase.client.from_('positions').select('*').eq('status', 'closed')
                
                # Filter by source if specified
                if source != 'all':
                    query = query.eq('source', source)
                
                response = query.order('closed_at', desc=True).limit(limit).execute()
                
                positions = []
                for pos in response.data:
                    positions.append({
                        'symbol': pos['symbol'],
                        'qty': pos['quantity'],
                        'open_price': float(pos['entry_price']),
                        'close_price': float(pos['close_price']) if pos['close_price'] else 0,
                        'pnl': float(pos['pnl']) if pos['pnl'] else 0,
                        'pnl_pct': ((float(pos['close_price']) - float(pos['entry_price'])) / float(pos['entry_price']) * 100) if pos['close_price'] and pos['entry_price'] else 0,
                        'opened_at': pos['opened_at'],
                        'closed_at': pos['closed_at'],
                        'source': pos.get('source', 'manual')  # Include source
                    })
                
                logger.info(f"Retrieved {len(positions)} closed positions from Supabase (source: {source})")
                
                if positions:
                    return jsonify({
                        'success': True,
                        'positions': positions,
                        'total': len(positions),
                        'source': 'supabase',
                        'filter': source
                    })
                # If Supabase is empty, fall through to Alpaca
            except Exception as e:
                logger.error(f"Error getting positions from Supabase: {e}")
                # Fall through to Alpaca method
        
        # Fallback: Use Alpaca orders (less accurate due to old test data)
        logger.warning("Using Alpaca orders for closed positions (may include old test data)")
        
        days = request.args.get('days', 1, type=int)  # Default: today only
        from datetime import timezone, timedelta
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        orders = alpaca_client.get_orders(status='all', limit=1000)
        recent_orders = [o for o in orders if o.filled_at and o.filled_at >= cutoff_date]
        
        positions_map = {}
        min_datetime = datetime.min.replace(tzinfo=timezone.utc)
        
        for order in sorted(recent_orders, key=lambda x: x.filled_at if x.filled_at else min_datetime):
            if order.status.value != 'filled':
                continue
            
            symbol = order.symbol
            side = order.side.value
            qty = float(order.filled_qty) if order.filled_qty else 0
            price = float(order.filled_avg_price) if order.filled_avg_price else 0
            filled_at = order.filled_at
            
            if symbol not in positions_map:
                positions_map[symbol] = {
                    'buy_queue': [],
                    'closed_positions': []
                }
            
            if side == 'buy':
                positions_map[symbol]['buy_queue'].append({
                    'qty': qty,
                    'price': price,
                    'time': filled_at
                })
            elif side == 'sell':
                sell_qty_remaining = qty
                sell_price = price
                sell_time = filled_at
                
                while sell_qty_remaining > 0 and positions_map[symbol]['buy_queue']:
                    buy = positions_map[symbol]['buy_queue'][0]
                    matched_qty = min(sell_qty_remaining, buy['qty'])
                    pnl = (sell_price - buy['price']) * matched_qty
                    pnl_pct = ((sell_price - buy['price']) / buy['price']) * 100 if buy['price'] > 0 else 0
                    
                    positions_map[symbol]['closed_positions'].append({
                        'symbol': symbol,
                        'qty': matched_qty,
                        'open_price': round(buy['price'], 2),
                        'close_price': round(sell_price, 2),
                        'pnl': round(pnl, 2),
                        'pnl_pct': round(pnl_pct, 2),
                        'opened_at': buy['time'].isoformat() if buy['time'] else None,
                        'closed_at': sell_time.isoformat() if sell_time else None,
                        'source': 'unknown'  # Can't determine source from Alpaca orders
                    })
                    
                    sell_qty_remaining -= matched_qty
                    positions_map[symbol]['buy_queue'][0]['qty'] -= matched_qty
                    
                    if positions_map[symbol]['buy_queue'][0]['qty'] <= 0:
                        positions_map[symbol]['buy_queue'].pop(0)
        
        all_closed_positions = []
        for symbol_data in positions_map.values():
            all_closed_positions.extend(symbol_data['closed_positions'])
        
        all_closed_positions.sort(key=lambda x: x['closed_at'] if x['closed_at'] else '', reverse=True)
        limited_positions = all_closed_positions[:limit]
        
        return jsonify({
            'success': True,
            'positions': limited_positions,
            'total': len(all_closed_positions),
            'source': 'alpaca_orders',
            'days_filter': days,
            'filter': source,
            'warning': 'Using Alpaca orders - may include old test data. New trades will be tracked accurately in Supabase.'
        })
        
    except Exception as e:
        logger.error(f"Error getting closed positions: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/daily-performance', methods=['GET'])
def get_daily_performance():
    """Get today's performance data from Alpaca (source of truth).
    
    Combines portfolio history for P&L with today's filled orders.
    This ensures data persists correctly across page refreshes.
    """
    try:
        import zoneinfo
        try:
            eastern = zoneinfo.ZoneInfo('America/New_York')
        except Exception:
            import pytz
            eastern = pytz.timezone('America/New_York')
        
        now_eastern = datetime.now(eastern)
        start_of_today = now_eastern.replace(hour=0, minute=0, second=0, microsecond=0)
        today_str = now_eastern.strftime('%Y-%m-%d')
        
        # 1) Get today's filled orders from Alpaca (with date filter)
        all_orders = alpaca_client.get_orders(status='all', limit=500, after=start_of_today)
        
        filled_orders = []
        for order in all_orders:
            if order.status.value != 'filled':
                continue
            filled_orders.append({
                'id': order.id,
                'symbol': order.symbol,
                'qty': float(order.qty),
                'filled_qty': float(order.filled_qty) if order.filled_qty else 0,
                'side': order.side.value,
                'type': order.type.value,
                'status': order.status.value,
                'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None,
                'submitted_at': order.submitted_at.isoformat() if order.submitted_at else None,
                'filled_at': order.filled_at.isoformat() if order.filled_at else None
            })
        
        buy_orders = [o for o in filled_orders if o['side'] == 'buy']
        sell_orders = [o for o in filled_orders if o['side'] == 'sell']
        
        total_buy_capital = sum((o['filled_avg_price'] or 0) * (o['filled_qty'] or 0) for o in buy_orders)
        
        # 2) Try to get closed positions from Supabase for accurate P&L
        closed_positions = []
        supabase_available = False
        try:
            from services.supabase_client import SupabaseClient
            supabase = SupabaseClient()
            if supabase.is_connected():
                supabase_available = True
                query = supabase.client.from_('positions').select('*').eq('status', 'closed')
                response = query.order('closed_at', desc=True).limit(200).execute()
                
                for pos in response.data:
                    closed_at = pos.get('closed_at', '')
                    if closed_at and closed_at[:10] == today_str:
                        entry_price = float(pos['entry_price']) if pos.get('entry_price') else 0
                        close_price = float(pos['close_price']) if pos.get('close_price') else 0
                        qty = pos.get('quantity', 0)
                        pnl = float(pos['pnl']) if pos.get('pnl') else 0
                        pnl_pct = ((close_price - entry_price) / entry_price * 100) if entry_price else 0
                        
                        closed_positions.append({
                            'symbol': pos['symbol'],
                            'qty': qty,
                            'open_price': entry_price,
                            'close_price': close_price,
                            'pnl': pnl,
                            'pnl_pct': round(pnl_pct, 2),
                            'opened_at': pos.get('opened_at'),
                            'closed_at': closed_at,
                            'source': pos.get('source', 'manual')
                        })
        except Exception as e:
            logger.warning(f"Supabase unavailable for daily performance: {e}")
        
        # 3) If no Supabase data, reconstruct closed positions from Alpaca orders
        if not closed_positions:
            # Match buy/sell pairs from today's orders
            buys_by_symbol = {}
            for o in buy_orders:
                sym = o['symbol']
                if sym not in buys_by_symbol:
                    buys_by_symbol[sym] = []
                buys_by_symbol[sym].append(o)
            
            for o in sell_orders:
                sym = o['symbol']
                if sym in buys_by_symbol and buys_by_symbol[sym]:
                    buy = buys_by_symbol[sym].pop(0)
                    buy_price = buy['filled_avg_price'] or 0
                    sell_price = o['filled_avg_price'] or 0
                    matched_qty = min(buy['filled_qty'], o['filled_qty'])
                    pnl = (sell_price - buy_price) * matched_qty
                    pnl_pct = ((sell_price - buy_price) / buy_price * 100) if buy_price else 0
                    
                    closed_positions.append({
                        'symbol': sym,
                        'qty': matched_qty,
                        'open_price': round(buy_price, 2),
                        'close_price': round(sell_price, 2),
                        'pnl': round(pnl, 2),
                        'pnl_pct': round(pnl_pct, 2),
                        'opened_at': buy['filled_at'],
                        'closed_at': o['filled_at'],
                        'source': 'alpaca'
                    })
        
        # 4) Calculate summary metrics
        total_pnl = sum(p['pnl'] for p in closed_positions)
        capital_deployed = sum(p['open_price'] * p['qty'] for p in closed_positions)
        return_on_capital = (total_pnl / capital_deployed * 100) if capital_deployed > 0 else 0
        
        return jsonify({
            'success': True,
            'date': today_str,
            'summary': {
                'total_pnl': round(total_pnl, 2),
                'capital_deployed': round(capital_deployed, 2),
                'return_on_capital': round(return_on_capital, 2),
                'closed_trade_count': len(closed_positions),
                'buy_order_count': len(buy_orders),
                'total_buy_capital': round(total_buy_capital, 2),
            },
            'closed_positions': closed_positions,
            'buy_orders': buy_orders,
            'source': 'supabase' if supabase_available else 'alpaca',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting daily performance: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio-history', methods=['GET'])
def get_portfolio_history():
    """Get portfolio history with P&L directly from Alpaca REST API"""
    try:
        import requests as req
        period = request.args.get('period', '1M')
        timeframe = request.args.get('timeframe', '1D')
        
        config = Config()
        base = config.ALPACA_BASE_URL.rstrip('/v2').rstrip('/')
        url = f"{base}/v2/account/portfolio/history"
        headers = {
            'APCA-API-KEY-ID': config.ALPACA_API_KEY,
            'APCA-API-SECRET-KEY': config.ALPACA_SECRET_KEY,
        }
        params = {'period': period, 'timeframe': timeframe, 'extended_hours': 'false'}
        
        resp = req.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        return jsonify({
            'success': True,
            'history': {
                'timestamp': data.get('timestamp', []),
                'equity': data.get('equity', []),
                'profit_loss': data.get('profit_loss', []),
                'profit_loss_pct': data.get('profit_loss_pct', []),
                'base_value': data.get('base_value', 0),
                'timeframe': data.get('timeframe', '1D'),
            },
            'source': 'alpaca'
        })
    except Exception as e:
        logger.error(f"Error getting portfolio history: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/account-activities', methods=['GET'])
def get_account_activities():
    """Get account activities (fills, transactions) from Alpaca"""
    try:
        from alpaca.trading.requests import GetAccountActivitiesRequest
        from alpaca.trading.enums import ActivityType
        
        # Get fills (executed trades)
        activities = alpaca_client.trading_client.get_account_activities(
            GetAccountActivitiesRequest(
                activity_types=[ActivityType.FILL],
                page_size=100
            )
        )
        
        activities_data = []
        for activity in activities:
            activities_data.append({
                'id': activity.id,
                'activity_type': activity.activity_type,
                'transaction_time': activity.transaction_time.isoformat() if activity.transaction_time else None,
                'type': activity.type if hasattr(activity, 'type') else None,
                'price': float(activity.price) if hasattr(activity, 'price') and activity.price else None,
                'qty': float(activity.qty) if hasattr(activity, 'qty') and activity.qty else None,
                'side': activity.side if hasattr(activity, 'side') else None,
                'symbol': activity.symbol if hasattr(activity, 'symbol') else None,
                'leaves_qty': float(activity.leaves_qty) if hasattr(activity, 'leaves_qty') and activity.leaves_qty else None,
                'order_id': activity.order_id if hasattr(activity, 'order_id') else None,
                'cum_qty': float(activity.cum_qty) if hasattr(activity, 'cum_qty') and activity.cum_qty else None,
                'order_status': activity.order_status if hasattr(activity, 'order_status') else None
            })
        
        return jsonify({
            'success': True,
            'activities': activities_data,
            'total': len(activities_data),
            'source': 'alpaca'
        })
    except Exception as e:
        logger.error(f"Error getting account activities: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# OLD PORTFOLIO HISTORY ENDPOINT - REMOVED (replaced with Alpaca version above)

@app.route('/api/manual-order', methods=['POST'])
def submit_manual_order():
    """Submit manual order from dashboard"""
    try:
        data = request.json
        logger.info(f"Manual order submitted: {data}")
        
        # Use the existing order manager
        result = order_manager.execute_webhook_order(data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error submitting manual order: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/options/positions', methods=['GET'])
def get_option_positions():
    """Get all open option positions"""
    try:
        positions = options_trader.get_option_positions()
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
        
        return jsonify({'success': True, 'positions': positions_data})
    except Exception as e:
        logger.error(f"Error getting option positions: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/options/trade-0dte', methods=['POST'])
def trade_0dte_option():
    """Trade 0DTE option with intelligent strike selection"""
    try:
        data = request.json
        logger.info(f"Received 0DTE option trade request: {data}")
        
        underlying = data.get('underlying', 'SPY')
        direction = data.get('direction', 'call')  # 'call' or 'put'
        qty = int(data.get('qty', 1))
        side = data.get('side', 'buy')  # 'buy' or 'sell'
        std_devs = float(data.get('std_devs', 2.5))  # Standard deviations for OTM when selling
        
        logger.info(f"Trading 0DTE option: {underlying} {direction} {side} {qty} contracts, std_devs={std_devs}")
        
        order = options_trader.trade_0dte_option(underlying, direction, qty, side, std_devs)
        
        if order:
            logger.info(f"Option order placed successfully: {order.id}")
            return jsonify({
                'success': True,
                'order_id': order.id,
                'symbol': order.symbol,
                'qty': float(order.qty),
                'side': order.side.value,
                'status': order.status.value
            })
        else:
            error_msg = 'Failed to place option order - check backend logs for details'
            logger.error(error_msg)
            return jsonify({'success': False, 'error': error_msg}), 400
            
    except Exception as e:
        error_msg = f"Error trading 0DTE option: {str(e)}"
        logger.error(error_msg)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/options/close/<symbol>', methods=['DELETE'])
def close_option_position(symbol):
    """Close option position"""
    try:
        result = options_trader.close_option_position(symbol)
        return jsonify({'success': True, 'message': f'Option position {symbol} closed'})
    except Exception as e:
        logger.error(f"Error closing option position: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/quote/<symbol>', methods=['GET'])
def get_quote(symbol):
    """Get latest quote for a symbol"""
    try:
        quote = alpaca_client.get_latest_quote(symbol.upper())
        if quote:
            return jsonify({
                'success': True,
                'symbol': symbol.upper(),
                'ask_price': float(quote.ask_price) if quote.ask_price else None,
                'bid_price': float(quote.bid_price) if quote.bid_price else None,
                'ask_size': float(quote.ask_size) if quote.ask_size else None,
                'bid_size': float(quote.bid_size) if quote.bid_size else None,
                'timestamp': quote.timestamp.isoformat() if quote.timestamp else None
            })
        else:
            return jsonify({'success': False, 'error': 'No quote found'}), 404
    except Exception as e:
        logger.error(f"Error getting quote: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/options/chain', methods=['GET'])
def get_option_chain():
    """Get option chain for a symbol with live quotes"""
    try:
        underlying = request.args.get('symbol', 'SPY').upper()
        expiration = request.args.get('expiration', '')
        option_type = request.args.get('type', 'call')
        expirations_only = request.args.get('expirations_only', 'false') == 'true'

        import requests as req
        headers = {
            'APCA-API-KEY-ID': Config().ALPACA_API_KEY,
            'APCA-API-SECRET-KEY': Config().ALPACA_SECRET_KEY
        }

        if expirations_only:
            from datetime import timedelta
            today = datetime.now().strftime('%Y-%m-%d')
            far_out = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
            params = {'underlying_symbols': underlying, 'type': option_type, 'status': 'active',
                      'expiration_date_gte': today, 'expiration_date_lte': far_out, 'limit': 10000}
            resp = req.get('https://paper-api.alpaca.markets/v2/options/contracts', headers=headers, params=params)
            resp.raise_for_status()
            contracts = resp.json().get('option_contracts', [])
            return jsonify({'success': True, 'expirations': sorted(set(c['expiration_date'] for c in contracts))})

        if not expiration:
            expiration = datetime.now().strftime('%Y-%m-%d')

        params = {'underlying_symbols': underlying, 'type': option_type, 'status': 'active',
                  'expiration_date': expiration, 'limit': 250}
        resp = req.get('https://paper-api.alpaca.markets/v2/options/contracts', headers=headers, params=params)
        resp.raise_for_status()
        contracts = resp.json().get('option_contracts', [])
        if not contracts:
            return jsonify({'success': True, 'chain': [], 'expirations': []})

        contracts.sort(key=lambda c: float(c['strike_price']))
        symbols = [c['symbol'] for c in contracts]
        snapshots = {}
        for i in range(0, len(symbols), 100):
            batch = ','.join(symbols[i:i+100])
            snap_resp = req.get(f'https://data.alpaca.markets/v1beta1/options/snapshots?symbols={batch}&feed=indicative', headers=headers)
            if snap_resp.status_code == 200:
                snapshots.update(snap_resp.json().get('snapshots', {}))

        underlying_price = None
        try:
            tr = req.get(f'https://data.alpaca.markets/v2/stocks/{underlying}/trades/latest', headers=headers)
            if tr.status_code == 200:
                underlying_price = tr.json().get('trade', {}).get('p')
        except Exception:
            pass

        chain = []
        for c in contracts:
            snap = snapshots.get(c['symbol'], {})
            quote = snap.get('latestQuote', {})
            trade = snap.get('latestTrade', {})
            chain.append({'symbol': c['symbol'], 'name': c.get('name', ''), 'strike': float(c['strike_price']),
                          'expiration': c['expiration_date'], 'type': c['type'],
                          'bid': quote.get('bp', 0), 'ask': quote.get('ap', 0), 'last': trade.get('p', 0),
                          'volume': snap.get('dailyBar', {}).get('v', 0), 'open_interest': c.get('open_interest')})

        return jsonify({'success': True, 'chain': chain, 'underlying_price': underlying_price, 'selected_expiration': expiration})
    except Exception as e:
        logger.error(f"Error getting option chain: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/options/order', methods=['POST'])
def submit_option_order():
    """Submit an option order for a specific contract symbol"""
    try:
        data = request.json
        symbol = data.get('symbol')
        qty = int(data.get('qty', 1))
        side = data.get('side', 'buy')
        order_type = data.get('order_type', 'market')
        limit_price = data.get('limit_price')

        if not symbol:
            return jsonify({'success': False, 'error': 'symbol is required'}), 400

        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
        if order_type == 'limit' and limit_price:
            order_data = LimitOrderRequest(symbol=symbol, qty=qty, side=order_side,
                                           time_in_force=TimeInForce.DAY, limit_price=round(float(limit_price), 2))
        else:
            order_data = MarketOrderRequest(symbol=symbol, qty=qty, side=order_side, time_in_force=TimeInForce.DAY)

        order = alpaca_client.trading_client.submit_order(order_data)
        return jsonify({'success': True, 'order_id': order.id, 'symbol': order.symbol,
                        'qty': float(order.qty), 'side': order.side.value, 'status': order.status.value})
    except Exception as e:
        logger.error(f"Error submitting option order: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/notes', methods=['GET'])
def get_notes():
    """Get saved notes from file"""
    try:
        notes_file = 'trading_notes.txt'
        if os.path.exists(notes_file):
            with open(notes_file, 'r') as f:
                notes = f.read()
            return jsonify({'success': True, 'notes': notes})
        else:
            return jsonify({'success': True, 'notes': ''})
    except Exception as e:
        logger.error(f"Error reading notes: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/notes', methods=['POST'])
def save_notes():
    """Save notes to file"""
    try:
        data = request.json
        notes = data.get('notes', '')
        
        notes_file = 'trading_notes.txt'
        with open(notes_file, 'w') as f:
            f.write(notes)
        
        return jsonify({'success': True, 'message': 'Notes saved successfully'})
    except Exception as e:
        logger.error(f"Error saving notes: {str(e)}")
        return jsonify({'error': str(e)}), 500

# SCREENER ENDPOINTS - COMMENTED OUT (from autonomous trader)
# @app.route('/api/screener/assets', methods=['GET'])
# @app.route('/api/screener/screen', methods=['POST'])
# @app.route('/api/screener/asset/<symbol>', methods=['GET'])
# @app.route('/api/auto-scanner/status', methods=['GET'])
# @app.route('/api/auto-scanner/start', methods=['POST'])
# @app.route('/api/auto-scanner/stop', methods=['POST'])
# @app.route('/api/auto-scanner/criteria', methods=['GET'])
# @app.route('/api/auto-scanner/criteria', methods=['POST'])
# @app.route('/api/smart-screener/run', methods=['POST'])
# @app.route('/api/smart-screener/settings', methods=['GET'])
# @app.route('/api/smart-screener/settings', methods=['POST'])
# @app.route('/api/smart-screener/buy-opportunities', methods=['GET'])
# @app.route('/api/smart-screener/sell-opportunities', methods=['GET'])

@app.route('/api/position-tracker/<symbol>', methods=['GET'])
def get_position_tracker_info(symbol):
    """Get Fibonacci position tracking info for a symbol"""
    try:
        info = order_manager.position_tracker.get_position_info(symbol.upper())
        return jsonify({'success': True, 'info': info})
    except Exception as e:
        logger.error(f"Error getting position tracker info: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/position-tracker', methods=['GET'])
def get_all_tracked_positions():
    """Get all tracked positions"""
    try:
        symbols = order_manager.position_tracker.get_all_tracked_symbols()
        tracked_positions = {}
        
        for symbol in symbols:
            tracked_positions[symbol] = order_manager.position_tracker.get_position_info(symbol)
        
        return jsonify({'success': True, 'positions': tracked_positions})
    except Exception as e:
        logger.error(f"Error getting tracked positions: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/position-tracker/<symbol>', methods=['DELETE'])
def reset_position_tracker(symbol):
    """Reset position tracking for a symbol"""
    try:
        order_manager.position_tracker.reset_symbol(symbol.upper())
        return jsonify({'success': True, 'message': f'Reset tracking for {symbol}'})
    except Exception as e:
        logger.error(f"Error resetting position tracker: {str(e)}")
        return jsonify({'error': str(e)}), 500

# =====================================================
# RSI SCANNER ENDPOINTS

@app.route('/api/rsi-scanner/scan', methods=['POST'])
def run_rsi_scan():
    """Run RSI scan on Magnificent 7"""
    try:
        results = rsi_scanner.scan_all()
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error running RSI scan: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/rsi-scanner/status', methods=['GET'])
def get_rsi_scanner_status():
    """Get RSI scanner status"""
    try:
        status = rsi_scanner.get_status()
        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        logger.error(f"Error getting RSI scanner status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/rsi-scanner/settings', methods=['POST'])
def update_rsi_scanner_settings():
    """Update RSI scanner settings"""
    try:
        settings = request.json
        rsi_scanner.update_settings(settings)
        return jsonify({
            'success': True,
            'settings': rsi_scanner.get_status()
        })
    except Exception as e:
        logger.error(f"Error updating RSI scanner settings: {str(e)}")
        return jsonify({'error': str(e)}), 500

# =====================================================
# QUOTE-BASED RSI SCANNER ENDPOINTS (Real-Time Quotes)

@app.route('/api/quote-scanner/start', methods=['POST'])
def start_quote_scanner():
    """Start quote-based scanner (real-time)"""
    try:
        from services.quote_based_rsi_scanner import get_quote_scanner
        import asyncio
        
        scanner = get_quote_scanner()
        
        # Update settings if provided
        if request.json:
            scanner.update_settings(request.json)
        
        # Start in background thread
        def run_scanner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(scanner.run_continuous(interval=60))
        
        import threading
        thread = threading.Thread(target=run_scanner, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Quote-based scanner started',
            'status': scanner.get_status()
        })
    except Exception as e:
        logger.error(f"Error starting quote scanner: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/quote-scanner/stop', methods=['POST'])
def stop_quote_scanner():
    """Stop quote-based scanner"""
    try:
        from services.quote_based_rsi_scanner import get_quote_scanner
        
        scanner = get_quote_scanner()
        scanner.stop()
        
        return jsonify({
            'success': True,
            'message': 'Quote-based scanner stopped',
            'status': scanner.get_status()
        })
    except Exception as e:
        logger.error(f"Error stopping quote scanner: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/quote-scanner/scan', methods=['POST'])
def run_quote_scan():
    """Run single quote-based scan"""
    try:
        from services.quote_based_rsi_scanner import get_quote_scanner
        
        scanner = get_quote_scanner()
        results = scanner.scan_once()
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error running quote scan: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/quote-scanner/status', methods=['GET'])
def get_quote_scanner_status():
    """Get quote-based scanner status"""
    try:
        from services.quote_based_rsi_scanner import get_quote_scanner
        
        scanner = get_quote_scanner()
        status = scanner.get_status()
        
        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        logger.error(f"Error getting quote scanner status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/quote-scanner/settings', methods=['POST'])
def update_quote_scanner_settings():
    """Update quote-based scanner settings"""
    try:
        from services.quote_based_rsi_scanner import get_quote_scanner
        
        scanner = get_quote_scanner()
        settings = request.json
        scanner.update_settings(settings)
        
        return jsonify({
            'success': True,
            'message': 'Settings updated',
            'status': scanner.get_status()
        })
    except Exception as e:
        logger.error(f"Error updating quote scanner settings: {str(e)}")
        return jsonify({'error': str(e)}), 500

# =====================================================
# STREAMING RSI SCANNER ENDPOINTS (WebSocket Real-Time)

@app.route('/api/streaming-scanner/start', methods=['POST'])
def start_streaming_scanner():
    """Start WebSocket streaming scanner"""
    try:
        from services.streaming_rsi_scanner import get_streaming_scanner
        import asyncio
        
        scanner = get_streaming_scanner()
        
        # Update settings if provided
        if request.json:
            scanner.update_settings(request.json)
        
        # Start in background thread
        def run_scanner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(scanner.start())
        
        import threading
        thread = threading.Thread(target=run_scanner, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Streaming scanner started',
            'status': scanner.get_status()
        })
    except Exception as e:
        logger.error(f"Error starting streaming scanner: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/streaming-scanner/stop', methods=['POST'])
def stop_streaming_scanner():
    """Stop WebSocket streaming scanner"""
    try:
        from services.streaming_rsi_scanner import get_streaming_scanner
        import asyncio
        
        scanner = get_streaming_scanner()
        
        # Stop scanner
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(scanner.stop())
        
        return jsonify({
            'success': True,
            'message': 'Streaming scanner stopped',
            'status': scanner.get_status()
        })
    except Exception as e:
        logger.error(f"Error stopping streaming scanner: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/streaming-scanner/status', methods=['GET'])
def get_streaming_scanner_status():
    """Get streaming scanner status"""
    try:
        from services.streaming_rsi_scanner import get_streaming_scanner
        
        scanner = get_streaming_scanner()
        status = scanner.get_status()
        
        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        logger.error(f"Error getting streaming scanner status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/streaming-scanner/settings', methods=['POST'])
def update_streaming_scanner_settings():
    """Update streaming scanner settings"""
    try:
        from services.streaming_rsi_scanner import get_streaming_scanner
        
        scanner = get_streaming_scanner()
        settings = request.json
        scanner.update_settings(settings)
        
        return jsonify({
            'success': True,
            'message': 'Settings updated',
            'status': scanner.get_status()
        })
    except Exception as e:
        logger.error(f"Error updating streaming scanner settings: {str(e)}")
        return jsonify({'error': str(e)}), 500

# =====================================================
# AUTO RSI SCANNER ENDPOINTS (Continuous Mode)

@app.route('/api/auto-scanner/start', methods=['POST'])
def start_auto_scanner():
    """Start continuous auto scanner"""
    try:
        from services.auto_rsi_scanner import get_auto_scanner
        
        auto_scanner = get_auto_scanner()
        
        # Update settings if provided
        if request.json:
            auto_scanner.update_settings(request.json)
        
        success = auto_scanner.start()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Auto scanner started',
                'status': auto_scanner.get_status()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Auto scanner is already running',
                'status': auto_scanner.get_status()
            })
    except Exception as e:
        logger.error(f"Error starting auto scanner: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/auto-scanner/stop', methods=['POST'])
def stop_auto_scanner():
    """Stop continuous auto scanner"""
    try:
        from services.auto_rsi_scanner import get_auto_scanner
        
        auto_scanner = get_auto_scanner()
        success = auto_scanner.stop()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Auto scanner stopped',
                'status': auto_scanner.get_status()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Auto scanner is not running',
                'status': auto_scanner.get_status()
            })
    except Exception as e:
        logger.error(f"Error stopping auto scanner: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auto-scanner/status', methods=['GET'])
def get_auto_scanner_status():
    """Get auto scanner status"""
    try:
        from services.auto_rsi_scanner import get_auto_scanner
        
        auto_scanner = get_auto_scanner()
        status = auto_scanner.get_status()
        status['is_healthy'] = auto_scanner.is_healthy()
        
        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        logger.error(f"Error getting auto scanner status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auto-scanner/settings', methods=['POST'])
def update_auto_scanner_settings():
    """Update auto scanner settings"""
    try:
        from services.auto_rsi_scanner import get_auto_scanner
        
        auto_scanner = get_auto_scanner()
        settings = request.json
        auto_scanner.update_settings(settings)
        
        return jsonify({
            'success': True,
            'message': 'Settings updated',
            'status': auto_scanner.get_status()
        })
    except Exception as e:
        logger.error(f"Error updating auto scanner settings: {str(e)}")
        return jsonify({'error': str(e)}), 500

# =====================================================
# AUTONOMOUS TRADING ENDPOINTS - COMMENTED OUT
# =====================================================

@app.route('/api/autonomous/config', methods=['GET'])
def get_autonomous_config():
    """Get autonomous trading configuration"""
    try:
        from services.supabase_client import SupabaseClient
        supabase = SupabaseClient()
        
        result = supabase.client.table('auto_trading_config').select('*').limit(1).execute()
        
        if result.data:
            return jsonify({'success': True, 'config': result.data[0]})
        else:
            return jsonify({'success': False, 'error': 'No config found'}), 404
    except Exception as e:
        logger.error(f"Error getting autonomous config: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/autonomous/config', methods=['PUT'])
def update_autonomous_config():
    """Update autonomous trading configuration"""
    try:
        from services.supabase_client import SupabaseClient
        supabase = SupabaseClient()
        
        config_data = request.json
        
        # Update the config (there should only be one row)
        result = supabase.client.table('auto_trading_config').update(config_data).eq('id', config_data.get('id')).execute()
        
        return jsonify({'success': True, 'config': result.data[0] if result.data else config_data})
    except Exception as e:
        logger.error(f"Error updating autonomous config: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/autonomous/opportunities', methods=['GET'])
def get_autonomous_opportunities():
    """Get current trading opportunities from stock scores"""
    try:
        from services.supabase_client import SupabaseClient
        supabase = SupabaseClient()
        
        # Get today's top opportunities
        from datetime import date
        today = date.today().isoformat()
        
        result = supabase.client.table('stock_scores')\
            .select('*')\
            .eq('scan_date', today)\
            .in_('signal', ['STRONG_BUY', 'BUY'])\
            .order('total_score', desc=True)\
            .limit(20)\
            .execute()
        
        return jsonify({
            'success': True,
            'opportunities': result.data,
            'total': len(result.data)
        })
    except Exception as e:
        logger.error(f"Error getting opportunities: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/autonomous/signals', methods=['GET'])
def get_trading_signals():
    """Get recent trading signals"""
    try:
        from services.supabase_client import SupabaseClient
        supabase = SupabaseClient()
        
        status = request.args.get('status', 'all')
        limit = request.args.get('limit', 50, type=int)
        
        query = supabase.client.table('trading_signals').select('*')
        
        if status != 'all':
            query = query.eq('status', status.upper())
        
        result = query.order('created_at', desc=True).limit(limit).execute()
        
        return jsonify({
            'success': True,
            'signals': result.data,
            'total': len(result.data)
        })
    except Exception as e:
        logger.error(f"Error getting signals: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/autonomous/run-scan', methods=['POST'])
def run_autonomous_scan():
    """Manually trigger an autonomous scan"""
    try:
        from services.autonomous_trader import AutonomousTrader
        import asyncio
        
        trader = AutonomousTrader()
        
        # Run one cycle
        asyncio.run(trader.run_cycle())
        
        return jsonify({
            'success': True,
            'message': 'Scan completed successfully'
        })
    except Exception as e:
        logger.error(f"Error running scan: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/autonomous/system-logs', methods=['GET'])
def get_system_logs():
    """Get system activity logs"""
    try:
        from services.supabase_client import SupabaseClient
        supabase = SupabaseClient()
        
        limit = request.args.get('limit', 100, type=int)
        level = request.args.get('level', 'all')
        component = request.args.get('component', 'all')
        
        query = supabase.client.table('system_logs').select('*')
        
        if level != 'all':
            query = query.eq('log_level', level.upper())
        
        if component != 'all':
            query = query.eq('component', component.upper())
        
        result = query.order('created_at', desc=True).limit(limit).execute()
        
        return jsonify({
            'success': True,
            'logs': result.data,
            'total': len(result.data)
        })
    except Exception as e:
        logger.error(f"Error getting system logs: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/autonomous/performance', methods=['GET'])
def get_autonomous_performance():
    """Get autonomous trading performance metrics"""
    try:
        from services.supabase_client import SupabaseClient
        supabase = SupabaseClient()
        
        days = request.args.get('days', 30, type=int)
        
        # Get performance metrics
        result = supabase.client.table('performance_metrics')\
            .select('*')\
            .order('date', desc=True)\
            .limit(days)\
            .execute()
        
        return jsonify({
            'success': True,
            'metrics': result.data,
            'total': len(result.data)
        })
    except Exception as e:
        logger.error(f"Error getting performance: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================
# STRATEGY SETTINGS API - Supabase-backed, real-time
# ============================================================

import json as _json

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.json')

def _load_settings_file():
    """Load settings from local JSON file, falling back to .env defaults"""
    config = Config()
    defaults = {
        'trading_enabled': config._DEFAULTS.get('trading_enabled', True),
        'fibonacci_enabled': config._DEFAULTS.get('fibonacci_enabled', True),
        'fibonacci_base': config._DEFAULTS.get('fibonacci_base', 0.1),
        'fibonacci_max_iterations': config._DEFAULTS.get('fibonacci_max_iterations', 8),
        'fibonacci_symbol_bases': config._DEFAULTS.get('fibonacci_symbol_bases', {}),
        'max_position_size': config._DEFAULTS.get('max_position_size', 10000),
        'max_daily_loss': config._DEFAULTS.get('max_daily_loss', 999999999),
        'max_open_positions': config._DEFAULTS.get('max_open_positions', 10),
        'profit_protection_enabled': config._DEFAULTS.get('profit_protection_enabled', True),
        'profit_protection_threshold': config._DEFAULTS.get('profit_protection_threshold', 0.0),
    }
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                saved = _json.load(f)
            defaults.update(saved)
    except Exception as e:
        logger.error(f"Error loading settings file: {e}")
    return defaults

def _save_settings_file(settings):
    """Save settings to local JSON file"""
    with open(SETTINGS_FILE, 'w') as f:
        _json.dump(settings, f, indent=2)

# Settings schema: defines all available settings
SETTINGS_SCHEMA = [
    {'key': 'trading_enabled', 'value_type': 'bool', 'label': 'Trading Enabled', 'category': 'general', 'description': 'Master kill switch for all trading'},
    {'key': 'fibonacci_enabled', 'value_type': 'bool', 'label': 'Fibonacci Sizing', 'category': 'fibonacci', 'description': 'Use Fibonacci sequence for position sizing'},
    {'key': 'fibonacci_base', 'value_type': 'float', 'label': 'Fibonacci Base Qty', 'category': 'fibonacci', 'description': 'Base quantity for first buy (e.g. 0.1 = 0.1 shares)'},
    {'key': 'fibonacci_max_iterations', 'value_type': 'int', 'label': 'Max Fibonacci Steps', 'category': 'fibonacci', 'description': 'Max buy orders before blocking further buys'},
    {'key': 'fibonacci_symbol_bases', 'value_type': 'json', 'label': 'Symbol-Specific Bases', 'category': 'fibonacci', 'description': 'JSON object of per-symbol base overrides, e.g. {"ETH/USD": 0.01}'},
    {'key': 'max_position_size', 'value_type': 'float', 'label': 'Max Position Size ($)', 'category': 'risk', 'description': 'Maximum dollar value for a single position'},
    {'key': 'max_daily_loss', 'value_type': 'float', 'label': 'Max Daily Loss ($)', 'category': 'risk', 'description': 'Stop trading if daily loss exceeds this amount'},
    {'key': 'max_open_positions', 'value_type': 'int', 'label': 'Max Open Positions', 'category': 'risk', 'description': 'Maximum number of simultaneous open positions'},
    {'key': 'profit_protection_enabled', 'value_type': 'bool', 'label': 'Profit Protection', 'category': 'risk', 'description': 'Only sell positions that are in profit'},
    {'key': 'profit_protection_threshold', 'value_type': 'float', 'label': 'Min Profit to Sell (%)', 'category': 'risk', 'description': 'Minimum profit percentage before allowing sell (0 = any profit)'},
]

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get current strategy settings from local JSON file"""
    try:
        settings = _load_settings_file()
        return jsonify({'success': True, 'settings': settings, 'schema': SETTINGS_SCHEMA})
    except Exception as e:
        logger.error(f"Error getting settings: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update strategy settings — saves to local JSON file, takes effect immediately"""
    try:
        data = request.json
        logger.info(f"Updating settings: {data}")

        settings = _load_settings_file()
        settings.update(data)
        _save_settings_file(settings)

        # Clear config caches so all services pick up new values immediately
        order_manager.config._cache = {}
        order_manager.config._cache_time = 0
        risk_manager.config._cache = {}
        risk_manager.config._cache_time = 0

        logger.info(f"Settings saved to file: {list(data.keys())}")

        return jsonify({
            'success': True,
            'message': 'Settings updated',
            'updated': list(data.keys())
        })
    except Exception as e:
        logger.error(f"Error updating settings: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings/init', methods=['POST'])
def init_settings():
    """Initialize Supabase with default settings (run once)"""
    try:
        from services.supabase_client import SupabaseClient
        supabase = SupabaseClient()

        if not supabase.is_connected():
            return jsonify({'success': False, 'error': 'Supabase not connected'}), 500

        config = Config()
        defaults = {
            'trading_enabled': config._DEFAULTS.get('trading_enabled', True),
            'fibonacci_enabled': config._DEFAULTS.get('fibonacci_enabled', True),
            'fibonacci_base': config._DEFAULTS.get('fibonacci_base', 1.0),
            'fibonacci_max_iterations': config._DEFAULTS.get('fibonacci_max_iterations', 10),
            'fibonacci_symbol_bases': config._DEFAULTS.get('fibonacci_symbol_bases', {}),
            'max_position_size': config._DEFAULTS.get('max_position_size', 10000),
            'max_daily_loss': config._DEFAULTS.get('max_daily_loss', 500),
            'max_open_positions': config._DEFAULTS.get('max_open_positions', 10),
            'profit_protection_enabled': config._DEFAULTS.get('profit_protection_enabled', True),
            'profit_protection_threshold': config._DEFAULTS.get('profit_protection_threshold', 0.0),
        }

        schema_map = {s['key']: s for s in SETTINGS_SCHEMA}
        upsert_list = []

        for key, value in defaults.items():
            s = schema_map.get(key, {})
            if s.get('value_type') == 'json' and not isinstance(value, str):
                import json
                value = json.dumps(value)
            upsert_list.append({
                'key': key,
                'value': str(value),
                'value_type': s.get('value_type', 'string'),
                'label': s.get('label', key),
                'category': s.get('category', 'general'),
                'description': s.get('description', ''),
            })

        supabase.bulk_upsert_settings(upsert_list)

        return jsonify({'success': True, 'message': 'Settings initialized', 'count': len(upsert_list)})
    except Exception as e:
        logger.error(f"Error initializing settings: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    logger.info(f"Starting trading bot server on port {Config().PORT}")
    logger.info(f"Paper trading: {Config().is_paper_trading}")
    app.run(host='0.0.0.0', port=Config().PORT, debug=True)



@app.route('/api/position-stats', methods=['GET'])
def get_position_stats():
    """Get position statistics from Supabase"""
    try:
        from services.supabase_client import SupabaseClient
        supabase = SupabaseClient()
        
        if not supabase.is_connected():
            return jsonify({'error': 'Supabase not connected'}), 500
        
        # Get all closed positions
        closed_response = supabase.client.from_('positions').select('*').eq('status', 'closed').execute()
        closed_positions = closed_response.data
        
        # Calculate statistics
        total_trades = len(closed_positions)
        winning_trades = [p for p in closed_positions if float(p.get('pnl', 0)) > 0]
        losing_trades = [p for p in closed_positions if float(p.get('pnl', 0)) < 0]
        
        total_pnl = sum(float(p.get('pnl', 0)) for p in closed_positions)
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        
        avg_win = sum(float(p.get('pnl', 0)) for p in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(float(p.get('pnl', 0)) for p in losing_trades) / len(losing_trades) if losing_trades else 0
        
        largest_win = max((float(p.get('pnl', 0)) for p in winning_trades), default=0)
        largest_loss = min((float(p.get('pnl', 0)) for p in losing_trades), default=0)
        
        return jsonify({
            'success': True,
            'stats': {
                'total_trades': total_trades,
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'total_pnl': round(total_pnl, 2),
                'win_rate': round(win_rate, 2),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'largest_win': round(largest_win, 2),
                'largest_loss': round(largest_loss, 2)
            }
        })
    except Exception as e:
        logger.error(f"Error getting position stats: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/all-trades', methods=['GET'])
def get_all_trades():
    """Get all trades from Supabase"""
    try:
        from services.supabase_client import SupabaseClient
        supabase = SupabaseClient()
        
        if not supabase.is_connected():
            return jsonify({'error': 'Supabase not connected'}), 500
        
        limit = request.args.get('limit', 1000, type=int)
        
        # Get all trades
        response = supabase.client.from_('trades').select('*').order('executed_at', desc=True).limit(limit).execute()
        
        trades = []
        for trade in response.data:
            trades.append({
                'id': trade['id'],
                'symbol': trade['symbol'],
                'side': trade['side'],
                'quantity': trade['quantity'],
                'price': float(trade['price']),
                'order_id': trade.get('order_id'),
                'executed_at': trade['executed_at']
            })
        
        return jsonify({
            'success': True,
            'trades': trades,
            'total': len(trades)
        })
    except Exception as e:
        logger.error(f"Error getting trades: {str(e)}")
        return jsonify({'error': str(e)}), 500

# =====================================================
# AUTO PROFIT TAKER API

@app.route('/api/auto-profit/status', methods=['GET'])
def get_auto_profit_status():
    """Get auto profit taker status"""
    try:
        return jsonify({'success': True, **auto_profit_taker.get_status()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auto-profit/settings', methods=['POST'])
def update_auto_profit_settings():
    """Update auto profit taker settings"""
    try:
        data = request.json
        auto_profit_taker.update_settings(data)
        return jsonify({'success': True, 'message': 'Settings updated', **auto_profit_taker.get_status()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auto-profit/start', methods=['POST'])
def start_auto_profit():
    """Start auto profit taker"""
    try:
        auto_profit_taker.enabled = True
        auto_profit_taker._save_settings()
        auto_profit_taker.start()
        return jsonify({'success': True, 'message': 'Auto Profit Taker started'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auto-profit/stop', methods=['POST'])
def stop_auto_profit():
    """Stop auto profit taker"""
    try:
        auto_profit_taker.enabled = False
        auto_profit_taker._save_settings()
        auto_profit_taker.stop()
        return jsonify({'success': True, 'message': 'Auto Profit Taker stopped'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# =====================================================
# STATIC FILE SERVING FOR DASHBOARDS

# Get the parent directory (project root) at module level
import os
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@app.route('/')
def index():
    """Serve main dashboard"""
    return send_from_directory(ROOT_DIR, 'dashboard.html')

@app.route('/dashboard')
@app.route('/dashboard.html')
def dashboard():
    """Serve main dashboard"""
    return send_from_directory(ROOT_DIR, 'dashboard.html')

# =====================================================
# START SERVER

if __name__ == '__main__':
    logger.info(f"Starting trading bot server on port {Config().PORT}")
    logger.info(f"Paper trading: {Config().is_paper_trading}")
    app.run(host='0.0.0.0', port=Config().PORT, debug=True)
