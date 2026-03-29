# Maroon Investments — Algorithmic Trading Bot

Webhook-based trading system connecting TradingView alerts to Alpaca Markets with Fibonacci position sizing, profit protection, options trading with a full option chain browser, and a consolidated live dashboard.

## Features

- **Webhook Integration** — TradingView sends alerts, server executes trades automatically
- **Profit Protection** — Only closes positions when profitable, never takes losses
- **Fibonacci Position Sizing** — Strategic entry sizing (1, 1, 2, 3, 5, 8, 13...)
- **Options Trading** — Full option chain browser with bid/ask, volume, OI. Pick any strike/expiration and trade calls or puts
- **Stock Trading** — Market, limit, and stop orders with live quote lookup
- **Live Strategy Settings** — Change strategy parameters on the fly without restarting
- **Trade Tracking** — All trades saved to Supabase (with Alpaca fallback)
- **Consolidated Dashboard** — Portfolio overview, positions, orders, webhooks, closed trades, and strategy inputs in one UI
- **Trading Dashboard** — Dedicated execution dashboard for stocks and options with option chain browser
- **Portfolio Charts** — Portfolio value line chart and daily P&L bar chart
- **RSI Scanner** — Multiple scanner modes (quote-based, streaming, auto) for finding trade setups
- **Multi-Account Support** — Optional second Alpaca account configuration
- **GCP Deployment** — Auto-deploy endpoint for CI/CD

## Architecture

```
TradingView Alert → Webhook → Flask Server → Order Manager → Alpaca API
                                   ↓                ↓
                            Strategy Settings    Supabase DB
                                   ↓
                            Dashboard (HTML)
```

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your Alpaca API keys
```

### 3. Start the Server
```bash
python server/app.py
```
The server runs on `http://localhost:5001` by default (configurable via `PORT` in `.env`).

### 4. Access Dashboards
- **Main Dashboard:** `http://localhost:5001/dashboard`
- **Trading Dashboard:** `http://localhost:5001/trading.html`

### 5. Expose for Remote Access (optional)
```bash
ngrok http 5001
```
Use the ngrok URL to access dashboards from your phone or anywhere. Point TradingView alerts to `<ngrok-url>/webhook`.

## Dashboards

### Main Dashboard (`/dashboard`)
Consolidated single-page dashboard with sidebar navigation:
| Tab | Description |
|-----|-------------|
| Portfolio | Account equity, buying power, portfolio value chart, daily P&L bar chart, positions summary |
| Positions | All open positions with live P&L and close buttons |
| Orders | Full order history with cancel buttons for open orders |
| Webhooks | Webhook activity log |
| Closed | Closed trade history with P&L |
| Inputs | Live strategy settings — trading toggles, Fibonacci sizing, profit protection, risk limits |

### Trading Dashboard (`/trading.html`)
Dedicated trade execution interface:
| Tab | Description |
|-----|-------------|
| Stocks | Place stock orders (market/limit/stop), buy/sell/long/short, live quote lookup |
| Options | Full option chain browser — pick symbol, expiration, calls/puts, see bid/ask/volume/OI, click a strike to trade |
| Positions | Open stock positions with close buttons |
| Orders | Recent orders with cancel buttons |

## API Endpoints

### Core
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/account` | Account summary (equity, buying power, status) |
| GET | `/api/positions` | Open positions |
| GET | `/api/orders` | Order history |
| POST | `/api/order` | Submit stock order |
| POST | `/webhook` | TradingView webhook receiver |

### Options
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/options/chain` | Option chain with live quotes (params: `symbol`, `expiration`, `type`, `expirations_only`) |
| POST | `/api/options/order` | Submit option order for a specific contract |
| POST | `/api/options/trade-0dte` | Auto-select and trade 0DTE option |
| GET | `/api/options/positions` | Open option positions |
| DELETE | `/api/options/close/<symbol>` | Close option position |

### Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/portfolio-analytics` | Advanced portfolio metrics |
| GET | `/api/portfolio-history` | Portfolio value history for charting |
| GET | `/api/daily-performance` | Today's P&L and closed trades |
| GET | `/api/closed-positions` | Historical closed positions |
| GET | `/api/position-stats` | Position statistics |

### Settings
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/settings` | Current strategy settings |
| POST | `/api/settings` | Update strategy settings |
| GET | `/api/risk-status` | Risk management status |

### Scanners
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/rsi-scanner/scan` | Run RSI scan |
| POST | `/api/quote-scanner/start` | Start quote-based scanner |
| POST | `/api/streaming-scanner/start` | Start streaming scanner |
| POST | `/api/auto-scanner/start` | Start auto scanner |

## Webhook Format

```json
{
  "symbol": "AAPL",
  "action": "buy",
  "qty": 1,
  "order_type": "market"
}
```

Options webhook:
```json
{
  "symbol": "SPY",
  "asset_type": "option",
  "option_direction": "call",
  "side": "buy",
  "qty": 1,
  "std_devs": 2.5
}
```

## How It Works

**Buy Orders:** Webhook → check/reset Fibonacci counter → calculate Fibonacci quantity → execute buy → save to Supabase

**Sell Orders:** Webhook → check position P&L → if profitable, sell entire position → if not, block the sell and hold

**Options Chain:** Load chain → fetch contracts from Alpaca → batch-fetch snapshots for live bid/ask → display sorted by strike → click to select → submit order

## Project Structure

```
├── server/
│   ├── app.py                      # Flask server + all API endpoints
│   ├── config.py                   # Environment config with Supabase live-reload
│   ├── accounts_config.py          # Multi-account configuration
│   └── services/
│       ├── alpaca_client.py        # Alpaca API wrapper (trading + market data)
│       ├── order_manager.py        # Order execution + Fibonacci sizing
│       ├── options_trader.py       # Options trading (0DTE, chain, strike selection)
│       ├── position_tracker.py     # Fibonacci counter tracking
│       ├── risk_manager.py         # Risk validation
│       ├── portfolio_analytics.py  # Portfolio metrics calculation
│       ├── supabase_client.py      # Supabase database client
│       ├── lot_tracker.py          # Lot-level position tracking
│       ├── rsi_scanner.py          # RSI-based stock scanning
│       ├── quote_based_rsi_scanner.py  # Quote-based RSI scanner
│       ├── streaming_rsi_scanner.py    # Streaming RSI scanner
│       ├── auto_rsi_scanner.py     # Autonomous RSI scanner
│       └── multi_account_manager.py    # Multi-account support
├── dashboard.html                  # Consolidated main dashboard (portfolio, positions, orders, settings)
├── trading.html                    # Trading execution dashboard (stocks + options chain)
├── .env.example                    # Environment template
├── requirements.txt                # Python dependencies
└── position_tracker.json           # Local Fibonacci counter state
```

## Configuration

All strategy parameters can be changed live via the Inputs tab on the dashboard or in `.env`:

| Setting | Default | Description |
|---------|---------|-------------|
| `ALPACA_API_KEY` | — | Alpaca API key (required) |
| `ALPACA_SECRET_KEY` | — | Alpaca secret key (required) |
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` | Paper or live trading URL |
| `PORT` | 5001 | Server port |
| `TRADING_ENABLED` | true | Master trading switch |
| `FIBONACCI_ENABLED` | true | Enable Fibonacci position sizing |
| `FIBONACCI_BASE` | 1.0 | Base quantity per buy |
| `FIBONACCI_MAX_ITERATIONS` | 10 | Max buy-ins before blocking |
| `FIBONACCI_SYMBOL_BASES` | — | Per-symbol base overrides (e.g. `ETH/USD=0.01`) |
| `MAX_POSITION_SIZE` | 10000 | Max dollar value per position |
| `MAX_OPEN_POSITIONS` | 10 | Max concurrent positions |
| `MAX_DAILY_LOSS` | 500 | Daily loss limit |
| `SUPABASE_URL` | — | Supabase project URL (optional) |
| `SUPABASE_KEY` | — | Supabase anon key (optional) |

## Deployment

The server can be deployed to any cloud provider. A `/deploy` endpoint is included for CI/CD auto-deploy workflows.

For local development with remote access, use ngrok:
```bash
ngrok http 5001
```

## License

MIT
