"""批量执行 NMR 反向预测并导出结果表。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.nmr_server_service import nmr_server_service


DEFAULT_INPUT_PATH = Path(r"C:\Users\www59\Desktop\nmr_predict_inputs.xlsx")
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "nmr_predict_results.xlsx"
RESULT_SHEET_NAME = "预测结果"
REQUIRED_COLUMNS = [
    "H谱化学位移",
    "H谱峰裂分类型",
    "C谱化学位移",
]


class NmrPredictServiceProtocol(Protocol):
    """批量预测所依赖的 NMR 服务协议。"""

    def reverse_predict(
        self,
        h_shifts_input: str,
        h_split_input: str,
        c_shifts_input: str,
        formula: str,
        allowed_elements: str,
        candidates: str,
    ) -> list[dict]:
        """执行反向预测。"""

    def database_search(
        self,
        h_shifts_input: str,
        h_split_input: str,
        c_shifts_input: str,
        num_search: int,
        topk: int,
        allowed_elements: str,
    ) -> list[dict]:
        """执行数据库检索。"""


def normalize_cell_value(value: object) -> str:
    """将表格单元格值标准化为字符串。

    Args:
        value: 原始单元格值。

    Returns:
        去除首尾空白后的字符串；空值返回空字符串。
    """
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def ensure_required_columns(dataframe: pd.DataFrame) -> None:
    """校验输入表是否包含批量预测所需列。

    Args:
        dataframe: 输入 Excel 读取出的数据表。

    Raises:
        ValueError: 缺少关键列时抛出异常。
    """
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing_columns:
        raise ValueError(f"输入表缺少必要列: {', '.join(missing_columns)}")


def serialize_json(value: Any) -> str:
    """将结果对象序列化为适合写入 Excel 的 JSON 字符串。

    Args:
        value: 待序列化的对象。

    Returns:
        JSON 字符串。
    """
    return json.dumps(value, ensure_ascii=False)


def build_prediction_payload(
    row: pd.Series,
    service: NmrPredictServiceProtocol,
    num_search: int,
    topk: int,
    formula: str,
    allowed_elements: str,
    candidates: str,
) -> dict[str, str]:
    """执行单行反推并构造结果字段。

    Args:
        row: 输入表中的单行记录。
        service: NMR 预测服务对象。
        num_search: 数据库搜索候选检索数量。
        topk: 数据库搜索返回条数。
        formula: 反推约束中的分子式。
        allowed_elements: 允许元素约束，逗号分隔。
        candidates: 候选 SMILES 约束，逗号分隔。

    Returns:
        包含四个新增结果列的字典。
    """
    h_shifts_input = normalize_cell_value(row.get("H谱化学位移"))
    h_split_input = normalize_cell_value(row.get("H谱峰裂分类型"))
    c_shifts_input = normalize_cell_value(row.get("C谱化学位移"))

    try:
        reverse_res = service.reverse_predict(
            h_shifts_input=h_shifts_input,
            h_split_input=h_split_input,
            c_shifts_input=c_shifts_input,
            formula=formula,
            allowed_elements=allowed_elements,
            candidates=candidates,
        )
        # 暂时只取前10个
        reverse_res = reverse_res[:10]
        database_res = service.database_search(
            h_shifts_input=h_shifts_input,
            h_split_input=h_split_input,
            c_shifts_input=c_shifts_input,
            num_search=num_search,
            topk=topk,
            allowed_elements=allowed_elements,
        )
        reverse_predict_smiles = [info.get("smiles", "") for info in reverse_res]
        database_predict_smiles = [info.get("smiles", "") for info in database_res]
        print(reverse_predict_smiles)
        print(database_predict_smiles)
        return {
            "reverse_predict_smiles": serialize_json(reverse_predict_smiles),
            "database_predict_smiles": serialize_json(database_predict_smiles),
            "reverse_res": serialize_json(reverse_res),
            "database_res": serialize_json(database_res),
        }
    except Exception as exc:
        error_info = {"error": str(exc)}
        return {
            "reverse_predict_smiles": serialize_json([]),
            "database_predict_smiles": serialize_json([]),
            "reverse_res": serialize_json(error_info),
            "database_res": serialize_json(error_info),
        }


def build_result_dataframe(
    dataframe: pd.DataFrame,
    service: NmrPredictServiceProtocol,
    num_search: int,
    topk: int,
    formula: str,
    allowed_elements: str,
    candidates: str,
) -> pd.DataFrame:
    """基于输入表构造带预测结果的新数据表。

    Args:
        dataframe: 输入 Excel 读取出的数据表。
        service: NMR 预测服务对象。
        num_search: 数据库搜索候选检索数量。
        topk: 数据库搜索返回条数。
        formula: 反推约束中的分子式。
        allowed_elements: 允许元素约束，逗号分隔。
        candidates: 候选 SMILES 约束，逗号分隔。

    Returns:
        在原表后追加预测列后的新数据表。
    """
    ensure_required_columns(dataframe)

    result_rows: list[dict[str, str]] = []
    for _, row in dataframe.iterrows():
        result_rows.append(build_prediction_payload(
            row=row,
            service=service,
            num_search=num_search,
            topk=topk,
            formula=formula,
            allowed_elements=allowed_elements,
            candidates=candidates,
        ))

    result_dataframe = dataframe.copy()
    result_columns = pd.DataFrame(result_rows, index=result_dataframe.index)
    return pd.concat([result_dataframe, result_columns], axis=1)


def export_result_excel(dataframe: pd.DataFrame, output_path: Path) -> Path:
    """导出批量预测结果到新的 Excel 文件。

    Args:
        dataframe: 待导出的结果数据表。
        output_path: 目标输出路径。

    Returns:
        实际导出的文件路径。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        dataframe.to_excel(output_path, sheet_name=RESULT_SHEET_NAME, index=False)
        return output_path
    except PermissionError:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fallback_path = output_path.with_name(f"{output_path.stem}_{timestamp}{output_path.suffix}")
        dataframe.to_excel(fallback_path, sheet_name=RESULT_SHEET_NAME, index=False)
        return fallback_path


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="批量执行 NMR 反向预测并导出结果表")
    parser.add_argument(
        "--input",
        dest="input_path",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="输入 Excel 路径",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="输出 Excel 路径",
    )
    parser.add_argument(
        "--sheet-name",
        dest="sheet_name",
        default=0,
        help="输入工作表名称或索引，默认读取第一个工作表",
    )
    parser.add_argument(
        "--formula",
        default="",
        help="反向预测的分子式约束",
    )
    parser.add_argument(
        "--allowed-elements",
        default="",
        help="允许元素约束，逗号分隔",
    )
    parser.add_argument(
        "--candidates",
        default="",
        help="候选 SMILES 约束，逗号分隔",
    )
    parser.add_argument(
        "--num-search",
        type=int,
        default=500,
        help="数据库搜索候选检索数量",
    )
    parser.add_argument(
        "--topk",
        type=int,
        default=10,
        help="数据库搜索返回条数",
    )
    return parser.parse_args()


def main() -> int:
    """执行批量 NMR 反推并导出结果。"""
    args = parse_args()
    dataframe = pd.read_excel(args.input_path, sheet_name=args.sheet_name)
    result_dataframe = build_result_dataframe(
        dataframe=dataframe,
        service=nmr_server_service,
        num_search=args.num_search,
        topk=args.topk,
        formula=args.formula,
        allowed_elements=args.allowed_elements,
        candidates=args.candidates,
    )
    exported_path = export_result_excel(dataframe=result_dataframe, output_path=args.output_path)
    print(f"已处理 {len(result_dataframe)} 条记录")
    print(f"结果文件已导出到: {exported_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
