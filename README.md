# Taiwan Stock Short-Selling Selector 📉

自動化篩選台股適合「隔日放空當沖」標的的工具。

## 💡 策略邏輯
- **流動性過濾**：日成交量 > 2,000 張，確保進出無滑價。
- **技術指標**：
  - 跌破 5MA 且 5MA 下趨。
  - 當日收黑 K (跌勢確立)。
  - 20MA 正乖離 > 5% (找過熱反轉點)。
  - 量增下跌 (主力出貨訊號)。

## 🚀 如何執行
1. Clone 專案：`git clone https://github.com/你的帳號/你的倉庫名.git`
2. 安裝依賴：`pip install -r requirements.txt`
3. 執行 App：`streamlit run app.py`

## ⚠️ 免責聲明
本程式僅供量化分析研究參考，不保證獲利。投資人應根據市場即時狀況獨立判斷並自負盈虧。
