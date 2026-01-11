import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import urllib3
import time

# --- 1. 基礎設定與環境優化 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="台股放空極速選股器", layout="wide")

@st.cache_data(ttl=86400)
def get_listed_tickers():
    """抓取全台灣上市股票清單"""
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, verify=False, headers=headers, timeout=15)
        dfs = pd.read_html(res.text)
        df = dfs[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        # 篩選四位數代碼的股票
        df['code'] = df['有價證券代號及名稱'].astype(str).str.split('　').str[0]
        valid_codes = df[df['code'].str.len() == 4]['code'].tolist()
        return [c + ".TW" for c in valid_codes]
    except Exception as e:
        st.error(f"無法獲取股票清單: {e}")
        return []

def analyze_logic(ticker, df):
    """分析策略 (修正 MultiIndex 與 變數錯誤)"""
    try:
        # 確保資料結構正確
        if isinstance(df, pd.DataFrame) and 'Close' in df.columns:
            data = df.dropna()
        else:
            return None

        if len(data) < 20: return None
        
        curr = data.iloc[-1]
        prev = data.iloc[-2]
        
        # 指標計算
        ma5 = data['Close'].rolling(5).mean().iloc[-1]
        ma20 = data['Close'].rolling(20).mean().iloc[-1]
        vol_ma5 = data['Volume'].rolling(5).mean().iloc[-1]
        
        score = 0
        reasons = []
        
        # 核心條件篩選
        if curr['Close'] < ma5:
            score += 1
            reasons.append("破5MA")
        if curr['Close'] < curr['Open']:
            score += 1
            reasons.append("收黑K")
        
        bias = (curr['Close'] - ma20) / ma20
        if bias > 0.05:
            score += 2
            reasons.append("高乖離")
            
        if curr['Close'] < prev['Close'] and curr['Volume'] > vol_ma5:
            score += 1
            reasons.append("量增跌")
        
        # 僅回傳高分標的
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
    return None

# --- 2. UI 介面 ---
st.title("⚡ 台股極速當沖選股器 (最終修正版)")
st.info("本版本修正了變數錯誤與連線穩定性，適合在 GitHub/Streamlit Cloud 執行。")

if st.button("🚀 開始全市場掃描"):
    all_tickers = get_listed_tickers()
    if not all_tickers:
        st.error("找不到股票清單，請檢查網路。")
        st.stop()
        
    status_msg = st.empty()
    status_msg.info(f"第一階段：篩選 {len(all_tickers)} 隻標的流動性與漲跌停...")
    
    # --- 第一階段：快速篩選 (只抓 3 天資料確保穩定) ---
    try:
        fast_data = yf.download(all_tickers, period="3d", group_by='ticker', progress=False, threads=True)
    except Exception as e:
        st.error(f"下載數據失敗: {e}")
        st.stop()

    qualified_tickers = []
    
    for t in all_tickers:
        try:
            # 取得單一股票 DataFrame
            if len(all_tickers) > 1:
                temp_df = fast_data[t].dropna()
            else:
                temp_df = fast_data.dropna()
                
            if temp_df.empty: continue
            
            last_close = float(temp_df['Close'].iloc[-1])
            prev_close = float(temp_df['Close'].iloc[-2])
            last_vol = temp_df['Volume'].iloc[-1]
            
            pct_change = (last_close - prev_close) / prev_close
            
            # 修正濾網變數：
            # 1. 排除漲停 ( > 9.8%)
            # 2. 成交量 > 1500 張
            # 3. 股價 > 20 元
            if pct_change < 0.098 and last_vol >= 1500000 and last_close > 20:
                qualified_tickers.append(t)
        except:
            continue
            
    status_msg.success(f"篩選完成！共 {len(qualified_tickers)} 隻標的進入深度分析。")
    
    # --- 第二階段：深度分析 ---
    results = []
    if qualified_tickers:
        with st.spinner("計算技術指標中..."):
            # 下載一個月資料
            detail_data = yf.download(qualified_tickers, period="1mo", group_by='ticker', progress=False, threads=True)
            
            for t in qualified_tickers:
                # 處理單一標的情況
                df_to_analyze = detail_data[t] if len(qualified_tickers) > 1 else detail_data
                res = analyze_logic(t, df_to_analyze)
                if res:
                    results.append(res)
            
        if results:
            final_df = pd.DataFrame(results).sort_values(by="評分", ascending=False)
            st.success(f"🔥 明日放空觀察名單：")
            st.dataframe(final_df.head(10), use_container_width=True)
        else:
            st.warning("目前市場無符合 3 分以上的放空標的。")
    else:
        st.error("過濾後無剩餘標的，今日市場可能過於強勢或數據異常。")

st.caption("註：若出現 'No data found' 警告，通常是特定股票暫停交易，不影響整體執行。")
