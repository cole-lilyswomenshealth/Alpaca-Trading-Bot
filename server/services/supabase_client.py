"""
Supabase Client for Trading Bot
Handles all database operations
"""
import os
import logging
from postgrest import SyncPostgrestClient
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL')
        self.key = os.getenv('SUPABASE_KEY')
        
        if not self.url or not self.key:
            logger.warning("Supabase credentials not found in .env")
            self.client = None
            return
        
        # Create postgrest client
        self.client = SyncPostgrestClient(
            f"{self.url}/rest/v1",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}"
            }
        )
        
        logger.info("Supabase client initialized")
    
    def is_connected(self):
        """Check if client is connected"""
        return self.client is not None
    
    # Position Tracking
    def save_position(self, symbol, entry_price, quantity, strategy_id=None, source='manual'):
        """Save a new position"""
        try:
            data = {
                'symbol': symbol,
                'entry_price': entry_price,
                'quantity': quantity,
                'strategy_id': strategy_id,
                'fibonacci_count': 0,
                'source': source,  # Track if webhook or manual
                'opened_at': datetime.now().isoformat(),
                'status': 'open'
            }
            
            response = self.client.from_('positions').insert(data).execute()
            logger.info(f"Position saved: {symbol} (source: {source})")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error saving position: {e}")
            return None
    
    def update_position(self, position_id, **kwargs):
        """Update position fields"""
        try:
            response = self.client.from_('positions').update(kwargs).eq('id', position_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error updating position: {e}")
            return None
    
    def get_open_positions(self):
        """Get all open positions"""
        try:
            response = self.client.from_('positions').select('*').eq('status', 'open').execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def get_position_by_symbol(self, symbol):
        """Get open position for a symbol"""
        try:
            response = self.client.from_('positions').select('*').eq('symbol', symbol).eq('status', 'open').execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting position: {e}")
            return None
    
    def close_position(self, position_id, close_price, pnl):
        """Close a position"""
        try:
            data = {
                'status': 'closed',
                'closed_at': datetime.now().isoformat(),
                'close_price': close_price,
                'pnl': pnl
            }
            response = self.client.from_('positions').update(data).eq('id', position_id).execute()
            logger.info(f"Position closed: {position_id}")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return None
    
    # Trade History
    def save_trade(self, symbol, side, quantity, price, order_id, position_id=None, source='manual', fibonacci_position=None):
        """Save a trade to the trades table"""
        try:
            data = {
                'symbol': symbol,
                'side': side,
                'quantity': quantity,
                'price': price,
                'order_id': str(order_id),
                'source': source,
                'fibonacci_position': fibonacci_position,
                'executed_at': datetime.now().isoformat()
            }
            
            response = self.client.from_('trades').insert(data).execute()
            logger.info(f"Trade saved: {symbol} {side} {quantity} @ {price} (source: {source})")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error saving trade: {e}")
            return None
    
    def get_trades(self, limit=100):
        """Get recent trades"""
        try:
            response = self.client.from_('trades').select('*').order('executed_at', desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting trades: {e}")
            return []
    
    # Screener Results
    def save_screener_results(self, results, settings):
        """Save screener results"""
        try:
            data = {
                'results': results,
                'settings': settings,
                'total_found': len(results),
                'scanned_at': datetime.now().isoformat()
            }
            
            response = self.client.from_('screener_results').insert(data).execute()
            logger.info(f"Screener results saved: {len(results)} opportunities")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error saving screener results: {e}")
            return None
    
    def get_latest_screener_results(self):
        """Get most recent screener results"""
        try:
            response = self.client.from_('screener_results').select('*').order('scanned_at', desc=True).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting screener results: {e}")
            return None
    
    # Watchlists
    def save_watchlist(self, name, symbols, filters=None):
        """Save a watchlist"""
        try:
            data = {
                'name': name,
                'symbols': symbols,
                'filters': filters or {},
                'created_at': datetime.now().isoformat()
            }
            
            response = self.client.from_('watchlists').insert(data).execute()
            logger.info(f"Watchlist saved: {name}")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error saving watchlist: {e}")
            return None
    
    def get_watchlists(self):
        """Get all watchlists"""
        try:
            response = self.client.from_('watchlists').select('*').execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting watchlists: {e}")
            return []
    
    # Performance Metrics
    def save_performance_metrics(self, date, metrics):
        """Save daily performance metrics"""
        try:
            data = {
                'date': date,
                **metrics,
                'recorded_at': datetime.now().isoformat()
            }
            
            response = self.client.from_('performance_metrics').insert(data).execute()
            logger.info(f"Performance metrics saved for {date}")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error saving performance metrics: {e}")
            return None
    
    def get_performance_history(self, days=30):
        """Get performance history"""
        try:
            response = self.client.from_('performance_metrics').select('*').order('date', desc=True).limit(days).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting performance history: {e}")
            return []

    # =====================================================
    # WEBHOOK LOG - Every webhook received
    # =====================================================

    def log_webhook(self, payload, symbol, action, quantity, status, response=None, error_message=None, source_ip=None):
        """Log every webhook received by the server"""
        try:
            data = {
                'payload': payload if isinstance(payload, dict) else {},
                'symbol': symbol,
                'action': action,
                'quantity': float(quantity) if quantity else 0,
                'status': status,
                'response': response if isinstance(response, dict) else {},
                'error_message': error_message,
                'source_ip': source_ip,
                'received_at': datetime.now().isoformat()
            }
            response_data = self.client.from_('webhook_log').insert(data).execute()
            logger.info(f"Webhook logged to Supabase: {symbol} {action} {status}")
            return response_data.data[0] if response_data.data else None
        except Exception as e:
            logger.error(f"Error logging webhook: {e}")
            return None

    def get_webhook_log(self, limit=100):
        """Get recent webhook logs"""
        try:
            response = self.client.from_('webhook_log').select('*').order('received_at', desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting webhook log: {e}")
            return []

    # =====================================================
    # DAILY PERFORMANCE - End-of-day snapshots
    # =====================================================

    def save_daily_performance(self, date, portfolio_value, cash, buying_power, equity, day_pnl, day_pnl_pct, total_pnl, open_positions, trades_today=0):
        """Save daily portfolio snapshot"""
        try:
            data = {
                'date': date,
                'portfolio_value': portfolio_value,
                'cash': cash,
                'buying_power': buying_power,
                'equity': equity,
                'day_pnl': day_pnl,
                'day_pnl_pct': day_pnl_pct,
                'total_pnl': total_pnl,
                'open_positions': open_positions,
                'trades_today': trades_today,
            }
            response = self.client.from_('daily_performance').upsert(data, on_conflict='date').execute()
            logger.info(f"Daily performance saved for {date}")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error saving daily performance: {e}")
            return None

    def get_daily_performance_history(self, days=30):
        """Get daily performance history"""
        try:
            response = self.client.from_('daily_performance').select('*').order('date', desc=True).limit(days).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting daily performance: {e}")
            return []

    # =====================================================
    # STRATEGY SETTINGS (Real-time config from dashboard)
    # =====================================================
    
    def get_settings(self):
        """Get all strategy settings from Supabase"""
        try:
            response = self.client.from_('strategy_settings').select('*').execute()
            # Convert list of {key, value, ...} rows into a dict
            settings = {}
            for row in response.data:
                settings[row['key']] = {
                    'value': row['value'],
                    'type': row.get('value_type', 'string'),
                    'label': row.get('label', row['key']),
                    'category': row.get('category', 'general'),
                    'description': row.get('description', ''),
                    'id': row.get('id')
                }
            return settings
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return {}
    
    def get_setting(self, key):
        """Get a single setting value"""
        try:
            response = self.client.from_('strategy_settings').select('value,value_type').eq('key', key).execute()
            if response.data:
                row = response.data[0]
                return self._cast_value(row['value'], row.get('value_type', 'string'))
            return None
        except Exception as e:
            logger.error(f"Error getting setting {key}: {e}")
            return None
    
    def upsert_setting(self, key, value, value_type='string', label=None, category='general', description=''):
        """Create or update a setting"""
        try:
            data = {
                'key': key,
                'value': str(value),
                'value_type': value_type,
                'label': label or key,
                'category': category,
                'description': description,
                'updated_at': datetime.now().isoformat()
            }
            response = self.client.from_('strategy_settings').upsert(data, on_conflict='key').execute()
            logger.info(f"Setting saved: {key} = {value}")
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error saving setting {key}: {e}")
            return None
    
    def bulk_upsert_settings(self, settings_list):
        """Bulk upsert multiple settings"""
        try:
            for s in settings_list:
                s['value'] = str(s['value'])
                s['updated_at'] = datetime.now().isoformat()
            response = self.client.from_('strategy_settings').upsert(settings_list, on_conflict='key').execute()
            logger.info(f"Bulk settings saved: {len(settings_list)} settings")
            return response.data
        except Exception as e:
            logger.error(f"Error bulk saving settings: {e}")
            return None
    
    def _cast_value(self, value, value_type):
        """Cast a string value to its proper type"""
        try:
            if value_type == 'float':
                return float(value)
            elif value_type == 'int':
                return int(float(value))
            elif value_type == 'bool':
                return value.lower() in ('true', '1', 'yes')
            elif value_type == 'json':
                import json
                return json.loads(value)
            return value
        except:
            return value
