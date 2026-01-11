import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime, timedelta

# --- 設定頁面 ---
st.set_page_config(page_title="台股隔日放空選股器", layout="wide")

# --- 1. 自動抓取全台股清單 (含緩存功能) ---
@st.cache_data(ttl=86400) # 每天更新一次清單
def get_all_taiwan_tickers():
    """從交易所抓取所有上市與上櫃股票代碼"""
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
            # 篩選標準：代碼為 4 碼的普通股
            df['code'] = df['有價證券代號及名稱'].str.split('　').str[0]
            mask = df['code'].str.len() == 4
            all_tickers.extend([c + suffix for c in df[mask]['code']])
        except:
            continue
    return all_tickers

# --- 2. 核心選股策略邏輯 ---
def analyze_stock(ticker, df):
    """分析單一股票是否符合放空條件"""
    try:
        # 清理 yfinance 可能產生的多層索引
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        if len(df) < 20: return None
        
        # 取得最新與前一日數據
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 技術指標計算
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
        
        score = 0
        reasons = []

        # 條件 1: 基礎流動性濾網 (成交量 > 2000張，避免滑價)
        if curr['Volume'] < 2000000: return None 
        
        # 條件 2: 價格 > 20元 (太低價不適合放空)
        if curr['Close'] < 20: return None

        # 條件 3: 跌破 5 日線 (趨勢轉弱)
        if curr['Close'] < ma5:
            score += 1
            reasons.append("跌破5MA")
            
        # 條件 4: 今日收黑K (且跌幅 > 1%)
        if curr['Close'] < curr['Open']:
            score += 1
            reasons.append("收黑K")

        # 條件 5: 高乖離回檔 (正乖離 > 5%)
        bias = (curr['Close'] - ma20) / ma20
        if bias > 0.05:
            score += 2
            reasons.append("高乖離反轉")

        # 條件 6: 出量下跌 (量增跌)
        if curr['Close'] < prev['Close'] and curr['Volume'] > vol_ma5:
            score += 1
            reasons.append("出量下跌")

        if score >= 2: # 至少符合兩項才列出
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
    return None

# --- 3. Streamlit UI 介面 ---
st.title("📉 台股隔日放空當沖高勝率選股 App")
st.markdown("""
本工具自動掃描全台股，挑選出**高檔轉弱、量增跌破均線**的標的。  
*提醒：當沖放空風險極高，建議配合開盤走勢（開高走低）進場。*
""")

col1, col2 = st.columns(2)
with col1:
    scan_mode = st.radio("掃描範圍", ["快速掃描 (台灣50/中型100)", "深度掃描 (全台股 1700+)"])
with col2:
    min_score = st.slider("最低篩選分數 (建議 3 分)", 1, 5, 3)

if st.button("🚀 開始分析市場"):
    # 決定股票池
    if "快速" in scan_mode:
        tickers = ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "2303.TW", "2603.TW", "2609.TW", "2409.TW", "3481.TW", "2382.TW", "3231.TW", "2881.TW"]
    else:
        tickers = get_all_taiwan_tickers()
    
    results = []
    progress_text = st.empty()
    bar = st.progress(0)
    
    # 執行掃描
    with st.spinner("正在下載並分析歷史數據..."):
        # 分批抓取以穩定性為主
        batch_size = 30
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i : i + batch_size]
            # 下載一個月內的數據
            data = yf.download(batch, period="1mo", interval="1d", group_by='ticker', progress=False)
            
            for t in batch:
                try:
                    df = data[t].dropna() if len(batch) > 1 else data.dropna()
                    res = analyze_stock(t, df)
                    if res and res['評分'] >= min_score:
                        results.append(res)
                except:
                    continue
            
            # 更新進度條
            pct = min((i + batch_size) / len(tickers), 1.0)
            bar.progress(pct)
            progress_text.text(f"已處理 {min(i + batch_size, len(tickers))} / {len(tickers)} 隻股票")

    # 顯示結果
    if results:
        final_df = pd.DataFrame(results).sort_values(by="評分", ascending=False)
        st.success(f"掃描完畢！找到 {len(final_df)} 隻符合條件標的。")
        st.dataframe(final_df.head(10), use_container_width=True) # 只取前 10 隻
    else:
        st.warning("目前市場無符合篩選條件的標的，建議空手觀望。")

# --- 4. 風險管理小工具 ---
st.divider()
st.subheader("🛡️ 交易保險計算機 (Risk Control)")
col_a, col_b = st.columns(2)
with col_a:
    entry_price = st.number_input("預計進場價", value=100.0)
with col_b:
    loss_limit = st.slider("預計停損百分比 (%)", 1.0, 5.0, 2.0)

st.error(f"⚠️ 強制停損建議價格：**{entry_price * (1 + loss_limit/100):.2f}** (若股價突破此價格，請務必回補)")
