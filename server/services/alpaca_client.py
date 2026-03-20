from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
    StopLimitOrderRequest, TrailingStopOrderRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta
from config import Config

class AlpacaClient:
    def __init__(self):
        self.config = Config()
        self.trading_client = TradingClient(
            self.config.ALPACA_API_KEY,
            self.config.ALPACA_SECRET_KEY,
            paper=self.config.is_paper_trading
        )
        self.data_client = StockHistoricalDataClient(
            self.config.ALPACA_API_KEY,
            self.config.ALPACA_SECRET_KEY
        )
    
    def get_account(self):
        """Get account information"""
        return self.trading_client.get_account()
    
    def get_positions(self):
        """Get all open positions"""
        return self.trading_client.get_all_positions()
    
    def get_position(self, symbol):
        """Get specific position"""
        try:
            return self.trading_client.get_open_position(symbol)
        except Exception:
            return None
    
    def get_orders(self, status='all', limit=100):
        """Get orders"""
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        
        status_map = {
            'open': QueryOrderStatus.OPEN,
            'closed': QueryOrderStatus.CLOSED,
            'all': QueryOrderStatus.ALL
        }
        
        request = GetOrdersRequest(
            status=status_map.get(status, QueryOrderStatus.ALL),
            limit=limit
        )
        return self.trading_client.get_orders(request)
    
    def submit_market_order(self, symbol, qty, side, time_in_force='day'):
        """Submit market order"""
        order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
        
        # Map time_in_force string to enum
        tif_map = {
            'day': TimeInForce.DAY,
            'gtc': TimeInForce.GTC,
            'ioc': TimeInForce.IOC,
            'fok': TimeInForce.FOK
        }
        tif = tif_map.get(time_in_force.lower(), TimeInForce.GTC)
        
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=tif
        )
        return self.trading_client.submit_order(order_data)
    
    def submit_limit_order(self, symbol, qty, side, limit_price, time_in_force='day'):
        """Submit limit order"""
        order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
        tif = TimeInForce.DAY if time_in_force.lower() == 'day' else TimeInForce.GTC
        
        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            limit_price=limit_price,
            time_in_force=tif
        )
        return self.trading_client.submit_order(order_data)
    
    def submit_stop_order(self, symbol, qty, side, stop_price, time_in_force='gtc'):
        """Submit stop order"""
        order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
        tif = TimeInForce.DAY if time_in_force.lower() == 'day' else TimeInForce.GTC
        
        order_data = StopOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            stop_price=stop_price,
            time_in_force=tif
        )
        return self.trading_client.submit_order(order_data)
    
    def cancel_order(self, order_id):
        """Cancel order"""
        return self.trading_client.cancel_order_by_id(order_id)
    
    def cancel_all_orders(self):
        """Cancel all open orders"""
        return self.trading_client.cancel_orders()
    
    def close_position(self, symbol):
        """Close position"""
        return self.trading_client.close_position(symbol)
    
    def close_all_positions(self):
        """Close all positions"""
        return self.trading_client.close_all_positions()
    
    def get_latest_quote(self, symbol, feed='sip'):
        """Get latest quote for symbol with real-time SIP feed"""
        request = StockLatestQuoteRequest(
            symbol_or_symbols=symbol,
            feed=feed  # Use SIP for real-time quotes
        )
        quotes = self.data_client.get_stock_latest_quote(request)
        return quotes[symbol] if symbol in quotes else None
    
    def get_bars(self, symbol, timeframe='1Day', start=None, end=None, feed='sip'):
        """Get historical bars with real-time SIP feed"""
        if start is None:
            start = datetime.now() - timedelta(days=30)
        if end is None:
            end = datetime.now()
        
        timeframe_map = {
            '1Min': TimeFrame.Minute,
            '5Min': TimeFrame(5, 'Min'),
            '15Min': TimeFrame(15, 'Min'),
            '1Hour': TimeFrame.Hour,
            '1Day': TimeFrame.Day
        }
        
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe_map.get(timeframe, TimeFrame.Day),
            start=start,
            end=end,
            feed=feed  # Use SIP for real-time data (default)
        )
        return self.data_client.get_stock_bars(request)
    
    def get_portfolio_history(self, period='1M', timeframe='1D', extended_hours=False):
        """Get portfolio history with P&L data from Alpaca"""
        from alpaca.trading.requests import GetPortfolioHistoryRequest
        
        request = GetPortfolioHistoryRequest(
            period=period,
            timeframe=timeframe,
            extended_hours=extended_hours
        )
        return self.trading_client.get_portfolio_history(request)
