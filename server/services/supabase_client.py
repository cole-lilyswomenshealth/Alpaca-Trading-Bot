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
    def save_trade(self, symbol, side, quantity, price, order_id, position_id=None, source='manual'):
        """Save a trade"""
        try:
            data = {
                'symbol': symbol,
                'side': side,
                'quantity': quantity,
                'price': price,
                'order_id': str(order_id),  # Convert UUID to string
                'position_id': str(position_id) if position_id else None,
                'source': source,  # Track if webhook or manual
                'executed_at': datetime.now().isoformat()
            }
            
            response = self.client.from_('trades').insert(data).execute()
            logger.info(f"Trade saved: {symbol} {side} {quantity} (source: {source})")
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
