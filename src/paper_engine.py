import json
import os
from datetime import datetime
from config import CUSTOM_PORTFOLIO_WATCHLIST, SCREENER_UNIVERSE, SCREENER_DEFAULT_ALLOCATION
from indicators import get_stock_analysis

def load_portfolio(filepath):
    """טעינת תיק או יצירת תיק התחלתי במידה ולא קיים"""
    if not os.path.exists(filepath):
        initial = {
            "cash": 10000.0,
            "initial_balance": 10000.0,
            "current_equity": 10000.0,
            "return_pct": 0.0,
            "positions": {},
            "history": []
        }
        save_portfolio(filepath, initial)
        return initial
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def save_portfolio(filepath, data):
    """שמירת נתוני התיק לקובץ JSON"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def update_positions_and_exits(portfolio):
    """בדיקת פוזיציות קיימות וסגירה ב-Take Profit או Stop Loss"""
    total_positions_value = 0.0

    for ticker, pos in list(portfolio["positions"].items()):
        analysis = get_stock_analysis(ticker)
        if not analysis:
            continue
        
        cur_price = analysis["price"]
        pos_val = pos["shares"] * cur_price
        total_positions_value += pos_val
        
        # בדיקת יעדי יציאה
        reason = None
        if cur_price >= pos["take_profit"]:
            reason = "Take Profit (שיא/יעד)"
        elif cur_price <= pos["stop_loss"]:
            reason = "Stop Loss (שפל)"
            
        if reason:
            revenue = pos["shares"] * cur_price
            profit = revenue - (pos["shares"] * pos["entry_price"])
            profit_pct = ((cur_price / pos["entry_price"]) - 1) * 100
            
            portfolio["cash"] += revenue
            portfolio["history"].append({
                "ticker": ticker,
                "entry_price": pos["entry_price"],
                "exit_price": cur_price,
                "shares": pos["shares"],
                "profit_usd": round(profit, 2),
                "profit_pct": round(profit_pct, 2),
                "reason": reason,
                "entry_date": pos.get("entry_date", ""),
                "exit_date": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            del portfolio["positions"][ticker]
            print(f"[!] נסגרה פוזיציה ב-{ticker} ({reason}) במחיר ${cur_price} | תוצאה: {profit_pct:+.2f}%")

    portfolio["current_equity"] = round(portfolio["cash"] + total_positions_value, 2)
    portfolio["return_pct"] = round(((portfolio["current_equity"] / portfolio["initial_balance"]) - 1) * 100, 2)

def run_portfolio_cycle(filepath, ticker_allocations):
    """הרצת מחזור בדיקה מלא על תיק מסוים"""
    portfolio = load_portfolio(filepath)
    update_positions_and_exits(portfolio)
    
    # חיפוש איתותים חדשים לקנייה
    for ticker, alloc in ticker_allocations.items():
        if ticker in portfolio["positions"]:
            continue  # כבר קיימת פוזיציה פתוחה
            
        analysis = get_stock_analysis(ticker)
        if analysis and analysis["signal"]:
            invest_amount = portfolio["initial_balance"] * alloc
            if portfolio["cash"] >= invest_amount:
                shares = round(invest_amount / analysis["price"], 4)
                actual_cost = shares * analysis["price"]
                
                portfolio["cash"] -= actual_cost
                portfolio["positions"][ticker] = {
                    "shares": shares,
                    "entry_price": analysis["price"],
                    "entry_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "take_profit": analysis["take_profit"],
                    "stop_loss": analysis["stop_loss"]
                }
                print(f"[+] רכישה חדשה: {ticker} | מחיר: ${analysis['price']} | יעד: ${analysis['take_profit']} | סטופ: ${analysis['stop_loss']}")

    save_portfolio(filepath, portfolio)
    return portfolio

if __name__ == "__main__":
    print("--- מריץ עדכון תיק עצמאי ---")
    custom_res = run_portfolio_cycle("data/portfolio_custom.json", CUSTOM_PORTFOLIO_WATCHLIST)
    
    print("\n--- מריץ עדכון תיק סורק ---")
    screener_allocs = {t: SCREENER_DEFAULT_ALLOCATION for t in SCREENER_UNIVERSE}
    screener_res = run_portfolio_cycle("data/portfolio_screener.json", screener_allocs)
    
    print("\n==========================================")
    print(f"📊 שווי תיק עצמאי: ${custom_res['current_equity']} (תשואה: {custom_res['return_pct']:+}%)")
    print(f"📊 שווי תיק סורק:  ${screener_res['current_equity']} (תשואה: {screener_res['return_pct']:+}%)")
    print("==========================================")