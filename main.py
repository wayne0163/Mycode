from gui.main_window import run_gui
from core.daily_data_manager import DailyDataManager
from core.fina_data_manager import FinaDataManager

def main():
    # 初始化数据管理
    daily_dm = DailyDataManager()
    fina_dm = FinaDataManager()
    
    # 启动 GUI 界面
    run_gui(daily_dm, fina_dm)

if __name__ == "__main__":
    main()