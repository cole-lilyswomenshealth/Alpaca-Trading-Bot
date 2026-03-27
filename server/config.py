import os
import logging
import time
from dotenv import load_dotenv

# Force reload environment variables
load_dotenv(override=True)

logger = logging.getLogger(__name__)


class Config:
    # Alpaca API (always from .env — never change these from dashboard)
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

    # ---- Defaults (used when Supabase is unavailable) ----
    _DEFAULTS = {
        'trading_enabled': True,
        'fibonacci_enabled': True,
        'fibonacci_base': 1.0,
        'fibonacci_max_iterations': 10,
        'fibonacci_symbol_bases': {},
        'max_position_size': 10000.0,
        'max_daily_loss': 500.0,
        'max_open_positions': 10,
        'profit_protection_enabled': True,
        'profit_protection_threshold': 0.0,
    }

    def __init__(self):
        self._supabase = None
        self._cache = {}
        self._cache_time = 0
        self._cache_ttl = 5  # seconds — re-read from Supabase every 5s

        # Load .env defaults into _DEFAULTS overrides
        env_overrides = {
            'trading_enabled': os.getenv('TRADING_ENABLED', 'true').lower() == 'true',
            'fibonacci_enabled': os.getenv('FIBONACCI_ENABLED', 'true').lower() == 'true',
            'fibonacci_base': float(os.getenv('FIBONACCI_BASE', 1.0)),
            'fibonacci_max_iterations': int(os.getenv('FIBONACCI_MAX_ITERATIONS', 10)),
            'max_position_size': float(os.getenv('MAX_POSITION_SIZE', 10000)),
            'max_daily_loss': float(os.getenv('MAX_DAILY_LOSS', 500)),
            'max_open_positions': int(os.getenv('MAX_OPEN_POSITIONS', 10)),
        }
        self._DEFAULTS.update(env_overrides)

        # Parse symbol bases from .env
        symbol_bases_str = os.getenv('FIBONACCI_SYMBOL_BASES', '')
        if symbol_bases_str:
            bases = {}
            for pair in symbol_bases_str.split(','):
                if '=' in pair:
                    sym, base = pair.strip().split('=')
                    bases[sym.strip().upper()] = float(base.strip())
            self._DEFAULTS['fibonacci_symbol_bases'] = bases

    def _get_supabase(self):
        """Lazy-load Supabase client"""
        if self._supabase is None:
            try:
                from services.supabase_client import SupabaseClient
                self._supabase = SupabaseClient()
            except Exception:
                self._supabase = None
        return self._supabase

    def _load_settings(self):
        """Load settings from local JSON file with caching"""
        now = time.time()
        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        # Read from local settings.json file
        try:
            import json
            settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.json')
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    self._cache = json.load(f)
                self._cache_time = now
                return self._cache
        except Exception as e:
            logger.warning(f"Failed to load settings.json: {e}")

        # Fallback: try Supabase
        sb = self._get_supabase()
        if sb and sb.is_connected():
            try:
                raw = sb.get_settings()
                if raw:
                    self._cache = {k: sb._cast_value(v['value'], v['type']) for k, v in raw.items()}
                    self._cache_time = now
                    return self._cache
            except Exception as e:
                logger.warning(f"Failed to load settings from Supabase: {e}")

        return {}

    def _get(self, key):
        """Get a setting: Supabase first, then .env default"""
        settings = self._load_settings()
        if key in settings:
            return settings[key]
        return self._DEFAULTS.get(key)

    # ---- Properties the server reads ----
    @property
    def TRADING_ENABLED(self):
        return self._get('trading_enabled')

    @property
    def FIBONACCI_ENABLED(self):
        return self._get('fibonacci_enabled')

    @property
    def FIBONACCI_BASE(self):
        return self._get('fibonacci_base')

    @property
    def FIBONACCI_MAX_ITERATIONS(self):
        return self._get('fibonacci_max_iterations')

    @property
    def FIBONACCI_SYMBOL_BASES(self):
        val = self._get('fibonacci_symbol_bases')
        if isinstance(val, str):
            import json
            try:
                return json.loads(val)
            except:
                return {}
        return val or {}

    @property
    def MAX_POSITION_SIZE(self):
        return self._get('max_position_size')

    @property
    def MAX_DAILY_LOSS(self):
        return self._get('max_daily_loss')

    @property
    def MAX_OPEN_POSITIONS(self):
        return self._get('max_open_positions')

    @property
    def PROFIT_PROTECTION_ENABLED(self):
        return self._get('profit_protection_enabled')

    @property
    def PROFIT_PROTECTION_THRESHOLD(self):
        return self._get('profit_protection_threshold')

    @property
    def is_paper_trading(self):
        return 'paper' in self.ALPACA_BASE_URL.lower()
