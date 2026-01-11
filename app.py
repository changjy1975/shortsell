import streamlit as st
import pandas as pd
import yfinance as yf

# 擴大股票池
def get_extended_tickers():
    return [
        "2330.TW", "2317.TW", "2454.TW", "2308.TW", "2303.TW", "2603.TW", "2609.TW", 
        "2409.TW", "3481.TW", "2382.TW", "3231.TW", "2357.TW", "2881.TW", "2882.TW",
        "2886.TW", "2301.TW", "2324.TW", "2610.TW", "2618.TW", "2353.TW", "2408.TW"
    ]

def analyze_short_opportunity(ticker, df):
    try:
        if df is None or len(df) < 20: return None
        
        # 處理 yfinance 可能產生的 MultiIndex
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

        if last_close < ma5:
            score += 1
            reasons.append("破5MA")
        if last_close < open_price:
            score += 1
            reasons.append("收黑K")
        bias = (last_close - ma20) / ma20
        if bias > 0.05:
            score += 1
            reasons.append("高乖離")
        if last_close < prev_close and volume_now > volume_ma5:
            score += 1
            reasons.append("出量跌")

        return {
            '股票代號': ticker,
            '收盤價': f"{last_close:.2f}",  # 關鍵修正：確保小數兩位
            '評分': score,
            '符合條件': "、".join(reasons) if reasons else "無",
            '20MA乖離': f"{bias*100:.2f}%",
            '成交量': int(volume_now)
        }
    except:
        return None

# --- UI 介面 ---
st.set_page_config(page_title="台股放空選股器", layout="wide")
st.title("📉 台股隔日放空當沖選股器")
st.markdown("---")

if st.button("🚀 執行大數據掃描"):
    tickers = get_extended_tickers()
    results = []
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    for i, ticker in enumerate(tickers):
        progress_text.text(f"正在分析: {ticker}...")
        data = yf.download(ticker, period="1mo", interval="1d", progress=False)
        res = analyze_short_opportunity(ticker, data)
        if res and res['評分'] >= 1: # 調整為至少有1分才顯示
            results.append(res)
        progress_bar.progress((i + 1) / len(tickers))
    
    progress_text.text("分析完成！")
    
    if results:
        # 轉換為 DataFrame 並排序
        final_df = pd.DataFrame(results).sort_values(by='評分', ascending=False)
        
        # 美化表格顯示
        st.subheader(f"🔍 篩選結果 (共 {len(final_df)} 隻標的)")
        st.dataframe(
            final_df.head(10), 
            use_container_width=True,
            column_config={
                "評分": st.column_config.NumberColumn(format="%d ⭐"),
                "成交量": st.column_config.NumberColumn(format="%d")
            }
        )
        
        # 增加風險控制小提示
        st.warning("📊 **操作指南**：建議優先觀察『評分 > 2』且『20MA 乖離為正』的標的。")
    else:
        st.error("目前市場動能較強，未發現符合放空條件之標的。")

st.markdown("---")
st.caption("免責聲明：本工具僅供策略研究參考，投資具有風險，操作請務必設定停損。")
