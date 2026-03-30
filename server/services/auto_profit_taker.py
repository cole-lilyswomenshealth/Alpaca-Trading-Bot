"""
Auto Profit Taker
Background scanner that monitors positions and auto-sells when profit target is hit.
Runs independently of webhooks — no TradingView signal needed to exit.
"""
import threading
import time
import logging
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'auto_profit_settings.json')

class AutoProfitTaker:
    def __init__(self, alpaca_client):
        self.client = alpaca_client
        self.running = False
        self.thread = None
        self.scan_interval = 5  # seconds between scans
        self.default_target = 0.5  # default profit % target
        self.symbol_targets = {}  # per-symbol overrides
        self.enabled = False
        self.last_scan = None
        self.scan_count = 0
        self.sells_executed = 0
        self.log = []  # recent activity log
        self._load_settings()

    def _load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    s = json.load(f)
                self.enabled = s.get('enabled', False)
                self.default_target = s.get('default_target', 0.5)
                self.symbol_targets = s.get('symbol_targets', {})
                self.scan_interval = s.get('scan_interval', 5)
        except Exception as e:
            logger.error(f"Error loading auto-profit settings: {e}")

    def _save_settings(self):
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump({
                    'enabled': self.enabled,
                    'default_target': self.default_target,
                    'symbol_targets': self.symbol_targets,
                    'scan_interval': self.scan_interval,
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving auto-profit settings: {e}")

    def update_settings(self, settings):
        if 'enabled' in settings:
            self.enabled = settings['enabled']
        if 'default_target' in settings:
            self.default_target = float(settings['default_target'])
        if 'symbol_targets' in settings:
            self.symbol_targets = settings['symbol_targets']
        if 'scan_interval' in settings:
            self.scan_interval = max(2, int(settings['scan_interval']))
        self._save_settings()
        # Start or stop based on enabled
        if self.enabled and not self.running:
            self.start()
        elif not self.enabled and self.running:
            self.stop()

    def get_status(self):
        return {
            'enabled': self.enabled,
            'running': self.running,
            'default_target': self.default_target,
            'symbol_targets': self.symbol_targets,
            'scan_interval': self.scan_interval,
            'last_scan': self.last_scan,
            'scan_count': self.scan_count,
            'sells_executed': self.sells_executed,
            'log': self.log[-20:]  # last 20 entries
        }

    def _add_log(self, msg, type='info'):
        entry = {'time': datetime.now().isoformat(), 'msg': msg, 'type': type}
        self.log.append(entry)
        if len(self.log) > 100:
            self.log = self.log[-100:]

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.thread.start()
        self._add_log('Auto Profit Taker started', 'success')
        logger.info("Auto Profit Taker started")

    def stop(self):
        self.running = False
        self._add_log('Auto Profit Taker stopped', 'info')
        logger.info("Auto Profit Taker stopped")

    def _get_target(self, symbol):
        """Get profit target for a symbol (check overrides first)"""
        # Check both formats: BTCUSD and BTC/USD
        if symbol in self.symbol_targets:
            return float(self.symbol_targets[symbol])
        clean = symbol.replace('/', '')
        if clean in self.symbol_targets:
            return float(self.symbol_targets[clean])
        slashed = symbol
        if '/' not in symbol and symbol.endswith('USD') and len(symbol) > 3:
            slashed = symbol[:-3] + '/' + symbol[-3:]
        if slashed in self.symbol_targets:
            return float(self.symbol_targets[slashed])
        return self.default_target

    def _scan_loop(self):
        while self.running:
            try:
                self._scan_positions()
            except Exception as e:
                logger.error(f"Auto profit scan error: {e}")
                self._add_log(f'Scan error: {str(e)}', 'error')
            time.sleep(self.scan_interval)

    def _scan_positions(self):
        if not self.enabled:
            return

        positions = self.client.get_positions()
        self.last_scan = datetime.now().isoformat()
        self.scan_count += 1

        for pos in positions:
            symbol = pos.symbol
            qty = float(pos.qty)
            unrealized_plpc = float(pos.unrealized_plpc) * 100  # Convert to %
            unrealized_pl = float(pos.unrealized_pl)
            target = self._get_target(symbol)

            if unrealized_plpc >= target and target > 0:
                # Target hit — sell entire position
                try:
                    is_crypto = '/' in symbol or (len(symbol) > 4 and symbol.endswith('USD') and not symbol[0].isdigit())
                    tif = 'gtc' if is_crypto else 'day'

                    order = self.client.submit_market_order(
                        symbol=symbol,
                        qty=abs(qty),
                        side='sell',
                        time_in_force=tif
                    )
                    self.sells_executed += 1
                    msg = f'SOLD {symbol}: {qty} shares at {unrealized_plpc:.2f}% profit (${unrealized_pl:.2f}) — target was {target}%'
                    self._add_log(msg, 'success')
                    logger.info(f"Auto Profit Taker: {msg}")
                except Exception as e:
                    msg = f'Failed to sell {symbol}: {str(e)}'
                    self._add_log(msg, 'error')
                    logger.error(f"Auto Profit Taker: {msg}")


# Singleton
_instance = None

def get_auto_profit_taker(alpaca_client=None):
    global _instance
    if _instance is None and alpaca_client:
        _instance = AutoProfitTaker(alpaca_client)
        if _instance.enabled:
            _instance.start()
    return _instance
