"""报告写入通用服务。"""

from __future__ import annotations

import os


def save_text_report(output_dir: str, sample_name: str, report_content: str) -> str:
    """将文本报告保存到指定样品目录。"""
    sample_output_dir = os.path.join(output_dir, sample_name)
    os.makedirs(sample_output_dir, exist_ok=True)

    report_file_path = os.path.join(sample_output_dir, f"{sample_name}_report.txt")
    with open(report_file_path, "w", encoding="utf-8") as file:
        file.write(report_content)
    return report_file_path
