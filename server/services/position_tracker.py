"""
Position Tracker for Fibonacci Position Sizing
Tracks buy orders per symbol to implement strategic entry sizing
"""
import json
import os
from datetime import datetime

class PositionTracker:
    def __init__(self, data_file='position_tracker.json'):
        self.data_file = data_file
        self.data = self._load_data()
    
    def _load_data(self):
        """Load tracking data from file"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_data(self):
        """Save tracking data to file"""
        with open(self.data_file, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def get_fibonacci_number(self, n):
        """Get the nth Fibonacci number (1-indexed)"""
        if n <= 0:
            return 1
        elif n == 1 or n == 2:
            return 1
        
        fib = [1, 1]
        for i in range(2, n):
            fib.append(fib[i-1] + fib[i-2])
        
        return fib[n-1]
    
    def get_buy_count(self, symbol):
        """Get the number of buy orders for a symbol since last sell"""
        if symbol not in self.data:
            return 0
        return self.data[symbol].get('buy_count', 0)
    
    def get_next_quantity(self, symbol, base_quantity=1, max_iterations=10):
        """
        Get the next quantity to buy using Fibonacci sequence
        
        Args:
            symbol: Stock symbol
            base_quantity: Base unit (default 1 share, can be 0.1, 2, 3, etc.)
            max_iterations: Maximum number of buy iterations (default 10)
        
        Returns:
            Quantity for next buy order, or None if max iterations reached
        """
        buy_count = self.get_buy_count(symbol)
        
        # Check if we've reached max iterations
        if buy_count >= max_iterations:
            print(f"FIBONACCI LIMIT REACHED: {symbol}")
            print(f"  Buy count: {buy_count}")
            print(f"  Max iterations: {max_iterations}")
            print(f"  ❌ NO MORE BUYS ALLOWED until position is closed")
            return None
        
        next_position = buy_count + 1  # Next buy will be position N+1
        
        fib_multiplier = self.get_fibonacci_number(next_position)
        quantity = base_quantity * fib_multiplier
        
        print(f"FIBONACCI SIZING: {symbol}")
        print(f"  Buy count: {buy_count}/{max_iterations}")
        print(f"  Next position: {next_position}")
        print(f"  Fibonacci multiplier: {fib_multiplier}")
        print(f"  Base quantity: {base_quantity}")
        print(f"  Final quantity: {quantity} shares")
        
        return quantity
    
    def record_buy(self, symbol, quantity, price=None):
        """Record a buy order"""
        if symbol not in self.data:
            self.data[symbol] = {
                'buy_count': 0,
                'buy_history': [],
                'last_sell': None
            }
        
        self.data[symbol]['buy_count'] += 1
        self.data[symbol]['buy_history'].append({
            'timestamp': datetime.now().isoformat(),
            'quantity': quantity,
            'price': price,
            'position': self.data[symbol]['buy_count']
        })
        
        self._save_data()
        
        print(f"RECORDED BUY: {symbol} - {quantity} shares (Position #{self.data[symbol]['buy_count']})")
    
    def record_sell(self, symbol):
        """Record a sell order - resets the buy count"""
        if symbol in self.data:
            self.data[symbol]['last_sell'] = datetime.now().isoformat()
            self.data[symbol]['buy_count'] = 0
            # Keep history but mark the cycle as complete
            if 'cycles' not in self.data[symbol]:
                self.data[symbol]['cycles'] = []
            
            self.data[symbol]['cycles'].append({
                'completed_at': datetime.now().isoformat(),
                'buy_history': self.data[symbol]['buy_history']
            })
            
            self.data[symbol]['buy_history'] = []
            
            self._save_data()
            
            print(f"RECORDED SELL: {symbol} - Reset buy count to 0")
    
    def get_position_info(self, symbol):
        """Get detailed position information"""
        if symbol not in self.data:
            return {
                'symbol': symbol,
                'buy_count': 0,
                'next_quantity': 1,
                'buy_history': [],
                'total_cycles': 0
            }
        
        data = self.data[symbol]
        return {
            'symbol': symbol,
            'buy_count': data.get('buy_count', 0),
            'next_quantity': self.get_next_quantity(symbol),
            'buy_history': data.get('buy_history', []),
            'total_cycles': len(data.get('cycles', [])),
            'last_sell': data.get('last_sell')
        }
    
    def get_all_tracked_symbols(self):
        """Get all symbols being tracked"""
        return list(self.data.keys())
    
    def reset_symbol(self, symbol):
        """Reset tracking for a specific symbol"""
        if symbol in self.data:
            del self.data[symbol]
            self._save_data()
            print(f"RESET: {symbol} tracking data cleared")
