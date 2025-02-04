import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from tkinter import filedialog
import logging

# ====================== 配置初始化 ======================
logging.basicConfig(
    filename='screening.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ====================== 核心函数 ======================
def calculate_technical_indicators(df):
    """计算技术指标"""
    try:
        # 移动平均线
        df['MA20'] = df['close'].rolling(20, min_periods=1).mean()
        df['MA60'] = df['close'].rolling(60, min_periods=1).mean()
        df['MA240'] = df['close'].rolling(240, min_periods=1).mean()
        
        # RSI计算
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain6 = gain.rolling(6, min_periods=1).mean()
        avg_loss6 = loss.rolling(6, min_periods=1).mean().replace(0, np.nan)
        df['RSI6'] = 100 - (100 / (1 + (avg_gain6 / avg_loss6)))
        
        avg_gain13 = gain.rolling(13, min_periods=1).mean()
        avg_loss13 = loss.rolling(13, min_periods=1).mean().replace(0, np.nan)
        df['RSI13'] = 100 - (100 / (1 + (avg_gain13 / avg_loss13)))
        
        # 成交量均线
        df['VOL_MA3'] = df['vol'].rolling(3, min_periods=1).mean()
        df['VOL_MA18'] = df['vol'].rolling(18, min_periods=1).mean()
        
        return df.dropna()
    except Exception as e:
        logging.error(f"指标计算失败: {str(e)}")
        raise

def check_screening_conditions(df):
    """检查筛选条件"""
    if len(df) < 242:
        return False
    
    latest = df.iloc[-1]
    
    # 条件1: MA240向上
    cond1 = latest['MA240'] > df['MA240'].iloc[-2]
    
    # 条件2: 最新价 > 240天前价格的110%
    cond2 = latest['close'] > df['close'].iloc[-240] * 1.1
    
    # 条件3: MA趋势
    cond3 = (latest['MA60'] > df['MA60'].iloc[-2]) or (latest['MA20'] > df['MA20'].iloc[-2])
    
    # 条件4: 成交量交叉
    cond4 = False
    for i in range(-3, 0):
        if (df['VOL_MA3'].iloc[i] > df['VOL_MA18'].iloc[i]) and \
            (df['VOL_MA3'].iloc[i-1] <= df['VOL_MA18'].iloc[i-1]):
            cond4 = True
            break
    
    # 成交量趋势
    vol_ma3_up = (df['VOL_MA3'].iloc[-1] > df['VOL_MA3'].iloc[-2]) and \
                    (df['VOL_MA3'].iloc[-2] > df['VOL_MA3'].iloc[-3])
    vol_ma18_up = (df['VOL_MA18'].iloc[-1] > df['VOL_MA18'].iloc[-2]) and \
                    (df['VOL_MA18'].iloc[-2] > df['VOL_MA18'].iloc[-3])
    cond4 = cond4 and vol_ma3_up and vol_ma18_up
    
    # 条件5: RSI
    cond5 = (latest['RSI13'] > 50) and (latest['RSI6'] > 70)
    
    return all([cond1, cond2, cond3, cond4, cond5])

# ====================== 主流程 ======================
def run_screening(daily_db_path):
    """主筛选流程"""
    try:
        # 1. 选择文件
        csv_path = filedialog.askopenfilename(
            title="选择自选股CSV文件",
            filetypes=[("CSV文件", "*.csv")]
        )
        if not csv_path:
            return None
        
        # 2. 读取股票列表
        watchlist = pd.read_csv(csv_path)
        ts_codes = watchlist['ts_code'].dropna().unique()
        
        # 3. 连接数据库
        conn = sqlite3.connect(daily_db_path)
        results = []
        
        # 4. 遍历分析
        for ts_code in ts_codes:
            try:
                df = pd.read_sql(
                    f"SELECT * FROM daily_data WHERE ts_code='{ts_code}' ORDER BY trade_date",
                    conn
                )
                if len(df) < 242:
                    continue
                
                df = calculate_technical_indicators(df)
                if check_screening_conditions(df):
                    latest = df.iloc[-1]
                    results.append({
                        '股票代码': ts_code,
                        '最新收盘价': round(latest['close'], 2),  # 新增四舍五入
                        'MA20': round(latest['MA20'], 2),
                        'MA60': round(latest['MA60'], 2),
                        'MA240': round(latest['MA240'], 2),
                        'RSI6': round(latest['RSI6'], 2),
                        'RSI13': round(latest['RSI13'], 2),
                        'VOL_MA3': round(latest['VOL_MA3'], 2),  # 新增成交量均线格式化
                        'VOL_MA18': round(latest['VOL_MA18'], 2)  # 新增成交量均线格式化
                    })
            except Exception as e:
                logging.error(f"股票 {ts_code} 处理失败: {str(e)}")
                continue
        
        # 5. 保存结果
        if results:
            # 转换为DataFrame并统一格式化数值
            result_df = pd.DataFrame(results)
            # 对所有数值列四舍五入到两位小数
            numeric_cols = result_df.select_dtypes(include=[np.number]).columns
            result_df[numeric_cols] = result_df[numeric_cols].round(2)
        
            save_dir = "data"
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            pd.DataFrame(result_df).to_csv(
                    save_path, 
                    index=False, 
                    encoding='utf-8-sig',
                    float_format='%.2f'  # 强制所有浮点数列保留两位小数
                )
            return {'count': len(result_df), 'path': save_path}
        else:
            return None
            
    except Exception as e:
        logging.error(f"筛选流程错误: {str(e)}")
        raise