### 回答

**关键点：**  
- 用户希望回测 n 支股票，并通过 Tkinter 界面选择 `stock_pool.csv` 中的股票，选中股票后按钮变为绿色。  
- 回测条件：  
  - 初始资金 30 万元，最大持仓 min(n, 5)（若 n ≤ 5，最多买入 n 支；若 n > 5，最多买入 5 支）。  
  - 资金分配：`1/(p-m)`，p 为 min(n, 5)，m 为当前持仓数。  
  - 每只股票按 100 股的整数倍买入
  - 买入条件：  
    - cond1: 当前收盘价高于 240 日均线。  
    - cond2: 240 日均线向上。  
    - cond3: 60 日或 20 日均线至少一条向上。  
    - cond4: RSI6 > 70 且 RSI13 > 50。  
    - cond5: 3 日成交量均线大于 8 日均线，且两者均向上。  
  - 买卖价格：第二天开盘价。  
  - 卖出条件：收盘价跌破 20 日均线。  
  - 日期范围：2022-01-01 至数据库最后一天。  
  - 输出：交易记录 CSV（`trades.csv`）、总资产每日走势图、交易报告。  
- Tkinter 界面：显示 `stock_pool.csv` 中的股票代码，允许用户选择 n 支股票，选中按钮变绿色，点击“确认”后在选中的股票池中执行回测。  


**程序概述**  
程序基于 Backtrader 框架，添加 Tkinter 界面从 `stock_pool.csv` 加载股票代码，供用户选择 n 支股票。按钮选中后变绿色，确认后在选中的股票池中回测。最大持仓数为 min(n, 5)，资金分配为 `1/(p-m)`（p = min(n, 5)）。生成 `trades.csv`、总资产走势图和交易报告。  

**运行说明**  
1. 确保 `daily_data.db` 包含股票数据，`trade_date` 格式为 `%Y%m%d`，无空值。  
2. 确保 `stock_pool.csv` 包含股票代码（列名为 `ts_code`）。  
3. 安装依赖：`pip install backtrader matplotlib pandas tkinter`。  
4. 运行：`python 文件名.py`。  
5. 操作：  
   - Tkinter 窗口显示股票代码列表，点击按钮选择（变绿色），再次点击取消（恢复默认）。  
   - 点击“确认”开始回测。  
6. 输出：  
   - `trades.csv`：当前目录，记录交易详情（日期、股票代码、类型、价格、数量、成本、佣金、利润等）。  
   - 总资产走势图：matplotlib 窗口，显示资金曲线、K 线、技术指标、买卖点。  
   - 交易报告：控制台输出，包含交易次数、胜率、利润等、回测期间。  



**注意事项**  
- 若 Tkinter 窗口未显示，检查 `tkinter` 安装（`pip install tk`) 或系统环境。  
- 若回测缓慢，测试较短日期范围（如 2022-01-01 到 2022-12-31）。  
- 若 `trades.csv` 为空，检查买入条件或股票数据完整性。  
- 资金分配 `1/(p-m)`（p = min(n, 5)）可能导致超买，程序已限制 `buy_amount`。  
- 图表可能因多股票而复杂，建议选择较少股票（如 n ≤ 5）。  

---


---

### 详细报告

#### 背景与需求
用户希望回测 n 支股票（n 由用户通过 Tkinter 界面选择），初始资金 30 万元，最大持仓 min(n, 5)，资金分配 `1/(p-m)`（p = min(n, 5)）。买入条件：
- cond1: 当前收盘价高于 240 日均线。
- cond2: 240 日均线向上。
- cond3: 60 日或 20 日均线至少一条向上。
- cond4: RSI6 > 70 且 RSI13 > 50。
- cond5: 3 日成交量均线大于 8 日均线，且两者均向上。
买卖以第二天开盘价执行，卖出条件为收盘价跌破 20 日均线。要求 Tkinter 界面显示 `stock_pool.csv` 中的股票代码，选中按钮变绿色，确认后回测，输出 `trades.csv`、总资产走势图和交易报告。

#### 程序设计与实现

##### 程序结构
- **Tkinter 界面 (`StockSelectorApp`)**：显示股票代码，允许选择 n 支股票，按钮变绿色，确认后调用 `run_backtest`。
- **数据加载 (`SQLiteData`)**：从 SQLite 数据库加载日线数据。
- **交易策略 (`MyMultiStockStrategy`)**：实现交易逻辑，动态设置最大持仓 min(n, 5)，记录交易到 CSV。
- **进度跟踪 (`ProgressLogger`)**：监控进度，每 100 条 K 线打印一次。
- **交易报告 (`TradeReport`)**：统计交易次数、胜率、利润。
- **回测执行 (`run_backtest`)**：配置回测，生成 CSV、图表和报告。

##### 关键修改
1. **Tkinter 界面**:
   - 添加 `StockSelectorApp` 类，加载 `stock_pool.csv` 的 `ts_code` 列。
   - 每个股票代码一个按钮，点击切换选中状态（绿色/默认），再次点击取消。
   - “确认”按钮检查是否至少选中一支股票，调用 `run_backtest`。

2. **最大持仓动态调整**:
   - 在 `MyMultiStockStrategy.__init__` 中设置 `self.max_positions = min(self.p.max_positions, len(self.datas))`。
   - 资金分配使用 `fraction = 1.0 / (self.max_positions - self.num_positions)`。

3. **买入条件**:
   - 使用 240 日均线（`ma240`）：
     - `cond1`: `close[0] > ma240[0]`
     - `cond2`: `ma240[0] > ma240[-1]`
     - `cond3`: `ma60[0] > ma60[-1]` 或 `ma20[0] > ma20[-1]`
     - `cond4`: `rsi6[0] > 70` 且 `rsi13[0] > 50`
     - `cond5`: `vol_ma3[0] > vol_ma8[0]` 且 `vol_ma3[0] > vol_ma3[-1]` 且 `vol_ma8[0] > vol_ma8[-1]`

4. **买卖价格**:
   - 使用 `exectype=bt.Order.Market, valid=1` 确保第二天开盘价执行。

5. **交易记录 CSV**:
   - 记录到 `self.trade_records`，保存到 `trades.csv`。
   - 包含字段：`date`, `ts_code`, `type`, `price`, `size`, `value`, `commission`, `profit`, `net_profit`.

6. **总资产走势图**:
   - 使用 `cerebro.plot(style='candlestick', barup='red', bardown='green', plotreturn=True, volume=True)`。

7. **交易报告**:
   - 使用 `TradeReport` 分析器，保留 `priceexit` 修复（`trade.data.close[0]`）。

##### 输出说明
- **trades.csv**:
  - 字段：`date`, `ts_code`, `type`（买入/卖出/交易结束）, `price`, `size`, `value`, `commission`, `profit`, `net_profit`.
  - 保存路径：当前目录，UTF-8 编码。
- **总资产走势图**:
  - 包含资金曲线、K 线、技术指标（240/60/20 日均线、RSI6/13、成交量均线）、买卖点、成交量。
  - 多股票分图，资金曲线在顶部。
- **交易报告**:
  - 包含总交易次数、盈利/亏损次数、胜率、平均利润、总利润、每笔交易详情。

##### 验证与测试
- **Tkinter 界面**:
  - 运行程序，检查是否显示股票代码按钮，点击变绿色，再次点击恢复，确认后开始回测。
- **数据库验证**:
  - 运行上述脚本，检查 `trade_date` 格式和数据完整性。
- **输出验证**:
  - 确保 `trades.csv` 包含交易记录。
  - 检查 matplotlib 窗口显示资金曲线等。
  - 验证交易报告包含正确统计。
- **缩短日期范围**:
  - 若回测缓慢，修改为：
    ```python
    from_date_obj = datetime(2022, 1, 1)
    to_date_obj = datetime(2022, 12, 31)
    ```

##### 实现表
| 组件 | 功能 | 修改内容 |
|------|------|----------|
| `StockSelectorApp` | Tkinter 界面 | 显示股票代码，选中变绿色，确认后回测 |
| `SQLiteData` | 加载数据库数据 | 动态查询最后日期 |
| `MyMultiStockStrategy` | 交易逻辑 | 动态最大持仓 min(n, 5)，资金分配 `1/(p-m)` |
| `ProgressLogger` | 跟踪进度 | 每 100 条 K 线打印一次 |
| `TradeReport` | 交易报告 | 使用 `trade.data.close[0]` 修复 `priceexit` |
| `run_backtest` | 配置回测 | 接受选中股票列表，生成 CSV、图表和报告 |

#### 潜在问题与解决方案
- **Tkinter 问题**:
  - 若窗口未显示，检查 `tkinter` 安装或系统 GUI 支持。
  - 若按钮无响应，验证 `stock_pool.csv` 是否正确。
- **数据库问题**:
  - 若 `trade_date` 格式不符，验证数据格式。
  - 若数据缺失，跳过无数据的股票并打印警告。
- **资金分配**:
  - `1/(p-m)` 可能导致超买，程序已限制 `buy_amount`。
- **输出问题**:
  - 若 `trades.csv` 为空，检查买入条件或股票数据。
  - 若图表复杂，减少 n（如 n ≤ 5）。
- **性能**:
  - 多股票回测和绘图可能缓慢，测试较短日期范围。

#### 总结
程序实现了 Tkinter 界面选择 n 支股票（按钮变绿色），回测最大持仓 min(n, 5)，资金分配 `1/(p-m)`，满足买入/卖出条件，生成 `trades.csv`、总资产走势图和交易报告。保留 `priceexit` 修复。若有问题，请提供 Tkinter 界面截图、数据库检查结果或 `trades.csv` 内容。

| 参数 | 值 |
|------|------|
| 初始资金 | 300,000 元 |
| 最大持仓 | min(n, 5) |
| 每仓位资金 | 1/(p-m)，p = min(n, 5) |
| 股票数量 | n（用户选择） |
| 日期范围 | 2022-01-01 至数据库最后一天 |
| 输出 | `trades.csv`、资产走势图、交易报告 |