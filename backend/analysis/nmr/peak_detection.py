"""
NMR 峰检测模块

提供基线校准、平滑处理和自动峰检测功能。
"""

import numpy as np
from scipy.signal import find_peaks, peak_widths


def baseline_correction(data, degree=3):
    """
    使用多项式拟合进行基线校准，通过mask只拟合低强度区域避免强峰干扰

    Args:
        data: 原始NMR数据
        degree: 多项式拟合的阶数

    Returns:
        基线校准后的数据
    """
    # 创建索引数组
    x = np.arange(len(data))

    # 使用多项式拟合估计基线
    baseline = np.polyval(np.polyfit(x, data, degree), x)

    # 从原始数据中减去基线
    corrected_data = data - baseline

    # 确保数据为正值
    corrected_data = np.maximum(corrected_data, 0)

    return corrected_data


def calculate_baseline(data, degree=3, noise_percentile=60):
    """
    计算NMR谱图的基线（只返回基线，不扣除）

    Args:
        data: 原始NMR数据
        degree: 多项式拟合的阶数
        noise_percentile: 噪声百分位数，用于确定基线阈值

    Returns:
        baseline: 计算得到的基线数组
    """
    x = np.arange(len(data))

    # 1. 确定基线掩码 (Baseline Mask)
    # 我们假设谱图中大部分区域是基线，只有少部分是峰
    # 通过百分位数确定一个初步的噪声阈值
    baseline_threshold = np.percentile(data, noise_percentile)

    # 找出所有低于该阈值的点（即认为是基线的点）
    mask = data < baseline_threshold

    x_baseline = x[mask]
    y_baseline = data[mask]

    # 2. 只用这些基线点进行多项式拟合
    # 这样大峰（高于阈值的点）就不会干扰拟合曲线了
    coeffs = np.polyfit(x_baseline, y_baseline, degree)
    baseline = np.polyval(coeffs, x)

    return baseline


def baseline_correction_robust(data, degree=3, noise_percentile=60):
    """
    改进的基线校准：只对非信号区域进行多项式拟合

    Args:
        data: 原始NMR数据
        degree: 多项式拟合的阶数
        noise_percentile: 噪声百分位数

    Returns:
        corrected_data: 基线校准后的数据
        baseline: 基线数组（仅在 return_baseline=True 时返回）
    """
    # 使用公共方法计算基线
    baseline = calculate_baseline(data, degree=degree, noise_percentile=noise_percentile)

    # 3. 扣除基线
    corrected_data = data - baseline

    return corrected_data


def smooth_data(data, window_size=5):
    """
    平滑处理，减少噪声干扰

    Args:
        data: 原始NMR数据
        window_size: 平滑窗口大小

    Returns:
        平滑处理后的数据
    """
    # 使用移动平均法进行平滑
    smoothed_data = np.convolve(data, np.ones(window_size) / window_size, mode='same')

    return smoothed_data


def detect_peaks(data, ppm_scale, threshold=0.05, min_distance=0.3, min_prominence=0.01, baseline_degree=3, smooth_window=5):
    """
    自动检测NMR谱图中的峰

    Args:
        data: 处理后的NMR数据
        ppm_scale: ppm刻度
        threshold: 阈值比例，同时峰检测（相对于最高峰）
        min_distance: 最小峰间距(ppm)
        min_prominence: 最小峰相对于邻近谷底的高度差
        baseline_degree: 基线校准多项式阶数
        smooth_window: 平滑窗口大小

    Returns:
        检测到的峰列表，每个元素为 (ppm, height, width)
    """
    # 1. 基线校准（使用mask过滤强峰，只拟合基线区域）
    corrected_data = baseline_correction_robust(data, degree=baseline_degree)


    # 2. 平滑处理
    # smoothed_data = smooth_data(corrected_data, smooth_window)
    # TODO 这里更改在前面做平滑处理
    smoothed_data = corrected_data

    # 计算数据的标准差，用于确定阈值
    # 在 detect_peaks 函数内部修改
    max_val = np.max(smoothed_data)

    # TODO 这里和prominence异曲同工，暂时删除
    # 建议将高度阈值设为最大值的 0.5% - 5%，相对基线的高度
    peak_threshold = max_val * threshold

    # 显著性（Prominence）是关键，设小一点
    # 允许检测出比最大峰矮很多的小突起
    custom_prominence = max_val * min_prominence
    peaks, properties = find_peaks(
        smoothed_data,
        # 最小间距样本点数
        distance=int(min_distance / np.abs(ppm_scale[1] - ppm_scale[0])),
        prominence=custom_prominence  # 使用这个更敏感的显著性
    )

    if len(peaks) == 0:
        return []

    # 计算峰宽
    widths, _, _, _ = peak_widths(smoothed_data, peaks)

    # 转换峰宽为ppm单位
    ppm_step = np.abs(ppm_scale[1] - ppm_scale[0])
    widths_ppm = widths * ppm_step

    # 构建检测到的峰列表
    detected_peaks = []
    for i, peak_idx in enumerate(peaks):
        ppm = ppm_scale[peak_idx]
        height = smoothed_data[peak_idx]
        width = widths_ppm[i]
        detected_peaks.append((ppm, height, width))

    # 按峰高排序，保留较强的峰
    detected_peaks.sort(key=lambda x: x[1], reverse=True)

    # 过滤掉距离太近的峰
    filtered_peaks = []
    for peak in detected_peaks:
        ppm, _, _ = peak
        # 检查是否与已保留的峰距离足够远
        too_close = False
        for existing_peak in filtered_peaks:
            existing_ppm, _, _ = existing_peak
            if abs(ppm - existing_ppm) < min_distance:
                too_close = True
                break
        if not too_close:
            filtered_peaks.append(peak)

    # 按ppm值排序（从低到高，TMS/低场峰在先）
    filtered_peaks.sort(key=lambda x: x[0], reverse=False)

    return filtered_peaks


def create_integration_regions_from_peaks(detected_peaks, width_multiplier=1, detection_range=None, peak_types=None,
                                          multiplet_results=None):
    """
    根据检测到的峰自动创建积分区域

    Args:
        detected_peaks: 检测到的峰列表，每个元素为 (ppm, height, width)
        width_multiplier: 峰宽倍数，用于确定积分区域范围
        detection_range: 检测区域范围 (min_ppm, max_ppm)，用于限制积分区域不超过检测范围
        peak_types: 标注峰类型的列表，与 detected_peaks 一一对应
        multiplet_results: 多重峰分析结果列表，若提供则按多重峰分组创建合并积分区域

    Returns:
        积分区域列表，每个元素为 (name, start, end, peak_position)
    """
    if multiplet_results:
        return _create_regions_from_multiplets(multiplet_results, detection_range, width_multiplier)

    # 归一化输入范围：将 (10.0, 0.0) 或 (0.0, 10.0) 统一为 (0.0, 10.0)
    limit_low, limit_high = (min(detection_range), max(detection_range)) if detection_range else (None, None)

    # 预统计每种非目标峰类型的数量，用于判断是否需要添加序号
    type_totals = {}
    if peak_types:
        for pt in peak_types:
            if pt != "目标峰":
                type_totals[pt] = type_totals.get(pt, 0) + 1

    integration_regions = []
    type_counters = {}
    for i, (ppm, _, width) in enumerate(detected_peaks):
        # 为每个峰创建积分区域，并确保从小到大顺序
        r_low = ppm - width * width_multiplier
        r_high = ppm + width * width_multiplier
        r_low, r_high = min(r_low, r_high), max(r_low, r_high)

        # 限制积分区域在检测范围内
        if limit_low is not None:
            r_low = max(r_low, limit_low)
            r_high = min(r_high, limit_high)

        region_name = f"峰 {i+1} 积分区域"
        if peak_types and i < len(peak_types):
            ptype = peak_types[i]
            if ptype != "目标峰":
                type_counters[ptype] = type_counters.get(ptype, 0) + 1
                if type_totals[ptype] > 1:
                    region_name = f"【{ptype}】{type_counters[ptype]}"
                else:
                    region_name = f"【{ptype}】"
            else:
                region_name = f"【目标峰】 {i+1}"

        # 保留峰的位置信息
        integration_regions.append((region_name, r_low, r_high, ppm))

    return integration_regions


def _create_regions_from_multiplets(multiplet_results, detection_range=None, width_multiplier=1.0):
    """根据多重峰分析结果创建合并的积分区域

    Args:
        multiplet_results: MultipletResult 列表
        detection_range: 检测区域范围
        width_multiplier: 积分区间扩展倍数

    Returns:
        积分区域列表，每个元素为 (name, start, end, center_ppm)
    """

    # 归一化输入范围
    limit_low, limit_high = (min(detection_range), max(detection_range)) if detection_range else (None, None)

    # 预统计每种非目标峰类型的数量，用于判断是否需要添加序号
    type_totals = {}
    for mp in multiplet_results:
        ptype = mp.peak_type if hasattr(mp, 'peak_type') else "目标峰"
        if ptype != "目标峰":
            type_totals[ptype] = type_totals.get(ptype, 0) + 1

    integration_regions = []
    type_counters = {}
    for i, mp in enumerate(multiplet_results):
        # 直接计算数学意义上的边界 (小值, 大值)
        r_low = min(p - w * width_multiplier for p, _, w in mp.sub_peaks)
        r_high = max(p + w * width_multiplier for p, _, w in mp.sub_peaks)

        # 裁剪逻辑
        if limit_low is not None:
            r_low = max(r_low, limit_low)
            r_high = min(r_high, limit_high)

        # 生成区域名称：根据 peak_type 区分目标峰和非目标峰（溶剂/杂质/TMS）
        ptype = mp.peak_type if hasattr(mp, 'peak_type') else "目标峰"
        if ptype != "目标峰":
            type_counters[ptype] = type_counters.get(ptype, 0) + 1
            if type_totals[ptype] > 1:
                region_name = f"【{ptype}】{type_counters[ptype]}"
            else:
                region_name = f"【{ptype}】"
        elif mp.pattern == "s" and len(mp.sub_peaks) == 1:
            region_name = f"【目标峰】 {i+1}"
        else:
            display = mp.to_display_str()
            region_name = f"【目标峰】 {i+1} ({display})"

        integration_regions.append((region_name, r_low, r_high, mp.center_ppm))

    return integration_regions