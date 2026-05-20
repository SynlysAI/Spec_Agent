"""基于峰检测计算LC-MS一致性测试中每个样品多次实验的CV系数。"""

import os
from typing import Optional

import numpy as np
import yaml


CONFIG_PATH = r"E:\LCMS\config\example_config.yaml"
DATA_DIR = r"E:\LCMS\outputs\rda_batch_analysis\mzml"
REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")


# ---------------------------------------------------------------------------
# mzML 读取
# ---------------------------------------------------------------------------

def _try_import_mzml_reader():
    """尝试导入 mzML 读取依赖（优先 pyteomics）。"""
    try:
        from pyteomics import mzml
        return "pyteomics", mzml
    except ImportError:
        pass
    try:
        import pymzml
        return "pymzml", pymzml
    except ImportError:
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
    """读取 mzML 文件，返回 TIC 时间/强度和扫描记录。

    Args:
        filepath: mzML 文件路径。

    Returns:
        (tic_times, tic_intensities, scan_records) 元组。
    """
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
                ints = np.asarray(spectrum.get("intensity array", []), dtype=float)
                scan_time = _extract_scan_time_pyteomics(spectrum)
                if scan_time is None:
                    continue
                scan_records.append((scan_time, mzs, ints))
                tic_times.append(scan_time)
                tic_intensities.append(float(np.sum(ints)))
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
            ints = np.asarray(spectrum.i, dtype=float)
            scan_records.append((scan_time, mzs, ints))
            tic_times.append(scan_time)
            tic_intensities.append(float(np.sum(ints)))

    return (np.asarray(tic_times, dtype=float),
            np.asarray(tic_intensities, dtype=float),
            scan_records)


# ---------------------------------------------------------------------------
# EIC 提取与峰检测
# ---------------------------------------------------------------------------

def extract_eic(scan_records: list[tuple], mz_target: float, mz_tolerance: float
                ) -> tuple[np.ndarray, np.ndarray]:
    """从扫描记录中提取指定 m/z 范围的 EIC（提取离子色谱图）。

    Args:
        scan_records: read_mzml 返回的扫描记录列表。
        mz_target: 目标 m/z 值。
        mz_tolerance: m/z 容差。

    Returns:
        (times, intensities) 数组。
    """
    times, intensities = [], []
    low, high = mz_target - mz_tolerance, mz_target + mz_tolerance
    for scan_time, mzs, ints in scan_records:
        mask = (mzs >= low) & (mzs <= high)
        intensities.append(float(np.sum(ints[mask])) if np.any(mask) else 0.0)
        times.append(scan_time)
    return np.asarray(times, dtype=float), np.asarray(intensities, dtype=float)


def detect_peak(times: np.ndarray, intensities: np.ndarray,
                rt_start: float, rt_end: float) -> Optional[dict]:
    """在指定 RT 窗口内检测峰，返回峰的 RT、面积和高度。

    Args:
        times: 时间数组。
        intensities: 强度数组。
        rt_start: RT 窗口起始（分钟）。
        rt_end: RT 窗口结束（分钟）。

    Returns:
        峰信息字典，包含 rt/area/height，未检测到返回 None。
    """
    mask = (times >= rt_start) & (times <= rt_end)
    sub_t, sub_i = times[mask], intensities[mask]
    if len(sub_t) < 3:
        return None

    apex_idx = int(np.argmax(sub_i))
    if sub_i[apex_idx] <= 0:
        return None

    threshold = float(sub_i[apex_idx]) * 0.05
    start_idx = apex_idx
    end_idx = apex_idx
    while start_idx > 0 and sub_i[start_idx] > threshold:
        start_idx -= 1
    while end_idx < len(sub_i) - 1 and sub_i[end_idx] > threshold:
        end_idx += 1
    if end_idx - start_idx < 2:
        return None

    peak_t = sub_t[start_idx:end_idx + 1]
    peak_i = sub_i[start_idx:end_idx + 1]
    baseline = np.linspace(peak_i[0], peak_i[-1], len(peak_i))
    corrected = np.maximum(peak_i - baseline, 0.0)

    return {
        "rt": float(sub_t[apex_idx]),
        "area": float(np.trapezoid(corrected, peak_t)),
        "height": float(np.max(corrected)),
    }


# ---------------------------------------------------------------------------
# CV 计算
# ---------------------------------------------------------------------------

def calc_cv(values: list[float]) -> Optional[float]:
    """计算变异系数 CV(%)。

    Args:
        values: 数值列表。

    Returns:
        CV 百分比，数据不足时返回 None。
    """
    if len(values) < 2:
        return None
    arr = np.array(values)
    mean = float(np.mean(arr))
    if mean == 0:
        return None
    return float(np.std(arr, ddof=1) / mean * 100)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    """遍历所有样品，基于配置文件计算并输出多次实验的 CV 系数。"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".mzML"))
    # 按样品分组：X.mzML, X_1.mzML, X_2.mzML -> X
    groups = sorted({
        f.replace(".mzML", "").rsplit("_", 1)[0] if "_" in f and f.split("_")[-1].replace(".mzML", "").isdigit()
        else f.replace(".mzML", "")
        for f in files
    })

    tic_enabled = config.get("tic", {}).get("enabled", True)
    tic_window = config.get("tic", {}).get("rt_window", {})
    eic_targets = config.get("eic_targets", [])

    results = []

    for sample_name in groups:
        # 收集该样品的所有重复文件
        sample_files = sorted(f for f in files if f.replace(".mzML", "").rsplit("_", 1)[0] == sample_name
                              or f == f"{sample_name}.mzML")

        tic_peaks = []       # TIC 峰列表，每次测量一个
        eic_peaks = {}       # {target_name: [每次测量的峰]}

        for mzml_file in sample_files:
            filepath = os.path.join(DATA_DIR, mzml_file)
            try:
                tic_times, tic_intensities, scan_records = read_mzml(filepath)
            except Exception as e:
                print(f"  警告: {mzml_file} 读取失败: {e}")
                continue

            # TIC 峰检测
            if tic_enabled and len(tic_times) > 0:
                peak = detect_peak(tic_times, tic_intensities,
                                   float(tic_window.get("start", 0)),
                                   float(tic_window.get("end", 10)))
                if peak:
                    tic_peaks.append(peak)

            # EIC 峰检测
            for target in eic_targets:
                name = target["name"]
                eic_times, eic_intensities = extract_eic(
                    scan_records, float(target["mz"]), float(target["mz_tolerance"]))
                rt_win = target.get("rt_window", {})
                peak = detect_peak(eic_times, eic_intensities,
                                   float(rt_win.get("start", 0)),
                                   float(rt_win.get("end", 10)))
                if peak:
                    eic_peaks.setdefault(name, []).append(peak)

        # 计算 CV
        sample_result = {"name": sample_name, "peaks": []}

        if tic_peaks:
            rts = [p["rt"] for p in tic_peaks]
            areas = [p["area"] for p in tic_peaks]
            heights = [p["height"] for p in tic_peaks]
            sample_result["peaks"].append({
                "type": "TIC",
                "analyte": "TIC_main_peak",
                "n_replicates": len(tic_peaks),
                "rt_cv": calc_cv(rts),
                "area_cv": calc_cv(areas),
                "height_cv": calc_cv(heights),
                "mean_rt": float(np.mean(rts)),
                "mean_area": float(np.mean(areas)),
            })

        for target_name, peaks in eic_peaks.items():
            rts = [p["rt"] for p in peaks]
            areas = [p["area"] for p in peaks]
            heights = [p["height"] for p in peaks]
            sample_result["peaks"].append({
                "type": "EIC",
                "analyte": target_name,
                "n_replicates": len(peaks),
                "rt_cv": calc_cv(rts),
                "area_cv": calc_cv(areas),
                "height_cv": calc_cv(heights),
                "mean_rt": float(np.mean(rts)),
                "mean_area": float(np.mean(areas)),
            })

        if sample_result["peaks"]:
            results.append(sample_result)
        else:
            results.append({"name": sample_name, "error": "未检测到峰"})

    _build_report(results, config)


def _build_report(results: list[dict], config: dict):
    """构建并保存 md 报告。

    Args:
        results: 各样品的计算结果列表。
        config: YAML 配置字典。
    """
    lines = []
    lines.append("# LC-MS 一致性测试报告 — 基于峰检测的 CV 系数")
    lines.append("")
    lines.append(f"**测试目录**: `{DATA_DIR}`")
    lines.append(f"**配置文件**: `{CONFIG_PATH}`")
    lines.append(f"**验收标准**: RT CV ≤ {config['acceptance']['rt_cv_max_percent']}%, "
                 f"面积 CV ≤ {config['acceptance']['area_cv_max_percent']}%")
    lines.append("")
    lines.append("## 汇总结果")
    lines.append("")
    lines.append("| 样品 | 峰类型 | 分析物 | 重复数 | RT CV(%) | 面积 CV(%) | 高度 CV(%) |")
    lines.append("|---|---|---|---:|---:|---:|---:|")

    valid_results = [r for r in results if "error" not in r]
    all_rt_cvs = []
    all_area_cvs = []

    for r in valid_results:
        for p in r["peaks"]:
            rt_cv_str = f"{p['rt_cv']:.4f}" if p["rt_cv"] is not None else "N/A"
            area_cv_str = f"{p['area_cv']:.4f}" if p["area_cv"] is not None else "N/A"
            height_cv_str = f"{p['height_cv']:.4f}" if p["height_cv"] is not None else "N/A"
            lines.append(f"| {r['name']} | {p['type']} | {p['analyte']} | "
                         f"{p['n_replicates']} | {rt_cv_str} | {area_cv_str} | {height_cv_str} |")
            if p["rt_cv"] is not None:
                all_rt_cvs.append(p["rt_cv"])
            if p["area_cv"] is not None:
                all_area_cvs.append(p["area_cv"])

    for r in results:
        if "error" in r:
            lines.append(f"| {r['name']} | {r['error']} | | | | | |")

    if all_rt_cvs:
        lines.append(f"| **汇总（{len(valid_results)} 个样品）** | | | | "
                     f"**{np.mean(all_rt_cvs):.4f}** | **{np.mean(all_area_cvs):.4f}** | |")

    # 各样品详情
    lines.append("")
    lines.append("## 各样品峰详情")
    for r in valid_results:
        lines.append("")
        lines.append(f"### {r['name']}")
        lines.append("")
        lines.append("| 类型 | 分析物 | 平均RT(min) | 平均面积 | RT CV(%) | 面积 CV(%) | 高度 CV(%) |")
        lines.append("|---|---|---:|---:|---:|---:|---:|")
        for p in r["peaks"]:
            rt_cv_str = f"{p['rt_cv']:.4f}" if p["rt_cv"] is not None else "N/A"
            area_cv_str = f"{p['area_cv']:.4f}" if p["area_cv"] is not None else "N/A"
            height_cv_str = f"{p['height_cv']:.4f}" if p["height_cv"] is not None else "N/A"
            lines.append(f"| {p['type']} | {p['analyte']} | {p['mean_rt']:.4f} | "
                         f"{p['mean_area']:.2f} | {rt_cv_str} | {area_cv_str} | {height_cv_str} |")

    report_text = "\n".join(lines)
    print(report_text)

    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(REPORT_DIR, "lcms_cv_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n报告已保存: {report_path}")


if __name__ == "__main__":
    main()
