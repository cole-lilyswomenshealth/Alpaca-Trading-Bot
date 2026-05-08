"""
Larry Williams Volatility Breakout — strategy core.

The same family of system Larry Williams used to win the 1987 Robbins World Cup
and his daughter Michelle won in 1997 (turning $10k into ~$100k). Adapted for
equities (long-only by default).

Strategy in one sentence:
    Buy if today's price thrusts K * yesterday's range above today's open;
    exit at the close; stop loss STOP_MULT * yesterday's range below entry.

Inputs (configurable):
    K              breakout fraction of prev-day range          (default 0.5)
    STOP_MULT      stop-loss as multiple of prev-day range      (default 1.0)
    USE_TREND_FILTER   only long when close > 200d SMA          (default True)
    USE_VOL_FILTER     only trade when ATR(10) > avg(ATR(10),50) (default True)
    ALLOW_SHORTS   take symmetric breakdown signals too          (default False)

This module is pure pandas — no Flask/Alpaca deps — so it can be reused by
both the live scanner and the backtester. It exposes:

    add_signal_columns(df, **params)   ->  df with signal/level/stop columns
    backtest(df, **params)             ->  trade list + equity curve
    breakout_levels(prev_high, prev_low, today_open, k=0.5)
                                       ->  (long_trigger, short_trigger)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

@dataclass
class WilliamsParams:
    k: float = 0.5                       # breakout fraction of prev-day range
    stop_mult: float = 1.0               # stop-loss = stop_mult * prev-day range
    sma_len: int = 200                   # trend filter
    atr_len: int = 10                    # short ATR for vol filter
    atr_avg_len: int = 50                # baseline for vol filter
    use_trend_filter: bool = True
    use_vol_filter: bool = True
    allow_shorts: bool = False
    commission_per_trade: float = 0.0    # $ per round trip (or per side, see backtest)
    slippage_bps: float = 1.0            # basis points of price per fill

    def as_dict(self) -> dict:
        return {
            'k': self.k, 'stop_mult': self.stop_mult,
            'sma_len': self.sma_len, 'atr_len': self.atr_len,
            'atr_avg_len': self.atr_avg_len,
            'use_trend_filter': self.use_trend_filter,
            'use_vol_filter': self.use_vol_filter,
            'allow_shorts': self.allow_shorts,
            'commission_per_trade': self.commission_per_trade,
            'slippage_bps': self.slippage_bps,
        }


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1
    ).max(axis=1)
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    return true_range(high, low, close).rolling(n, min_periods=n).mean()


def breakout_levels(prev_high: float, prev_low: float, today_open: float,
                    k: float = 0.5) -> tuple[float, float]:
    """Long trigger above today's open by k*prev_range; short trigger symmetric."""
    rng = prev_high - prev_low
    return today_open + k * rng, today_open - k * rng


# ---------------------------------------------------------------------------
# Signal column builder
# ---------------------------------------------------------------------------

def add_signal_columns(df: pd.DataFrame, params: Optional[WilliamsParams] = None
                        ) -> pd.DataFrame:
    """
    Given a daily OHLCV DataFrame indexed by date with columns
        Open, High, Low, Close
    return a copy with columns added:

        prev_range          High[-1] - Low[-1]
        long_trigger        Open + k*prev_range
        short_trigger       Open - k*prev_range
        long_signal         bool — High >= long_trigger AND filters pass
        short_signal        bool — Low  <= short_trigger AND filters pass + shorts allowed
        long_entry          fill price for long entries (= long_trigger)
        short_entry         fill price for short entries (= short_trigger)
        long_stop           entry - stop_mult * prev_range
        short_stop          entry + stop_mult * prev_range
        sma                 close-based trend SMA
        atr_short, atr_long ATR series for vol filter
    """
    if params is None:
        params = WilliamsParams()

    out = df.copy()
    # tolerate lowercase column names from yfinance/alpaca
    rename = {c: c.title() for c in out.columns if c.lower() in
              ('open', 'high', 'low', 'close', 'volume')}
    out = out.rename(columns=rename)

    o, h, l, c = out['Open'], out['High'], out['Low'], out['Close']

    out['prev_range'] = (h.shift(1) - l.shift(1))
    out['long_trigger'] = o + params.k * out['prev_range']
    out['short_trigger'] = o - params.k * out['prev_range']

    # Filters use *yesterday's* values to avoid look-ahead.
    out['sma'] = c.rolling(params.sma_len, min_periods=params.sma_len).mean()
    out['atr_short'] = atr(h, l, c, params.atr_len)
    out['atr_long'] = out['atr_short'].rolling(
        params.atr_avg_len, min_periods=params.atr_avg_len
    ).mean()

    trend_ok = (~params.use_trend_filter) | (c.shift(1) > out['sma'].shift(1))
    vol_ok = (~params.use_vol_filter) | (out['atr_short'].shift(1) > out['atr_long'].shift(1))
    filters_ok = trend_ok & vol_ok

    out['long_signal'] = (h >= out['long_trigger']) & filters_ok & out['prev_range'].notna()
    out['short_signal'] = (
        params.allow_shorts
        & (l <= out['short_trigger'])
        & filters_ok
        & out['prev_range'].notna()
    )

    out['long_entry'] = out['long_trigger']
    out['short_entry'] = out['short_trigger']
    out['long_stop'] = out['long_entry'] - params.stop_mult * out['prev_range']
    out['short_stop'] = out['short_entry'] + params.stop_mult * out['prev_range']

    return out


# ---------------------------------------------------------------------------
# Daily backtester (long-only by default; long+short if allow_shorts=True)
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    side: str                # 'long' or 'short'
    entry_price: float
    exit_price: float
    stop_price: float
    pnl_pct: float           # signed
    exit_reason: str         # 'eod' or 'stop'


def _apply_slippage(price: float, side: str, action: str, bps: float) -> float:
    """Adverse slippage: pay more on buy, receive less on sell."""
    adj = price * (bps / 10_000.0)
    if side == 'long':
        return price + adj if action == 'enter' else price - adj
    else:  # short
        return price - adj if action == 'enter' else price + adj


def backtest(df: pd.DataFrame, params: Optional[WilliamsParams] = None,
             starting_equity: float = 10_000.0,
             risk_per_trade: float = 0.02) -> dict:
    """
    Run the strategy bar-by-bar. One position at a time. Position sized so that
    a full stop-out loses approximately `risk_per_trade` of current equity.

    Returns:
        {
          'trades': list[Trade],
          'equity': pd.Series indexed by date,
          'metrics': {...}
        }
    """
    if params is None:
        params = WilliamsParams()

    s = add_signal_columns(df, params)

    equity = starting_equity
    equity_curve: list[tuple[pd.Timestamp, float]] = []
    trades: list[Trade] = []

    for date, row in s.iterrows():
        long_taken = bool(row['long_signal'])
        short_taken = bool(row['short_signal']) and params.allow_shorts

        # Prefer long over short if both fire on the same bar (shouldn't normally
        # happen with a sane K, but be deterministic).
        side = 'long' if long_taken else ('short' if short_taken else None)

        if side is None:
            equity_curve.append((date, equity))
            continue

        entry_raw = row['long_entry'] if side == 'long' else row['short_entry']
        stop_raw = row['long_stop'] if side == 'long' else row['short_stop']
        entry = _apply_slippage(entry_raw, side, 'enter', params.slippage_bps)
        stop = stop_raw  # the stop level itself isn't slipped; the *fill* is
        risk_per_share = abs(entry - stop)
        if risk_per_share <= 0:
            equity_curve.append((date, equity))
            continue

        # Position sizing: lose ~risk_per_trade of equity if stopped out.
        dollars_at_risk = equity * risk_per_trade
        shares = dollars_at_risk / risk_per_share
        if shares <= 0:
            equity_curve.append((date, equity))
            continue

        # Did intrabar action hit the stop before close?
        # Conservative assumption: if low <= stop (long), the stop fills.
        hit_stop = (
            (side == 'long' and row['Low'] <= stop) or
            (side == 'short' and row['High'] >= stop)
        )
        if hit_stop:
            exit_raw = stop
            reason = 'stop'
        else:
            exit_raw = float(row['Close'])
            reason = 'eod'
        exit_price = _apply_slippage(exit_raw, side, 'exit', params.slippage_bps)

        if side == 'long':
            pnl_dollars = (exit_price - entry) * shares
        else:
            pnl_dollars = (entry - exit_price) * shares
        pnl_dollars -= params.commission_per_trade  # round-trip
        equity += pnl_dollars

        pnl_pct = pnl_dollars / (entry * shares) if shares else 0.0
        trades.append(Trade(
            entry_date=date, exit_date=date, side=side,
            entry_price=entry, exit_price=exit_price, stop_price=stop,
            pnl_pct=pnl_pct, exit_reason=reason,
        ))
        equity_curve.append((date, equity))

    eq = pd.Series(
        [v for _, v in equity_curve],
        index=pd.DatetimeIndex([d for d, _ in equity_curve], name='date'),
        name='equity',
    )

    metrics = _compute_metrics(eq, trades, starting_equity)
    return {'trades': trades, 'equity': eq, 'metrics': metrics, 'signals': s}


def _compute_metrics(equity: pd.Series, trades: list[Trade],
                     starting_equity: float) -> dict:
    if equity.empty:
        return {}
    ret = equity.pct_change().fillna(0)
    total_return = equity.iloc[-1] / starting_equity - 1
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    cagr = (equity.iloc[-1] / starting_equity) ** (1 / years) - 1 if years > 0 else 0.0

    # Sharpe assuming 252 trading days, rf=0
    sharpe = (ret.mean() / ret.std() * np.sqrt(252)) if ret.std() > 0 else 0.0

    rolling_max = equity.cummax()
    drawdown = equity / rolling_max - 1
    max_dd = drawdown.min()

    pnl_pcts = [t.pnl_pct for t in trades]
    wins = [p for p in pnl_pcts if p > 0]
    losses = [p for p in pnl_pcts if p <= 0]
    win_rate = (len(wins) / len(pnl_pcts)) if pnl_pcts else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    profit_factor = (
        (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float('inf')
    )

    return {
        'total_return': float(total_return),
        'cagr': float(cagr),
        'sharpe': float(sharpe),
        'max_drawdown': float(max_dd),
        'num_trades': len(trades),
        'win_rate': float(win_rate),
        'avg_win_pct': avg_win,
        'avg_loss_pct': avg_loss,
        'profit_factor': float(profit_factor),
        'final_equity': float(equity.iloc[-1]),
    }
