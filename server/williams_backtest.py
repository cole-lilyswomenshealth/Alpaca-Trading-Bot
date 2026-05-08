"""
Larry Williams Volatility Breakout — historical backtester.

Usage:
    cd server
    python williams_backtest.py --symbols SPY QQQ IWM --years 10
    python williams_backtest.py --symbols AAPL MSFT --k 0.5 --stop-mult 1.0 --no-vol-filter
    python williams_backtest.py --csv my_data.csv  (offline mode)

Data sources, in order of preference:
    1. Alpaca historical bars (uses your existing ALPACA_API_KEY).
    2. yfinance fallback (free, daily bars only) — pip install yfinance.
    3. CSV file with columns: date,Open,High,Low,Close,Volume.

Outputs:
    - Per-symbol metrics table printed to stdout.
    - Combined equity curve CSV written to ./equity_curves.csv.
    - Optional matplotlib chart if --plot is passed.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Allow running from either server/ or repo root.
THIS = Path(__file__).resolve()
REPO_ROOT = THIS.parent.parent
sys.path.insert(0, str(THIS.parent))         # so `services...` imports work
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

from services.williams_breakout import WilliamsParams, backtest


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_alpaca(symbol: str, years: int) -> pd.DataFrame | None:
    """Try Alpaca first; return None if creds aren't set or any error occurs."""
    try:
        from services.alpaca_client import AlpacaClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        client = AlpacaClient()
        end = datetime.utcnow()
        start = end - timedelta(days=years * 366)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed='sip',
        )
        bars = client.data_client.get_stock_bars(req)
        if symbol not in bars.data:
            return None
        rows = [{
            'date': b.timestamp,
            'Open': float(b.open),
            'High': float(b.high),
            'Low': float(b.low),
            'Close': float(b.close),
            'Volume': float(b.volume),
        } for b in bars.data[symbol]]
        if not rows:
            return None
        return pd.DataFrame(rows).set_index('date').sort_index()
    except Exception as e:
        print(f"  [alpaca] {symbol}: {e}")
        return None


def load_yfinance(symbol: str, years: int) -> pd.DataFrame | None:
    try:
        import yfinance as yf
    except ImportError:
        print("  [yfinance] not installed — `pip install yfinance` to use the free fallback")
        return None
    try:
        period = f"{years}y" if years <= 10 else "max"
        df = yf.download(symbol, period=period, progress=False, auto_adjust=False)
        if df is None or df.empty:
            return None
        df = df.rename(columns={
            'Adj Close': 'AdjClose'
        })
        # yfinance sometimes returns a MultiIndex on single tickers — flatten it.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]
    except Exception as e:
        print(f"  [yfinance] {symbol}: {e}")
        return None


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Try to find a date column.
    date_col = next((c for c in df.columns if c.lower() in ('date', 'datetime', 'timestamp')), None)
    if not date_col:
        raise ValueError(f"CSV missing a date column. Saw: {list(df.columns)}")
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col).sort_index()
    df = df.rename(columns={c: c.title() for c in df.columns})
    return df


def get_data(symbol: str, years: int, csv: str | None) -> pd.DataFrame | None:
    if csv:
        return load_csv(csv)
    df = load_alpaca(symbol, years)
    if df is not None and not df.empty:
        print(f"  [{symbol}] loaded {len(df)} bars from Alpaca")
        return df
    df = load_yfinance(symbol, years)
    if df is not None and not df.empty:
        print(f"  [{symbol}] loaded {len(df)} bars from yfinance")
        return df
    return None


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def fmt_pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def print_metrics(symbol: str, m: dict):
    print(f"\n=== {symbol} ===")
    print(f"  Trades        : {m.get('num_trades', 0)}")
    print(f"  Win rate      : {m.get('win_rate', 0) * 100:.1f}%")
    print(f"  Total return  : {fmt_pct(m.get('total_return', 0))}")
    print(f"  CAGR          : {fmt_pct(m.get('cagr', 0))}")
    print(f"  Sharpe        : {m.get('sharpe', 0):.2f}")
    print(f"  Max drawdown  : {fmt_pct(m.get('max_drawdown', 0))}")
    print(f"  Avg win       : {fmt_pct(m.get('avg_win_pct', 0))}")
    print(f"  Avg loss      : {fmt_pct(m.get('avg_loss_pct', 0))}")
    print(f"  Profit factor : {m.get('profit_factor', 0):.2f}")
    print(f"  Final equity  : ${m.get('final_equity', 0):,.2f}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Larry Williams Volatility Breakout backtester")
    p.add_argument('--symbols', nargs='+', default=['SPY', 'QQQ', 'IWM'])
    p.add_argument('--years', type=int, default=10)
    p.add_argument('--csv', type=str, default=None,
                   help="Path to a CSV with date,Open,High,Low,Close,Volume — bypasses online data sources")
    p.add_argument('--equity', type=float, default=10_000.0)
    p.add_argument('--risk-per-trade', type=float, default=0.02,
                   help="Fraction of equity to risk on a full stop-out (default 0.02 = 2%)")
    p.add_argument('--k', type=float, default=0.5)
    p.add_argument('--stop-mult', type=float, default=1.0)
    p.add_argument('--no-trend-filter', action='store_true')
    p.add_argument('--no-vol-filter', action='store_true')
    p.add_argument('--allow-shorts', action='store_true')
    p.add_argument('--commission', type=float, default=0.0)
    p.add_argument('--slippage-bps', type=float, default=1.0)
    p.add_argument('--out', default='equity_curves.csv')
    p.add_argument('--plot', action='store_true')
    args = p.parse_args(argv)

    params = WilliamsParams(
        k=args.k,
        stop_mult=args.stop_mult,
        use_trend_filter=not args.no_trend_filter,
        use_vol_filter=not args.no_vol_filter,
        allow_shorts=args.allow_shorts,
        commission_per_trade=args.commission,
        slippage_bps=args.slippage_bps,
    )

    print("Larry Williams Volatility Breakout — Backtest")
    print(f"Params: {params.as_dict()}")
    print(f"Universe: {args.symbols} | Years: {args.years} | Starting equity: ${args.equity:,.0f}")

    all_curves = {}
    for sym in args.symbols:
        df = get_data(sym, args.years, args.csv)
        if df is None or df.empty:
            print(f"  [{sym}] no data — skipping")
            continue
        result = backtest(df, params, starting_equity=args.equity,
                          risk_per_trade=args.risk_per_trade)
        print_metrics(sym, result['metrics'])
        all_curves[sym] = result['equity']

    if not all_curves:
        print("\nNo results. Check your data sources / API keys.")
        return 1

    eq_df = pd.DataFrame(all_curves)
    eq_df.to_csv(args.out)
    print(f"\nEquity curves written to {args.out}")

    if args.plot:
        try:
            import matplotlib.pyplot as plt
            plt.figure(figsize=(11, 6))
            for sym, s in all_curves.items():
                plt.plot(s.index, s.values, label=sym)
            plt.title("Larry Williams Volatility Breakout — Equity Curves")
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            chart_path = args.out.replace('.csv', '.png')
            plt.savefig(chart_path, dpi=120)
            print(f"Chart saved to {chart_path}")
        except ImportError:
            print("matplotlib not installed — skipping chart")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
