"""LCMS 设备重复性评测服务。"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

from app.core.logging import get_logger
from app.schemas.consistency import ConsistencyDeviceRunItem, ConsistencyGroupResultItem
from app.services.consistency_common import DEVICE_LABELS, average, build_artifact, calc_cv, format_number


logger = get_logger("spec_agent.services.consistency.lcms")


def _try_import_mzml_reader():
    """尝试导入 mzML 读取依赖。"""
    try:
        from pyteomics import mzml

        return "pyteomics", mzml
    except ImportError:
        pass
    try:
        pymzml_module = importlib.import_module("pymzml")
        return "pymzml", pymzml_module
    except ModuleNotFoundError:
        pass
    raise RuntimeError("未检测到 mzML 读取依赖，请安装 pyteomics 或 pymzml。")


def _extract_scan_time_pyteomics(spectrum: dict) -> Optional[float]:
    """从 pyteomics 的 spectrum 字典中提取扫描时间（分钟）。"""
    scans = spectrum.get("scanList", {}).get("scan", [])
    if not scans:
        return None
    value = scans[0].get("scan start time")
    if value is None:
        return None
    unit = scans[0].get("unitName", "minute")
    if "second" in str(unit).lower():
        return float(value) / 60.0
    return float(value)


def read_mzml(filepath: str) -> tuple[np.ndarray, np.ndarray, list[tuple]]:
    """读取 mzML 文件。"""
    backend_name, backend = _try_import_mzml_reader()
    scan_records = []
    tic_times = []
    tic_intensities = []

    if backend_name == "pyteomics":
        with backend.read(filepath) as reader:
            for spectrum in reader:
                if spectrum.get("ms level") != 1:
                    continue
                mzs = np.asarray(spectrum.get("m/z array", []), dtype=float)
                intensities = np.asarray(spectrum.get("intensity array", []), dtype=float)
                scan_time = _extract_scan_time_pyteomics(spectrum)
                if scan_time is None:
                    continue
                scan_records.append((scan_time, mzs, intensities))
                tic_times.append(scan_time)
                tic_intensities.append(float(np.sum(intensities)))
    else:
        run = backend.run.Reader(filepath)
        for spectrum in run:
            ms_level = getattr(spectrum, "ms_level", None)
            if ms_level not in (None, 1):
                continue
            scan_time = getattr(spectrum, "scan_time_in_minutes", lambda: None)()
            if scan_time is None:
                continue
            mzs = np.asarray(spectrum.mz, dtype=float)
            intensities = np.asarray(spectrum.i, dtype=float)
            scan_records.append((scan_time, mzs, intensities))
            tic_times.append(scan_time)
            tic_intensities.append(float(np.sum(intensities)))

    return np.asarray(tic_times, dtype=float), np.asarray(tic_intensities, dtype=float), scan_records


def extract_eic(scan_records: list[tuple], mz_target: float, mz_tolerance: float) -> tuple[np.ndarray, np.ndarray]:
    """提取 EIC。"""
    times = []
    intensities = []
    low_bound, high_bound = mz_target - mz_tolerance, mz_target + mz_tolerance
    for scan_time, mzs, spectrum_intensities in scan_records:
        mask = (mzs >= low_bound) & (mzs <= high_bound)
        intensities.append(float(np.sum(spectrum_intensities[mask])) if np.any(mask) else 0.0)
        times.append(scan_time)
    return np.asarray(times, dtype=float), np.asarray(intensities, dtype=float)


def detect_peak(times: np.ndarray, intensities: np.ndarray, rt_start: float, rt_end: float) -> Optional[dict]:
    """在指定 RT 窗口内检测峰。"""
    mask = (times >= rt_start) & (times <= rt_end)
    sub_times, sub_intensities = times[mask], intensities[mask]
    if len(sub_times) < 3:
        return None

    apex_index = int(np.argmax(sub_intensities))
    if sub_intensities[apex_index] <= 0:
        return None

    threshold = float(sub_intensities[apex_index]) * 0.05
    start_index = apex_index
    end_index = apex_index
    while start_index > 0 and sub_intensities[start_index] > threshold:
        start_index -= 1
    while end_index < len(sub_intensities) - 1 and sub_intensities[end_index] > threshold:
        end_index += 1
    if end_index - start_index < 2:
        return None

    peak_times = sub_times[start_index:end_index + 1]
    peak_intensities = sub_intensities[start_index:end_index + 1]
    baseline = np.linspace(peak_intensities[0], peak_intensities[-1], len(peak_intensities))
    corrected = np.maximum(peak_intensities - baseline, 0.0)
    return {
        "rt": float(sub_times[apex_index]),
        "area": float(np.trapezoid(corrected, peak_times)),
        "height": float(np.max(corrected)),
    }


def run_lcms_consistency(data_path: str, output_dir: Path, config_path: str) -> ConsistencyDeviceRunItem:
    """执行 LCMS 设备重复性评测。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "LCMS 一致性评测开始: data_path=%s, output_dir=%s, config_path=%s",
        data_path,
        output_dir,
        config_path,
    )
    if not os.path.isdir(data_path):
        report_text = f"# LCMS 一致性测试报告\n\n数据目录不存在：`{data_path}`\n"
        report_path = output_dir / "lcms_consistency_report.md"
        report_path.write_text(report_text, encoding="utf-8")
        logger.warning("LCMS 一致性评测失败，数据目录不存在: data_path=%s", data_path)
        return ConsistencyDeviceRunItem(
            device_type="lcms",
            device_label=DEVICE_LABELS["lcms"],
            status="FAILED",
            duration_seconds=0.0,
            summary_metrics={"group_count": 0},
            group_results=[],
            text_report=report_text,
            artifacts=[build_artifact(report_path)],
            error_message=f"数据目录不存在: {data_path}",
        )

    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    files = sorted(file_name for file_name in os.listdir(data_path) if file_name.endswith(".mzML"))
    groups = sorted(
        {
            file_name.replace(".mzML", "").rsplit("_", 1)[0]
            if "_" in file_name and file_name.split("_")[-1].replace(".mzML", "").isdigit()
            else file_name.replace(".mzML", "")
            for file_name in files
        }
    )

    tic_enabled = config.get("tic", {}).get("enabled", True)
    tic_window = config.get("tic", {}).get("rt_window", {})
    eic_targets = config.get("eic_targets", [])

    group_results: list[ConsistencyGroupResultItem] = []
    rt_cv_values: list[float] = []
    area_cv_values: list[float] = []
    height_cv_values: list[float] = []
    target_count = 0
    failed_groups = 0

    lines = [
        "# LC-MS 一致性测试报告 — 基于峰检测的 CV 系数",
        "",
        f"**测试目录**: `{data_path}`",
        f"**配置文件**: `{config_path}`",
        f"**验收标准**: RT CV ≤ {config['acceptance']['rt_cv_max_percent']}%, 面积 CV ≤ {config['acceptance']['area_cv_max_percent']}%",
        "",
        "## 汇总结果",
        "",
        "| 样品 | 峰类型 | 分析物 | 重复数 | RT CV(%) | 面积 CV(%) | 高度 CV(%) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]

    logger.info("LCMS 一致性评测样品组统计完成: total_groups=%s", len(groups))
    for index, sample_name in enumerate(groups, start=1):
        logger.info("LCMS 一致性评测处理样品组: group=%s, progress=%s/%s", sample_name, index, len(groups))
        sample_files = sorted(
            file_name
            for file_name in files
            if file_name.replace(".mzML", "").rsplit("_", 1)[0] == sample_name or file_name == f"{sample_name}.mzML"
        )

        tic_peaks = []
        eic_peaks: dict[str, list[dict]] = {}
        errors: list[str] = []

        for mzml_file in sample_files:
            filepath = os.path.join(data_path, mzml_file)
            try:
                tic_times, tic_intensities, scan_records = read_mzml(filepath)
            except Exception as exc:
                errors.append(f"{mzml_file}: {exc}")
                continue

            if tic_enabled and len(tic_times) > 0:
                peak = detect_peak(
                    tic_times,
                    tic_intensities,
                    float(tic_window.get("start", 0)),
                    float(tic_window.get("end", 10)),
                )
                if peak:
                    tic_peaks.append(peak)

            for target in eic_targets:
                name = target["name"]
                eic_times, eic_intensities = extract_eic(
                    scan_records,
                    float(target["mz"]),
                    float(target["mz_tolerance"]),
                )
                rt_window = target.get("rt_window", {})
                peak = detect_peak(
                    eic_times,
                    eic_intensities,
                    float(rt_window.get("start", 0)),
                    float(rt_window.get("end", 10)),
                )
                if peak:
                    eic_peaks.setdefault(name, []).append(peak)

        sample_peak_rows: list[dict] = []
        if tic_peaks:
            rts = [peak["rt"] for peak in tic_peaks]
            areas = [peak["area"] for peak in tic_peaks]
            heights = [peak["height"] for peak in tic_peaks]
            rt_cv = calc_cv(rts)
            area_cv = calc_cv(areas)
            height_cv = calc_cv(heights)
            if rt_cv is not None:
                rt_cv_values.append(rt_cv)
            if area_cv is not None:
                area_cv_values.append(area_cv)
            if height_cv is not None:
                height_cv_values.append(height_cv)
            target_count += 1
            sample_peak_rows.append(
                {
                    "type": "TIC",
                    "analyte": "TIC_main_peak",
                    "n_replicates": len(tic_peaks),
                    "mean_rt": float(np.mean(rts)),
                    "mean_area": float(np.mean(areas)),
                    "rt_cv": rt_cv,
                    "area_cv": area_cv,
                    "height_cv": height_cv,
                }
            )

        for target_name, peaks in eic_peaks.items():
            rts = [peak["rt"] for peak in peaks]
            areas = [peak["area"] for peak in peaks]
            heights = [peak["height"] for peak in peaks]
            rt_cv = calc_cv(rts)
            area_cv = calc_cv(areas)
            height_cv = calc_cv(heights)
            if rt_cv is not None:
                rt_cv_values.append(rt_cv)
            if area_cv is not None:
                area_cv_values.append(area_cv)
            if height_cv is not None:
                height_cv_values.append(height_cv)
            target_count += 1
            sample_peak_rows.append(
                {
                    "type": "EIC",
                    "analyte": target_name,
                    "n_replicates": len(peaks),
                    "mean_rt": float(np.mean(rts)),
                    "mean_area": float(np.mean(areas)),
                    "rt_cv": rt_cv,
                    "area_cv": area_cv,
                    "height_cv": height_cv,
                }
            )

        if sample_peak_rows:
            group_results.append(
                ConsistencyGroupResultItem(
                    group_name=sample_name,
                    status="SUCCESS",
                    replicate_count=max((row["n_replicates"] for row in sample_peak_rows), default=0),
                    metrics={"peaks": sample_peak_rows},
                    remark="; ".join(errors),
                )
            )
            for peak_row in sample_peak_rows:
                lines.append(
                    f"| {sample_name} | {peak_row['type']} | {peak_row['analyte']} | {peak_row['n_replicates']} | "
                    f"{format_number(peak_row['rt_cv'], 4)} | {format_number(peak_row['area_cv'], 4)} | "
                    f"{format_number(peak_row['height_cv'], 4)} |"
                )
            logger.info(
                "LCMS 样品组执行完成: group=%s, peak_rows=%s, errors=%s",
                sample_name,
                len(sample_peak_rows),
                len(errors),
            )
        else:
            failed_groups += 1
            remark = "未检测到峰" if not errors else f"未检测到峰；{'; '.join(errors)}"
            group_results.append(
                ConsistencyGroupResultItem(
                    group_name=sample_name,
                    status="FAILED",
                    replicate_count=0,
                    metrics={},
                    remark=remark,
                )
            )
            lines.append(f"| {sample_name} | {remark} | | | | | |")
            logger.warning("LCMS 样品组执行失败: group=%s, reason=%s", sample_name, remark)

    if rt_cv_values or area_cv_values:
        lines.append(
            f"| **汇总（{len(group_results) - failed_groups} 个样品）** | | | | **{format_number(average(rt_cv_values), 4)}** | "
            f"**{format_number(average(area_cv_values), 4)}** | |"
        )

    lines.append("")
    lines.append("## 各样品峰详情")
    for result_item in group_results:
        peaks = result_item.metrics.get("peaks", [])
        if result_item.status != "SUCCESS" or not peaks:
            continue
        lines.append("")
        lines.append(f"### {result_item.group_name}")
        lines.append("")
        lines.append("| 类型 | 分析物 | 平均RT(min) | 平均面积 | RT CV(%) | 面积 CV(%) | 高度 CV(%) |")
        lines.append("|---|---|---:|---:|---:|---:|---:|")
        for peak_row in peaks:
            lines.append(
                f"| {peak_row['type']} | {peak_row['analyte']} | {peak_row['mean_rt']:.4f} | {peak_row['mean_area']:.2f} | "
                f"{format_number(peak_row['rt_cv'], 4)} | {format_number(peak_row['area_cv'], 4)} | {format_number(peak_row['height_cv'], 4)} |"
            )

    report_text = "\n".join(lines)
    report_path = output_dir / "lcms_consistency_report.md"
    report_path.write_text(report_text, encoding="utf-8")

    status = "SUCCESS" if group_results and failed_groups < len(group_results) else "FAILED"
    logger.info(
        "LCMS 一致性评测完成: status=%s, total_groups=%s, failed_groups=%s, report_path=%s",
        status,
        len(group_results),
        failed_groups,
        report_path,
    )
    return ConsistencyDeviceRunItem(
        device_type="lcms",
        device_label=DEVICE_LABELS["lcms"],
        status=status,
        duration_seconds=0.0,
        summary_metrics={
            "group_count": len(group_results),
            "rt_cv_avg": average(rt_cv_values),
            "area_cv_avg": average(area_cv_values),
            "height_cv_avg": average(height_cv_values),
            "target_count": target_count,
            "failed_group_count": failed_groups,
        },
        group_results=group_results,
        text_report=report_text,
        artifacts=[build_artifact(report_path)],
        error_message=None if status == "SUCCESS" else "全部样品组执行失败",
    )
