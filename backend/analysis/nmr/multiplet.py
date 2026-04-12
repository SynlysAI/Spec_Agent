"""
NMR 多重峰 (Multiplet) 子峰聚合与模式识别模块

功能：
1. 将相邻子峰按偶合常数窗口聚类
2. 对每个簇进行模式匹配 (s/d/t/q/dd/dt/m)
3. 合并积分区域
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np


@dataclass
class MultipletResult:
    """单个多重峰组的分析结果"""
    pattern: str                # "s", "d", "t", "q", "dd", "dt", "m"
    center_ppm: float           # 加权中心位置
    j_values: List[float]       # 偶合常数列表 (Hz)
    sub_peaks: List[Tuple]      # 子峰列表 [(ppm, height, width), ...]
    intensity_ratio: List[float]  # 归一化强度比例
    region_start: float         # 聚合后积分区域起始 ppm (较大值)
    region_end: float           # 聚合后积分区域结束 ppm (较小值)
    peak_type: str = "目标峰"   # 峰类型标注，如 "目标峰"、"Solvent-CHCl3"、"TMS" 等

    def to_display_str(self) -> str:
        """生成展示字符串，如 't (J=7.0 Hz)'"""
        if self.pattern == "s":
            return "s"
        if self.pattern == "m":
            return "m"
        j_str = ", ".join(f"{j:.1f}" for j in self.j_values)
        return f"{self.pattern} (J={j_str} Hz)"


# 帕斯卡三角形前几行 (归一化)
PASCAL_ROWS = {
    1: [1.0],
    2: [1.0, 1.0],
    3: [1.0, 2.0, 1.0],
    4: [1.0, 3.0, 3.0, 1.0],
    5: [1.0, 4.0, 6.0, 4.0, 1.0],
}


def _ppm_to_hz(ppm_diff: float, sfo1: float) -> float:
    """将 ppm 差值转换为 Hz"""
    return abs(ppm_diff) * sfo1


def _normalize_intensities(heights: List[float]) -> List[float]:
    """将强度列表归一化，使最小值为 1.0"""
    min_h = min(heights)
    if min_h <= 0:
        min_h = 1.0
    return [h / min_h for h in heights]


def _check_ratio_match(observed: List[float], expected: List[float], tolerance: float = 0.25) -> bool:
    """检查观察到的强度比是否与期望比例匹配

    Args:
        observed: 归一化后的观察强度比
        expected: 期望的理论强度比
        tolerance: 相对误差容限
    """
    if len(observed) != len(expected):
        return False
    exp_sum = sum(expected)
    obs_sum = sum(observed)
    if exp_sum == 0 or obs_sum == 0:
        return False
    exp_norm = [e / exp_sum for e in expected]
    obs_norm = [o / obs_sum for o in observed]
    for e, o in zip(exp_norm, obs_norm):
        if abs(e - o) > tolerance:
            return False
    return True


def _check_equal_spacing(positions: List[float], sfo1: float, tolerance_hz: float = 1.5) -> Tuple[bool, float]:
    """检查峰位置是否等间距

    Args:
        positions: ppm 位置列表（已排序）
        sfo1: 谱仪频率 MHz
        tolerance_hz: 允许的间距误差 (Hz)

    Returns:
        (is_equal_spacing, avg_spacing_hz)
    """
    if len(positions) < 2:
        return True, 0.0

    gaps = [abs(positions[i] - positions[i + 1]) * sfo1 for i in range(len(positions) - 1)]
    avg_gap = np.mean(gaps)

    for gap in gaps:
        if abs(gap - avg_gap) > tolerance_hz:
            return False, avg_gap
    return True, avg_gap


def cluster_peaks_by_coupling(
    peaks: List[Tuple],
    sfo1: float,
    max_coupling_hz: float = 20.0,
) -> List[List[Tuple]]:
    """将相邻子峰按偶合常数窗口聚类

    Args:
        peaks: 检测到的峰列表，元素为 (ppm, height, width)
        sfo1: 谱仪基础频率 (MHz)
        max_coupling_hz: 最大偶合常数阈值 (Hz)，相邻峰间距小于此值归入同一簇

    Returns:
        聚类后的峰簇列表，每簇内按 ppm 从高到低排序
    """
    if not peaks:
        return []

    # 按 ppm 从高到低排序
    sorted_peaks = sorted(peaks, key=lambda p: p[0], reverse=True)

    clusters = []
    current_cluster = [sorted_peaks[0]]

    for i in range(1, len(sorted_peaks)):
        prev_ppm = current_cluster[-1][0]
        curr_ppm = sorted_peaks[i][0]
        gap_hz = _ppm_to_hz(prev_ppm - curr_ppm, sfo1)

        if gap_hz < max_coupling_hz:
            current_cluster.append(sorted_peaks[i])
        else:
            clusters.append(current_cluster)
            current_cluster = [sorted_peaks[i]]

    clusters.append(current_cluster)
    return clusters


def _analyze_simple_pattern(n_peaks: int, cluster: List[Tuple], sfo1: float) -> MultipletResult | None:
    """尝试匹配简单多重峰模式 (s/d/t/q)

    Returns:
        匹配成功返回 MultipletResult，否则返回 None
    """
    positions = [p[0] for p in cluster]
    heights = [p[1] for p in cluster]
    widths = [p[2] for p in cluster]
    norm_heights = _normalize_intensities(heights)

    if n_peaks == 1:
        # 单峰 (s)
        ppm, height, width = cluster[0]
        return MultipletResult(
            pattern="s",
            center_ppm=ppm,
            j_values=[],
            sub_peaks=cluster,
            intensity_ratio=[1.0],
            region_start=ppm + width,
            region_end=ppm - width,
        )

    equal_spaced, avg_j = _check_equal_spacing(positions, sfo1)

    if n_peaks == 2:
        # 双峰 (d): 间距恒定，强度比 ~1:1
        if _check_ratio_match(norm_heights, PASCAL_ROWS[2], tolerance=0.30):
            j_val = _ppm_to_hz(positions[0] - positions[1], sfo1)
            return MultipletResult(
                pattern="d",
                center_ppm=sum(p * h for p, h in zip(positions, heights)) / sum(heights),
                j_values=[j_val],
                sub_peaks=cluster,
                intensity_ratio=norm_heights,
                region_start=max(p + w for p, _, w in cluster),
                region_end=min(p - w for p, _, w in cluster),
            )

    if n_peaks == 3 and equal_spaced:
        # 三重峰 (t): 等间距，强度比 ~1:2:1
        if _check_ratio_match(norm_heights, PASCAL_ROWS[3], tolerance=0.35):
            return MultipletResult(
                pattern="t",
                center_ppm=sum(p * h for p, h in zip(positions, heights)) / sum(heights),
                j_values=[avg_j],
                sub_peaks=cluster,
                intensity_ratio=norm_heights,
                region_start=max(p + w for p, _, w in cluster),
                region_end=min(p - w for p, _, w in cluster),
            )

    if n_peaks == 4 and equal_spaced:
        # 四重峰 (q): 等间距，强度比 ~1:3:3:1
        if _check_ratio_match(norm_heights, PASCAL_ROWS[4], tolerance=0.35):
            return MultipletResult(
                pattern="q",
                center_ppm=sum(p * h for p, h in zip(positions, heights)) / sum(heights),
                j_values=[avg_j],
                sub_peaks=cluster,
                intensity_ratio=norm_heights,
                region_start=max(p + w for p, _, w in cluster),
                region_end=min(p - w for p, _, w in cluster),
            )

    return None


def _analyze_complex_pattern(cluster: List[Tuple], sfo1: float) -> MultipletResult:
    """分析复杂多重峰模式 (dd, dt, td, tt 等)，使用迭代反卷积方法

    策略：
    1. 找到所有峰间距，按大小排序
    2. 最大间距 → 大偶合常数 J1
    3. 将峰按 J1 间距分成两组，检查每组是否为简单模式
    4. 如果能分成两个简单模式，组合成 dd/dt/td 等
    5. 否则标记为 m (multiplet)
    """
    positions = [p[0] for p in cluster]
    heights = [p[1] for p in cluster]
    n = len(cluster)

    if n < 2:
        return _make_multiplet_m(cluster, sfo1)

    # 计算所有相邻峰间距 (Hz)
    gaps = []
    for i in range(n - 1):
        gap_hz = _ppm_to_hz(positions[i] - positions[i + 1], sfo1)
        gaps.append(gap_hz)

    if not gaps:
        return _make_multiplet_m(cluster, sfo1)

    # 尝试 dd 模式 (doublet of doublets): 4 个峰，2 个不同 J
    if n == 4:
        j1, j2 = _try_dd_pattern(positions, heights, sfo1)
        if j1 is not None:
            return MultipletResult(
                pattern="dd",
                center_ppm=sum(p * h for p, h in zip(positions, heights)) / sum(heights),
                j_values=sorted([j1, j2], reverse=True),
                sub_peaks=cluster,
                intensity_ratio=_normalize_intensities(heights),
                region_start=max(p + w for p, _, w in cluster),
                region_end=min(p - w for p, _, w in cluster),
            )

    # 尝试 dt 模式 (doublet of triplets): 6 个峰
    if n == 6:
        result = _try_dt_pattern(cluster, sfo1)
        if result is not None:
            return result

    # 尝试 td 模式 (triplet of doublets): 6 个峰
    if n == 6:
        result = _try_td_pattern(cluster, sfo1)
        if result is not None:
            return result

    # 兜底: 标记为 m
    return _make_multiplet_m(cluster, sfo1)


def _try_dd_pattern(
    positions: List[float], heights: List[float], sfo1: float
) -> Tuple[float | None, float | None]:
    """尝试识别 dd 模式 (4 个峰，2 个偶合常数)

    dd 的特征：4 个峰形成矩形排列
    峰位置按 ppm 从高到低: p1, p2, p3, p4
    J1 = |p1 - p3| = |p2 - p4| (大间距)
    J2 = |p1 - p2| = |p3 - p4| (小间距)

    Returns:
        (J1, J2) 或 (None, None)
    """
    if len(positions) != 4:
        return None, None

    p1, p2, p3, p4 = positions

    # 计算所有可能的间距
    j12 = _ppm_to_hz(p1 - p2, sfo1)
    j13 = _ppm_to_hz(p1 - p3, sfo1)
    j14 = _ppm_to_hz(p1 - p4, sfo1)
    j23 = _ppm_to_hz(p2 - p3, sfo1)
    j24 = _ppm_to_hz(p2 - p4, sfo1)
    j34 = _ppm_to_hz(p3 - p4, sfo1)

    # dd 模式检查：存在两组平行间距
    # 方案1: J1 = j13 = j24, J2 = j12 = j34
    tol_hz = 2.0  # Hz 容差
    if abs(j13 - j24) < tol_hz and abs(j12 - j34) < tol_hz and j13 > j12:
        return (j13 + j24) / 2, (j12 + j34) / 2

    # 方案2: J1 = j14, 分成 j12 + j24 或者 j13 + j34
    # J1 = j12 = j34, J2 = j23
    if abs(j12 - j34) < tol_hz and j23 < j12:
        return (j12 + j34) / 2, j23

    # 方案3: J1 = j14 = j23, 但这不满足矩形结构
    # 方案4: J1 = j13 = j24 (与方案1相同)

    return None, None


def _try_dt_pattern(cluster: List[Tuple], sfo1: float) -> MultipletResult | None:
    """尝试识别 dt 模式 (doublet of triplets, 6 个峰)

    dt 特征：先按大 J 分成两组（每组 3 个），组内等间距（小 J）
    """
    positions = [p[0] for p in cluster]
    heights = [p[1] for p in cluster]
    n = len(positions)

    if n != 6:
        return None

    # 按 ppm 从高到低已排序
    # dt: 峰排列模式 [a1, b1, a2, b2, a3, b3] 交错排列
    # 其中 a 组为 triplet 内的三个位置，b 组是 a 的偏移 (大 J)
    # 或者：先按大 J 分成两组 {p1,p3,p5} 和 {p2,p4,p6}

    # 尝试分组：奇数位和偶数位
    group_a = [(positions[i], heights[i], cluster[i][2]) for i in range(0, n, 2)]
    group_b = [(positions[i], heights[i], cluster[i][2]) for i in range(1, n, 2)]

    if len(group_a) == 3 and len(group_b) == 3:
        pos_a = [p[0] for p in group_a]
        eq_a, j_small = _check_equal_spacing(pos_a, sfo1, tolerance_hz=2.0)
        pos_b = [p[0] for p in group_b]
        eq_b, j_small_b = _check_equal_spacing(pos_b, sfo1, tolerance_hz=2.0)

        if eq_a and eq_b and abs(j_small - j_small_b) < 2.0:
            # 大 J = 两组中心之间的间距
            center_a = np.mean(pos_a)
            center_b = np.mean(pos_b)
            j_large = _ppm_to_hz(center_a - center_b, sfo1)
            j_small_avg = (j_small + j_small_b) / 2

            if j_large > j_small_avg:
                return MultipletResult(
                    pattern="dt",
                    center_ppm=sum(p * h for p, h in zip(positions, heights)) / sum(heights),
                    j_values=sorted([j_large, j_small_avg], reverse=True),
                    sub_peaks=cluster,
                    intensity_ratio=_normalize_intensities(heights),
                    region_start=max(p + w for p, _, w in cluster),
                    region_end=min(p - w for p, _, w in cluster),
                )

    return None


def _try_td_pattern(cluster: List[Tuple], sfo1: float) -> MultipletResult | None:
    """尝试识别 td 模式 (triplet of doublets, 6 个峰)

    td 特征：先按大 J 分成三组（每组 2 个），组内间距为小 J
    峰排列: [a1, b1, a2, b2, a3, b3] 其中 {a1,a2,a3} 等间距（大 J）
    """
    positions = [p[0] for p in cluster]
    heights = [p[1] for p in cluster]
    n = len(positions)

    if n != 6:
        return None

    # 尝试分组：相邻峰对 (p1,p2), (p3,p4), (p5,p6) 每对内间距为小 J
    pairs = [(positions[i:i + 2], heights[i:i + 2]) for i in range(0, n, 2)]

    if len(pairs) == 3:
        # 检查每对内间距是否一致（小 J）
        pair_gaps = [_ppm_to_hz(p[0][0] - p[0][1], sfo1) for p in pairs]
        avg_small_j = np.mean(pair_gaps)
        small_j_consistent = all(abs(g - avg_small_j) < 2.0 for g in pair_gaps)

        if small_j_consistent:
            # 每对的中心位置
            pair_centers = [np.mean(p[0]) for p in pairs]
            eq_centers, j_large = _check_equal_spacing(pair_centers, sfo1, tolerance_hz=2.0)

            if eq_centers and j_large > avg_small_j:
                return MultipletResult(
                    pattern="td",
                    center_ppm=sum(p * h for p, h in zip(positions, heights)) / sum(heights),
                    j_values=sorted([j_large, avg_small_j], reverse=True),
                    sub_peaks=cluster,
                    intensity_ratio=_normalize_intensities(heights),
                    region_start=max(p + w for p, _, w in cluster),
                    region_end=min(p - w for p, _, w in cluster),
                )

    return None


def _make_multiplet_m(cluster: List[Tuple], sfo1: float) -> MultipletResult:
    """创建 m (multiplet) 兜底结果"""
    positions = [p[0] for p in cluster]
    heights = [p[1] for p in cluster]

    return MultipletResult(
        pattern="m",
        center_ppm=sum(p * h for p, h in zip(positions, heights)) / sum(heights),
        j_values=[],
        sub_peaks=cluster,
        intensity_ratio=_normalize_intensities(heights),
        region_start=max(p + w for p, _, w in cluster),
        region_end=min(p - w for p, _, w in cluster),
    )


def analyze_multiplet_pattern(cluster: List[Tuple], sfo1: float) -> MultipletResult:
    """对单个簇进行模式匹配

    Args:
        cluster: 一个簇内的峰列表 [(ppm, height, width), ...]
        sfo1: 谱仪基础频率 (MHz)

    Returns:
        MultipletResult 分析结果
    """
    n = len(cluster)

    # 先尝试简单模式
    result = _analyze_simple_pattern(n, cluster, sfo1)
    if result is not None:
        return result

    # 尝试复杂模式
    return _analyze_complex_pattern(cluster, sfo1)


def analyze_all_multiplets(
    detected_peaks: List[Tuple],
    sfo1: float,
    peak_types: List[str] | None = None,
    max_coupling_hz: float = 20.0,
) -> List[MultipletResult]:
    """对所有峰执行聚类 + 模式匹配

    Args:
        detected_peaks: 检测到的峰列表 [(ppm, height, width), ...]
        sfo1: 谱仪基础频率 (MHz)
        peak_types: 峰类型标注列表，与 detected_peaks 一一对应
        max_coupling_hz: 最大偶合常数阈值 (Hz)

    Returns:
        多重峰分析结果列表
    """
    if not detected_peaks:
        return []

    # 分离目标峰和非目标峰（非目标峰不参与聚合）
    target_peaks = []
    target_indices = []
    non_target_peaks = []
    non_target_indices = []
    non_target_types = []

    for i, peak in enumerate(detected_peaks):
        ptype = peak_types[i] if peak_types and i < len(peak_types) else "目标峰"
        if ptype == "目标峰":
            target_peaks.append(peak)
            target_indices.append(i)
        else:
            non_target_peaks.append(peak)
            non_target_indices.append(i)
            non_target_types.append(ptype)

    # 对目标峰进行聚类
    clusters = cluster_peaks_by_coupling(target_peaks, sfo1, max_coupling_hz)

    # 对每个簇进行模式匹配
    multiplet_results = []
    for cluster in clusters:
        result = analyze_multiplet_pattern(cluster, sfo1)
        multiplet_results.append(result)

    # 非目标峰（溶剂、杂质、TMS）每个单独作为 singlet，保留原始峰类型标签
    for idx, peak in enumerate(non_target_peaks):
        ppm, height, width = peak
        ptype = non_target_types[idx] if idx < len(non_target_types) else "目标峰"
        multiplet_results.append(MultipletResult(
            pattern="s",
            center_ppm=ppm,
            j_values=[],
            sub_peaks=[peak],
            intensity_ratio=[1.0],
            region_start=ppm + width,
            region_end=ppm - width,
            peak_type=ptype,
        ))

    # 按中心 ppm 从低到高排序
    multiplet_results.sort(key=lambda r: r.center_ppm, reverse=False)

    return multiplet_results
