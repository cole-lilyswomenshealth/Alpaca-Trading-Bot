-- ============================================================
-- Maroon Investments - Supabase Database Schema
-- Clean, organized tables for investor reporting
-- ============================================================

-- Drop old tables if they exist
DROP TABLE IF EXISTS trades CASCADE;
DROP TABLE IF EXISTS positions CASCADE;
DROP TABLE IF EXISTS strategy_settings CASCADE;
DROP TABLE IF EXISTS screener_results CASCADE;
DROP TABLE IF EXISTS watchlists CASCADE;
DROP TABLE IF EXISTS performance_metrics CASCADE;

-- ============================================================
-- 1. TRADES - Every single buy/sell execution
-- ============================================================
CREATE TABLE trades (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity DECIMAL NOT NULL,
    price DECIMAL NOT NULL,
    total_cost DECIMAL GENERATED ALWAYS AS (quantity * price) STORED,
    order_id TEXT,
    order_type TEXT DEFAULT 'market',
    source TEXT DEFAULT 'webhook' CHECK (source IN ('webhook', 'manual', 'system')),
    status TEXT DEFAULT 'filled',
    fibonacci_position INTEGER,
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_executed_at ON trades(executed_at);
CREATE INDEX idx_trades_side ON trades(side);

-- ============================================================
-- 2. POSITIONS - Open and closed position tracking
-- ============================================================
CREATE TABLE positions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT DEFAULT 'long',
    quantity DECIMAL NOT NULL,
    entry_price DECIMAL NOT NULL,
    close_price DECIMAL,
    pnl DECIMAL,
    pnl_pct DECIMAL,
    status TEXT DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    source TEXT DEFAULT 'webhook',
    fibonacci_count INTEGER DEFAULT 0,
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_positions_symbol ON positions(symbol);
CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_closed_at ON positions(closed_at);

-- ============================================================
-- 3. WEBHOOK_LOG - Every webhook received by the server
-- ============================================================
CREATE TABLE webhook_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    payload JSONB,
    symbol TEXT,
    action TEXT,
    quantity DECIMAL,
    status TEXT DEFAULT 'received' CHECK (status IN ('received', 'success', 'error', 'blocked')),
    response JSONB,
    error_message TEXT,
    source_ip TEXT,
    received_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_webhook_log_received_at ON webhook_log(received_at);
CREATE INDEX idx_webhook_log_symbol ON webhook_log(symbol);
CREATE INDEX idx_webhook_log_status ON webhook_log(status);

-- ============================================================
-- 4. DAILY_PERFORMANCE - End-of-day portfolio snapshots
-- ============================================================
CREATE TABLE daily_performance (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    portfolio_value DECIMAL,
    cash DECIMAL,
    buying_power DECIMAL,
    equity DECIMAL,
    day_pnl DECIMAL,
    day_pnl_pct DECIMAL,
    total_pnl DECIMAL,
    open_positions INTEGER,
    trades_today INTEGER,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_daily_performance_date ON daily_performance(date);

-- ============================================================
-- 5. PNL_SUMMARY - Monthly/quarterly P&L for investor reports
-- ============================================================
CREATE TABLE pnl_summary (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    period_type TEXT NOT NULL CHECK (period_type IN ('daily', 'weekly', 'monthly', 'quarterly', 'yearly')),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    starting_equity DECIMAL,
    ending_equity DECIMAL,
    net_pnl DECIMAL,
    net_pnl_pct DECIMAL,
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate DECIMAL,
    capital_deployed DECIMAL,
    return_on_capital DECIMAL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(period_type, period_start)
);

CREATE INDEX idx_pnl_summary_period ON pnl_summary(period_type, period_start);

-- ============================================================
-- Enable Row Level Security (optional, for production)
-- ============================================================
-- ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE webhook_log ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE daily_performance ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE pnl_summary ENABLE ROW LEVEL SECURITY;
