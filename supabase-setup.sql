-- Strategy Settings table for real-time bot configuration
-- Run this in your Supabase SQL Editor (Dashboard → SQL Editor → New Query)

CREATE TABLE IF NOT EXISTS strategy_settings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL DEFAULT 'string',
    label TEXT,
    category TEXT DEFAULT 'general',
    description TEXT DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security but allow all operations with anon key
ALTER TABLE strategy_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all access to strategy_settings"
    ON strategy_settings
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Index for fast key lookups
CREATE INDEX IF NOT EXISTS idx_strategy_settings_key ON strategy_settings(key);
