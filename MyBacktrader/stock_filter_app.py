import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import sqlite3
from datetime import datetime
import os
import numpy as np # For handling potential inf values in data

class StockFilterApp:
    def __init__(self, master):
        self.master = master
        master.title("A股股票篩選工具")
        master.geometry("1200x800") # 設定視窗初始大小

        self.df = pd.DataFrame() # 儲存載入的數據
        self.filtered_df = pd.DataFrame() # 儲存篩選後的數據
        self.all_industries = [] # 儲存所有唯一的行業列表
        self.selected_industries_cache = set() # 儲存已選中的行業名稱，用於持久化選擇狀態

        # --- 檔案路徑變數 ---
        self.db_path_var = tk.StringVar(value="")
        self.basic_csv_path_var = tk.StringVar(value="")
        self.daily_table_name_var = tk.StringVar(value="daily_data") # 預設表名

        # --- GUI 介面設計 ---
        self._create_widgets()

    def _create_widgets(self):
        # 框架用於組織輸入和按鈕
        input_frame = ttk.LabelFrame(self.master, text="檔案和資料庫設定")
        input_frame.pack(padx=10, pady=10, fill="x", expand=True)

        # SQLite 資料庫路徑
        ttk.Label(input_frame, text="SQLite資料庫 (.db):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(input_frame, textvariable=self.db_path_var, width=50).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(input_frame, text="選擇檔案", command=self._browse_db_file).grid(row=0, column=2, padx=5, pady=5)

        # 股票基礎資訊 CSV 路徑
        ttk.Label(input_frame, text="股票基礎資訊 (.csv):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(input_frame, textvariable=self.basic_csv_path_var, width=50).grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(input_frame, text="選擇檔案", command=self._browse_basic_csv).grid(row=1, column=2, padx=5, pady=5)

        # 日線數據表名
        ttk.Label(input_frame, text="日線數據表名:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(input_frame, textvariable=self.daily_table_name_var, width=30).grid(row=2, column=1, padx=5, pady=5, sticky="w")

        # 載入數據按鈕
        ttk.Button(input_frame, text="載入數據", command=self._load_data_action).grid(row=3, column=0, columnspan=3, pady=10)

        input_frame.grid_columnconfigure(1, weight=1) # 讓路徑輸入框可伸縮

        # --- 篩選條件框架 ---
        filter_frame = ttk.LabelFrame(self.master, text="篩選條件")
        filter_frame.pack(padx=10, pady=10, fill="x", expand=True)

        # PE_TTM 篩選
        ttk.Label(filter_frame, text="PE_TTM 範圍:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.pe_min_var = tk.DoubleVar(value=0.1)
        self.pe_max_var = tk.DoubleVar(value=1000.0) # 初始值設高一些
        ttk.Entry(filter_frame, textvariable=self.pe_min_var, width=10).grid(row=0, column=1, padx=2, pady=5, sticky="w")
        ttk.Label(filter_frame, text="-").grid(row=0, column=2, padx=2, pady=5)
        ttk.Entry(filter_frame, textvariable=self.pe_max_var, width=10).grid(row=0, column=3, padx=2, pady=5, sticky="w")

        # PB 篩選
        ttk.Label(filter_frame, text="PB 範圍:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.pb_min_var = tk.DoubleVar(value=0.1)
        self.pb_max_var = tk.DoubleVar(value=100.0) # 初始值設高一些
        ttk.Entry(filter_frame, textvariable=self.pb_min_var, width=10).grid(row=1, column=1, padx=2, pady=5, sticky="w")
        ttk.Label(filter_frame, text="-").grid(row=1, column=2, padx=2, pady=5)
        ttk.Entry(filter_frame, textvariable=self.pb_max_var, width=10).grid(row=1, column=3, padx=2, pady=5, sticky="w")

        # Total_MV 篩選 (億元)
        ttk.Label(filter_frame, text="總市值 (億元) 範圍:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.mv_min_var = tk.DoubleVar(value=1.0)
        self.mv_max_var = tk.DoubleVar(value=10000.0) # 初始值設高一些
        ttk.Entry(filter_frame, textvariable=self.mv_min_var, width=10).grid(row=2, column=1, padx=2, pady=5, sticky="w")
        ttk.Label(filter_frame, text="-").grid(row=2, column=2, padx=2, pady=5)
        ttk.Entry(filter_frame, textvariable=self.mv_max_var, width=10).grid(row=2, column=3, padx=2, pady=5, sticky="w")

        # 行業篩選 (使用Listbox 和 搜索框)
        ttk.Label(filter_frame, text="選擇行業:").grid(row=0, column=4, padx=5, pady=5, sticky="nw")
        
        # 行業搜索框
        self.industry_search_var = tk.StringVar()
        self.industry_search_entry = ttk.Entry(filter_frame, textvariable=self.industry_search_var, width=25)
        self.industry_search_entry.grid(row=0, column=5, padx=5, pady=2, sticky="ew")
        # 綁定按鍵釋放事件，實時過濾行業列表
        self.industry_search_entry.bind("<KeyRelease>", self._filter_industries)

        self.industry_listbox = tk.Listbox(filter_frame, selectmode=tk.MULTIPLE, height=6,
                                           selectbackground="blue", selectforeground="white") # 設置選中背景色
        self.industry_listbox.grid(row=1, column=5, rowspan=2, padx=5, pady=5, sticky="nsew")
        industry_scrollbar = ttk.Scrollbar(filter_frame, orient="vertical", command=self.industry_listbox.yview)
        industry_scrollbar.grid(row=1, column=6, rowspan=2, sticky="ns")
        self.industry_listbox.config(yscrollcommand=industry_scrollbar.set)
        filter_frame.grid_columnconfigure(5, weight=1) # 讓行業列表可伸縮
        filter_frame.grid_rowconfigure(1, weight=1) # 讓行業列表高度可伸縮

        # 篩選按鈕
        ttk.Button(filter_frame, text="篩選股票", command=self._apply_filters).grid(row=3, column=0, columnspan=7, pady=10)

        # --- 結果顯示框架 (Treeview) ---
        result_frame = ttk.LabelFrame(self.master, text="篩選結果")
        result_frame.pack(padx=10, pady=10, fill="both", expand=True)

        self.tree = ttk.Treeview(result_frame, columns=('ts_code', 'name', 'industry', 'close', 'pe_ttm', 'pb', 'total_mv_billion', 'trade_date'), show='headings')
        self.tree.pack(fill="both", expand=True)

        # 定義列標題
        self.tree.heading('ts_code', text='股票代碼')
        self.tree.heading('name', text='名稱')
        self.tree.heading('industry', text='行業')
        self.tree.heading('close', text='收盤價')
        self.tree.heading('pe_ttm', text='PE_TTM')
        self.tree.heading('pb', text='PB')
        self.tree.heading('total_mv_billion', text='總市值(億元)')
        self.tree.heading('trade_date', text='交易日期')

        # 定義列寬
        self.tree.column('ts_code', width=100, anchor='center')
        self.tree.column('name', width=120, anchor='center')
        self.tree.column('industry', width=120, anchor='center')
        self.tree.column('close', width=80, anchor='center')
        self.tree.column('pe_ttm', width=80, anchor='center')
        self.tree.column('pb', width=80, anchor='center')
        self.tree.column('total_mv_billion', width=120, anchor='center')
        self.tree.column('trade_date', width=100, anchor='center')

        # 捲軸
        tree_scrollbar_y = ttk.Scrollbar(self.tree, orient="vertical", command=self.tree.yview)
        tree_scrollbar_y.pack(side="right", fill="y")
        self.tree.config(yscrollcommand=tree_scrollbar_y.set)

        tree_scrollbar_x = ttk.Scrollbar(self.tree, orient="horizontal", command=self.tree.xview)
        tree_scrollbar_x.pack(side="bottom", fill="x")
        self.tree.config(xscrollcommand=tree_scrollbar_x.set)

        # 保存結果按鈕
        ttk.Button(self.master, text="保存為股票池CSV", command=self._save_filtered_data).pack(pady=10)

    def _browse_db_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("SQLite databases", "*.db")])
        if file_path:
            self.db_path_var.set(file_path)

    def _browse_basic_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if file_path:
            self.basic_csv_path_var.set(file_path)

    def _load_data_action(self):
        db_file = self.db_path_var.get()
        daily_table = self.daily_table_name_var.get()
        basic_csv = self.basic_csv_path_var.get()

        if not db_file or not basic_csv:
            messagebox.showerror("錯誤", "請選擇SQLite資料庫和股票基礎資訊CSV檔案。")
            return

        if not daily_table:
            messagebox.showerror("錯誤", "請輸入日線數據表名。")
            return

        try:
            self.df = self._load_data(db_file, daily_table, basic_csv)
            if not self.df.empty:
                messagebox.showinfo("成功", f"數據載入完成！共 {len(self.df)} 支股票。")
                self.all_industries = sorted(self.df['industry'].dropna().unique().tolist())
                self._populate_industry_listbox(self.all_industries) # 初始填充所有行業
                self._update_slider_ranges() # 更新篩選範圍的預設值和實際範圍
                self._apply_filters() # 載入後預設篩選一次
            else:
                messagebox.showwarning("警告", "未能載入任何數據，請檢查檔案內容和表名。")
        except Exception as e:
            messagebox.showerror("錯誤", f"載入數據時發生錯誤: {e}")

    def _load_data(self, db_file, daily_table, basic_csv):
        conn = None
        try:
            conn = sqlite3.connect(db_file)

            # 1. 從SQLite資料庫載入股票最新的市場資料 (包含pe_ttm, pb, total_mv)
            query_latest_fundamentals = f"""
                SELECT
                    t1.ts_code,
                    t1.trade_date,
                    t1.open,
                    t1.high,
                    t1.low,
                    t1.close,
                    t1.vol,
                    t1.pe_ttm,
                    t1.pb,
                    t1.total_mv
                FROM
                    {daily_table} t1
                INNER JOIN (
                    SELECT
                        ts_code,
                        MAX(trade_date) AS max_trade_date
                    FROM
                        {daily_table}
                    GROUP BY
                        ts_code
                ) t2 ON t1.ts_code = t2.ts_code AND t1.trade_date = t2.max_trade_date
            """
            df_daily_latest = pd.read_sql_query(query_latest_fundamentals, conn)

            # 確保估值資料是數值類型，將無效值轉換為NaN
            for col in ['pe_ttm', 'pb', 'total_mv']:
                df_daily_latest[col] = pd.to_numeric(df_daily_latest[col], errors='coerce')


            # 2. 從CSV檔案載入股票基礎資訊
            if not os.path.exists(basic_csv):
                raise FileNotFoundError(f"股票基礎資訊文件 '{basic_csv}' 不存在。")

            df_basic = pd.read_csv(basic_csv)
            # 確保ts_code列類型一致，以便合併
            df_basic['ts_code'] = df_basic['ts_code'].astype(str)
            df_daily_latest['ts_code'] = df_daily_latest['ts_code'].astype(str)

            # 3. 合併資料
            df_merged = pd.merge(df_daily_latest, df_basic, on='ts_code', how='inner')

            # 計算總市值 (億元)
            df_merged['total_mv_billion'] = df_merged['total_mv'] / 10000.0 # 假設total_mv是萬元

            return df_merged

        finally:
            if conn:
                conn.close()

    def _populate_industry_listbox(self, industries_to_display):
        # 獲取當前選中的行業，用於持久化
        current_selection_names = {self.industry_listbox.get(i) for i in self.industry_listbox.curselection()}
        self.selected_industries_cache.update(current_selection_names) # 更新緩存

        self.industry_listbox.delete(0, tk.END) # 清空現有項目

        for industry in industries_to_display:
            self.industry_listbox.insert(tk.END, industry)

        # 重新選擇之前被選中的項目
        for i, industry in enumerate(industries_to_display):
            if industry in self.selected_industries_cache:
                self.industry_listbox.selection_set(i)

    def _filter_industries(self, event=None):
        search_text = self.industry_search_var.get().lower()
        if not self.all_industries: # 如果數據未載入
            return

        # 過濾行業列表
        filtered_industries = [
            industry for industry in self.all_industries
            if search_text in industry.lower()
        ]
        self._populate_industry_listbox(filtered_industries)


    def _update_slider_ranges(self):
        # 根據載入的數據更新篩選範圍的預設值和實際範圍
        if self.df.empty:
            return

        # PE_TTM
        clean_pe = self.df['pe_ttm'].dropna().replace([np.inf, -np.inf], np.nan).dropna()
        if not clean_pe.empty:
            min_pe, max_pe = float(clean_pe.min()), float(clean_pe.max())
            self.pe_min_var.set(max(0.1, round(min_pe, 1)))
            self.pe_max_var.set(round(max_pe, 1))

        # PB
        clean_pb = self.df['pb'].dropna().replace([np.inf, -np.inf], np.nan).dropna()
        if not clean_pb.empty:
            min_pb, max_pb = float(clean_pb.min()), float(clean_pb.max())
            self.pb_min_var.set(max(0.1, round(min_pb, 1)))
            self.pb_max_var.set(round(max_pb, 1))

        # Total_MV (億元)
        clean_mv = self.df['total_mv_billion'].dropna().replace([np.inf, -np.inf], np.nan).dropna()
        if not clean_mv.empty:
            min_mv, max_mv = float(clean_mv.min()), float(clean_mv.max())
            self.mv_min_var.set(round(min_mv, 0))
            self.mv_max_var.set(round(max_mv, 0))


    def _apply_filters(self):
        if self.df.empty:
            messagebox.showwarning("警告", "請先載入數據。")
            return

        filtered_df = self.df.copy()

        try:
            # PE_TTM 篩選
            pe_min = self.pe_min_var.get()
            pe_max = self.pe_max_var.get()
            filtered_df = filtered_df[
                (filtered_df['pe_ttm'].notna()) &
                (filtered_df['pe_ttm'] >= pe_min) &
                (filtered_df['pe_ttm'] <= pe_max)
            ]

            # PB 篩選
            pb_min = self.pb_min_var.get()
            pb_max = self.pb_max_var.get()
            filtered_df = filtered_df[
                (filtered_df['pb'].notna()) &
                (filtered_df['pb'] >= pb_min) &
                (filtered_df['pb'] <= pb_max)
            ]

            # Total_MV 篩選 (億元)
            mv_min = self.mv_min_var.get()
            mv_max = self.mv_max_var.get()
            filtered_df = filtered_df[
                (filtered_df['total_mv_billion'].notna()) &
                (filtered_df['total_mv_billion'] >= mv_min) &
                (filtered_df['total_mv_billion'] <= mv_max)
            ]

            # 行業篩選
            # 在應用篩選前，先將當前 Listbox 中的選中項目更新到緩存中
            current_listbox_selection = {self.industry_listbox.get(i) for i in self.industry_listbox.curselection()}
            self.selected_industries_cache = current_listbox_selection


            if self.selected_industries_cache: # 使用緩存的選中行業
                filtered_df = filtered_df[filtered_df['industry'].isin(list(self.selected_industries_cache))]

            self.filtered_df = filtered_df
            self._update_treeview()
            messagebox.showinfo("篩選完成", f"已篩選出 {len(self.filtered_df)} 支股票。")

        except ValueError:
            messagebox.showerror("輸入錯誤", "請確保PE、PB、總市值範圍輸入的是有效數字。")
        except Exception as e:
            messagebox.showerror("篩選錯誤", f"篩選過程中發生錯誤: {e}")


    def _update_treeview(self):
        # 清空 Treeview 中的所有行
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 插入篩選後的數據
        for index, row in self.filtered_df.iterrows():
            self.tree.insert("", tk.END, values=(
                row['ts_code'],
                row['name'],
                row['industry'],
                f"{row['close']:.2f}",
                f"{row['pe_ttm']:.2f}" if pd.notna(row['pe_ttm']) else "N/A",
                f"{row['pb']:.2f}" if pd.notna(row['pb']) else "N/A",
                f"{row['total_mv_billion']:.2f}" if pd.notna(row['total_mv_billion']) else "N/A",
                row['trade_date']
            ))

    def _save_filtered_data(self):
        if self.filtered_df.empty:
            messagebox.showwarning("警告", "沒有篩選結果可以保存。")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"stock_pool_{timestamp}.csv"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_filename,
            filetypes=[("CSV files", "*.csv")]
        )

        if file_path:
            try:
                # 保存 self.filtered_df 中的所有列，用於核對
                self.filtered_df.to_csv(file_path, index=False, encoding='utf-8-sig')
                messagebox.showinfo("保存成功", f"篩選結果已保存到:\n{file_path}")
            except Exception as e:
                messagebox.showerror("保存失敗", f"保存檔案時發生錯誤: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = StockFilterApp(root)
    root.mainloop()

