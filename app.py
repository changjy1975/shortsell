import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import urllib3
from datetime import datetime

# --- 基礎設定與 SSL 修正 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="台股隔日放空選股器", layout="wide")

# --- 1. 自動抓取「上市股票」清單 (已優化縮減範圍) ---
@st.cache_data(ttl=86400)
def get_listed_taiwan_tickers():
    """僅從交易所官網抓取『上市股票』代碼，縮小掃描範圍以提升速度"""
    # 僅抓取上市 (strMode=2)，移除上櫃 (strMode=4)
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    all_tickers = []
    try:
        # verify=False 跳過 SSL 驗證
        res = requests.get(url, verify=False, headers=headers, timeout=15)
        dfs = pd.read_html(res.text)
        df = dfs[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        
        # 篩選標準：代碼為 4 碼的普通股
        df['code_name'] = df['有價證券代號及名稱'].astype(str)
        df['code'] = df['code_name'].str.split('　').str[0]
        mask = df['code'].str.len() == 4
        
        codes = df[mask]['code'].tolist()
        # 上市股票後綴為 .TW
        all_tickers.extend([str(c) + ".TW" for c in codes])
    except Exception as e:
        st.error(f"抓取上市清單失敗: {e}")
            
    return list(set(all_tickers))

# --- 2. 核心選股策略邏輯 ---
def analyze_stock(ticker, df):
    """分析單一股票是否符合放空條件"""
    try:
        # 清理 yfinance 的 MultiIndex 欄位
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df = df.dropna()
        if len(df) < 20: return None
        
        curr = df.iloc[-1]   # 今日
        prev = df.iloc[-2]   # 昨日
        
        # 指標計算
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
        
        score = 0
        reasons = []

        # --- 濾網 A: 基礎流動性 (設 1000 張為門檻) ---
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

        if score >= 2: # 至少符合兩項訊號才顯示
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
st.title("📉 台股隔日放空當沖選股器 (上市限定版)")
st.markdown("本系統專注於**上市股票**，挑選出具備空頭動能與高檔轉弱訊號的標的。")

c1, c2 = st.columns(2)
with c1:
    scan_mode = st.selectbox("1. 選擇掃描範圍", ["快速掃描 (權值股 Top 50)", "上市股票深度掃描 (約 1000 隻)"])
with c2:
    min_score = st.slider("2. 最低篩選分數", 1, 5, 3)

if st.button("🚀 開始掃描分析"):
    if "快速" in scan_mode:
        tickers = [
            "2330.TW", "2317.TW", "2454.TW", "2308.TW", "2303.TW", "2603.TW", "2609.TW", 
            "2615.TW", "2409.TW", "3481.TW", "2382.TW", "3231.TW", "2357.TW", "2881.TW", 
            "2882.TW", "2886.TW", "2301.TW", "2324.TW", "2610.TW", "2618.TW", "2353.TW"
        ]
    else:
        with st.spinner("正在獲取最新上市股票清單..."):
            tickers = get_listed_taiwan_tickers()
    
    results = []
    bar = st.progress(0)
    status_text = st.empty()
    
    # 批次下載設定 (20 隻一組較為穩定)
    batch_size = 20 
    total = len(tickers)
    
    with st.spinner(f"正在分析 {total} 隻上市標的..."):
        for i in range(0, total, batch_size):
            batch = tickers[i : i + batch_size]
            try:
                data = yf.download(batch, period="1mo", interval="1d", group_by='ticker', progress=False, threads=True)
                
                for t in batch:
                    if len(batch) > 1:
                        if t in data and not data[t].empty:
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
            status_text.text(f"已掃描: {min(i + batch_size, total)} / {total}")
            
            # 加入微小延遲保護連線
            time.sleep(0.4)

    st.divider()
    if results:
        final_df = pd.DataFrame(results).sort_values(by="評分", ascending=False)
        st.success(f"掃描完畢！共找到 {len(final_df)} 隻符合條件之標的。")
        st.dataframe(final_df, use_container_width=True)
    else:
        st.warning("目前的篩選條件下無符合標的。這代表市場上市股普遍強勢。")

st.caption("免責聲明：本程式由 AI 輔助開發，僅供量化研究參考，不保證獲利。投資人應獨立判斷風險。")
