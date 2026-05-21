import os
import warnings

from config import setup_matplotlib_font

setup_matplotlib_font()
import matplotlib.pyplot as plt
import nmrglue as ng
import numpy as np
import scipy.integrate as spi
from scipy.optimize import curve_fit

from analysis.nmr.peak_detection import calculate_baseline
from app.core.logging import get_logger

logger = get_logger("spec_agent.analysis.nmr")

# 过滤无关警告
warnings.filterwarnings("ignore", category=UserWarning, module="nmrglue.fileio.bruker")
warnings.filterwarnings("ignore", category=RuntimeWarning, message="Casting complex values to real discards the imaginary part")
warnings.filterwarnings("ignore", message=".*tight_layout.*", category=UserWarning)


def ensure_nmr_xaxis_direction(ax, ppm_scale):
    """统一为 NMR 常见的左高右低显示。"""
    if ax is None:
        return
    if not ax.xaxis_inverted():
        ax.invert_xaxis()


def voigt_profile(x, amp, center, sigma, gamma):
    """Voigt 峰形函数：高斯与洛伦兹的卷积"""
    # 高斯部分
    gaussian = np.exp(-(x - center)**2 / (2 * sigma**2))
    # 洛伦兹部分
    lorentzian = gamma**2 / ((x - center)**2 + gamma**2)
    # 归一化
    return amp * gaussian * lorentzian

def integrate_region(data, ppm_scale, ppm_start, ppm_end, method='trapezoid'):
    """积分指定 ppm 范围内的信号

    积分前会先扣除基线，并对低于基线的部分取 0（即不计算负积分）
    """
    if ppm_start < ppm_end:
        ppm_start, ppm_end = ppm_end, ppm_start
    mask = (ppm_scale >= ppm_end) & (ppm_scale <= ppm_start)
    # 处理掩码为空的情况
    if not np.any(mask):
        logger.warning("积分范围 [%s-%s] ppm 内没有数据点", ppm_end, ppm_start)
        return 0.0

    # 获取积分区域内的数据
    x_data = ppm_scale[mask]
    y_data = data[mask]

    # 计算基线（使用全部数据计算基线，然后提取对应区域的基线）
    baseline = calculate_baseline(data)
    baseline_in_region = baseline[mask]

    # 扣除基线，并对低于基线的部分取 0
    y_corrected = y_data - baseline_in_region
    y_corrected = np.maximum(y_corrected, 0)  # 将负值设为 0

    if method == 'trapezoid':
        # 使用梯形积分法，取绝对值是因为在核磁共振（NMR）中，ppm_scale 从大到小（例如 $10 \to 0$）是标准习惯
        return np.abs(spi.trapezoid(y_corrected, x_data))
    elif method == 'voigt':
        # 使用 Voigt 拟合峰形积分法

        if len(x_data) < 5:
            # 数据点太少，无法拟合，使用梯形积分
            return spi.trapezoid(y_corrected, x_data)

        # 初始参数估计
        center_guess = (ppm_start + ppm_end) / 2
        amp_guess = np.max(y_corrected)
        sigma_guess = (ppm_start - ppm_end) / 4
        gamma_guess = sigma_guess

        try:
            # 拟合 Voigt 峰形
            popt, _ = curve_fit(
                voigt_profile,
                x_data,
                y_corrected,
                p0=[amp_guess, center_guess, sigma_guess, gamma_guess],
                bounds=([0, ppm_end, 0, 0], [amp_guess*2, ppm_start, (ppm_start-ppm_end), (ppm_start-ppm_end)])
            )

            # 计算拟合曲线的积分
            amp, center, sigma, gamma = popt
            # 使用数值积分计算 Voigt 峰形的积分
            integral = spi.quad(voigt_profile, ppm_end, ppm_start, args=(amp, center, sigma, gamma))[0]
            return integral
        except:
            # 拟合失败，使用梯形积分
            return spi.trapezoid(y_corrected, x_data)
    else:
        # 未知方法，使用梯形积分
        return spi.trapezoid(y_corrected, x_data)


def extract_metadata_from_dic(dic):
    """从 Bruker dic 中提取溶剂、核信息和谱仪频率"""
    metadata = {}
    if 'acqus' in dic:
        metadata['solvent'] = dic['acqus'].get('SOLVENT', '<未知溶剂>')
        metadata['nucleus'] = dic['acqus'].get('NUC1', '<未知核>')
        # 谱仪基础频率 (MHz)，用于 ppm → Hz 换算
        sfo1 = dic['acqus'].get('SFO1')
        if sfo1 is not None:
            metadata['sfo1'] = round(float(sfo1), 2)
        sw_h = dic['acqus'].get('SW_h')
        if sw_h is not None:
            metadata['sw_h'] = round(float(sw_h), 2)
    else:
        metadata['solvent'] = '<未知溶剂>'
        metadata['nucleus'] = '<未知核>'
    return metadata

def find_tms_offset(data, ppm_scale):
    """在 -0.5 到 0.5 ppm 范围内找寻 TMS 峰，计算需要的偏移量"""
    mask = (ppm_scale >= -0.5) & (ppm_scale <= 0.5)
    if not np.any(mask):
        return 0.0
    
    # 截取该范围的数据
    region_data = data[mask]
    region_ppm = ppm_scale[mask]
    
    # 获取最高点
    max_idx = np.argmax(region_data)
    peak_val = region_data[max_idx]
    
    # 如果该峰的高度不足全谱最大值的 1%，可能不是有效的 TMS，不进行校正
    if peak_val < np.max(data) * 0.01:
        return 0.0
        
    tms_ppm = region_ppm[max_idx]
    # 需要满足： tms_ppm + offset = 0.0 => offset = -tms_ppm
    return float(-tms_ppm)


def process_nmr_data(bruker_subdir):
    """处理 NMR 数据，返回处理后的数据、ppm 标尺、处理步骤、元数据（包括TMS校正）"""
    # 读取 Bruker 数据
    dic, data = ng.bruker.read(dir=bruker_subdir)

    # 创建字典保存各处理步骤的数据
    processing_steps = {
        '原始数据': data.copy()  # 保存原始数据
    }

    # 数据处理流程
    data = ng.bruker.remove_digital_filter(dic, data)  # 移除数字滤波器
    processing_steps['移除数字滤波器'] = data.copy()

    data = ng.proc_base.zf_size(data, 32768)   # 零填充到 32768 点
    processing_steps['零填充'] = data.copy()

    data = ng.proc_base.fft(data)  # 快速傅里叶变换
    processing_steps['傅里叶变换'] = data.copy()

    data = ng.process.proc_autophase.autops(data, 'acme')  # 自动相位校正
    processing_steps['相位校正'] = data.copy()

    data = ng.process.proc_bl.baseline_corrector(data)  # 基线校正
    processing_steps['基线校正'] = data.copy()

    data = ng.proc_base.di(data)  # 丢弃虚部
    processing_steps['最终处理结果'] = data.copy()

    # 计算化学位移范围
    ppm_scale = calculate_ppm_scale(dic)
    
    # 提取 meta data
    metadata = extract_metadata_from_dic(dic)
    tms_offset = find_tms_offset(data, ppm_scale)
    metadata['tms_offset'] = tms_offset

    return data, ppm_scale, processing_steps, metadata

def calculate_ppm_scale(bruker_parameters: dict):
    """计算 ppm 范围"""
    sw_h = bruker_parameters["acqus"]["SW_h"]  # 扫描宽度（Hz）
    sfo1 = bruker_parameters["acqus"]["SFO1"]  # 中心频率（Hz）
    o1 = bruker_parameters["acqus"]["O1"]  # 偏移频率（Hz）
    sw_ppm = sw_h / sfo1  # 扫描宽度（ppm）
    offset_ppm = o1 / sfo1  # 偏移频率（ppm）
    F1 = offset_ppm + sw_ppm / 2  # 上边界（ppm）
    F2 = offset_ppm - sw_ppm / 2  # 下边界（ppm）

    # 构建 ppm 标尺
    ppm_scale = np.linspace(F1, F2, 32768)[::-1]
    return ppm_scale


def get_nmr_sample_data(sample_path: str, index: int = 0):
    """获取核磁样品的后处理数据

    Args:
        sample_path: 样品根目录路径
        index: 选取样品目录下的第几个文件夹（从0开始）

    Returns:
        data: NMR 数据数组
        ppm_scale: 化学位移标尺
        processing_steps: 流程中间数据
        metadata: 提取到的核信息、溶剂信息及TMS位移校正字典
    """
    # 获取所有子目录并排序
    subdirs = [os.path.join(sample_path, d) for d in os.listdir(sample_path)
               if os.path.isdir(os.path.join(sample_path, d))]
    subdirs.sort()

    # 边界检查
    if index < 0 or index >= len(subdirs):
        logger.warning("index %d 超出范围，样品目录下共有 %d 个文件夹", index, len(subdirs))
        raise IndexError(f"index {index} 超出范围，样品目录下共有 {len(subdirs)} 个文件夹")

    # 选取第 index 个文件夹作为 Bruker 数据目录
    bruker_subdir = subdirs[index]

    # 直接使用 Bruker 软件处理后的数据
    pdata_path = os.path.join(bruker_subdir, 'pdata', "1")
    if os.path.exists(pdata_path):
        data, ppm_scale, metadata = process_pdata_directly(pdata_path)
        processing_steps = {'最终处理结果': data.copy()}
    else:
        data, ppm_scale, processing_steps, metadata = process_nmr_data(bruker_subdir)
    return data, ppm_scale, processing_steps, metadata


def process_pdata_directly(pdata_path):
    """
    直接读取 Bruker 软件处理好的 (pdata) 数据，并将其重采样至指定长度
    """
    # 1. 直接读取处理后的实部数据 (1r)
    pdic, pdata = ng.bruker.read_pdata(pdata_path)

    # 2. 生成原始的化学位移 (ppm) 轴
    udic = ng.bruker.guess_udic(pdic, pdata)
    uc = ng.fileiobase.uc_from_udic(udic)
    ppm_scale = uc.ppm_scale()
    
    # 尝试读取元数据
    bruker_dir = os.path.dirname(os.path.dirname(pdata_path))
    try:
        dic, _ = ng.bruker.read(dir=bruker_dir)
        metadata = extract_metadata_from_dic(dic)
    except Exception:
        metadata = {'solvent': '<未知溶剂>', 'nucleus': '<未知核>'}
        
    tms_offset = find_tms_offset(pdata, ppm_scale)
    metadata['tms_offset'] = tms_offset
    
    return pdata, ppm_scale, metadata

def plot_nmr_spectrum(ppm_scale, data, sample_name, output_dir):
    """绘制并保存 NMR 谱图"""
    plt.figure(figsize=(12, 6))
    plt.plot(ppm_scale, data, 'b-', linewidth=0.8)
    ensure_nmr_xaxis_direction(plt.gca(), ppm_scale)
    plt.xlabel('δ (ppm)', fontsize=12)
    plt.ylabel('Intensity', fontsize=12)
    plt.title(f'NMR Spectrum - {sample_name}', fontsize=14)
    plt.grid(linestyle=':', alpha=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'{sample_name}.png'), dpi=150)
    plt.close()

def plot_processing_steps(ppm_scale, processing_steps, sample_name, output_dir, integration_regions=None, normalized_results=None):
    """绘制 NMR 积分区域、归一化值对比和内标峰详细视图"""
    # 创建子图（1 行 3 列布局）
    fig, axes = plt.subplots(1, 3, figsize=(18, 6),
                           gridspec_kw={'hspace': 0.3, 'wspace': 0.3, 'top': 0.85})

    # 绘制内标定量相关的可视化
    if integration_regions and normalized_results:
        final_data = np.abs(processing_steps.get('最终处理结果', processing_steps.get(list(processing_steps.keys())[-1])))

        # 1. 绘制积分区域标记
        ax = axes[0]
        ax.plot(ppm_scale, final_data, color='black', linewidth=0.8)
        ensure_nmr_xaxis_direction(ax, ppm_scale)

        # 标记积分区域
        for region in integration_regions:
            # 兼容新旧格式
            if len(region) == 4:
                name, start, end, peak_position = region
            else:
                name, start, end = region
            # 找到 ppm 范围内的索引
            mask = (ppm_scale >= min(start, end)) & (ppm_scale <= max(start, end))
            # 填充积分区域
            ax.fill_between(ppm_scale[mask], 0, final_data[mask], alpha=0.3,
                           label=f'{name}')
            # 在区域中心显示名称
            center_ppm = (start + end) / 2
            max_height = np.max(final_data[mask]) * 0.8
            ax.text(center_ppm, max_height, name, ha='center', va='center',
                    bbox=dict(facecolor='white', alpha=0.7))

        ax.set_xlabel('δ (ppm)', fontsize=16)
        ax.set_ylabel('强度', fontsize=16)
        ax.set_title('积分区域标记', fontsize=18)
        ax.grid(linestyle=':', alpha=0.5)

        # 2. 绘制归一化值对比图
        ax = axes[1]
        regions = [r[0] if len(r) < 4 else r[0] for r in integration_regions]
        x = np.arange(len(regions))
        width = 0.7

        # 获取归一化结果
        normalized_values = [normalized_results.get(r, 0) for r in regions]

        # 绘制归一化后的值
        bars = ax.bar(x, normalized_values, width, color='orange')

        # 为每个柱子添加数值标签
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                    f'{height:.2f}', ha='center', va='bottom', fontsize=12)

        ax.set_ylabel('归一化积分值', fontsize=16)
        ax.set_title('归一化值对比', fontsize=18)
        ax.set_xticks(x)
        ax.set_xticklabels(regions, rotation=45, ha='right')
        ax.grid(axis='y', linestyle=':', alpha=0.5)

        # 自动调整 y 轴范围
        if normalized_values:
            max_value = max(normalized_values)
            ax.set_ylim(0, max_value * 1.2)

        # 3. 绘制内标峰详细视图
        ax = axes[2]

        # 放大显示内标峰区域
        if len(integration_regions[0]) == 4:
            standard_name, standard_min, standard_end, _ = integration_regions[0]
        else:
            standard_name, standard_min, standard_end = integration_regions[0]
        mask = (ppm_scale >= standard_min) & (ppm_scale <= standard_end)
        ax.plot(ppm_scale[mask], final_data[mask], color='red', linewidth=1.2)

        # 填充内标峰区域
        ax.fill_between(ppm_scale[mask], 0, final_data[mask], alpha=0.3, color='red')

        # 计算内标峰的积分值
        internal_standard = processing_steps.get('积分结果', {}).get(standard_name, 0)
        ax.text((standard_min + standard_end) / 2, np.max(final_data[mask]) * 0.5,
                f'内标峰积分值：{internal_standard:.2f}',
                ha='center', va='center',
                bbox=dict(facecolor='white', alpha=0.7))

        ensure_nmr_xaxis_direction(ax, ppm_scale)
        ax.set_xlabel('δ (ppm)', fontsize=16)
        ax.set_ylabel('强度', fontsize=16)
        ax.set_title(f'内标峰详细视图', fontsize=18)
        ax.grid(linestyle=':', alpha=0.5)

    # 添加总标题
    fig.suptitle(f'NMR 数据积分与定量分析 - {sample_name}', fontsize=20, y=0.98)

    # 保存图像
    plt.savefig(os.path.join(output_dir, f'{sample_name}_processing_steps.png'), dpi=200, bbox_inches='tight')
    plt.close()  # 关闭图像以释放资源


def plot_peak_detection_overview(ppm_scale, data, sample_name, output_dir, detected_peaks=None,
                                 integration_regions=None, multiplet_results=None,
                                 detection_range=None):
    """绘制峰检测总览图与积分区域图。

    Args:
        ppm_scale: 化学位移数组。
        data: 峰检测使用的谱图数据。
        sample_name: 样品名称。
        output_dir: 图像输出目录。
        detected_peaks: 检测到的峰列表。
        integration_regions: 积分区域列表。
        multiplet_results: 多重峰分析结果列表。
        detection_range: 检测范围。
    """
    abs_data = np.abs(data)
    detected_peaks = detected_peaks or []
    integration_regions = integration_regions or []
    multiplet_results = multiplet_results or []

    fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharex=True,
                             gridspec_kw={'hspace': 0.18})

    peak_ax = axes[0]
    peak_ax.plot(ppm_scale, abs_data, color='black', linewidth=0.9)
    peak_ax.set_ylabel('强度', fontsize=12)
    peak_ax.set_title(f'峰检测结果 - {sample_name}', fontsize=14)
    peak_ax.grid(linestyle=':', alpha=0.5)

    if detection_range is not None:
        range_min, range_max = min(detection_range), max(detection_range)
        peak_ax.axvspan(range_min, range_max, color='#cfe5ff', alpha=0.25, label='检测范围')

    for index, peak in enumerate(detected_peaks, start=1):
        ppm, height, _width = peak
        peak_ax.axvline(ppm, color='#2f7ed8', linestyle='--', linewidth=0.8, alpha=0.8)
        peak_ax.scatter([ppm], [height], color='#d14a61', s=18, zorder=3)
        peak_ax.text(ppm, height, f'{index}', fontsize=8, ha='center', va='bottom')

    for mp in multiplet_results:
        peak_ax.axvspan(min(mp.region_end, mp.region_start), max(mp.region_end, mp.region_start),
                        color='#8bd3c7', alpha=0.18)
        peak_ax.text(mp.center_ppm, np.max(abs_data) * 0.92, mp.to_display_str(),
                     fontsize=8, ha='center', va='top', rotation=0,
                     bbox=dict(facecolor='white', alpha=0.65, edgecolor='none'))

    region_ax = axes[1]
    region_ax.plot(ppm_scale, abs_data, color='black', linewidth=0.9)
    region_ax.set_xlabel('δ (ppm)', fontsize=12)
    region_ax.set_ylabel('强度', fontsize=12)
    region_ax.set_title(f'积分区域结果 - {sample_name}', fontsize=14)
    region_ax.grid(linestyle=':', alpha=0.5)

    for region in integration_regions:
        if len(region) == 4:
            name, start, end, peak_position = region
        else:
            name, start, end = region
            peak_position = (start + end) / 2
        left, right = min(start, end), max(start, end)
        mask = (ppm_scale >= left) & (ppm_scale <= right)
        if np.any(mask):
            region_ax.fill_between(ppm_scale[mask], 0, abs_data[mask], alpha=0.28, color='#f6bd60')
            region_ax.text(peak_position, np.max(abs_data[mask]) * 0.82, name,
                           fontsize=8, ha='center', va='center',
                           bbox=dict(facecolor='white', alpha=0.7, edgecolor='none'))

    # 该图上下子图共享 x 轴，只能统一反序一次，避免重复翻转回正。
    ensure_nmr_xaxis_direction(region_ax, ppm_scale)

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, f'{sample_name}_peak_detection_overview.png'), dpi=180, bbox_inches='tight')
    plt.close(fig)
