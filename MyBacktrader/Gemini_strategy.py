import backtrader as bt
import pandas as pd
import sqlite3
import os
from datetime import datetime, date
import sys
import io
import matplotlib.pyplot as plt

# 确保标准输出的编码为 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
os.environ["PYTHONIOENCODING"] = "utf-8"

print("--- 程序启动 ---")
sys.stdout.flush()

# --- 配置参数 ---
DB_FILE = 'daily_data.db' # SQLite数据库文件名
DAILY_DATA_TABLE = 'daily_data' # 存储股票日线数据的表名
STOCK_POOL_CSV = 'stock_pool.csv' # 存储自选股票代码的CSV文件
PLOT_RESULTS = True # 是否显示回测图表 (这将使用Backtrader的内置绘图)


# --- 辅助函数：从SQLite加载数据并转换为PandasData ---
def load_stock_data(ts_code, fromdate, todate, db_file, table_name):
    '''
    从SQLite数据库加载指定股票、日期范围的数据，并转换为bt.feeds.PandasData。
    '''
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        query = f"""
            SELECT trade_date, open, high, low, close, vol
            FROM {table_name}
            WHERE ts_code = ? AND trade_date BETWEEN ? AND ?
            ORDER BY trade_date ASC
        """
        from_date_str = fromdate.strftime('%Y%m%d')
        to_date_str = todate.strftime('%Y%m%d')
        
        df = pd.read_sql_query(query, conn, params=(ts_code, from_date_str, to_date_str))
        
        if df.empty:
            print(f"警告: 股票 {ts_code} 在 {from_date_str} 到 {to_date_str} 之间没有找到数据。")
            sys.stdout.flush()
            return None

        # 确保列名与Backtrader PandasData的期望一致
        df.columns = ['datetime', 'open', 'high', 'low', 'close', 'volume']
        
        # 将 datetime 列设置为索引，并转换为 datetime 对象
        df['datetime'] = pd.to_datetime(df['datetime'], format='%Y%m%d')
        df.set_index('datetime', inplace=True)
        
        # 补齐 Backtrader 可能需要的其他列，如 openinterest
        if 'openinterest' not in df.columns:
            df['openinterest'] = 0.0 # 或者 pd.NA
            
        print(f"信息: 已为股票 {ts_code} 成功加载 {len(df)} 条数据。")
        sys.stdout.flush()
        
        # 创建 PandasData feed
        # IMPORTANT CHANGE: Removed fromdate/todate from PandasData constructor
        # Let PandasData infer date range from the DataFrame's index directly
        data = bt.feeds.PandasData(dataname=df)
        return data

    except sqlite3.Error as e:
        print(f"错误: 从数据库加载股票 {ts_code} 数据失败: {e}")
        sys.stdout.flush()
        return None
    except Exception as e:
        print(f"错误: 处理股票 {ts_code} 数据时发生未知错误: {e}")
        sys.stdout.flush()
        return None
    finally:
        if conn:
            conn.close()


# --- 回测策略 ---
class MyMultiStockStrategy(bt.Strategy):
    params = (
        ('max_positions', 5), # 最多同时持仓股票数量
    )

    def __init__(self):
        self.log_messages = [] # 用于存储日志信息
        self.orders = {} # 字典，用于追踪每只股票的挂单 {data: order_object}
        self.bought_price = {} # 记录每只股票的买入价格 {data: price}
        
        self.inds = {} # 字典，存储每只股票的技术指标
        for d in self.datas:
            self.inds[d] = {
                'ma240': bt.indicators.SMA(d.close, period=240, subplot=True),
                'ma120': bt.indicators.SMA(d.close, period=120, subplot=True),
                'ma60': bt.indicators.SMA(d.close, period=60, subplot=True),
                'ma20': bt.indicators.SMA(d.close, period=20, subplot=True),
                'vol_ma3': bt.indicators.SMA(d.volume, period=3, subplot=True),
                'vol_ma8': bt.indicators.SMA(d.volume, period=8, subplot=True),
                'rsi13': bt.indicators.RSI(d.close, period=13, subplot=True),
                'rsi6': bt.indicators.RSI(d.close, period=6, subplot=True),
            }

    def log(self, txt, dt=None, data=None):
        '''策略日志函数'''
        dt = dt or self.datas[0].datetime.date(0) # 使用主数据的时间作为日志日期
        ts_code_str = f"[{data._name}] " if data else ""
        message = f'{dt.isoformat()}, {ts_code_str}{txt}'
        self.log_messages.append(message)
        print(message) # 打印到控制台
        sys.stdout.flush()

    def notify_order(self, order):
        # 订单状态通知
        if order.status in [order.Submitted, order.Accepted]:
            # 订单已提交/接受，等待执行
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    '买入执行, 股票: %s, 价格: %.2f, 数量: %.2f, 成本: %.2f, 佣金: %.2f' %
                    (order.data._name, order.executed.price, order.executed.size,
                     order.executed.value, order.executed.comm),
                    data=order.data
                )
                self.bought_price[order.data] = order.executed.price
            elif order.issell():
                self.log(
                    '卖出执行, 股票: %s, 价格: %.2f, 数量: %.2f, 成本: %.2f, 佣金: %.2f' %
                    (order.data._name, order.executed.price, order.executed.size,
                     order.executed.value, order.executed.comm),
                    data=order.data
                )
                if order.data in self.bought_price:
                    del self.bought_price[order.data]

            # 订单完成后，从挂单字典中移除
            if order.data in self.orders:
                self.orders[order.data] = None 

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            # 订单取消/保证金不足/拒绝
            reason = order.info.get('status_text', '未知原因') # 使用 .get 避免 KeyError
            self.log(f'订单取消/保证金不足/拒绝, 股票: {order.data._name}, 原因: {reason}', data=order.data)
            if order.data in self.orders:
                self.orders[order.data] = None

    def notify_trade(self, trade):
        # 交易结束（平仓）通知
        if not trade.isclosed:
            return # 只处理已平仓的交易
        self.log(f'交易结束, 股票: {trade.data._name}, 总利润: {trade.pnl:.2f}, 净利润: {trade.pnlcomm:.2f}', data=trade.data)

    def next(self):
        # 获取当前持仓的股票数量
        current_num_positions = len([d for d in self.positions if self.positions[d].size != 0])

        for d in self.datas: # 遍历所有数据流（股票）
            # 检查当前数据是否有效，即 Backtrader 是否有足够的数据填充其 lines
            # 对于 PandasData，has_a_future() 是可用的，并用于判断是否还有未来的数据点
            if not d.has_a_future(): 
                continue

            ind = self.inds[d]
            
            # 确保有足够的数据点来计算最长周期的指标 (MA240)
            # len(d) 应该大于等于 max_period 才能确保指标有值
            max_period = max([ind[key].params.period for key in ind if hasattr(ind[key], 'params')])
            if len(d) <= max_period: 
                continue

            # 确保所有关键指标都有值（防止冷启动阶段None/NaN）
            if any(ind[key][0] is None or pd.isna(ind[key][0]) for key in ind):
                continue

            # 检查是否有针对这只股票的挂单，如果有，则跳过
            if d in self.orders and self.orders[d] is not None:
                continue

            position = self.getposition(d) # 获取当前股票的持仓信息

            # --- 卖出条件 (收盘价跌破 20 日均线) ---
            if position: # 如果有持仓
                ma20_current = ind['ma20'][0] # 使用当前 bar 的20日均线
                if d.close[0] < ma20_current: # 当前收盘价跌破20日均线
                    self.log(f'触发卖出信号 (跌破20均线), 股票: {d._name}, 当前价: {d.close[0]:.2f}, 20日均线: {ma20_current:.2f}', data=d)
                    # 下卖单，执行价格为下一天的开盘价 (Order.Open)
                    self.orders[d] = self.close(data=d, exectype=bt.Order.Open)
                continue # 如果已有持仓或已发出卖单，则跳过买入逻辑

            # --- 买入条件 ---
            # 如果当前没有持仓，且持仓数量未达到上限
            if not position and current_num_positions < self.p.max_positions:
                
                ma240_line = ind['ma240']
                ma60_line = ind['ma60']
                ma20_line = ind['ma20']
                rsi13_line = ind['rsi13']
                rsi6_line = ind['rsi6']
                vol_ma3_line = ind['vol_ma3']
                vol_ma8_line = ind['vol_ma8']

                # cond1: 当前收盘价高于240 日均线。
                cond1 = d.close[0] > ma240_line[0]

                # cond2: 240 日均线向上。
                cond2 = ma240_line[0] > ma240_line[-1]

                # cond3: 60 日或 20 日均线至少一条向上。
                cond3 = (ma60_line[0] > ma60_line[-1]) or (ma20_line[0] > ma20_line[-1])

                # cond4: RSI6 > 70 且 RSI13 > 50。
                cond4 = rsi6_line[0] > 70 and rsi13_line[0] > 50

                # cond5: 成交量ma3大于ma8，且都是向上。
                cond5 = (vol_ma3_line[0] > vol_ma8_line[0]) and \
                        (vol_ma3_line[0] > vol_ma3_line[-1]) and \
                        (vol_ma8_line[0] > vol_ma8_line[-1])
                        
                # 综合所有买入条件
                if all([cond1, cond2, cond3, cond4, cond5]):
                    available_cash = self.broker.getcash()
                    if available_cash > 0:
                        # 资金分配：1/(5-n) 的可用资金，n为当前持仓数
                        denominator = self.p.max_positions - current_num_positions
                        
                        # 避免除以0或负数
                        if denominator <= 0:
                            self.log(f'警告: 股票 {d._name} 无法买入，已达最大持仓数。', data=d)
                            continue
                        
                        funds_to_invest = available_cash / denominator
                        
                        # 买入价格为第二天开盘价，d.open[1] 表示下一根K线的开盘价
                        # 确保 d.open[1] 有效
                        price_to_buy = d.open[1] 
                        
                        if price_to_buy is not None and not pd.isna(price_to_buy) and price_to_buy > 0:
                            size = funds_to_invest // price_to_buy # 计算可买入股数 (向下取整)
                            if size > 0:
                                self.log(f'发出买入信号, 股票: {d._name}, 建议买入数量: {size}, 占用资金: {size * price_to_buy:.2f}', data=d)
                                # 下买单，执行价格为下一天的开盘价 (Order.Open)
                                self.orders[d] = self.buy(data=d, size=size, exectype=bt.Order.Open)
                        # else:
                            # 调试时可以打印警告，正常运行时无需
                            # self.log(f'警告: 股票 {d._name} 在 {self.datas[0].datetime.date(0)} 下一个交易日开盘价不可用，无法下单。')


# --- 回测分析器 ---
class ProgressLogger(bt.Analyzer):
    '''
    用于在回测过程中打印进度的分析器。
    '''
    def __init__(self):
        self.counter = 0
        self.start_date = None
        self.end_date = None
        self.total_days = 0
        self.last_log_date = None # 用于控制日志打印频率

    def start(self):
        super().start()
        all_fromdates = []
        all_todates = []

        if not self.strategy.datas:
            return

        for d in self.strategy.datas:
            try:
                # bt.feeds.PandasData 会正确设置 d.fromdate 和 d.todate
                if d.size() > 0 and d.fromdate and d.todate:
                    all_fromdates.append(d.fromdate.date())
                    all_todates.append(d.todate.date())
            except Exception as e:
                print(f"警告: ProgressLogger.start - 获取数据流 {d._name} 日期失败: {e}")
                sys.stdout.flush()
                continue

        if all_fromdates and all_todates:
            self.start_date = max(all_fromdates) 
            self.end_date = min(all_todates)     
            self.total_days = (self.end_date - self.start_date).days
            print(f"信息: 回测日期范围: {self.start_date.isoformat()} 到 {self.end_date.isoformat()} (共 {self.total_days} 天)")
        else:
            print("警告: 无法确定回测日期范围，进度显示可能不准确或不会显示。")
        sys.stdout.flush()
        print("\n--- 回测进度 ---")
        sys.stdout.flush()

    def next(self):
        self.counter += 1
        current_date = None
        if self.strategy.datas and len(self.strategy.datas[0]) > 0:
            try:
                current_date = self.strategy.datas[0].datetime.date(0)
            except IndexError:
                pass

        if current_date:
            # 每50个交易日或每周一打印一次进度
            if self.counter % 50 == 0 or (self.last_log_date is None or (current_date - self.last_log_date).days >= 7):
                if self.total_days > 0 and self.start_date:
                    days_passed = (current_date - self.start_date).days
                    progress_percent = (days_passed / self.total_days) * 100
                    progress_percent = min(progress_percent, 100.0) 
                    print(f"当前日期: {current_date.isoformat()} (进度: {progress_percent:.2f}%)")
                else:
                    print(f"当前日期: {current_date.isoformat()}")
                self.last_log_date = current_date 
                sys.stdout.flush()

    def stop(self):
        super().stop()
        print("--- 回测进度结束 ---")
        sys.stdout.flush()

class TradeRecorder(bt.Analyzer):
    '''
    分析器：记录所有已执行的交易，用于生成 CSV 报告。
    '''
    def __init__(self):
        self.trades = []

    def notify_trade(self, trade):
        # 只记录已平仓的交易
        if trade.isclosed:
            self.trades.append({
                '股票代码': trade.data._name,
                '开仓日期': bt.num2date(trade.history.open.datetime).date(),
                '平仓日期': bt.num2date(trade.history.close.datetime).date(),
                '买入价格': trade.history.open.price,
                '卖出价格': trade.history.close.price,
                '交易数量': trade.history.size,
                '总利润': trade.pnl,
                '净利润': trade.pnlcomm,
                '利润率 (%)': (trade.pnlcomm / trade.value * 100) if trade.value else 0, # 计算利润率
                '佣金': trade.commission
            })

class ValueTracker(bt.Analyzer):
    '''
    分析器：记录每个交易日结束时的总资产。
    '''
    def __init__(self):
        self.values = []

    def next(self):
        # 记录当前日期和投资组合总价值
        current_date = self.strategy.datas[0].datetime.date(0)
        current_value = self.strategy.broker.getvalue()
        self.values.append({
            '日期': current_date,
            '总资产': current_value
        })

# --- 回测主函数 ---
def run_backtest(stock_pool_path):
    cerebro = bt.Cerebro()

    # 设置初始资金和佣金
    initial_capital = 300000.0 # 初始资金30万元
    print(f"设置初始资金: {initial_capital:.2f} 元")
    sys.stdout.flush()

    commission_rate = 0.0003
    print(f"设置佣金: {commission_rate*100:.2f}%")
    sys.stdout.flush()

    cerebro.broker.setcash(initial_capital)
    cerebro.broker.setcommission(commission=commission_rate)
    
    # 添加策略和分析器
    print("添加回测策略和分析器...")
    sys.stdout.flush()
    cerebro.addstrategy(MyMultiStockStrategy) # 使用多股票策略
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade_analysis')
    cerebro.addanalyzer(ProgressLogger, _name='progress_logger')
    cerebro.addanalyzer(TradeRecorder, _name='trade_recorder') # 添加交易记录分析器
    cerebro.addanalyzer(ValueTracker, _name='value_tracker') # 添加资产走势记录分析器

    # 读取自选股票池，并选择前10只股票
    print(f"尝试读取自选股票池文件: {stock_pool_path}")
    sys.stdout.flush()
    try:
        stock_df = pd.read_csv(stock_pool_path, encoding='utf-8')
        selected_ts_codes = stock_df['ts_code'].tolist()
        if not selected_ts_codes:
            print("错误: 自选股票池为空，请检查CSV文件内容。")
            sys.stdout.flush()
            return
        # 获取前10只股票进行回测
        ts_codes_to_backtest = selected_ts_codes[:10]
        print(f"将对以下 {len(ts_codes_to_backtest)} 只股票进行回测: {ts_codes_to_backtest}")
        sys.stdout.flush()
    except FileNotFoundError:
        print(f"错误: 未找到自选股票池文件 '{stock_pool_path}'。请检查路径和文件名。")
        sys.stdout.flush()
        return
    except KeyError:
        print(f"错误: 自选股票池文件 '{stock_pool_path}' 中未找到 'ts_code' 列。请检查列名。")
        sys.stdout.flush()
        return
    except Exception as e:
        print(f"错误: 读取自选股票池文件时发生未知错误: {e}")
        sys.stdout.flush()
        return

    # 确定回测日期范围（从2022-01-01到数据库中的最新日期）
    from_date_obj = datetime(2022, 1, 1) # 回测起始日期
    conn_check = None
    to_date_obj = None
    try:
        conn_check = sqlite3.connect(DB_FILE)
        cursor_check = conn_check.cursor()
        cursor_check.execute(f"SELECT MAX(trade_date) FROM {DAILY_DATA_TABLE}")
        last_date_str = cursor_check.fetchone()[0]
        if last_date_str:
            to_date_obj = datetime.strptime(last_date_str, '%Y%m%d')
            print(f"信息: 数据库中最新数据日期: {to_date_obj.date()}")
        else:
            print("错误: 数据库中没有找到任何数据。")
            sys.stdout.flush()
            return
    except sqlite3.Error as e:
        print(f"错误: 获取数据库最新日期失败: {e}")
        sys.stdout.flush()
        return
    finally:
        if conn_check:
            conn_check.close()
    
    if not to_date_obj: # 如果没有获取到结束日期，则退出
        return

    # 为所有选定股票添加数据馈送
    # Backtrader会自动处理多个数据流的时间同步
    for stock_code in ts_codes_to_backtest:
        print(f"正在添加股票 {stock_code} 的数据到回测引擎...")
        sys.stdout.flush()
        # 预检查该股票在指定日期范围内的数据量
        conn_precheck = None
        try:
            conn_precheck = sqlite3.connect(DB_FILE)
            cursor_precheck = conn_precheck.cursor()
            check_query = f"""
                SELECT COUNT(*)
                FROM {DAILY_DATA_TABLE}
                WHERE ts_code = ? AND trade_date BETWEEN ? AND ?
            """
            from_date_str_check = from_date_obj.strftime('%Y%m%d')
            to_date_str_check = to_date_obj.strftime('%Y%m%d')
            cursor_precheck.execute(check_query, (stock_code, from_date_str_check, to_date_str_check))
            count_rows = cursor_precheck.fetchone()[0]

            if count_rows == 0:
                print(f"警告: 数据库中未找到股票 {stock_code} 在 {from_date_str_check} 到 {to_date_str_check} 之间的数据。将跳过此股票。")
                sys.stdout.flush()
                continue # 跳过此股票，处理下一只
            else:
                print(f"信息: 数据库中确认股票 {stock_code} 在 {from_date_str_check} 到 {to_date_str_check} 之间有 {count_rows} 条数据。")
                sys.stdout.flush()

        except sqlite3.Error as e:
            print(f"错误: 数据库预检查失败 for {stock_code}: {e}. 将跳过此股票。")
            sys.stdout.flush()
            continue
        finally:
            if conn_precheck:
                conn_precheck.close()

        try:
            # 使用获取到的 from_date_obj 和 to_date_obj
            data = load_stock_data(stock_code, from_date_obj, to_date_obj, DB_FILE, DAILY_DATA_TABLE)
            if data:
                cerebro.adddata(data)
                print(f"股票 {stock_code} 的数据已成功添加到 Backtrader 引擎。")
                sys.stdout.flush()
            else:
                print(f"警告: 未能为股票 {stock_code} 加载数据，已跳过。")
                sys.stdout.flush()
        except Exception as e:
            print(f"错误: 添加股票 {stock_code} 的数据时发生致命错误: {e}. 将跳过此股票。")
            sys.stdout.flush()
            continue

    if not cerebro.datas:
        print("错误: 没有成功添加任何股票数据，回测无法运行。")
        sys.stdout.flush()
        return

    print('开始回测模拟...')
    sys.stdout.flush()
    try:
        strategies = cerebro.run()
        print('DEBUG: cerebro.run() 调用已完成。')
        sys.stdout.flush()

        strategy = strategies[0] # 获取运行的策略实例

        print('回测模拟完成。')
        sys.stdout.flush()

        # --- 生成报告 ---
        print("\n--- 回测统计报告 ---")
        print(f"初始资金: {cerebro.broker.startingcash:.2f} 元")
        final_value = cerebro.broker.getvalue()
        print(f"期末资金: {final_value:.2f} 元")
        total_return_pct = (final_value / cerebro.broker.startingcash - 1) * 100
        print(f"总收益率: {total_return_pct:.2f}%")

        # 获取分析器结果
        if 'sharpe' in strategy.analyzers:
            sharpe_ratio_analysis = strategy.analyzers.sharpe.get_analysis()
            if 'sharperatio' in sharpe_ratio_analysis and sharpe_ratio_analysis['sharperatio'] is not None:
                 print(f"夏普比率: {sharpe_ratio_analysis['sharperatio']:.2f}")
            else:
                print("夏普比率: 无法计算 (可能没有交易或波动性为零)")
        if 'drawdown' in strategy.analyzers:
            print(f"最大回撤: {strategy.analyzers.drawdown.get_analysis().max.drawdown:.2f}%")
        if 'returns' in strategy.analyzers:
            print(f"年化收益率: {strategy.analyzers.returns.get_analysis()['anret'] * 100:.2f}%")
        
        # trade_analysis提供更多交易细节，可以打印或进一步处理
        trade_analysis = strategy.analyzers.trade_analysis.get_analysis()
        if trade_analysis and 'total' in trade_analysis:
            print(f"总交易次数: {trade_analysis.total.total}")
            print(f"盈利交易次数: {trade_analysis.won.total}")
            print(f"亏损交易次数: {trade_analysis.lost.total}")
            print(f"胜率: {trade_analysis.won.total / trade_analysis.total.total * 100 if trade_analysis.total.total > 0 else 0:.2f}%")
        
        sys.stdout.flush()

        # 保存交易记录到 CSV 文件
        trade_records = strategy.analyzers.trade_recorder.trades
        if trade_records:
            trade_df = pd.DataFrame(trade_records)
            trade_df.to_csv('trade_records.csv', index=False, encoding='utf-8-sig')
            print("\n交易记录已保存到 'trade_records.csv'")
            sys.stdout.flush()

        # 绘制并保存总资产每日走势图
        value_records = strategy.analyzers.value_tracker.values
        if value_records:
            value_df = pd.DataFrame(value_records)
            value_df['日期'] = pd.to_datetime(value_df['日期'])
            value_df.set_index('日期', inplace=True)
            
            plt.figure(figsize=(14, 7))
            plt.plot(value_df.index, value_df['总资产'], label='总资产')
            plt.title('总资产每日走势', fontsize=18)
            plt.xlabel('日期', fontsize=14)
            plt.ylabel('资产 (元)', fontsize=14)
            plt.grid(True)
            plt.legend()
            plt.tight_layout()
            plt.savefig('portfolio_value_plot.png')
            print("总资产每日走势图已保存为 'portfolio_value_plot.png'")
            sys.stdout.flush()
        else:
            print("警告: 未生成总资产每日走势数据，无法绘制图表。")
            sys.stdout.flush()
        
        # Backtrader 内置的绘图 (可选)
        if PLOT_RESULTS:
            print("\n正在生成 Backtrader 内置回测图表 (这将是一个交互式窗口)...")
            sys.stdout.flush()
            # cerebro.plot() 会打开一个交互式窗口，可能需要手动关闭才能让程序继续
            cerebro.plot(style='candlestick', barup='red', bardown='green', plotreturn=True)
            print("Backtrader 内置图表生成完成。")
            sys.stdout.flush()
        else:
            print("\n已禁用 Backtrader 内置图表显示。")
            sys.stdout.flush()

    except Exception as e:
        print(f"回测模拟过程中发生错误: {e}")
        # import traceback # 调试时可以取消注释以打印完整堆栈
        # traceback.print_exc()
        sys.stdout.flush()


# --- 运行回测程序 ---
if __name__ == '__main__':
    print("--- 回测程序开始执行 ---")
    sys.stdout.flush()
    run_backtest(STOCK_POOL_CSV)
    print("--- 回测程序执行结束 ---")
    sys.stdout.flush()
