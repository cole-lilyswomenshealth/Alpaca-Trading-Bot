"""
Multi-Account Configuration
Supports multiple Alpaca accounts with different strategies
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Account configurations
ACCOUNTS = {
    'account1': {
        'name': 'Account 1 - Main Strategy',
        'api_key': os.getenv('ALPACA_API_KEY'),
        'secret_key': os.getenv('ALPACA_SECRET_KEY'),
        'base_url': os.getenv('ALPACA_BASE_URL'),
        'fibonacci_enabled': True,
        'fibonacci_base': 0.1,
        'fibonacci_max_iterations': 8,
        'profit_protection_enabled': True,
        'profit_protection_threshold': 0.05,
        'webhook_path': '/webhook/account1'
    },
    'account2': {
        'name': 'Account 2 - Alternative Strategy',
        'api_key': os.getenv('ALPACA_API_KEY_2', ''),  # Add second account credentials
        'secret_key': os.getenv('ALPACA_SECRET_KEY_2', ''),
        'base_url': os.getenv('ALPACA_BASE_URL_2', 'https://paper-api.alpaca.markets'),
        'fibonacci_enabled': True,
        'fibonacci_base': 0.2,  # Different base
        'fibonacci_max_iterations': 6,  # Different max
        'profit_protection_enabled': True,
        'profit_protection_threshold': 0.03,  # Different threshold
        'webhook_path': '/webhook/account2'
    }
}

def get_account_config(account_id):
    """Get configuration for specific account"""
    return ACCOUNTS.get(account_id)

def get_all_accounts():
    """Get all configured accounts"""
    return ACCOUNTS

def is_account_configured(account_id):
    """Check if account has valid credentials"""
    config = ACCOUNTS.get(account_id)
    if not config:
        return False
    return bool(config['api_key'] and config['secret_key'])
