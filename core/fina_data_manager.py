import os
import sqlite3
import pandas as pd
import tushare as ts
import logging
import time
from datetime import datetime
from configparser import ConfigParser

class FinaDataManager:
    def __init__(self):
        # 读取配置
        self.config = self.read_config()

        # 数据库路径
        self.financial_db = self.config['Database']['financial_db']

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
        if not os.path.exists('config/settings.ini'):
            raise FileNotFoundError("配置文件 config/settings.ini 不存在，请检查！")
        parser = ConfigParser()
        parser.read('config/settings.ini')
        return {section: dict(parser.items(section)) for section in parser.sections()}

    def create_directories(self):
        """创建数据库目录"""
        os.makedirs(os.path.dirname(self.financial_db), exist_ok=True)

    def setup_logging(self):
        """配置日志"""
        logging.basicConfig(
            filename='data_update.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def _init_tables(self):
        """创建数据库表结构"""
        with sqlite3.connect(self.financial_db) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS financial_data (
                    ts_code TEXT,
                    end_date TEXT,
                    roe_dt REAL,
                    or_yoy REAL,
                    op_yoy REAL,
                    PRIMARY KEY (ts_code, end_date)
                )''')

    def get_existing_periods(self):
        """获取数据库中已有的年报 end_date 列表"""
        with sqlite3.connect(self.financial_db) as conn:
            try:
                df = pd.read_sql("SELECT DISTINCT end_date FROM financial_data", conn)
                return df['end_date'].astype(str).tolist()  # 确保 end_date 是字符串类型
            except Exception as e:
                logging.error(f"获取已有年报数据失败: {str(e)}")
                return []

    def update_financial_data(self):
        """更新过去 5 年的年报数据"""
        today = datetime.today()
        current_year = today.year  # 例如 2025
        last_year = current_year - 1  # 2024

        # 需要查询的年报年份
        required_years = [f"{y}1231" for y in range(current_year - 5, last_year + 1)]  # 2020-2024

        # 2025 年 7 月 1 日之前，还要查询 2024 年
        if today.month >= 7:
            required_years = [y for y in required_years if y != f"{last_year}1231"]  # 2024 年报数据不再查询

        # 获取数据库已有数据，避免重复插入
        existing_periods = self.get_existing_periods()
        new_years = [str(y) for y in required_years if str(y) not in existing_periods]  # 确保 end_date 是字符串类型

        if not new_years:
            print("所有目标年份的数据已存在，无需更新")
            logging.info("所有目标年份的数据已存在，无需更新")
            return True

        print(f"需要更新 {len(new_years)} 个年报数据: {new_years}")

        for period in new_years:
            try:
                print(f"正在获取 {period} 年报数据...")
                # 调用 Tushare API 获取数据
                df = self.pro.fina_indicator_vip(period=str(period), fields='ts_code,end_date,roe_dt,or_yoy,op_yoy')

                # 检查 API 返回的数据是否为空
                if df is None or df.empty:
                    logging.warning(f"{period} 年报数据为空，跳过")
                    continue

                # 检查返回数据中是否包含所有需要的字段
                required_fields = ['ts_code', 'end_date', 'roe_dt', 'or_yoy', 'op_yoy']
                missing_fields = [field for field in required_fields if field not in df.columns]
                if missing_fields:
                    logging.error(f"{period} 年报数据缺失字段: {missing_fields}")
                    continue

                # 清理数据，去重
                df['end_date'] = df['end_date'].astype(str)  # 确保 end_date 是字符串类型
                df = df.drop_duplicates(subset=['ts_code', 'end_date'])

                # 写入数据库（先删除已有数据，再插入）
                with sqlite3.connect(self.financial_db) as conn:
                    conn.execute("DELETE FROM financial_data WHERE end_date = ?", (str(period),))
                    df.to_sql('financial_data', conn, if_exists='append', index=False)
                    logging.info(f"{period} 年报数据写入数据库，共 {len(df)} 条记录")

                print(f"{period} 年报数据更新完成，共 {len(df)} 条记录")

            except Exception as e:
                logging.error(f"{period} 年报数据处理失败: {str(e)}")
                continue

            # 限制请求频率，防止 Tushare 限流
            time.sleep(1)

        print("所有年报数据更新完成")
        return True


if __name__ == "__main__":
    # 初始化 DataManager 并更新年报数据
    dm = FinaDataManager()

    print("\n正在更新财务数据...")
    if dm.update_financial_data():
        print("财务数据更新成功！")
    else:
        print("财务数据更新失败，请查看日志")