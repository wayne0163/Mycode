import pandas as pd

def process_csv(input_file, output_file):
    """
    处理自选股 CSV 文件，将 ts_code 列中的数据改为标准的 ts_code 字段，并根据市场添加 .SZ/.SH/.BJ 后缀。

    :param input_file: 输入的 CSV 文件路径
    :param output_file: 输出的 CSV 文件路径
    """
    try:
        # 读取 CSV 文件
        df = pd.read_csv(input_file)
        
        # 检查是否有 'ts_code' 列
        if 'ts_code' not in df.columns:
            print("错误：CSV 文件中没有找到 'ts_code' 列！")
            return

        # 处理 'ts_code' 列，去掉多余的字符，并添加市场后缀
        df['ts_code'] = df['ts_code'].apply(lambda x: process_stock_code(x))

        # 保存为新的 CSV 文件
        df.to_csv(output_file, index=False)
        print(f"处理完成，结果已保存到 {output_file}。")
    except Exception as e:
        print(f"处理文件时出错：{e}")

def process_stock_code(code):
    """
    处理单个股票代码，去掉多余的字符，并根据市场添加 .SZ/.SH/.BJ 后缀。
    """
    # 去掉前缀和空格
    code_part = str(code).replace('ts_code: ', '').strip()
    
    # 根据股票代码的前几位判断市场
    if code_part.startswith('60') or code_part.startswith('68'):  # 上交所（包括科创板）
        return f"{code_part}.SH"
    elif code_part.startswith('00') or code_part.startswith('30'):  # 深交所（包括创业板）
        return f"{code_part}.SZ"
    elif code_part.startswith('8') or code_part.startswith('4'):  # 北交所
        return f"{code_part}.BJ"
    else:
        return f"{code_part}.UNKNOWN"  # 未知市场

# 示例输入输出路径
input_file = 'select3.csv'
output_file = 'select3_processed.csv'

# 调用函数处理文件
process_csv(input_file, output_file)