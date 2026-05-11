"""批量导出 NMR 目标峰信息到 Excel。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.nmr.export_service import build_target_peak_export_row, normalize_nucleus_type
from app.modules.nmr.service import load_nmr_basic_info
from app.modules.nmr.workflow import default_peak_detection_params, run_nmr_analysis


ROOT_DIRS = [
    r"E:\spectrum_files\nmr\自测0508\氢谱",
    r"E:\spectrum_files\nmr\自测0508\碳谱",
]
"""待扫描的根目录列表；后续新增目录时直接在这里追加。"""

OUTPUT_PATH = str(PROJECT_ROOT / "outputs" / "nmr_target_peaks(自测0508).xlsx")
"""导出结果路径。"""


def _is_loadable_nmr_sample_dir(path: Path) -> bool:
    """判断目录是否可被现有 NMR 读取链路直接加载。"""
    if not path.is_dir():
        return False

    try:
        load_nmr_basic_info(str(path))
    except Exception:
        return False
    return True


def iter_nmr_sample_dirs(root_dirs: Iterable[str]) -> list[str]:
    """遍历根目录下所有可分析的 NMR 样品目录。"""
    sample_dirs: list[str] = []
    seen_paths: set[str] = set()

    for root_dir in root_dirs:
        root_path = Path(root_dir)
        if not root_path.exists() or not root_path.is_dir():
            continue

        if _is_loadable_nmr_sample_dir(root_path):
            resolved = str(root_path.resolve())
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                sample_dirs.append(resolved)
            continue

        for child in sorted(root_path.iterdir(), key=lambda item: item.name):
            if not _is_loadable_nmr_sample_dir(child):
                continue
            resolved = str(child.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            sample_dirs.append(resolved)

    return sample_dirs


def detect_nucleus_type(sample_path: str) -> str:
    """读取样品核类型并标准化为 H/C。"""
    _, _, metadata = load_nmr_basic_info(sample_path)
    return normalize_nucleus_type(metadata.get("nucleus"))


def build_peak_detection_params(sample_path: str) -> dict[str, object]:
    """根据样品核类型选择默认峰检测参数。"""
    nucleus_type = detect_nucleus_type(sample_path)
    nucleus = "13C" if nucleus_type == "C" else "1H"
    return default_peak_detection_params(nucleus=nucleus)


def export_nmr_target_peaks(root_dirs: list[str], output_path: str) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """批量分析并导出 NMR 目标峰信息。"""
    rows: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    for sample_path in iter_nmr_sample_dirs(root_dirs):
        try:
            params = build_peak_detection_params(sample_path)
            result = run_nmr_analysis(
                input_path=sample_path,
                peak_detection_params=params,
            )
            if result.get("errors"):
                errors.append({
                    "文件路径": sample_path,
                    "错误信息": "；".join(str(item) for item in result["errors"]),
                })
                continue

            nmr_results = result.get("structured_data", {}).get("nmr_results", [])
            if not nmr_results:
                errors.append({
                    "文件路径": sample_path,
                    "错误信息": "未返回 nmr_results",
                })
                continue

            rows.append(build_target_peak_export_row(sample_path, nmr_results[0]))
        except Exception as exc:
            errors.append({
                "文件路径": sample_path,
                "错误信息": str(exc),
            })

    dataframe = pd.DataFrame(rows, columns=[
        "文件路径",
        "文件名",
        "所属谱类型(H/C)",
        "溶剂",
        "目标峰化学位移",
        "峰裂分类型",
        "全部峰信息JSON",
    ])
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with pd.ExcelWriter(output_file) as writer:
            dataframe.to_excel(writer, sheet_name="目标峰汇总", index=False)
            if errors:
                pd.DataFrame(errors).to_excel(writer, sheet_name="异常记录", index=False)
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "导出 .xlsx 需要安装 openpyxl 或 xlsxwriter。"
        ) from exc

    return dataframe, errors


def main() -> int:
    """执行批量导出脚本。"""
    dataframe, errors = export_nmr_target_peaks(ROOT_DIRS, OUTPUT_PATH)
    print(f"已导出 {len(dataframe)} 条记录到: {OUTPUT_PATH}")
    if errors:
        print(f"另有 {len(errors)} 条异常记录已写入 Excel 的“异常记录”工作表。")
    else:
        print("未发现异常样本。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"脚本执行失败: {exc}")
        if sys.stdin.isatty():
            input("按回车键退出...")
        raise
