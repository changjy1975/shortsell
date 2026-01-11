import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime

# --- 頁面設定 ---
st.set_page_config(page_title="台股隔日放空選股器", layout="wide")

# --- 1. 自動抓取全台股清單 (含緩存功能，避免重複爬蟲) ---
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
            df = pd.read_html(res.text)[0]
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            # 篩選標準：代碼為 4 碼的普通股 (排除權證、ETF)
            df['code'] = df['有價證券代號及名稱'].str.split('　').str[0]
            mask = df['code'].str.len() == 4
            all_tickers.extend([c + suffix for c in df[mask]['code']])
        except:
            continue
    return list(set(all_tickers)) # 移除重複項

# --- 2. 核心選股策略邏輯 ---
def analyze_stock(ticker, df):
    """分析單一股票是否符合放空條件"""
    try:
        # 清理 yfinance 可能產生的多層索引 (MultiIndex)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        if len(df) < 20: return None
        
        # 取得最新(今日收盤)與前一日數據
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 計算技術指標
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
        
        score = 0
        reasons = []

        # --- 基礎濾網 ---
        # 1. 流動性濾網 (成交量 > 2000張，確保當沖進出容易)
        if curr['Volume'] < 2000000: return None 
        # 2. 價格濾網 (股價 > 20元)
        if curr['Close'] < 20: return None

        # --- 空方訊號評分 ---
        # 訊號 A: 跌破 5 日線 (短期趨勢轉弱)
        if curr['Close'] < ma5:
            score += 1
            reasons.append("跌破5MA")
            
        # 訊號 B: 今日收黑K (代表盤中拋售力道強)
        if curr['Close'] < curr['Open']:
            score += 1
            reasons.append("收黑K")

        # 訊號 C: 高乖離反轉 (20MA 正乖離 > 5%)
        bias = (curr['Close'] - ma20) / ma20
        if bias > 0.05:
            score += 2
            reasons.append("高乖離回檔")

        # 訊號 D: 量增下跌 (價跌量增是經典弱勢訊號)
        if curr['Close'] < prev['Close'] and curr['Volume'] > vol_ma5:
            score += 1
            reasons.append("量增下跌")

        # 篩選門檻：至少符合設定分數才列出
        return {
            "代號": ticker,
            "收盤價": f"{curr['Close']:.2f}",
            "漲跌幅": f"{((curr['Close']-prev['Close'])/prev['Close']*100):.2f}%",
            "評分": score,
            "符合訊號": "、".join(reasons),
            "20MA乖離": f"{(bias*100):.2f}%",
            "成交量(張)": int(curr['Volume']/1000)
        }
    except:
        return None

# --- 3. Streamlit 介面呈現 ---
st.title("📉 台股隔日放空當沖選股 App")
st.markdown("本系統掃描全台股市場，挑選出具備**空頭動能**與**高檔轉弱**訊號的標的。")

# 介面側邊欄/頂部選項
scan_mode = st.selectbox("選擇掃描模式", ["快速掃描 (台灣50/中型100)", "深度掃描 (全台股清單)"])
min_score = st.slider("最低篩選分數 (評分越高代表空方訊號越強)", 1, 5, 3)

if st.button("🚀 開始掃描分析"):
    # 建立股票清單
    if "快速" in scan_mode:
        tickers = ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "2303.TW", "2603.TW", "2609.TW", "2409.TW", "3481.TW", "2382.TW", "3231.TW", "2881.TW", "2882.TW"]
    else:
        with st.spinner("正在獲取最新全台股清單..."):
            tickers = get_all_taiwan_tickers()
    
    results = []
    progress_text = st.empty()
    bar = st.progress(0)
    
    # 開始批次分析
    with st.spinner("正在分析市場數據..."):
        batch_size = 40  # 調整批次大小以優化效能
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i : i + batch_size]
            # 下載歷史資料
            data = yf.download(batch, period="1mo", interval="1d", group_by='ticker', progress=False)
            
            for t in batch:
                try:
                    # 處理單一標的與多標的資料結構差異
                    df = data[t].dropna() if len(batch) > 1 else data.dropna()
                    res = analyze_stock(t, df)
                    if res and res['評分'] >= min_score:
                        results.append(res)
                except:
                    continue
            
            # 更新進度條
            pct = min((i + batch_size) / len(tickers), 1.0)
            bar.progress(pct)
            progress_text.text(f"掃描進度: {min(i + batch_size, len(tickers))} / {len(tickers)}")

    # 顯示分析結果
    st.divider()
    if results:
        final_df = pd.DataFrame(results).sort_values(by="評分", ascending=False)
        st.success(f"掃描完畢！共找到 {len(final_df)} 隻符合條件之標的。")
        st.table(final_df.head(10)) # 顯示前 10 隻最符合條件的
    else:
        st.warning("當前篩選條件下無符合標的，可能代表市場正處於極端強勢，建議保守看待。")

st.caption("免責聲明：本工具僅供策略研究參考，投資人應自行評估交易風險並自負盈虧。")
