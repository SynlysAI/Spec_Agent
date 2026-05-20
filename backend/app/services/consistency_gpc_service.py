"""GPC 设备重复性评测服务。"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from app.schemas.consistency import ConsistencyDeviceRunItem, ConsistencyGroupResultItem
from app.services.consistency_common import DEVICE_LABELS, average, build_artifact, calc_cv, format_number, safe_float


def _get_sample_code(sample_dir: str) -> str | None:
    """从样品目录 JSON 中提取样品组编码。"""
    json_files = sorted(file_name for file_name in os.listdir(sample_dir) if file_name.endswith(".json"))
    if not json_files:
        return None
    json_path = os.path.join(sample_dir, json_files[0])
    with open(json_path, "r", encoding="utf-8") as file:
        data = json.load(file)
    code = str(data.get("code", "")).strip()
    return code.rsplit("_", 1)[0] if "_" in code else code


def _find_arw_file(sample_dir: str) -> str | None:
    """查找样品目录中的 `.arw` 文件。"""
    for file_name in sorted(os.listdir(sample_dir)):
        if file_name.lower().endswith(".arw"):
            return os.path.join(sample_dir, file_name)
    return None


def _extract_mw_mn(arw_path: str) -> dict[str, Any]:
    """执行 GPC 分析并提取 Mw/Mn。"""
    try:
        from app.modules.gpc.workflow import run_gpc_analysis

        result = run_gpc_analysis(arw_path)
        analysis_results = result.get("structured_data", {}).get("analysis_results", [])
        if not analysis_results:
            return {"error": "解析结果为空"}
        molecular_parameters = analysis_results[0].get("molecular_parameters", {})
        mw = safe_float(molecular_parameters.get("mw"))
        mn = safe_float(molecular_parameters.get("mn"))
        if mw is None or mn is None:
            return {
                "error": f"分子量缺失: mw={molecular_parameters.get('mw')}, mn={molecular_parameters.get('mn')}",
            }
        return {"mw": mw, "mn": mn}
    except Exception as exc:
        return {"error": str(exc)}


def run_gpc_consistency(data_path: str, output_dir: Path) -> ConsistencyDeviceRunItem:
    """执行 GPC 设备重复性评测。

    Args:
        data_path: 数据目录路径。
        output_dir: 设备输出目录。

    Returns:
        设备级结果对象。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    if not os.path.isdir(data_path):
        report_text = f"# GPC 一致性测试报告\n\n数据目录不存在：`{data_path}`\n"
        report_path = output_dir / "gpc_consistency_report.md"
        report_path.write_text(report_text, encoding="utf-8")
        return ConsistencyDeviceRunItem(
            device_type="gpc",
            device_label=DEVICE_LABELS["gpc"],
            status="FAILED",
            duration_seconds=0.0,
            summary_metrics={"group_count": 0},
            group_results=[],
            text_report=report_text,
            artifacts=[build_artifact(report_path)],
            error_message=f"数据目录不存在: {data_path}",
        )

    sample_dirs = sorted(
        directory_name
        for directory_name in os.listdir(data_path)
        if os.path.isdir(os.path.join(data_path, directory_name))
    )
    groups: dict[str, list[str]] = defaultdict(list)
    for directory_name in sample_dirs:
        full_path = os.path.join(data_path, directory_name)
        group_name = _get_sample_code(full_path)
        if group_name:
            groups[group_name].append(directory_name)

    group_results: list[ConsistencyGroupResultItem] = []
    mw_cv_values: list[float] = []
    mn_cv_values: list[float] = []
    failed_groups = 0

    lines = [
        "# GPC 一致性测试报告 — Mw/Mn CV 系数",
        "",
        f"**测试目录**: `{data_path}`",
        f"**样品组数**: {len(groups)} 组",
        "",
        "## 汇总结果",
        "",
        "| 样品组 | 测试次数 | Mw均值(Da) | Mw CV(%) | Mn均值(Da) | Mn CV(%) | 备注 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]

    for group_name in sorted(groups.keys()):
        directory_list = groups[group_name]
        mw_list: list[float] = []
        mn_list: list[float] = []
        errors: list[str] = []

        for directory_name in sorted(directory_list):
            full_path = os.path.join(data_path, directory_name)
            arw_path = _find_arw_file(full_path)
            if not arw_path:
                errors.append(f"{directory_name}: 未找到.arw文件")
                continue

            analysis_result = _extract_mw_mn(arw_path)
            if "error" in analysis_result:
                errors.append(f"{directory_name}: {analysis_result['error']}")
                continue

            mw_list.append(analysis_result["mw"])
            mn_list.append(analysis_result["mn"])

        if len(mw_list) < 2:
            failed_groups += 1
            remark = f"有效数据不足({len(mw_list)}次): {'; '.join(errors)}"
            group_results.append(
                ConsistencyGroupResultItem(
                    group_name=group_name,
                    status="FAILED",
                    replicate_count=len(mw_list),
                    metrics={},
                    remark=remark,
                )
            )
            lines.append(f"| {group_name} | | | | | | {remark} |")
            continue

        mw_mean = float(np.mean(mw_list))
        mn_mean = float(np.mean(mn_list))
        mw_cv = calc_cv(mw_list)
        mn_cv = calc_cv(mn_list)
        if mw_cv is not None:
            mw_cv_values.append(mw_cv)
        if mn_cv is not None:
            mn_cv_values.append(mn_cv)

        remark = "; ".join(errors)
        group_results.append(
            ConsistencyGroupResultItem(
                group_name=group_name,
                status="SUCCESS",
                replicate_count=len(mw_list),
                metrics={
                    "mw_mean": mw_mean,
                    "mw_cv": mw_cv,
                    "mn_mean": mn_mean,
                    "mn_cv": mn_cv,
                },
                remark=remark,
            )
        )
        lines.append(
            f"| {group_name} | {len(mw_list)} | {mw_mean:.2f} | {format_number(mw_cv, 4)} | "
            f"{mn_mean:.2f} | {format_number(mn_cv, 4)} | {remark} |"
        )

    if mw_cv_values or mn_cv_values:
        lines.append(
            f"| **汇总（{len(group_results) - failed_groups} 组）** | | | **{format_number(average(mw_cv_values), 4)}** | "
            f"| **{format_number(average(mn_cv_values), 4)}** | |"
        )

    report_text = "\n".join(lines)
    report_path = output_dir / "gpc_consistency_report.md"
    report_path.write_text(report_text, encoding="utf-8")

    status = "SUCCESS" if group_results and failed_groups < len(group_results) else "FAILED"
    return ConsistencyDeviceRunItem(
        device_type="gpc",
        device_label=DEVICE_LABELS["gpc"],
        status=status,
        duration_seconds=0.0,
        summary_metrics={
            "group_count": len(group_results),
            "mw_cv_avg": average(mw_cv_values),
            "mn_cv_avg": average(mn_cv_values),
            "failed_group_count": failed_groups,
        },
        group_results=group_results,
        text_report=report_text,
        artifacts=[build_artifact(report_path)],
        error_message=None if status == "SUCCESS" else "全部样品组执行失败",
    )
