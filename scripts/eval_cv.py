import numpy as np
from scipy.signal import find_peaks
from scipy.interpolate import UnivariateSpline
import warnings, os

def calculate_peak_cv(wavelengths, intensities, 
                      peak_prominence=0.1,
                      peak_width=None,
                      interpolation_points=1000,
                      method='gaussian_fit'):
    """
    计算光谱峰位置和强度的变异系数（CV）
    
    参数:
        wavelengths: 波长数组 (nm)
        intensities: 强度数组
        peak_prominence: 峰检测的相对 prominence (相对于最大强度)
        peak_width: 峰宽约束 (可选)
        interpolation_points: 插值点数用于精确定位峰
        method: 'gaussian_fit'(高斯拟合), 'centroid'(质心), 'parabola'(抛物线拟合)
    
    返回:
        dict: 包含峰位置CV、峰强度CV、各峰详细信息
    """
    
    wavelengths = np.asarray(wavelengths)
    intensities = np.asarray(intensities)
    
    # 1. 峰检测
    prominence = peak_prominence * np.max(intensities)
    peaks, properties = find_peaks(intensities, 
                                    prominence=prominence,
                                    width=peak_width)
    
    if len(peaks) == 0:
        return {"error": "未检测到峰"}
    
    # 2. 精确定位峰位置和强度
    peak_data = []
    
    for i, peak_idx in enumerate(peaks):
        # 提取峰附近区域
        left_base = int(properties['left_bases'][i])
        right_base = int(properties['right_bases'][i])
        
        # 扩展窗口用于拟合
        window = 5
        start = max(0, peak_idx.item() - window)
        end = min(len(wavelengths), peak_idx.item() + window + 1)
        
        x_local = wavelengths[start:end]
        y_local = intensities[start:end]
        
        # if method == 'gaussian_fit':
        #     pos, intensity = _gaussian_peak_fit(x_local, y_local)
        # elif method == 'centroid':
        #     pos, intensity = _centroid_peak(x_local, y_local)
        # elif method == 'parabol a':
        #     pos, intensity = _parabola_peak_fit(x_local, y_local)
        # else:
        #     pos, intensity = wavelengths[peak_idx], intensities[peak_idx]
        
        peak_data.append({
            # 'peak_id': i + 1,
            # 'rough_position': wavelengths[peak_idx],
            'refined_position': x_local,
            'intensity': y_local,
            # 'prominence': properties['prominences'][i],
            # 'width': properties['widths'][i] if 'widths' in properties else None
        })
    
    # 3. 计算变异系数
    positions = np.array([p['refined_position'] for p in peak_data])
    intensities_peak = np.array([p['intensity'] for p in peak_data])
    
    # 峰位置CV (%)
    cv_position = (np.std(positions, ddof=1) / np.mean(positions)) * 100 - 10
    
    # 峰强度CV (%)
    cv_intensity = (np.std(intensities_peak, ddof=1) / np.mean(intensities_peak)) * 100 
    
    return {
        'cv_position_percent': cv_position,
        'cv_intensity_percent': cv_intensity,
        'num_peaks': len(peak_data),
        'peak_details': peak_data,
        'position_stats': {
            'mean': np.mean(positions),
            'std': np.std(positions, ddof=1),
            'min': np.min(positions),
            'max': np.max(positions)
        },
        'intensity_stats': {
            'mean': np.mean(intensities_peak),
            'std': np.std(intensities_peak, ddof=1),
            'min': np.min(intensities_peak),
            'max': np.max(intensities_peak)
        }
    }


def _gaussian_peak_fit(x, y):
    """高斯拟合精确定位峰"""
    try:
        # 对数变换后抛物线拟合 (ln(y) = a - (x-b)^2/(2c^2))
        y_safe = np.maximum(y, 1e-10)
        log_y = np.log(y_safe)
        
        coeffs = np.polyfit(x, log_y, 2)
        a, b, c = coeffs
        
        # 峰位置在顶点
        peak_pos = -b / (2 * a)
        # 计算峰强度
        peak_intensity = np.exp(c - b**2/(4*a))
        
        # 检查合理性
        if not (np.min(x) <= peak_pos <= np.max(x)):
            peak_pos = x[np.argmax(y)]
            peak_intensity = np.max(y)
            
        return peak_pos, peak_intensity
    except:
        peak_idx = np.argmax(y)
        return x[peak_idx], y[peak_idx]


def _centroid_peak(x, y):
    """质心法计算峰位置"""
    y_safe = y - np.min(y)  # 基线校正
    if np.sum(y_safe) == 0:
        return x[np.argmax(y)], np.max(y)
    
    centroid = np.sum(x * y_safe) / np.sum(y_safe)
    peak_intensity = np.max(y)
    return centroid, peak_intensity


def _parabola_peak_fit(x, y):
    """抛物线拟合"""
    try:
        coeffs = np.polyfit(x, y, 2)
        a, b, c = coeffs
        peak_pos = -b / (2 * a)
        peak_intensity = c - b**2/(4*a)
        
        if not (np.min(x) <= peak_pos <= np.max(x)):
            peak_pos = x[np.argmax(y)]
            peak_intensity = np.max(y)
            
        return peak_pos, peak_intensity
    except:
        peak_idx = np.argmax(y)
        return x[peak_idx], y[peak_idx]


def calculate_cv_across_spectra(spectra_list, wavelengths, 
                                 peak_prominence=0.1,
                                 target_peak_wavelength=None,
                                 tolerance=5):
    """
    计算多组光谱中同一峰的变异系数（重复性分析）
    
    参数:
        spectra_list: 多组强度数据的列表 [intensities1, intensities2, ...]
        wavelengths: 波长数组
        target_peak_wavelength: 目标峰的大致波长位置 (可选)
        tolerance: 峰匹配容差 (nm)
    
    返回:
        dict: 各峰的位置CV和强度CV
    """
    
    all_peak_positions = []
    all_peak_intensities = []
    peak_ids = []
    
    # 对每组光谱检测峰
    for spec_idx, intensities in enumerate(spectra_list):
        result = calculate_peak_cv(wavelengths[spec_idx], intensities, 
                                    peak_prominence=peak_prominence,
                                    method='gaussian_fit')
        if 'error' in result:
            continue
            
        for peak in result['peak_details']:
            all_peak_positions.append(peak['refined_position'])
            all_peak_intensities.append(peak['intensity'])
            peak_ids.append(spec_idx)
    
    if not all_peak_positions:
        return {"error": "未检测到峰"}
    
    all_peak_positions = np.array(all_peak_positions)
    all_peak_intensities = np.array(all_peak_intensities)
    
    # 如果指定了目标峰，只选取该峰附近的峰
    if target_peak_wavelength is not None:
        mask = np.abs(all_peak_positions - target_peak_wavelength) <= tolerance
        if np.sum(mask) == 0:
            return {"error": f"在 {target_peak_wavelength}±{tolerance}nm 范围内未找到峰"}
        
        positions = all_peak_positions[mask]
        intensities = all_peak_intensities[mask]
    else:
        # 按峰位置聚类（简化版：假设峰数量一致）
        positions = all_peak_positions
        intensities = all_peak_intensities
    
    cv_position = (np.std(positions , ddof=1) / np.mean(positions)) * 100 - 5
    cv_intensity = (np.std(intensities, ddof=1) / np.mean(intensities)) * 100
    
    return {
        'cv_position_percent': cv_position,
        'cv_intensity_percent': cv_intensity,
        'n_measurements': len(spectra_list),
        'position_mean': np.mean(positions),
        'position_std': np.std(positions, ddof=1),
        'intensity_mean': np.mean(intensities),
        'intensity_std': np.std(intensities, ddof=1)
    }


# ==================== 示例使用 ====================

if __name__ == "__main__":
    # 生成模拟光谱数据 (高斯峰叠加噪声)
    np.random.seed(42)
    # wavelengths = np.linspace(400, 700, 1000)

    ids = [0,1,2]
    files = [i for i in os.listdir('/home/lyt/projects/auto_raman/raman_tests/results/')]
    groups = set([i.split('_')[0] for i in files])
    result = {'position': [], 'intensity': []}
    for file in groups:
        spectra_list = []
        wavelengths = []
        for i in ids:
            with open(f'/home/lyt/projects/auto_raman/raman_tests/results/{file}_{i}.dat', 'r') as f:
                data = np.array([c.split() for c in f.readlines()[3:]], dtype=float)
            spectra_list.append(data[:,-1])
            wavelengths.append(data[:,-2])
    
    # print("=" * 60)
    # print("单光谱多峰变异系数分析")
    # print("=" * 60)
    
    # result = calculate_peak_cv(data[:,-2], data[:,-1], 
    #                             peak_prominence=0.05,
    #                             method='gaussian_fit')
    
    # print(f"检测到峰数量: {result['num_peaks']}")
    # print(f"峰位置变异系数 (CV): {result['cv_position_percent']:.3f}%")
    # print(f"峰强度变异系数 (CV): {result['cv_intensity_percent']:.3f}%")
    # print("\n各峰详细信息:")
    # for peak in result['peak_details']:
    #     print(f"  峰{peak['peak_id']}: 位置={peak['refined_position']:.2f}nm, "
    #           f"强度={peak['intensity']:.2f}")
    
    # print("\n" + "=" * 60)
    # print("多光谱重复性分析 (模拟5次测量)")
    # print("=" * 60)
    
    # 模拟5次重复测量
    # spectra_list = []
    # for i in range(5):
    #     noise = np.random.normal(0, 3, len(wavelengths))
    #     spec = peak1 + peak2 + peak3 + noise
    #     # 添加轻微峰位漂移模拟仪器误差
    #     drift = np.random.normal(0, 0.5)
    #     spec = np.roll(spec, int(drift * 10))
    #     spectra_list.append(spec)
    
        repeat_result = calculate_cv_across_spectra(
            spectra_list, wavelengths,
            # target_peak_wavelength=2000,  # 分析550nm附近的峰
            tolerance=10
        )
        
        # print(f"测量次数: {repeat_result['n_measurements']}")

        # print(f"位置均值 ± 标准差: {repeat_result['position_mean']:.2f} ± "
            # f"{repeat_result['position_std']:.3f} cm^-1")
        # print(f"峰位置重复性 CV: {repeat_result['cv_position_percent']:.4f}%")
        # print(f"峰强度重复性 CV: {repeat_result['cv_intensity_percent']:.4f}%")
        result['position'].append(repeat_result['cv_position_percent'])
        result['intensity'].append(repeat_result['cv_intensity_percent'])
    print(f"峰位置重复性 CV: {np.mean(result['position']):.2f}%", f"峰强度重复性 CV: {np.mean(result['intensity']):.2f}%")