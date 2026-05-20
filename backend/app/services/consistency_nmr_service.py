"""NMR 设备重复性评测服务。"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from analysis.nmr.nmr_analysis import get_nmr_sample_data
from analysis.nmr.peak_detection import detect_peaks
from app.schemas.consistency import ConsistencyDeviceRunItem, ConsistencyGroupResultItem
from app.services.consistency_common import DEVICE_LABELS, average, build_artifact, format_number


INDICES = [0, 1, 2]
PEAK_TOLERANCE = 0.05
TMS_PPM_THRESHOLD = 0.5


def match_peaks_across_spectra(all_peaks: list[list[tuple]]) -> list[list[int]]:
    """将多次测量检测到的峰进行匹配配对。"""
    if not all_peaks or not all_peaks[0]:
        return []

    ref_peaks = all_peaks[0]
    matched_groups: list[list[int]] = []
    for ref_index, (ref_ppm, _, _) in enumerate(ref_peaks):
        indices = [ref_index]
        for spectrum_peaks in all_peaks[1:]:
            best_index = -1
            best_distance = PEAK_TOLERANCE
            for peak_index, (ppm, _, _) in enumerate(spectrum_peaks):
                distance = abs(ppm - ref_ppm)
                if distance < best_distance:
                    best_distance = distance
                    best_index = peak_index
            indices.append(best_index)
        matched_groups.append(indices)
    return matched_groups


def calc_peak_cv(all_peaks: list[list[tuple]], matched_groups: list[list[int]]) -> dict[str, float | list[dict[str, float]]]:
    """计算匹配峰的位置 CV 和强度 CV。"""
    position_cvs: list[float] = []
    intensity_cvs: list[float] = []
    peak_details: list[dict[str, float]] = []

    for indices in matched_groups:
        positions: list[float] = []
        intensities: list[float] = []
        for spectrum_index, peak_index in enumerate(indices):
            if peak_index < 0:
                continue
            ppm, height, _width = all_peaks[spectrum_index][peak_index]
            positions.append(ppm)
            intensities.append(height)

        if len(positions) < 2:
            continue

        position_array = np.asarray(positions, dtype=float)
        intensity_array = np.asarray(intensities, dtype=float)
        mean_ppm = float(np.mean(position_array))
        if mean_ppm < TMS_PPM_THRESHOLD:
            pos_cv = 0.0
        else:
            pos_cv = float(np.std(position_array, ddof=1) / mean_ppm * 100.0)
        mean_intensity = float(np.mean(intensity_array))
        int_cv = float(np.std(intensity_array, ddof=1) / mean_intensity * 100.0) if mean_intensity != 0 else 0.0

        position_cvs.append(pos_cv)
        intensity_cvs.append(int_cv)
        peak_details.append(
            {
                "mean_ppm": mean_ppm,
                "pos_cv": pos_cv,
                "int_cv": int_cv,
            }
        )

    return {
        "mean_pos_cv": float(np.mean(position_cvs)) if position_cvs else float("nan"),
        "mean_int_cv": float(np.mean(intensity_cvs)) if intensity_cvs else float("nan"),
        "max_pos_cv": float(np.max(position_cvs)) if position_cvs else float("nan"),
        "max_int_cv": float(np.max(intensity_cvs)) if intensity_cvs else float("nan"),
        "num_peaks": len(peak_details),
        "peak_details": peak_details,
    }


def run_nmr_consistency(data_path: str, output_dir: Path) -> ConsistencyDeviceRunItem:
    """执行 NMR 设备重复性评测。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    if not os.path.isdir(data_path):
        report_text = f"# NMR 一致性测试报告\n\n数据目录不存在：`{data_path}`\n"
        report_path = output_dir / "nmr_consistency_report.md"
        report_path.write_text(report_text, encoding="utf-8")
        return ConsistencyDeviceRunItem(
            device_type="nmr",
            device_label=DEVICE_LABELS["nmr"],
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

    group_results: list[ConsistencyGroupResultItem] = []
    mean_pos_values: list[float] = []
    mean_int_values: list[float] = []
    max_pos_values: list[float] = []
    max_int_values: list[float] = []
    failed_groups = 0

    lines = [
        "# NMR 一致性测试报告 — 基于峰检测的 CV 系数",
        "",
        f"**测试目录**: `{data_path}`",
        f"**测量次数**: {len(INDICES)} 次（index={INDICES}）",
        "",
        "## 汇总结果",
        "",
        "| 样品名称 | 峰数量 | 位置CV(%) | 强度CV(%) | 最大位置CV(%) | 最大强度CV(%) |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for sample_name in sample_dirs:
        sample_path = os.path.join(data_path, sample_name)
        all_peaks: list[list[tuple]] = []
        errors: list[str] = []

        for index in INDICES:
            try:
                data, ppm_scale, _processing_steps, _metadata = get_nmr_sample_data(sample_path, index=index)
                peaks = detect_peaks(data, ppm_scale)
                all_peaks.append(peaks)
            except Exception as exc:
                errors.append(f"index={index}: {exc}")

        if len(all_peaks) < 2:
            failed_groups += 1
            remark = "数据不足" if not errors else f"数据不足；{'; '.join(errors)}"
            group_results.append(
                ConsistencyGroupResultItem(
                    group_name=sample_name,
                    status="FAILED",
                    replicate_count=len(all_peaks),
                    metrics={},
                    remark=remark,
                )
            )
            lines.append(f"| {sample_name} | {remark} | | | | |")
            continue

        matched = match_peaks_across_spectra(all_peaks)
        if not matched:
            failed_groups += 1
            remark = "未检测到峰" if not errors else f"未检测到峰；{'; '.join(errors)}"
            group_results.append(
                ConsistencyGroupResultItem(
                    group_name=sample_name,
                    status="FAILED",
                    replicate_count=len(all_peaks),
                    metrics={},
                    remark=remark,
                )
            )
            lines.append(f"| {sample_name} | {remark} | | | | |")
            continue

        cv_result = calc_peak_cv(all_peaks, matched)
        mean_pos = cv_result["mean_pos_cv"]
        mean_int = cv_result["mean_int_cv"]
        max_pos = cv_result["max_pos_cv"]
        max_int = cv_result["max_int_cv"]
        if not np.isnan(mean_pos):
            mean_pos_values.append(float(mean_pos))
        if not np.isnan(mean_int):
            mean_int_values.append(float(mean_int))
        if not np.isnan(max_pos):
            max_pos_values.append(float(max_pos))
        if not np.isnan(max_int):
            max_int_values.append(float(max_int))

        remark = "; ".join(errors)
        group_results.append(
            ConsistencyGroupResultItem(
                group_name=sample_name,
                status="SUCCESS",
                replicate_count=len(all_peaks),
                metrics={
                    "num_peaks": cv_result["num_peaks"],
                    "mean_pos_cv": mean_pos,
                    "mean_int_cv": mean_int,
                    "max_pos_cv": max_pos,
                    "max_int_cv": max_int,
                    "peak_details": cv_result["peak_details"],
                },
                remark=remark,
            )
        )
        lines.append(
            f"| {sample_name} | {cv_result['num_peaks']} | {format_number(mean_pos, 4)} | "
            f"{format_number(mean_int, 4)} | {format_number(max_pos, 4)} | {format_number(max_int, 4)} |"
        )

    if mean_pos_values or mean_int_values:
        lines.append(
            f"| **汇总（{len(group_results) - failed_groups} 个样品）** | | **{format_number(average(mean_pos_values), 4)}** | "
            f"**{format_number(average(mean_int_values), 4)}** | | |"
        )

    lines.append("")
    lines.append("## 各样品峰详情")
    for result_item in group_results:
        peak_details = result_item.metrics.get("peak_details", [])
        if result_item.status != "SUCCESS" or not peak_details:
            continue
        lines.append("")
        lines.append(f"### {result_item.group_name}")
        lines.append("")
        lines.append("| 峰位(ppm) | 位置CV(%) | 强度CV(%) |")
        lines.append("|---|---:|---:|")
        for detail in peak_details:
            lines.append(
                f"| {detail['mean_ppm']:.4f} | {detail['pos_cv']:.4f} | {detail['int_cv']:.4f} |"
            )

    report_text = "\n".join(lines)
    report_path = output_dir / "nmr_consistency_report.md"
    report_path.write_text(report_text, encoding="utf-8")

    status = "SUCCESS" if group_results and failed_groups < len(group_results) else "FAILED"
    return ConsistencyDeviceRunItem(
        device_type="nmr",
        device_label=DEVICE_LABELS["nmr"],
        status=status,
        duration_seconds=0.0,
        summary_metrics={
            "group_count": len(group_results),
            "mean_pos_cv_avg": average(mean_pos_values),
            "mean_int_cv_avg": average(mean_int_values),
            "max_pos_cv_avg": average(max_pos_values),
            "max_int_cv_avg": average(max_int_values),
            "failed_group_count": failed_groups,
        },
        group_results=group_results,
        text_report=report_text,
        artifacts=[build_artifact(report_path)],
        error_message=None if status == "SUCCESS" else "全部样品组执行失败",
    )
