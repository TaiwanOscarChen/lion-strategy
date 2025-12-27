# ==========================================
# 🦁 獅王戰情室 V13.1：GitHub 雲端永動機 (V9.1 介面完美復刻版)
# 功能：自動存檔記憶 + 100% V9.1 介面 + 每日自動執行
# ==========================================
import os
import datetime
import pandas as pd
import yfinance as yf
import pandas_ta as ta

# ------------------------------------------
# 1. 系統設定
# ------------------------------------------
CONFIG = {
    'INITIAL_CAPITAL': 100000, # 初始本金
    'GOAL_PROFIT': 300000,     # 目標獲利
    'BUDGET': 20000,           # 單檔預算
    'MAX_STOCKS_DAILY': 5,     # 最大持倉
    'TARGET_PCT': 0.15,        # 停利 +15%
    'STOP_LOSS_PCT': 0.05,     # 停損 -5%
    'BACKTEST_DAYS': 90,       # 回測/掃描天數
    'FEE_RATE': 0.001425, 'FEE_DISCOUNT': 0.2, 'TAX_RATE': 0.003, 'MIN_FEE': 1
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
        self.ledger_file = 'Lion_Ledger.csv' # 直接存在當前目錄
        self.ledger = self.load_ledger()

    def load_ledger(self):
        # 嘗試讀取 GitHub 上的舊帳本，讓機器人有記憶
        if os.path.exists(self.ledger_file):
            print("📂 讀取歷史帳本...")
            return pd.read_csv(self.ledger_file)
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
            # 修正：處理 timezone 問題，確保 index 格式一致
            if mkt_df.index.tz is None: mkt_df.index = mkt_df.index.tz_localize(None)
            
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
                    if vix_val > 30: status = "恐慌 (Bear)"
                    elif c > ma20 and ma20 > ma60: status = "多頭 (Bull)"
                    elif c < ma20 and ma20 < ma60: status = "空頭 (Short)"
                    else: status = "震盪 (Flat)"
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
        if mkt_data is None or stk_data is None or not stk_data:
            self.generate_report(None, None, "資料下載失敗")
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
            if pd.isna(row['MA20']): continue
            s2 = (row['Close'] > row['MA20'] and row['MA20'] > row['MA60'])
            s3 = (row['RSI'] < 30)
            s4 = (row['Volume'] > row['VolMA5'] and row['Close'] > row['MA20'])
            final_strat, score = None, 0
            
            if "多頭" in tw_env:
                if s4: final_strat, score = "4.主力籌碼", 5
                elif s2: final_strat, score = "2.日檢趨勢", 4
            elif "恐慌" in tw_env or "空頭" in tw_env:
                if s3: final_strat, score = "3.熊市抄底", 5
            else: # 震盪
                if s3: final_strat, score = "3.熊市抄底", 4
                elif s4: final_strat, score = "4.主力籌碼", 3

            if strict and score < 5: final_strat = None
            if final_strat: candidates.append({'code': t, 'price': row['Close'], 'strat': final_strat, 'score': score, 'env': f"{tw_env}|{us_env}"})
        
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        # 只取前幾名且尚未持有的
        new_buys_df = pd.DataFrame()
        for p in candidates[:CONFIG['MAX_STOCKS_DAILY']]:
            if current_holdings >= CONFIG['MAX_STOCKS_DAILY']: break
            # 檢查是否已持倉或今日已買
            if not self.ledger[(self.ledger['狀態']=='持倉') & (self.ledger['代號']==p['code'])].empty: continue
            
            shares = int(CONFIG['BUDGET'] / p['price'])
            if shares == 0: continue
            
            cost = shares * p['price']
            fee, _ = self.calc_cost(cost, False)
            total_cost = cost + fee
            sl = max(p.get('ma20', 0), p['price'] * (1 - CONFIG['STOP_LOSS_PCT']))
            tp = p['price'] * (1 + CONFIG['TARGET_PCT'])
            
            new_row = {
                '交易ID': f"{d_str}_{p['code']}",
                '買入日期': d_str, '代號': p['code'], '買入價': p['price'], '股數': shares,
                '總成本': int(total_cost), '設定停損': round(sl, 2), '設定目標': round(tp, 2),
                '狀態': '持倉', '策略': p['strat'], '市場環境': p['env'], 
                '賣出價':0, '賣出日期':'-', '淨損益':0, '報酬率%':0, '出場原因':'-'
            }
            # 存入帳本
            new_row_df = pd.DataFrame([new_row])
            self.ledger = pd.concat([self.ledger, new_row_df], ignore_index=True)
            new_buys_df = pd.concat([new_buys_df, new_row_df], ignore_index=True)
            current_holdings += 1

        self.save_ledger()
        self.generate_report(new_buys_df, d_str)

    def generate_report(self, new_buys_df, date_str, error_msg=None):
        if error_msg:
            html = f"<h1>獅王戰情室 - 系統訊息</h1><p>{error_msg}</p>"
            with open('index.html', 'w', encoding='utf-8') as f: f.write(html)
            return

        # V9.1 原始介面邏輯
        closed = self.ledger[self.ledger['狀態'] == '已平倉']
        open_pos = self.ledger[self.ledger['狀態'] == '持倉']
        
        net_profit = closed['淨損益'].sum() if not closed.empty else 0
        invested = open_pos['總成本'].sum() if not open_pos.empty else 0
        current_total = CONFIG['INITIAL_CAPITAL'] + net_profit
        remaining = current_total - invested
        progress = min(100, max(0, (net_profit / CONFIG['GOAL_PROFIT']) * 100))
        pnl_color = '#d93025' if net_profit > 0 else '#1e8e3e'

        # 生成 HTML 片段 (完全依照 V9.1 CSS)
        def get_buy_cards(df):
            if df.empty: return "<div class='no-data'>今日無新訊號，請觀察庫存或空手觀望。</div>"
            cards = ""
            for _, r in df.iterrows():
                strat_cls = "t-lion" if "日檢" in r['策略'] else ("t-bear" if "熊市" in r['策略'] else "t-main")
                cards += f"""
                <div class="trade-card" style="border-left-color: #2c3e50;">
                    <div class="trade-header">
                        <span>{r['代號']} <span class="tag {strat_cls}">{r['策略']}</span></span>
                        <span style="color:#d93025; font-weight:bold;">進場</span>
                    </div>
                    <div class="trade-detail">
                        <span>參考價: ${r['買入價']}</span>
                        <span>建議股數: <b>{r['股數']}</b> 股</span>
                    </div>
                    <div class="trade-info"><span>環境: {r['市場環境']}</span></div>
                    <div class="trade-footer">🛑 停損: {r['設定停損']} | 🎯 停利: {r['設定目標']}</div>
                </div>"""
            return cards

        def get_exit_cards(df):
            if df.empty: return "<div class='no-data'>目前無庫存。</div>"
            cards = ""
            for _, r in df.iterrows():
                cards += f"""
                <div class="trade-card" style="border-left-color: #f9ab00;">
                    <div class="trade-header">
                        <span>{r['代號']}</span>
                        <span style="color:#f9ab00;">持倉中</span>
                    </div>
                    <div class="trade-detail">
                        <span>成本: ${int(r['總成本']):,} ({r['股數']}股)</span>
                    </div>
                    <div class="trade-footer" style="color:#d93025; font-weight:bold;">
                        🛑 停損: {r['設定停損']} | 🎯 停利: {r['設定目標']}
                    </div>
                </div>"""
            return cards

        def get_history_cards(df):
            if df.empty: return "<div class='no-data'>尚無交易紀錄</div>"
            cards = ""
            for _, r in df.iterrows():
                pnl = int(r['淨損益'])
                pnl_cls = "pnl-pos" if pnl > 0 else "pnl-neg"
                pnl_txt = f"+{pnl}" if pnl > 0 else f"{pnl}"
                strat_cls = "t-lion" if "日檢" in r['策略'] else ("t-bear" if "熊市" in r['策略'] else "t-main")
                cards += f"""
                <div class="trade-card" style="border-left-color: {'#d93025' if pnl>0 else '#1e8e3e'}">
                    <div class="trade-header">
                        <span>{r['代號']} <span class="tag {strat_cls}">{r['策略']}</span></span>
                        <span class="{pnl_cls}">{pnl_txt}</span>
                    </div>
                    <div class="trade-detail">
                        <span>${int(r['買入價']):,} x {int(r['股數'])}股</span>
                        <span class="{pnl_cls}">ROI: {r['報酬率%']}%</span>
                    </div>
                    <div class="trade-info"><span>成本: ${int(r['總成本']):,}</span><span>{r['出場原因']}</span></div>
                    <div class="trade-footer"><span>賣出: {r['賣出日期']}</span></div>
                </div>"""
            return cards

        strat_html = "<div class='no-data'>尚無資料</div>"
        if not closed.empty:
            perf = closed.groupby('策略').agg(
                交易次數=('淨損益','count'), 總獲利=('淨損益','sum'),
                平均獲利=('淨損益', lambda x: int(x.mean())),
                勝率=('淨損益', lambda x: (x>0).sum()/len(x)*100)
            ).sort_values('總獲利', ascending=False)
            strat_html = perf.to_html(classes='data-table', float_format="%.1f")

        html = f"""
        <!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>獅王 V9.1 戰略儀表板</title>
        <style>
            body{{font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;background:#f0f2f5;padding:10px;margin:0}}
            .card{{background:white;padding:15px;border-radius:12px;margin-bottom:12px;box-shadow:0 2px 5px rgba(0,0,0,0.05)}}
            .header h2{{margin:0;color:#2c3e50;font-size:1.3em;text-align:center}}
            .date{{color:#888;font-size:0.8em;text-align:center;margin-bottom:10px}}
            .progress-wrap{{background:#e9ecef;border-radius:10px;height:10px;margin:10px 0;overflow:hidden}}
            .progress-bar{{background:linear-gradient(90deg, #ff9966, #d93025);height:100%;width:{progress}%}}
            .money-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}}
            .money-item{{background:#f8f9fa;padding:10px;border-radius:8px;text-align:center;border-left:3px solid #ccc}}
            .money-val{{font-size:1.1em;font-weight:bold;display:block;color:#333}}
            .money-lbl{{font-size:0.75em;color:#666}}
            .section-title{{font-size:1em;color:#333;margin:20px 0 8px 0;border-left:4px solid #d93025;padding-left:8px;font-weight:bold}}
            .trade-card{{background:#fff;border-left:5px solid #ccc;padding:12px;margin-bottom:8px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1)}}
            .trade-header{{display:flex;justify-content:space-between;font-weight:bold;margin-bottom:6px;font-size:1em}}
            .trade-detail{{display:flex;justify-content:space-between;font-size:0.85em;color:#444;border-bottom:1px dashed #eee;padding-bottom:6px;margin-bottom:6px}}
            .trade-info{{display:flex;justify-content:space-between;font-size:0.85em;color:#555;margin-bottom:4px}}
            .trade-footer{{display:flex;justify-content:space-between;font-size:0.8em;color:#999;border-top:1px solid #f0f0f0;padding-top:4px;margin-top:4px}}
            .tag{{padding:2px 5px;border-radius:3px;color:white;font-size:0.75em}}
            .t-lion{{background:#d93025}} .t-bear{{background:#f9ab00}} .t-main{{background:#333}}
            .pnl-pos{{color:#d93025;font-weight:bold}} .pnl-neg{{color:#1e8e3e;font-weight:bold}}
            .no-data{{text-align:center;color:#999;padding:10px;font-size:0.9em}}
            .data-table{{width:100%;border-collapse:collapse;font-size:0.85em}}
            .data-table th{{background:#2c3e50;color:white;padding:6px;text-align:center}}
            .data-table td{{border-bottom:1px solid #eee;padding:6px;text-align:center}}
        </style></head><body>
            <div class="card header">
                <h2>🦁 獅王戰情 V9.1 (30萬目標)</h2>
                <div class="date">{date_str} (GitHub 雲端版)</div>
                <div class="progress-wrap"><div class="progress-bar"></div></div>
                <div style="text-align:right;font-size:0.8em;color:#d93025;font-weight:bold">達成率 {int(progress)}%</div>
            </div>
            <div class="money-grid">
                <div class="money-item" style="border-color:#2c3e50"><span class="money-val">${int(CONFIG['INITIAL_CAPITAL']):,}</span><span class="money-lbl">🪙 初始本金</span></div>
                <div class="money-item" style="border-color:#f9ab00"><span class="money-val">${int(current_total):,}</span><span class="money-lbl">💰 當前權益</span></div>
                <div class="money-item" style="border-color:{pnl_color}"><span class="money-val" style="color:{pnl_color}">${int(net_profit):,}</span><span class="money-lbl">💵 淨損益</span></div>
                <div class="money-item" style="border-color:#2f855a"><span class="money-val">${int(remaining):,}</span><span class="money-lbl">🔋 可用資金</span></div>
            </div>
            <div class="section-title">🚨 隔日進場訊號 (Buy Signals)</div>{get_buy_cards(new_buys_df)}
            <div class="section-title">🛡️ 持倉出場計畫 (Exit Plan)</div>{get_exit_cards(open_pos)}
            <div class="section-title">📊 策略獲利矩陣 (Profit Matrix)</div>
            <div class="card" style="overflow-x:auto">{strat_html}</div>
            <div class="section-title">📜 近期交易紀錄 (History)</div>{get_history_cards(closed.tail(10))}
        </body></html>
        """
        with open('index.html', 'w', encoding='utf-8') as f: f.write(html)

if __name__ == "__main__":
    bot = LionGithubEngine()
    bot.run()
