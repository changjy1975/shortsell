import streamlit as st
from scraper import fetch_taiwan_stock_data, get_universe
from strategy import analyze_short_opportunity

st.title("🏹 台股隔日放空高勝率篩選器")

if st.button("開始掃描台股標的"):
    universe = get_universe()
    with st.spinner(f"正在分析 {len(universe)} 隻標的..."):
        all_data = fetch_taiwan_stock_data(universe)
        results = []
        
        for ticker in universe:
            try:
                # yfinance 多個標的下載後的處理方式
                df = all_data[ticker]
                res = analyze_short_opportunity(ticker, df)
                if res: results.append(res)
            except:
                continue
        
        # 依照 Score 排序並取前 10 名
        final_df = pd.DataFrame(results).sort_values(by='Score', ascending=False).head(10)
        
        st.subheader("📋 明日建議放空觀察清單 Top 10")
        st.table(final_df)
        
        st.warning("⚠️ 當沖提醒：開盤若直接跳空大跌不追空，待反彈無力再進場。")
