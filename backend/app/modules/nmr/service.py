from __future__ import annotations

import os
from typing import Any

import numpy as np

from analysis.nmr.multiplet import analyze_all_multiplets
from analysis.nmr.nmr_analysis import (
    get_nmr_sample_data,
    integrate_region,
    plot_nmr_spectrum,
    plot_peak_detection_overview,
    plot_processing_steps,
)
from analysis.nmr.peak_detection import (
    create_integration_regions_from_peaks,
    detect_peaks,
    smooth_data,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.modules.nmr.export_service import build_peak_annotations, build_peak_details
from app.modules.common.report_service import save_text_report

logger = get_logger("spec_agent.modules.nmr.service")


def get_ppm_range(folder_path: str, uploaded_ppm_scale=None, experiment_idx: int = 0) -> tuple[float, float]:
    """解析当前样品的 ppm 显示范围。

    Args:
        folder_path: NMR 样品目录路径；当值为 ``"UPLOADED_FILE"`` 时表示使用上传文件。
        uploaded_ppm_scale: 上传文件解析出的 ppm 数组，仅在 ``folder_path`` 为
            ``"UPLOADED_FILE"`` 时使用。
        experiment_idx: 要读取的实验编号索引，默认为 0。

    Returns:
        一个二元组 ``(min_ppm, max_ppm)``，用于界面展示和积分区域初始化。

    Raises:
        ValueError: 当上传文件或目录数据不可用时抛出。
    """
    if folder_path == "UPLOADED_FILE":
        if uploaded_ppm_scale is None:
            logger.warning("get_ppm_range: 上传文件模式下未提供 ppm_scale 数据")
            raise ValueError("请先上传谱图文件")
        return float(np.min(uploaded_ppm_scale)), float(np.max(uploaded_ppm_scale))

    if not folder_path or not os.path.exists(folder_path):
        logger.warning("get_ppm_range: 样品目录不存在, folder_path=%s", folder_path)
        raise ValueError("文件夹不存在，请检查路径")

    _, ppm_scale, _, _ = get_nmr_sample_data(folder_path, index=experiment_idx)
    return float(min(ppm_scale)), float(max(ppm_scale))


def load_nmr_basic_info(folder_path: str, uploaded_ppm_scale=None, experiment_idx: int = 0) -> tuple[float, float, dict[str, Any]]:
    """加载 NMR 基础信息，包含 ppm 范围和实验元数据。"""
    if folder_path == "UPLOADED_FILE":
        if uploaded_ppm_scale is None:
            logger.warning("load_nmr_basic_info: 上传文件模式下未提供 ppm_scale 数据")
            raise ValueError("请先上传谱图文件")
        return float(np.min(uploaded_ppm_scale)), float(np.max(uploaded_ppm_scale)), {
            "solvent": "未知", "nucleus": "未知", "tms_offset": 0.0
        }

    if not folder_path or not os.path.exists(folder_path):
        logger.warning("load_nmr_basic_info: 样品目录不存在, folder_path=%s", folder_path)
        raise ValueError("文件夹不存在，请检查路径")

    _, ppm_scale, _, metadata = get_nmr_sample_data(folder_path, index=experiment_idx)
    return float(min(ppm_scale)), float(max(ppm_scale)), metadata


def build_manual_integration_regions(integration_regions_config: list[dict[str, Any]]) -> list[
    tuple[str, float, float]]:
    """将手动模式下的区域配置转换为积分区间列表。

    Args:
        integration_regions_config: 页面层维护的积分区域配置列表。

    Returns:
        适配积分流程的区域列表，元素格式为 ``(区域名称, 起始ppm, 结束ppm)``。
    """
    regions = []
    for config in integration_regions_config:
        start, end = config["range"]
        regions.append((config["name"], start, end))
    return regions


def _load_peak_detection_input(folder_path: str, peak_detection_params: dict[str, Any],
                               uploaded_data: dict[str, Any] | None, experiment_idx: int = 0) -> dict[str, Any]:
    """加载峰检测所需的输入数据。

    Args:
        folder_path: 数据来源路径；可为实际目录或 ``"UPLOADED_FILE"``。
        peak_detection_params: 峰检测参数字典。
        uploaded_data: 上传谱图的缓存数据，包含 ppm、强度和文件名。
        experiment_idx: 实验编号索引。

    Returns:
        峰检测输入上下文，包含样品名、谱图数据、ppm 刻度和处理步骤字典。

    Raises:
        ValueError: 当输入数据不完整或目录无效时抛出。
    """
    if folder_path == "UPLOADED_FILE":
        if not uploaded_data or "ppm_scale" not in uploaded_data or "data" not in uploaded_data:
            logger.warning("_load_peak_detection_input: 上传数据不完整, uploaded_data=%s", bool(uploaded_data))
            raise ValueError("请先上传谱图文件")

        sample_name = os.path.splitext(uploaded_data.get("file_name", "uploaded_spectrum"))[0]
        data = uploaded_data["data"]
        ppm_scale = uploaded_data["ppm_scale"]
        processing_steps = {
            "原始数据": data,
            "最终处理结果": data,
        }
        return {
            "sample_name": sample_name,
            "data": data,
            "ppm_scale": ppm_scale,
            "processing_steps": processing_steps,
            "metadata": {"solvent": "未知", "nucleus": "未知", "tms_offset": 0.0, "sfo1": 400.13}
        }

    if not os.path.exists(folder_path):
        logger.warning("_load_peak_detection_input: 样品目录不存在, folder_path=%s", folder_path)
        raise ValueError("样品目录不存在，请检查路径")

    sample_name = os.path.basename(folder_path)
    data, ppm_scale, processing_steps, metadata = get_nmr_sample_data(folder_path, index=experiment_idx)
    smooth_window = peak_detection_params.get("smooth_window")
    processed_data = smooth_data(data, smooth_window)

    return {
        "sample_name": sample_name,
        "data": processed_data,
        "ppm_scale": ppm_scale,
        "processing_steps": {"最终处理结果": processed_data},
        "metadata": metadata
    }


def build_peak_detection_result(
        folder_path: str,
        integration_mode: str,
        peak_detection_params: dict[str, Any],
        integration_regions_config: list[dict[str, Any]] | None = None,
        uploaded_data: dict[str, Any] | None = None,
        experiment_idx: int = 0,
) -> dict[str, Any]:
    """执行 NMR 峰检测并返回统一结果结构。

    Args:
        folder_path: 数据来源路径；可以是样品目录，也可以是 ``"UPLOADED_FILE"``。
        integration_mode: 积分模式，支持 ``"自动模式"`` 和 ``"手动模式"``。
        peak_detection_params: 峰检测参数字典。
        integration_regions_config: 手动模式下的区域配置。
        uploaded_data: 上传谱图时的缓存数据。
        experiment_idx: 选择的实验编号索引。

    Returns:
        峰检测结果字典，可直接写入 `st.session_state.nmr_peak_detection_results`。

    Raises:
        ValueError: 当峰检测失败或输入配置不完整时抛出。
    """
    peak_input = _load_peak_detection_input(folder_path, peak_detection_params, uploaded_data, experiment_idx)
    data = peak_input["data"]
    ppm_scale = peak_input["ppm_scale"]
    metadata = peak_input["metadata"]

    if integration_mode == "自动模式":
        detection_data = data
        detection_ppm_scale = ppm_scale
        detection_range = None

        if peak_detection_params.get("detection_range_mode") == "自定义范围":
            range_min = peak_detection_params.get("detection_range_min")
            range_max = peak_detection_params.get("detection_range_max")
            if range_min is not None and range_max is not None:
                if range_min > range_max:
                    range_min, range_max = range_max, range_min
                detection_range = (range_min, range_max)
                mask = (ppm_scale >= range_min) & (ppm_scale <= range_max)
                if np.any(mask):
                    detection_data = data[mask]
                    detection_ppm_scale = ppm_scale[mask]
                else:
                    logger.warning("build_peak_detection_result: 指定检测范围 %.1f-%.1f ppm 内无数据点", range_min, range_max)
                    raise ValueError(f"指定的检测范围 {range_min:.1f} - {range_max:.1f} ppm 内没有数据点")

        nuc = str(metadata.get('nucleus', '1H')).strip()
        enable_multiplet = peak_detection_params.get("enable_multiplet", True)
        is_1h = nuc in ("1H", "1H\n", "<1H>")
        is_13c = nuc in ("13C", "13C\n", "<13C>")

        # 峰检测核心参数：如果 UI 传参缺失（如 CLI 调用），则根据核类型补全默认值
        threshold = peak_detection_params.get("threshold")
        if threshold is None:
            threshold = 0.05 if is_13c else 0.01

        min_distance = peak_detection_params.get("min_distance")
        if min_distance is None:
            min_distance = 1.0 if is_13c else 0.3

        min_prominence = peak_detection_params.get("min_prominence")
        if min_prominence is None:
            min_prominence = 0.03 if is_13c else 0.01

        smooth_window = peak_detection_params.get("smooth_window")
        if smooth_window is None:
            smooth_window = 11 if is_13c else 5

        baseline_degree = peak_detection_params.get("baseline_degree", 3)

        effective_min_distance = min_distance
        if enable_multiplet:
            sfo1_val = peak_detection_params.get("sfo1") or metadata.get("sfo1", 400.13)
            min_resolvable_j_hz = 15.0 if is_13c else 3.0
            fine_min_distance = min_resolvable_j_hz / sfo1_val
            if effective_min_distance > fine_min_distance:
                effective_min_distance = fine_min_distance

        detected_peaks = detect_peaks(
            detection_data,
            detection_ppm_scale,
            threshold,
            effective_min_distance,
            min_prominence,
            baseline_degree,
            smooth_window,
        )

        if not detected_peaks:
            logger.warning("build_peak_detection_result: 自动检测峰失败, threshold=%.3f, min_distance=%.2f", threshold, effective_min_distance)
            raise ValueError("自动检测峰失败，请尝试调整参数或使用手动模式")

        json_path = str(settings.solvent_impurities_path)
        try:
            import json
            with open(json_path, 'r', encoding='utf-8') as f:
                solvent_dict = json.load(f)
        except Exception:
            solvent_dict = {}

        solv = str(metadata.get('solvent', '')).strip()
        tms_offset = metadata.get('tms_offset', 0.0)
        ui_offset = peak_detection_params.get("ppm_offset", tms_offset)

        ref_peaks = []
        if nuc in solvent_dict and solv in solvent_dict[nuc]:
            ref_peaks = solvent_dict[nuc][solv]
        elif '1H' in solvent_dict and solv in solvent_dict['1H']:
            ref_peaks = solvent_dict['1H'][solv]

        # 多重峰聚合分析（支持多种核且用户开启时执行）
        multiplet_results = None
        if enable_multiplet:
            sfo1 = peak_detection_params.get("sfo1") or metadata.get("sfo1", 400.13)
            max_coupling_hz = peak_detection_params.get("max_coupling_hz", 20.0)
            # 此时全部作为目标峰进行聚类
            multiplet_results = analyze_all_multiplets(
                detected_peaks, sfo1, None, max_coupling_hz
            )

        # 根据核类型动态调整峰识别容差 (13C 范围广、波动大，放宽到 1.5 ppm)
        match_tolerance = 1.5 if is_13c else 0.1

        peak_types = []
        if multiplet_results:
            for mp in multiplet_results:
                shifted_ppm = mp.center_ppm + ui_offset
                matched_name = ""
                matched_type = "目标峰"
                for ref in ref_peaks:
                    if abs(shifted_ppm - ref["ppm"]) < match_tolerance:
                        matched_type = ref.get("type", "Impurity")
                        matched_name = ref.get("name", "Unknown")
                        break
                if matched_name:
                    ptype = f"{matched_type}-{matched_name}"
                else:
                    ptype = "目标峰"
                mp.peak_type = ptype
                peak_types.append(ptype)
        else:
            for (ppm, _, _) in detected_peaks:
                shifted_ppm = ppm + ui_offset
                matched_name = ""
                matched_type = "目标峰"
                for ref in ref_peaks:
                    if abs(shifted_ppm - ref["ppm"]) < match_tolerance:
                        matched_type = ref.get("type", "Impurity")
                        matched_name = ref.get("name", "Unknown")
                        break
                if matched_name:
                    peak_types.append(f"{matched_type}-{matched_name}")
                else:
                    peak_types.append("目标峰")

        integration_regions = create_integration_regions_from_peaks(
            detected_peaks,
            width_multiplier=peak_detection_params["width_multiplier"],
            detection_range=detection_range,
            peak_types=peak_types,
            multiplet_results=multiplet_results,
        )
    else:
        if not integration_regions_config:
            logger.warning("build_peak_detection_result: 手动模式下未配置积分区域")
            raise ValueError("手动模式下缺少积分区域配置")
        integration_regions = build_manual_integration_regions(integration_regions_config)
        detection_range = None
        multiplet_results = None

    return {
        "sample_name": peak_input["sample_name"],
        "data": data,
        "ppm_scale": ppm_scale,
        "processing_steps": peak_input["processing_steps"],
        "integration_regions": integration_regions,
        "detection_range": detection_range,
        "metadata": metadata,
        "detected_peaks": detected_peaks if integration_mode == "自动模式" else [],
        "multiplet_results": multiplet_results,
    }


def build_initial_nmr_results(peak_detection_result: dict[str, Any]) -> list[dict[str, Any]]:
    """根据峰检测结果构造 NMR 结果初始结构。

    Args:
        peak_detection_result: `build_peak_detection_result()` 的返回值。

    Returns:
        用于页面层展示的初始结果列表，结构与 `st.session_state.nmr_results` 保持一致。
    """
    return [{
        "sample_name": peak_detection_result["sample_name"],
        "data": peak_detection_result["data"],
        "ppm_scale": peak_detection_result["ppm_scale"],
        "processing_steps": peak_detection_result["processing_steps"],
        "integration_results": {},
        "normalized_results": {},
        "integration_regions": peak_detection_result["integration_regions"],
        "detection_range": peak_detection_result["detection_range"],
        "metadata": peak_detection_result.get("metadata", {}),
        "multiplet_results": peak_detection_result.get("multiplet_results"),
        "peak_annotations": build_peak_annotations(
            peak_detection_result["integration_regions"],
            peak_detection_result.get("multiplet_results"),
        ),
        "peak_details": build_peak_details(
            integration_regions=peak_detection_result["integration_regions"],
            multiplet_results=peak_detection_result.get("multiplet_results"),
            integration_results={},
            normalized_results={},
        ),
    }]


def run_integration_analysis(
        peak_results: dict[str, Any],
        internal_standard_idx: int | None,
        integration_method_label: str,
        output_dir: str,
) -> list[dict[str, Any]]:
    """执行积分与归一化计算，并生成分析图文件。

    Args:
        peak_results: 峰检测结果字典。
        internal_standard_idx: 被选中的内标峰索引；``None`` 表示不指定内标峰，
            所有区域保持原始名称，不进行归一化。
        integration_method_label: 页面层展示的积分方法名称。
        output_dir: 样品分析输出根目录。

    Returns:
        更新后的 `nmr_results` 列表，包含积分值、归一化值与图像输出信息。

    Raises:
        ValueError: 当内标峰无效或积分区域为空时抛出。
    """
    sample_name = peak_results["sample_name"]
    data = peak_results["data"]
    ppm_scale = peak_results["ppm_scale"]
    processing_steps = dict(peak_results["processing_steps"])
    integration_regions = peak_results["integration_regions"]
    detected_peaks = peak_results.get("detected_peaks", [])
    detection_range = peak_results.get("detection_range")
    multiplet_results = peak_results.get("multiplet_results")

    if not integration_regions:
        logger.warning("run_integration_analysis: 积分区域为空, sample_name=%s", sample_name)
        raise ValueError("请至少配置一个积分区域")

    updated_regions = []
    for index, region in enumerate(integration_regions):
        if len(region) == 4:
            name, start, end, _peak_position = region
        else:
            name, start, end = region

        if internal_standard_idx is not None and index == internal_standard_idx:
            updated_regions.append((f"{name}(内标峰)", start, end))
        else:
            updated_regions.append((name, start, end))

    method = "voigt" if integration_method_label == "Voigt拟合峰形积分（推荐）" else "trapezoid"
    integration_results = {}
    for name, start, end in updated_regions:
        integration_results[name] = integrate_region(data, ppm_scale, start, end, method=method)

    if internal_standard_idx is not None:
        internal_standard_name = updated_regions[internal_standard_idx][0]
        if internal_standard_name not in integration_results:
            logger.warning("run_integration_analysis: 内标峰区域 '%s' 不在积分结果中, sample_name=%s", internal_standard_name, sample_name)
            raise ValueError("内标峰区域不在积分结果中，请检查配置")

        internal_standard_value = integration_results[internal_standard_name]
        normalized_results = {
            name: (area / internal_standard_value)
            for name, area in integration_results.items()
        }
    else:
        normalized_results = {}

    processing_steps["积分结果"] = integration_results
    processing_steps["归一化结果"] = normalized_results

    sample_output_dir = os.path.join(output_dir, sample_name)
    os.makedirs(sample_output_dir, exist_ok=True)
    plot_nmr_spectrum(ppm_scale, data, sample_name, sample_output_dir)
    plot_peak_detection_overview(
        ppm_scale,
        data,
        sample_name,
        sample_output_dir,
        detected_peaks=detected_peaks,
        integration_regions=integration_regions,
        multiplet_results=multiplet_results,
        detection_range=detection_range,
    )
    plot_processing_steps(
        ppm_scale,
        processing_steps,
        sample_name,
        sample_output_dir,
        integration_regions=updated_regions,
        normalized_results=normalized_results,
    )

    return [{
        "sample_name": sample_name,
        "data": data,
        "ppm_scale": ppm_scale,
        "processing_steps": processing_steps,
        "integration_results": integration_results,
        "normalized_results": normalized_results,
        "integration_regions": updated_regions,
        "metadata": peak_results.get("metadata", {}),
        "multiplet_results": peak_results.get("multiplet_results"),
        "peak_annotations": build_peak_annotations(
            peak_results.get("integration_regions", []),
            peak_results.get("multiplet_results"),
        ),
        "peak_details": build_peak_details(
            integration_regions=updated_regions,
            multiplet_results=peak_results.get("multiplet_results"),
            integration_results=integration_results,
            normalized_results=normalized_results,
        ),
    }]


def build_summary_rows(nmr_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """生成 NMR 汇总表所需的平铺行数据。

    Args:
        nmr_results: 当前会话中的 NMR 分析结果列表。

    Returns:
        每个样品对应一行的字典列表，便于直接转成 DataFrame。
    """
    table_data = []
    for result in nmr_results:
        row_data = {"样品": result["sample_name"]}
        for name, value in result["integration_results"].items():
            row_data[f"积分值_{name}"] = value
        for name, value in result["normalized_results"].items():
            row_data[f"归一化值_{name}"] = value
        table_data.append(row_data)
    return table_data


def build_analysis_report(
        nmr_results: list[dict[str, Any]],
        integration_mode: str,
        peak_detection_params: dict[str, Any],
        integration_method: str,
        ppm_offset: float,
) -> str:
    """构建 NMR 分析报告文本。

    Args:
        nmr_results: NMR 结果列表。
        integration_mode: 峰识别模式。
        peak_detection_params: 峰检测参数字典。
        integration_method: 当前选中的积分方法文案。
        ppm_offset: 化学位移偏移校正值。

    Returns:
        完整的 Markdown 风格纯文本报告。
    """
    report = "# NMR分析报告\n\n"

    for index, result_item in enumerate(nmr_results):
        sample_name = result_item["sample_name"]
        integration_results = result_item["integration_results"]
        normalized_results = result_item["normalized_results"]
        integration_regions = result_item.get("integration_regions", [])
        metadata = result_item.get("metadata", {})

        report += f"## 样品 {index + 1}: {sample_name}\n"

        report += "\n### 实验信息\n"
        report += f"- 测试核: {metadata.get('nucleus', '未知')}\n"
        report += f"- 样品溶剂: {metadata.get('solvent', '未知')}\n"
        report += f"- 谱仪频率: {metadata.get('sfo1', '未知')}MHz\n"

        report += "\n### 峰配置信息\n"
        report += f"- 峰识别模式: {integration_mode}\n"

        if integration_mode == "自动模式":
            report += f"- 峰检测阈值: {peak_detection_params.get('threshold', 0.02):.3f}\n"
            report += f"- 最小峰间距: {peak_detection_params.get('min_distance', 0.3):.2f} ppm\n"
            report += f"- 最小峰高阈值: {peak_detection_params.get('min_prominence', 0.01):.3f}\n"
            report += f"- 基线校准多项式阶数: {peak_detection_params.get('baseline_degree', 3)}\n"
            report += f"- 平滑窗口大小: {peak_detection_params.get('smooth_window', 5)}\n"
            report += "\n### 自动峰检测区域结果\n"
            report += f"- 化学位移偏移校正: {ppm_offset:+.2f} ppm\n"
            tms_offset_val = metadata.get("tms_offset", 0.0)
            report += f"- 自动 TMS 偏移校正: {tms_offset_val:+.2f} ppm\n"
            report += f"- 检测到的积分区域数量: {len(integration_regions)}\n"
        else:
            report += "\n### 手动积分区域配置\n"
            report += f"- 积分区域数量: {len(integration_regions)}\n"

        multiplet_results = result_item.get("multiplet_results")
        for region_index, region in enumerate(integration_regions):
            if len(region) == 4:
                name, start, end, peak_position = region
            else:
                name, start, end = region
                peak_position = (start + end) / 2

            # 显示时确保积分范围从小到大
            display_start = min(start, end) + ppm_offset
            display_end = max(start, end) + ppm_offset

            sub_peak_count = f", 子峰数: {len(multiplet_results[region_index].sub_peaks)}" if multiplet_results and region_index < len(multiplet_results) else ""
            report += (
                f"  - 区域 {region_index + 1}: {name} "
                f"(峰位置: {peak_position + ppm_offset:.2f} ppm, "
                f"积分范围: {display_start:.2f} - {display_end:.2f} ppm{sub_peak_count})\n"
            )

        report += "\n### 积分方法\n"
        report += f"- 积分方法: {integration_method}\n"
        report += "\n### 积分结果\n"
        for name, value in integration_results.items():
            report += f"- {name}: {value:.2f}\n"

        report += "\n### 归一化结果\n"
        for name, value in normalized_results.items():
            report += f"- {name}: {value:.2f}\n"

        report += "\n"

    return report


def save_analysis_report(output_dir: str, nmr_results: list[dict[str, Any]], report_content: str) -> list[str]:
    """将统一报告保存到每个样品的输出目录。

    Args:
        output_dir: NMR 输出根目录。
        nmr_results: 当前分析结果列表。
        report_content: 完整报告文本。

    Returns:
        所有已写入报告文件的路径列表。
    """
    report_paths = []
    for result_item in nmr_results:
        sample_name = result_item["sample_name"]
        report_paths.append(save_text_report(output_dir, sample_name, report_content))
    return report_paths
