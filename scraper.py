import yfinance as yf
import pandas as pd

def fetch_taiwan_stock_data(ticker_list, period="3mo"):
    """
    批次抓取台股歷史資料
    ticker_list: ['2330.TW', '2317.TW', ...]
    """
    # 抓取 OHLCV 資料
    data = yf.download(ticker_list, period=period, interval="1d", group_by='ticker')
    return data

def get_universe():
    # 建議先從台灣 50 (0050) 與 中型 100 (0051) 的成分股開始，避免流動性風險
    # 這裡僅列出部分示意，你可以擴充至 150 隻常用標的
    return ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "2303.TW", "2881.TW", "2882.TW"]
