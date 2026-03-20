"""
Auto RSI Scanner - Runs continuously with error handling and auto-restart
Ensures the scanner never stops running
"""
import threading
import time
import logging
from datetime import datetime
from services.rsi_scanner import RSIScanner

logger = logging.getLogger(__name__)

class AutoRSIScanner:
    def __init__(self, scan_interval=60):
        self.scanner = RSIScanner()
        self.scan_interval = scan_interval  # seconds between scans
        self.is_running = False
        self.thread = None
        self.last_scan_time = None
        self.scan_count = 0
        self.error_count = 0
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.last_error = None
        
    def start(self):
        """Start the auto scanner"""
        if self.is_running:
            logger.warning("Auto scanner is already running")
            return False
        
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info(f"🚀 Auto RSI Scanner started - scanning every {self.scan_interval} seconds")
        return True
    
    def stop(self):
        """Stop the auto scanner"""
        if not self.is_running:
            logger.warning("Auto scanner is not running")
            return False
        
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("⏹️ Auto RSI Scanner stopped")
        return True
    
    def _run_loop(self):
        """Main scanning loop with error handling and auto-restart"""
        logger.info("=" * 60)
        logger.info("AUTO RSI SCANNER - CONTINUOUS MODE")
        logger.info("=" * 60)
        
        while self.is_running:
            try:
                # Run scan
                scan_start = time.time()
                logger.info(f"\n🔍 Scan #{self.scan_count + 1} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                results = self.scanner.scan_all()
                
                scan_duration = time.time() - scan_start
                self.last_scan_time = datetime.now()
                self.scan_count += 1
                self.consecutive_errors = 0  # Reset error counter on success
                
                # Log scan summary
                signals = [r for r in results if r.get('signal')]
                logger.info(f"✅ Scan complete in {scan_duration:.2f}s - {len(results)} symbols, {len(signals)} signals")
                
                # Wait for next scan
                time.sleep(self.scan_interval)
                
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received - stopping scanner")
                self.is_running = False
                break
                
            except Exception as e:
                self.error_count += 1
                self.consecutive_errors += 1
                self.last_error = str(e)
                
                logger.error(f"❌ Scan error #{self.error_count}: {e}")
                logger.error(f"   Consecutive errors: {self.consecutive_errors}/{self.max_consecutive_errors}")
                
                # Log full traceback for debugging
                import traceback
                logger.error(traceback.format_exc())
                
                # Check if we've hit max consecutive errors
                if self.consecutive_errors >= self.max_consecutive_errors:
                    logger.critical(f"🚨 MAX CONSECUTIVE ERRORS REACHED ({self.max_consecutive_errors})")
                    logger.critical("   Attempting to reinitialize scanner...")
                    
                    try:
                        # Try to reinitialize the scanner
                        self.scanner = RSIScanner()
                        self.consecutive_errors = 0
                        logger.info("✅ Scanner reinitialized successfully")
                    except Exception as reinit_error:
                        logger.critical(f"❌ Failed to reinitialize scanner: {reinit_error}")
                        logger.critical("   Continuing with existing scanner instance...")
                
                # Wait before retry (exponential backoff)
                retry_delay = min(10 * self.consecutive_errors, 60)  # Max 60 seconds
                logger.info(f"   Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
        
        logger.info("Auto RSI Scanner loop ended")
    
    def get_status(self):
        """Get scanner status"""
        return {
            'is_running': self.is_running,
            'scan_interval': self.scan_interval,
            'last_scan_time': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'scan_count': self.scan_count,
            'error_count': self.error_count,
            'consecutive_errors': self.consecutive_errors,
            'last_error': self.last_error,
            'uptime_seconds': (datetime.now() - self.last_scan_time).total_seconds() if self.last_scan_time else 0
        }
    
    def update_settings(self, settings):
        """Update scanner settings"""
        self.scanner.update_settings(settings)
        if 'scan_interval' in settings:
            self.scan_interval = int(settings['scan_interval'])
            logger.info(f"Scan interval updated to {self.scan_interval} seconds")
    
    def is_healthy(self):
        """Check if scanner is healthy"""
        if not self.is_running:
            return False
        
        # Check if last scan was recent (within 2x scan interval)
        if self.last_scan_time:
            time_since_last_scan = (datetime.now() - self.last_scan_time).total_seconds()
            if time_since_last_scan > (self.scan_interval * 2):
                return False
        
        # Check consecutive errors
        if self.consecutive_errors >= self.max_consecutive_errors:
            return False
        
        return True

# Global instance
_auto_scanner = None

def get_auto_scanner():
    """Get or create the global auto scanner instance"""
    global _auto_scanner
    if _auto_scanner is None:
        _auto_scanner = AutoRSIScanner()
    return _auto_scanner
