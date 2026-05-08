"""
Auto Williams Breakout Scanner — runs the volatility-breakout scanner on a
threaded loop with error handling, exponential backoff, and an EOD flatten
that closes any position the scanner opened today.

Mirrors the structure of services.auto_rsi_scanner.AutoRSIScanner.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, time as dtime, timezone
from typing import Optional

import pytz

from services.williams_breakout_scanner import (
    WilliamsBreakoutScanner, get_scanner,
)

logger = logging.getLogger(__name__)

EASTERN = pytz.timezone('US/Eastern')
MARKET_OPEN = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)
EOD_FLATTEN_AT = dtime(15, 55)  # close 5 min before the bell


class AutoWilliamsScanner:
    def __init__(self, scan_interval: int = 60):
        self.scanner: WilliamsBreakoutScanner = get_scanner()
        self.scan_interval = scan_interval  # seconds between scans
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.last_scan_time: Optional[datetime] = None
        self.scan_count = 0
        self.error_count = 0
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.last_error: Optional[str] = None
        self._eod_flattened_for: Optional[str] = None  # ISO date of last EOD close

    # -- lifecycle -------------------------------------------------------

    def start(self) -> bool:
        if self.is_running:
            logger.warning("Auto Williams scanner already running")
            return False
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info(f"🚀 Auto Williams scanner started — every {self.scan_interval}s")
        return True

    def stop(self) -> bool:
        if not self.is_running:
            logger.warning("Auto Williams scanner not running")
            return False
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("⏹️ Auto Williams scanner stopped")
        return True

    # -- run loop --------------------------------------------------------

    def _run_loop(self):
        logger.info("=" * 60)
        logger.info("AUTO WILLIAMS BREAKOUT SCANNER — CONTINUOUS MODE")
        logger.info("=" * 60)

        while self.is_running:
            try:
                now_et = datetime.now(EASTERN)

                if self._should_flatten(now_et):
                    self._flatten_today_positions()

                if not self._market_open(now_et):
                    # Sleep longer outside of market hours to be polite
                    time.sleep(min(self.scan_interval * 5, 300))
                    continue

                t0 = time.time()
                logger.info(f"🔍 Williams scan #{self.scan_count + 1} — {now_et:%Y-%m-%d %H:%M:%S %Z}")
                results = self.scanner.scan_all()
                duration = time.time() - t0
                self.last_scan_time = datetime.now(timezone.utc)
                self.scan_count += 1
                self.consecutive_errors = 0

                signals = [r for r in results if r.get('signal')]
                logger.info(f"✅ Williams scan complete in {duration:.2f}s — {len(results)} symbols, {len(signals)} signals")

                time.sleep(self.scan_interval)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt — stopping Williams scanner")
                self.is_running = False
                break

            except Exception as e:
                self.error_count += 1
                self.consecutive_errors += 1
                self.last_error = str(e)
                logger.error(f"❌ Williams scan error #{self.error_count}: {e}")
                import traceback
                logger.error(traceback.format_exc())

                if self.consecutive_errors >= self.max_consecutive_errors:
                    logger.critical(f"🚨 Williams scanner: {self.consecutive_errors} consecutive errors — reinitializing")
                    try:
                        self.scanner = WilliamsBreakoutScanner()
                        self.consecutive_errors = 0
                    except Exception as reinit_err:
                        logger.critical(f"   reinit failed: {reinit_err}")

                retry_delay = min(10 * self.consecutive_errors, 60)
                time.sleep(retry_delay)

        logger.info("Auto Williams scanner loop ended")

    # -- helpers ---------------------------------------------------------

    def _market_open(self, now_et: datetime) -> bool:
        if now_et.weekday() >= 5:  # Sat/Sun
            return False
        return MARKET_OPEN <= now_et.time() <= MARKET_CLOSE

    def _should_flatten(self, now_et: datetime) -> bool:
        """At 3:55pm ET on a trading day, if we haven't flattened yet, do it."""
        if now_et.weekday() >= 5:
            return False
        if not (EOD_FLATTEN_AT <= now_et.time() <= MARKET_CLOSE):
            return False
        today_iso = now_et.date().isoformat()
        return self._eod_flattened_for != today_iso

    def _flatten_today_positions(self):
        """Close any open position whose symbol fired a Williams entry today.

        The Larry Williams system holds intraday only — we exit at the close.
        """
        try:
            today_iso = datetime.now(EASTERN).date().isoformat()
            fired_today = []
            for sym, st in self.scanner._session_state.items():
                d = st.get('date')
                if d and d.isoformat() == today_iso and st.get('fired'):
                    fired_today.append(sym)

            if not fired_today:
                self._eod_flattened_for = today_iso
                return

            logger.info(f"🛎️ EOD flatten — closing Williams entries: {fired_today}")
            for sym in fired_today:
                try:
                    self.scanner.alpaca.close_position(sym)
                    logger.info(f"  closed {sym}")
                except Exception as e:
                    logger.error(f"  could not close {sym}: {e}")

            # Also cancel any unfilled protective-stop orders we placed for those symbols
            try:
                from alpaca.trading.enums import QueryOrderStatus
                from alpaca.trading.requests import GetOrdersRequest
                req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=200)
                open_orders = self.scanner.alpaca.trading_client.get_orders(req)
                for o in open_orders:
                    if o.symbol in fired_today and o.type.value == 'stop':
                        try:
                            self.scanner.alpaca.cancel_order(o.id)
                            logger.info(f"  cancelled stop {o.id} for {o.symbol}")
                        except Exception as e:
                            logger.error(f"  could not cancel stop {o.id}: {e}")
            except Exception as e:
                logger.error(f"  EOD stop-cancel sweep failed: {e}")

            self._eod_flattened_for = today_iso
        except Exception as e:
            logger.error(f"EOD flatten failed: {e}")

    # -- introspection ---------------------------------------------------

    def update_settings(self, settings: dict) -> None:
        if 'scan_interval' in settings:
            try:
                self.scan_interval = int(settings['scan_interval'])
                logger.info(f"Williams scan interval set to {self.scan_interval}s")
            except Exception:
                pass
        # Pass through any scanner-specific settings (symbols, k, stop_mult, ...)
        self.scanner.update_settings(settings)

    def get_status(self) -> dict:
        return {
            'is_running': self.is_running,
            'scan_interval': self.scan_interval,
            'last_scan_time': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'scan_count': self.scan_count,
            'error_count': self.error_count,
            'consecutive_errors': self.consecutive_errors,
            'last_error': self.last_error,
            'eod_flattened_for': self._eod_flattened_for,
            'scanner': self.scanner.get_status(),
        }

    def is_healthy(self) -> bool:
        if not self.is_running:
            return False
        if self.consecutive_errors >= self.max_consecutive_errors:
            return False
        if self.last_scan_time:
            age = (datetime.now(timezone.utc) - self.last_scan_time).total_seconds()
            if age > self.scan_interval * 4:
                return False
        return True


# Module-level singleton (matches AutoRSIScanner pattern)
_auto_scanner: Optional[AutoWilliamsScanner] = None


def get_auto_williams_scanner() -> AutoWilliamsScanner:
    global _auto_scanner
    if _auto_scanner is None:
        _auto_scanner = AutoWilliamsScanner()
    return _auto_scanner
