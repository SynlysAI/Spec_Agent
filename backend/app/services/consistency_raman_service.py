"""Raman 设备重复性评测服务。"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

from app.schemas.consistency import ConsistencyDeviceRunItem, ConsistencyGroupResultItem
from app.services.consistency_common import DEVICE_LABELS, average, build_artifact, format_number


IDS = [0, 1, 2]
PEAK_PROMINENCE = 0.1
PEAK_TOLERANCE = 10
HEADER_LINES = 3


def load_raman_data(filepath: str) -> tuple[np.ndarray, np.ndarray]:
    """加载 Raman 数据。"""
    with open(filepath, "r", encoding="utf-8") as file:
        data = np.array([line.split() for line in file.readlines()[HEADER_LINES:]], dtype=float)
    return data[:, -2], data[:, -1]


def _gaussian_peak_fit(x_values: np.ndarray, y_values: np.ndarray) -> tuple[float, float]:
    """高斯拟合精确定位峰。"""
    try:
        y_safe = np.maximum(y_values, 1e-10)
        log_y = np.log(y_safe)
        coefficient_a, coefficient_b, coefficient_c = np.polyfit(x_values, log_y, 2)

        peak_position = -coefficient_b / (2 * coefficient_a)
        peak_intensity = np.exp(coefficient_c - coefficient_b ** 2 / (4 * coefficient_a))

        if not (np.min(x_values) <= peak_position <= np.max(x_values)):
            peak_position = float(x_values[np.argmax(y_values)])
            peak_intensity = float(np.max(y_values))
        return float(peak_position), float(peak_intensity)
    except Exception:
        max_index = int(np.argmax(y_values))
        return float(x_values[max_index]), float(y_values[max_index])


def detect_raman_peaks(wavelengths: np.ndarray, intensities: np.ndarray) -> list[tuple[float, float]]:
    """检测 Raman 峰。"""
    prominence = PEAK_PROMINENCE * np.max(intensities)
    peaks, _properties = find_peaks(intensities, prominence=prominence)

    results: list[tuple[float, float]] = []
    for peak_index in peaks:
        window = 5
        start = max(0, int(peak_index) - window)
        end = min(len(wavelengths), int(peak_index) + window + 1)
        x_local = wavelengths[start:end]
        y_local = intensities[start:end]
        refined_position, refined_intensity = _gaussian_peak_fit(x_local, y_local)
        results.append((refined_position, refined_intensity))
    return results


def match_peaks_across_spectra(all_peaks: list[list[tuple[float, float]]]) -> list[list[int]]:
    """将多次测量检测到的峰进行匹配。"""
    if not all_peaks or not all_peaks[0]:
        return []
    reference_peaks = all_peaks[0]
    matched_groups: list[list[int]] = []
    for reference_index, (reference_position, _) in enumerate(reference_peaks):
        indices = [reference_index]
        for spectrum_peaks in all_peaks[1:]:
            best_index = -1
            best_distance = PEAK_TOLERANCE
            for peak_index, (position, _) in enumerate(spectrum_peaks):
                distance = abs(position - reference_position)
                if distance < best_distance:
                    best_distance = distance
                    best_index = peak_index
            indices.append(best_index)
        matched_groups.append(indices)
    return matched_groups


def calc_peak_cv(all_peaks: list[list[tuple[float, float]]], matched_groups: list[list[int]]) -> dict[str, float | list[dict[str, float]]]:
    """计算匹配峰的位置和强度 CV。"""
    position_cvs: list[float] = []
    intensity_cvs: list[float] = []
    peak_details: list[dict[str, float]] = []

    for indices in matched_groups:
        positions: list[float] = []
        intensities: list[float] = []
        for spectrum_index, peak_index in enumerate(indices):
            if peak_index < 0:
                continue
            position, height = all_peaks[spectrum_index][peak_index]
            positions.append(position)
            intensities.append(height)

        if len(positions) < 2:
            continue

        position_array = np.asarray(positions, dtype=float)
        intensity_array = np.asarray(intensities, dtype=float)
        mean_position = float(np.mean(position_array))
        mean_intensity = float(np.mean(intensity_array))
        pos_cv = float(np.std(position_array, ddof=1) / mean_position * 100.0) if mean_position != 0 else 0.0
        int_cv = float(np.std(intensity_array, ddof=1) / mean_intensity * 100.0) if mean_intensity != 0 else 0.0

        position_cvs.append(pos_cv)
        intensity_cvs.append(int_cv)
        peak_details.append(
            {
                "mean_pos": mean_position,
                "pos_cv": pos_cv,
                "int_cv": int_cv,
            }
        )

    return {
        "mean_pos_cv": float(np.mean(position_cvs)) if position_cvs else float("nan"),
        "mean_int_cv": float(np.mean(intensity_cvs)) if intensity_cvs else float("nan"),
        "max_pos_cv": float(np.max(position_cvs)) if position_cvs else float("nan"),
        "max_int_cv": float(np.max(intensity_cvs)) if intensity_cvs else float("nan"),
        "num_peaks": len(position_cvs),
        "peak_details": peak_details,
    }


def run_raman_consistency(data_path: str, output_dir: Path) -> ConsistencyDeviceRunItem:
    """执行 Raman 设备重复性评测。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    if not os.path.isdir(data_path):
        report_text = f"# Raman 一致性测试报告\n\n数据目录不存在：`{data_path}`\n"
        report_path = output_dir / "raman_consistency_report.md"
        report_path.write_text(report_text, encoding="utf-8")
        return ConsistencyDeviceRunItem(
            device_type="raman",
            device_label=DEVICE_LABELS["raman"],
            status="FAILED",
            duration_seconds=0.0,
            summary_metrics={"group_count": 0},
            group_results=[],
            text_report=report_text,
            artifacts=[build_artifact(report_path)],
            error_message=f"数据目录不存在: {data_path}",
        )

    files = sorted(os.listdir(data_path))
    groups = sorted(set(file_name.rsplit("_", 1)[0] for file_name in files if "_" in file_name))

    group_results: list[ConsistencyGroupResultItem] = []
    mean_pos_values: list[float] = []
    mean_int_values: list[float] = []
    max_pos_values: list[float] = []
    max_int_values: list[float] = []
    failed_groups = 0

    lines = [
        "# Raman 一致性测试报告 — 基于峰检测的 CV 系数",
        "",
        f"**测试目录**: `{data_path}`",
        f"**测量次数**: {len(IDS)} 次（id={IDS}）",
        "",
        "## 汇总结果",
        "",
        "| 样品名称 | 峰数量 | 位置CV(%) | 强度CV(%) | 最大位置CV(%) | 最大强度CV(%) |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for sample_name in groups:
        all_peaks: list[list[tuple[float, float]]] = []
        for sample_index in IDS:
            filepath = os.path.join(data_path, f"{sample_name}_{sample_index}.dat")
            if not os.path.exists(filepath):
                continue
            wavelengths, intensities = load_raman_data(filepath)
            all_peaks.append(detect_raman_peaks(wavelengths, intensities))

        if len(all_peaks) < 2:
            failed_groups += 1
            group_results.append(
                ConsistencyGroupResultItem(
                    group_name=sample_name,
                    status="FAILED",
                    replicate_count=len(all_peaks),
                    metrics={},
                    remark="数据不足",
                )
            )
            lines.append(f"| {sample_name} | 数据不足 | | | | |")
            continue

        matched = match_peaks_across_spectra(all_peaks)
        if not matched:
            failed_groups += 1
            group_results.append(
                ConsistencyGroupResultItem(
                    group_name=sample_name,
                    status="FAILED",
                    replicate_count=len(all_peaks),
                    metrics={},
                    remark="未检测到峰",
                )
            )
            lines.append(f"| {sample_name} | 未检测到峰 | | | | |")
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
                remark="",
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
        lines.append("| 峰位(cm⁻¹) | 位置CV(%) | 强度CV(%) |")
        lines.append("|---|---:|---:|")
        for detail in peak_details:
            lines.append(f"| {detail['mean_pos']:.2f} | {detail['pos_cv']:.4f} | {detail['int_cv']:.4f} |")

    report_text = "\n".join(lines)
    report_path = output_dir / "raman_consistency_report.md"
    report_path.write_text(report_text, encoding="utf-8")

    status = "SUCCESS" if group_results and failed_groups < len(group_results) else "FAILED"
    return ConsistencyDeviceRunItem(
        device_type="raman",
        device_label=DEVICE_LABELS["raman"],
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
