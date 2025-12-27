# ==========================================
# 🦁 獅王戰情室 V13.0：GitHub 雲端機器人版
# 功能：介面 100% 復刻 V10.5 + 自動生成網頁
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
    'INITIAL_CAPITAL': 100000,
    'GOAL_PROFIT': 300000,
    'BUDGET': 20000,
    'MAX_STOCKS_DAILY': 5,
    'TARGET_PCT': 0.15,
    'STOP_LOSS_PCT': 0.05,
    'BACKTEST_DAYS': 120,
    'FEE_RATE': 0.001425,
    'FEE_DISCOUNT': 0.2,
    'TAX_RATE': 0.003,
    'MIN_FEE': 1
}

DEFAULT_POOL = [
    "2330.TW", "2317.TW", "2454.TW", "2382.TW", "2376.TW", "3231.TW", 
    "6669.TW", "3035.TW", "3017.TW", "2368.TW", "3037.TW", "2303.TW",
    "2603.TW", "2609.TW", "2615.TW", "1513.TW", "1519.TW", "3711.TW",
    "6235.TW", "6285.TW", "3661.TW", "3443.TW", "5269.TW",
    "2356.TW", "2357.TW", "3008.TW", "3019.TW", "2421.TW"
]

# ------------------------------------------
# 2. 核心引擎
# ------------------------------------------
class LionGithubEngine:
    def __init__(self):
        self.today_str = datetime.date.today().strftime('%Y-%m-%d')
        # GitHub Actions 無狀態，每次都重新計算
        self.ledger = pd.DataFrame(columns=['交易ID', '買入日期', '代號', '買入價', '股數', '手續費(買)', '總成本', '設定停損', '設定目標', '賣出價', '賣出日期', '手續費(賣)', '證交稅', '總收入', '淨損益', '報酬率%', '狀態', '持有天數', '策略', '市場環境', '出場原因'])

    def prepare_data(self, days=150):
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
                    clean_stk[t] = df.dropna()
                except: continue
            return mkt_data, clean_stk
        except: return None, None

    def sense_market(self, mkt_df, date):
        status = "中性"; us_status = "中性"
        if mkt_df is None: return status, us_status
        try:
            idx = mkt_df.index.get_indexer([date], method='nearest')[0]
            curr_date = mkt_df.index[idx]
            if '^TWII' in mkt_df:
                twii = mkt_df['^TWII'].loc[:curr_date]
                c = twii['Close'].iloc[-1]
                ma20 = twii['Close'].rolling(20).mean().iloc[-1]
                ma60 = twii['Close'].rolling(60).mean().iloc[-1]
                if c > ma20 and ma20 > ma60: status = "多頭"
                elif c < ma20 and ma20 < ma60: status = "空頭"
            if '^IXIC' in mkt_df:
                nas = mkt_df['^IXIC'].loc[:curr_date]
                if not nas.empty:
                    if nas['Close'].iloc[-1] > nas['Close'].rolling(20).mean().iloc[-1]: us_status = "美股助漲"
                    else: us_status = "美股偏弱"
        except: pass
        return status, us_status

    def run(self):
        mkt_data, stk_data = self.prepare_data(days=120)
        
        # 若無數據，生成維護頁面
        if mkt_data is None or stk_data is None or not stk_data:
            self.generate_html(pd.DataFrame(), "暫無數據", error=True)
            return

        sim_date = mkt_data.index[-1]
        d_str = sim_date.strftime('%Y-%m-%d')
        tw_env, us_env = self.sense_market(mkt_data, sim_date)
        strict = True if us_env == "美股偏弱" else False

        # 選出今日潛力股
        candidates = []
        for t, df in stk_data.items():
            row = df.iloc[-1]
            if pd.isna(row['MA20']): continue
            s2 = (row['Close'] > row['MA20'] and row['MA20'] > row['MA60'])
            s4 = (row['Volume'] > row['VolMA5'] and row['Close'] > row['MA20'])
            final_strat, score = None, 0
            if "多頭" in tw_env:
                if s4: final_strat, score = "4.主力籌碼", 5
                elif s2: final_strat, score = "2.日檢趨勢", 4
            if strict and score < 5: final_strat = None
            if final_strat: candidates.append({'code': t, 'price': row['Close'], 'strat': final_strat, 'score': score, 'env': f"{tw_env}|{us_env}"})
        
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        new_buys_df = pd.DataFrame()
        for p in candidates[:5]:
            shares = int(CONFIG['BUDGET'] / p['price'])
            if shares == 0: continue
            new_row = {
                '代號': p['code'], '買入價': p['price'], '股數': shares,
                '設定停損': round(p['price']*0.9, 2), '設定目標': round(p['price']*1.15, 2),
                '策略': p['strat'], '市場環境': p['env']
            }
            new_buys_df = pd.concat([new_buys_df, pd.DataFrame([new_row])], ignore_index=True)

        self.generate_html(new_buys_df, d_str)

    def generate_html(self, new_buys_df, date_str, error=False):
        if error:
            html = f"<h1>🦁 獅王戰情室 - 系統維護中</h1><p>暫無數據 (假日或休市)，請稍後再試。</p><p>更新時間: {datetime.datetime.now()}</p>"
        else:
            progress = 0
            current_total = CONFIG['INITIAL_CAPITAL']
            net_profit = 0
            remaining = CONFIG['INITIAL_CAPITAL']
            pnl_color = '#333'

            # 1. 隔日進場訊號 HTML
            buy_cards = ""
            if not new_buys_df.empty:
                for _, r in new_buys_df.iterrows():
                    strat_cls = "t-lion"
                    buy_cards += f"""
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
            else: buy_cards = "<div class='no-data'>今日無新訊號，請空手觀望。</div>"

            # 2. 其他區塊 (雲端版簡化顯示)
            exit_cards = "<div class='no-data'>☁️ 雲端版每日重新掃描，庫存請依券商為準</div>"
            history_cards = "<div class='no-data'>尚無交易紀錄</div>"

            html = f"""
            <!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>獅王 V13.0</title>
            <style>
                body{{font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;background:#f0f2f5;padding:10px;margin:0}}
                .card{{background:white;padding:15px;border-radius:12px;margin-bottom:12px;box-shadow:0 2px 5px rgba(0,0,0,0.05)}}
                .header h2{{margin:0;color:#2c3e50;font-size:1.3em;text-align:center}}
                .progress-wrap{{background:#e9ecef;border-radius:10px;height:10px;margin:10px 0;overflow:hidden}}
                .progress-bar{{background:linear-gradient(90deg, #ff9966, #d93025);height:100%;width:{progress}%}}
                .money-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}}
                .money-item{{background:#f8f9fa;padding:10px;border-radius:8px;text-align:center;border-left:3px solid #ccc}}
                .money-val{{font-size:1.1em;font-weight:bold;display:block;color:#333}}
                .money-lbl{{font-size:0.75em;color:#666}}
                .section-title{{font-size:1em;color:#333;margin:20px 0 8px 0;border-left:4px solid #d93025;padding-left:8px;font-weight:bold}}
                .trade-card{{background:#fff;border-left:5px solid #ccc;padding:12px;margin-bottom:8px;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1)}}
                .trade-header{{display:flex;justify-content:space-between;font-weight:bold;margin-bottom:5px}}
                .trade-detail{{display:flex;justify-content:space-between;font-size:0.85em;color:#444;border-bottom:1px dashed #eee;padding-bottom:6px;margin-bottom:5px}}
                .trade-info{{display:flex;justify-content:space-between;font-size:0.85em;color:#555;margin-bottom:4px}}
                .trade-footer{{display:flex;justify-content:space-between;font-size:0.8em;color:#999;border-top:1px solid #f0f0f0;padding-top:4px;margin-top:4px}}
                .tag{{padding:2px 5px;border-radius:3px;color:white;font-size:0.75em}}
                .t-lion{{background:#d93025}} .t-bear{{background:#f9ab00}} .t-main{{background:#333}}
                .pnl-pos{{color:#d93025;font-weight:bold}} .pnl-neg{{color:#1e8e3e;font-weight:bold}}
                .no-data{{text-align:center;color:#999;padding:10px;font-size:0.9em}}
                .refresh-btn{{display:block;width:100%;padding:10px;background:#2c3e50;color:white;text-align:center;text-decoration:none;border-radius:8px;margin-bottom:15px}}
            </style></head><body>
                <div class="card header">
                    <h2>🦁 獅王戰情 V13.0 (GitHub 雲端版)</h2>
                    <div style="text-align:center;color:#888;font-size:0.8em;">更新時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
                    <div class="progress-wrap"><div class="progress-bar"></div></div>
                    <div style="text-align:right;font-size:0.8em;color:#d93025;font-weight:bold">達成率 {int(progress)}%</div>
                </div>
                <div class="money-grid">
                    <div class="money-item" style="border-color:#2c3e50"><span class="money-val">${int(CONFIG['INITIAL_CAPITAL']):,}</span><span class="money-lbl">🪙 初始本金</span></div>
                    <div class="money-item" style="border-color:#f9ab00"><span class="money-val">${int(current_total):,}</span><span class="money-lbl">💰 當前權益</span></div>
                    <div class="money-item" style="border-color:{pnl_color}"><span class="money-val" style="color:{pnl_color}">${int(net_profit):,}</span><span class="money-lbl">💵 淨損益</span></div>
                    <div class="money-item" style="border-color:#2f855a"><span class="money-val">${int(remaining):,}</span><span class="money-lbl">🔋 可用資金</span></div>
                </div>
                <div class="section-title">🚨 隔日進場訊號 (Buy Signals)</div>{buy_cards}
                <div class="section-title">🛡️ 持倉出場計畫 (Exit Plan)</div>{exit_cards}
                <div class="section-title">📜 近期交易紀錄 (History)</div>{history_cards}
            </body></html>
            """
        
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(html)

if __name__ == "__main__":
    bot = LionGithubEngine()
    bot.run()
