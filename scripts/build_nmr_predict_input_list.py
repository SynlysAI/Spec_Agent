"""从 Excel 汇总表构建 NMR 反推脚本批量输入列表。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd


EXCEL_PATH = Path(r"C:\Users\www59\Desktop\nmr_target_peaks.xlsx")
SHEET_NAME = "目标峰汇总"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "outputs" / "nmr_predict_inputs.xlsx"

FILE_PATH_COLUMN = "文件路径"
FILE_NAME_COLUMN = "文件名"
SPECTRUM_TYPE_COLUMN = "所属谱类型(H/C)"
SHIFT_COLUMN = "目标峰化学位移"
SPLIT_COLUMN = "峰裂分类型"


@dataclass(frozen=True)
class SpectrumRecord:
    """表示 Excel 中的一条谱图记录。"""

    sample_key: str
    spectrum_type: str
    file_path: str
    file_name: str
    shifts: str
    split_types: str


def normalize_cell_value(value: object) -> str:
    """将单元格值标准化为字符串，空值转为空字符串。

    Args:
        value: Excel 单元格原始值。

    Returns:
        适合下游脚本直接使用的字符串。
    """
    if value is None:
        return ""

    if isinstance(value, float) and math.isnan(value):
        return ""

    return str(value).strip()


def build_sample_key(file_name: str, spectrum_type: str) -> str:
    """根据文件名与谱类型生成样品归并键。

    Args:
        file_name: Excel 中的文件名。
        spectrum_type: 当前记录的谱类型，仅支持 H/C。

    Returns:
        去除末尾 H/C 标记后的样品归并键。
    """
    normalized_name = file_name.strip()
    normalized_type = spectrum_type.strip().upper()
    suffix_pattern = re.compile(
        rf"^(?P<sample>.+?)(?:\s*[-_]\s*|\s+){re.escape(normalized_type)}\s*$",
        re.IGNORECASE,
    )
    matched = suffix_pattern.match(normalized_name)
    if matched:
        return matched.group("sample").strip()
    return normalized_name


def build_spectrum_record(row: pd.Series) -> SpectrumRecord:
    """将 DataFrame 行转换为谱图记录对象。

    Args:
        row: Excel 读取后的单行记录。

    Returns:
        标准化后的谱图记录。
    """
    spectrum_type = normalize_cell_value(row.get(SPECTRUM_TYPE_COLUMN)).upper()
    file_name = normalize_cell_value(row.get(FILE_NAME_COLUMN))
    return SpectrumRecord(
        sample_key=build_sample_key(file_name=file_name, spectrum_type=spectrum_type),
        spectrum_type=spectrum_type,
        file_path=normalize_cell_value(row.get(FILE_PATH_COLUMN)),
        file_name=file_name,
        shifts=normalize_cell_value(row.get(SHIFT_COLUMN)),
        split_types=normalize_cell_value(row.get(SPLIT_COLUMN)),
    )


def load_spectrum_records(excel_path: Path, sheet_name: str) -> list[SpectrumRecord]:
    """加载 Excel 中的谱图记录。

    Args:
        excel_path: Excel 文件路径。
        sheet_name: 工作表名称。

    Returns:
        经过标准化的谱图记录列表。
    """
    dataframe = pd.read_excel(excel_path, sheet_name=sheet_name)
    records: list[SpectrumRecord] = []

    for _, row in dataframe.iterrows():
        record = build_spectrum_record(row)
        if record.spectrum_type not in {"H", "C"}:
            continue
        records.append(record)

    return records


def build_predict_input_list(records: list[SpectrumRecord]) -> list[list[str]]:
    """将谱图记录归并为反推脚本所需输入列表。

    Args:
        records: Excel 中读取出的谱图记录列表。

    Returns:
        每项结构为：
        [H谱文件路径, H谱文件名, C谱文件路径, C谱文件名, h_shifts_input, h_split_input, c_shifts_input]
        的二维列表。
    """
    grouped_records: dict[str, dict[str, list[SpectrumRecord]]] = {}
    ordered_keys: list[str] = []

    for record in records:
        if record.sample_key not in grouped_records:
            grouped_records[record.sample_key] = {"H": [], "C": []}
            ordered_keys.append(record.sample_key)
        grouped_records[record.sample_key][record.spectrum_type].append(record)

    predict_inputs: list[list[str]] = []
    for sample_key in ordered_keys:
        h_records = grouped_records[sample_key]["H"]
        c_records = grouped_records[sample_key]["C"]
        pair_count = max(len(h_records), len(c_records))

        for index in range(pair_count):
            h_record = h_records[index] if index < len(h_records) else None
            c_record = c_records[index] if index < len(c_records) else None
            predict_inputs.append([
                h_record.file_path if h_record else "",
                h_record.file_name if h_record else "",
                c_record.file_path if c_record else "",
                c_record.file_name if c_record else "",
                h_record.shifts if h_record else "",
                h_record.split_types if h_record else "",
                c_record.shifts if c_record else "",
            ])

    return predict_inputs


def export_predict_inputs_to_excel(predict_inputs: list[list[str]], output_path: Path) -> Path:
    """将反推输入列表导出为 Excel。

    Args:
        predict_inputs: 待导出的反推输入二维列表。
        output_path: Excel 输出路径。

    Returns:
        实际导出的 Excel 文件路径。
    """
    dataframe = pd.DataFrame(
        predict_inputs,
        columns=[
            "H谱文件路径",
            "H谱文件名",
            "C谱文件路径",
            "C谱文件名",
            "H谱化学位移",
            "H谱峰裂分类型",
            "C谱化学位移",
        ],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        dataframe.to_excel(output_path, index=False)
        return output_path
    except PermissionError:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fallback_path = output_path.with_name(f"{output_path.stem}_{timestamp}{output_path.suffix}")
        dataframe.to_excel(fallback_path, index=False)
        return fallback_path


def main() -> int:
    """读取 Excel 并打印批量反推输入列表。"""
    records = load_spectrum_records(excel_path=EXCEL_PATH, sheet_name=SHEET_NAME)
    predict_inputs = build_predict_input_list(records=records)
    exported_path = export_predict_inputs_to_excel(
        predict_inputs=predict_inputs,
        output_path=OUTPUT_PATH,
    )
    print(predict_inputs)
    print(f"已导出 Excel 文件: {exported_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
