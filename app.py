import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import urllib3
import time

# --- 1. 基礎設定與環境優化 ---
# 忽略證交所網站的 SSL 憑證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="台股極速選股器", layout="wide")

@st.cache_data(ttl=86400)
def get_listed_tickers():
    """抓取全台灣上市股票清單"""
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        # verify=False 解決證交所 SSL 憑證問題
        res = requests.get(url, verify=False, headers=headers, timeout=15)
        dfs = pd.read_html(res.text)
        df = dfs[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        # 篩選四位數代碼的股票 (排除權證、存託憑證等)
        df['code'] = df['有價證券代號及名稱'].astype(str).str.split('　').str[0]
        valid_codes = df[df['code'].str.len() == 4]['code'].tolist()
        return [c + ".TW" for c in valid_codes]
    except Exception as e:
        st.error(f"無法獲取上市股票清單: {e}")
        return []

def analyze_logic(ticker, df):
    """分析策略邏輯"""
    try:
        # 確保數據結構正確且無空值
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
            reasons.append("跌破5MA")
        if curr['Close'] < curr['Open']:
            score += 1
            reasons.append("收黑K")
        
        # 計算 20MA 乖離率
        bias = (curr['Close'] - ma20) / ma20
        if bias > 0.05:
            score += 2
            reasons.append("高乖離")
            
        # 量增跌：今日收盤價低於昨日，且成交量大於 5 日均量
        if curr['Close'] < prev['Close'] and curr['Volume'] > vol_ma5:
            score += 1
            reasons.append("量增跌")
        
        # 僅回傳評分達標的標的
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
st.title("⚡ 台股極速當沖選股器 (上市限定)")
st.info("💡 說明：本工具僅掃描上市股票，並自動過濾「低成交量」與「漲停」標的。")

# 修改後的按鈕名稱
if st.button("🚀 開始上市股票掃描"):
    # 整個掃描過程都包在 spinner 內，確保顯示「掃描中」
    with st.spinner("🔍 正在進行上市股票掃描中，請稍候..."):
        all_tickers = get_listed_tickers()
        if not all_tickers:
            st.error("找不到股票清單，請檢查網路。")
            st.stop()
            
        status_msg = st.empty()
        status_msg.info(f"第一階段：初步篩選 {len(all_tickers)} 隻標的之流動性...")
        
        # --- 第一階段：快速篩選 (只抓 3 天資料確保速度) ---
        try:
            # 兩段式下載：第一段先抓取最近 3 日數據
            fast_data = yf.download(all_tickers, period="3d", group_by='ticker', progress=False, threads=True)
        except Exception as e:
            st.error(f"下載數據失敗: {e}")
            st.stop()

        qualified_tickers = []
        
        for t in all_tickers:
            try:
                # 取得單一股票數據
                if len(all_tickers) > 1:
                    temp_df = fast_data[t].dropna()
                else:
                    temp_df = fast_data.dropna()
                    
                if temp_df.empty: continue
                
                last_close = float(temp_df['Close'].iloc[-1])
                prev_close = float(temp_df['Close'].iloc[-2])
                last_vol = temp_df['Volume'].iloc[-1]
                
                # 計算漲跌幅
                pct_change = (last_close - prev_close) / prev_close
                
                # 濾網條件：
                # 1. 排除今日漲停 (漲幅 > 9.8%)
                # 2. 成交量 > 1500 張 (1,500,000 股)
                # 3. 股價 > 20 元
                if pct_change < 0.098 and last_vol >= 1500000 and last_close > 20:
                    qualified_tickers.append(t)
            except:
                continue
                
        status_msg.success(f"✅ 第一階段篩選完成！共 {len(qualified_tickers)} 隻標的進入深度分析...")
        
        # --- 第二階段：深度分析 (只分析篩選後的標的) ---
        results = []
        if qualified_tickers:
            # 下載一個月歷史資料進行指標計算
            detail_data = yf.download(qualified_tickers, period="1mo", group_by='ticker', progress=False, threads=True)
            
            # 進度條提示
            progress_bar = st.progress(0)
            for i, t in enumerate(qualified_tickers):
                # 處理單一標的情況
                df_to_analyze = detail_data[t] if len(qualified_tickers) > 1 else detail_data
                res = analyze_logic(t, df_to_analyze)
                if res:
                    results.append(res)
                # 更新掃描中進度
                progress_bar.progress((i + 1) / len(qualified_tickers))
            
            # 清除掃描中提示
            status_msg.empty()
            
            if results:
                final_df = pd.DataFrame(results).sort_values(by="評分", ascending=False)
                st.success(f"🔥 分析完成！明日建議放空觀察清單：")
                st.dataframe(final_df.head(10), use_container_width=True)
            else:
                st.warning("目前的篩選條件下，無符合評分標準的標的。")
        else:
            st.error("初步篩選後無剩餘標的，可能今日市場過於強勢或無符合流動性之股票。")

st.caption("數據來源：Yahoo Finance。僅供策略研究參考。")
