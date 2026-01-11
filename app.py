import streamlit as st
import pandas as pd  # 確保這行存在
import yfinance as yf
from datetime import datetime, timedelta

# --- 1. 核心選股策略函數 (放在 app.py 內確保 pd 可被存取) ---
def analyze_short_opportunity(ticker, df):
    """
    針對單一股票進行空方評分
    """
    if df is None or len(df) < 20: 
        return None
    
    try:
        # 取得最後兩日的資料
        last_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2]
        open_price = df['Open'].iloc[-1]
        
        # 計算技術指標
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        volume_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
        
        score = 0
        
        # 條件 1：收盤跌破 5 日線
        if last_close < ma5: score += 1
        
        # 條件 2：5 日線趨勢向下
        if ma5 < df['Close'].rolling(5).mean().iloc[-2]: score += 1
        
        # 條件 3：今日出量下跌 (當日量 > 5日均量)
        if last_close < prev_close and df['Volume'].iloc[-1] > volume_ma5:
            score += 1
            
        # 條件 4：乖離率大於 7% 且收黑 K (過熱反轉)
        bias = (last_close - ma20) / ma20
        if bias > 0.07 and last_close < open_price:
            score += 2 

        return {
            '股票代號': ticker,
            '目前價格': round(last_close, 2),
            '空方評分': score,
            '20MA乖離': f"{round(bias*100, 2)}%",
            '今日成交量': int(df['Volume'].iloc[-1])
        }
    except Exception as e:
        return None

# --- 2. Streamlit 介面 ---
st.set_page_config(page_title="台股放空選股器", layout="wide")
st.title("📉 台股隔日放空當沖選股器")

# 選股清單 (可自行增加)
tickers = ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "2303.TW", "2603.TW", "2609.TW", "2409.TW", "3481.TW"]

if st.button("🚀 開始掃描分析"):
    results = []
    
    with st.spinner('正在從 yfinance 抓取即時數據...'):
        # 為了避免 MultiIndex 混亂，我們逐一抓取或使用正確的切片
        for ticker in tickers:
            data = yf.download(ticker, period="1mo", interval="1d", progress=False)
            
            if not data.empty:
                res = analyze_short_opportunity(ticker, data)
                if res:
                    results.append(res)
    
    if results:
        # 修正 NameError：確保 pd 在這行之前已經 import
        final_df = pd.DataFrame(results).sort_values(by='空方評分', ascending=False)
        
        st.subheader("📋 建議觀察清單 (評分越高越適合放空)")
        st.dataframe(final_df, use_container_width=True)
        
        st.info("💡 提示：建議挑選評分在 3 分以上的標的，並在明日開盤後觀察是否持續走弱。")
    else:
        st.error("掃描結束，未找到符合條件的股票。")
