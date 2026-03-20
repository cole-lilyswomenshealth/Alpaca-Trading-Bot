"""
Options Trading Service
Handles 0DTE options trading strategies
"""
from datetime import datetime, timedelta
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, AssetStatus, ContractType
import logging
import math

logger = logging.getLogger(__name__)

class OptionsTrader:
    def __init__(self, alpaca_client):
        self.client = alpaca_client
    
    def calculate_implied_volatility_estimate(self, underlying_symbol):
        """
        Estimate implied volatility using historical volatility
        For 0DTE, we'll use a simplified approach based on recent price movement
        
        Returns: Estimated daily volatility as a decimal (e.g., 0.01 = 1%)
        """
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            from datetime import datetime, timedelta
            
            data_client = StockHistoricalDataClient(
                self.client.config.ALPACA_API_KEY,
                self.client.config.ALPACA_SECRET_KEY
            )
            
            # Get last 5 days of data to calculate volatility
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            
            request = StockBarsRequest(
                symbol_or_symbols=underlying_symbol,
                timeframe=TimeFrame.Day,
                start=start_date,
                end=end_date
            )
            
            bars = data_client.get_stock_bars(request)
            
            if underlying_symbol not in bars.data or len(bars.data[underlying_symbol]) < 2:
                # Default to 1% daily volatility if we can't calculate
                logger.warning(f"Insufficient data to calculate volatility for {underlying_symbol}, using default 1%")
                return 0.01
            
            # Calculate daily returns
            prices = [float(bar.close) for bar in bars.data[underlying_symbol]]
            returns = []
            for i in range(1, len(prices)):
                daily_return = (prices[i] - prices[i-1]) / prices[i-1]
                returns.append(daily_return)
            
            # Calculate standard deviation of returns (historical volatility)
            if len(returns) < 2:
                return 0.01
            
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
            daily_volatility = math.sqrt(variance)
            
            logger.info(f"Calculated daily volatility for {underlying_symbol}: {daily_volatility:.4f} ({daily_volatility*100:.2f}%)")
            
            # For 0DTE, scale down the volatility since we're only holding for part of a day
            # Assume we're holding for ~4 hours out of 6.5 hour trading day
            intraday_factor = math.sqrt(4 / 6.5)
            adjusted_volatility = daily_volatility * intraday_factor
            
            logger.info(f"Adjusted 0DTE volatility: {adjusted_volatility:.4f} ({adjusted_volatility*100:.2f}%)")
            
            return adjusted_volatility
            
        except Exception as e:
            logger.error(f"Error calculating volatility: {e}")
            # Default to 1% if calculation fails
            return 0.01
    
    def find_option_by_strike_selection(self, underlying_symbol, option_type='call', side='buy', expiration_date=None, std_devs=2.5):
        """
        Find option contract based on strike selection strategy
        
        Args:
            underlying_symbol: Stock symbol (e.g., 'SPY')
            option_type: 'call' or 'put'
            side: 'buy' (ATM) or 'sell' (OTM by std_devs)
            expiration_date: Date string 'YYYY-MM-DD' or None for today
            std_devs: Number of standard deviations for OTM (when selling)
        
        Returns:
            Option contract symbol or None
        """
        try:
            # Get current price of underlying
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestTradeRequest
            
            data_client = StockHistoricalDataClient(
                self.client.config.ALPACA_API_KEY,
                self.client.config.ALPACA_SECRET_KEY
            )
            
            request = StockLatestTradeRequest(symbol_or_symbols=underlying_symbol)
            trades = data_client.get_stock_latest_trade(request)
            current_price = float(trades[underlying_symbol].price)
            
            logger.info(f"Current {underlying_symbol} price: ${current_price}")
            
            # Calculate target strike based on side
            if side.lower() == 'buy':
                # For buying: ATM (at-the-money)
                target_strike = current_price
                logger.info(f"Buying strategy: Looking for ATM strike near ${target_strike:.2f}")
            else:
                # For selling: OTM by std_devs standard deviations
                volatility = self.calculate_implied_volatility_estimate(underlying_symbol)
                price_move = current_price * volatility * std_devs
                
                if option_type.lower() == 'call':
                    # Sell call: strike above current price
                    target_strike = current_price + price_move
                else:
                    # Sell put: strike below current price
                    target_strike = current_price - price_move
                
                logger.info(f"Writing strategy: {std_devs} std devs OTM = ${price_move:.2f} move")
                logger.info(f"Target strike: ${target_strike:.2f} (current: ${current_price:.2f})")
            
            # Use today's date if not specified (0DTE)
            if not expiration_date:
                expiration_date = datetime.now().strftime('%Y-%m-%d')
            
            # Get option contracts for this underlying using proper Alpaca SDK method
            from alpaca.trading.requests import GetOptionContractsRequest
            from alpaca.trading.enums import AssetStatus, ContractType
            
            # Convert option_type string to ContractType enum
            contract_type = ContractType.CALL if option_type.lower() == 'call' else ContractType.PUT
            
            request = GetOptionContractsRequest(
                underlying_symbols=[underlying_symbol],
                status=AssetStatus.ACTIVE,
                expiration_date=expiration_date,
                type=contract_type
            )
            
            contracts_response = self.client.trading_client.get_option_contracts(request)
            
            if not contracts_response or not contracts_response.option_contracts:
                logger.error(f"No {option_type} contracts found for {underlying_symbol} expiring {expiration_date}")
                return None
            
            logger.info(f"Found {len(contracts_response.option_contracts)} {option_type} contracts for {underlying_symbol}")
            
            # Find strike closest to target
            best_contract = None
            min_diff = float('inf')
            
            for contract in contracts_response.option_contracts:
                strike = float(contract.strike_price)
                diff = abs(strike - target_strike)
                
                if diff < min_diff:
                    min_diff = diff
                    best_contract = contract
            
            if best_contract:
                strike_type = "ATM" if side.lower() == 'buy' else f"{std_devs}σ OTM"
                logger.info(f"Found {strike_type} {option_type}: {best_contract.symbol} (Strike: ${best_contract.strike_price}, Target: ${target_strike:.2f})")
                return best_contract.symbol
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding option by strike selection: {e}")
            import traceback
            traceback.print_exc()
            return None
        """
        Find at-the-money option contract
        
        Args:
            underlying_symbol: Stock symbol (e.g., 'SPY')
            option_type: 'call' or 'put'
            expiration_date: Date string 'YYYY-MM-DD' or None for today
        
        Returns:
            Option contract symbol or None
        """
        try:
            # Get current price of underlying
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestTradeRequest
            
            data_client = StockHistoricalDataClient(
                self.client.config.ALPACA_API_KEY,
                self.client.config.ALPACA_SECRET_KEY
            )
            
            request = StockLatestTradeRequest(symbol_or_symbols=underlying_symbol)
            trades = data_client.get_stock_latest_trade(request)
            current_price = float(trades[underlying_symbol].price)
            
            logger.info(f"Current {underlying_symbol} price: ${current_price}")
            
            # Use today's date if not specified (0DTE)
            if not expiration_date:
                expiration_date = datetime.now().strftime('%Y-%m-%d')
            
            # Get option contracts for this underlying using proper Alpaca SDK method
            from alpaca.trading.requests import GetOptionContractsRequest
            from alpaca.trading.enums import AssetStatus, ContractType
            
            # Convert option_type string to ContractType enum
            contract_type = ContractType.CALL if option_type.lower() == 'call' else ContractType.PUT
            
            request = GetOptionContractsRequest(
                underlying_symbols=[underlying_symbol],
                status=AssetStatus.ACTIVE,
                expiration_date=expiration_date,
                type=contract_type
            )
            
            contracts_response = self.client.trading_client.get_option_contracts(request)
            
            if not contracts_response or not contracts_response.option_contracts:
                logger.error(f"No {option_type} contracts found for {underlying_symbol} expiring {expiration_date}")
                return None
            
            logger.info(f"Found {len(contracts_response.option_contracts)} {option_type} contracts for {underlying_symbol}")
            
            # Find ATM strike (closest to current price)
            atm_contract = None
            min_diff = float('inf')
            
            for contract in contracts_response.option_contracts:
                strike = float(contract.strike_price)
                diff = abs(strike - current_price)
                
                if diff < min_diff:
                    min_diff = diff
                    atm_contract = contract
            
            if atm_contract:
                logger.info(f"Found ATM {option_type}: {atm_contract.symbol} (Strike: ${atm_contract.strike_price})")
                return atm_contract.symbol
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding ATM option: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    
    def find_atm_option(self, underlying_symbol, option_type='call', expiration_date=None):
        """
        Find at-the-money option contract (legacy method, calls new method)
        
        Args:
            underlying_symbol: Stock symbol (e.g., 'SPY')
            option_type: 'call' or 'put'
            expiration_date: Date string 'YYYY-MM-DD' or None for today
        
        Returns:
            Option contract symbol or None
        """
        return self.find_option_by_strike_selection(
            underlying_symbol=underlying_symbol,
            option_type=option_type,
            side='buy',  # ATM for buying
            expiration_date=expiration_date
        )
    
    def trade_0dte_option(self, underlying_symbol, direction, qty=1, side='buy', std_devs=2.5):
        """
        Trade 0DTE option with intelligent strike selection
        
        Args:
            underlying_symbol: Stock symbol (e.g., 'SPY')
            direction: 'call' for bullish, 'put' for bearish
            qty: Number of contracts
            side: 'buy' (ATM) or 'sell' (OTM by std_devs)
            std_devs: Standard deviations for OTM when selling (default 2.5)
        
        Returns:
            Order object or None
        """
        try:
            logger.info(f"Attempting to trade 0DTE {direction} option for {underlying_symbol}, side={side}, qty={qty}, std_devs={std_devs}")
            
            # Find option based on strike selection strategy
            option_symbol = self.find_option_by_strike_selection(
                underlying_symbol=underlying_symbol,
                option_type=direction.lower(),
                side=side,
                expiration_date=None,  # Today (0DTE)
                std_devs=std_devs
            )
            
            if not option_symbol:
                error_msg = f"Could not find appropriate {direction} option for {underlying_symbol}"
                logger.error(error_msg)
                raise Exception(error_msg)
            
            logger.info(f"Found option contract: {option_symbol}")
            
            # Determine order side
            order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
            
            # Submit market order for the option
            order_data = MarketOrderRequest(
                symbol=option_symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY  # Options must use DAY
            )
            
            logger.info(f"Submitting order: {order_side.value} {qty} {option_symbol}")
            order = self.client.trading_client.submit_order(order_data)
            logger.info(f"0DTE option order submitted successfully: {side.upper()} {order.symbol}, Order ID: {order.id}, Status: {order.status.value}")
            
            return order
            
        except Exception as e:
            logger.error(f"Error trading 0DTE option: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_option_positions(self):
        """Get all open option positions"""
        try:
            all_positions = self.client.get_positions()
            option_positions = [p for p in all_positions if '/' not in p.symbol and len(p.symbol) > 10]
            return option_positions
        except Exception as e:
            logger.error(f"Error getting option positions: {e}")
            return []
    
    def close_option_position(self, option_symbol):
        """Close an option position"""
        try:
            return self.client.close_position(option_symbol)
        except Exception as e:
            logger.error(f"Error closing option position: {e}")
            return None
