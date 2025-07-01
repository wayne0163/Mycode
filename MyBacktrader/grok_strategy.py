import backtrader as bt
import pandas as pd
import sqlite3
import tkinter as tk
from tkinter import messagebox
import os
from datetime import datetime
import sys
import io

# 确保标准输出编码为 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
os.environ["PYTHONIOENCODING"] = "utf-8"

# --- 配置参数 ---
DB_FILE = 'daily_data.db'
DAILY_DATA_TABLE = 'daily_data'
STOCK_POOL_CSV = 'stock_pool.csv'
PLOT_RESULTS = True
TRADES_CSV = 'trades.csv'

# --- Tkinter 界面 ---
class StockSelectorApp:
    def __init__(self, root, stock_codes, callback):
        self.root = root
        self.stock_codes = stock_codes
        self.callback = callback
        self.selected_stocks = set()
        self.buttons = {}
        self.root.title("股票选择器")
        self.root.geometry("800x600")  # 设置窗口初始大小
        self.root.configure(bg="#f0f0f0")  # 设置窗口背景颜色

        # 添加标题标签
        title_label = tk.Label(
            self.root, 
            text="请选择股票：", 
            font=("微软雅黑", 14), 
            bg="#f0f0f0",
            pady=10
        )
        title_label.grid(row=0, column=0, columnspan=5, pady=10)

        # 计算每行显示的按钮数量，可根据需要调整
        buttons_per_row = 5
        for idx, code in enumerate(stock_codes):
            row = idx // buttons_per_row + 1
            col = idx % buttons_per_row
            btn = tk.Button(
                self.root, 
                text=code, 
                command=lambda c=code: self.toggle_stock(c),
                font=("微软雅黑", 10),
                bg="#ffffff",
                activebackground="#e0e0e0",
                padx=10,
                pady=5
            )
            btn.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            self.buttons[code] = btn

        # 设置列权重，让按钮能自动扩张
        for i in range(buttons_per_row):
            self.root.columnconfigure(i, weight=1)

        # 添加确认按钮
        confirm_btn = tk.Button(
            self.root, 
            text="确认", 
            command=self.confirm_selection,
            font=("微软雅黑", 14),
            bg="#4CAF50",
            fg="white",
            activebackground="#45a049",
            padx=20,
            pady=10
        )
        last_row = len(stock_codes) // buttons_per_row + 2
        confirm_btn.grid(row=last_row, column=0, columnspan=buttons_per_row, pady=20)

    def toggle_stock(self, code):
        if code in self.selected_stocks:
            self.selected_stocks.remove(code)
            self.buttons[code].config(bg='#ffffff')
        else:
            self.selected_stocks.add(code)
            self.buttons[code].config(bg='#4CAF50')
        print(f"当前选中的股票: {list(self.selected_stocks)}")
        sys.stdout.flush()

    def confirm_selection(self):
        if not self.selected_stocks:
            messagebox.showwarning("警告", "请至少选择一支股票！")
            return
        self.callback(list(self.selected_stocks))
        self.root.destroy()

# --- 自定义数据加载器 ---
class SQLiteData(bt.feeds.DataBase):
    params = (
        ('dataname', None),
        ('fromdate', datetime(2000, 1, 1)),
        ('todate', datetime.now()),
        ('timeframe', bt.TimeFrame.Days),
        ('compression', 1),
        ('tz', None),
        ('dtformat', '%Y%m%d'),
        ('nullvalue', float('NaN'))
    )

    def __init__(self):
        super().__init__()
        self.conn = None
        self.cursor = None

    def start(self):
        try:
            self.conn = sqlite3.connect(DB_FILE)
            self.cursor = self.conn.cursor()
            query = f"""
                SELECT trade_date, open, high, low, close, vol
                FROM {DAILY_DATA_TABLE}
                WHERE ts_code = ? AND trade_date BETWEEN ? AND ?
                ORDER BY trade_date ASC
            """
            from_date_str = self.p.fromdate.strftime('%Y%m%d')
            to_date_str = self.p.todate.strftime('%Y%m%d')
            self.cursor.execute(query, (self.p.dataname, from_date_str, to_date_str))
        except sqlite3.Error as e:
            print(f"错误: 数据库连接或查询失败: {e}")
            sys.stdout.flush()
            raise

    def stop(self):
        if self.conn:
            self.conn.close()

    def _load(self):
        row = self.cursor.fetchone()
        if row is None:
            return False
        try:
            dt = datetime.strptime(row[0], '%Y%m%d')
            self.lines.datetime[0] = bt.date2num(dt)
            self.lines.open[0] = float(row[1]) if row[1] is not None else float('nan')
            self.lines.high[0] = float(row[2]) if row[2] is not None else float('nan')
            self.lines.low[0] = float(row[3]) if row[3] is not None else float('nan')
            self.lines.close[0] = float(row[4]) if row[4] is not None else float('nan')
            self.lines.volume[0] = float(row[5]) if row[5] is not None else float('nan')
            self.lines.openinterest[0] = float('NaN')
            return True
        except Exception as e:
            print(f"错误: 数据处理失败: {e}, 数据: {row}")
            sys.stdout.flush()
            return False

# --- 策略 ---
class MyMultiStockStrategy(bt.Strategy):
    params = (
        ('max_positions', 5),
    )

    def __init__(self):
        self.log_messages = []
        self.trade_records = []
        self.order = {}
        self.bought_price = {}
        self.num_positions = 0
        self.max_positions = min(self.p.max_positions, len(self.datas))
        self.indicators = {}
        for d in self.datas:
            self.indicators[d] = {
                'ma240': bt.indicators.SMA(d.close, period=240, subplot=True),
                'ma60': bt.indicators.SMA(d.close, period=60, subplot=True),
                'ma20': bt.indicators.SMA(d.close, period=20, subplot=True),
                'vol_ma3': bt.indicators.SMA(d.volume, period=3, subplot=True),
                'vol_ma8': bt.indicators.SMA(d.volume, period=8, subplot=True),
                'rsi13': bt.indicators.RSI(d.close, period=13, subplot=True),
                'rsi6': bt.indicators.RSI(d.close, period=6, subplot=True),
            }

    def log(self, txt, dt=None, data=None):
        dt = dt or self.datas[0].datetime.date(0)
        ts_code_str = f"[{data._name}] " if data else ""
        message = f'{dt.isoformat()}, {ts_code_str}{txt}'
        self.log_messages.append(message)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            trade_type = '买入' if order.isbuy() else '卖出'
            self.log(
                f'{trade_type}执行, 股票: {order.data._name}, 价格: {order.executed.price:.2f}, 数量: {order.executed.size:.2f}, 成本: {order.executed.value:.2f}, 佣金: {order.executed.comm:.2f}',
                data=order.data
            )
            self.trade_records.append({
                'date': self.datas[0].datetime.date(0).isoformat(),
                'ts_code': order.data._name,
                'type': trade_type,
                'price': order.executed.price,
                'size': order.executed.size,
                'value': order.executed.value,
                'commission': order.executed.comm
            })
            if order.isbuy():
                self.bought_price[order.data] = order.executed.price
                self.num_positions += 1
            elif order.issell():
                if order.data in self.bought_price:
                    del self.bought_price[order.data]
                self.num_positions -= 1
            self.order.pop(order.data, None)
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            reason = order.info.get('status_text', '未知原因')
            self.log(f'订单取消/保证金不足/拒绝, 股票: {order.data._name}, 原因: {reason}', data=order.data)
            self.order.pop(order.data, None)

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        self.log(f'交易结束, 股票: {trade.data._name}, 总利润: {trade.pnl:.2f}, 净利润: {trade.pnlcomm:.2f}', data=trade.data)
        self.trade_records.append({
            'date': self.datas[0].datetime.date(0).isoformat(),
            'ts_code': trade.data._name,
            'type': '交易结束',
            'price': trade.price,
            'size': trade.size,
            'value': trade.value,
            'commission': trade.commission,
            'profit': trade.pnl,
            'net_profit': trade.pnlcomm
        })

    def next(self):
        for d in self.datas:
            ind = self.indicators[d]
            required_bars = max(ind['ma240'].params.period, ind['ma60'].params.period,
                                ind['ma20'].params.period, ind['vol_ma3'].params.period,
                                ind['vol_ma8'].params.period, ind['rsi13'].params.period,
                                ind['rsi6'].params.period)
            if len(d) <= required_bars:
                continue
            if any(ind[key][0] is None for key in ind):
                continue
            if d in self.order:
                continue
            position = self.getposition(d)
            if position:
                if len(d) > 1 and d.close[-1] < ind['ma20'][-1]:
                    self.log(f'触发卖出信号 (跌破20均线), 股票: {d._name}, 当前价: {d.close[-1]:.2f}, 20日均线: {ind["ma20"][-1]:.2f}', data=d)
                    self.order[d] = self.sell(data=d, size=position.size, exectype=bt.Order.Market, valid=1)
                continue
            if self.num_positions < self.max_positions:
                cond1 = d.close[0] > ind['ma240'][0]
                cond2 = len(ind['ma240']) > 1 and ind['ma240'][0] > ind['ma240'][-1]
                cond3 = (len(ind['ma60']) > 1 and ind['ma60'][0] > ind['ma60'][-1]) or \
                        (len(ind['ma20']) > 1 and ind['ma20'][0] > ind['ma20'][-1])
                cond4 = ind['rsi6'][0] > 70 and ind['rsi13'][0] > 50
                cond5 = ind['vol_ma3'][0] > ind['vol_ma8'][0] and \
                        len(ind['vol_ma3']) > 1 and ind['vol_ma3'][0] > ind['vol_ma3'][-1] and \
                        len(ind['vol_ma8']) > 1 and ind['vol_ma8'][0] > ind['vol_ma8'][-1]
                if all([cond1, cond2, cond3, cond4, cond5]):
                    available_cash = self.broker.getcash()
                    if self.num_positions < self.max_positions:
                        fraction = 1.0 / (self.max_positions - self.num_positions)
                        buy_amount = available_cash * fraction
                        if buy_amount > 0:
                            size = (buy_amount // d.close[0]) // 100 * 100  # 按100股整数倍买入
                            if size > 0:
                                self.log(f'发出买入信号, 股票: {d._name}, 建议买入数量: {size}, 占用资金: {size * d.close[0]:.2f}', data=d)
                                self.order[d] = self.buy(data=d, size=size, exectype=bt.Order.Market, valid=1)

    def stop(self):
        # 保存交易记录到 CSV
        if self.trade_records:
            df = pd.DataFrame(self.trade_records)
            df.to_csv(TRADES_CSV, index=False, encoding='utf-8')
            print(f"交易记录已保存到 {TRADES_CSV}")

# --- 进度分析器 ---
class ProgressLogger(bt.Analyzer):
    def __init__(self):
        self.counter = 0
        self.start_date = None
        self.end_date = None
        self.total_days = 0

    def start(self):
        all_fromdates = []
        all_todates = []
        for d in self.strategy.datas:
            try:
                if d.size() > 0:
                    all_fromdates.append(d.fromdate.date())
                    all_todates.append(d.todate.date())
            except Exception:
                continue
        if all_fromdates and all_todates:
            self.start_date = max(all_fromdates)
            self.end_date = min(all_todates)
            self.total_days = (self.end_date - self.start_date).days
            print(f"回测日期范围: {self.start_date} 到 {self.end_date} ({self.total_days} 天)")

    def next(self):
        self.counter += 1
        if self.counter % 100 == 0:
            current_date = self.strategy.datas[0].datetime.date(0)
            print(f"当前日期: {current_date.isoformat()}")

    def stop(self):
        pass

# --- 交易报告分析器 ---
class TradeReport(bt.Analyzer):
    def __init__(self):
        self.trades = []
        self.total_cash = []
        self.total_value = []

    def notify_cashvalue(self, cash, value):
        self.total_cash.append(cash)
        self.total_value.append(value)

    def notify_trade(self, trade):
        if trade.isclosed:
            exit_price = trade.data.close[0] if trade.data.close[0] is not None else trade.price
            self.trades.append({
                'ts_code': trade.data._name,
                'entry_date': trade.dtopen,
                'exit_date': trade.dtclose,
                'entry_price': trade.price,
                'exit_price': exit_price,
                'size': trade.size,
                'profit': trade.pnl,
                'net_profit': trade.pnlcomm
            })

    def get_analysis(self):
        total_trades = len(self.trades)
        if total_trades == 0:
            return {
                'total_trades': 0,
                'win_trades': 0,
                'loss_trades': 0,
                'win_rate': 0.0,
                'avg_profit': 0.0,
                'total_profit': 0.0,
                'trades': []
            }
        win_trades = sum(1 for trade in self.trades if trade['net_profit'] > 0)
        loss_trades = total_trades - win_trades
        total_profit = sum(trade['net_profit'] for trade in self.trades)
        avg_profit = total_profit / total_trades if total_trades > 0 else 0.0
        return {
            'total_trades': total_trades,
            'win_trades': win_trades,
            'loss_trades': loss_trades,
            'win_rate': win_trades / total_trades * 100 if total_trades > 0 else 0.0,
            'avg_profit': avg_profit,
            'total_profit': total_profit,
            'trades': self.trades
        }

# --- 回测主函数 ---
def run_backtest(selected_ts_codes):
    cerebro = bt.Cerebro()
    initial_capital = 300000.0
    commission_rate = 0.0003
    print(f"设置初始资金: {initial_capital:.2f} 元")
    print(f"设置佣金: {commission_rate*100:.2f}%")
    sys.stdout.flush()
    cerebro.broker.setcash(initial_capital)
    cerebro.broker.setcommission(commission=commission_rate)

    from_date_obj = datetime(2022, 1, 1)
    conn_check = sqlite3.connect(DB_FILE)
    cursor_check = conn_check.cursor()
    cursor_check.execute(f"SELECT MAX(trade_date) FROM {DAILY_DATA_TABLE}")
    last_date_str = cursor_check.fetchone()[0]
    if not last_date_str:
        print("错误: 数据库中无数据")
        conn_check.close()
        return
    to_date_obj = datetime.strptime(last_date_str, '%Y%m%d')
    print(f"数据库最后日期: {to_date_obj.date()}")
    sys.stdout.flush()

    try:
        for ts_code in selected_ts_codes:
            check_query = f"""
                SELECT COUNT(*)
                FROM {DAILY_DATA_TABLE}
                WHERE ts_code = ? AND trade_date BETWEEN ? AND ?
            """
            from_date_str_check = from_date_obj.strftime('%Y%m%d')
            to_date_str_check = to_date_obj.strftime('%Y%m%d')
            cursor_check.execute(check_query, (ts_code, from_date_str_check, to_date_str_check))
            count_rows = cursor_check.fetchone()[0]
            if count_rows == 0:
                print(f"警告: 股票 {ts_code} 在 {from_date_str_check} 到 {to_date_str_check} 之间无数据")
                sys.stdout.flush()
                continue
            data = SQLiteData(dataname=ts_code, fromdate=from_date_obj, todate=to_date_obj)
            cerebro.adddata(data)
            print(f"股票 {ts_code} 的数据已添加")
            sys.stdout.flush()
    except sqlite3.Error as e:
        print(f"错误: 数据库预检查失败: {e}")
        sys.stdout.flush()
        return
    finally:
        conn_check.close()

    print("添加回测策略...")
    sys.stdout.flush()
    cerebro.addstrategy(MyMultiStockStrategy, max_positions=min(len(selected_ts_codes), 5))
    print("添加回测分析器...")
    sys.stdout.flush()
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(TradeReport, _name='trade_report')
    cerebro.addanalyzer(ProgressLogger, _name='progress_logger')

    print('开始回测...')
    sys.stdout.flush()
    try:
        strategies = cerebro.run()
        strategy = strategies[0]
        print('回测完成')
        sys.stdout.flush()

        print("\n--- 回测统计 ---")
        print(f"初始资金: {cerebro.broker.startingcash:.2f}")
        print(f"期末资金: {cerebro.broker.getvalue():.2f}")
        print(f"总收益率: {(cerebro.broker.getvalue() / cerebro.broker.startingcash - 1) * 100:.2f}%")
        if 'sharpe' in strategy.analyzers:
            sharpe_ratio = strategy.analyzers.sharpe.get_analysis()
            print(f"夏普比率: {sharpe_ratio['sharperatio']:.2f}" if sharpe_ratio['sharperatio'] else "夏普比率: 无法计算")
        if 'drawdown' in strategy.analyzers:
            print(f"最大回撤: {strategy.analyzers.drawdown.get_analysis().max.drawdown:.2f}%")
        if 'returns' in strategy.analyzers:
            print(f"年化收益率: {strategy.analyzers.returns.get_analysis()['anret'] * 100:.2f}%")

        print("\n--- 交易报告 ---")
        trade_analysis = strategy.analyzers.trade_report.get_analysis()
        print(f"总交易次数: {trade_analysis['total_trades']}")
        print(f"盈利交易次数: {trade_analysis['win_trades']}")
        print(f"亏损交易次数: {trade_analysis['loss_trades']}")
        print(f"胜率: {trade_analysis['win_rate']:.2f}%")
        print(f"平均每笔交易利润: {trade_analysis['avg_profit']:.2f}")
        print(f"总利润: {trade_analysis['total_profit']:.2f}")
        print("\n详细交易记录:")
        for trade in trade_analysis['trades']:
            entry_date = bt.num2date(trade['entry_date']).date().isoformat()
            exit_date = bt.num2date(trade['exit_date']).date().isoformat()
            print(f"股票: {trade['ts_code']}, 买入日期: {entry_date}, 卖出日期: {exit_date}, "
                  f"买入价: {trade['entry_price']:.2f}, 卖出价: {trade['exit_price']:.2f}, "
                  f"数量: {trade['size']:.2f}, 净利润: {trade['net_profit']:.2f}")
        sys.stdout.flush()

        print("\n--- 交易日志 ---")
        for msg in strategy.log_messages:
            print(msg)
        sys.stdout.flush()

        if PLOT_RESULTS:
            print("\n生成资产分析图...")
            sys.stdout.flush()
            cerebro.plot(style='candlestick', barup='red', bardown='green', plotreturn=True, volume=True)
            print("图表生成完成")
            sys.stdout.flush()
    except Exception as e:
        print(f"回测错误: {e}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        return

# --- 主程序 ---
if __name__ == '__main__':
    print("--- 回测程序开始执行 ---")
    sys.stdout.flush()
    try:
        stock_df = pd.read_csv(STOCK_POOL_CSV, encoding='utf-8')
        stock_codes = stock_df['ts_code'].tolist()
        if not stock_codes:
            print(f"错误: 自选股票池文件 '{STOCK_POOL_CSV}' 为空")
            sys.stdout.flush()
            sys.exit(1)
    except FileNotFoundError:
        print(f"错误: 未找到自选股票池文件 '{STOCK_POOL_CSV}'")
        sys.stdout.flush()
        sys.exit(1)
    except KeyError:
        print(f"错误: 自选股票池文件 '{STOCK_POOL_CSV}' 中未找到 'ts_code' 列")
        sys.stdout.flush()
        sys.exit(1)
    except Exception as e:
        print(f"错误: 读取自选股票池文件时发生未知错误: {e}")
        sys.stdout.flush()
        sys.exit(1)

    root = tk.Tk()
    app = StockSelectorApp(root, stock_codes, run_backtest)
    root.mainloop()
    print("--- 回测程序执行结束 ---")
    sys.stdout.flush()