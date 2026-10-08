import numpy as np
import pandas as pd
from typing import List, Dict, Any

class AnalyticsEngine:
    @staticmethod
    def calculate_indicators(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not candles or len(candles) < 5:
            return {
                "ema20": None,
                "ema50": None,
                "rsi": 50.0,
                "trend": "NEUTRAL",
                "confidence_score": 50.0,
                "summary": "Insufficient data points for analysis"
            }

        df = pd.DataFrame(candles)
        df['close'] = df['close'].astype(float)
        closes = df['close']

        # Calculate Exponential Moving Averages
        ema20 = closes.ewm(span=min(20, len(closes)), adjust=False).mean().iloc[-1]
        ema50 = closes.ewm(span=min(50, len(closes)), adjust=False).mean().iloc[-1] if len(closes) >= 10 else ema20

        # Calculate RSI (14)
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=min(14, len(closes)-1)).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=min(14, len(closes)-1)).mean()
        
        last_gain = gain.iloc[-1] if not gain.empty else 0
        last_loss = loss.iloc[-1] if not loss.empty else 0
        
        if last_loss == 0:
            rsi = 100.0 if last_gain > 0 else 50.0
        else:
            rs = last_gain / last_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        latest_price = closes.iloc[-1]

        # Signal Logic and Confidence Calculation
        bullish_signals = 0
        total_signals = 4

        if latest_price > ema20:
            bullish_signals += 1
        if ema20 > ema50:
            bullish_signals += 1
        if 45 <= rsi <= 70:
            bullish_signals += 1
        if closes.iloc[-1] > closes.iloc[0]:
            bullish_signals += 1

        confidence = round(50.0 + (abs(bullish_signals - 2) * 17.5), 1)
        confidence = min(92.0, max(55.0, confidence))

        if bullish_signals >= 3:
            trend = "BULLISH"
            summary = f"Strong upside momentum. Price above EMA20 ({round(ema20, 2)}). RSI is {round(rsi, 1)}."
        elif bullish_signals <= 1:
            trend = "BEARISH"
            summary = f"Downside momentum pressure. Price below EMA20 ({round(ema20, 2)}). RSI is {round(rsi, 1)}."
        else:
            trend = "NEUTRAL"
            summary = f"Consolidating in range. RSI is {round(rsi, 1)}."

        return {
            "latest_price": round(latest_price, 4),
            "ema20": round(float(ema20), 4),
            "ema50": round(float(ema50), 4),
            "rsi": round(float(rsi), 2),
            "trend": trend,
            "confidence_score": confidence,
            "summary": summary
        }
