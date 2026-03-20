# Maroon Investments — Algorithmic Trading Bot

Webhook-based trading system connecting TradingView alerts to Alpaca Markets with Fibonacci position sizing, profit protection, and a live strategy settings dashboard.

## Features

- **Webhook Integration** — TradingView sends alerts, server executes trades automatically
- **Profit Protection** — Only closes positions when profitable, never takes losses
- **Fibonacci Position Sizing** — Strategic entry sizing (1, 1, 2, 3, 5, 8, 13...)
- **Live Strategy Settings** — Change strategy parameters on the fly without restarting
- **Trade Tracking** — All trades saved to Supabase
- **Performance Dashboard** — Monitor daily P&L, capital deployed, and order history

## Architecture

```
TradingView Alert → Webhook → Flask Server → Order Manager → Alpaca API
                                   ↓                ↓
                            Strategy Settings    Supabase DB
```

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your Alpaca and Supabase API keys
```

### 3. Start the Server
```bash
python server/app.py
```

### 4. Start the Dashboard Server
```bash
python start-dashboard.py
```

### 5. Expose Webhook (for TradingView)
```bash
ngrok http 5000
```
Point your TradingView alerts to the ngrok URL + `/webhook`.

## Dashboards

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| Strategy Settings | `http://localhost:8080/strategy-settings.html` | Change strategy inputs live |
| Daily Performance | `http://localhost:8080/daily-performance.html` | View P&L and trade history |

## Webhook Format

```json
{
  "symbol": "AAPL",
  "action": "buy",
  "quantity": 1,
  "order_type": "market"
}
```

## How It Works

**Buy Orders:** Webhook → check/reset Fibonacci counter → calculate Fibonacci quantity → execute buy → save to Supabase

**Sell Orders:** Webhook → check position P&L → if profitable, sell entire position → if not, block the sell and hold

## Project Structure

```
├── server/
│   ├── app.py                  # Flask server + API endpoints
│   ├── config.py               # Environment configuration
│   └── services/
│       ├── alpaca_client.py    # Alpaca API wrapper
│       ├── order_manager.py    # Order execution + Fibonacci sizing
│       ├── position_tracker.py # Fibonacci counter tracking
│       ├── risk_manager.py     # Risk validation
│       ├── supabase_client.py  # Database client
│       ├── rsi_scanner.py      # RSI-based scanning
│       ├── options_trader.py   # 0DTE options trading
│       └── portfolio_analytics.py
├── daily-performance.html      # Performance dashboard
├── strategy-settings.html      # Live strategy settings UI
├── start-dashboard.py          # Dashboard HTTP server
├── .env.example                # Environment template
└── requirements.txt
```

## Configuration

All strategy parameters can be changed live via the Settings Dashboard or in `.env`:

| Setting | Default | Description |
|---------|---------|-------------|
| `FIBONACCI_ENABLED` | true | Enable Fibonacci position sizing |
| `FIBONACCI_BASE` | 0.1 | Base quantity per buy |
| `FIBONACCI_MAX_ITERATIONS` | 8 | Max buy-ins before blocking |
| `FIBONACCI_SYMBOL_BASES` | ETH/USD=0.01 | Per-symbol base overrides |
| `MAX_POSITION_SIZE` | 10000 | Max dollar value per position |
| `MAX_OPEN_POSITIONS` | 10 | Max concurrent positions |
| `MAX_DAILY_LOSS` | 500 | Daily loss limit |
| `TRADING_ENABLED` | true | Master trading switch |

## License

MIT
