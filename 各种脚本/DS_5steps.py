"""
股票数据分析工具 - 整合版 (修复所有已知错误)
功能：日交易数据更新 | 财务数据更新 | 财务分析 | 股票筛选
"""

import os
import sys
import subprocess
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import tushare as ts
from sqlalchemy import create_engine
import tkinter as tk
from tkinter import messagebox, filedialog

# ======================== 全局配置 ========================
ts.set_token('30f35108e87dec2f757afd730f4709c9e2af38b468895e73c9a3312a')  # 需替换为有效Token
pro = ts.pro_api()

# 获取脚本所在目录
script_dir = os.path.dirname(os.path.abspath(__file__))

# 数据库路径
daily_db_name = os.path.join(script_dir, 'data_date_to_sqlite.db')
financial_db_name = os.path.join(script_dir, 'financial_data.db')

# 结果保存目录
result_dir = os.path.join(script_dir, 'result')
os.makedirs(result_dir, exist_ok=True)  # 自动创建结果目录

# ======================== 核心功能 ========================
# ---------------------- 日交易数据处理 ----------------------
# 数据库名称
db_name = 'data_date_to_sqlite.db'

# 检查数据库是否存在
def check_db_exists(db_name):
    return os.path.exists(db_name)

# 获取数据库中最近的日期
def get_last_date(db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    # 获取所有表名（即日期）
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    conn.close()
    
    if not tables:
        return None
    
    # 转换表名为日期并找到最新的日期
    dates = [datetime.strptime(table[0], '%Y%m%d') for table in tables]
    last_date = max(dates).strftime('%Y%m%d')
    return last_date

# 下载某天的日交易数据和指标数据，并合并
def download_data_for_date(date):
    # 下载某天的全部股票的日交易数据
    df_daily = pro.daily(trade_date=date)
    
    # 如果没有数据，返回None
    if df_daily.empty:
        return None
    
    # 下载某天的全部股票的基本指标数据
    df_daily_basic = pro.daily_basic(trade_date=date, fields='ts_code,pe_ttm,pb,total_mv')
    
    # 合并两个数据框
    merged_data = pd.merge(df_daily, df_daily_basic, on='ts_code')
    return merged_data

# 保存数据到SQLite数据库
def save_data_to_db(data, db_name, date):
    conn = sqlite3.connect(db_name)
    # 将数据保存到以日期为表名的表中
    data.to_sql(date, conn, if_exists='append', index=False)
    conn.close()

# 获取最近2年的交易日
def get_recent_trade_dates():
    end_date = datetime.today().strftime('%Y%m%d')
    start_date = (datetime.today() - timedelta(days=2*365)).strftime('%Y%m%d')
    trade_cal = pro.trade_cal(exchange='', start_date=start_date, end_date=end_date, is_open='1')
    trade_cal = trade_cal.sort_values(by='cal_date', ascending=True) #确定是最大的日期也就是最近的日期在最后 
    trade_dates = trade_cal.tail(250)['cal_date'].tolist()
    return trade_dates

# 下载最近250天的交易数据
def download_recent_data():
    trade_dates = get_recent_trade_dates()
    all_data = []
    
    for date in trade_dates:
        print(f"Downloading data for {date}")
        data = download_data_for_date(date)
        if data is not None:  # 如果数据不为空
            all_data.append(data)
    
    return all_data

# 下载缺失的数据
def download_missing_data(start_date):
    end_date = datetime.today().strftime('%Y%m%d')
    trade_cal = pro.trade_cal(exchange='', start_date=start_date, end_date=end_date, is_open='1')
    trade_dates = trade_cal['cal_date'].tolist()
    all_data = []
    
    for date in trade_dates:
        print(f"Downloading data for {date}")
        data = download_data_for_date(date)
        if data is not None:  # 如果数据不为空
            all_data.append(data)
    
    return all_data

def update_daily_data():
    if not check_db_exists(db_name):  # 检查数据库是否存在
        print("数据库不存在，下载最近250天的数据...")
        recent_data = download_recent_data()  # 下载最近250天的数据
        for data in recent_data:
            date_str = data['trade_date'].iloc[0]
            save_data_to_db(data, db_name, date_str)  # 保存数据到数据库
    else:
        print("数据库存在，下载最近250天的数据...")
        last_date = get_last_date(db_name)  # 获取数据库中最近的日期
        if last_date:
            print(f"数据库存在，下载从{last_date}到今天的缺失数据...")
            missing_data = download_missing_data(last_date)  # 下载缺失的数据
            for data in missing_data:
                date_str = data['trade_date'].iloc[0]
                save_data_to_db(data, db_name, date_str)  # 保存数据到数据库
        else:
            print("数据库存在，但没有表，下载最近250天的数据...")
            recent_data = download_recent_data()  # 下载最近250天的数据
            for data in recent_data:
                date_str = data['trade_date'].iloc[0]
                save_data_to_db(data, db_name, date_str)  # 保存数据到数据库    

# ---------------------- 财务数据处理 ----------------------
def get_report_type(end_date):
    """判断报表类型"""
    q_map = {'0331':1, '0630':2, '0930':3, '1231':4}
    return q_map.get(end_date[4:], 0)

def annualize_roe(row):
    """ROE年化处理"""
    factors = {1:4, 2:2, 3:4/3, 4:1}
    row['roe_dt'] *= factors.get(row['report_type'], 1)
    return row

def update_financial_data():
    """更新财务数据"""
    def get_previous_quarter():
        now = datetime.now()
        current_q = (now.month - 1) // 3 + 1
        if current_q == 1:
            return datetime(now.year-1, 12, 31)
        elif current_q == 2:
            return datetime(now.year, 3, 31)
        elif current_q == 3:
            return datetime(now.year, 6, 30)
        else:
            return datetime(now.year, 9, 30)

    try:
        # 获取需要更新的季度
        target_date = get_previous_quarter()
        date_str = target_date.strftime('%Y%m%d')
        
        # 下载并处理数据
        df = pro.fina_indicator_vip(period=date_str)
        if not df.empty:
            df['report_type'] = df['end_date'].apply(get_report_type)
            df = df.apply(annualize_roe, axis=1)
            
            # 存入数据库
            engine = create_engine(f'sqlite:///{financial_db_name}')
            df.to_sql(date_str, engine, if_exists='replace', index=False)
            
        messagebox.showinfo("成功", f"财务数据已更新至 {date_str}")
    except Exception as e:
        messagebox.showerror("错误", f"财务数据更新失败: {str(e)}")

# ---------------------- 财务分析 ----------------------
def financial_analysis():
    """执行财务分析"""
    try:
        # 数据库连接
        conn = sqlite3.connect(financial_db_name)
        tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn)['name'].tolist()
        
        # 获取最新三个报告期
        valid_dates = sorted([d for d in tables if d.isdigit()], reverse=True)[:3]
        dfs = [pd.read_sql(f'SELECT * FROM "{d}"', conn) for d in valid_dates]
        
        # 合并分析
        merged = pd.concat(dfs).drop_duplicates('ts_code')
        merged = merged[['ts_code', 'roe_dt', 'or_yoy', 'op_yoy']]
        
        # 获取最新PE/PB
        pe_data = pro.daily_basic(trade_date=latest_trade_date())
        result = pd.merge(merged, pe_data, on='ts_code')
        
        # 保存结果

        today_str = datetime.today().strftime("%Y%m%d")
        save_path = os.path.join(result_dir, f'financial_result_{today_str}.csv')
        result.to_csv(save_path, index=False)
        messagebox.showinfo("成功", "财务分析完成，结果已保存")
    except Exception as e:
        messagebox.showerror("错误", f"财务分析失败: {str(e)}")

def latest_trade_date():
    """获取最近交易日"""
    cal = pro.trade_cal(start_date=(datetime.today()-timedelta(days=30)).strftime('%Y%m%d'))
    return cal[cal['is_open']==1]['cal_date'].iloc[-1]


# ======================== 新增功能函数 ========================
def open_script_folder():
    """打开程序所在目录"""
    try:
        if sys.platform == 'win32':
            os.startfile(script_dir)
        elif sys.platform == 'darwin':
            subprocess.run(['open', script_dir])
        else:
            subprocess.run(['xdg-open', script_dir])
    except Exception as e:
        messagebox.showerror("错误", f"无法打开目录: {str(e)}")

# ======================== 核心功能函数 ========================
def load_market_data():
    """加载全市场数据"""
    try:
        conn = sqlite3.connect(daily_db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cursor.fetchall()]
        tables = sorted(tables, key=lambda x: datetime.strptime(x, '%Y%m%d'), reverse=True)[:250]  # 取最近250个交易日
        
        print(f"最近的250个交易日最后日期: {tables[-1]}")
        
        # 读取所有数据
        df_all = pd.DataFrame()
        for table in tables:
            df = pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
            df_all = pd.concat([df_all, df])
        
        code_all = df_all['ts_code'].unique().tolist()
        return df_all, code_all
    finally:
        conn.close()

def calculate_technical(df):
    """计算技术指标"""
    df = df.copy()
    # 移动平均线
    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()
    df['MA240'] = df['close'].rolling(240).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    df['RSI6'] = 100 - (100 / (1 + (gain.rolling(6).mean() / loss.rolling(6).mean())))
    df['RSI13'] = 100 - (100 / (1 + (gain.rolling(13).mean() / loss.rolling(13).mean())))
    
    # 成交量均线
    df['VOL_MA3'] = df['vol'].rolling(3).mean()
    df['VOL_MA18'] = df['vol'].rolling(18).mean()
    
    return df.dropna()

def check_conditions(stock_data):
    """检查筛选条件"""
    if len(stock_data) < 242:
        return False
    
    latest = stock_data.iloc[-1]
    
    # 条件1: MA240向上
    cond1 = latest['MA240'] > stock_data['MA240'].iloc[-2]
    
    # 条件2: 最新价 > 240天前价格的110%
    cond2 = latest['close'] > stock_data['close'].iloc[-240] * 1.1
    
    # 条件3: MA60或MA20向上
    cond3 = (latest['MA60'] > stock_data['MA60'].iloc[-2]) or \
            (latest['MA20'] > stock_data['MA20'].iloc[-2])
    
    # 条件4: 成交量均线黄金交叉且向上
    cond4 = False
    # 检查最近3天内的交叉
    for i in range(-3, 0):
        if (stock_data['VOL_MA3'].iloc[i] > stock_data['VOL_MA18'].iloc[i]) and \
        (stock_data['VOL_MA3'].iloc[i-1] <= stock_data['VOL_MA18'].iloc[i-1]):
            cond4 = True
            break
    # 检查均线趋势
    vol_ma3_up = (stock_data['VOL_MA3'].iloc[-1] > stock_data['VOL_MA3'].iloc[-2]) and \
                (stock_data['VOL_MA3'].iloc[-2] > stock_data['VOL_MA3'].iloc[-3])
    vol_ma18_up = (stock_data['VOL_MA18'].iloc[-1] > stock_data['VOL_MA18'].iloc[-2]) and \
                (stock_data['VOL_MA18'].iloc[-2] > stock_data['VOL_MA18'].iloc[-3])
    cond4 = cond4 and vol_ma3_up and vol_ma18_up
    
    # 条件5: RSI条件
    cond5 = (latest['RSI13'] > 50) and (latest['RSI6'] > 70)
    
    return all([cond1, cond2, cond3, cond4, cond5])

# ======================== 筛选功能 ========================
def full_market_selection():
    """执行全市场筛选"""
    try:
        df_all, code_all = load_market_data()
        results = []
        
        for code in code_all:
            stock = df_all[df_all['ts_code'] == code]
            if stock.empty:
                continue
                
            stock = calculate_technical(stock)
            if check_conditions(stock):
                results.append(stock.iloc[-1])
        
        if results:
            result_df = pd.DataFrame(results)
            # 合并基本面数据
            stock_basic = pro.stock_basic(fields='ts_code,name,industry')
            result_df = pd.merge(result_df, stock_basic, on='ts_code')
            
            # 数据清洗
            result_df['total_mv'] = result_df['total_mv'] / 10000
            result_df = result_df.dropna().round(2)
            
            # 保存结果
            today_str = datetime.now().strftime("%Y%m%d")
            save_path = os.path.join(result_dir, f'all_selected_{today_str}.csv')
            result_df.to_csv(save_path, index=False)
            messagebox.showinfo("成功", f"全市场筛选完成，找到{len(result_df)}只股票")
        else:
            messagebox.showinfo("结果", "没有符合筛选条件的股票")
            
    except Exception as e:
        messagebox.showerror("错误", f"全市场筛选失败: {str(e)}")

def custom_stock_selection():
    """执行自选股筛选"""
    try:
        filepath = filedialog.askopenfilename(
            title="选择自选股文件",
            filetypes=[("CSV文件", "*.csv")]
        )
        
        if not filepath:
            return
            
        df_custom = pd.read_csv(filepath)
        if 'ts_code' not in df_custom.columns:
            messagebox.showerror("错误", "CSV文件必须包含ts_code列")
            return
            
        custom_codes = df_custom['ts_code'].unique()
        df_all, _ = load_market_data()
        results = []
        
        for code in custom_codes:
            stock = df_all[df_all['ts_code'] == code]
            if stock.empty:
                continue
                
            stock = calculate_technical(stock)
            if check_conditions(stock):
                results.append(stock.iloc[-1])
        
        if results:
            result_df = pd.DataFrame(results)
            # 合并基本面数据
            stock_basic = pro.stock_basic(fields='ts_code,name,industry')
            result_df = pd.merge(result_df, stock_basic, on='ts_code')
            
            # 数据清洗
            result_df['total_mv'] = result_df['total_mv'] / 10000
            result_df = result_df.dropna().round(2)
            
            # 保存结果
            today_str = datetime.now().strftime("%Y%m%d")
            save_path = os.path.join(result_dir, f'custom_selected_{today_str}.csv')
            result_df.to_csv(save_path, index=False) 
            messagebox.showinfo("成功", f"自选股筛选完成，找到{len(result_df)}只股票")
        else:
            messagebox.showinfo("结果", "没有符合筛选条件的自选股")
            
    except Exception as e:
        messagebox.showerror("错误", f"自选股筛选失败: {str(e)}")
# ======================== 新增状态管理类 ========================
class TaskStatus:
    def __init__(self):
        self.current_task = "空闲"
        self.progress = 0
        self.is_running = False

# ======================== 增强版GUI界面 ========================
class EnhancedStockApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("股票分析系统 v2.1")
        self.geometry("500x550")
        
        # 状态管理
        self.task_status = TaskStatus()
        
        # 创建界面组件
        self.create_buttons()
        self.create_version_label()

    def create_buttons(self):
        """创建功能按钮"""
        btn_style = {
            'width': 35,
            'height': 1,
            'font': ('微软雅黑', 11),
        }
        
        # 功能按钮布局
        tk.Button(self, text="📊 更新日线数据", command=update_daily_data, bg='#E1E1E1',**btn_style).pack(pady=5)
        tk.Button(self, text="📈 更新财务数据", command=update_financial_data,bg='#E1E1E1', **btn_style).pack(pady=5)
        tk.Button(self, text="🔍 执行财务分析", command=financial_analysis, bg='#E1E1E1',**btn_style).pack(pady=5)
        tk.Button(self, text="🌐 全市场筛选", command=full_market_selection, bg='#E1E1E1',**btn_style).pack(pady=5)
        tk.Button(self, text="⭐ 自选股筛选", command=custom_stock_selection,bg='#E1E1E1', **btn_style).pack(pady=5)
        tk.Button(self, text="📂 打开程序目录", command=open_script_folder, bg='#A9D0F5',**btn_style).pack(pady=8)
        tk.Button(self, text="🚪 退出系统", command=self.quit, bg='#FF9999', **btn_style).pack(pady=10)

    def create_version_label(self):
        """创建版本信息标签"""
        version_frame = tk.Frame(self)
        version_frame.pack(side='bottom', pady=5)
        tk.Label(version_frame, text="Version 2.1 | © 2023 Stock Analysis System", 
                font=('Arial', 8), fg='gray').pack()

if __name__ == "__main__":
    app = EnhancedStockApp()
    app.mainloop()
