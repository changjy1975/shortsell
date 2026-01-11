import pandas as pd

def analyze_short_opportunity(ticker, df):
    """
    針對單一股票進行空方評分
    """
    if len(df) < 20: return None
    
    last_close = df['Close'].iloc[-1]
    prev_close = df['Close'].iloc[-2]
    ma5 = df['Close'].rolling(5).mean().iloc[-1]
    ma20 = df['Close'].rolling(20).mean().iloc[-1]
    volume_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    
    score = 0
    
    # 條件 1：跌破 5 日線 (短期轉弱)
    if last_close < ma5: score += 1
    
    # 條件 2：5 日線下彎 (趨勢向下)
    if ma5 < df['Close'].rolling(5).mean().iloc[-2]: score += 1
    
    # 條件 3：今日出量下跌 (恐慌性拋售或主力出貨)
    if last_close < prev_close and df['Volume'].iloc[-1] > volume_ma5:
        score += 1
        
    # 條件 4：乖離率過大後的首根長黑 (過熱反轉)
    bias = (last_close - ma20) / ma20
    if bias > 0.07 and last_close < df['Open'].iloc[-1]: # 正乖離 > 7% 且收黑
        score += 2 

    return {
        'Ticker': ticker,
        'Close': round(last_close, 2),
        'Score': score,
        'Bias_20MA': f"{round(bias*100, 2)}%"
    }
