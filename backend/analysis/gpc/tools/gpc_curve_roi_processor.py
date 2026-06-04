import logging
import os
from typing import Dict, Any, List, Tuple, Optional

from config import setup_logging, setup_matplotlib_font, GLOBAL_CONFIG

setup_matplotlib_font()
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import signal

from analysis.gpc.tools.gpc_calibration_curve import GPCCalibrationCurve

# 配置日志记录
setup_logging(logger_name="GPCCurveROIProcessor")
logger = logging.getLogger("GPCCurveROIProcessor")

class GPCCurveROIProcessor:
    """GPC曲线ROI处理器，用于寻找洗脱曲线的感兴趣区域"""
    
    def __init__(self):
        """初始化GPC曲线ROI处理器"""
        self.calibration = GPCCalibrationCurve()
        self.mw_threshold = 1000  # 分子量阈值，大于此值的区域保留

    @staticmethod
    def read_arw_file(file_path: str) -> pd.DataFrame:
        """
        读取ARW文件
        
        参数:
        file_path: ARW文件路径
        
        返回:
        pd.DataFrame: 包含保留时间和强度数据的DataFrame
        """
        try:
            logger.info(f"开始读取ARW文件: {file_path}")
            data = pd.read_csv(file_path, sep="\t", header=None, names=["retention_time", "intensity"])
            logger.info(f"成功读取ARW文件，共 {len(data)} 行数据")
            return data
        except Exception as e:
            logger.error(f"读取ARW文件失败: {str(e)}")
            raise
    
    def find_solvent_peak_region(self, curves: List[pd.DataFrame], output_path: str = None, curve_name: str = None, full_calib_name: str = None) -> Tuple[float, float]:
        """
        通过对比三条曲线，找到出峰重叠且靠后的溶剂峰区域
        
        参数:
        curves: 三条曲线的DataFrame列表 [green_curve, red_curve, white_curve]
        output_path: 输出可视化图片路径，如果为None则不保存
        curve_name: 仪器特性曲线名称
        full_calib_name: 完整的仪器特性曲线名称
        
        返回:
        Tuple[float, float]: 溶剂峰区域的起始和结束时间（分钟）
        """
        try:
            logger.info("开始寻找溶剂峰区域")
            
            # 1. 平滑曲线，减少噪声
            smoothed_curves = []
            for curve in curves:
                smoothed = curve.copy()
                smoothed["intensity"] = curve["intensity"].rolling(window=10, center=True, min_periods=1).mean()
                smoothed_curves.append(smoothed)
            
            # 2. 在保留时间25-35分钟范围内寻找溶剂峰
            solvent_search_start = 25.0
            solvent_search_end = 35.0
            
            # 获取整个时间序列范围
            min_time = min(curve["retention_time"].min() for curve in curves)
            max_time = max(curve["retention_time"].max() for curve in curves)
            
            # 3. 检测每条曲线在整个时间序列上的所有主要峰值
            all_peak_times = []
            all_peak_heights = []
            for i, curve in enumerate(smoothed_curves):
                # 检测整个时间序列上的峰值，优化参数，只检测明显的峰值
                peaks, properties = signal.find_peaks(
                    curve["intensity"], 
                    prominence=0.5,  # 提高prominence值，只检测明显的峰值
                    height=1.0,      # 提高高度阈值，只检测高峰值
                    width=0.5        # 提高宽度阈值，只检测宽峰
                )
                
                peak_times = curve["retention_time"].iloc[peaks].values
                peak_heights = curve["intensity"].iloc[peaks].values
                
                # 如果没有检测到峰值，使用曲线最大值作为峰值
                if len(peak_times) == 0:
                    max_idx = curve["intensity"].idxmax()
                    peak_times = np.array([curve.loc[max_idx, "retention_time"]])
                    peak_heights = np.array([curve.loc[max_idx, "intensity"]])
                
                # 在溶剂峰搜索范围内的峰值，用于后续溶剂峰确定
                solvent_range_peaks = peak_times[(peak_times >= solvent_search_start) & (peak_times <= solvent_search_end)]
                
                all_peak_times.append(peak_times)
                all_peak_heights.append(peak_heights)
                logger.info(f"曲线 {i+1} 在整个时间序列上检测到 {len(peak_times)} 个主要峰值，其中溶剂峰搜索范围内有 {len(solvent_range_peaks)} 个峰值: {solvent_range_peaks}")
            
            # 4. 寻找三条曲线中重叠且更高的峰值
            # 使用0.3分钟的时间窗口，降低重叠阈值，让系统更容易检测到重叠峰
            time_window = 0.3
            solvent_peak_time = 30.0  # 默认值
            found_solvent_peak = False
            
            # 只使用溶剂峰搜索范围内的峰值来确定溶剂峰
            solvent_range_all_peaks = []
            solvent_range_all_heights = []
            for curve_peaks, curve_heights in zip(all_peak_times, all_peak_heights):
                # 获取溶剂峰搜索范围内的峰值和对应的高度
                solvent_peaks = curve_peaks[(curve_peaks >= solvent_search_start) & (curve_peaks <= solvent_search_end)]
                solvent_range_all_peaks.append(solvent_peaks)
                
                # 获取对应的峰值高度
                peak_indices = np.where(np.isin(curve_peaks, solvent_peaks))[0]
                solvent_heights = curve_heights[peak_indices]
                solvent_range_all_heights.append(solvent_heights)
            
            # 收集所有溶剂峰搜索范围内的峰值，包括高度信息
            all_solvent_peaks_with_height = []
            for curve_idx, (curve_peaks, curve_heights) in enumerate(zip(solvent_range_all_peaks, solvent_range_all_heights)):
                for peak_time, peak_height in zip(curve_peaks, curve_heights):
                    all_solvent_peaks_with_height.append((peak_time, peak_height, curve_idx))
            
            # 按高度降序排序，优先考虑更高的峰值
            all_solvent_peaks_with_height.sort(key=lambda x: x[1], reverse=True)
            
            # 查找重叠的高峰值
            for t, height, curve_idx in all_solvent_peaks_with_height:
                # 检查是否有至少两条曲线在该时间附近有峰值
                overlap_count = 0
                for curve_peaks in solvent_range_all_peaks:
                    if any(abs(peak - t) <= time_window for peak in curve_peaks):
                        overlap_count += 1
                
                # 如果至少两条曲线有重叠峰值，且时间在合理范围内，则确定为溶剂峰
                if overlap_count >= 2 and solvent_search_start <= t <= solvent_search_end:
                    solvent_peak_time = t
                    found_solvent_peak = True
                    break
            
            # 如果没有找到合适的峰值，回退到原始逻辑：从后往前寻找
            if not found_solvent_peak:
                # 获取溶剂峰搜索范围内的所有峰值时间并排序
                flat_peak_times = [t for curve_peaks in solvent_range_all_peaks for t in curve_peaks]
                flat_peak_times.sort()
                
                # 从后往前寻找，确保找到靠后的重叠峰
                for t in reversed(flat_peak_times):
                    overlap_count = 0
                    for curve_peaks in solvent_range_all_peaks:
                        if any(abs(peak - t) <= time_window for peak in curve_peaks):
                            overlap_count += 1
                    
                    # 如果至少两条曲线有重叠峰值，且时间足够靠后（>27分钟），则确定为溶剂峰
                    if overlap_count >= 2 and t > 27.0:
                        solvent_peak_time = t
                        found_solvent_peak = True
                        break
            
            if found_solvent_peak:
                logger.info(f"基于三条曲线重叠找到溶剂峰时间: {solvent_peak_time} 分钟")
            else:
                logger.warning("未找到明确的重叠溶剂峰，使用默认值")
            
            # 5. 确定溶剂峰区域：增加前后的时间范围，让溶剂峰区域更大
            solvent_start = solvent_peak_time - 1.5  # 峰值前1.5分钟
            solvent_end = solvent_peak_time + 2.0    # 峰值后2.0分钟
            
            # 确保溶剂峰区域范围合理
            solvent_start = max(solvent_start, 24.0)  # 扩大下限
            solvent_end = min(solvent_end, 36.0)      # 扩大上限
            
            logger.info(f"最终溶剂峰区域: {solvent_start:.2f} - {solvent_end:.2f} 分钟")
            
            # 6. 可视化溶剂峰检测结果
            if output_path:
                self._plot_solvent_peak_detection(smoothed_curves, all_peak_times, all_peak_heights, solvent_peak_time, solvent_start, solvent_end, output_path, curve_name, min_time, max_time, full_calib_name)
            
            return (solvent_start, solvent_end)
        except Exception as e:
            logger.error(f"寻找溶剂峰区域失败: {str(e)}")
            return (29.0, 32.0)
    
    def find_mw_roi_region(self, curve: pd.DataFrame, calibration_func, output_path: str = None, curve_name: str = None, full_calib_name: str = None) -> Tuple[float, float]:
        """
        根据分子量阈值（1000）找到感兴趣的分子量区域
        
        参数:
        curve: 曲线的DataFrame
        calibration_func: 校准曲线函数，输入保留时间，输出log(M)
        output_path: 输出可视化图片路径，如果为None则不保存
        curve_name: 仪器特性曲线名称
        full_calib_name: 完整的仪器特性曲线名称
        
        返回:
        Tuple[float, float]: 感兴趣分子量区域的起始和结束时间（分钟）
        """
        try:
            logger.info("开始寻找分子量感兴趣区域")
            
            # 计算每个保留时间对应的分子量
            curve_with_mw = curve.copy()
            curve_with_mw["log_mw"] = curve["retention_time"].apply(calibration_func)
            curve_with_mw["mw"] = 10 ** curve_with_mw["log_mw"]
            
            # 过滤无效分子量值，但保留所有时间点（即使分子量超出范围）
            # 对于超出范围的分子量，我们将其限制在合理范围内，以便可视化
            valid_mw_curve = curve_with_mw.copy()
            valid_mw_curve["mw"] = valid_mw_curve["mw"].clip(lower=1.0, upper=1e10)  # 限制分子量范围，但保留所有时间点
            
            # 找到分子量大于阈值（1000）的区域
            mw_roi = valid_mw_curve[valid_mw_curve["mw"] > self.mw_threshold]
            
            if not mw_roi.empty:
                mw_start = mw_roi["retention_time"].min()
                mw_end = mw_roi["retention_time"].max()
                logger.info(f"分子量感兴趣区域: {mw_start:.2f} - {mw_end:.2f} 分钟")
            else:
                logger.warning("未找到分子量大于阈值的区域，使用默认分子量区域")
                # 如果没有找到符合条件的区域，使用默认值
                mw_start = 10.0
                mw_end = 30.0
            
            # 可视化分子量ROI检测过程
            if output_path:
                self._plot_mw_roi_detection(curve, curve_with_mw, valid_mw_curve, mw_start, mw_end, self.mw_threshold, output_path, curve_name, full_calib_name)
            
            return (mw_start, mw_end)
        except Exception as e:
            logger.error(f"寻找分子量感兴趣区域失败: {str(e)}")
            # 发生错误时返回默认分子量区域
            return (10.0, 30.0)
    
    def calculate_roi(
        self,
        curve_name: str,
        curve_path: str,
        calibration_curve_name: str = None,
        three_arw_paths: Optional[Tuple[str, str, str]] = None,
        calibration_file_path: str = None,
        return_details: bool = False,
        visualize: bool = False,
        output_dir: str = None,
    ) -> Tuple[float, float] or Dict[str, Any]:
        """
        计算仪器特性曲线的ROI（感兴趣区域）
        
        参数:
        curve_name: 仪器特性曲线名称（如 "GPC_03_20240920_Cal001"）；若提供 ``three_arw_paths`` 则由绿线文件名推导，此参数可忽略。
        curve_path: 曲线数据目录；若提供 ``three_arw_paths`` 则不再使用。
        calibration_curve_name: 校准曲线完整名称（如 "GPC_03_20240920_Cal001_Copoly_THF_mix"），在 `data/calibration_curves` 下查找同名 JSON
        three_arw_paths: 可选，三条三色曲线文件的绝对路径，顺序为 (green, red, white)。
        calibration_file_path: 可选，校准表文件路径；``.json`` 直接读取，``.pdf`` 先解析再拟合（与样品命名无关）。
        return_details: 是否返回详细信息，默认False
        visualize: 是否生成可视化结果，默认False
        output_dir: 可视化结果输出目录，默认None
        
        返回:
        如果return_details为False: Tuple[float, float] - ROI的起始和结束时间（分钟）
        如果return_details为True: Dict[str, Any] - 包含详细分析结果的字典
        """
        try:
            # 1. 读取三条曲线数据
            if three_arw_paths is not None:
                if len(three_arw_paths) != 3:
                    logger.warning("three_arw_paths 长度异常: %d, 需要 3 条", len(three_arw_paths))
                    raise ValueError("three_arw_paths 必须为 (green, red, white) 三条 .arw 路径")
                g_path, r_path, w_path = three_arw_paths
                for p, label in ((g_path, "green"), (r_path, "red"), (w_path, "white")):
                    if not p or not os.path.isfile(p):
                        logger.warning("三色曲线文件不存在 (%s): %s", label, p)
                        raise ValueError(f"三色曲线文件不存在 ({label}): {p}")
                curves = [
                    self.read_arw_file(g_path),
                    self.read_arw_file(r_path),
                    self.read_arw_file(w_path),
                ]
                stem = os.path.splitext(os.path.basename(g_path))[0]
                if stem.lower().endswith("_green"):
                    curve_name = stem[: -len("_green")]
                else:
                    curve_name = stem
                logger.info(f"使用显式三色路径计算 ROI，推导曲线名: {curve_name}")
            else:
                logger.info(f"开始计算曲线 {curve_name} 的ROI")
                colors = ["green", "red", "white"]
                curves = []
                for color in colors:
                    file_path = os.path.join(curve_path, f"{curve_name}_{color}.arw")
                    curve = self.read_arw_file(file_path)
                    curves.append(curve)
            
            # 2. 获取校准曲线函数（显式文件：json / pdf 均由 get_calibration_curve_from_file 处理）
            if calibration_file_path and os.path.isfile(calibration_file_path):
                calibration_func = self.calibration.get_calibration_curve_from_file(calibration_file_path)
                full_calib_name = os.path.splitext(os.path.basename(calibration_file_path))[0]
            elif calibration_curve_name:
                calibration_func = self.calibration.get_calibration_curve(calibration_curve_name)
                full_calib_name = calibration_curve_name  # 使用提供的完整校准曲线名称
            else:
                # 尝试查找匹配的校准曲线文件
                try:
                    json_dir = GLOBAL_CONFIG["data_storage"]["calibration_curves"]
                    json_files = [f for f in os.listdir(json_dir) if f.endswith(".json")]
                    
                    # 查找匹配的校准曲线文件
                    matched_curve = None
                    for json_file in json_files:
                        if curve_name in json_file:
                            matched_curve = os.path.splitext(json_file)[0]
                            break
                    
                    if matched_curve:
                        logger.info(f"找到匹配的校准曲线文件: {matched_curve}")
                        calibration_func = self.calibration.get_calibration_curve(matched_curve)
                        full_calib_name = matched_curve  # 保存完整的校准曲线名称
                    else:
                        logger.warning(f"未找到匹配的校准曲线文件，使用默认校准曲线")
                        # 使用默认的校准曲线函数
                        def default_calibration_func(t):
                            return -0.2 * t + 9.0
                        calibration_func = default_calibration_func
                        full_calib_name = "默认校准曲线"  # 默认校准曲线名称
                except Exception as e:
                    logger.warning(f"获取校准曲线失败: {str(e)}，使用默认校准曲线")
                    # 使用默认的校准曲线函数
                    def default_calibration_func(t):
                        return -0.2 * t + 9.0
                    calibration_func = default_calibration_func
                    full_calib_name = "默认校准曲线"  # 默认校准曲线名称
            
            # 3. 寻找溶剂峰区域（无三色曲线时使用默认截断时间）
            # 3. 寻找溶剂峰区域
            solvent_output_path = os.path.join(output_dir, f"{curve_name}_solvent_peak_detection.png") if visualize and output_dir else None
            solvent_start, solvent_end = self.find_solvent_peak_region(curves, solvent_output_path, curve_name, full_calib_name)

            # 4. 寻找分子量感兴趣区域
            mw_output_path = os.path.join(output_dir, f"{curve_name}_mw_roi_detection.png") if visualize and output_dir else None
            mw_start, mw_end = self.find_mw_roi_region(curves[0], calibration_func, mw_output_path, curve_name, full_calib_name)

            # 5. 结合两个分析结果，确定最终ROI
            # ROI = 分子量感兴趣区域 - 溶剂峰区域
            roi_start = mw_start
            roi_end = min(mw_end, solvent_start)  # 剔除溶剂峰区域

            logger.info(f"最终ROI计算结果:")
            logger.info(f"  溶剂峰区域: {solvent_start:.2f} - {solvent_end:.2f} 分钟")
            logger.info(f"  分子量感兴趣区域: {mw_start:.2f} - {mw_end:.2f} 分钟")
            logger.info(f"  最终ROI: {roi_start:.2f} - {roi_end:.2f} 分钟")
            
            # 6. 可视化最终结果
            if visualize and output_dir:
                # 创建输出目录（如果不存在）
                os.makedirs(output_dir, exist_ok=True)
                
                # 绘制最终ROI结果
                roi_output_path = os.path.join(output_dir, f"{curve_name}_roi_result.png")
                self.plot_roi_result(curves[0], roi_start, roi_end, solvent_start, solvent_end, output_path=roi_output_path, curve_name=curve_name, mw_threshold=self.mw_threshold, full_calib_name=full_calib_name)
            
            if return_details:
                return {
                    "curve_name": curve_name,
                    "roi_start": roi_start,
                    "roi_end": roi_end,
                    "solvent_start": solvent_start,
                    "solvent_end": solvent_end,
                    "mw_start": mw_start,
                    "mw_end": mw_end,
                    "curves": curves,
                    "mw_threshold": self.mw_threshold,
                    "full_calib_name": full_calib_name,  # 返回完整的校准曲线名称
                    "calibration_func": calibration_func
                }
            else:
                return roi_start, roi_end
        except Exception as e:
            logger.error(f"计算ROI失败: {str(e)}")
            raise
    
    def plot_roi_result(self, curve: pd.DataFrame, roi_start: float, roi_end: float, solvent_start: float, solvent_end: float, output_path: str = None, curve_name: str = None, mw_threshold: float = 1000, full_calib_name: str = None, reference_curves: List[pd.DataFrame] = None, actual_curve_name: str = None) -> None:
        """
        可视化ROI结果，包括溶剂峰区域和分子量感兴趣区域，使两个区域的标记能够重叠显示

        参数:
        curve: 曲线的DataFrame
        roi_start: ROI起始时间（分钟）
        roi_end: ROI结束时间（分钟）
        solvent_start: 溶剂峰区域起始时间（分钟）
        solvent_end: 溶剂峰区域结束时间（分钟）
        output_path: 输出图片路径，如果为None则显示图片
        curve_name: 仪器特性曲线名称
        mw_threshold: 分子量阈值
        full_calib_name: 完整的仪器特性曲线名称
        reference_curves: 参考曲线列表（三色曲线），用于绘制虚线
        actual_curve_name: 实际洗脱曲线名称，用于标题
        """
        try:
            logger.info("开始绘制ROI结果图")

            # 计算每个保留时间对应的分子量，用于分析0-12.09部分
            # 这里我们需要临时计算分子量，以便分析0-12.09部分
            # 首先获取校准曲线函数
            json_dir = GLOBAL_CONFIG["data_storage"]["calibration_curves"]
            json_files = [f for f in os.listdir(json_dir) if f.endswith(".json")]

            # 查找匹配的校准曲线文件
            matched_curve = None
            for json_file in json_files:
                if curve_name in json_file:
                    matched_curve = os.path.splitext(json_file)[0]
                    break

            if matched_curve:
                calibration_func = self.calibration.get_calibration_curve(matched_curve)
            else:
                # 使用默认的校准曲线函数
                def calibration_func(t):
                    return -0.2 * t + 9.0

            # 计算分子量
            curve_with_mw = curve.copy()
            curve_with_mw["log_mw"] = curve["retention_time"].apply(calibration_func)
            curve_with_mw["mw"] = 10 ** curve_with_mw["log_mw"]

            # 过滤无效分子量值，但保留所有时间点（即使分子量超出范围）
            # 对于超出范围的分子量，我们将其限制在合理范围内，以便可视化
            valid_mw_curve = curve_with_mw.copy()
            valid_mw_curve["mw"] = valid_mw_curve["mw"].clip(lower=1.0, upper=1e10)  # 限制分子量范围，但保留所有时间点

            # 分析低分子量区域：除了高分子量ROI之外的所有部分（<1000 Da）
            # 低分子量区域包括高分子量ROI之前和之后的所有部分
            low_mw_region = valid_mw_curve[valid_mw_curve["mw"] <= mw_threshold]

            # 获取整个时间序列的范围
            full_time_start = valid_mw_curve["retention_time"].min()
            full_time_end = valid_mw_curve["retention_time"].max()

            # 初始化低分子量区域变量
            low_mw_before_start = full_time_start
            low_mw_before_end = roi_start
            low_mw_after_start = roi_end
            low_mw_after_end = full_time_end

            # 低分子量区域包括两部分：ROI之前和ROI之后
            # ROI之前的低分子量区域
            low_mw_before_roi = low_mw_region[low_mw_region["retention_time"] < roi_start]
            if not low_mw_before_roi.empty:
                low_mw_before_start = low_mw_before_roi["retention_time"].min()
                low_mw_before_end = roi_start

            # ROI之后的低分子量区域
            low_mw_after_roi = low_mw_region[low_mw_region["retention_time"] > roi_end]
            if not low_mw_after_roi.empty:
                low_mw_after_start = roi_end
                low_mw_after_end = low_mw_after_roi["retention_time"].max()

            # 创建大图，包含分析步骤
            fig, axes = plt.subplots(3, 1, figsize=(15, 18), sharex=True)

            # 添加标题，使用实际洗脱曲线名称
            if actual_curve_name:
                fig.suptitle(f"GPC曲线ROI分析结果 - {actual_curve_name}\n分子量阈值: {mw_threshold} Da", fontsize=20, y=0.98)
            else:
                fig.suptitle(f"GPC曲线ROI分析结果 - {full_calib_name}\n分子量阈值: {mw_threshold} Da", fontsize=20, y=0.98)

            # 子图1: 原始曲线和分析步骤1-2
            ax1 = axes[0]
            ax1.plot(curve["retention_time"], curve["intensity"], label="原始曲线", color="black", alpha=0.7)

            # 标记低分子量区域：包括ROI之前和之后的所有部分
            ax1.axvspan(low_mw_before_start, low_mw_before_end, color="yellow", alpha=0.2, label=f"低分子量区域 (< {mw_threshold} Da)")
            ax1.axvspan(low_mw_after_start, low_mw_after_end, color="yellow", alpha=0.2)

            # 添加分析步骤标注
            ax1.text(0.02, 0.95, "分析步骤1: 读取并预处理GPC曲线数据", transform=ax1.transAxes, fontsize=12, fontweight='bold', verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            ax1.text(0.02, 0.85, "分析步骤2: 分别进行溶剂峰检测和分子量ROI检测", transform=ax1.transAxes, fontsize=12, fontweight='bold', verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            ax1.text(0.02, 0.75, f"注: 低分子量区域(<{mw_threshold} Da)包括除高分子量ROI外的所有部分，通常不包含在ROI中", transform=ax1.transAxes, fontsize=12, fontweight='bold', verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))



            ax1.set_title("GPC曲线ROI分析结果 - 分析步骤1-3", fontsize=16)
            ax1.set_ylabel("信号强度", fontsize=14)
            ax1.legend(fontsize=12, loc='upper right')
            ax1.grid(True, alpha=0.3)

            # 子图2: 标记各检测区域
            ax2 = axes[1]
            ax2.plot(curve["retention_time"], curve["intensity"], label="原始曲线", color="black", alpha=0.7)

            # 标记低分子量区域：包括ROI之前和之后的所有部分
            ax2.axvspan(low_mw_before_start, low_mw_before_end, color="yellow", alpha=0.2, label=f"低分子量区域 (< {mw_threshold} Da)")
            ax2.axvspan(low_mw_after_start, low_mw_after_end, color="yellow", alpha=0.2)

            # 标记溶剂峰区域（粉红色阴影）
            if solvent_start < solvent_end:
                ax2.axvspan(solvent_start, solvent_end, color="pink", alpha=0.4, label=f"溶剂峰区域 ({solvent_start:.2f} - {solvent_end:.2f} min)")

            # 标记分子量ROI区域（绿色阴影）
            if roi_start < roi_end:
                ax2.axvspan(roi_start, roi_end, color="green", alpha=0.3, label=f"分子量ROI区域 ({roi_start:.2f} - {roi_end:.2f} min, > {mw_threshold} Da)")

            # 添加分析步骤标注
            ax2.text(0.02, 0.95, "分析步骤3: 标记检测到的溶剂峰区域和分子量ROI区域", transform=ax2.transAxes, fontsize=12, fontweight='bold', verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))



            ax2.set_title("GPC曲线ROI分析结果 - 分析步骤4", fontsize=16)
            ax2.set_ylabel("信号强度", fontsize=14)
            ax2.legend(fontsize=12, loc='upper right')
            ax2.grid(True, alpha=0.3)

            # 子图3: 最终ROI结果
            ax3 = axes[2]
            ax3.plot(curve["retention_time"], curve["intensity"], label="原始曲线", color="black", alpha=0.7)

            # 只标记最终ROI区域，其他区域留白
            if roi_start < roi_end:
                ax3.axvspan(roi_start, roi_end, color="blue", alpha=0.5, label=f"最终ROI区域 ({roi_start:.2f} - {roi_end:.2f} min, > {mw_threshold} Da)")

            # 添加分析步骤标注，简化说明
            ax3.text(0.02, 0.95, "分析步骤5: 最终ROI结果", transform=ax3.transAxes, fontsize=12, fontweight='bold', verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))

            # 简化图例，只保留必要的标记
            ax3.set_title("GPC曲线ROI分析结果 - 分析步骤5", fontsize=16)
            ax3.set_xlabel("保留时间 (分钟)", fontsize=14)
            ax3.set_ylabel("信号强度", fontsize=14)
            ax3.legend(fontsize=12, loc='upper right')
            ax3.grid(True, alpha=0.3)

            # 设置x轴范围，聚焦在有数据的区域
            min_rt = curve["retention_time"].min()
            max_rt = curve["retention_time"].max()
            ax3.set_xlim([min_rt, max_rt])

            # 调整Y轴范围，只基于洗脱曲线的强度
            # 计算洗脱曲线的最大和最小强度
            min_intensity = curve["intensity"].min() * 0.9  # Y轴下限，留出一些余量
            max_intensity = curve["intensity"].max() * 1.1  # Y轴上限，留出一些余量

            # 确保Y轴下限不低于0，除非曲线有负值
            if min_intensity > 0:
                min_intensity = 0

            # 移除硬性Y轴范围限制，确保所有数据都能显示
            # 根据曲线的实际强度范围自动调整，确保曲线显示清晰
            for ax in axes:
                # 设置合适的Y轴范围，确保所有曲线都能完整显示
                ax.set_ylim([min_intensity, max_intensity])

                # 添加Y轴范围标注到图例
                ax.plot([], [], ' ', label=f'Y轴范围: {min_intensity:.2f} - {max_intensity:.2f}')

            # 调整布局
            plt.tight_layout(rect=[0, 0, 1, 0.96])

            # 保存或显示图片
            if output_path:
                plt.savefig(output_path, dpi=300, bbox_inches="tight")
                logger.info(f"ROI结果图已保存到: {output_path}")
            else:
                plt.show()

        except Exception as e:
            logger.error(f"绘制ROI结果图失败: {str(e)}")
            raise
    
    def _normalize_curve(self, curve: pd.DataFrame) -> pd.DataFrame:
        """
        对曲线进行归一化处理，将强度值归一化到0-1范围内
        
        参数:
        curve: 原始曲线DataFrame
        
        返回:
        归一化后的曲线DataFrame
        """
        normalized_curve = curve.copy()
        min_intensity = curve["intensity"].min()
        max_intensity = curve["intensity"].max()
        
        # 避免除以零
        if max_intensity - min_intensity > 0:
            normalized_curve["intensity"] = (curve["intensity"] - min_intensity) / (max_intensity - min_intensity)
        return normalized_curve
    
    def _plot_solvent_peak_detection(self, smoothed_curves: List[pd.DataFrame], all_peak_times: List[np.ndarray], all_peak_heights: List[np.ndarray], solvent_peak_time: float, solvent_start: float, solvent_end: float, output_path: str, curve_name: str, min_time: float, max_time: float, full_calib_name: str = None) -> None:
        """
        绘制溶剂峰检测过程的大图，包含详细的分析步骤
        
        参数:
        smoothed_curves: 平滑后的曲线列表
        all_peak_times: 各曲线的峰值时间列表
        all_peak_heights: 各曲线的峰值高度列表
        solvent_peak_time: 确定的溶剂峰时间
        solvent_start: 溶剂峰区域起始时间
        solvent_end: 溶剂峰区域结束时间
        output_path: 输出图片路径
        curve_name: 仪器特性曲线名称
        min_time: 整个时间序列的最小时间
        max_time: 整个时间序列的最大时间
        full_calib_name: 完整的仪器特性曲线名称
        """
        try:
            logger.info("开始绘制溶剂峰检测过程")
            
            color_names = ["绿色曲线", "红色曲线", "蓝色曲线"]
            colors = ["green", "red", "blue"]
            
            # 归一化曲线数据
            normalized_curves = [self._normalize_curve(curve) for curve in smoothed_curves]
            
            # 创建大图，包含4个子图，展示完整分析步骤
            fig, axes = plt.subplots(2, 2, figsize=(18, 15))
            
            # 添加三色曲线名称，明确说明是三色曲线分析
            fig.suptitle(f"溶剂峰检测分析 - 三色曲线 ({full_calib_name if full_calib_name else curve_name})\n分子量阈值: {self.mw_threshold} Da", fontsize=20, y=0.98)
            
            # 子图1: 原始曲线和峰值检测（分析步骤1-2）
            ax1 = axes[0, 0]
            
            # 收集所有峰值信息，用于后续分析
            all_peaks_info = []
            
            for i, (curve, normalized_curve, color, name) in enumerate(zip(smoothed_curves, normalized_curves, colors, color_names)):
                # 绘制归一化后的曲线
                ax1.plot(normalized_curve["retention_time"], normalized_curve["intensity"], color=color, label=f"{name} (归一化)", alpha=0.8)
                
                # 绘制峰值（需要将峰值高度也归一化）
                for j, (peak_time, peak_height) in enumerate(zip(all_peak_times[i], all_peak_heights[i])):
                    # 归一化峰值高度
                    min_intensity = curve["intensity"].min()
                    max_intensity = curve["intensity"].max()
                    normalized_peak_height = (peak_height - min_intensity) / (max_intensity - min_intensity) if (max_intensity - min_intensity) > 0 else 0
                    
                    # 绘制峰值点
                    ax1.scatter(peak_time, normalized_peak_height, color=color, marker="x", s=120, alpha=1.0, edgecolors='black', linewidths=1.5)
                    
                    # 为每个峰值添加标注，显示保留时间
                    ax1.annotate(f"{peak_time:.2f} min", xy=(peak_time, normalized_peak_height), 
                               xytext=(5, 5), textcoords="offset points", fontsize=10, 
                               bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=color, alpha=0.7))
                    
                    # 收集峰值信息
                    all_peaks_info.append({
                        "curve_name": name,
                        "curve_index": i,
                        "peak_index": j,
                        "retention_time": peak_time,
                        "height": peak_height,
                        "normalized_height": normalized_peak_height,
                        "color": color
                    })
            
            # 对所有峰值进行排序，便于分析
            all_peaks_info_sorted = sorted(all_peaks_info, key=lambda x: x["retention_time"])
            
            # 添加峰值分析说明
            ax1.text(0.02, 0.85, "分析步骤1-2: 平滑曲线与峰值检测\n所有峰值均已标记，标注显示保留时间", 
                     transform=ax1.transAxes, fontsize=12, fontweight='bold', 
                     verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
            
            ax1.set_title("溶剂峰检测 - 分析步骤1-2: 平滑曲线与峰值检测", fontsize=16)
            ax1.set_xlabel("保留时间 (分钟)", fontsize=14)
            ax1.set_ylabel("归一化信号强度", fontsize=14)
            ax1.legend(fontsize=12, loc='upper right')
            ax1.grid(True, alpha=0.3)
            ax1.set_xlim([min_time, max_time])  # 拉长到整个时间序列
            
            # 子图2: 峰值时间对比（分析步骤3）
            ax2 = axes[0, 1]
            
            # 1. 绘制所有峰值点，包括重叠和非重叠区域
            all_peak_points = []
            for i, (peak_times, color, name) in enumerate(zip(all_peak_times, colors, color_names)):
                y_positions = np.ones_like(peak_times) * (i + 1)
                ax2.scatter(peak_times, y_positions, color=color, label=name, alpha=0.9, s=120, edgecolors='black', linewidths=1.5)
                
                # 记录所有峰值点，用于后续重叠分析
                for peak_time in peak_times:
                    all_peak_points.append((peak_time, i+1, color))
            
            # 2. 绘制所有峰值的垂直线，显示完整的峰值分布
            # 先绘制所有垂直线，避免遮挡
            for i, (peak_times, color) in enumerate(zip(all_peak_times, colors)):
                for peak_time in peak_times:
                    ax2.axvline(x=peak_time, color=color, linestyle="--", alpha=0.4, linewidth=1)
            
            # 3. 标记重叠区域
            # 定义重叠阈值
            overlap_threshold = 0.3  # 分钟
            
            # 创建所有峰值时间的平面列表
            flat_peak_times = [peak_time for curve_peaks in all_peak_times for peak_time in curve_peaks]
            
            # 找出重叠区域
            overlap_regions = []
            # 对所有峰值时间排序
            sorted_peaks = sorted(flat_peak_times)
            
            i = 0
            while i < len(sorted_peaks):
                current_peak = sorted_peaks[i]
                # 查找重叠的峰值
                overlap_group = [current_peak]
                j = i + 1
                while j < len(sorted_peaks):
                    if sorted_peaks[j] - current_peak <= overlap_threshold:
                        overlap_group.append(sorted_peaks[j])
                        j += 1
                    else:
                        break
                # 如果有2个或更多峰值重叠，标记为重叠区域
                if len(overlap_group) >= 2:
                    overlap_start = min(overlap_group)
                    overlap_end = max(overlap_group)
                    overlap_regions.append((overlap_start, overlap_end))
                i = j
            
            # 绘制重叠区域阴影
            for start, end in overlap_regions:
                ax2.axvspan(start - 0.1, end + 0.1, color='gray', alpha=0.2, label='峰值重叠区域')
            
            # 4. 标记溶剂峰位置
            ax2.axvline(x=solvent_peak_time, color="purple", linestyle="-", linewidth=3, alpha=0.8, label=f"确定的溶剂峰时间 ({solvent_peak_time:.2f} min)")
            
            # 5. 设置标题和标签
            ax2.set_title("溶剂峰检测 - 分析步骤3: 峰值时间对比与重叠分析", fontsize=16)
            ax2.set_xlabel("保留时间 (分钟)", fontsize=14)
            ax2.set_yticks([1, 2, 3])
            ax2.set_yticklabels(color_names)
            ax2.set_xlim([min_time, max_time])  # 拉长到整个时间序列
            
            # 6. 优化图例，只显示一次重叠区域标签
            handles, labels = ax2.get_legend_handles_labels()
            unique_labels = {}
            for handle, label in zip(handles, labels):
                if label not in unique_labels:
                    unique_labels[label] = handle
            ax2.legend(unique_labels.values(), unique_labels.keys(), fontsize=12, loc='upper right')
            
            ax2.grid(True, alpha=0.3)
            
            # 7. 添加详细的峰值分析说明
            # 统计每个曲线的峰值数量
            peak_counts = [len(peak_times) for peak_times in all_peak_times]
            
            # 统计重叠区域数量
            overlap_count = len(overlap_regions)
            
            # 生成峰值分析文本
            analysis_text = f"分析说明: 每个曲线的峰值用不同颜色标记\n"
            analysis_text += f"- 绿色曲线峰值数量: {peak_counts[0]} 个\n"
            analysis_text += f"- 红色曲线峰值数量: {peak_counts[1]} 个\n"
            analysis_text += f"- 蓝色曲线峰值数量: {peak_counts[2]} 个\n"
            analysis_text += f"- 峰值重叠区域数量: {overlap_count} 个\n"
            analysis_text += f"- 垂直虚线表示各曲线的所有峰值\n"
            analysis_text += f"- 灰色阴影区域表示峰值重叠区域\n"
            analysis_text += f"- 紫色实线表示最终确定的溶剂峰\n"
            analysis_text += f"\n所有峰值均已标记，便于完整分析峰分布情况"
            
            ax2.text(0.02, 0.95, analysis_text, 
                     transform=ax2.transAxes, fontsize=11, fontweight='bold', verticalalignment='top', 
                     bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
            
            # 子图3: 溶剂峰区域确定（分析步骤4）
            ax3 = axes[1, 0]
            for i, (normalized_curve, color, name) in enumerate(zip(normalized_curves, colors, color_names)):
                ax3.plot(normalized_curve["retention_time"], normalized_curve["intensity"], color=color, label=f"{name} (归一化)", alpha=0.8)
            
            # 标记溶剂峰区域
            ax3.axvspan(solvent_start, solvent_end, color="pink", alpha=0.4, label=f"溶剂峰区域 ({solvent_start:.2f} - {solvent_end:.2f} min)")
            ax3.axvline(x=solvent_peak_time, color="purple", linestyle="--", linewidth=2, alpha=0.8, label=f"溶剂峰时间 ({solvent_peak_time:.2f} min)")
            
            # 添加分析步骤说明，调整位置避免重叠
            ax3.text(0.02, 0.85, "分析步骤4: 基于重叠峰值确定溶剂峰区域\n- 溶剂峰时间: {:.2f} min\n- 区域范围: 峰值前1分钟至峰值后1.5分钟".format(solvent_peak_time), 
                     transform=ax3.transAxes, fontsize=12, fontweight='bold', verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightpink', alpha=0.8))
            
            ax3.set_title("溶剂峰检测 - 分析步骤4: 溶剂峰区域确定", fontsize=16)
            ax3.set_xlabel("保留时间 (分钟)", fontsize=14)
            ax3.set_ylabel("归一化信号强度", fontsize=14)
            ax3.set_xlim([min_time, max_time])  # 拉长到整个时间序列
            ax3.legend(fontsize=12, loc='upper right')
            ax3.grid(True, alpha=0.3)
            
            # 子图4: 最终溶剂峰结果（分析步骤5）
            ax4 = axes[1, 1]
            # 显示归一化后的第一条曲线和溶剂峰区域
            ax4.plot(normalized_curves[0]["retention_time"], normalized_curves[0]["intensity"], color="black", label="GPC曲线 (归一化)", alpha=0.7)
            ax4.axvspan(solvent_start, solvent_end, color="pink", alpha=0.6, label=f"溶剂峰区域 ({solvent_start:.2f} - {solvent_end:.2f} min)")
            
            # 添加分析步骤说明
            ax4.text(0.02, 0.85, "分析步骤5: 最终溶剂峰检测结果\n- 通过三条曲线对比找到重叠且靠后的溶剂峰\n- 溶剂峰区域将从ROI中剔除", 
                     transform=ax4.transAxes, fontsize=12, fontweight='bold', verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightpink', alpha=0.8))
            
            ax4.set_title("溶剂峰检测 - 分析步骤5: 最终溶剂峰结果", fontsize=16)
            ax4.set_xlabel("保留时间 (分钟)", fontsize=14)
            ax4.set_ylabel("归一化信号强度", fontsize=14)
            ax4.set_xlim([min_time, max_time])  # 拉长到整个时间序列
            ax4.legend(fontsize=12, loc='upper right')
            ax4.grid(True, alpha=0.3)
            
            # 调整布局
            plt.tight_layout(rect=[0, 0, 1, 0.96])
            
            # 保存图片
            plt.savefig(output_path, dpi=300, bbox_inches="tight")
            logger.info(f"溶剂峰检测图已保存到: {output_path}")
            plt.close()
            
        except Exception as e:
            logger.error(f"绘制溶剂峰检测过程失败: {str(e)}")
            plt.close()
            raise
    
    def _plot_mw_roi_detection(self, curve: pd.DataFrame, curve_with_mw: pd.DataFrame, valid_mw_curve: pd.DataFrame, mw_start: float, mw_end: float, mw_threshold: float, output_path: str, curve_name: str = None, full_calib_name: str = None) -> None:
        """
        绘制分子量ROI检测过程的大图，包含详细的分析步骤，X轴拉长到整个时间序列
        
        参数:
        curve: 原始曲线
        curve_with_mw: 包含分子量信息的曲线
        valid_mw_curve: 过滤后的有效分子量曲线
        mw_start: ROI起始时间
        mw_end: ROI结束时间
        mw_threshold: 分子量阈值
        output_path: 输出图片路径
        curve_name: 仪器特性曲线名称
        full_calib_name: 完整的仪器特性曲线名称
        """
        try:
            logger.info("开始绘制分子量ROI检测过程")
            
            # 获取整个时间序列范围
            min_time = curve["retention_time"].min()
            max_time = curve["retention_time"].max()
            
            # 创建大图，包含4个子图，展示完整分析步骤
            fig, axes = plt.subplots(2, 2, figsize=(18, 15))
            
            # 添加仪器特性曲线名称和分子量阈值，使用完整名称
            fig.suptitle(f"分子量ROI检测分析 - {full_calib_name if full_calib_name else curve_name}\n分子量阈值: {mw_threshold} Da", fontsize=20, y=0.98)
            
            # 子图1: 原始曲线（分析步骤1）
            ax1 = axes[0, 0]
            ax1.plot(curve["retention_time"], curve["intensity"], color="black", label="原始GPC曲线")
            ax1.set_title("分子量ROI检测 - 分析步骤1: 原始GPC曲线", fontsize=16)
            ax1.set_xlabel("保留时间 (分钟)", fontsize=14)
            ax1.set_ylabel("信号强度", fontsize=14)
            ax1.legend(fontsize=12, loc='upper right')
            ax1.grid(True, alpha=0.3)
            ax1.set_xlim([min_time, max_time])  # 拉长到整个时间序列
            
            # 子图2: 保留时间-分子量关系（分析步骤2-3）
            ax2 = axes[0, 1]
            
            # 绘制完整的分子量分布曲线，包括0-12.09分钟的低分子量区域
            ax2.plot(valid_mw_curve["retention_time"], valid_mw_curve["mw"], color="blue", label="分子量分布")
            ax2.axhline(y=mw_threshold, color="red", linestyle="--", linewidth=2, label=f"分子量阈值 ({mw_threshold} Da)")
            
            # 分析低分子量区域和高分子量区域
            low_mw_region = valid_mw_curve[valid_mw_curve["mw"] <= mw_threshold]
            high_mw_region = valid_mw_curve[valid_mw_curve["mw"] > mw_threshold]
            
            # 如果有低分子量区域数据，绘制出来
            if not low_mw_region.empty:
                ax2.plot(low_mw_region["retention_time"], low_mw_region["mw"], color="yellow", linewidth=3, label="低分子量区域 (< 1000 Da)")
                # 标注低分子量区域
                ax2.fill_between(low_mw_region["retention_time"], low_mw_region["mw"], mw_threshold, color="yellow", alpha=0.2)
            
            # 如果有高分子量区域数据，绘制出来
            if not high_mw_region.empty:
                ax2.plot(high_mw_region["retention_time"], high_mw_region["mw"], color="green", linewidth=3, label="高分子量区域 (> 1000 Da)")
                # 标注高分子量区域
                ax2.fill_between(high_mw_region["retention_time"], high_mw_region["mw"], mw_threshold, color="green", alpha=0.2)
            
            ax2.set_yscale("log")
            
            # 设置Y轴范围，确保所有曲线都能完整显示
            # 计算分子量的最小值和最大值，考虑到对数刻度
            min_mw_plot = valid_mw_curve["mw"].min()
            max_mw_plot = valid_mw_curve["mw"].max()
            
            # 确保Y轴范围足够大，涵盖所有数据点
            # 对于对数刻度，我们需要设置合理的上下限
            ax2.set_ylim([min_mw_plot * 0.5, max_mw_plot * 2])  # 扩大范围，确保所有曲线都能显示
            
            # 添加分析步骤说明，调整位置避免重叠
            ax2.text(0.02, 0.85, f"分析步骤2-3: 建立保留时间-分子量关系\n- 使用校准曲线将保留时间转换为分子量\n- 设置分子量阈值 {mw_threshold} Da 筛选感兴趣区域\n- 低分子量区域: < 1000 Da (主要在0-12.09分钟)\n- 高分子量区域: > 1000 Da (主要在12.09分钟后)", 
                     transform=ax2.transAxes, fontsize=12, fontweight='bold', verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
            
            ax2.set_title("分子量ROI检测 - 分析步骤2-3: 保留时间-分子量关系", fontsize=16)
            ax2.set_xlabel("保留时间 (分钟)", fontsize=14)
            ax2.set_ylabel("分子量 (道尔顿)", fontsize=14)
            ax2.legend(fontsize=12, loc='upper right')
            ax2.grid(True, alpha=0.3)
            ax2.set_xlim([min_time, max_time])  # 拉长到整个时间序列
            
            # 子图3: 分子量分布直方图（分析步骤4）
            ax3 = axes[1, 0]
            # 只使用有效的分子量值
            valid_mw = valid_mw_curve["mw"].dropna()
            if not valid_mw.empty:
                # 设置合理的直方图范围
                min_mw = valid_mw.min()
                max_mw = valid_mw.max()
                
                # 确保范围是合理的
                min_mw = max(min_mw, 100)  # 最小分子量至少为100
                max_mw = min(max_mw, 1e7)   # 最大分子量不超过1e7
                
                # 创建直方图
                ax3.hist(valid_mw, bins=np.logspace(np.log10(min_mw), np.log10(max_mw), 50), color="green", alpha=0.7, label="分子量分布")
                ax3.axvline(x=mw_threshold, color="red", linestyle="--", linewidth=2, label=f"分子量阈值 ({mw_threshold} Da)")
                ax3.axvspan(mw_threshold, max_mw, color="green", alpha=0.3, label="分子量>阈值区域")
                ax3.set_xscale("log")
                
                # 添加分析步骤说明
                ax3.text(0.02, 0.85, f"分析步骤4: 分子量分布分析\n- 统计分子量分布情况\n- 确定分子量>阈值({mw_threshold} Da)的区域范围", 
                         transform=ax3.transAxes, fontsize=12, fontweight='bold', verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))
                
                ax3.set_title("分子量ROI检测 - 分析步骤4: 分子量分布直方图", fontsize=16)
                ax3.set_xlabel("分子量 (道尔顿)", fontsize=14)
                ax3.set_ylabel("频率", fontsize=14)
                ax3.legend(fontsize=12, loc='upper right')
                ax3.grid(True, alpha=0.3)
            
            # 分析低分子量区域（0-12.09分钟部分）
            low_mw_region = valid_mw_curve[valid_mw_curve["mw"] <= mw_threshold]
            low_mw_start = low_mw_region["retention_time"].min() if not low_mw_region.empty else 0.0
            low_mw_end = low_mw_region["retention_time"].max() if not low_mw_region.empty else 12.09
            
            # 子图4: 最终分子量ROI结果（分析步骤5）
            ax4 = axes[1, 1]
            ax4.plot(curve["retention_time"], curve["intensity"], color="black", label="GPC曲线", alpha=0.7)
            
            # 标记低分子量区域（0-12.09分钟部分）
            ax4.axvspan(low_mw_start, low_mw_end, color="yellow", alpha=0.2, label=f"低分子量区域 ({low_mw_start:.2f} - {low_mw_end:.2f} min, < {mw_threshold} Da)")
            
            # 标记分子量ROI区域
            ax4.axvspan(mw_start, mw_end, color="green", alpha=0.6, label=f"分子量ROI区域 ({mw_start:.2f} - {mw_end:.2f} min, > {mw_threshold} Da)")
            
            # 添加分析步骤说明
            ax4.text(0.02, 0.85, f"分析步骤5: 最终分子量ROI结果\n- 基于分子量阈值 {mw_threshold} Da 确定ROI区域\n- ROI区域: {mw_start:.2f} - {mw_end:.2f} 分钟\n- 低分子量区域: {low_mw_start:.2f} - {low_mw_end:.2f} 分钟 (分子量 < {mw_threshold} Da)", 
                     transform=ax4.transAxes, fontsize=12, fontweight='bold', verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))
            
            ax4.set_title("分子量ROI检测 - 分析步骤5: 最终分子量ROI结果", fontsize=16)
            ax4.set_xlabel("保留时间 (分钟)", fontsize=14)
            ax4.set_ylabel("信号强度", fontsize=14)
            ax4.set_xlim([min_time, max_time])  # 拉长到整个时间序列
            ax4.legend(fontsize=12, loc='upper right')
            ax4.grid(True, alpha=0.3)
            
            # 调整布局
            plt.tight_layout(rect=[0, 0, 1, 0.96])
            
            # 保存图片
            plt.savefig(output_path, dpi=300, bbox_inches="tight")
            logger.info(f"分子量ROI检测图已保存到: {output_path}")
            plt.close()
            
        except Exception as e:
            logger.error(f"绘制分子量ROI检测过程失败: {str(e)}")
            plt.close()
            raise
