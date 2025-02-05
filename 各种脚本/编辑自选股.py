import os
import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import tushare as ts
from datetime import datetime


class StockProcessingApp:
    """
    股票代码处理工具

    功能说明：
    1. 提供一个图形化界面 (GUI)。
    2. 将自选股 CSV 文件中的股票代码转换为标准格式（带市场后缀）。
    3. 将处理后的股票代码导出为纯文本文件。
    4. 使用 Tushare API 获取公司的基础信息（名称、行业）。
    5. 提供退出按钮。

    使用说明：
    1. 点击“选择 CSV 文件”，选择要处理的文件。
    2. 输入输出文件名（可选）。
    3. 点击相应的按钮执行功能。
    """

    def __init__(self, root):
        self.root = root
        self.root.title("股票代码处理工具")

        # 初始化变量
        self.input_file = ""
        self.output_file = tk.StringVar(value="output.csv")

        # 创建控件
        self.input_btn = tk.Button(root, text="选择 CSV 文件", command=self.select_input_file)
        self.input_btn.grid(row=0, column=0, padx=10, pady=10)

        self.output_entry_label = tk.Label(root, text="输出文件名:")
        self.output_entry_label.grid(row=0, column=1, padx=10, pady=10)
        self.output_entry = tk.Entry(root, textvariable=self.output_file, width=20)
        self.output_entry.grid(row=0, column=2, padx=10, pady=10)

        # 功能按钮
        self.process_btn = tk.Button(root, text="转换为 ts_code 格式", command=self.process_stock_codes)
        self.process_btn.grid(row=1, column=0, padx=10, pady=10, sticky="ew")

        self.txt_btn = tk.Button(root, text="导出纯文本文件", command=self.export_txt_file)
        self.txt_btn.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        self.basic_btn = tk.Button(root, text="获取基础资料", command=self.get_stock_basic)
        self.basic_btn.grid(row=1, column=2, padx=10, pady=10, sticky="ew")

        self.quit_btn = tk.Button(root, text="退出", command=root.quit)
        self.quit_btn.grid(row=2, column=0, columnspan=3, padx=10, pady=10, sticky="ew")

        # 提示标签
        self.status_label = tk.Label(root, text="请选择输入文件并设置输出文件名。")
        self.status_label.grid(row=3, column=0, columnspan=3, padx=10, pady=10)

        # Tushare API 初始化
        self.tushare_token = "30f35108e87dec2f757afd730f4709c9e2af38b468895e73c9a3312a"

    def select_input_file(self):
        """选择输入文件"""
        self.input_file = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        self.status_label.config(text=f"已选择文件: {self.input_file}")

    def process_stock_codes(self):
        """将股票代码转换为标准格式"""
        if not self.input_file:
            messagebox.showerror("错误", "未选择输入文件！")
            return

        df = pd.read_csv(self.input_file, dtype={'ts_code': str})
        if 'ts_code' not in df.columns:
            messagebox.showerror("错误", "CSV 文件中没有找到 'ts_code' 列！")
            return

        df['ts_code'] = df['ts_code'].apply(self.process_code)
        df.to_csv(self.output_file.get(), index=False)
        messagebox.showinfo("成功", f"处理完成，结果已保存到 {self.output_file.get()}。")

    @staticmethod
    def process_code(code):
        """处理单个股票代码"""
        code_part = str(code).strip().zfill(6)
        if code_part.startswith(('60', '68')):
            return f"{code_part}.SH"
        elif code_part.startswith(('00', '30')):
            return f"{code_part}.SZ"
        elif code_part.startswith(('8', '4')):
            return f"{code_part}.BJ"
        else:
            return f"{code_part}.UNKNOWN"

    def export_txt_file(self):
        """将股票代码导出为纯文本文件"""
        if not self.input_file:
            messagebox.showerror("错误", "未选择输入文件！")
            return

        df = pd.read_csv(self.input_file, dtype={'ts_code': str})
        if 'ts_code' not in df.columns:
            messagebox.showerror("错误", "CSV 文件中没有找到 'ts_code' 列！")
            return

        # 提取代码部分并去掉后缀
        codes = [code.split(".")[0].strip() for code in df['ts_code']]
        output_file = self.output_file.get().replace(".csv", ".txt")
        with open(output_file, "w") as f:
            f.write(",".join(codes))
        messagebox.showinfo("成功", f"导出完成，结果已保存到 {output_file}。")

    def get_stock_basic(self):
        """获取股票基础资料"""
        if not self.input_file:
            messagebox.showerror("错误", "未选择输入文件！")
            return

        if not self.tushare_token:
            messagebox.showerror("错误", "未设置 Tushare API Token，请先在代码中设置！")
            return

        # 初始化 Tushare API
        ts.set_token(self.tushare_token)
        pro = ts.pro_api()

        df = pd.read_csv(self.input_file, dtype={'ts_code': str})
        if 'ts_code' not in df.columns:
            messagebox.showerror("错误", "CSV 文件中没有找到 'ts_code' 列！")
            return

        # 获取基础资料
        try:
            basic_df = pro.stock_basic(fields=["ts_code", "name", "industry"])
            merged_df = pd.merge(df, basic_df, on="ts_code")
        except Exception as e:
            messagebox.showerror("错误", f"获取基础资料失败: {e}")
            return

        # 保存为带日期的文件
        date_str = datetime.now().strftime("%Y%m%d")
        output_file = f"Selected_{date_str}.csv"
        merged_df.to_csv(output_file, index=False)
        messagebox.showinfo("成功", f"基础资料已保存到 {output_file}。")


if __name__ == "__main__":
    # 设置 Tushare API Token（请替换成你的 Tushare Token）
    StockProcessingApp.tushare_token = "your_tushare_token_here"

    # 创建主窗口并启动 GUI
    root = tk.Tk()
    app = StockProcessingApp(root)
    root.mainloop()