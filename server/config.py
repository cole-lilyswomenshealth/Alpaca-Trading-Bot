import os
from dotenv import load_dotenv

# Force reload environment variables
load_dotenv(override=True)

class Config:
    # Alpaca API
    ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
    ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
    ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    
    # Server
    PORT = int(os.getenv('PORT', 5000))
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///trading_bot.db')
    
    # Security
    WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET')
    
    # Risk Management
    MAX_POSITION_SIZE = float(os.getenv('MAX_POSITION_SIZE', 10000))
    MAX_DAILY_LOSS = float(os.getenv('MAX_DAILY_LOSS', 500))
    MAX_OPEN_POSITIONS = int(os.getenv('MAX_OPEN_POSITIONS', 10))
    TRADING_ENABLED = os.getenv('TRADING_ENABLED', 'true').lower() == 'true'
    
    # Fibonacci Position Sizing
    FIBONACCI_ENABLED = os.getenv('FIBONACCI_ENABLED', 'true').lower() == 'true'
    FIBONACCI_BASE = float(os.getenv('FIBONACCI_BASE', 1.0))  # Base quantity (1 = 1 share, 0.1 = fractional, etc.)
    FIBONACCI_MAX_ITERATIONS = int(os.getenv('FIBONACCI_MAX_ITERATIONS', 10))  # Max buy orders before blocking
    
    # Per-symbol Fibonacci bases (optional overrides)
    FIBONACCI_SYMBOL_BASES = {}
    symbol_bases_str = os.getenv('FIBONACCI_SYMBOL_BASES', '')
    if symbol_bases_str:
        for pair in symbol_bases_str.split(','):
            if '=' in pair:
                symbol, base = pair.strip().split('=')
                FIBONACCI_SYMBOL_BASES[symbol.strip().upper()] = float(base.strip())
    
    @property
    def is_paper_trading(self):
        return 'paper' in self.ALPACA_BASE_URL.lower()
