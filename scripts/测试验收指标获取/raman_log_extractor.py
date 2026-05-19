import os
import glob


LOG_DIR = r"E:\spectrum_files\PROJ_PRESENTATION\evidence\01_result1\logs_raman\logs"
OUTPUT_FILE = r"E:\spectrum_files\PROJ_PRESENTATION\evidence\01_result1\logs_raman\raman_test_extracted.log"

# 无噪音日志过滤关键词，匹配到任一关键词的行将被丢弃
NOISE_PATTERNS = [
    "usbCnt_new - connect",
    "main_window: QEvent::WindowDeactivate",
    "onWriteComplete",
    "--usb write:",
    "Temperature has stabilized",
]

# 优先保留关键词，匹配到任一关键词的行将始终保留，不受噪音过滤和 body 范围限制
NEED_PATTERNS = [
    "对焦",
]


def is_needed(line):
    """判断日志行是否为需要优先保留的有效日志。"""
    return any(pattern in line for pattern in NEED_PATTERNS)


def is_noise(line):
    """判断日志行是否为无用的噪音日志。优先保留的行不会被判定为噪音。"""
    if is_needed(line):
        return False
    return any(pattern in line for pattern in NOISE_PATTERNS)


def extract_test_logs(content):
    """从日志内容中提取与测试有关的片段，并过滤噪音行。

    通过定位包含 body: "{ 的行，成对提取相邻两个 body 行之间的所有日志，
    这些片段对应一次完整的拉曼光谱测试采集过程。

    Args:
        content: 日志文件的所有行列表。

    Returns:
        过滤噪音后的测试相关日志行列表。
    """

    body_indices = [i for i, line in enumerate(content) if 'body: "{' in line]

    # 构建 body 范围内的行号集合
    body_range_indices = set()
    for i in range(0, len(body_indices) - 1):
        body_range_indices.update(range(body_indices[i], body_indices[i + 1]))

    extracted = []
    # 1. 提取相邻 body 行之间的测试日志（噪音过滤）
    for i in range(0, len(body_indices) - 1):
        start = body_indices[i]
        end = body_indices[i + 1]
        extracted.extend(line for line in content[start:end] if not is_noise(line))

    # 2. 补充收集 body 范围外匹配 NEED_PATTERNS 的行
    extracted_ids = {id(line) for line in extracted}
    for idx, line in enumerate(content):
        if idx not in body_range_indices and is_needed(line) and id(line) not in extracted_ids:
            extracted.append(line)

    return extracted


def process_all_logs(log_dir, output_file):
    """批量处理目录下所有拉曼日志文件，提取测试内容并合并输出。

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
            print(f"{filename}: 提取到 {len(extracted)} 行测试日志")
            all_extracted.append(f"{'=' * 60}\n")
            all_extracted.append(f"# 来源: {filename}\n")
            all_extracted.append(f"{'=' * 60}\n")
            all_extracted.extend(extracted)
        else:
            print(f"{filename}: 未找到测试日志")

    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(all_extracted)
    print(f"\n已写入 {len(all_extracted)} 行到 {output_file}")


if __name__ == "__main__":
    process_all_logs(LOG_DIR, OUTPUT_FILE)
