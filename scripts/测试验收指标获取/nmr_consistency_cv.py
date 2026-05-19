"""基于峰检测计算NMR一致性测试中每个样品三次实验的CV系数。"""

import os
import numpy as np
from analysis.nmr.nmr_analysis import get_nmr_sample_data
from analysis.nmr.peak_detection import detect_peaks


TEST_DIR = r"E:\spectrum_files\nmr\0000一致性测试"
REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")
INDICES = [0, 1, 2]
PEAK_TOLERANCE = 0.05  # 峰匹配容差（ppm）
TMS_PPM_THRESHOLD = 0.5  # TMS峰的ppm阈值，低于此值不参与位置CV计算


def match_peaks_across_spectra(all_peaks: list[list[tuple]]) -> list[list[int]]:
    """将多次测量检测到的峰进行匹配配对。

    以第一次测量的峰为参考，在后续测量的峰列表中寻找最近的匹配峰。

    Args:
        all_peaks: 多次测量的峰列表，每个元素为 [(ppm, height, width), ...]。

    Returns:
        匹配结果列表，每个元素为各次测量中匹配峰的索引列表（-1表示未匹配）。
    """
    if not all_peaks or not all_peaks[0]:
        return []

    ref_peaks = all_peaks[0]
    matched_groups = []

    for ref_idx, (ref_ppm, _, _) in enumerate(ref_peaks):
        indices = [ref_idx]
        for spec_peaks in all_peaks[1:]:
            best_idx = -1
            best_dist = PEAK_TOLERANCE
            for j, (ppm, _, _) in enumerate(spec_peaks):
                dist = abs(ppm - ref_ppm)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = j
            indices.append(best_idx)
        matched_groups.append(indices)

    return matched_groups


def calc_peak_cv(all_peaks: list[list[tuple]], matched_groups: list[list[int]]) -> dict:
    """计算匹配峰的位置CV和强度CV。

    Args:
        all_peaks: 多次测量的峰列表。
        matched_groups: 峰匹配结果。

    Returns:
        包含位置CV、强度CV及峰详情的字典。
    """
    position_cvs = []
    intensity_cvs = []
    peak_details = []

    for indices in matched_groups:
        positions = []
        intensities = []
        for spec_idx, peak_idx in enumerate(indices):
            if peak_idx < 0:
                continue
            ppm, height, width = all_peaks[spec_idx][peak_idx]
            positions.append(ppm)
            intensities.append(height)

        if len(positions) < 2:
            continue

        positions = np.array(positions)
        intensities = np.array(intensities)
        mean_ppm = np.mean(positions)

        # TMS峰（ppm≈0）不参与位置CV，避免均值接近零导致CV失真
        if mean_ppm < TMS_PPM_THRESHOLD:
            pos_cv = 0.0
        else:
            pos_cv = (np.std(positions, ddof=1) / mean_ppm) * 100
        int_cv = (np.std(intensities, ddof=1) / np.mean(intensities)) * 100 if np.mean(intensities) != 0 else 0

        position_cvs.append(pos_cv)
        intensity_cvs.append(int_cv)
        peak_details.append({
            "mean_ppm": np.mean(positions),
            "pos_cv": pos_cv,
            "int_cv": int_cv,
        })

    return {
        "mean_pos_cv": np.mean(position_cvs) if position_cvs else float("nan"),
        "mean_int_cv": np.mean(intensity_cvs) if intensity_cvs else float("nan"),
        "max_pos_cv": np.max(position_cvs) if position_cvs else float("nan"),
        "max_int_cv": np.max(intensity_cvs) if intensity_cvs else float("nan"),
        "num_peaks": len(peak_details),
        "peak_details": peak_details,
    }


def _print_debug(sample_name: str, all_peaks: list[list[tuple]], matched_groups: list[list[int]]):
    """打印单个样品的峰检测与匹配详情。

    Args:
        sample_name: 样品名称。
        all_peaks: 多次测量的峰列表。
        matched_groups: 峰匹配结果。
    """
    print(f"\n{'=' * 70}")
    print(f"  调试: {sample_name}")
    print(f"{'=' * 70}")
    for i, peaks in enumerate(all_peaks):
        print(f"\n  第{i + 1}次测量 — 检测到 {len(peaks)} 个峰:")
        for j, (ppm, height, width) in enumerate(peaks):
            print(f"    峰{j:>2}: ppm={ppm:>8.4f}  height={height:>10.2f}  width={width:.4f}")

    print(f"\n  匹配结果:")
    for gi, indices in enumerate(matched_groups):
        parts = []
        for spec_idx, peak_idx in enumerate(indices):
            if peak_idx < 0:
                parts.append(f"测量{spec_idx + 1}=未匹配")
            else:
                ppm, height, _ = all_peaks[spec_idx][peak_idx]
                parts.append(f"测量{spec_idx + 1}={ppm:.4f}")
        print(f"    峰组{gi + 1}: {', '.join(parts)}")
    print()


def main(verbose_sample: str = ""):
    """遍历所有样品目录，基于峰检测计算并输出三次实验的CV系数。

    Args:
        verbose_sample: 指定样品名称时，输出该样品的峰检测详情。
    """
    sample_dirs = sorted([
        d for d in os.listdir(TEST_DIR)
        if os.path.isdir(os.path.join(TEST_DIR, d))
    ])

    results = []

    for sample_name in sample_dirs:
        sample_path = os.path.join(TEST_DIR, sample_name)
        all_peaks = []
        for idx in INDICES:
            try:
                data, ppm_scale, _, metadata = get_nmr_sample_data(sample_path, index=idx)
                peaks = detect_peaks(data, ppm_scale)
                all_peaks.append(peaks)
            except Exception as e:
                print(f"  警告: {sample_name} index={idx} 读取失败: {e}")
                continue

        if len(all_peaks) < 2:
            results.append({"name": sample_name, "error": "数据不足"})
            continue

        matched = match_peaks_across_spectra(all_peaks)
        if not matched:
            results.append({"name": sample_name, "error": "未检测到峰"})
            continue

        if verbose_sample and sample_name == verbose_sample:
            _print_debug(sample_name, all_peaks, matched)

        cv_result = calc_peak_cv(all_peaks, matched)
        results.append({"name": sample_name, **cv_result})

    # 构建报告内容
    lines = []
    lines.append(f"# NMR 一致性测试报告 — 基于峰检测的 CV 系数")
    lines.append(f"")
    lines.append(f"**测试目录**: `{TEST_DIR}`")
    lines.append(f"**测量次数**: {len(INDICES)} 次（index={INDICES}）")
    lines.append(f"")
    lines.append(f"## 汇总结果")
    lines.append(f"")
    lines.append(f"| 样品名称 | 峰数量 | 位置CV(%) | 强度CV(%) | 最大位置CV(%) | 最大强度CV(%) |")
    lines.append(f"|---|---:|---:|---:|---:|---:|")

    for r in results:
        if "error" in r:
            lines.append(f"| {r['name']} | {r['error']} | | | | |")
            continue
        lines.append(f"| {r['name']} | {r['num_peaks']} | {r['mean_pos_cv']:.4f} | "
                     f"{r['mean_int_cv']:.4f} | {r['max_pos_cv']:.4f} | {r['max_int_cv']:.4f} |")

    # 汇总统计
    valid = [r for r in results if "error" not in r]
    if valid:
        avg_pos = np.mean([r["mean_pos_cv"] for r in valid])
        avg_int = np.mean([r["mean_int_cv"] for r in valid])
        lines.append(f"| **汇总（{len(valid)} 个样品）** | | **{avg_pos:.4f}** | **{avg_int:.4f}** | | |")

    # 各样品峰详情
    lines.append(f"")
    lines.append(f"## 各样品峰详情")
    for r in results:
        if "error" in r or "peak_details" not in r:
            continue
        lines.append(f"")
        lines.append(f"### {r['name']}")
        lines.append(f"")
        lines.append(f"| 峰位(ppm) | 位置CV(%) | 强度CV(%) |")
        lines.append(f"|---|---:|---:|")
        for p in r["peak_details"]:
            lines.append(f"| {p['mean_ppm']:.4f} | {p['pos_cv']:.4f} | {p['int_cv']:.4f} |")

    report_text = "\n".join(lines)

    # 控制台输出
    print(report_text)

    # 保存为 md 文件
    os.makedirs(REPORT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(REPORT_DIR, "nmr_cv_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n报告已保存: {report_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NMR一致性测试CV系数计算")
    parser.add_argument("-v", "--verbose", type=str, default="", help="输出指定样品的峰检测详情")
    args = parser.parse_args()
    main(verbose_sample=args.verbose)
