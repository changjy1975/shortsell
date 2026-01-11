import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
from datetime import datetime

# --- 頁面設定 ---
st.set_page_config(page_title="台股隔日放空選股器", layout="wide")

# --- 1. 自動抓取全台股清單 (含緩存功能) ---
@st.cache_data(ttl=86400)
def get_all_taiwan_tickers():
    """從交易所官網抓取所有上市與上櫃股票代碼"""
    urls = [
        ("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", ".TW"),  # 上市
        ("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4", ".TWO") # 上櫃
    ]
    all_tickers = []
    for url, suffix in urls:
        try:
            res = requests.get(url)
            # 使用 pandas 讀取網頁表格
            dfs = pd.read_html(res.text)
            df = dfs[0]
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            # 篩選標準：代碼為 4 碼的普通股 (排除權證、ETF、存託憑證)
            df['code_name'] = df['有價證券代號及名稱'].astype(str)
            df['code'] = df['code_name'].str.split('　').str[0]
            mask = df['code'].str.len() == 4
            all_tickers.extend([c + suffix for c in df[mask]['code']])
        except Exception as e:
            st.warning(f"抓取 {suffix} 清單時發生錯誤: {e}")
            continue
    return list(set(all_tickers))

# --- 2. 核心選股策略邏輯 ---
def analyze_stock(ticker, df):
    """分析單一股票是否符合放空條件"""
    try:
        # 強制清理 yfinance 的 MultiIndex 欄位 (深度掃描最常出錯的地方)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 移除 NaN 值
        df = df.dropna()
        if len(df) < 20: return None
        
        curr = df.iloc[-1]   # 今日數據
        prev = df.iloc[-2]   # 昨日數據
        
        # 指標計算
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
        
        score = 0
        reasons = []

        # --- 濾網 A: 基礎流動性 (深度掃描建議設 1000 張，否則會掃不出東西) ---
        if curr['Volume'] < 1000000: return None 
        
        # --- 濾網 B: 股價大於 20 元 ---
        if curr['Close'] < 20: return None

        # --- 空方訊號評分 ---
        # 1. 跌破 5 日線 (趨勢轉弱)
        if curr['Close'] < ma5:
            score += 1
            reasons.append("跌破5MA")
            
        # 2. 今日收黑 K
        if curr['Close'] < curr['Open']:
            score += 1
            reasons.append("收黑K")

        # 3. 高乖離回檔 (20MA 正乖離 > 5%)
        bias = (curr['Close'] - ma20) / ma20
        if bias > 0.05:
            score += 2
            reasons.append("高乖離")

        # 4. 量增下跌 (價跌量增)
        if curr['Close'] < prev['Close'] and curr['Volume'] > vol_ma5:
            score += 1
            reasons.append("量增跌")

        if score > 0:
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

# --- 3. Streamlit UI 介面 ---
st.title("📉 台股隔日放空當沖選股器")
st.markdown("本系統自動掃描全台股市場，挑選出具備**空頭動能**與**高檔轉弱**訊號的標的。")

# 介面選項
c1, c2 = st.columns(2)
with c1:
    scan_mode = st.selectbox("1. 選擇掃描範圍", ["快速掃描 (權值股 Top 50)", "深度掃描 (全台股上市櫃)"])
with c2:
    min_score = st.slider("2. 最低篩選分數 (建議 3 分)", 1, 5, 3)

if st.button("🚀 開始掃描分析"):
    # 建立股票清單
    if "快速" in scan_mode:
        tickers = [
            "2330.TW", "2317.TW", "2454.TW", "2308.TW", "2303.TW", "2603.TW", "2609.TW", 
            "2615.TW", "2409.TW", "3481.TW", "2382.TW", "3231.TW", "2357.TW", "2881.TW", 
            "2882.TW", "2886.TW", "2301.TW", "2324.TW", "2610.TW", "2618.TW", "2353.TW"
        ]
    else:
        with st.spinner("正在獲取最新全台股清單..."):
            tickers = get_all_taiwan_tickers()
    
    results = []
    bar = st.progress(0)
    status_text = st.empty()
    
    # 開始批次分析
    batch_size = 25  # 減小批次大小以增加深度掃描穩定性
    total = len(tickers)
    
    with st.spinner(f"正在分析 {total} 隻標的，請稍候..."):
        for i in range(0, total, batch_size):
            batch = tickers[i : i + batch_size]
            try:
                # 批次下載
                data = yf.download(batch, period="1mo", interval="1d", group_by='ticker', progress=False, threads=True)
                
                for t in batch:
                    if len(batch) > 1:
                        if t in data:
                            res = analyze_stock(t, data[t])
                    else:
                        res = analyze_stock(t, data)
                    
                    if res and res['評分'] >= min_score:
                        results.append(res)
            except:
                continue
            
            # 更新進度
            current_progress = min((i + batch_size) / total, 1.0)
            bar.progress(current_progress)
            status_text.text(f"掃描進度: {min(i + batch_size, total)} / {total}")
            
            # 深度掃描時加入微小延遲防止被 Yahoo 封鎖
            if "深度" in scan_mode:
                time.sleep(0.5)

    # 顯示結果
    st.divider()
    if results:
        final_df = pd.DataFrame(results).sort_values(by="評分", ascending=False)
        st.success(f"掃描完畢！共找到 {len(final_df)} 隻符合條件之標的。")
        st.dataframe(final_df, use_container_width=True)
    else:
        st.warning("目前的篩選條件找不到標的。這通常代表市場目前過於強勢，不建議進行放空。")

st.caption("免責聲明：本程式由 AI 輔助開發，僅供策略研究參考。投資人應獨立評估風險，本程式不保證任何獲利。")
