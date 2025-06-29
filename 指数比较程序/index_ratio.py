# 中证2000与沪深300比值分析脚本
# 依赖库：tushare、pandas、matplotlib

import tushare as ts
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import sys
import io
import os

# 确保标准输出编码为 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
os.environ["PYTHONIOENCODING"] = "utf-8"
# 初始化 tushare
TOKEN = '30f35108e87dec2f757afd730f4709c9e2af38b468895e73c9a3312a'  # <<< 替换为你的 Tushare Pro Token
ts.set_token(TOKEN)
pro = ts.pro_api()

# 配置参数
start_date = '20240701'
end_date = datetime.today().strftime('%Y%m%d')

# 指数代码
CSI_2000 = '000933.SH'  # 中证2000
CSI_300 = '000300.SH'   # 沪深300

# 获取指数日线行情（复权因子不适用指数）
def get_index_close(ts_code):
    df = pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    df = df[['trade_date', 'close']].sort_values('trade_date')
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df.set_index('trade_date', inplace=True)
    return df

# 获取数据
df_2000 = get_index_close(CSI_2000)
df_300 = get_index_close(CSI_300)

# 合并数据
df = pd.DataFrame()
df['2000'] = df_2000['close']
df['300'] = df_300['close']
df.dropna(inplace=True)

# 归一化：起始点为 100
base_2000 = df['2000'].iloc[0]
base_300 = df['300'].iloc[0]
df['2000_norm'] = df['2000'] / base_2000 * 100
df['300_norm'] = df['300'] / base_300 * 100

# 比率与20日均线
df['ratio'] = df['2000_norm'] / df['300_norm']
df['ratio_ma20'] = df['ratio'].rolling(window=20).mean()

# 绘图
plt.figure(figsize=(12, 6))
plt.plot(df.index, df['ratio'], label='中证2000 / 沪深300 比值')
plt.plot(df.index, df['ratio_ma20'], label='20日均线', linestyle='--')
plt.title('中证2000 / 沪深300 比值与20日均线')
plt.xlabel('日期')
plt.ylabel('比值')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()
