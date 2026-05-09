import os
from typing import Optional, List

import numpy as np
import pandas as pd
from scipy import signal
from scipy.ndimage import minimum_filter1d
from scipy.signal import savgol_filter

from analysis.gpc.tools.gpc_curve_roi_processor import GPCCurveROIProcessor
from analysis.gpc.tools.gpc_data_name_parser import GPCDataNameParser
from analysis.gpc.utils.gpc_plotter import GPCDataPlotter
from app.core.logging import get_logger

logger = get_logger("spec_agent.analysis.gpc.analyzer")


class GPCAnalyzer:
    def __init__(
            self,
            time_data,
            signal_data,
            calibration_func,
            peak_expansion_level: Optional[float] = None,
    ):
        """
        初始化 GPC 分析器
        :param time_data: 时间/洗脱体积数组
        :param signal_data: 检测器响应强度数组
        :param calibration_func: 校正曲线函数
        """
        self.time = np.array(time_data)
        self.signal = np.array(signal_data)
        self.cal_poly = calibration_func
        self.peak_expansion_level = peak_expansion_level
        # 生成峰检测和边界检测配置
        self.config = self._generate_config()

        # 内部状态
        self.smoothed_signal = None
        self.peaks_info = {}  # 存储每个峰的计算结果
        self.molecular_info = []  # 存储分子量计算结果
        self.segments = []  # 存储峰检测结果

    def preprocess(self, window_size=None, poly_order=2):
        """对信号进行平滑处理"""
        if window_size is None:
            window_size = max(5, int(len(self.signal) * 0.05))
        self.smoothed_signal = savgol_filter(self.signal, window_size, poly_order)
        return self.smoothed_signal

    def detect_multi_peaks_bounds(self, height_ratio=0.05, distance=None, prominence=None):
        """
        自动检测多峰及其边界
        """
        # 1. 寻找峰顶
        height = np.max(self.signal) * height_ratio
        peaks, _, _, _ = self.detect_peaks(height=height, distance=distance, prominence=prominence)

        # 2. 计算斜率辅助确定边界 (3-Sigma原则)
        slopes = np.gradient(self.smoothed_signal, self.time)
        baseline_std = np.std(slopes[:len(slopes) // 10])
        threshold = baseline_std * 3

        self.segments = []
        for p in peaks:
            # 向左搜索起点
            start_idx = 0
            for i in range(p, 0, -1):
                # 停止条件：斜率走平且信号低，或遇到另一个峰的下坡
                if (abs(slopes[i]) < threshold and self.smoothed_signal[i] < self.smoothed_signal[p] * 0.1) \
                        or (i < p - 5 and self.smoothed_signal[i] > self.smoothed_signal[i + 1]):
                    start_idx = i
                    break

            # 向右搜索终点
            end_idx = len(self.signal) - 1
            for i in range(p, len(self.signal) - 1):
                if (abs(slopes[i]) < threshold and self.smoothed_signal[i] < self.smoothed_signal[p] * 0.1) \
                        or (i > p + 5 and self.smoothed_signal[i] > self.smoothed_signal[i - 1]):
                    end_idx = i
                    break

            self.segments.append((start_idx, end_idx, p))
        return self.segments

    def detect_peaks_bounds(self, height_ratio=0.05, distance=None, prominence=None):
        self.segments = []
        # 如果检测到峰值，总是使用最高峰（索引0，因为detect_peaks已按高度排序）
        # 1. 寻找峰顶
        height = np.max(self.signal) * height_ratio
        peaks, _, _, _ = self.detect_peaks(height=height, distance=distance, prominence=prominence)
        for idx, _ in enumerate(peaks):
            peak_details = self.get_peak_region(
                peaks=peaks,
                peak_index=idx,
            )
            self.segments.append(peak_details)
        self.peaks_info["peaks_details"] = self.segments
        return self.peaks_info

    def get_peak_region(self, peaks, peak_index=0):
        """
        获取指定峰值的区域边界，支持两种模式：自动检测和手动指定

        参数:
            peaks: 所有峰值的索引数组
            peak_index: 要获取的峰值索引（从0开始）
        返回:
            left_bound: 左边界索引
            right_bound: 右边界索引
        """
        if peak_index < 0 or peak_index >= len(peaks):
            logger.warning("峰值索引 %s 超出范围 [0, %s]", peak_index, len(peaks) - 1)
            raise ValueError(f"峰值索引 {peak_index} 超出范围 [0, {len(peaks)-1}]")

        # 自动模式处理（原有逻辑）
        peak_idx = peaks[peak_index]
        total_points = len(self.smoothed_signal)
        peak_time = self.time[peak_idx]

        # 获取基线信息
        # 使用滚动窗口计算基线
        window_size = max(5, int(len(self.smoothed_signal) * 0.02))
        baseline = minimum_filter1d(self.smoothed_signal, size=window_size, mode='reflect')

        # 第一步：使用_find_peak_boundaries获取基础边界，传递配置和阈值参数
        # _find_peak_boundaries方法会处理config的默认值
        initial_left, initial_right = self._find_peak_boundaries(
            self.smoothed_signal, peak_idx, baseline, self.config
        )

        # 计算峰宽和信号特性
        peak_width = initial_right - initial_left
        peak_height = self.signal[peak_idx]

        # 判断峰类型（窄分布/宽分布）
        # 使用相对峰宽来判断：峰宽相对于总数据点数的比例
        relative_width = peak_width / total_points
        is_narrow_peak = relative_width < 0.05  # 相对峰宽小于5%认为是窄峰

        # 自适应扩展策略
        if is_narrow_peak:
            # 窄分布峰：适度扩展以捕获完整峰形
            # 放宽窄峰的扩展策略，不再限制过度扩展
            left_bound = initial_left
            right_bound = initial_right

            # 基于信号趋势的扩展
            # 向左扩展：如果左侧信号有上升趋势，适当扩展
            left_extend = 0
            for i in range(initial_left, max(0, initial_left - self.config['narrow_peak_search_range']), -1):  # 使用配置的搜索范围
                if i > 0 and self.smoothed_signal[i] > self.smoothed_signal[i-1] * self.config['narrow_peak_trend_factor']:  # 使用配置的趋势阈值
                    left_extend = initial_left - i
                    break

            # 向右扩展：如果右侧信号有下降趋势，适当扩展
            right_extend = 0
            for i in range(initial_right, min(total_points - 1, initial_right + self.config['narrow_peak_search_range'])):  # 使用配置的搜索范围
                if i < total_points - 1 and self.smoothed_signal[i] > self.smoothed_signal[i+1] * self.config['narrow_peak_trend_factor']:  # 使用配置的趋势阈值
                    right_extend = i - initial_right
                    break

            # 对于窄峰，额外增加固定扩展量
            left_extend = max(left_extend, self.config['narrow_peak_min_extend'])  # 使用配置的最小扩展量
            right_extend = max(right_extend, self.config['narrow_peak_min_extend'])  # 使用配置的最小扩展量

            left_bound = max(0, left_bound - left_extend)
            right_bound = min(total_points - 1, right_bound + right_extend)
        else:
            # 宽分布峰：适度扩展以确保捕获完整峰形
            # 基于峰宽的动态扩展量，使用配置的扩展因子范围
            width_factor = min(self.config['width_factor_max'], max(self.config['width_factor_min'], relative_width * 2))  # 使用配置的扩展因子范围

            left_expand = int(peak_width * width_factor)
            right_expand = int(peak_width * width_factor)

            left_bound = max(0, initial_left - left_expand)
            right_bound = min(total_points - 1, initial_right + right_expand)

        # 确保边界与峰值之间有最小距离，使用配置参数
        min_distance = max(self.config['min_distance_min'], int(total_points * self.config['min_distance_factor']))  # 使用配置的最小距离参数
        left_bound = max(0, min(left_bound, peak_idx - min_distance))
        right_bound = min(total_points - 1, max(right_bound, peak_idx + min_distance))

        # 对于多峰情况，确保相邻峰之间不重叠
        if len(peaks) > 1:
            # 左边界调整：不能超过前一个峰的右边界
            if peak_index > 0:
                prev_peak_idx = peaks[peak_index - 1]
                prev_left, prev_right = self._find_peak_boundaries(
                    self.smoothed_signal, prev_peak_idx, baseline, self.config
                )
                # 设置两个峰之间的中点作为边界
                mid_point = (prev_peak_idx + peak_idx) // 2
                left_bound = max(left_bound, prev_right + 1)
                left_bound = max(left_bound, mid_point - 5)  # 给点余量

            # 右边界调整：不能超过后一个峰的左边界
            if peak_index < len(peaks) - 1:
                next_peak_idx = peaks[peak_index + 1]
                next_left, next_right = self._find_peak_boundaries(
                    self.smoothed_signal, next_peak_idx, baseline, self.config
                )
                # 设置两个峰之间的中点作为边界
                mid_point = (peak_idx + next_peak_idx) // 2
                right_bound = min(right_bound, next_left - 1)
                right_bound = min(right_bound, mid_point + 5)  # 给点余量

        # 确保边界在有效范围内
        left_bound = max(0, min(left_bound, len(self.time) - 1))
        right_bound = max(0, min(right_bound, len(self.time) - 1))

        peak_details = {
            "left_bound": left_bound,
            "right_bound": right_bound,
            "peak_idx": peak_idx,
            "peak_time": round(peak_time, 2),
            "peak_height": round(peak_height, 2),
            "left_time": round(self.time[left_bound], 2),
            "right_time": round(self.time[right_bound], 2),
            "peak_width": round(peak_width, 2)
        }
        return peak_details


    @staticmethod
    def _find_peak_boundaries(signal, peak_idx, baseline, config):
        """
        使用改进的导数和基线方法寻找峰的完整边界

        参数:
            signal: 输入信号数组
            peak_idx: 峰值索引
            baseline: 基线数组（可选）
            config: 配置参数字典，包含边界检测和峰值扩展的相关配置
            peak_expansion_level: 峰值扩展水平参数（0-1之间的浮点数），用于量化控制峰值检测的严格程度
                                 0表示最严格的检测（最小检测范围，高阈值），1表示最宽松的检测（最大检测范围，低阈值）
                                 此参数会自动调整边界检测的相关配置

        返回:
            left_bound: 峰左边界索引
            right_bound: 峰右边界索引

        算法说明:
            1. 使用阈值方法寻找峰的大致边界
            2. 使用导数方法寻找峰的精确拐点
            3. 综合两种方法结果并进行智能扩展
            4. 确保边界在有效范围内
        """
        # 获取信号长度
        n = len(signal)

        # 计算一阶导数（使用更大步长使导数更平滑）
        dy = np.gradient(signal, 2)
        # 计算二阶导数（使用更大步长使导数更平滑）
        d2y = np.gradient(dy, 2)


        # 计算阈值，用于判断峰的起始和结束
        if baseline is not None:
            # 使用基线的统计特性计算阈值
            baseline_mean = np.mean(baseline)
            baseline_std = np.std(baseline)
            threshold = max(baseline_mean + config['baseline_std_factor'] * baseline_std,
                           np.min(baseline) * config['baseline_min_factor'])  # 使用配置的阈值系数
        else:
            # 基于信号最大值的固定比例计算阈值
            threshold = np.max(signal) * config['signal_max_factor']  # 使用配置的信号最大值比例

        # 确保峰值索引有效
        if peak_idx < 0 or peak_idx >= n:
            logger.warning("峰值索引 %s 超出信号范围 [0, %s]", peak_idx, n - 1)
            raise ValueError(f"峰值索引 {peak_idx} 超出信号范围 [0, {n-1}]")

        # 步骤1: 使用阈值方法寻找左右边界
        # 向左寻找第一个低于阈值的点
        left_bound_threshold = 0
        for i in range(peak_idx, 0, -1):
            if 0 <= i < n and signal[i] < threshold:
                left_bound_threshold = i
                break

        # 向右寻找第一个低于阈值的点
        right_bound_threshold = n - 1
        for i in range(peak_idx, n - 1):
            if 0 <= i < n and signal[i] < threshold:
                right_bound_threshold = i
                break

        # 步骤2: 使用导数方法寻找峰的拐点
        # 向左寻找拐点：结合一阶导和二阶导
        left_bound_derivative = peak_idx
        search_range_left = max(0, left_bound_threshold - 50)
        dy_len = len(dy)
        d2y_len = len(d2y)

        # 向左寻找：一阶导由正变负（峰上升结束）或二阶导符号变化（拐点）
        for i in range(peak_idx, search_range_left, -1):
            if 0 < i < dy_len and i-1 < dy_len and i < d2y_len:
                # 条件1: 一阶导由正变负（上升转为下降）
                condition1 = dy[i] <= 0 < dy[i - 1]
                # 条件2: 二阶导符号变化（拐点）且一阶导绝对值较大
                condition2 = i > 0 and (d2y[i] * d2y[i-1] <= 0) and abs(dy[i]) > 0.01 * max(abs(dy))

                if condition1 or condition2:
                    left_bound_derivative = i
                    break

        # 向右寻找拐点：结合一阶导和二阶导
        right_bound_derivative = peak_idx
        search_range_right = min(n - 1, right_bound_threshold + 50)

        # 向右寻找：一阶导由负变正（峰下降结束）或二阶导符号变化（拐点）
        for i in range(peak_idx, search_range_right):
            if i < dy_len - 1 and i+1 < dy_len and i < d2y_len - 1:
                # 条件1: 一阶导由负变正（下降转为上升）
                condition1 = dy[i] >= 0 and dy[i+1] < 0
                # 条件2: 二阶导符号变化（拐点）且一阶导绝对值较大
                condition2 = i < d2y_len - 1 and (d2y[i] * d2y[i+1] <= 0) and abs(dy[i]) > 0.01 * max(abs(dy))

                if condition1 or condition2:
                    right_bound_derivative = i
                    break

        # 步骤3: 综合两种方法的结果
        left_bound = min(left_bound_threshold, left_bound_derivative)
        right_bound = max(right_bound_threshold, right_bound_derivative)

        # 步骤4: 智能扩展边界以确保捕获完整峰
        peak_width = right_bound - left_bound

        # 计算最大扩展量（基于信号长度的动态值）
        max_extend = max(config['max_extend_min'], min(config['max_extend_max'], int(n * config['signal_length_factor'])))  # 使用配置的扩展量参数

        if peak_width > 0:
            # 根据峰宽比例扩展边界，使用配置的扩展比例
            left_extend = max(config['max_extend_min'], min(max_extend, int(peak_width * config['peak_width_extend'])))  # 扩展配置比例的峰宽
            left_bound = max(0, left_bound - left_extend)

            right_extend = max(config['max_extend_min'], min(max_extend, int(peak_width * config['peak_width_extend'])))  # 扩展配置比例的峰宽
            right_bound = min(n - 1, right_bound + right_extend)
        else:
            # 峰宽为0时的默认扩展
            left_bound = max(0, left_bound - 5)
            right_bound = min(n - 1, right_bound + 5)

        # 步骤5: 确保边界与峰值之间有最小距离
        min_distance_from_peak = max(3, int(n * 0.01))
        left_bound = max(0, min(left_bound, peak_idx - min_distance_from_peak))
        right_bound = min(n - 1, max(right_bound, peak_idx + min_distance_from_peak))

        # 最终安全检查
        return max(0, left_bound), min(n - 1, right_bound)

    def _generate_config(self):
        """
        生成或更新配置参数字典

        参数:
            peak_expansion_level: 峰值扩展水平参数（0-1之间的浮点数）
            config: 初始配置参数字典

        返回:
            dict: 处理后的配置字典
        """
        if self.peak_expansion_level is None:
            return {
                'baseline_std_factor': 1.5,  # 基线标准差系数
                'baseline_min_factor': 1.5,  # 基线最小值系数
                'signal_max_factor': 0.03,  # 信号最大值比例
                'max_extend_min': 8,  # 最大扩展量最小值
                'max_extend_max': 30,  # 最大扩展量最大值
                'signal_length_factor': 0.075,  # 信号长度比例
                'peak_width_extend': 0.5,  # 峰宽扩展比例
                'min_distance_factor': 0.005,  # 最小距离因子
                'min_distance_min': 3,  # 最小距离最小值
                'narrow_peak_search_range': 30,  # 窄峰搜索范围
                'narrow_peak_trend_factor': 1.3,  # 窄峰信号趋势阈值
                'narrow_peak_min_extend': 10,  # 窄峰最小扩展量
                'width_factor_min': 0.15,  # 宽峰扩展因子最小值
                'width_factor_max': 0.5,  # 宽峰扩展因子最大值
            }
        # 确保peak_expansion_level在0-1范围内
        peak_expansion_level = max(0.0, min(1.0, self.peak_expansion_level))

        # 基于peak_expansion_level生成动态配置
        config_ranges = {
            'baseline_std_factor': (2.5, 1.0),      # 基线标准差系数：严格(2.5) → 宽松(1.0)
            'baseline_min_factor': (2.0, 1.0),      # 基线最小值系数：严格(2.0) → 宽松(1.0)
            'signal_max_factor': (0.05, 0.01),       # 信号最大值比例：严格(5%) → 宽松(1%)
            'max_extend_min': (5, 15),               # 最大扩展量最小值：严格(5) → 宽松(15)
            'max_extend_max': (20, 40),              # 最大扩展量最大值：严格(20) → 宽松(40)
            'signal_length_factor': (0.05, 0.1),     # 信号长度比例：严格(5%) → 宽松(10%)
            'peak_width_extend': (0.2, 0.8),         # 峰宽扩展比例：严格(20%) → 宽松(80%)
            'min_distance_factor': (0.01, 0.002),    # 最小距离因子：严格(1%) → 宽松(0.2%)
            'min_distance_min': (5, 2),              # 最小距离最小值：严格(5) → 宽松(2)
            'narrow_peak_search_range': (20, 50),    # 窄峰搜索范围：严格(20) → 宽松(50)
            'narrow_peak_trend_factor': (1.5, 1.1),  # 窄峰信号趋势阈值：严格(1.5) → 宽松(1.1)
            'narrow_peak_min_extend': (5, 15),       # 窄峰最小扩展量：严格(5) → 宽松(15)
            'width_factor_min': (0.1, 0.2),          # 宽峰扩展因子最小值：严格(10%) → 宽松(20%)
            'width_factor_max': (0.3, 0.7),          # 宽峰扩展因子最大值：严格(30%) → 宽松(70%)
        }

        # 基于peak_expansion_level插值生成配置
        dynamic_config = {}
        for key, (strict_val, loose_val) in config_ranges.items():
            dynamic_config[key] = strict_val + (loose_val - strict_val) * peak_expansion_level

            # 对整数类型的配置项进行取整
            if key in ['max_extend_min', 'max_extend_max', 'narrow_peak_search_range',
                      'narrow_peak_min_extend', 'min_distance_min']:
                dynamic_config[key] = int(dynamic_config[key])
        return dynamic_config


    def detect_peaks(self, height=None, prominence=None, distance=None):
        """
        检测色谱峰

        参数:
            height: 峰高阈值
            prominence: 峰的突出度
            distance: 峰之间的最小距离

        返回:
            peaks: 检测到的峰值索引
            peak_times: 峰值对应的时间
            peak_heights: 峰值对应的信号强度
            properties: 峰值属性信息
        """
        if self.smoothed_signal is None:
            self.preprocess()

        # 自适应参数调整 - 降低阈值以便捕获更多潜在峰
        if prominence is None or prominence <= 0:
            # 基于信号标准差动态调整prominence，但使用更小的值
            signal_std = np.std(self.smoothed_signal)
            prominence = max(0.05, float(signal_std * 0.3))  # 降低从0.5到0.3，捕获更多小峰

        if distance is None or distance <= 0:
            # 基于数据点数动态调整distance，使用更小的值
            distance = max(5.0, len(self.smoothed_signal) * 0.005)  # 降低从0.01到0.005，允许更密集的峰

        if height is None:
            height = np.max(self.smoothed_signal) * 0.05

        # 检测峰值 - 降低检测阈值以捕获更多峰
        peaks, properties = signal.find_peaks(
            self.smoothed_signal,
            height=height,  # 不设置默认height，允许检测更多低峰
            prominence=prominence,
            distance=distance,
            width=0,  # 允许检测任何宽度的峰
            rel_height=0.5,  # 用于计算半峰宽
            wlen=None  # 不限制窗口长度，允许检测宽峰
        )

        # 提取峰信息
        peak_times = self.time[peaks]

        # 安全地获取峰值高度
        if 'peak_heights' in properties:
            peak_heights = properties['peak_heights']
        else:
            peak_heights = self.signal[peaks]

        # 按照峰高从高到低排序
        if len(peaks) > 1:
            # 获取排序索引（从高到低）
            sorted_indices = np.argsort(peak_heights)[::-1]

            # 重新排列peaks、peak_times和peak_heights
            peaks = peaks[sorted_indices]
            peak_times = peak_times[sorted_indices]
            peak_heights = peak_heights[sorted_indices]

            # 重新排列properties中的相关数据
            for key in properties:
                if isinstance(properties[key], np.ndarray) and len(properties[key]) == len(sorted_indices):
                    properties[key] = properties[key][sorted_indices]

        # 存储峰值信息
        self.peaks_info = {
            'peaks': peaks,
            'peak_times': peak_times,
            'peak_heights': peak_heights,
            'properties': properties
        }
        return peaks, peak_times, peak_heights, properties

    def calculate_all_molecular_weights(
            self,
            detect_mode: str = 'auto',
            manual_interval: Optional[List[float]] = None
    ):
        """计算每个已识别峰的 Mn, Mw, PDI"""
        self.molecular_info = []
        for i, _ in enumerate(self.segments):
            molecular_data = self.calculate_molecular_weights(i, detect_mode, manual_interval)
            self.molecular_info.append(molecular_data)
        return self.molecular_info

    def calculate_molecular_weights(
            self,
            peak_index: int,
            detect_mode: str = 'auto',
            manual_interval: Optional[List[float]] = None,
    ):
        peak_details = self.segments[peak_index]
        p_idx = peak_details["peak_idx"]
        if detect_mode == "manual":
            manual_left_time, manual_right_time = manual_interval
            # 将时间转换为对应的索引
            start = np.searchsorted(self.time, manual_left_time)
            end = np.searchsorted(self.time, manual_right_time)
        else:

            start = peak_details["left_bound"]
            end = peak_details["right_bound"]

        t_seg = self.time[start:end + 1]
        s_seg = self.signal[start:end + 1]

        # 线性基线扣除
        baseline = np.linspace(s_seg[0], s_seg[-1], len(s_seg))
        h_i = np.maximum(s_seg - baseline, 0)

        # 分子量计算 M = 10^(f(t))
        log_M = self.cal_poly(t_seg)
        M_i = 10 ** log_M

        # 矩法积分
        sum_h = np.sum(h_i)

        Mn = sum_h / np.sum(h_i / M_i)
        Mw = np.sum(h_i * M_i) / sum_h
        Mz = np.sum(h_i * M_i ** 2) / np.sum(h_i * M_i)
        PDI = Mw / Mn

        return {
            'Peak_No': peak_index,
            'RT': self.time[p_idx],
            'Mn': Mn,
            'Mw': Mw,
            'Mz': Mz,
            'PDI': PDI,
            'M_i': M_i,
            'log_M': log_M,
            'h_i': h_i,
            'time_range': (self.time[start], self.time[end])
        }


# --- 使用示例 ---
if __name__ == "__main__":
    # 0. 模拟或读取数据
    curve_path = r"E:\肖旭\光刻胶\工程中心-GPC-数据\工程中心-GPC-测试数据\test\GPC_03_20241210-2_Cal001_Copoly_THF_mix\GPC_03_20241210-2_Cal001_Copoly_THF_mix.arw"
    three_color_curve_path = r"E:\肖旭\光刻胶\工程中心-GPC-数据\工程中心-GPC-标曲三色曲线"
    actual_curve = pd.read_csv(curve_path, sep=r'\s+', header=None, names=["retention_time", "intensity"])
    actual_curve_name = os.path.basename(curve_path)
    simple_name = os.path.splitext(actual_curve_name)[0]
    # roi识别->峰值检测->最终分子量计算
    # roi识别
    three_color_curve_name = GPCDataNameParser().match_three_color_curve(actual_curve_name, three_color_curve_path)

    roi_processor = GPCCurveROIProcessor()
    roi_result = roi_processor.calculate_roi(
        three_color_curve_name,
        three_color_curve_path,
        return_details=True,
        visualize=False,
        output_dir=None
    )

    # 读取实际洗脱曲线数据并提取ROI范围内的数据
    roi_start, roi_end = roi_result['roi_start'], roi_result['roi_end']
    roi_data = actual_curve[(actual_curve['retention_time'] >= roi_start) & (actual_curve['retention_time'] <= roi_end)].copy()

    # 获取校准曲线函数
    calibration_func = roi_processor.calibration.get_calibration_curve(roi_result['full_calib_name'])
    time_data, signal_data = roi_data['retention_time'].values, roi_data['intensity'].values

    # 2. 峰值检测及分子量计算
    gpc_analyzer = GPCAnalyzer(time_data, signal_data, calibration_func)

    peaks_info = gpc_analyzer.detect_peaks_bounds(height_ratio=0.1)
    molecular_info = gpc_analyzer.calculate_all_molecular_weights()
    output_dir = os.path.join(r"E:\github_project\Spec_Agent\outputs\gpc_results", simple_name)
    gpc_plotter = GPCDataPlotter(
        time_data=time_data,
        signal_data=signal_data,
        calibration_func=calibration_func,
        peaks_info=peaks_info,
        molecular_info=molecular_info,
        output_dir=output_dir,
        sample_name="1234455"
    )

    # 绘制分析结果图
    gpc_plotter.plot_roi_result(
        actual_curve,
        roi_result,
        actual_curve_name=actual_curve_name
    )
    gpc_plotter.plot_gpc_machine_curve()
    gpc_plotter.plot_peak_detect_process(peak_index=0)
    gpc_plotter.plot_gpc_result(peak_index=0)
    gpc_plotter.plot_with_cumulative(peak_index=0)
