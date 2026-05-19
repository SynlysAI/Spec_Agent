import os
import glob


LOG_DIR = r"E:\spectrum_files\PROJ_PRESENTATION\evidence\01_result1\logs_raman\logs"
OUTPUT_FILE = r"E:\spectrum_files\PROJ_PRESENTATION\evidence\01_result1\logs_raman\raman_test_extracted.log"

# 实验相关日志关键词白名单，匹配到任一关键词的行将被保留
SIGNAL_PATTERNS = [
    # 请求与响应
    "JY req:",
    "body:",
    "JY status callback",
    "JY capture req accepted",
    "JY http response sent",
    "JY callback",
    "sltJyHttpReqCapture",
    "sltJyHttpCallback",
    "JY 采集流程完成",
    # 光谱采集参数
    "Actual exposure time",
    "Actual accumulation",
    "Actual kinetic",
    "Starting acquisition",
    "laser pulse",
    "laser:",
    "slider pos",
    # 自动对焦
    "对焦",
    # "粗搜索",
    # "精搜索",
    "Brightness",
    "select set max rate",
]


def is_signal(line):
    """判断日志行是否为实验相关的有效日志。"""
    return any(pattern in line for pattern in SIGNAL_PATTERNS)


def extract_test_logs(content):
    """从日志内容中提取与自动化实验相关的日志行。

    通过关键词白名单匹配，保留所有实验相关的日志，包括请求响应、
    光谱采集参数、自动对焦过程等。

    Args:
        content: 日志文件的所有行列表。

    Returns:
        实验相关的日志行列表。
    """
    return [line for line in content if is_signal(line)]


def process_all_logs(log_dir, output_file):
    """批量处理目录下所有拉曼日志文件，提取实验内容并合并输出。

    Args:
        log_dir: 日志文件所在目录路径。
        output_file: 提取结果输出文件路径。
    """
    log_files = sorted(glob.glob(os.path.join(log_dir, "*.log")))
    if not log_files:
        print(f"目录 {log_dir} 下未找到 .log 文件")
        return

    all_extracted = []
    for log_path in log_files:
        filename = os.path.basename(log_path)
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.readlines()
        extracted = extract_test_logs(content)
        if extracted:
            print(f"{filename}: 提取到 {len(extracted)} 行实验日志")
            all_extracted.append(f"{'=' * 60}\n")
            all_extracted.append(f"# 来源: {filename}\n")
            all_extracted.append(f"{'=' * 60}\n")
            all_extracted.extend(extracted)
        else:
            print(f"{filename}: 未找到实验日志")

    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(all_extracted)
    print(f"\n已写入 {len(all_extracted)} 行到 {output_file}")


if __name__ == "__main__":
    process_all_logs(LOG_DIR, OUTPUT_FILE)
