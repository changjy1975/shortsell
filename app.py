import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import urllib3
import time

# --- 1. 基礎設定 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="台股極速多空選股器", layout="wide")

@st.cache_data(ttl=86400)
def get_stock_tickers(market_type):
    """抓取清單"""
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2" if market_type == "上市" else "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    suffix = ".TW" if market_type == "上市" else ".TWO"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, verify=False, headers=headers, timeout=15)
        df = pd.read_html(res.text)[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        df['code'] = df['有價證券代號及名稱'].astype(str).str.split('　').str[0]
        valid_codes = df[df['code'].str.len() == 4]['code'].tolist()
        return [c + suffix for c in valid_codes]
    except Exception as e:
        st.error(f"清單抓取失敗: {e}")
        return []

def analyze_stock(ticker, df, mode="空方"):
    """核心策略：回傳所有評分大於 0 的結果，交由 UI 篩選"""
    try:
        if not isinstance(df, pd.DataFrame) or 'Close' not in df.columns: return None
        data = df.dropna()
        if len(data) < 20: return None
        
        curr, prev = data.iloc[-1], data.iloc[-2]
        ma5 = data['Close'].rolling(5).mean().iloc[-1]
        ma20 = data['Close'].rolling(20).mean().iloc[-1]
        vol_ma5 = data['Volume'].rolling(5).mean().iloc[-1]
        bias = (curr['Close'] - ma20) / ma20
        
        score, reasons = 0, []

        if mode == "空方":
            if curr['Close'] < ma5: score += 1; reasons.append("破5MA")
            if curr['Close'] < curr['Open']: score += 1; reasons.append("收黑K")
            if bias > 0.05: score += 2; reasons.append("高乖離")
            if curr['Close'] < prev['Close'] and curr['Volume'] > vol_ma5: score += 1; reasons.append("量增跌")
        else:
            if curr['Close'] > ma5: score += 1; reasons.append("突破5MA")
            if curr['Close'] > curr['Open']: score += 1; reasons.append("收紅K")
            if bias < -0.05: score += 2; reasons.append("跌深反彈")
            if curr['Close'] > prev['Close'] and curr['Volume'] > vol_ma5: score += 1; reasons.append("量增漲")
            
        # 只要有一項訊號就回傳，不再硬編碼 3 分
        if score > 0:
            return {
                "代號": ticker, 
                "收盤價": round(float(curr['Close']), 2),
                "漲跌幅": f"{((curr['Close']-prev['Close'])/prev['Close']*100):.2f}%",
                "評分": int(score), 
                "符合訊號": "、".join(reasons),
                "20MA乖離": f"{(bias*100):.2f}%", 
                "成交量(張)": int(curr['Volume']/1000)
            }
    except: return None

# --- 2. Sidebar 設定 ---
st.sidebar.title("⚙️ 參數設定")
market_choice = st.sidebar.selectbox("1. 市場類型", ["上市", "上櫃"])
trade_mode = st.sidebar.radio("2. 交易方向", ["空方當沖 (Short)", "多方當沖 (Long)"])

# 這裡的變數 min_score 將會與結果連動
min_score = st.sidebar.slider("3. 評分門檻 (即時過濾結果)", 1, 5, 3)

VOL_THRESHOLD = 3000000 

# --- 3. UI 呈現 ---
st.title(f"🚀 台股極速雙向選股器 ({market_choice})")
st.warning(f"當前模式：{trade_mode[:2]} / 門檻：>= {min_score} 分 / 成交量 > 3000 張")

if st.button(f"🔍 開始{market_choice}股票掃描"):
    with st.spinner(f"正在掃描市場中..."):
        all_tickers = get_stock_tickers(market_choice)
        if not all_tickers: st.stop()
        
        status_msg = st.empty()
        status_msg.info(f"第一階段：流動性過濾中...")
        
        fast_data = yf.download(all_tickers, period="3d", group_by='ticker', progress=False, threads=True)
        
        qualified_tickers = []
        for t in all_tickers:
            try:
                temp_df = fast_data[t].dropna() if len(all_tickers) > 1 else fast_data.dropna()
                if temp_df.empty: continue
                last_close, prev_close, last_vol = float(temp_df['Close'].iloc[-1]), float(temp_df['Close'].iloc[-2]), float(temp_df['Volume'].iloc[-1])
                is_limit_up = (last_close - prev_close) / prev_close >= 0.098
                
                if last_vol >= VOL_THRESHOLD and last_close > 20:
                    if trade_mode.startswith("空方") and is_limit_up: continue
                    qualified_tickers.append(t)
            except: continue
        
        status_msg.success(f"✅ 第一階段完成！篩選出 {len(qualified_tickers)} 隻高流動性標的。")
        
        # 第二階段深度分析
        results = []
        if qualified_tickers:
            detail_data = yf.download(qualified_tickers, period="1mo", group_by='ticker', progress=False, threads=True)
            progress_bar = st.progress(0)
            
            for i, t in enumerate(qualified_tickers):
                df_to_analyze = detail_data[t] if len(qualified_tickers) > 1 else detail_data
                res = analyze_stock(t, df_to_analyze, mode=trade_mode[:2])
                
                # --- 關鍵連線修正：根據 Sidebar 的 min_score 進行篩選 ---
                if res and res['評分'] >= min_score:
                    results.append(res)
                progress_bar.progress((i + 1) / len(qualified_tickers))
            
            status_msg.empty()
            if results:
                final_df = pd.DataFrame(results).sort_values(by="評分", ascending=False)
                st.success(f"🔥 符合 {min_score} 分以上標的：")
                st.dataframe(final_df, use_container_width=True)
                
                st.markdown("---")
                st.subheader("📊 策略評分權重說明")
                col_l, col_r = st.columns(2)
                with col_l:
                    st.write("**空方 (Short)**")
                    st.markdown("- 跌破5MA (+1)\n- 收黑K (+1)\n- 高正乖離 (>5%) (+2)\n- 量增跌 (+1)")
                with col_r:
                    st.write("**多方 (Long)**")
                    st.markdown("- 突破5MA (+1)\n- 收紅K (+1)\n- 高負乖離 (<-5%) (+2)\n- 量增漲 (+1)")
            else:
                st.warning(f"目前的門檻設定為 {min_score} 分，市場中沒有符合該強度的標的。")
        else:
            st.error("掃描結束，今日市場流動性不足 3000 張。")

st.caption("數據來源：Yahoo Finance | 兩階段加速過濾技術")
