import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import pytz
import sys
import altair as alt # <--- 新增: 引入 Altair 以繪製客製化圖表

# <--- 全域設定: 手動翻譯清單 (最強力的備案，優先級最高) --->
MANUAL_STOCK_NAMES = {
    # 電子/半導體
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2303": "聯電", 
    "2308": "台達電", "2382": "廣達", "2357": "華碩", "3231": "緯創",
    "3711": "日月光投控", "3034": "聯詠", "2379": "瑞昱", "3008": "大立光",
    "6669": "緯穎", "2345": "智邦", "2412": "中華電", "3045": "台灣大", "4904": "遠傳",
    # 金融
    "2881": "富邦金", "2882": "國泰金", "2886": "兆豐金", "2891": "中信金",
    "2884": "玉山金", "2892": "第一金", "2880": "華南金", "2885": "元大金",
    "2883": "開發金", "2890": "永豐金", "2887": "台新金", "5880": "合庫金",
    # 傳產/航運/塑化/水泥
    "2603": "長榮", "2609": "陽明", "2615": "萬海", "2618": "長榮航", "2610": "華航",
    "1301": "台塑", "1303": "南亞", "1326": "台化", "1304": "台聚",
    "2002": "中鋼", "1101": "台泥", "1102": "亞泥", "1605": "華新",
    # ETF
    "0050": "元大台灣50", "0056": "元大高股息", "00878": "國泰永續高股息",
    "00929": "復華台灣科技優息", "00940": "元大台灣價值高息", "00919": "群益台灣精選高息",
    "006208": "富邦台50", "00713": "元大台灣高息低波", "00939": "統一台灣高息動能"
}

# <--- 模組匯入檢查: 捕捉 twstock 與 lxml 的狀態 --->
import_error_msg = None
missing_lxml = False
try:
    import twstock
except ImportError as e:
    twstock = None
    error_str = str(e)
    import_error_msg = error_str
    if "lxml" in error_str:
        missing_lxml = True
except Exception as e:
    twstock = None
    import_error_msg = str(e)

# 設定網頁標題與版面
st.set_page_config(page_title="台股每日收盤紀錄小幫手", page_icon="📈", layout="wide")

# 自定義 CSS
st.markdown("""
<style>
    .stMetric { font-family: "Source Sans Pro", sans-serif; }
</style>
""", unsafe_allow_html=True)

def get_stock_data(stock_list):
    """ 抓取今日數據 (表格用) """
    data_list = []
    valid_tickers = [] 
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_stocks = len(stock_list)
    
    for i, code in enumerate(stock_list):
        code = code.strip()
        if not code: continue
        
        # 加上 .TW
        ticker_symbol = f"{code}.TW"
        status_text.text(f"正在抓取: {code} ...")
        
        try:
            stock = yf.Ticker(ticker_symbol)
            hist = stock.history(period="5d") 
            
            if len(hist) > 0:
                latest = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else latest
                
                price = latest['Close']
                prev_close = prev['Close']
                change = price - prev_close
                pct_change = (change / prev_close) * 100
                
                # <--- 名稱判斷邏輯優化 --->
                # 1. 先抓 yfinance 的名字 (通常是英文)
                name = stock.info.get('longName', code) 
                
                # 2. 強制檢查手動清單 (優先級最高，保證熱門股顯示中文)
                if code in MANUAL_STOCK_NAMES:
                    name = MANUAL_STOCK_NAMES[code]
                # 3. 如果手動清單沒有，且 twstock 模組活著，才嘗試用 twstock 查
                elif twstock and code in twstock.codes:
                    name = twstock.codes[code].name
                # <--- 結束 --->
                
                data_list.append({
                    "代號": code,
                    "名稱": name,
                    "日期": latest.name.strftime('%Y-%m-%d'),
                    "收盤價": round(price, 2),
                    "漲跌": round(change, 2),
                    "漲跌幅(%)": round(pct_change, 2),
                    "成交量": int(latest['Volume'])
                })
                valid_tickers.append((code, ticker_symbol, name))
            else:
                st.warning(f"找不到 {code} 的資料。")
                
        except Exception as e:
            st.error(f"抓取 {code} 錯誤: {e}")
            
        progress_bar.progress((i + 1) / total_stocks)
        
    status_text.text("抓取完成！")
    return pd.DataFrame(data_list), valid_tickers

def get_weekly_trend(valid_tickers):
    """ 抓取本週一至今的走勢數據 (圖表用 - 僅顯示 09:00 與 13:30) """
    
    tw = pytz.timezone('Asia/Taipei')
    today = datetime.now(tw)
    monday = today - timedelta(days=today.weekday())
    start_date = monday.strftime('%Y-%m-%d')
    
    trend_data = pd.DataFrame()
    
    for code, symbol, name in valid_tickers:
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(start=start_date, interval='1d')
            
            if not df.empty:
                points = []
                for date, row in df.iterrows():
                    d = date.replace(tzinfo=None)
                    
                    # 09:00 開盤
                    points.append({
                        'DateTime': d + timedelta(hours=9), 
                        'Price': row['Open']
                    })
                    
                    # 13:30 收盤
                    points.append({
                        'DateTime': d + timedelta(hours=13, minutes=30), 
                        'Price': row['Close']
                    })
                
                stock_df = pd.DataFrame(points).set_index('DateTime')
                
                start_price = stock_df['Price'].iloc[0]
                stock_df['CumReturn'] = ((stock_df['Price'] - start_price) / start_price) * 100
                
                series = stock_df['CumReturn']
                series.name = f"{code} {name}"
                
                if trend_data.empty:
                    trend_data = pd.DataFrame(series)
                else:
                    trend_data = trend_data.join(series, how='outer')
        except Exception:
            pass
    
    # 格式化 X 軸
    if not trend_data.empty:
        trend_data = trend_data.sort_index()
        weekdays_map = {0: '週一', 1: '週二', 2: '週三', 3: '週四', 4: '週五', 5: '週六', 6: '週日'}
        
        new_index = []
        for dt in trend_data.index:
            wd = weekdays_map[dt.weekday()]
            hm = dt.strftime("%H:%M")
            md = f"{dt.month}月{dt.day}號"
            new_index.append(f"{md} {wd} {hm}")
            
        trend_data.index = new_index
        
    return trend_data

def get_monthly_trend(valid_tickers):
    """ 抓取本月1號至今的走勢數據 (圖表用 - 每日收盤 13:30) """
    
    tw = pytz.timezone('Asia/Taipei')
    today = datetime.now(tw)
    # 取得本月1號的日期
    start_date = today.replace(day=1).strftime('%Y-%m-%d')
    
    trend_data = pd.DataFrame()
    
    for code, symbol, name in valid_tickers:
        try:
            stock = yf.Ticker(symbol)
            # 抓取日線 (日線的 Close 就是當日 13:30 收盤價)
            df = stock.history(start=start_date, interval='1d')
            
            if not df.empty:
                # 處理時區，確保可以合併
                df.index = df.index.map(lambda x: x.replace(tzinfo=None))
                
                # 計算相對於本月第一天收盤的漲跌幅
                start_price = df['Close'].iloc[0]
                # 避免除以零
                if start_price > 0:
                    series = ((df['Close'] - start_price) / start_price) * 100
                    series.name = f"{code} {name}"
                    
                    if trend_data.empty:
                        trend_data = pd.DataFrame(series)
                    else:
                        trend_data = trend_data.join(series, how='outer')
        except Exception:
            pass
            
    # 格式化 X 軸 (只顯示日期 MM/DD)
    if not trend_data.empty:
        trend_data = trend_data.sort_index()
        new_index = [dt.strftime("%m/%d") for dt in trend_data.index]
        trend_data.index = new_index
        
    return trend_data

# <--- 修正: 今年每月走勢比較 (導入自動校正與過濾機制) --->
def get_yearly_trend(valid_tickers):
    """ 抓取今年每月第一天與最後一天的收盤數據 """
    
    tw = pytz.timezone('Asia/Taipei')
    now = datetime.now(tw)
    current_year = now.year
    start_date = f"{current_year}-01-01"
    
    # 1. 先收集所有股票的原始資料
    all_series = {}
    
    for code, symbol, name in valid_tickers:
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(start=start_date, interval='1d')
            if not df.empty:
                df.index = df.index.tz_localize(None) # 移除時區
                df = df[df['Volume'] > 0] # 基本過濾成交量0
                
                # 時間守門員: 移除今日盤中資料
                last_date = df.index[-1].date()
                if last_date == now.date() and now.strftime('%H:%M') < '13:30':
                    df = df.iloc[:-1]
                
                if not df.empty:
                     # 存入收盤價，Key為 "股票代號 名稱"
                     all_series[f"{code} {name}"] = df['Close']
        except Exception:
            pass

    if not all_series:
        return pd.DataFrame()

    # 2. 合併成一個大表 (Date x Stocks)
    # 使用 outer join 保留所有日期，然後用 ffill 填補缺漏 (處理12/8缺12/9的情況)
    combined_df = pd.DataFrame(all_series)
    combined_df = combined_df.sort_index()
    combined_df = combined_df.ffill() # 關鍵: 若某股缺了最新收盤日，沿用昨日收盤價

    # 3. 過濾無效交易日 (解決 8/1 幽靈資料)
    # 邏輯: 每一天必須有超過一半的股票有資料，才算是有效開盤日
    # (combined_df 經過 ffill 後，要看原始資料其實比較準，但 ffill 後看 'NaN' 變少)
    # 我們改用一個簡單邏輯：該日期的「資料筆數」必須大於 0 (因為 pivot 後沒資料是 NaN)
    # 由於前面已經 ffill，這裡我們直接假設 ffill 後的 index 都是潛在有效日。
    # 但為了排除 8/1 (如果大部分股票 8/1 都是 NaN，ffill 也不會有值，除非 7/31 有值)
    # 更精準的作法：回頭看原始資料的覆蓋率。
    # 這裡採用簡化法：直接使用合併後的 Index，因為 yfinance 通常大部分股票日期是一致的。
    # 如果 8/1 只有一支股票有，其他都是 NaN。
    # 我們計算每個 Row 的非 NaN 數量
    valid_counts = combined_df.notna().sum(axis=1)
    threshold = len(valid_tickers) * 0.3 # 門檻: 至少30%股票有值
    combined_df = combined_df[valid_counts >= threshold]

    # 4. 找出每個月的「第一天」與「最後一天」 (基於過濾後的有效日期)
    combined_df['Month'] = combined_df.index.month
    target_dates = []
    
    for month, group in combined_df.groupby('Month'):
        if not group.empty:
            target_dates.append(group.index[0]) # 該月第一天
            if group.index[-1] != group.index[0]:
                target_dates.append(group.index[-1]) # 該月最後一天

    # 5. 只保留這些目標日期的資料
    final_df = combined_df.loc[target_dates].copy()
    
    # 移除 Month 欄位，準備計算漲跌幅
    if 'Month' in final_df.columns:
        del final_df['Month']

    # 6. 計算 YTD 漲跌幅
    trend_data = pd.DataFrame()
    for col in final_df.columns:
        # 找到該股票今年的第一個有效價格 (基期)
        # 注意: 有些股票可能年中才上市，基期不一定是 1/2
        first_valid_idx = final_df[col].first_valid_index()
        if first_valid_idx is not None:
            start_price = final_df.loc[first_valid_idx, col]
            if start_price > 0:
                trend_data[col] = ((final_df[col] - start_price) / start_price) * 100
    
    # 7. 格式化 X 軸
    if not trend_data.empty:
        new_index = [dt.strftime("%m/%d") for dt in trend_data.index]
        trend_data.index = new_index

    return trend_data
# <--- 修正結束 --->

def get_history_by_date(stock_list, target_date):
    """ 查詢特定日期的股價資料 """
    
    # <--- 新增: 時間檢核邏輯 (台灣時間) --->
    tw = pytz.timezone('Asia/Taipei')
    now = datetime.now(tw)
    
    # 1. 如果查詢日期是「今天」，且現在時間早於 13:30，表示尚未收盤
    # 我們不應該顯示資料，以免使用者誤以為盤中價格是收盤價
    if target_date == now.date() and now.strftime('%H:%M') < '13:30':
        return pd.DataFrame() # 回傳空資料，觸發外層的「查無資料」提示
    
    # 2. 如果查詢日期是「未來」，也不應該有資料
    if target_date > now.date():
        return pd.DataFrame()
    # <--- 結束 --->
    
    data_list = []
    
    # yfinance 的 end 日期是不包含的，所以要查詢單日需要設為隔天
    next_day = target_date + timedelta(days=1)
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(stock_list)
    
    for i, code in enumerate(stock_list):
        code = code.strip()
        if not code: continue
        
        ticker_symbol = f"{code}.TW"
        status_text.text(f"正在查詢: {code} ...")
        
        try:
            stock = yf.Ticker(ticker_symbol)
            # 抓取該日資料
            hist = stock.history(start=target_date, end=next_day)
            
            if not hist.empty:
                row = hist.iloc[0]
                
                # 名稱邏輯 (複製上方邏輯)
                name = stock.info.get('longName', code)
                if code in MANUAL_STOCK_NAMES:
                    name = MANUAL_STOCK_NAMES[code]
                elif twstock and code in twstock.codes:
                    name = twstock.codes[code].name
                
                data_list.append({
                    "代號": code,
                    "名稱": name,
                    # 日期格式強制加上 13:30
                    "日期": f"{target_date.strftime('%Y-%m-%d')} 13:30", 
                    "開盤": round(row['Open'], 2),
                    "最高": round(row['High'], 2),
                    "最低": round(row['Low'], 2),
                    # 欄位名稱明確標示為 13:30 收盤價
                    "收盤價 (13:30)": round(row['Close'], 2), 
                    "成交量": int(row['Volume'])
                })
        except Exception:
            pass
        
        progress_bar.progress((i + 1) / total)
        
    status_text.empty()
    progress_bar.empty()
    
    return pd.DataFrame(data_list)

# <--- 用於繪製客製化 Tooltip 的 Altair 繪圖函數 --->
def plot_custom_chart(df):
    """ 
    使用 Altair 繪製互動式圖表 
    1. index 改為「日期」
    2. Tooltip 數值加上 % 並取小數兩位
    """
    # 重設索引，將 Index (日期字串) 轉為一般欄位以便繪圖
    df = df.reset_index()
    date_col = df.columns[0] # 取得日期欄位名稱 (通常是 'index')
    
    # 轉換為 Long Format (長表格)，這是 Altair 喜歡的格式
    df_long = df.melt(id_vars=[date_col], var_name='股票', value_name='漲跌幅')
    
    # 建立一個專門顯示用的欄位 (將數值轉為 "1.23%" 字串)
    df_long['漲跌幅顯示'] = df_long['漲跌幅'].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else "")
    
    # 建立圖表
    chart = alt.Chart(df_long).mark_line(point=True).encode(
        # X 軸: 使用日期欄位，並設定 sort=None 確保照原本順序排列
        x=alt.X(date_col, title='日期', sort=None),
        # Y 軸: 設定標題
        y=alt.Y('漲跌幅', title='漲跌幅 (%)'),
        # 顏色: 依股票區分
        color='股票',
        # Tooltip: 滑鼠移上去顯示的內容
        tooltip=[
            alt.Tooltip(date_col, title='日期'),
            alt.Tooltip('股票', title='股票'),
            alt.Tooltip('漲跌幅顯示', title='漲跌幅') # 使用格式化後的欄位
        ]
    ).interactive() # 允許縮放和平移
    
    # 在 Streamlit 顯示
    st.altair_chart(chart, use_container_width=True)
# <--- 結束 --->

def color_change(val):
    color = 'red' if val > 0 else 'green' if val < 0 else 'black'
    return f'color: {color}'

# --- 主程式 ---

st.title("📈 台股每日收盤紀錄小幫手")

st.sidebar.header("設定")

# <--- 側邊欄狀態顯示與除錯引導 --->
if twstock:
    st.sidebar.success("✅ 中文名稱模組: 已啟用")
else:
    st.sidebar.warning("⚠️ 中文名稱模組: 未偵測到")
    
    if missing_lxml:
        st.sidebar.error("🔴 缺少關鍵套件: lxml")
        st.sidebar.info("請在終端機輸入: `pip install lxml`")
    elif import_error_msg:
         st.sidebar.error(f"錯誤原因: {import_error_msg}")
    
    with st.sidebar.expander("🛠️ 除錯小幫手"):
        st.caption("如果安裝後仍無效，請確認 Python 路徑一致：")
        st.code(sys.executable)
        if missing_lxml:
             st.caption("請嘗試執行以下指令修復：")
             st.code(f"{sys.executable} -m pip install lxml")

default_stocks = "006208, 2317, 2353, 00893"
user_input = st.sidebar.text_area("輸入股票代號 (逗號分隔):", value=default_stocks, height=150)
stock_codes = [x.strip() for x in user_input.split(',') if x.strip()]

# Session State 初始化
if 'stock_data' not in st.session_state:
    st.session_state.stock_data = pd.DataFrame()
if 'valid_tickers' not in st.session_state:
    st.session_state.valid_tickers = []
if 'update_time' not in st.session_state:
    st.session_state.update_time = ""

# 按鈕更新邏輯
if st.sidebar.button("更新股價", type="primary"):
    if not stock_codes:
        st.warning("請輸入代號")
    else:
        tw = pytz.timezone('Asia/Taipei')
        current_time = datetime.now(tw).strftime('%Y-%m-%d %H:%M:%S')
        
        df, valid_tickers = get_stock_data(stock_codes)
        
        st.session_state.stock_data = df
        st.session_state.valid_tickers = valid_tickers
        st.session_state.update_time = current_time

# 顯示邏輯
if not st.session_state.stock_data.empty:
    df = st.session_state.stock_data
    valid_tickers = st.session_state.valid_tickers
    
    st.info(f"資料更新時間: {st.session_state.update_time}")
    
    # 重點關注
    st.subheader("重點關注")
    cols = st.columns(min(3, len(df)))
    for idx, col in enumerate(cols):
        row = df.iloc[idx]
        col.metric(
            label=f"{row['代號']} {row['名稱']}",
            value=f"{row['收盤價']}",
            delta=f"{row['漲跌']} ({row['漲跌幅(%)']}%)",
            delta_color="inverse"
        )

    # 詳細清單
    st.subheader("詳細清單")
    styled_df = df.style.applymap(color_change, subset=['漲跌', '漲跌幅(%)']) \
                        .format("{:.2f}", subset=['收盤價', '漲跌', '漲跌幅(%)']) \
                        .format("{:,}", subset=['成交量']) 
    
    st.dataframe(styled_df, use_container_width=True)
    
    # 下載按鈕
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 下載紀錄",
        data=csv,
        file_name=f'stock_{datetime.now().strftime("%Y%m%d")}.csv',
        mime='text/csv',
    )
    
    # 本週走勢圖
    st.markdown("---")
    st.subheader("📊 本週走勢比較 (每日 09:00 與 13:30)")
    st.caption("顯示每日開盤與收盤的變化趨勢，以週一開盤為基準 (0%)")
    
    with st.spinner('正在繪製本週走勢圖...'):
        chart_data = get_weekly_trend(valid_tickers)
        if not chart_data.empty:
            plot_custom_chart(chart_data)
        else:
            st.info("目前沒有足夠的走勢資料。")
            
    # 本月走勢圖
    st.markdown("---")
    st.subheader("📅 本月走勢比較 (每日收盤)")
    st.caption("顯示本月1號至今的收盤價漲跌幅 (%)，X軸僅顯示日期")
    
    with st.spinner('正在繪製本月走勢圖...'):
        month_chart_data = get_monthly_trend(valid_tickers)
        if not month_chart_data.empty:
            plot_custom_chart(month_chart_data)
        else:
            st.info("目前沒有足夠的本月資料。")
            
    # <--- 新增: 今年每月走勢比較 UI --->
    st.markdown("---")
    st.subheader("📆 今年每月走勢比較 (每月首日與末日)")
    st.caption("抓取今年每個月的「第一天」與「最後一天」收盤價，觀察長期月線趨勢 (0% 為今年年初基準)")
    
    with st.spinner('正在繪製年線趨勢圖...'):
        yearly_chart_data = get_yearly_trend(valid_tickers)
        if not yearly_chart_data.empty:
            plot_custom_chart(yearly_chart_data)
        else:
            st.info("目前沒有足夠的年度資料。")
    # <--- 結束 --->
            
elif st.session_state.update_time:
    st.error("無法取得資料。")

# <--- 新增: 歷史股價查詢區塊 UI (固定顯示在最下方) --->
st.markdown("---")
st.subheader("🔎 指定日期股價查詢")
st.caption("選擇特定日期，查詢上方設定清單中的股價資訊 (顯示當日 13:30 收盤價)")

col1, col2 = st.columns([1, 4])
with col1:
    # 日期選擇器: 預設為今天
    tw = pytz.timezone('Asia/Taipei')
    search_date = st.date_input("請選擇日期", value=datetime.now(tw).date())

with col2:
    st.write("") # 排版用空白 (讓按鈕對齊輸入框)
    st.write("")
    do_search = st.button("查詢該日股價")
    
if do_search:
    if not stock_codes:
         st.warning("請先在側邊欄輸入股票代號")
    else:
        with st.spinner(f"正在抓取 {search_date} 的資料..."):
            history_df = get_history_by_date(stock_codes, search_date)
            
            if not history_df.empty:
                st.success(f"查詢完成！共找到 {len(history_df)} 筆資料。")
                # <--- 修改: 增加價格欄位的格式化 {:.2f} --->
                st.dataframe(
                    history_df.style
                    .format("{:,}", subset=['成交量'])
                    .format("{:.2f}", subset=['開盤', '最高', '最低', '收盤價 (13:30)']),
                    use_container_width=True
                )
                # <--- 修改結束 --->
            else:
                st.warning(f"查無資料：{search_date} 可能是假日、颱風假或尚未開盤。")
# <--- 結束 --->
