from config import Config
from datetime import datetime, timedelta

class RiskManager:
    def __init__(self, alpaca_client):
        self.config = Config()
        self.client = alpaca_client
    
    def validate_order(self, symbol, qty, side, order_type='market', price=None):
        """Validate order against risk rules"""
        errors = []
        
        # Check if trading is enabled
        if not self.config.TRADING_ENABLED:
            errors.append("Trading is currently disabled")
            return False, errors
        
        # Get account info
        account = self.client.get_account()
        
        # Check if account is active
        if account.status != 'ACTIVE':
            errors.append(f"Account status is {account.status}, not ACTIVE")
            return False, errors
        
        # Check total exposure limit on BUY orders
        if side.lower() == 'buy':
            max_exposure = self.config.MAX_POSITION_SIZE  # Total max open value
            positions = self.client.get_positions()
            total_exposure = sum(abs(float(p.market_value)) for p in positions)
            order_cost = self._estimate_order_cost(symbol, qty, side, order_type, price)
            
            if total_exposure + order_cost > max_exposure:
                errors.append(f"Total exposure limit: ${total_exposure:.2f} invested + ${order_cost:.2f} order = ${total_exposure + order_cost:.2f} exceeds ${max_exposure:.2f} max")
                return False, errors
        
        return True, []
    
    def _estimate_order_cost(self, symbol, qty, side, order_type, price):
        """Estimate order cost"""
        if side.lower() == 'sell':
            return 0  # Selling doesn't require buying power
        
        if order_type == 'market':
            # Skip quote lookup for crypto (not supported by StockHistoricalDataClient)
            if '/' in symbol:
                # Crypto - use conservative estimate based on symbol
                if 'BTC' in symbol:
                    estimated_price = 70000
                elif 'ETH' in symbol:
                    estimated_price = 3000
                else:
                    estimated_price = 100
            else:
                # Stock - get latest quote
                quote = self.client.get_latest_quote(symbol)
                if quote:
                    estimated_price = float(quote.ask_price)
                else:
                    estimated_price = 1000  # Conservative high estimate
        else:
            estimated_price = price if price else 0
        
        return estimated_price * qty
    
    def _check_daily_loss_limit(self, account):
        """Check if daily loss limit is exceeded"""
        # Calculate daily P&L
        equity = float(account.equity)
        last_equity = float(account.last_equity)
        daily_pnl = equity - last_equity
        
        # If we're losing more than the limit, block trading
        if daily_pnl < -self.config.MAX_DAILY_LOSS:
            return False
        
        return True
    
    def get_risk_status(self):
        """Get current risk status"""
        account = self.client.get_account()
        positions = self.client.get_positions()
        
        equity = float(account.equity)
        last_equity = float(account.last_equity)
        daily_pnl = equity - last_equity
        
        return {
            'trading_enabled': self.config.TRADING_ENABLED,
            'account_status': account.status,
            'buying_power': float(account.buying_power),
            'equity': equity,
            'daily_pnl': daily_pnl,
            'daily_loss_limit': self.config.MAX_DAILY_LOSS,
            'daily_loss_remaining': self.config.MAX_DAILY_LOSS + daily_pnl,
            'open_positions': len(positions),
            'max_positions': self.config.MAX_OPEN_POSITIONS,
            'positions_remaining': self.config.MAX_OPEN_POSITIONS - len(positions)
        }
