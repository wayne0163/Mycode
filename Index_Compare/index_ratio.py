# 指数比值分析系统（使用数据库 + Tkinter GUI + 可变均线周期）

import tushare as ts
import pandas as pd
import sqlite3
import os
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

# 配置 tushare
TOKEN = 'YOUR_TUSHARE_TOKEN_HERE'  # <<< 替换为你的 token
ts.set_token(TOKEN)
pro = ts.pro_api()

# 配置参数
DB_NAME = 'index_data.db'
TABLE_NAME = 'index'
START_DATE = '20240101'
TODAY = datetime.today().strftime('%Y%m%d')

# 常用指数代码列表
INDEX_DICT = {
    '上证综指': '000001.SH',
    '沪深300': '000300.SH',
    '中证500': '000905.SH',
    '中证1000': '000852.SH',
    '中证2000': '000933.SH',
    '创业板指': '399006.SZ',
    '科创50': '000688.SH'
}

# 创建数据库表结构
def create_index_table():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            ts_code TEXT,
            trade_date TEXT,
            close REAL,
            PRIMARY KEY (ts_code, trade_date)
        )
    ''')
    conn.commit()
    conn.close()

# 下载并更新指数数据
def update_index_data():
    create_index_table()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    for name, ts_code in INDEX_DICT.items():
        latest = cursor.execute(f"SELECT MAX(trade_date) FROM {TABLE_NAME} WHERE ts_code = ?", (ts_code,)).fetchone()[0]
        start = latest if latest else START_DATE
        df = pro.index_daily(ts_code=ts_code, start_date=start, end_date=TODAY)
        if df.empty:
            continue
        df = df[['ts_code', 'trade_date', 'close']]
        df.to_sql(TABLE_NAME, conn, if_exists='append', index=False, method='multi')
    conn.close()
    messagebox.showinfo("更新完成", "指数数据已更新到数据库。")

# 从数据库中读取指数数据
def load_index_data(ts_code):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query(f"SELECT trade_date, close FROM {TABLE_NAME} WHERE ts_code = ? ORDER BY trade_date", conn, params=(ts_code,))
    conn.close()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df.set_index('trade_date', inplace=True)
    return df

# 绘图函数
def plot_ratio(numerator_code, denominator_code, ma_days):
    df_n = load_index_data(numerator_code)
    df_d = load_index_data(denominator_code)
    df = pd.DataFrame()
    df['n'] = df_n['close']
    df['d'] = df_d['close']
    df.dropna(inplace=True)

    # 比值及均线
    df['ratio'] = df['n'] / df['d']
    df['ma'] = df['ratio'].rolling(window=ma_days).mean()
    df['位置'] = df.apply(lambda x: '上方' if x['ratio'] > x['ma'] else '下方', axis=1)

    # 保存 CSV
    export = df[['n', 'd', 'ratio', 'ma', '位置']].copy()
    export.columns = ['分子指数', '分母指数', '比值', f'{ma_days}日均线', '均线位置']
    export.to_csv('index_ratio_from_db.csv', encoding='utf-8-sig')

    # 画图
    plt.figure(figsize=(12, 6))
    plt.plot(df.index, df['ratio'], label='比值')
    plt.plot(df.index, df['ma'], label=f'{ma_days}日均线', linestyle='--')
    plt.title(f'{numerator_code} / {denominator_code} 比值与{ma_days}日均线')
    plt.xlabel('日期')
    plt.ylabel('比值')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()

# GUI 界面
root = tk.Tk()
root.title("指数比值分析工具")

label1 = tk.Label(root, text="选择分子（上方指数）")
label1.grid(row=0, column=0)
numerator_cb = ttk.Combobox(root, values=list(INDEX_DICT.keys()))
numerator_cb.current(0)
numerator_cb.grid(row=0, column=1)

label2 = tk.Label(root, text="选择分母（下方指数）")
label2.grid(row=1, column=0)
denominator_cb = ttk.Combobox(root, values=list(INDEX_DICT.keys()))
denominator_cb.current(1)
denominator_cb.grid(row=1, column=1)

label3 = tk.Label(root, text="选择均线天数")
label3.grid(row=2, column=0)
ma_cb = ttk.Combobox(root, values=[5, 10, 20, 30, 60, 120, 240])
ma_cb.set(20)
ma_cb.grid(row=2, column=1)

def on_plot():
    num_name = numerator_cb.get()
    den_name = denominator_cb.get()
    if num_name == den_name:
        messagebox.showwarning("错误", "请选择不同的指数进行比较")
        return
    try:
        ma_days = int(ma_cb.get())
    except:
        messagebox.showwarning("错误", "均线天数必须为整数")
        return
    plot_ratio(INDEX_DICT[num_name], INDEX_DICT[den_name], ma_days)

btn_plot = tk.Button(root, text="绘制比值图", command=on_plot, bg="lightgreen")
btn_plot.grid(row=3, column=0, columnspan=2, pady=10)

btn_download = tk.Button(root, text="下载/更新数据", command=update_index_data, bg="skyblue")
btn_download.grid(row=4, column=0, columnspan=2, pady=10)

root.mainloop()