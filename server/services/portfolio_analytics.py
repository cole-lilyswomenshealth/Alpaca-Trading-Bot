"""
Portfolio Analytics Service
Calculates advanced trading metrics and performance indicators
"""
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any

class PortfolioAnalytics:
    def __init__(self, alpaca_client):
        self.client = alpaca_client
        self.risk_free_rate = 0.045  # 4.5% annual risk-free rate (approximate current rate)
        
    def calculate_all_metrics(self, orders_history: List[Dict], account_data: Dict, exclude_symbols: List[str] = None) -> Dict[str, Any]:
        """Calculate all portfolio metrics
        
        Args:
            orders_history: List of order dictionaries
            account_data: Account data dictionary
            exclude_symbols: Optional list of symbols to exclude from calculations (e.g., ['ETH/USD', 'BTC/USD'])
        """
        
        # Get closed trades
        closed_trades = self._get_closed_trades(orders_history, exclude_symbols)
        
        # Calculate basic metrics
        total_trades = len(closed_trades)
        winning_trades = [t for t in closed_trades if t['pnl'] > 0]
        losing_trades = [t for t in closed_trades if t['pnl'] < 0]
        
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate returns
        returns = [t['return_pct'] for t in closed_trades]
        
        # Calculate advanced metrics
        sharpe_ratio = self._calculate_sharpe_ratio(returns)
        sortino_ratio = self._calculate_sortino_ratio(returns)
        max_drawdown = self._calculate_max_drawdown(closed_trades, account_data)
        
        # Calculate profit metrics
        total_pnl = sum(t['pnl'] for t in closed_trades)
        avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t['pnl'] for t in losing_trades]) if losing_trades else 0
        profit_factor = abs(sum(t['pnl'] for t in winning_trades) / sum(t['pnl'] for t in losing_trades)) if losing_trades and sum(t['pnl'] for t in losing_trades) != 0 else 0
        
        # Calculate expectancy
        expectancy = self._calculate_expectancy(winning_trades, losing_trades, total_trades)
        
        # Calculate projected returns
        daily_return = np.mean(returns) if returns else 0
        monthly_return = self._calculate_monthly_return(returns)
        annual_return = self._calculate_annual_return(returns)
        
        # Calculate volatility
        volatility = np.std(returns) * np.sqrt(252) if returns else 0  # Annualized
        
        # Calculate beta (simplified - using SPY as benchmark)
        beta = self._calculate_beta(returns)
        
        # Calculate alpha
        alpha = self._calculate_alpha(annual_return, beta)
        
        # Calculate Calmar ratio
        calmar_ratio = (annual_return / abs(max_drawdown)) if max_drawdown != 0 else 0
        
        # Calculate consecutive wins/losses
        max_consecutive_wins = self._calculate_max_consecutive(closed_trades, 'win')
        max_consecutive_losses = self._calculate_max_consecutive(closed_trades, 'loss')
        
        # Calculate average holding period
        avg_holding_period = self._calculate_avg_holding_period(closed_trades)
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'expectancy': round(expectancy, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'sortino_ratio': round(sortino_ratio, 2),
            'max_drawdown': round(max_drawdown, 2),
            'max_drawdown_pct': round(max_drawdown, 2),
            'calmar_ratio': round(calmar_ratio, 2),
            'daily_return': round(daily_return, 4),
            'monthly_return': round(monthly_return, 2),
            'annual_return': round(annual_return, 2),
            'volatility': round(volatility * 100, 2),  # As percentage
            'beta': round(beta, 2),
            'alpha': round(alpha, 2),
            'max_consecutive_wins': max_consecutive_wins,
            'max_consecutive_losses': max_consecutive_losses,
            'avg_holding_period': avg_holding_period,
            'risk_reward_ratio': round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0
        }
    
    def _get_closed_trades(self, orders_history: List[Dict], exclude_symbols: List[str] = None) -> List[Dict]:
        """Extract closed trades from order history
        
        Args:
            orders_history: List of order dictionaries
            exclude_symbols: Optional list of symbols to exclude (e.g., ['ETH/USD', 'BTC/USD'])
        """
        closed_trades = []
        
        # Set default exclude list if not provided
        if exclude_symbols is None:
            exclude_symbols = []
        
        # Group orders by symbol to match buys with sells
        symbol_positions = {}
        
        # Sort orders by date, handling None values
        def get_order_date(order):
            date = order.get('filled_at') or order.get('submitted_at') or ''
            return date if date else ''
        
        for order in sorted(orders_history, key=get_order_date):
            if order['status'] != 'filled':
                continue
            
            symbol = order['symbol']
            
            # Skip excluded symbols
            if symbol in exclude_symbols:
                continue
            side = order['side']
            qty = float(order['filled_qty'])
            price = float(order['filled_avg_price']) if order.get('filled_avg_price') else 0
            
            if symbol not in symbol_positions:
                symbol_positions[symbol] = {'qty': 0, 'cost_basis': 0, 'trades': []}
            
            if side == 'buy':
                symbol_positions[symbol]['cost_basis'] += qty * price
                symbol_positions[symbol]['qty'] += qty
            elif side == 'sell' and symbol_positions[symbol]['qty'] > 0:
                # Calculate P&L for this trade
                avg_cost = symbol_positions[symbol]['cost_basis'] / symbol_positions[symbol]['qty']
                pnl = (price - avg_cost) * qty
                return_pct = ((price - avg_cost) / avg_cost) * 100
                
                closed_trades.append({
                    'symbol': symbol,
                    'pnl': pnl,
                    'return_pct': return_pct,
                    'entry_price': avg_cost,
                    'exit_price': price,
                    'qty': qty,
                    'entry_date': order.get('submitted_at'),
                    'exit_date': order.get('filled_at')
                })
                
                # Update position
                symbol_positions[symbol]['qty'] -= qty
                if symbol_positions[symbol]['qty'] > 0:
                    symbol_positions[symbol]['cost_basis'] -= qty * avg_cost
                else:
                    symbol_positions[symbol]['cost_basis'] = 0
        
        return closed_trades
    
    def _calculate_sharpe_ratio(self, returns: List[float]) -> float:
        """Calculate Sharpe Ratio"""
        if not returns or len(returns) < 2:
            return 0
        
        returns_array = np.array(returns) / 100  # Convert percentage to decimal
        avg_return = np.mean(returns_array)
        std_return = np.std(returns_array)
        
        if std_return == 0:
            return 0
        
        # Annualize
        daily_rf = self.risk_free_rate / 252
        sharpe = (avg_return - daily_rf) / std_return * np.sqrt(252)
        
        return sharpe
    
    def _calculate_sortino_ratio(self, returns: List[float]) -> float:
        """Calculate Sortino Ratio (uses downside deviation)"""
        if not returns or len(returns) < 2:
            return 0
        
        returns_array = np.array(returns) / 100
        avg_return = np.mean(returns_array)
        
        # Calculate downside deviation
        downside_returns = [r for r in returns_array if r < 0]
        if not downside_returns:
            return 0
        
        downside_std = np.std(downside_returns)
        
        if downside_std == 0:
            return 0
        
        daily_rf = self.risk_free_rate / 252
        sortino = (avg_return - daily_rf) / downside_std * np.sqrt(252)
        
        return sortino
    
    def _calculate_max_drawdown(self, closed_trades: List[Dict], account_data: Dict) -> float:
        """Calculate maximum drawdown"""
        if not closed_trades:
            return 0
        
        # Calculate cumulative P&L
        cumulative_pnl = []
        running_total = 0
        
        for trade in closed_trades:
            running_total += trade['pnl']
            cumulative_pnl.append(running_total)
        
        if not cumulative_pnl:
            return 0
        
        # Calculate drawdown
        peak = cumulative_pnl[0]
        max_dd = 0
        
        for value in cumulative_pnl:
            if value > peak:
                peak = value
            dd = peak - value
            if dd > max_dd:
                max_dd = dd
        
        # Convert to percentage of account equity
        equity = account_data.get('equity', 100000)
        max_dd_pct = (max_dd / equity) * 100
        
        return max_dd_pct
    
    def _calculate_expectancy(self, winning_trades: List[Dict], losing_trades: List[Dict], total_trades: int) -> float:
        """Calculate expectancy (average expected profit per trade)"""
        if total_trades == 0:
            return 0
        
        win_rate = len(winning_trades) / total_trades
        loss_rate = len(losing_trades) / total_trades
        
        avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
        avg_loss = abs(np.mean([t['pnl'] for t in losing_trades])) if losing_trades else 0
        
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        
        return expectancy
    
    def _calculate_monthly_return(self, returns: List[float]) -> float:
        """Calculate projected monthly return"""
        if not returns:
            return 0
        
        daily_return = np.mean(returns) / 100
        # Compound daily return over ~21 trading days
        monthly_return = ((1 + daily_return) ** 21 - 1) * 100
        
        return monthly_return
    
    def _calculate_annual_return(self, returns: List[float]) -> float:
        """Calculate projected annual return"""
        if not returns:
            return 0
        
        daily_return = np.mean(returns) / 100
        # Compound daily return over 252 trading days
        annual_return = ((1 + daily_return) ** 252 - 1) * 100
        
        return annual_return
    
    def _calculate_beta(self, returns: List[float]) -> float:
        """Calculate beta (simplified - assumes market return of 10%)"""
        if not returns or len(returns) < 2:
            return 1.0
        
        # Simplified beta calculation
        # In production, you'd compare against actual SPY returns
        portfolio_volatility = np.std(returns)
        market_volatility = 1.0  # Normalized market volatility
        
        # Correlation with market (simplified assumption)
        correlation = 0.7  # Typical stock correlation with market
        
        beta = correlation * (portfolio_volatility / market_volatility)
        
        return max(0, beta)  # Beta shouldn't be negative for long-only portfolio
    
    def _calculate_alpha(self, annual_return: float, beta: float) -> float:
        """Calculate alpha (excess return over expected return)"""
        market_return = 10.0  # Assume 10% market return
        expected_return = self.risk_free_rate + beta * (market_return - self.risk_free_rate)
        alpha = annual_return - expected_return
        
        return alpha
    
    def _calculate_max_consecutive(self, closed_trades: List[Dict], trade_type: str) -> int:
        """Calculate maximum consecutive wins or losses"""
        if not closed_trades:
            return 0
        
        max_consecutive = 0
        current_consecutive = 0
        
        for trade in closed_trades:
            if trade_type == 'win' and trade['pnl'] > 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            elif trade_type == 'loss' and trade['pnl'] < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive
    
    def _calculate_avg_holding_period(self, closed_trades: List[Dict]) -> str:
        """Calculate average holding period"""
        if not closed_trades:
            return "N/A"
        
        holding_periods = []
        
        for trade in closed_trades:
            if trade.get('entry_date') and trade.get('exit_date'):
                try:
                    entry = datetime.fromisoformat(trade['entry_date'].replace('Z', '+00:00'))
                    exit = datetime.fromisoformat(trade['exit_date'].replace('Z', '+00:00'))
                    duration = (exit - entry).total_seconds() / 3600  # Hours
                    holding_periods.append(duration)
                except:
                    continue
        
        if not holding_periods:
            return "N/A"
        
        avg_hours = np.mean(holding_periods)
        
        if avg_hours < 24:
            return f"{avg_hours:.1f} hours"
        else:
            return f"{avg_hours/24:.1f} days"
