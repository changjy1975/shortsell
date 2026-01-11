import streamlit as st
import pandas as pd
import yfinance as yf

# --- 1. 擴大股票池 (增加流動性好的標的) ---
def get_extended_tickers():
    return [
        "2330.TW", "2317.TW", "2454.TW", "2308.TW", "2303.TW", "2603.TW", "2609.TW", 
        "2409.TW", "3481.TW", "2382.TW", "3231.TW", "2357.TW", "2881.TW", "2882.TW",
        "2886.TW", "2301.TW", "2324.TW", "2610.TW", "2618.TW", "2353.TW"
    ]

# --- 2. 策略邏輯修正 ---
def analyze_short_opportunity(ticker, df):
    try:
        # 確保資料足夠
        if df is None or len(df) < 20: return None
        
        # 強制移除多層索引 (yfinance 常見問題)
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        
        last_close = float(df['Close'].iloc[-1])
        prev_close = float(df['Close'].iloc[-2])
        open_price = float(df['Open'].iloc[-1])
        
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        volume_now = df['Volume'].iloc[-1]
        volume_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
        
        score = 0
        reasons = []

        # 條件 A: 跌破 5 日線 (0.5分)
        if last_close < ma5:
            score += 1
            reasons.append("破5MA")
            
        # 條件 B: 今日收黑 K (1分)
        if last_close < open_price:
            score += 1
            reasons.append("收黑K")

        # 條件 C: 乖離過大 (1分)
        bias = (last_close - ma20) / ma20
        if bias > 0.05:
            score += 1
            reasons.append("高乖離回檔")
            
        # 條件 D: 出量下跌 (1分)
        if last_close < prev_close and volume_now > volume_ma5:
            score += 1
            reasons.append("出量下跌")

        return {
            '股票代號': ticker,
            '收盤價': round(last_close, 2),
            '評分': score,
            '符合條件': "、".join(reasons) if reasons else "無",
            '20MA乖離': f"{round(bias*100, 2)}%"
        }
    except Exception as e:
        return None

# --- 3. Streamlit UI ---
st.set_page_config(page_title="台股放空篩選器", layout="wide")
st.title("📉 台股隔日放空當沖選股器")

if st.button("🚀 開始掃描分析"):
    tickers = get_extended_tickers()
    results = []
    
    progress_bar = st.progress(0)
    for i, ticker in enumerate(tickers):
        # 逐一抓取避免 MultiIndex 錯誤
        data = yf.download(ticker, period="1mo", interval="1d", progress=False)
        res = analyze_short_opportunity(ticker, data)
        if res and res['評分'] > 0: # 只要有符合一個條件就列出
            results.append(res)
        progress_bar.progress((i + 1) / len(tickers))
    
    if results:
        final_df = pd.DataFrame(results).sort_values(by='評分', ascending=False)
        st.subheader(f"📋 掃描完成：共找到 {len(final_df)} 隻潛在標的")
        st.table(final_df.head(10)) # 取前 10 名
    else:
        st.error("目前的篩選條件在目前的市場中找不到標的，請嘗試更換日期或增加股票池。")

st.info("💡 提醒：GitHub 專案建議在 README 說明，若遇大多頭市場，符合放空條件的標的會自然減少，這也是一種保護機制。")
