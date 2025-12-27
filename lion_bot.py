# ==========================================
# 🦁 獅王戰情室 V10.5：GitHub 完美移植版
# 功能：介面與邏輯 100% 復刻 Colab 版本 + 自動存檔記憶
# ==========================================
import os
import datetime
import pandas as pd
import yfinance as yf
import pandas_ta as ta

# ------------------------------------------
# 1. 系統設定 (源自 V10.5)
# ------------------------------------------
CONFIG = {
    'INITIAL_CAPITAL': 100000, # 初始本金
    'GOAL_PROFIT': 300000,     # 目標獲利
    'BUDGET': 20000,           # 單檔預算
    'MAX_STOCKS_DAILY': 5,     # 最大持倉
    'TARGET_PCT': 0.15,        # 停利 +15%
    'STOP_LOSS_PCT': 0.05,     # 停損 -5%
    'BACKTEST_DAYS': 90,       # 回測/掃描天數
    'FEE_RATE': 0.001425,
    'FEE_DISCOUNT': 0.2,
    'TAX_RATE': 0.003,
    'MIN_FEE': 1
}

# 您的選股清單
DEFAULT_POOL = [
    "2330.TW", "2317.TW", "2454.TW", "2382.TW", "2376.TW", "3231.TW", 
    "6669.TW", "3035.TW", "3017.TW", "2368.TW", "3037.TW", "2303.TW",
    "2603.TW", "2609.TW", "2615.TW", "1513.TW", "1519.TW", "3711.TW",
    "6235.TW", "6285.TW", "3661.TW", "3443.TW", "5269.TW",
    "2356.TW", "2357.TW", "3008.TW", "3019.TW", "2421.TW"
]

class LionGithubEngine:
    def __init__(self):
        self.today_str = datetime.date.today().strftime('%Y-%m-%d')
        # 改為固定檔名，方便 GitHub 追蹤
        self.ledger_file = 'Lion_Ledger.csv' 
        self.ledger = self.load_ledger()

    def load_ledger(self):
        # 嘗試讀取 GitHub 上的舊帳本
        if os.path.exists(self.ledger_file):
            print("📂 讀取歷史帳本...")
            try:
                return pd.read_csv(self.ledger_file)
            except:
                pass
        print("✨ 建立新帳本...")
        return pd.DataFrame(columns=[
            '交易ID', '買入日期', '代號', '買入價', '股數',
            '手續費(買)', '總成本', '設定停損', '設定目標',
            '賣出價', '賣出日期', '手續費(賣)', '證交稅', '總收入',
            '淨損益', '報酬率%', '狀態', '持有天數',
            '策略', '市場環境', '出場原因'
        ])

    def save_ledger(self):
        self.ledger.to_csv(self.ledger_file, index=False, encoding='utf-8-sig')
        print("💾 帳本已儲存")

    def calc_cost(self, amount, is_sell=False):
        fee = max(int(amount * CONFIG['FEE_RATE'] * CONFIG['FEE_DISCOUNT']), CONFIG['MIN_FEE'])
        tax = int(amount * CONFIG['TAX_RATE']) if is_sell else 0
        return fee, tax

    def prepare_data(self, days=120):
        start = datetime.date.today() - datetime.timedelta(days=days)
        tickers = ["^TWII", "^VIX", "^IXIC", "^SOX"]
        try:
            mkt_data = yf.download(tickers, start=start, progress=False, group_by='ticker', auto_adjust=True)
            stk_data = yf.download(DEFAULT_POOL, start=start, progress=False, group_by='ticker', auto_adjust=True)
            if mkt_data.empty or stk_data.empty: return None, None
            clean_stk = {}
            for t in DEFAULT_POOL:
                try:
                    df = stk_data[t].copy()
                    if df.empty or len(df) < 60: continue 
                    df['MA5'] = ta.sma(df['Close'], 5)
                    df['MA20'] = ta.sma(df['Close'], 20)
                    df['MA60'] = ta.sma(df['Close'], 60)
                    df['VolMA5'] = ta.sma(df['Volume'], 5)
                    df['RSI'] = ta.rsi(df['Close'], 14)
                    df['OBV'] = ta.obv(df['Close'], df['Volume'])
                    clean_stk[t] = df.dropna()
                except: continue
            return mkt_data, clean_stk
        except: return None, None

    def sense_market(self, mkt_df, date):
        status = "中性"; us_status = "中性"
        if mkt_df is None: return status, us_status
        try:
            # 修正：處理 timezone 問題
            if mkt_df.index.tz is None: mkt_df.index = mkt_df.index.tz_localize(None)
            
            # 使用 asof 尋找最接近的日期 (解決 GitHub Action 執行時區可能導致的數據落差)
            idx = mkt_df.index.get_indexer([date], method='nearest')[0]
            curr_date = mkt_df.index[idx]
            
            if '^TWII' in mkt_df:
                twii = mkt_df['^TWII'].loc[:curr_date]
                vix = mkt_df['^VIX'].loc[:curr_date]
                if not twii.empty:
                    c = twii['Close'].iloc[-1]
                    ma20 = twii['Close'].rolling(20).mean().iloc[-1]
                    ma60 = twii['Close'].rolling(60).mean().iloc[-1]
                    vix_val = vix['Close'].iloc[-1] if not vix.empty else 20
                    if vix_val > 30: status = "恐慌"
                    elif c > ma20 and ma20 > ma60: status = "多頭"
                    elif c < ma20 and ma20 < ma60: status = "空頭"
            if '^IXIC' in mkt_df:
                nas = mkt_df['^IXIC'].loc[:curr_date]
                if not nas.empty:
                    nas_c = nas['Close'].iloc[-1]
                    nas_ma20 = nas['Close'].rolling(20).mean().iloc[-1]
                    if nas_c > nas_ma20: us_status = "美股助漲"
                    else: us_status = "美股偏弱"
        except: pass
        return status, us_status

    def run(self):
        mkt_data, stk_data = self.prepare_data(days=120)
        
        # 若抓不到資料 (例如假日或 API 異常)，生成錯誤頁面但保留舊帳本
        if mkt_data is None or stk_data is None or not stk_data:
            print("⚠️ 無法取得市場數據")
            self.generate_report(pd.DataFrame(), "⚠️ 暫無數據 (假日或休市)")
            return

        sim_date = mkt_data.index[-1]
        d_str = sim_date.strftime('%Y-%m-%d')
        tw_env, us_env = self.sense_market(mkt_data, sim_date)
        strict = True if us_env == "美股偏弱" else False

        # Phase A: 庫存管理 (檢查是否需賣出)
        open_pos = self.ledger[self.ledger['狀態'] == '持倉']
        for idx, row in open_pos.iterrows():
            t = row['代號']
            if t not in stk_data: continue
            bar = stk_data[t].iloc[-1]
            reason, price = None, 0
            
            if bar['Low'] <= row['設定停損']: reason, price = "❌ 觸價停損", row['設定停損']
            elif bar['High'] >= row['設定目標']: reason, price = "✅ 獲利達標", row['設定目標']
            elif "日檢" in row['策略'] and bar['Close'] < bar['MA20']: reason, price = "⚠️ 趨勢破線", bar['Close']
            
            if reason:
                rev = price * row['股數']
                fee, tax = self.calc_cost(rev, True)
                pnl = rev - fee - tax - row['總成本']
                roi = (pnl / row['總成本']) * 100
                
                self.ledger.at[idx, '狀態'] = '已平倉'
                self.ledger.at[idx, '賣出日期'] = d_str
                self.ledger.at[idx, '賣出價'] = round(price, 2)
                self.ledger.at[idx, '淨損益'] = int(pnl)
                self.ledger.at[idx, '報酬率%'] = round(roi, 2)
                self.ledger.at[idx, '出場原因'] = reason

        # Phase B: 每日選股
        current_holdings = len(self.ledger[self.ledger['狀態']=='持倉'])
        candidates = []
        for t, df in stk_data.items():
            row = df.iloc[-1]
            # 確保 MA 有值
            if pd.isna(row['MA20']) or pd.isna(row['MA60']): continue
            
            s2 = (row['Close'] > row['MA20'] and row['MA20'] > row['MA60'])
            s3 = (row['RSI'] < 30)
            s4 = (row['Volume'] > row['VolMA5'] and row['Close'] > row['MA20'])
            final_strat, score = None, 0
            
            if "多頭" in tw_env:
                if s4: final_strat, score = "4.主力籌碼", 5
                elif s2: final_strat, score = "2.日檢趨勢", 4
            elif "恐慌" in tw_env:
                if s3: final_strat, score = "3.熊市抄底", 5
            
            if strict and score < 5: final_strat = None
            if final_strat: candidates.append({'code': t, 'price': row['Close'], 'strat': final_strat, 'score': score, 'env': f"{tw_env}|{us_env}"})
        
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        new_buys_df = pd.DataFrame()
        for p in candidates[:CONFIG['MAX_STOCKS_DAILY']]:
            if current_holdings >= CONFIG['MAX_STOCKS_DAILY']: break
            if not self.ledger[(self.ledger['狀態']=='持倉') & (self.ledger['代號']==p['code'])].empty: continue
            
            price = p['price']
            shares = int(CONFIG['BUDGET'] / price)
            if shares == 0: continue
            
            cost = shares * price
            fee, _ = self.calc_cost(cost, False)
            total_cost = cost + fee
            sl = max(p.get('ma20', 0) if 'ma20' in p else price*0.95, price * (1 - CONFIG['STOP_LOSS_PCT']))
            tp = price * (1 + CONFIG['TARGET_PCT'])
            
            new_row = {
                '交易ID': f"{d_str}_{p['code']}",
                '買入日期': d_str, '代號': p['code'], '買入價': price, '股數': shares,
                '手續費(買)': fee, '總成本': int(total_cost), 
                '設定停損': round(sl, 2), '設定目標': round(tp, 2),
                '狀態': '持倉', '策略': p['strat'], '市場環境': p['env'], 
                '賣出價':0, '賣出日期':'-', '淨損益':0, '報酬率%':0, '出場原因':'-'
            }
            new_row_df = pd.DataFrame([new_row])
            self.ledger = pd.concat([self.ledger, new_row_df], ignore_index=True)
            new_buys_df = pd.concat([new_buys_df, new_row_df], ignore_index=True)
            current_holdings += 1

        self.save_ledger()
        self.generate_report(new_buys_df, d_str)

    def generate_report(self, new_buys_df, date_str):
        # 數據準備 (V10.5 邏輯)
        closed = self.ledger[self.ledger['狀態'] == '已平倉']
        open_pos = self.ledger[self.ledger['狀態'] == '持倉']
        
        net_profit = closed['淨損益'].sum() if not closed.empty else 0
        invested = open_pos['總成本'].sum() if not open_pos.empty else 0
        current_total = CONFIG['INITIAL_CAPITAL'] + net_profit
        remaining = current_total - invested
        progress = min(100, max(0, (net_profit / CONFIG['GOAL_PROFIT']) * 100))
        pnl_color = '#d93025' if net_profit > 0 else '#1e8e3e'

        # 1. 隔日進場訊號 HTML
        buy_cards = ""
        if not new_buys_df.empty:
            for _, r in new_buys_df.iterrows():
                strat_cls = "t-lion" if "日檢" in r['策略'] else ("t-bear" if "熊市" in r['策略'] else "t-main")
                buy_cards += f"""
                <div class="trade-card" style="border-left-color: #2c3e50;">
                    <div class="trade-header">
                        <span>{r['代號']} <span class="tag {strat_cls}">{r['策略']}</span></span>
                        <span class="pnl-pos">進場</span>
                    </div>
                    <div class="trade-detail">
                        <span>${int(r['買入價']):,} x <b>{int(r['股數'])}</b>股</span>
                    </div>
                    <div class="trade-footer">損: {r['設定停損']} | 利: {r['設定目標']}</div>
                </div>"""
        else: buy_cards = "<div class='no-data'>今日無新訊號</div>"

        # 2. 持倉監控 HTML
        hold_cards = ""
        if not open_pos.empty:
            for _, r in open_pos.iterrows():
                hold_cards += f"""
                <div class="trade-card" style="border-left-color: #f9ab00;">
                    <div class="trade-header">
                        <span>{r['代號']}</span>
                        <span style="color:#f9ab00;">持倉</span>
                    </div>
                    <div class="trade-detail">
                        <span>成本: ${int(r['總成本']):,}</span>
                    </div>
                    <div class="trade-footer">🛑 {r['設定停損']} | 🎯 {r['設定目標']}</div>
                </div>"""
        else: hold_cards = "<div class='no-data'>目前空手</div>"

        # 3. 完整頁面 HTML (V10.5 樣式)
        html = f"""
        <!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>獅王 V10.5</title>
        <style>
            body{{font-family:sans-serif;background:#f0f2f5;padding:10px;margin:0}}
            .card{{background:white;padding:15px;border-radius:12px;margin-bottom:12px;box-shadow:0 2px 5px rgba(0,0,0,0.05)}}
            .money-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}}
            .money-item{{background:#f8f9fa;padding:10px;border-radius:8px;text-align:center;border-left:3px solid #ccc}}
            .money-val{{font-size:1.1em;font-weight:bold;display:block;color:#333}}
            .money-lbl{{font-size:0.75em;color:#666}}
            .section-title{{font-size:1em;color:#333;margin:20px 0 8px 0;border-left:4px solid #d93025;padding-left:8px;font-weight:bold}}
            .trade-card{{background:#fff;border-left:5px solid #2c3e50;padding:12px;margin-bottom:8px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1)}}
            .trade-header{{display:flex;justify-content:space-between;font-weight:bold;margin-bottom:5px}}
            .trade-detail{{font-size:0.9em;color:#555;margin-bottom:5px}}
            .trade-footer{{font-size:0.8em;color:#999;border-top:1px solid #f0f0f0;padding-top:5px}}
            .pnl-pos{{color:#d93025;font-weight:bold}} .no-data{{text-align:center;color:#999;padding:10px}}
            .tag{{padding:2px 5px;border-radius:3px;color:white;font-size:0.75em;margin-left:5px}}
            .t-lion{{background:#d93025}} .t-bear{{background:#f9ab00}} .t-main{{background:#333}}
            .refresh-btn{{display:block;width:100%;padding:10px;background:#2c3e50;color:white;text-align:center;text-decoration:none;border-radius:8px;margin-bottom:15px}}
        </style></head><body>
            <div class="card" style="text-align:center">
                <h2 style="margin:0;color:#2c3e50">🦁 獅王戰情 V10.5 (GitHub版)</h2>
                <div style="font-size:0.8em;color:#888;margin-bottom:5px">{date_str}</div>
                <div style="background:#eee;height:10px;border-radius:5px;margin:10px 0;overflow:hidden"><div style="background:#d93025;width:{progress}%;height:100%"></div></div>
                <div style="text-align:right;color:#d93025;font-size:0.8em;font-weight:bold">目標 30 萬: 達成 {int(progress)}%</div>
            </div>
            <div class="money-grid">
                <div class="money-item" style="border-color:#f9ab00"><span class="money-val">${int(current_total):,}</span><span class="money-lbl">💰 總權益</span></div>
                <div class="money-item" style="border-color:{pnl_color}"><span class="money-val" style="color:{pnl_color}">${int(net_profit):,}</span><span class="money-lbl">💵 淨損益</span></div>
                <div class="money-item"><span class="money-val">${int(invested):,}</span><span class="money-lbl">📉 已投入</span></div>
                <div class="money-item" style="border-color:#2f855a"><span class="money-val">${int(remaining):,}</span><span class="money-lbl">🔋 可用資金</span></div>
            </div>
            <div class="section-title">🚨 隔日進場訊號</div>{buy_cards}
            <div class="section-title">🛡️ 持倉監控</div>{hold_cards}
        </body></html>
        """
        
        # 儲存網頁，GitHub Pages 會讀取這個檔案
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(html)

if __name__ == "__main__":
    bot = LionGithubEngine()
    bot.run()
