import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import urllib3
import time
from datetime import datetime

# --- 基礎設定與 SSL 修正 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="台股極速放空選股器", layout="wide")

@st.cache_data(ttl=86400)
def get_listed_tickers():
    """抓取全台灣上市股票清單"""
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, verify=False, headers=headers, timeout=10)
        df = pd.read_html(res.text)[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        df['code'] = df['有價證券代號及名稱'].astype(str).str.split('　').str[0]
        # 只取四碼的股票，後綴為 .TW
        return [c + ".TW" for c in df[df['code'].str.len() == 4]['code']]
    except Exception as e:
        st.error(f"清單抓取失敗: {e}")
        return []

def analyze_logic(ticker, df):
    """技術面核心策略評分"""
    try:
        if df.empty or len(df) < 20: return None
        
        # 清理 MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 指標計算
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
        
        score = 0
        reasons = []
        
        # 1. 趨勢：破 5MA (1分)
        if curr['Close'] < ma5:
            score += 1
            reasons.append("跌破5MA")
            
        # 2. K線：收黑K (1分)
        if curr['Close'] < curr['Open']:
            score += 1
            reasons.append("收黑K")
            
        # 3. 乖離：20MA正乖離 > 5% (2分)
        bias = (curr['Close'] - ma20) / ma20
        if bias > 0.05:
            score += 2
            reasons.append("高乖離")
            
        # 4. 動能：價跌量增 (1分)
        if curr['Close'] < prev['Close'] and curr['Volume'] > vol_ma5:
            score += 1
            reasons.append("量增跌")
        
        # 設定回傳條件：評分需達 3 分以上
        if score >= 3:
            return {
                "代號": ticker,
                "收盤價": round(float(curr['Close']), 2),
                "漲跌幅": f"{((curr['Close']-prev['Close'])/prev['Close']*100):.2f}%",
                "評分": score,
                "符合訊號": "、".join(reasons),
                "20MA乖離": f"{(bias*100):.2f}%",
                "成交量(張)": int(curr['Volume']/1000)
            }
    except:
        return None

# --- UI 介面 ---
st.title("⚡ 台股極速當沖選股器 (上市限定)")
st.markdown("""
### 策略邏輯說明
1. **第一階段過濾**：自動過濾成交量不足 1,500 張、股價低於 20 元、以及 **當日漲停** 的股票。
2. **第二階段分析**：針對剩餘標的進行 5MA、20MA 乖離率與量價分析。
""")

if st.button("🚀 開始極速掃描"):
    all_tickers = get_listed_tickers()
    if not all_tickers:
        st.stop()
        
    st.info(f"第一階段：正在初步篩選 {len(all_tickers)} 隻標的...")
    
    # --- 第一階段：大批次下載 2 日數據進行快速過濾 ---
    fast_data = yf.download(all_tickers, period="2d", group_by='ticker', progress=False, threads=True)
    
    qualified_tickers = []
    excluded_limit_up = 0
    
    for t in all_tickers:
        try:
            temp_df = fast_data[t].dropna()
            if temp_df.empty: continue
            
            last_close = float(temp_df['Close'].iloc[-1])
            prev_close = float(temp_df['Close'].iloc[-2])
            last_vol = temp_df['Volume'].iloc[-1]
            
            # 計算是否漲停 (台股約 9.9% 以上即為漲停範圍)
            pct_change = (last_close - prev_close) / prev_close
            
            # 濾網：
            # 1. 成交量 > 1500張 (1,500,000股)
            # 2. 股價 > 20元
            # 3. 漲幅 < 9.8% (排除漲停股)
            if pct_change >= 0.098:
                excluded_limit_up += 1
                continue
                
            if last_vol >= 1500000 and last_price > 20:
                qualified_tickers.append(t)
        except:
            continue
            
    st.write(f"✅ 第一階段完成！排除漲停股 {excluded_limit_up} 隻，共 {len(qualified_tickers)} 隻進入深度分析。")
    
    # --- 第二階段：深度分析 ---
    results = []
    if qualified_tickers:
        with st.spinner("正在進行技術面評分..."):
            # 只針對合格標的下載 1 個月歷史資料
            detail_data = yf.download(qualified_tickers, period="1mo", group_by='ticker', progress=False, threads=True)
            
            for t in qualified_tickers:
                # 處理單一標的情況
                df_to_analyze = detail_data[t] if len(qualified_tickers) > 1 else detail_data
                res = analyze_logic(t, df_to_analyze)
                if res:
                    results.append(res)
            
        if results:
            final_df = pd.DataFrame(results).sort_values(by="評分", ascending=False)
            st.success(f"🔥 分析完成！以下為建議觀察清單 (Top 10)：")
            st.table(final_df.head(10))
        else:
            st.warning("目前的篩選條件下，沒有符合 3 分以上的標的。")
    else:
        st.error("第一階段過濾後無剩餘標的，今日可能不適合放空當沖。")

st.caption("數據來源：Yahoo Finance。加速技術：多執行緒批次抓取。")
