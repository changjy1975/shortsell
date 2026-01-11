import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import urllib3
import time

# --- 1. 基礎設定與環境優化 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="台股極速選股器", layout="wide")

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

def analyze_logic(ticker, df):
    """分析策略邏輯"""
    try:
        if isinstance(df, pd.DataFrame) and 'Close' in df.columns:
            data = df.dropna()
        else:
            return None

        if len(data) < 20: return None
        
        curr = data.iloc[-1]
        prev = data.iloc[-2]
        
        ma5 = data['Close'].rolling(5).mean().iloc[-1]
        ma20 = data['Close'].rolling(20).mean().iloc[-1]
        vol_ma5 = data['Volume'].rolling(5).mean().iloc[-1]
        
        score = 0
        reasons = []
        
        # 評分標準設定
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
st.title("📉 台股極速當沖選股器 (上市限定)")
st.info("💡 說明：本工具專為「隔日放空當沖」設計，挑選高檔轉弱之標的。")

if st.button("🚀 開始上市股票掃描"):
    with st.spinner("🔍 正在進行上市股票掃描中，請稍候..."):
        all_tickers = get_listed_tickers()
        if not all_tickers:
            st.error("找不到股票清單，請檢查網路。")
            st.stop()
            
        status_msg = st.empty()
        status_msg.info(f"第一階段：初步篩選 {len(all_tickers)} 隻標的流動性...")
        
        try:
            fast_data = yf.download(all_tickers, period="3d", group_by='ticker', progress=False, threads=True)
        except Exception as e:
            st.error(f"下載數據失敗: {e}")
            st.stop()

        qualified_tickers = []
        for t in all_tickers:
            try:
                temp_df = fast_data[t].dropna() if len(all_tickers) > 1 else fast_data.dropna()
                if temp_df.empty: continue
                last_close, prev_close = float(temp_df['Close'].iloc[-1]), float(temp_df['Close'].iloc[-2])
                last_vol = temp_df['Volume'].iloc[-1]
                pct_change = (last_close - prev_close) / prev_close
                if pct_change < 0.098 and last_vol >= 1500000 and last_close > 20:
                    qualified_tickers.append(t)
            except: continue
                
        status_msg.success(f"✅ 第一階段完成！共 {len(qualified_tickers)} 隻標的進入深度分析...")
        
        results = []
        if qualified_tickers:
            detail_data = yf.download(qualified_tickers, period="1mo", group_by='ticker', progress=False, threads=True)
            progress_bar = st.progress(0)
            for i, t in enumerate(qualified_tickers):
                df_to_analyze = detail_data[t] if len(qualified_tickers) > 1 else detail_data
                res = analyze_logic(t, df_to_analyze)
                if res: results.append(res)
                progress_bar.progress((i + 1) / len(qualified_tickers))
            
            status_msg.empty()
            if results:
                final_df = pd.DataFrame(results).sort_values(by="評分", ascending=False)
                st.success(f"🔥 分析完成！明日建議放空觀察清單：")
                st.dataframe(final_df.head(10), use_container_width=True)
                
                # --- 新增：評分計算方式說明 ---
                st.markdown("---")
                st.subheader("📊 評分邏輯說明")
                st.markdown("""
                本系統根據以下四項空方指標進行綜合評分（總分 5 分，達 **3 分** 以上方進入名單）：
                
                | 評分項目 | 邏輯說明 | 分數權重 |
                | :--- | :--- | :---: |
                | **跌破 5MA** | 收盤價低於 5 日均線，代表短期趨勢轉弱。 | +1 |
                | **當日收黑K** | 收盤價低於開盤價，代表盤中拋售力道強勁。 | +1 |
                | **高乖離回檔** | 收盤價高於 20MA 超過 5%，具備漲多修正空間。 | **+2** |
                | **量增下跌** | 價跌且成交量大於 5 日均量，顯示恐慌性出貨。 | +1 |
                
                > **💡 交易提醒：** 當沖放空建議觀察隔日開盤，若開高走低跌破平盤，勝率較高。
                """)
                
            else:
                st.warning("目前的篩選條件下，無符合評分標準的標的。")
        else:
            st.error("初步篩選後無剩餘標的。")

st.caption("數據來源：Yahoo Finance。僅供策略研究參考。")
