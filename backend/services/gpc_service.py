import json
import os
from typing import Optional

import pandas as pd

from config import GLOBAL_CONFIG


TEMP_UPLOAD_DIR = "temp"


def save_uploaded_file(uploaded_file, temp_dir: str = TEMP_UPLOAD_DIR) -> str | None:
    """将 Streamlit 上传文件保存到本地临时目录。

    Args:
        uploaded_file: `st.file_uploader()` 返回的文件对象。
        temp_dir: 临时目录路径，默认为项目内的 `temp`。

    Returns:
        保存后的文件路径；当未上传文件时返回 `None`。
    """
    if uploaded_file is None:
        return None

    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, uploaded_file.name)
    with open(file_path, "wb") as file:
        file.write(uploaded_file.getbuffer())
    return file_path


def preview_uploaded_curve(curve_path: str) -> pd.DataFrame:
    """读取上传的 GPC 曲线文件用于快速预览。

    Args:
        curve_path: 已保存到本地的曲线文件路径。

    Returns:
        包含 `rt` 和 `intensity` 两列的 DataFrame。
    """
    return pd.read_csv(curve_path, sep="\t", header=None, names=["rt", "intensity"])


def get_calibration_curves_path() -> str:
    """获取 GPC 校准曲线目录。"""
    return GLOBAL_CONFIG["data_storage"]["calibration_curves"]


def list_calibration_curve_files() -> list[str]:
    """列出当前校准曲线目录中的全部 JSON 文件名。

    Returns:
        已排序的校准曲线文件名列表。
    """
    calibration_curves_path = get_calibration_curves_path()
    os.makedirs(calibration_curves_path, exist_ok=True)
    return sorted([file_name for file_name in os.listdir(calibration_curves_path) if file_name.endswith(".json")])


def load_calibration_curve(file_name: str) -> dict:
    """加载指定的校准曲线 JSON 数据。

    Args:
        file_name: 校准曲线文件名。

    Returns:
        反序列化后的校准曲线字典。
    """
    file_path = os.path.join(get_calibration_curves_path(), file_name)
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_calibration_curve(curve_data: dict, file_name: str, metadata: dict) -> str:
    """保存校准曲线及其元数据。

    Args:
        curve_data: 从 PDF 提取的校准曲线原始数据。
        file_name: 目标文件名（不含扩展名）。
        metadata: 需要附加到曲线数据中的元信息。

    Returns:
        保存后的 JSON 文件路径。
    """
    payload = dict(curve_data)
    payload["metadata"] = metadata

    save_path = os.path.join(get_calibration_curves_path(), f"{file_name}.json")
    with open(save_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return save_path


def delete_calibration_curve(file_name: str):
    """删除指定的校准曲线文件。

    Args:
        file_name: 需要删除的校准曲线文件名。
    """
    file_path = os.path.join(get_calibration_curves_path(), file_name)
    if os.path.exists(file_path):
        os.remove(file_path)


def compute_gpc_errors(agent_data: dict, pdf_data: dict) -> dict:
    """计算 Agent 提取的分子量参数与 PDF 报告数据之间的误差。

    统一封装 Mn/Mw/Mz/PDI 四项误差百分比计算，供 Streamlit 界面
    和批量测试报告共用，避免重复实现。

    Args:
        agent_data: Agent 计算结果，需包含 ``mn``、``mw``、``mz``、``pdi`` 键。
        pdf_data: PDF 报告提取结果，需包含 ``Mn``、``Mw``、``Mz``、``多分散性`` 键。

    Returns:
        误差字典，键为 ``mn_error``、``mw_error``、``mz_error``、``pdi_error``；
        无法计算时对应值为 ``None``。
    """
    def _pct_error(agent_val, ref_val) -> Optional[float]:
        if ref_val and agent_val:
            return abs((agent_val - ref_val) / ref_val * 100)
        return None

    return {
        "mn_error": _pct_error(agent_data.get("mn"), pdf_data.get("Mn")),
        "mw_error": _pct_error(agent_data.get("mw"), pdf_data.get("Mw")),
        "mz_error": _pct_error(agent_data.get("mz"), pdf_data.get("Mz")),
        "pdi_error": _pct_error(agent_data.get("pdi"), pdf_data.get("多分散性")),
    }


def run_gpc_analysis(
    path: str,
    detect_mode: str,
    manual_interval: list | None,
    *,
    three_color_arw_paths: tuple[str, str, str] | list[str] | None = None,
    calibration_file_path: str | None = None,
    comparison_report_pdf_path: str | None = None,
) -> dict:
    """执行 GPC 工作流分析，返回统一结构的结果字典。

    Args:
        path: 输入的文件路径或目录路径。
        detect_mode: 峰检测模式，支持 `auto` 和 `manual`。
        manual_interval: 手动积分区间，仅在手动模式下使用。
        three_color_arw_paths: 可选。三条三色 `.arw` 的完整路径，顺序为 (绿, 红, 白)。
        calibration_file_path: 可选。校准表 `.json` 或 `.pdf`。
        comparison_report_pdf_path: 可选。用于与 Agent 结果对照的 GPC 测试报告 PDF。

    Returns:
        包含以下键的字典：
          - ``analysis_results``: 每个文件的分析结果列表（GPC 工作流产出，向后兼容）；
          - ``text_report``: Markdown 格式的完整文字报告；
          - ``errors``: 错误列表；
          - ``metadata``: 元信息。
    """
    from agents.langraph_gpc_agent import run_gpc_analysis as _agent_run_gpc

    out = _agent_run_gpc(
        input_path=path,
        detect_mode=detect_mode,
        manual_interval=manual_interval,
        three_color_arw_paths=three_color_arw_paths,
        calibration_file_path=calibration_file_path,
        comparison_report_pdf_path=comparison_report_pdf_path,
        enable_llm=False,
    )
    # 为 Streamlit 前端提供向后兼容的快捷键 analysis_results
    out["analysis_results"] = out.get("structured_data", {}).get("analysis_results", [])
    return out
