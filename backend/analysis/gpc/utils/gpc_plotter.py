import logging
import os
from typing import Optional, List, Dict, Callable

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from scipy.ndimage import minimum_filter1d
from config import setup_logging

# 配置日志记录
setup_logging(logger_name="GPCDataPlotter")
logger = logging.getLogger("GPCDataPlotter")

def enhanced_gpc_plot(time, response, start_idx, end_idx, M_i, h_i, Mn, Mw, Mz, PDI):
    """
    生成专业的 GPC 分析报告图
    """
    fig = plt.figure(figsize=(12, 10))
    gs = fig.add_gridspec(2, 2)

    # 1. 原始色谱图与基线
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(time, response, 'gray', alpha=0.5, label='原始信号')
    # 突出显示计算区间
    peak_t = time[start_idx:end_idx + 1]
    peak_r = response[start_idx:end_idx + 1]
    baseline = np.linspace(response[start_idx], response[end_idx], len(peak_t))

    ax1.fill_between(peak_t, baseline, peak_r, color='skyblue', alpha=0.3, label='积分区域')
    ax1.plot(peak_t, peak_r, 'blue', linewidth=1.5)
    ax1.scatter([time[start_idx], time[end_idx]], [response[start_idx], response[end_idx]], color='red', zorder=5)

    ax1.set_title("GPC 色谱峰检测与基线扣除", fontsize=14)
    ax1.set_xlabel("保留时间 (min)")
    ax1.set_ylabel("响应信号 (mV)")
    ax1.legend()
    ax1.grid(True, linestyle=':', alpha=0.6)

    # 2. 分子量分布曲线 (Differential Weight Fraction)
    # 纵坐标通常使用 dW/d(logM)，这里简化为响应强度
    ax2 = fig.add_subplot(gs[1, 0])
    # 为了绘图平滑，只取有效部分并按M_i从小到大排序
    sort_idx = np.argsort(M_i)
    ax2.plot(M_i[sort_idx], h_i[sort_idx], 'green', linewidth=2)

    # 标注 Mn 和 Mw
    ax2.axvline(Mn, color='orange', linestyle='--', label=f'Mn: {Mn:,.0f}')
    ax2.axvline(Mw, color='red', linestyle='--', label=f'Mw: {Mw:,.0f}')
    ax2.axvline(Mz, color='pink', linestyle='--', label=f'Mz: {Mz:,.0f}')
    ax2.set_xscale('log')  # GPC 分子量轴必须是对数坐标
    ax2.set_title("分子量分布图 (Log Scale)", fontsize=12)
    ax2.set_xlabel("分子量 M (g/mol)")
    ax2.set_ylabel("相对含量")
    ax2.legend()
    ax2.grid(True, which="both", ls="-", alpha=0.2)

    # 3. 结果汇总表
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.axis('off')
    results_text = (
        f"--- GPC 分析结果 ---\n\n"
        f"保留时间范围: {time[start_idx]:.2f} - {time[end_idx]:.2f} min\n"
        f"峰宽: {time[end_idx] - time[start_idx]:.2f} min\n\n"
        f"数均分子量 (Mn): {Mn:,.0f} Da\n"
        f"重均分子量 (Mw): {Mw:,.0f} Da\n"
        f"Z均分子量 (Mz): {Mz:,.0f} Da\n"
        f"多分散性 (PDI): {PDI:.3f}"
    )
    ax3.text(0.1, 0.5, results_text, fontsize=12,
             bbox=dict(facecolor='white', alpha=0.5, boxstyle='round,pad=1'))

    plt.tight_layout()
    plt.show()
    plt.close(fig)



class GPCDataPlotter:
    """GPC分析结果绘制器"""

    def __init__(self, time_data, signal_data, calibration_func, peaks_info, molecular_info, output_dir, sample_name):
        self.time_data = time_data
        self.signal_data = signal_data
        self.calibration_func = calibration_func
        self.peaks_info = peaks_info
        self.molecular_info = molecular_info
        self.output_dir = output_dir
        self.sample_name = sample_name

    def plot_gpc_machine_curve(self, save_path: Optional[str] = None):
        """绘制原始数据曲线：淋出时间 vs 对数分子量并保存到文件

        参数:
        filename (str): 保存图表的文件名，默认值为 'gpc_machine_curve.png'
        """
        fig, ax = plt.subplots(figsize=(8, 5))
        try:
            ax.plot(self.time_data, self.calibration_func(self.time_data), 'b-', linewidth=1.5)
            ax.set_xlabel('Time (min)')
            ax.set_ylabel('Log Molecular Weight (Da)')
            ax.set_title('GPC Machine Curve')
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            if save_path is None:
                save_path = os.path.join(self.output_dir, f"{self.sample_name}_gpc_machine_curve.png")
            fig.savefig(save_path, dpi=300, bbox_inches='tight')
        finally:
            plt.close(fig)
        print(f"GPC标定曲线已保存到 {save_path}")

    def plot_roi_result(
            self,
            curve: pd.DataFrame,
            roi_result: Dict,
            actual_curve_name: str = "",
            save_path: Optional[str] = None
    ) -> None:
        """
        可视化ROI结果，包括溶剂峰区域和分子量感兴趣区域，使两个区域的标记能够重叠显示

        参数:
        curve: 曲线的DataFrame
        roi_result: ROI计算结果
        actual_curve_name: 实际洗脱曲线名称，用于标题
        """
        fig = None
        try:
            roi_start = roi_result['roi_start']
            roi_end = roi_result['roi_end']
            solvent_start = roi_result['solvent_start']
            solvent_end = roi_result['solvent_end']
            mw_threshold = roi_result.get('mw_threshold', 1000)
            logger.info("开始绘制ROI结果图")


            # 计算分子量
            curve_with_mw = curve.copy()
            curve_with_mw["log_mw"] = curve["retention_time"].apply(self.calibration_func)
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
            fig.suptitle(f"GPC曲线ROI分析结果 - {actual_curve_name}\n分子量阈值: {mw_threshold} Da", fontsize=20,
                         y=0.98)

            # 子图1: 原始曲线和分析步骤1-2
            ax1 = axes[0]
            ax1.plot(curve["retention_time"], curve["intensity"], label="原始曲线", color="black", alpha=0.7)

            # 标记低分子量区域：包括ROI之前和之后的所有部分
            ax1.axvspan(low_mw_before_start, low_mw_before_end, color="yellow", alpha=0.2,
                        label=f"低分子量区域 (< {mw_threshold} Da)")
            ax1.axvspan(low_mw_after_start, low_mw_after_end, color="yellow", alpha=0.2)

            # 添加分析步骤标注
            ax1.text(0.02, 0.95, "分析步骤1: 读取并预处理GPC曲线数据", transform=ax1.transAxes, fontsize=12,
                     fontweight='bold', verticalalignment='top',
                     bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            ax1.text(0.02, 0.85, "分析步骤2: 分别进行溶剂峰检测和分子量ROI检测", transform=ax1.transAxes, fontsize=12,
                     fontweight='bold', verticalalignment='top',
                     bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            ax1.text(0.02, 0.75, f"注: 低分子量区域(<{mw_threshold} Da)包括除高分子量ROI外的所有部分，通常不包含在ROI中",
                     transform=ax1.transAxes, fontsize=12, fontweight='bold', verticalalignment='top',
                     bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

            ax1.set_title("GPC曲线ROI分析结果 - 分析步骤1-3", fontsize=16)
            ax1.set_ylabel("信号强度", fontsize=14)
            ax1.legend(fontsize=12, loc='upper right')
            ax1.grid(True, alpha=0.3)

            # 子图2: 标记各检测区域
            ax2 = axes[1]
            ax2.plot(curve["retention_time"], curve["intensity"], label="原始曲线", color="black", alpha=0.7)

            # 标记低分子量区域：包括ROI之前和之后的所有部分
            ax2.axvspan(low_mw_before_start, low_mw_before_end, color="yellow", alpha=0.2,
                        label=f"低分子量区域 (< {mw_threshold} Da)")
            ax2.axvspan(low_mw_after_start, low_mw_after_end, color="yellow", alpha=0.2)

            # 标记溶剂峰区域（粉红色阴影）
            if solvent_start < solvent_end:
                ax2.axvspan(solvent_start, solvent_end, color="pink", alpha=0.4,
                            label=f"溶剂峰区域 ({solvent_start:.2f} - {solvent_end:.2f} min)")

            # 标记分子量ROI区域（绿色阴影）
            if roi_start < roi_end:
                ax2.axvspan(roi_start, roi_end, color="green", alpha=0.3,
                            label=f"分子量ROI区域 ({roi_start:.2f} - {roi_end:.2f} min, > {mw_threshold} Da)")

            # 添加分析步骤标注
            ax2.text(0.02, 0.95, "分析步骤3: 标记检测到的溶剂峰区域和分子量ROI区域", transform=ax2.transAxes,
                     fontsize=12, fontweight='bold', verticalalignment='top',
                     bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))

            ax2.set_title("GPC曲线ROI分析结果 - 分析步骤4", fontsize=16)
            ax2.set_ylabel("信号强度", fontsize=14)
            ax2.legend(fontsize=12, loc='upper right')
            ax2.grid(True, alpha=0.3)

            # 子图3: 最终ROI结果
            ax3 = axes[2]
            ax3.plot(curve["retention_time"], curve["intensity"], label="原始曲线", color="black", alpha=0.7)

            # 只标记最终ROI区域，其他区域留白
            if roi_start < roi_end:
                ax3.axvspan(roi_start, roi_end, color="blue", alpha=0.5,
                            label=f"最终ROI区域 ({roi_start:.2f} - {roi_end:.2f} min, > {mw_threshold} Da)")

            # 添加分析步骤标注，简化说明
            ax3.text(0.02, 0.95, "分析步骤5: 最终ROI结果", transform=ax3.transAxes, fontsize=12, fontweight='bold',
                     verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))

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
            fig.tight_layout(rect=[0, 0, 1, 0.96])

            # 保存或显示图片
            if save_path is None:
                save_path = os.path.join(self.output_dir, f"{self.sample_name}_roi_identification.png")

            fig.savefig(save_path, dpi=300, bbox_inches="tight")
            logger.info(f"ROI结果图已保存到: {save_path}")

        except Exception as e:
            logger.error(f"绘制ROI结果图失败: {str(e)}")
            raise
        finally:
            if fig is not None:
                plt.close(fig)

    def plot_with_cumulative(self, peak_index: int = 0, save_path: Optional[str] = None):
        """
        绘制以 Log(M) 为横坐标的微分与累积分布图
        """
        if not self.molecular_info or peak_index >= len(self.molecular_info):
            print("分子量计算结果为空")
            return

        fig, ax1 = plt.subplots(figsize=(10, 6))
        try:
            ax2 = ax1.twinx()  # 创建共享 X 轴的右侧轴

            M, logM, diff_w, cum_w = self.calculate_cumulative_distribution(peak_index)

            # 绘制微分分布曲线 (左轴)
            line1, = ax1.plot(M, diff_w, color="blue", lw=2, label=f'Peak {peak_index + 1} 微分分布')
            ax1.fill_between(M, diff_w, color="blue", alpha=0.1)

            # 绘制累积分布曲线 (右轴) - 使用虚线区分
            line2, = ax2.plot(M, cum_w, color="red", linestyle='--', lw=2, alpha=0.8,
                              label=f'Peak {peak_index + 1} 累积分布')

            # 设置横坐标为对数轴
            ax1.set_xscale('log')

            # 格式化坐标轴
            ax1.set_xlabel('分子量 Molecular Weight (g/mol) [Log Scale]', fontsize=12)
            ax1.set_ylabel('相对含量 Relative Abundance (Normalized)', fontsize=12)
            ax2.set_ylabel('累积质量分数 Cumulative Weight (%)', fontsize=12)

            ax1.set_ylim(0, 1.1)  # 微分曲线留白
            ax2.set_ylim(0, 105)  # 累积曲线 0-100%

            # 网格与图例
            ax1.grid(True, which="both", ls="-", alpha=0.15)

            # 合并图例
            lines = [line1, line2]
            labels = [l.get_label() for l in lines]
            ax1.legend(lines, labels, loc='upper left')

            ax1.set_title('GPC 分子量分析 (Logarithmic Scale)', fontsize=14)
            fig.tight_layout()
            if save_path is None:
                save_path = os.path.join(self.output_dir, f"{self.sample_name}_detailed_gpc_plot.png")
            fig.savefig(save_path, dpi=300, bbox_inches='tight')
        finally:
            plt.close(fig)
        logger.info(f"GPC分子量分析图已保存到 {save_path}")

    def plot_gpc_result(self, peak_index=0, save_path=None):
        if not self.molecular_info or peak_index >= len(self.molecular_info):
            return
        log_M = self.molecular_info[peak_index]['log_M']
        h_i = self.molecular_info[peak_index]['h_i']
        mn = self.molecular_info[peak_index]['Mn']
        mw = self.molecular_info[peak_index]['Mw']
        mz = self.molecular_info[peak_index]['Mz']

        fig, ax = plt.subplots(figsize=(10, 6))
        try:
            # 绘制分布曲线 (dW/dlogM)
            # 归一化信号以便观察
            h_norm = h_i / np.max(h_i) if np.max(h_i) != 0 else h_i
            ax.plot(log_M, h_norm, color='royalblue', linewidth=2, label='MW Distribution')
            ax.fill_between(log_M, h_norm, color='royalblue', alpha=0.15)

            # 标注平均分子量位置
            ax.axvline(x=np.log10(mn), color='forestgreen', linestyle='--', label=f'Mn={mn:.2e}')
            ax.axvline(x=np.log10(mw), color='firebrick', linestyle='--', label=f'Mw={mw:.2e}')
            ax.axvline(x=np.log10(mz), color='darkorange', linestyle='--', label=f'Mz={mz:.2e}')

            # 图表修饰
            ax.set_title(f"分子量分布结果图 - {self.sample_name}", fontsize=14)
            ax.set_xlabel("log(M)", fontsize=12)
            ax.set_ylabel("Normalized Response", fontsize=12)
            ax.legend(loc='upper left')
            ax.grid(True, linestyle=':', alpha=0.7)

            if save_path is None:
                save_path = os.path.join(self.output_dir, f"{self.sample_name}_result_plot.png")

            # 保存图片
            fig.savefig(save_path, dpi=300, bbox_inches='tight')
        finally:
            plt.close(fig)  # 释放内存，防止在循环中产生过多画布
        logger.info(f"GPC分子量分布结果图已保存到 {save_path}")

    def plot_peak_detect_process(
            self,
            peak_index: int = 0,
            detect_mode: str = 'auto',
            manual_interval: Optional[List[float]] = None,
            save_path: Optional[str] = None,
    ):
        peaks = self.peaks_info['peaks']
        peak_times = self.peaks_info['peak_times']
        peak_heights = self.peaks_info['peak_heights']
        peak_idx = peaks[peak_index]

        if detect_mode == "manual":
            manual_left_time, manual_right_time = manual_interval
            # 将时间转换为对应的索引
            safe_left = np.searchsorted(self.time_data, manual_left_time)
            safe_right = np.searchsorted(self.time_data, manual_right_time)
        else:
            peaks_details = self.peaks_info['peaks_details']
            safe_left = peaks_details[peak_index]["left_bound"]
            safe_right = peaks_details[peak_index]["right_bound"]

        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        try:
            ax1, ax2, ax3, ax4 = axes.flatten()

            # 图1: 原始信号和检测到的所有峰值
            ax1.plot(self.time_data, self.signal_data, 'b-', linewidth=2, label='原始信号')
            # 确保peak_times和peak_heights有效且长度匹配
            if len(peak_times) > 0 and len(peak_heights) > 0 and len(peak_times) == len(peak_heights):
                ax1.scatter(peak_times, peak_heights, color='red', s=100, marker='o', zorder=5,
                            label='检测到的峰值')
            # 标记当前分析的峰值（安全检查）
            if 0 <= peak_idx < len(self.time_data) and 0 <= peak_idx < len(self.signal_data):
                ax1.scatter(self.time_data[peak_idx], self.signal_data[peak_idx],
                            color='darkred', s=150, marker='*', zorder=6,
                            label=f'当前分析峰值(峰{peak_index + 1})')
            ax1.set_title('步骤1: 原始信号与峰值检测', fontsize=16)
            ax1.set_xlabel('Elution Time (min)', fontsize=14)
            ax1.set_ylabel('Detector Response', fontsize=14)
            ax1.legend(fontsize=12, loc='best')
            ax1.grid(True, linestyle='--', alpha=0.7)

            window_size = max(5, int(len(self.signal_data) * 0.05))
            origin_baseline = minimum_filter1d(self.signal_data, size=window_size, mode='reflect')

            # 图2: 基线计算
            ax2.plot(self.time_data, self.signal_data, 'b-', linewidth=2, label='原始信号')
            ax2.plot(self.time_data, origin_baseline, 'g-', linewidth=2, label='计算基线')
            # 填充基线以上区域
            ax2.fill_between(self.time_data, origin_baseline, self.signal_data,
                             color='lightblue', alpha=0.3, label='基线以上信号')
            # 标记当前分析的峰值（安全检查）
            if 0 <= peak_idx < len(self.time_data) and 0 <= peak_idx < len(self.signal_data):
                ax2.scatter(self.time_data[peak_idx], self.signal_data[peak_idx],
                            color='darkred', s=150, marker='*', zorder=6,
                            label=f'当前分析峰值(峰{peak_index + 1})')
            ax2.set_title('步骤2: 基线计算', fontsize=16)
            ax2.set_xlabel('Elution Time (min)', fontsize=14)
            ax2.set_ylabel('Detector Response', fontsize=14)
            ax2.legend(fontsize=12, loc='best')
            ax2.grid(True, linestyle='--', alpha=0.7)

            # 图3: 导数计算和边界识别（整个区域）
            # 计算导数
            dy = np.gradient(self.signal_data, 2)
            d2y = np.gradient(dy, 2)

            # 显示整个信号区域
            view_start = 0
            view_end = len(self.time_data)

            # 创建多Y轴
            ax3_main = ax3

            # 副Y轴1：用于显示一阶导数
            ax3_der1 = ax3_main.twinx()
            # 副Y轴2：用于显示二阶导数
            ax3_der2 = ax3_main.twinx()
            # 调整副Y轴2的位置，避免与副Y轴1重叠
            ax3_der2.spines['right'].set_position(('outward', 60))

            # 绘制原始信号（安全检查）
            if view_start < view_end and view_start >= 0 and view_end <= len(self.time_data):
                # 绘制原始信号（主Y轴）
                line1 = ax3_main.plot(self.time_data[view_start:view_end],
                                      self.signal_data[view_start:view_end],
                                      'b-', linewidth=2, label='原始信号')

                # 绘制导数（安全检查）
                if len(dy) >= view_end and len(d2y) >= view_end:
                    # 绘制一阶导数（副Y轴1）
                    line2 = ax3_der1.plot(self.time_data[view_start:view_end],
                                          dy[view_start:view_end],
                                          'r-', linewidth=0.5, label='一阶导数')
                    # 绘制二阶导数（副Y轴2）
                    line3 = ax3_der2.plot(self.time_data[view_start:view_end],
                                          d2y[view_start:view_end],
                                          'g-', linewidth=0.5, label='二阶导数')

            # 绘制零线
            ax3_der1.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
            ax3_der2.axhline(y=0, color='gray', linestyle='-', alpha=0.3)

            # 标记峰值（安全检查）
            if 0 <= peak_idx < len(self.time_data) and 0 <= peak_idx < len(self.signal_data):
                peak_marker = ax3_main.scatter(self.time_data[peak_idx], self.signal_data[peak_idx],
                                               color='darkred', s=150, marker='*', zorder=6,
                                               label=f'峰值(峰{peak_index + 1})')

            # 绘制边界线
            if 0 <= safe_left < len(self.time_data):
                left_line = ax3_main.axvline(x=self.time_data[safe_left], color='orange', linestyle='--',
                                             linewidth=1, label='左边界')
            if 0 <= safe_right < len(self.time_data):
                right_line = ax3_main.axvline(x=self.time_data[safe_right], color='orange', linestyle='--',
                                              linewidth=1, label='右边界')

            # 设置轴标签和颜色
            ax3_main.set_title('步骤3: 导数计算与边界识别（整个区域）', fontsize=16)
            ax3_main.set_xlabel('Elution Time (min)', fontsize=14)
            ax3_main.set_ylabel('Detector Response', fontsize=14, color='b')
            ax3_der1.set_ylabel('一阶导数', fontsize=14, color='r')
            ax3_der2.set_ylabel('二阶导数', fontsize=14, color='g')

            # 设置轴刻度颜色
            ax3_main.tick_params(axis='y', labelcolor='b')
            ax3_der1.tick_params(axis='y', labelcolor='r')
            ax3_der2.tick_params(axis='y', labelcolor='g')

            # 合并图例
            lines = line1 + line2 + line3
            labels = [line.get_label() for line in lines]

            # 添加峰值标记、边界线和填充区域到图例
            if 'peak_marker' in locals():
                lines.append(peak_marker)
                labels.append(peak_marker.get_label())
            if 'left_line' in locals():
                lines.append(left_line)
                labels.append(left_line.get_label())

            ax3_main.legend(lines, labels, fontsize=10, loc='best')

            ax3_main.grid(True, linestyle='--', alpha=0.7)

            # 图4: 最终峰区域识别结果
            ax4.plot(self.time_data, self.signal_data, 'b-', linewidth=2, label='原始信号')

            # 绘制基线
            baseline = self.get_bound_baseline(safe_left, safe_right)
            ax4.plot(self.time_data[safe_left:safe_right + 1], baseline, 'g-', linewidth=2, label='基线')

            # 高亮显示识别的峰区域（安全检查）
            if safe_left <= safe_right and safe_right < len(self.time_data):
                ax4.fill_between(
                    self.time_data[safe_left:safe_right + 1],
                    baseline,
                    self.signal_data[safe_left:safe_right + 1],
                    color='lightgreen', alpha=0.5, label='识别的峰区域'
                )

            # 标记边界（安全检查）
            if 0 <= safe_left < len(self.time_data):
                ax4.axvline(x=self.time_data[safe_left], color='red', linestyle='--',
                            linewidth=2, label='左边界')
            if 0 <= safe_right < len(self.time_data):
                ax4.axvline(x=self.time_data[safe_right], color='red', linestyle='--',
                            linewidth=2, label='右边界')

            # 标记当前分析的峰值（安全检查）
            if 0 <= peak_idx < len(self.time_data) and 0 <= peak_idx < len(self.signal_data):
                ax4.scatter(self.time_data[peak_idx], self.signal_data[peak_idx],
                            color='darkred', s=150, marker='*', zorder=6,
                            label=f'当前分析峰值(峰{peak_index + 1})')

            # 添加峰信息文本（安全检查）
            try:
                if 0 <= peak_idx < len(self.time_data) and 0 <= peak_idx < len(self.signal_data) and 0 <= safe_left < len(
                        self.time_data) and 0 <= safe_right < len(self.time_data):
                    peak_summary = self.get_peak_summary(peak_index, safe_left, safe_right)
                    ax4.text(0.02, 0.02, peak_summary, transform=ax4.transAxes, fontsize=12,
                             verticalalignment='bottom', bbox=dict(boxstyle='round',
                                                                   facecolor='wheat', alpha=0.5))
            except Exception as e:
                print(f"添加峰信息文本时出错: {e}")

            ax4.set_title('步骤4: 峰区域识别结果', fontsize=16)
            ax4.set_xlabel('Elution Time (min)', fontsize=14)
            ax4.set_ylabel('Detector Response', fontsize=14)
            ax4.legend(fontsize=12, loc='upper right')
            ax4.grid(True, linestyle='--', alpha=0.7)

            # 添加总标题和模式信息
            # 从类属性获取sample_name，如果没有则使用默认值
            sample_name = getattr(self, 'sample_name', 'GPC样品')
            if detect_mode == 'manual':
                fig.suptitle(
                    f'GPC数据峰值检测完整过程 - {sample_name} (手动模式: {manual_interval[0]:.2f}-{manual_interval[1]:.2f} min)',
                    fontsize=20, fontweight='bold')
            else:
                fig.suptitle(f'GPC数据峰值检测完整过程 - {sample_name} (自动模式)',
                             fontsize=20, fontweight='bold')
            fig.tight_layout(rect=[0, 0, 1, 0.97])
            # 处理输出目录
            if save_path is None:
                save_path = os.path.join(self.output_dir, f"{self.sample_name}_peak_detect.png")
            # 保存图像
            fig.tight_layout()
            fig.savefig(save_path, dpi=300, bbox_inches='tight')
        finally:
            plt.close(fig)
        logger.info(f"GPC数据峰值检测过程图已保存到 {save_path}")

    def get_peak_detect_plot(
            self,
            peak_index: int,
            detect_mode: str = 'auto',
            manual_interval: Optional[List[float]] = None
    ):
        """构建 Plotly 图表用于 Streamlit 展示峰值检测结果"""
        peaks = self.peaks_info['peaks']
        peak_idx = peaks[peak_index]

        if detect_mode == "manual":
            manual_left_time, manual_right_time = manual_interval
            # 将时间转换为对应的索引
            safe_left = np.searchsorted(self.time_data, manual_left_time)
            safe_right = np.searchsorted(self.time_data, manual_right_time)
        else:
            peaks_details = self.peaks_info['peaks_details']
            safe_left = peaks_details[peak_index]["left_bound"]
            safe_right = peaks_details[peak_index]["right_bound"]

        try:
            import plotly.graph_objects as go

            # 创建 Plotly 图形对象
            fig_plotly = go.Figure()

            # 1. 绘制原始信号
            fig_plotly.add_trace(go.Scatter(
                x=self.time_data, y=self.signal_data,
                mode='lines', name='原始信号',
                line=dict(color='blue', width=2)
            ))

            # 2. 绘制基线
            baseline = self.get_bound_baseline(safe_left, safe_right)
            fig_plotly.add_trace(go.Scatter(
                x=self.time_data[safe_left:safe_right + 1], y=baseline,
                mode='lines', name='基线',
                line=dict(color='green', width=2)
            ))

            # 3. 绘制填充的峰区域 (利用 fill='tonexty' 填充信号与基线之间)
            if safe_left <= safe_right:
                region_time = self.time_data[safe_left:safe_right + 1]
                region_signal = self.signal_data[safe_left:safe_right + 1]
                region_baseline = baseline

                # 绘制区域边界并填充
                fig_plotly.add_trace(go.Scatter(
                    x=np.concatenate([region_time, region_time[::-1]]),
                    y=np.concatenate([region_signal, region_baseline[::-1]]),
                    fill='toself',
                    fillcolor='rgba(144, 238, 144, 0.5)',  # lightgreen 0.5 alpha
                    line=dict(color='rgba(255,255,255,0)'),
                    hoverinfo='skip',
                    showlegend=True,
                    name='识别的峰区域'
                ))

            # 4. 绘制左右边界竖线
            for b_idx, b_name, b_color in [(safe_left, '左边界', 'red'), (safe_right, '右边界', 'red')]:
                fig_plotly.add_vline(
                    x=self.time_data[b_idx],
                    line_dash="dash",
                    line_color=b_color,
                    annotation_text=b_name
                )

            # 5. 标记当前峰值点
            fig_plotly.add_trace(go.Scatter(
                x=[self.time_data[peak_idx]],
                y=[self.signal_data[peak_idx]],
                mode='markers',
                marker=dict(color='darkred', size=12, symbol='star'),
                name=f'当前峰值(峰{peak_index + 1})'
            ))

            # 6. 添加信息文本框 (Annotation)
            peak_summary = self.get_peak_summary(peak_index, safe_left, safe_right)
            fig_plotly.add_annotation(
                xref="paper", yref="paper",
                x=0.02, y=0.05,
                text=peak_summary.replace('\n', '<br>'),
                showarrow=False,
                align="left",
                bgcolor="rgba(245, 222, 179, 0.7)",  # wheat color
                bordercolor="gray", borderwidth=1
            )

            # 设置布局
            fig_plotly.update_layout(
                title=f'峰区域识别结果 - 峰 {peak_index + 1}',
                xaxis_title='Elution Time (min)',
                yaxis_title='Detector Response',
                hovermode='x unified',
                template='plotly_white',
                legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99)
            )
        except Exception as plotly_e:
            logger.error(f"创建 Plotly 图表失败: {plotly_e}")
            return None
        return fig_plotly

    def get_bound_baseline(self, left_bound, right_bound):
        """基于峰边界两点构建积分计算基线"""
        # 峰计算基线
        mask = (self.time_data >= self.time_data[left_bound]) & (self.time_data <= self.time_data[right_bound])
        t_sliced = self.time_data[mask]
        s_sliced = self.signal_data[mask]
        # 线性基线扣除
        s_left, s_right = s_sliced[0], s_sliced[-1]
        t_left, t_right = t_sliced[0], t_sliced[-1]
        baseline = s_left + (s_right - s_left) * (t_sliced - t_left) / (t_right - t_left)
        return baseline

    def get_peak_summary(
            self,
            peak_index: int,
            left_bound: int,
            right_bound: int
    ):
        peak_times = self.peaks_info['peak_times']
        peak_heights = self.peaks_info['peak_heights']
        peak_time = peak_times[peak_index]
        peak_height = peak_heights[peak_index]

        left_time = self.time_data[left_bound]
        right_time = self.time_data[right_bound]
        peak_width = right_time - left_time
        peak_summary = f"峰位置: {peak_time:.2f} min\n" + \
                       f"峰高度: {peak_height:.2f}\n" + \
                       f"左边界: {left_time:.2f} min\n" + \
                       f"右边界: {right_time:.2f} min\n" + \
                       f"峰宽度: {peak_width:.2f} min"
        return peak_summary

    def calculate_cumulative_distribution(self, peak_index=0):
        """
        计算指定峰的累积分布数据
        :param peak_index: 峰的索引（0表示第一个检测到的峰）
        """
        M_i = self.molecular_info[peak_index]['M_i']
        h_i = self.molecular_info[peak_index]['h_i']

        # 1. 按照分子量从小到大排序（累积分布必须升序计算）
        sort_idx = np.argsort(M_i)
        M_sorted = M_i[sort_idx]
        h_sorted = h_i[sort_idx]
        log_M_sorted = np.log10(M_sorted)

        # 2. 归一化处理
        # 累积分布：信号的积分累加
        cum_w = np.cumsum(h_sorted) / np.sum(h_sorted) * 100

        # 微分分布：在Log轴上，通常对信号进行归一化，使曲线下方总面积为1或最大值为1
        # 这里采用最大值归一化，方便在同一个图上观察
        diff_w = h_sorted / np.max(h_sorted)

        return M_sorted, log_M_sorted, diff_w, cum_w

