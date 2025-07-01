import backtrader as bt
import sqlite3
import pandas as pd
import os
from datetime import datetime
import tkinter as tk
from tkinter import messagebox
# import sys
# import io

# # 确保标准输出编码为 UTF-8
# sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
# os.environ["PYTHONIOENCODING"] = "utf-8"

DB_FILE = 'daily_data.db'
DAILY_DATA_TABLE = 'daily_data'
STOCK_POOL_CSV = 'stock_pool.csv'
TRADE_LOG_CSV = 'trades.csv'
REPORT_TXT = 'trade_report.txt'

from_date = datetime(2022, 1, 1)

def get_last_trade_date():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"SELECT MAX(trade_date) FROM {DAILY_DATA_TABLE}")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return datetime.strptime(result[0], "%Y%m%d") if result and result[0] else datetime.today()

to_date = get_last_trade_date()

class SQLiteData(bt.feeds.DataBase):
    params = (('dataname', None), ('fromdate', from_date), ('todate', to_date))

    def start(self):
        self.conn = sqlite3.connect(DB_FILE)
        self.cursor = self.conn.cursor()
        self.cursor.execute(f"""
            SELECT trade_date, open, high, low, close, vol
            FROM {DAILY_DATA_TABLE}
            WHERE ts_code = ? AND trade_date BETWEEN ? AND ?
            ORDER BY trade_date ASC
        """, (self.p.dataname, self.p.fromdate.strftime('%Y%m%d'), self.p.todate.strftime('%Y%m%d')))
        self.rows = self.cursor.fetchall()
        self.pos = 0

    def _load(self):
        if self.pos >= len(self.rows):
            return False
        row = self.rows[self.pos]
        self.pos += 1
        dt = datetime.strptime(row[0], '%Y%m%d')
        self.lines.datetime[0] = bt.date2num(dt)
        self.lines.open[0] = float(row[1])
        self.lines.high[0] = float(row[2])
        self.lines.low[0] = float(row[3])
        self.lines.close[0] = float(row[4])
        self.lines.volume[0] = float(row[5])
        self.lines.openinterest[0] = float('nan')
        return True

    def stop(self):
        self.cursor.close()
        self.conn.close()

class MyStrategy(bt.Strategy):
    def __init__(self):
        self.inds = {}
        self.orders = {}
        self.trade_log = []
        for data in self.datas:
            self.inds[data] = {
                'ma20': bt.ind.SMA(data.close, period=20),
                'ma60': bt.ind.SMA(data.close, period=60),
                'ma240': bt.ind.SMA(data.close, period=240),
                'rsi6': bt.ind.RSI(data.close, period=6),
                'rsi13': bt.ind.RSI(data.close, period=13),
                'vol_ma3': bt.ind.SMA(data.volume, period=3),
                'vol_ma8': bt.ind.SMA(data.volume, period=8)
            }
            self.orders[data] = None

    def next(self):
        p = min(len(self.datas), 5)
        m = len([d for d in self.datas if self.getposition(d).size > 0])
        available_cash = self.broker.get_cash()

        for data in self.datas:
            i = self.inds[data]
            pos = self.getposition(data)
            if len(data) < 240 or self.orders[data]:
                continue

            if pos and data.close[0] < i['ma20'][0]:
                self.orders[data] = self.close(data)
            elif not pos and m < p:
                conds = [
                    data.close[0] > i['ma240'][0],
                    i['ma240'][0] > i['ma240'][-1],
                    i['ma60'][0] > i['ma60'][-1] or i['ma20'][0] > i['ma20'][-1],
                    i['rsi6'][0] > 70 and i['rsi13'][0] > 50,
                    i['vol_ma3'][0] > i['vol_ma8'][0] and i['vol_ma3'][0] > i['vol_ma3'][-1] and i['vol_ma8'][0] > i['vol_ma8'][-1]
                ]
                if all(conds):
                    allocation = 1 / (p - m)
                    amount = available_cash * allocation
                    size = int((amount / data.open[1]) // 100 * 100)
                    if size > 0:
                        self.orders[data] = self.buy(data=data, size=size)

    def notify_order(self, order):
        if order.status in [order.Completed]:
            dt = bt.num2date(order.executed.dt).strftime('%Y-%m-%d')
            action = '买入' if order.isbuy() else '卖出'
            self.trade_log.append({
                '日期': dt,
                '股票': order.data._name,
                '方向': action,
                '价格': round(order.executed.price, 2),
                '数量': int(order.executed.size)
            })
            self.orders[order.data] = None
        elif order.status in [order.Canceled, order.Rejected]:
            self.orders[order.data] = None

def run_backtest(selected_codes):
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(300000.0)
    cerebro.broker.setcommission(commission=0.0003)

    for code in selected_codes:
        data = SQLiteData(dataname=code)
        cerebro.adddata(data, name=code)

    strat = cerebro.addstrategy(MyStrategy)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')

    print("开始回测...")
    results = cerebro.run()
    strat = results[0]

    pd.DataFrame(strat.trade_log).to_csv(TRADE_LOG_CSV, index=False)

    final_value = cerebro.broker.getvalue()
    generate_date = datetime.today().strftime('%Y-%m-%d')
    report = {
        '生成日期': generate_date,
        '初始资金': '300000 元',
        '期末资产': f"{final_value:.2f} 元",
        '收益': f"{final_value - 300000:.2f} 元",
        '年化收益率': '示意，需根据周期计算',
        '最大回撤': f"{strat.analyzers.drawdown.get_analysis()['max']['drawdown']:.2f}%",
        '夏普比率': str(strat.analyzers.sharpe.get_analysis()),
        '交易笔数': f"{len(strat.trade_log)}"
    }
    with open(REPORT_TXT, 'w', encoding='utf-8') as f:
        f.write("=== 回测交易报告 ===\n")
        for k, v in report.items():
            f.write(f"{k}：{v}\n")
    messagebox.showinfo("回测完成", f"已生成交易记录和报告。\n总资产：{final_value:.2f} 元")

def launch_gui():
    df = pd.read_csv(STOCK_POOL_CSV)
    codes = df['ts_code'].dropna().tolist()

    root = tk.Tk()
    root.title("股票选择")
    selections = {}

    def toggle(code, button):
        if code in selections:
            button.config(bg="SystemButtonFace")
            del selections[code]
        else:
            button.config(bg="lightgreen")
            selections[code] = True

    def on_confirm():
        if not selections:
            messagebox.showwarning("未选择", "请至少选择一支股票")
        else:
            root.destroy()
            run_backtest(list(selections.keys()))

    for idx, code in enumerate(codes):
        btn = tk.Button(root, text=code, width=12)
        btn.config(command=lambda c=code, b=btn: toggle(c, b))
        btn.grid(row=idx//5, column=idx%5, padx=5, pady=5)

    confirm_btn = tk.Button(root, text="确认回测", command=on_confirm, bg="skyblue")
    confirm_btn.grid(row=(len(codes)//5)+1, column=0, columnspan=5, pady=10)

    root.mainloop()

if __name__ == '__main__':
    launch_gui()
