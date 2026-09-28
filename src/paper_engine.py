import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CUSTOM_FILE = os.path.join(DATA_DIR, "portfolio_custom.json")
SCREENER_FILE = os.path.join(DATA_DIR, "portfolio_screener.json")

DEFAULT_PORTFOLIO = {
    "cash": 10000.0,
    "initial_capital": 10000.0,
    "total_equity": 10000.0,
    "total_performance_pct": 0.0,
    "open_positions": [],
    "closed_trades": [],
    "benchmark": {
        "start_price": None,
        "current_price": None,
        "performance_pct": 0.0
    }
}

def load_portfolio(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
    return DEFAULT_PORTFOLIO.copy()

def save_portfolio(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def process_single_portfolio(portfolio, raw_data, spy_perf, current_spy, now_dt, now_str):
    # עדכון Benchmark
    bm = portfolio.get("benchmark", {})
    if current_spy:
        if not bm.get("start_price"):
            bm["start_price"] = current_spy
        bm["current_price"] = current_spy
        start_p = bm["start_price"]
        bm["performance_pct"] = round(((current_spy - start_p) / start_p) * 100, 2)
        portfolio["benchmark"] = bm

    positions = portfolio.get("open_positions", [])
    still_open = []
    closed_trades = portfolio.get("closed_trades", [])
    cash = float(portfolio.get("cash", 10000.0))

    for pos in positions:
        tk = pos["ticker"]
        if tk not in raw_data:
            still_open.append(pos)
            continue

        df_tk = raw_data[tk].dropna()
        if len(df_tk) == 0:
            still_open.append(pos)
            continue

        latest_close = float(df_tk["Close"].iloc[-1])
        latest_high = float(df_tk["High"].iloc[-1])
        latest_low = float(df_tk["Low"].iloc[-1])

        entry = float(pos["entry_price"])
        shares = int(pos["shares"])
        stop_loss = float(pos["stop_loss"])
        target_1 = float(pos["target_1"])
        target_2 = float(pos.get("target_2", target_1 * 1.08))
        is_trailing = bool(pos.get("trailing_active", False))

        opened_at_str = pos.get("opened_at", now_str)
        try:
            d_parsed = datetime.strptime(opened_at_str, "%d/%m/%Y")
            days_active = (now_dt - d_parsed).days
        except Exception:
            days_active = 0

        pos["days_active"] = days_active
        pos["current_price"] = latest_close
        pos["current_pnl_pct"] = round(((latest_close - entry) / entry) * 100, 2)
        pos["current_value"] = round(shares * latest_close, 2)

        # TP2 - יציאה מלאה
        if latest_high >= target_2:
            pnl = (target_2 - entry) * shares
            cash += shares * target_2
            closed_trades.append({
                "ticker": tk,
                "entry_price": entry,
                "exit_price": target_2,
                "shares": shares,
                "pnl": round(pnl, 2),
                "pnl_pct": round(((target_2 - entry) / entry) * 100, 2),
                "reason": "TARGET_2",
                "opened_at": opened_at_str,
                "closed_at": now_str
            })
            continue

        # TP1 - יציאה של 50% והזזת סטופ לכניסה
        elif latest_high >= target_1 and not is_trailing and shares >= 2:
            half_shares = shares // 2
            remaining_shares = shares - half_shares
            cash += half_shares * target_1
            pnl_half = (target_1 - entry) * half_shares

            closed_trades.append({
                "ticker": tk,
                "entry_price": entry,
                "exit_price": target_1,
                "shares": half_shares,
                "pnl": round(pnl_half, 2),
                "pnl_pct": round(((target_1 - entry) / entry) * 100, 2),
                "reason": "TARGET_1_HALF",
                "opened_at": opened_at_str,
                "closed_at": now_str
            })

            pos["shares"] = remaining_shares
            pos["stop_loss"] = entry
            pos["trailing_active"] = True
            pos["current_value"] = round(remaining_shares * latest_close, 2)
            still_open.append(pos)
            continue

        # Stop Loss
        elif latest_low <= stop_loss:
            pnl = (stop_loss - entry) * shares
            cash += shares * stop_loss
            closed_trades.append({
                "ticker": tk,
                "entry_price": entry,
                "exit_price": stop_loss,
                "shares": shares,
                "pnl": round(pnl, 2),
                "pnl_pct": round(((stop_loss - entry) / entry) * 100, 2),
                "reason": "STOP_LOSS",
                "opened_at": opened_at_str,
                "closed_at": now_str
            })
            continue

        # Time Stop (מעל 15 יום)
        elif days_active >= 15:
            pnl = (latest_close - entry) * shares
            cash += shares * latest_close
            closed_trades.append({
                "ticker": tk,
                "entry_price": entry,
                "exit_price": latest_close,
                "shares": shares,
                "pnl": round(pnl, 2),
                "pnl_pct": round(((latest_close - entry) / entry) * 100, 2),
                "reason": "TIME_STOP_EXPIRED",
                "opened_at": opened_at_str,
                "closed_at": now_str
            })
            continue

        still_open.append(pos)

    portfolio["cash"] = round(cash, 2)
    portfolio["open_positions"] = still_open
    portfolio["closed_trades"] = closed_trades

    positions_value = sum([p["current_value"] for p in still_open])
    total_equity = round(cash + positions_value, 2)
    init_cap = float(portfolio.get("initial_capital", 10000.0))
    total_perf_pct = round(((total_equity - init_cap) / init_cap) * 100, 2)

    portfolio["total_equity"] = total_equity
    portfolio["total_performance_pct"] = total_perf_pct
    portfolio["last_updated"] = now_str
    return portfolio

def update_all_portfolios():
    custom_port = load_portfolio(CUSTOM_FILE)
    screener_port = load_portfolio(SCREENER_FILE)

    all_positions = custom_port.get("open_positions", []) + screener_port.get("open_positions", [])
    tickers_to_fetch = list(set([p["ticker"] for p in all_positions] + ["SPY"]))

    raw_data = yf.download(
        tickers_to_fetch,
        period="1mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True
    )

    now_dt = datetime.now()
    now_str = now_dt.strftime("%d/%m/%Y")

    current_spy = None
    spy_perf = 0.0
    if "SPY" in raw_data:
        spy_df = raw_data["SPY"].dropna()
        if len(spy_df) > 0:
            current_spy = float(spy_df["Close"].iloc[-1])

    print("Updating Custom Portfolio...")
    updated_custom = process_single_portfolio(custom_port, raw_data, spy_perf, current_spy, now_dt, now_str)
    save_portfolio(CUSTOM_FILE, updated_custom)

    print("Updating Screener Portfolio...")
    updated_screener = process_single_portfolio(screener_port, raw_data, spy_perf, current_spy, now_dt, now_str)
    save_portfolio(SCREENER_FILE, updated_screener)

    print("Both portfolios updated successfully.")

if __name__ == "__main__":
    update_all_portfolios()
