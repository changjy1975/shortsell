import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import urllib3
import time

# --- 1. 基礎設定 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="台股多空雙向選股器", layout="wide")

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
        df['code'] = df['有價證券代號及名稱'].astype(str).str.split('　').str[0]
        valid_codes = df[df['code'].str.len() == 4]['code'].tolist()
        return [c + ".TW" for c in valid_codes]
    except Exception as e:
        st.error(f"無法獲取上市股票清單: {e}")
        return []

# --- 2. 核心邏輯 (空方與多方) ---
def analyze_stock(ticker, df, mode="空方"):
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
            # 空方邏輯
            if curr['Close'] < ma5: score += 1; reasons.append("跌破5MA")
            if curr['Close'] < curr['Open']: score += 1; reasons.append("收黑K")
            if bias > 0.05: score += 2; reasons.append("高乖離回檔")
            if curr['Close'] < prev['Close'] and curr['Volume'] > vol_ma5: score += 1; reasons.append("量增跌")
        else:
            # 多方邏輯 (Long Strategy)
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

# --- 3. UI 介面與導覽 ---
st.sidebar.title("🛠️ 選股設定")
mode = st.sidebar.radio("切換交易方向", ["空方當沖 (Short)", "多方當沖 (Long)"])
min_score = st.sidebar.slider("最低評分門檻", 1, 5, 3)

if mode == "空方當沖 (Short)":
    st.title("📉 台股極速選股器 - 空方頁面")
    st.info("目標：挑選高檔轉弱、量增跌破均線的股票。")
else:
    st.title("📈 台股極速選股器 - 多方頁面")
    st.info("目標：挑選強勢突破、量增站上均線的股票。")

if st.button(f"🚀 開始上市股票掃描 ({mode[:2]})"):
    with st.spinner(f"🔍 正在進行{mode[:2]}掃描中，請稍候..."):
        all_tickers = get_listed_tickers()
        status_msg = st.empty()
        status_msg.info(f"第一階段：篩選 {len(all_tickers)} 隻標的流動性...")
        
        # 第一階段：快速篩選 (過濾量小、價格過低標的)
        fast_data = yf.download(all_tickers, period="3d", group_by='ticker', progress=False, threads=True)
        qualified_tickers = []
        for t in all_tickers:
            try:
                temp_df = fast_data[t].dropna()
                last_close, last_vol = float(temp_df['Close'].iloc[-1]), temp_df['Volume'].iloc[-1]
                
                # 做多不排除漲停，做空排除漲停
                is_limit_up = (last_close - temp_df['Close'].iloc[-2]) / temp_df['Close'].iloc[-2] >= 0.098
                
                if last_vol >= 1500000 and last_close > 20:
                    if mode.startswith("空方") and is_limit_up: continue
                    qualified_tickers.append(t)
            except: continue
        
        status_msg.success(f"✅ 第一階段完成！共 {len(qualified_tickers)} 隻進入深度分析...")
        
        # 第二階段：分析
        results = []
        if qualified_tickers:
            detail_data = yf.download(qualified_tickers, period="1mo", group_by='ticker', progress=False, threads=True)
            progress_bar = st.progress(0)
            for i, t in enumerate(qualified_tickers):
                df_to_analyze = detail_data[t] if len(qualified_tickers) > 1 else detail_data
                res = analyze_stock(t, df_to_analyze, mode=mode[:2])
                if res: results.append(res)
                progress_bar.progress((i + 1) / len(qualified_tickers))
            
            if results:
                final_df = pd.DataFrame(results).sort_values(by="評分", ascending=False)
                st.success(f"🔥 分析完成！明日建議{mode[:2]}觀察清單：")
                st.dataframe(final_df.head(10), use_container_width=True)
                
                st.markdown("---")
                st.subheader(f"📊 {mode[:2]}評分邏輯說明")
                if mode.startswith("空方"):
                    st.markdown("""
                    | 評分項目 | 邏輯說明 | 分數權重 |
                    | :--- | :--- | :---: |
                    | **跌破 5MA** | 短期趨勢轉弱。 | +1 |
                    | **收黑K** | 盤中拋售力道強。 | +1 |
                    | **高乖離回檔** | 20MA 正乖離 > 5%。 | **+2** |
                    | **量增下跌** | 價跌且量大於 5 日均量。 | +1 |
                    """)
                else:
                    st.markdown("""
                    | 評分項目 | 邏輯說明 | 分數權重 |
                    | :--- | :--- | :---: |
                    | **突破 5MA** | 短期趨勢轉強。 | +1 |
                    | **收紅K** | 買盤力道強勁。 | +1 |
                    | **跌深反彈** | 20MA 負乖離 > 5% (負乖離較大後轉折)。 | **+2** |
                    | **量增上漲** | 價漲且量大於 5 日均量。 | +1 |
                    """)
            else:
                st.warning("目前市場無符合標的。")
        else:
            st.error("初步篩選後無標的。")
