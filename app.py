import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import urllib3
import time

# --- 1. 基礎設定與環境優化 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="台股極速多空選股器", layout="wide")

# 抓取股票清單 (支援上市與上櫃)
@st.cache_data(ttl=86400)
def get_stock_tickers(market_type):
    """根據市場類型抓取代碼：上市(.TW) 或 上櫃(.TWO)"""
    if market_type == "上市":
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        suffix = ".TW"
    else:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
        suffix = ".TWO"
        
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, verify=False, headers=headers, timeout=15)
        dfs = pd.read_html(res.text)
        df = dfs[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        df['code'] = df['有價證券代號及名稱'].astype(str).str.split('　').str[0]
        # 過濾四碼普通股
        valid_codes = df[df['code'].str.len() == 4]['code'].tolist()
        return [c + suffix for c in valid_codes]
    except Exception as e:
        st.error(f"無法獲取{market_type}清單: {e}")
        return []

def analyze_logic(ticker, df, mode="空方"):
    """核心分析邏輯"""
    try:
        if not isinstance(df, pd.DataFrame) or 'Close' not in df.columns: return None
        data = df.dropna()
        if len(data) < 20: return None
        
        curr, prev = data.iloc[-1], data.iloc[-2]
        ma5 = data['Close'].rolling(5).mean().iloc[-1]
        ma20 = data['Close'].rolling(20).mean().iloc[-1]
        vol_ma5 = data['Volume'].rolling(5).mean().iloc[-1]
        bias = (curr['Close'] - ma20) / ma20
        
        score = 0
        reasons = []

        if mode == "空方":
            if curr['Close'] < ma5: score += 1; reasons.append("破5MA")
            if curr['Close'] < curr['Open']: score += 1; reasons.append("收黑K")
            if bias > 0.05: score += 2; reasons.append("高乖離回檔")
            if curr['Close'] < prev['Close'] and curr['Volume'] > vol_ma5: score += 1; reasons.append("量增跌")
        else:
            if curr['Close'] > ma5: score += 1; reasons.append("突破5MA")
            if curr['Close'] > curr['Open']: score += 1; reasons.append("收紅K")
            if bias < -0.05: score += 2; reasons.append("跌深反彈")
            if curr['Close'] > prev['Close'] and curr['Volume'] > vol_ma5: score += 1; reasons.append("量增漲")
            
        if score >= 3:
            return {
                "代號": ticker, "收盤價": round(float(curr['Close']), 2),
                "漲跌幅": f"{((curr['Close']-prev['Close'])/prev['Close']*100):.2f}%",
                "評分": score, "符合訊號": "、".join(reasons),
                "20MA乖離": f"{(bias*100):.2f}%", "成交量(張)": int(curr['Volume']/1000)
            }
    except: return None

# --- 2. Sidebar 欄位設定 ---
st.sidebar.title("🛠️ 選股設定儀表板")
market_choice = st.sidebar.selectbox("1. 選擇市場類型", ["上市", "上櫃"])
trade_mode = st.sidebar.radio("2. 切換交易方向", ["空方當沖 (Short)", "多方當沖 (Long)"])
min_score = st.sidebar.slider("3. 最低評分門檻", 1, 5, 3)

# 設定成交量濾網 (上市 1000張 / 上櫃 500張)
vol_threshold = 1000000 if market_choice == "上市" else 500000

# --- 3. UI 呈現 ---
st.title(f"⚡ 台股極速選股器 - {market_choice}{trade_mode[:2]}模式")
st.info(f"當前設定：篩選交易量 > {1000 if market_choice=='上市' else 500} 張標的。")

if st.button(f"🚀 開始{market_choice}股票掃描"):
    with st.spinner(f"🔍 正在進行 {market_choice} 市場掃描中，請稍候..."):
        all_tickers = get_stock_tickers(market_choice)
        if not all_tickers: st.stop()
        
        status_msg = st.empty()
        status_msg.info(f"第一階段：篩選 {len(all_tickers)} 隻標的流動性...")
        
        # 批次下載今日資訊
        fast_data = yf.download(all_tickers, period="3d", group_by='ticker', progress=False, threads=True)
        
        qualified_tickers = []
        for t in all_tickers:
            try:
                temp_df = fast_data[t].dropna() if len(all_tickers) > 1 else fast_data.dropna()
                if temp_df.empty: continue
                last_close, last_vol = float(temp_df['Close'].iloc[-1]), temp_df['Volume'].iloc[-1]
                
                # 排除漲停 (僅空方模式適用)
                is_limit_up = (last_close - temp_df['Close'].iloc[-2]) / temp_df['Close'].iloc[-2] >= 0.098
                
                # 動態成交量過濾器
                if last_vol >= vol_threshold and last_close > 20:
                    if trade_mode.startswith("空方") and is_limit_up: continue
                    qualified_tickers.append(t)
            except: continue
            
        status_msg.success(f"✅ 第一階段完成！共 {len(qualified_tickers)} 隻進入深度分析...")
        
        results = []
        if qualified_tickers:
            detail_data = yf.download(qualified_tickers, period="1mo", group_by='ticker', progress=False, threads=True)
            progress_bar = st.progress(0)
            for i, t in enumerate(qualified_tickers):
                df_to_analyze = detail_data[t] if len(qualified_tickers) > 1 else detail_data
                res = analyze_stock(t, df_to_analyze, mode=trade_mode[:2])
                if res: results.append(res)
                progress_bar.progress((i + 1) / len(qualified_tickers))
            
            if results:
                final_df = pd.DataFrame(results).sort_values(by="評分", ascending=False)
                st.success(f"🔥 分析完成！{market_choice}觀察清單：")
                st.dataframe(final_df.head(15), use_container_width=True)
                
                # 評分說明
                st.markdown("---")
                st.subheader("📊 評分邏輯說明")
                cols = st.columns(2)
                with cols[0]:
                    st.write("**空方邏輯 (Short)**")
                    st.markdown("- 破5MA (+1)\n- 收黑K (+1)\n- 正乖離>5% (+2)\n- 量增跌 (+1)")
                with cols[1]:
                    st.write("**多方邏輯 (Long)**")
                    st.markdown("- 突破5MA (+1)\n- 收紅K (+1)\n- 負乖離>5% (+2)\n- 量增漲 (+1)")
            else:
                st.warning("目前市場無符合標的。")
        else:
            st.error("初步篩選後無標的。")
