# core/data_manager.py
import os
import sqlite3
import pandas as pd
import tushare as ts
import logging
import time
from datetime import datetime, timedelta
from configparser import ConfigParser

class DailyDataManager:
    def __init__(self):
        # 初始化配置
        self.config = self.read_config()
        
        # 数据库路径
        self.daily_db = self.config['Database']['daily_db']        
        # 初始化 Tushare
        ts.set_token(self.config['API']['tushare_token'])
        self.pro = ts.pro_api()
        
        # 创建数据库目录
        self.create_directories()
        
        # 配置日志
        self.setup_logging()
        
        # 初始化数据库表
        self._init_tables()

    def read_config(self):
        """读取配置文件"""
        parser = ConfigParser()
        parser.read('config/settings.ini')
        return {section: dict(parser.items(section)) for section in parser.sections()}

    def create_directories(self):
        """创建数据库目录"""
        os.makedirs(os.path.dirname(self.daily_db), exist_ok=True)

    def setup_logging(self):
        """配置日志"""
        logging.basicConfig(
            filename='data_update.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def _init_tables(self):
        """创建数据库表结构"""
        # 日线数据表
        with sqlite3.connect(self.daily_db) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS daily_data (
                    ts_code TEXT,
                    trade_date TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    vol REAL,
                    pe_ttm REAL,
                    pb REAL,
                    total_mv REAL,
                    PRIMARY KEY (ts_code, trade_date)
                )''')

    def _clean_daily_data(self, df):
        """清洗日线数据"""
        if df.empty:
            return df
            
        # # 转换日期格式
        # df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
        
        # 处理缺失值
        df = df.dropna(subset=['ts_code', 'trade_date'])
        df = df.fillna({'pe_ttm': 0, 'pb': 0})
        
        # 去重处理
        return df.drop_duplicates(subset=['ts_code', 'trade_date'], keep='last')

    def get_latest_trade_date(self):
        """获取数据库中最新交易日期"""
        with sqlite3.connect(self.daily_db) as conn:
            try:
                result = conn.execute(
                    "SELECT MAX(trade_date) FROM daily_data"
                ).fetchone()[0]
                return result if result else None
            except:
                return None

    def update_daily_data(self):
        """更新日线数据"""
        try:
            # 获取最近的交易日期或默认为 400 天前的日期
            latest_in_db = self.get_latest_trade_date()
            if latest_in_db is None:
                start_date = (datetime.today() - timedelta(days=400)).strftime('%Y%m%d')
            else:
                start_date = latest_in_db
            end_date = datetime.today().strftime('%Y%m%d')
            # 获取所有待更新日期
            trade_cal = self.pro.trade_cal(
                start_date=start_date,
                end_date=end_date,
                is_open=1
            )
            # 输出转换后的日期范围
            trade_cal['cal_date'] = pd.to_datetime(trade_cal['cal_date'], format='%Y%m%d')
            start_date_dt = pd.to_datetime(start_date, format='%Y%m%d')
            end_date_dt = pd.to_datetime(end_date, format='%Y%m%d')
            # 筛选日期
            new_dates = trade_cal[
                (trade_cal['cal_date'] >= start_date_dt) & 
                (trade_cal['cal_date'] <= end_date_dt) & 
                (trade_cal['is_open'] == 1)
                ]['cal_date'].dt.strftime('%Y%m%d').tolist()
            if not new_dates:
                logging.info("没有需要更新的日线数据")
                print('没有需要更新的日期')
                return True

            # 逐个日期更新
            success_count = 0
            total = len(new_dates)
            print(f'需要更新 {total} 条记录')
            for idx, trade_date in enumerate(new_dates, 1):
                try:
                    # 单个日期获取数据
                    df_daily = self.pro.daily(trade_date=trade_date, fields='ts_code,trade_date,open,low,high,close,vol')
                    df_basic = self.pro.daily_basic(trade_date=trade_date, fields='ts_code,trade_date,pe_ttm,pb,total_mv')
                    
                    if df_daily is None or df_basic is None:
                        logging.error(f"日期 {trade_date} 数据获取失败")
                        continue
                    
                    # 合并清洗数据
                    merged = pd.merge(df_daily, df_basic, on=['ts_code', 'trade_date'], how='left')
                    merged = merged.fillna(value=0)
                    cleaned = self._clean_daily_data(merged)
                    
                    if cleaned.empty:
                        logging.warning(f"日期 {trade_date} 数据为空")
                        continue
                    
                    # 写入数据库
                    with sqlite3.connect(self.daily_db) as conn:
                        existing_data = pd.read_sql("SELECT ts_code, trade_date FROM daily_data", conn)
                        cleaned = cleaned.merge(existing_data, on=['ts_code', 'trade_date'], how='left', indicator=True)
                        cleaned = cleaned[cleaned['_merge'] == 'left_only'].drop(columns=['_merge'])
                        
                        if not cleaned.empty:
                            cleaned.to_sql('daily_data', conn, if_exists='append', index=False)

                    # 显示进度
                    print(f"进度: {idx}/{total} [{trade_date}]", end='\r')
                    
                    # 限速请求
                    time.sleep(1 if idx % 5 != 0 else 2)
                    
                except Exception as e:
                    logging.error(f"日期 {trade_date} 处理失败: {str(e)}")
                    continue
            
            print(f"\n完成！成功处理 {success_count}/{total} 个交易日")
            return True
        except Exception as e:
            logging.error(f"日线更新失败: {str(e)}")
            return False



if __name__ == "__main__":
    # 测试代码
    dm = DailyDataManager()
    
    print("正在更新日线数据...")
    if dm.update_daily_data():
        print("日线数据更新成功！")
    else:
        print("日线数据更新失败，请查看日志")