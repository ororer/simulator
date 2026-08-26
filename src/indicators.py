import yfinance as yf
import pandas as pd
import numpy as np

def calculate_rsi(series, period=14):
    """חישוב מדד ה-RSI"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_stock_analysis(ticker):
    """ניתוח טכני למניה: EMA 50, RSI, ושפל/שיא לסטופ ויעד"""
    try:
        # הורדת היסטוריה של 6 חודשים
        df = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if df.empty or len(df) < 55:
            return None
        
        # טיפול בעמודות אם הן בפורמט כפול
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # חישוב אינדיקטורים
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['RSI_14'] = calculate_rsi(df['Close'], 14)
        
        last_row = df.iloc[-1]
        close_price = float(last_row['Close'])
        ema_50 = float(last_row['EMA_50'])
        rsi = float(last_row['RSI_14'])
        
        # חלון של 15 ימי מסחר אחרונים (לא כולל היום הנוכחי)
        recent_window = df.iloc[-16:-1]
        swing_low = float(recent_window['Low'].min())
        swing_high = float(recent_window['High'].max())
        
        # סטופ לוס: 0.5% מתחת לשפל האחרון
        stop_loss = round(swing_low * 0.995, 2)
        
        # יעד רווח: שיא אחרון או יחס סיכון/סיכוי של לפחות 1:2
        risk = close_price - stop_loss
        min_target = round(close_price + (risk * 2.0), 2)
        take_profit = max(round(swing_high, 2), min_target)
        
        # תנאי כניסה: מעל EMA 50 + RSI בין 40 ל-55 + סיכון הגיוני
        is_signal = (close_price > ema_50) and (40.0 <= rsi <= 55.0) and (risk > 0)
        
        return {
            "ticker": ticker,
            "price": round(close_price, 2),
            "ema_50": round(ema_50, 2),
            "rsi": round(rsi, 2),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "signal": is_signal
        }
    except Exception as e:
        print(f"שגיאה בניתוח {ticker}: {e}")
        return None