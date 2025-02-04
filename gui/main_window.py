import tkinter as tk
from utils.technical_analyzer import run_screening
from tkinter import messagebox  # 新增filedialog
from core.daily_data_manager import DailyDataManager
from core.fina_data_manager import FinaDataManager

def run_gui(daily_dm, fina_dm):
    root = tk.Tk()
    root.title("股票系统 v1.0")
    root.geometry("400x400")  # 调整窗口大小
    root.resizable(False, False)

    # 定义更新日线数据的函数
    def on_update_daily():
        try:
            daily_dm.update_daily_data()
            messagebox.showinfo("成功", "日线数据已更新！")
        except Exception as e:
            messagebox.showerror("错误", f"更新日线数据失败：{str(e)}")

    # 定义更新财务数据的函数
    def on_update_fina():
        try:
            fina_dm.update_financial_data()
            messagebox.showinfo("成功", "财务数据已更新！")
        except Exception as e:
            messagebox.showerror("错误", f"更新财务数据失败：{str(e)}")

    # 定义筛选函数
    def on_screen_stocks():
        try:
            result = run_screening(daily_db_path=daily_dm.daily_db)
            if result:
                messagebox.showinfo("完成", f"筛选完成！共找到 {result['count']} 只股票\n保存路径：{result['path']}")
            else:
                messagebox.showinfo("提示", "没有符合条件的股票")
        except Exception as e:
            messagebox.showerror("错误", f"筛选失败：{str(e)}")
    # 定义退出函数
    def on_exit():
        if messagebox.askyesno("退出", "确定要退出程序吗？"):
            root.quit()
    # 按钮布局（新增筛选按钮）
    tk.Button(root, text="更新日线数据", command=on_update_daily, width=20, bg="lightgray", fg="black").pack(pady=10)
    tk.Button(root, text="更新财务数据", command=on_update_fina, width=20, bg="lightgray", fg="black").pack(pady=10)
    tk.Button(root, text="自选股筛选", command=on_screen_stocks, width=20, bg="lightblue", fg="black").pack(pady=10)  # 新增按钮
    tk.Button(root, text="退出", command=on_exit, width=20, bg="lightgray", fg="black").pack(pady=10)

    # 运行主循环
    root.mainloop()

if __name__ == "__main__":
    daily_dm = DailyDataManager()
    fina_dm = FinaDataManager()
    run_gui(daily_dm, fina_dm)
