import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import urllib3
import time

# --- 1. 基礎設定與連線優化 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="台股極速多空選股器", layout="wide")

@st.cache_data(ttl=86400)
def get_stock_tickers(market_type):
    """根據市場類型抓取代碼：上市(.TW) 或 上櫃(.TWO)"""
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2" if market_type == "上市" else "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    suffix = ".TW" if market_type == "上市" else ".TWO"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, verify=False, headers=headers, timeout=15)
        dfs = pd.read_html(res.text)
        df = dfs[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        df['code'] = df['有價證券代號及名稱'].astype(str).str.split('　').str[0]
        # 只取 4 碼普通股
        valid_codes = df[df['code'].str.len() == 4]['code'].tolist()
        return [c + suffix for c in valid_codes]
    except Exception as e:
        st.error(f"無法獲取{market_type}清單: {e}")
        return []

def analyze_stock(ticker, df, mode="空方"):
    """核心策略：量價與均線分析 (已修正名稱與邏輯)"""
    try:
        # 處理資料結構，確保是 DataFrame 且包含 Close
        if isinstance(df, pd.DataFrame) and 'Close' in df.columns:
            data = df.dropna()
        else:
            return None

        if len(data) < 20: return None
        
        curr, prev = data.iloc[-1], data.iloc[-2]
        ma5 = data['Close'].rolling(5).mean().iloc[-1]
        ma20 = data['Close'].rolling(20).mean().iloc[-1]
        vol_ma5 = data['Volume'].rolling(5).mean().iloc[-1]
        bias = (curr['Close'] - ma20) / ma20
        
        score, reasons = 0, []

        if mode == "空方":
            # 空方評分條件
            if curr['Close'] < ma5: score += 1; reasons.append("破5MA")
            if curr['Close'] < curr['Open']: score += 1; reasons.append("收黑K")
            if bias > 0.05: score += 2; reasons.append("高乖離")
            if curr['Close'] < prev['Close'] and curr['Volume'] > vol_ma5: score += 1; reasons.append("量增跌")
        else:
            # 多方評分條件
            if curr['Close'] > ma5: score += 1; reasons.append("突破5MA")
            if curr['Close'] > curr['Open']: score += 1; reasons.append("收紅K")
            if bias < -0.05: score += 2; reasons.append("跌深反彈")
            if curr['Close'] > prev['Close'] and curr['Volume'] > vol_ma5: score += 1; reasons.append("量增漲")
            
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
    except: return None

# --- 2. Sidebar 設定 ---
st.sidebar.title("⚙️ 參數設定")
market_choice = st.sidebar.selectbox("1. 市場類型", ["上市", "上櫃"])
trade_mode = st.sidebar.radio("2. 交易方向", ["空方當沖 (Short)", "多方當沖 (Long)"])
min_score = st.sidebar.slider("3. 評分門檻", 1, 5, 3)

# 統一設定成交量門檻為 3000 張 (3,000,000 股)
VOL_THRESHOLD = 3000000 

# --- 3. UI 呈現 ---
st.title(f"🚀 台股極速雙向選股器 ({market_choice})")
st.warning(f"當前模式：{trade_mode[:2]} / 成交量過濾： > 3000 張")

if st.button(f"🔍 開始{market_choice}股票掃描"):
    with st.spinner(f"正在執行兩階段加速掃描中..."):
        all_tickers = get_stock_tickers(market_choice)
        if not all_tickers: st.stop()
        
        status_msg = st.empty()
        status_msg.info(f"第一階段：流動性初步篩選 (目標: >3000張)...")
        
        # 第一階段：快速下載
        fast_data = yf.download(all_tickers, period="3d", group_by='ticker', progress=False, threads=True)
        
        qualified_tickers = []
        for t in all_tickers:
            try:
                temp_df = fast_data[t].dropna() if len(all_tickers) > 1 else fast_data.dropna()
                if temp_df.empty: continue
                
                last_close = float(temp_df['Close'].iloc[-1])
                prev_close = float(temp_df['Close'].iloc[-2])
                last_vol = float(temp_df['Volume'].iloc[-1])
                
                # 計算漲跌幅 (排除空方模式下的漲停股)
                is_limit_up = (last_close - prev_close) / prev_close >= 0.098
                
                if last_vol >= VOL_THRESHOLD and last_close > 20:
                    if trade_mode.startswith("空方") and is_limit_up: continue
                    qualified_tickers.append(t)
            except: continue
        
        status_msg.success(f"✅ 第一階段完成！篩選出 {len(qualified_tickers)} 隻高流動性標的。")
        
        # 第二階段：深度分析
        results = []
        if qualified_tickers:
            detail_data = yf.download(qualified_tickers, period="1mo", group_by='ticker', progress=False, threads=True)
            progress_bar = st.progress(0)
            
            for i, t in enumerate(qualified_tickers):
                # 確保深度分析調用的函數名稱一致
                df_to_analyze = detail_data[t] if len(qualified_tickers) > 1 else detail_data
                res = analyze_stock(t, df_to_analyze, mode=trade_mode[:2])
                if res: results.append(res)
                progress_bar.progress((i + 1) / len(qualified_tickers))
            
            status_msg.empty()
            if results:
                final_df = pd.DataFrame(results).sort_values(by="評分", ascending=False)
                st.success(f"🔥 {trade_mode[:2]}建議觀察清單 (Top {len(final_df)})：")
                st.dataframe(final_df, use_container_width=True)
                
                # 策略邏輯顯示
                st.markdown("---")
                st.subheader("📊 策略評分權重說明")
                col_l, col_r = st.columns(2)
                with col_l:
                    st.write("**空方 (Short)**")
                    st.markdown("- 跌破5MA (+1)\n- 收黑K (+1)\n- 高正乖離 (>5%) (+2)\n- 量增下跌 (+1)")
                with col_r:
                    st.write("**多方 (Long)**")
                    st.markdown("- 突破5MA (+1)\n- 收紅K (+1)\n- 高負乖離 (<-5%) (+2)\n- 量增上漲 (+1)")
            else:
                st.warning("目前的篩選條件下無標的達標。")
        else:
            st.error("掃描結束，今日市場流動性不足 3000 張或無符合標的。")

st.caption("數據來源：Yahoo Finance | 加速技術：兩階段向量化過濾")
