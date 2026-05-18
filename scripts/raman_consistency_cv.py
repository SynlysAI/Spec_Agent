"""基于峰检测计算Raman一致性测试中每个样品多次实验的CV系数。"""

import os
import numpy as np
from scipy.signal import find_peaks


DATA_DIR = r"E:\spectrum_files\raman\samples\2026-05-14"
IDS = [0, 1, 2]
PEAK_PROMINENCE = 0.1
PEAK_TOLERANCE = 10  # 峰匹配容差（cm⁻¹）
HEADER_LINES = 3  # dat文件头部跳过行数


def load_raman_data(filepath: str) -> tuple[np.ndarray, np.ndarray]:
    """加载Raman dat文件，返回拉曼位移和强度数组。

    Args:
        filepath: dat文件路径。

    Returns:
        (wavelengths, intensities) 元组。
    """
    with open(filepath, "r") as f:
        data = np.array([line.split() for line in f.readlines()[HEADER_LINES:]], dtype=float)
    return data[:, -2], data[:, -1]


def detect_peaks(wavelengths: np.ndarray, intensities: np.ndarray) -> list[tuple]:
    """检测Raman谱图中的峰。

    Args:
        wavelengths: 拉曼位移数组。
        intensities: 强度数组。

    Returns:
        峰列表，每个元素为 (position, height)。
    """
    prominence = PEAK_PROMINENCE * np.max(intensities)
    peaks, properties = find_peaks(intensities, prominence=prominence)

    result = []
    for i, peak_idx in enumerate(peaks):
        # 取峰附近局部窗口，用高斯拟合精确定位
        window = 5
        start = max(0, peak_idx.item() - window)
        end = min(len(wavelengths), peak_idx.item() + window + 1)
        x_local = wavelengths[start:end]
        y_local = intensities[start:end]

        refined_pos, refined_int = _gaussian_peak_fit(x_local, y_local)
        result.append((refined_pos, refined_int))
    return result


def _gaussian_peak_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """高斯拟合精确定位峰位置和强度。

    Args:
        x: 局部波长数组。
        y: 局部强度数组。

    Returns:
        (峰位置, 峰强度)。
    """
    try:
        y_safe = np.maximum(y, 1e-10)
        log_y = np.log(y_safe)
        a, b, c = np.polyfit(x, log_y, 2)

        peak_pos = -b / (2 * a)
        peak_intensity = np.exp(c - b ** 2 / (4 * a))

        if not (np.min(x) <= peak_pos <= np.max(x)):
            peak_pos = x[np.argmax(y)]
            peak_intensity = np.max(y)

        return peak_pos, peak_intensity
    except Exception:
        idx = np.argmax(y)
        return x[idx], y[idx]


def match_peaks_across_spectra(all_peaks: list[list[tuple]]) -> list[list[int]]:
    """将多次测量检测到的峰进行匹配配对。

    Args:
        all_peaks: 多次测量的峰列表，每个元素为 [(position, height), ...]。

    Returns:
        匹配结果列表，每个元素为各次测量中匹配峰的索引列表（-1表示未匹配）。
    """
    if not all_peaks or not all_peaks[0]:
        return []

    ref_peaks = all_peaks[0]
    matched_groups = []

    for ref_idx, (ref_pos, _) in enumerate(ref_peaks):
        indices = [ref_idx]
        for spec_peaks in all_peaks[1:]:
            best_idx = -1
            best_dist = PEAK_TOLERANCE
            for j, (pos, _) in enumerate(spec_peaks):
                dist = abs(pos - ref_pos)
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
        包含位置CV、强度CV及峰数量的字典。
    """
    position_cvs = []
    intensity_cvs = []

    for indices in matched_groups:
        positions = []
        intensities = []
        for spec_idx, peak_idx in enumerate(indices):
            if peak_idx < 0:
                continue
            pos, height = all_peaks[spec_idx][peak_idx]
            positions.append(pos)
            intensities.append(height)

        if len(positions) < 2:
            continue

        positions = np.array(positions)
        intensities = np.array(intensities)

        pos_cv = (np.std(positions, ddof=1) / np.mean(positions)) * 100 if np.mean(positions) != 0 else 0
        int_cv = (np.std(intensities, ddof=1) / np.mean(intensities)) * 100 if np.mean(intensities) != 0 else 0

        position_cvs.append(pos_cv)
        intensity_cvs.append(int_cv)

    return {
        "mean_pos_cv": np.mean(position_cvs) if position_cvs else float("nan"),
        "mean_int_cv": np.mean(intensity_cvs) if intensity_cvs else float("nan"),
        "max_pos_cv": np.max(position_cvs) if position_cvs else float("nan"),
        "max_int_cv": np.max(intensity_cvs) if intensity_cvs else float("nan"),
        "num_peaks": len(position_cvs),
    }


def main():
    """遍历所有样品，基于峰检测计算并输出多次实验的CV系数。"""
    files = sorted(os.listdir(DATA_DIR))
    groups = sorted(set(f.rsplit("_", 1)[0] for f in files))

    results = []

    for sample_name in groups:
        all_peaks = []
        for i in IDS:
            filepath = os.path.join(DATA_DIR, f"{sample_name}_{i}.dat")
            if not os.path.exists(filepath):
                continue
            wavelengths, intensities = load_raman_data(filepath)
            peaks = detect_peaks(wavelengths, intensities)
            all_peaks.append(peaks)

        if len(all_peaks) < 2:
            results.append({"name": sample_name, "error": "数据不足"})
            continue

        matched = match_peaks_across_spectra(all_peaks)
        if not matched:
            results.append({"name": sample_name, "error": "未检测到峰"})
            continue

        cv_result = calc_peak_cv(all_peaks, matched)
        results.append({"name": sample_name, **cv_result})

    # 输出表格
    header = f"{'样品名称':<20} {'峰数量':>6} {'位置CV(%)':>10} {'强度CV(%)':>10} {'最大位置CV(%)':>14} {'最大强度CV(%)':>14}"
    separator = "=" * len(header)
    print(separator)
    print("Raman 一致性测试 — 基于峰检测的 CV 系数")
    print(separator)
    print(header)
    print("-" * len(header))

    for r in results:
        if "error" in r:
            print(f"{r['name']:<20} {r['error']}")
            continue
        print(f"{r['name']:<20} {r['num_peaks']:>6} "
              f"{r['mean_pos_cv']:>10.4f} {r['mean_int_cv']:>10.4f} "
              f"{r['max_pos_cv']:>14.4f} {r['max_int_cv']:>14.4f}")

    print(separator)

    # 汇总统计
    valid = [r for r in results if "error" not in r]
    if valid:
        avg_pos = np.mean([r["mean_pos_cv"] for r in valid])
        avg_int = np.mean([r["mean_int_cv"] for r in valid])
        print(f"\n{'汇总 (' + str(len(valid)) + ' 个样品)':<20} "
              f"{'':>6} {avg_pos:>10.4f} {avg_int:>10.4f}")
        print(separator)


if __name__ == "__main__":
    main()
