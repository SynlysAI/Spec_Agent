import json
import logging
import os
from typing import Dict, List, Callable, Any

import numpy as np

from config import setup_logging, GLOBAL_CONFIG

# 配置日志记录
setup_logging(logger_name="GPCCalibrationCurve")
logger = logging.getLogger("GPCCalibrationCurve")

class GPCCalibrationCurve:
    """GPC校准曲线类，根据仪器特性曲线名称返回calibration_curve函数"""
    
    def __init__(self):
        """初始化GPC校准曲线类"""
        self.coefficients = None
        self.fit_order = 5  # 默认使用5阶多项式拟合
    
    def get_calibration_curve(self, curve_name: str) -> Callable[[float], float]:
        """
        根据仪器特性曲线名称获取calibration_curve函数
        
        参数:
        curve_name: 仪器特性曲线名称
        
        返回:
        Callable[[float], float]: calibration_curve函数，输入保留时间，输出log(M)
        """
        try:
            logger.info(f"获取仪器特性曲线: {curve_name}")
            
            # 构建JSON文件路径
            calibration_dir = GLOBAL_CONFIG["data_storage"]["calibration_curves"]
            json_path = os.path.join(calibration_dir, f"{curve_name}.json")
            logger.info(f"读取JSON文件: {json_path}")
            
            # 读取JSON文件
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 提取校准表数据
            calibration_table = data.get("calibration_table", [])
            if not calibration_table:
                logger.error("JSON文件中未找到校准表数据")
                return lambda t: -1.0
            
            # 分离保留时间和分子量
            retention_times = [row["retention_time"] for row in calibration_table]
            molecular_weights = [row["molecular_weight"] for row in calibration_table]
            
            logger.info(f"提取到 {len(retention_times)} 个数据点")
            logger.info(f"保留时间: {retention_times}")
            logger.info(f"分子量: {molecular_weights}")
            
            # 拟合校准曲线
            coefficients = self._fit_calibration_curve(retention_times, molecular_weights)
            if coefficients is None:
                logger.error("拟合校准曲线失败")
                return lambda t: -1.0
            
            # 保存系数
            self.coefficients = coefficients
            
            # 返回calibration_curve函数
            def calibration_curve(T: float) -> float:
                """
                GPC校正曲线函数：根据保留时间T计算log(M)
                
                参数:
                T: 保留时间（分钟）
                
                返回:
                float: 计算得到的log(M)值
                """
                return np.polyval(coefficients, T)
            
            logger.info("成功创建calibration_curve函数")
            return calibration_curve
        except Exception as e:
            logger.error(f"获取calibration_curve函数失败: {str(e)}")
            return lambda t: -1.0

    def get_calibration_curve_from_path(self, json_path: str) -> Callable[[float], float]:
        """
        从任意 JSON 文件路径加载校准曲线（与 data/calibration_curves 下按名称加载等价）。

        参数:
            json_path: 校准表 JSON 文件的绝对或相对路径。

        返回:
            Callable[[float], float]: calibration_curve 函数，输入保留时间，输出 log(M)。
        """
        try:
            json_path = os.path.abspath(json_path)
            logger.info(f"从路径加载仪器特性曲线: {json_path}")
            if not os.path.isfile(json_path):
                logger.error(f"校准曲线文件不存在: {json_path}")
                return lambda t: -1.0

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            calibration_table = data.get("calibration_table", [])
            if not calibration_table:
                logger.error("JSON 文件中未找到校准表数据")
                return lambda t: -1.0

            func = self._calibration_func_from_table_rows(calibration_table)
            logger.info("成功从自定义路径创建 calibration_curve 函数")
            return func
        except Exception as e:
            logger.error(f"从路径加载 calibration_curve 失败: {str(e)}")
            return lambda t: -1.0

    def _calibration_func_from_table_rows(
        self, calibration_table: List[Dict[str, Any]]
    ) -> Callable[[float], float]:
        """由 ``calibration_table`` 行列表拟合并返回 log(M)=f(RT) 的校准函数。"""
        if not calibration_table:
            logger.error("校准表为空")
            return lambda t: -1.0
        retention_times = [row["retention_time"] for row in calibration_table]
        molecular_weights = [row["molecular_weight"] for row in calibration_table]
        coefficients = self._fit_calibration_curve(retention_times, molecular_weights)
        if coefficients is None:
            return lambda t: -1.0
        self.coefficients = coefficients

        def calibration_curve(T: float) -> float:
            return np.polyval(coefficients, T)

        return calibration_curve

    def get_calibration_curve_from_pdf(self, pdf_path: str) -> Callable[[float], float]:
        """
        从 GPC 校准报告 PDF 中提取校正表并拟合校准曲线。

        参数:
            pdf_path: PDF 文件路径。

        返回:
            Callable[[float], float]: 输入保留时间，输出 log(M)。
        """
        try:
            from analysis.gpc.tools.gpc_pdf_processor import GPCPDFProcessor

            pdf_path = os.path.abspath(pdf_path)
            logger.info(f"从 PDF 加载仪器特性曲线: {pdf_path}")
            if not os.path.isfile(pdf_path):
                logger.error(f"PDF 文件不存在: {pdf_path}")
                return lambda t: -1.0

            with GPCPDFProcessor() as proc:
                data = proc.extract_gpc_calibration_table(pdf_path)
            if not data:
                logger.error("未能从 PDF 提取校准数据")
                return lambda t: -1.0
            calibration_table = data.get("calibration_table", [])
            return self._calibration_func_from_table_rows(calibration_table)
        except Exception as e:
            logger.error(f"从 PDF 加载 calibration_curve 失败: {str(e)}")
            return lambda t: -1.0

    def get_calibration_curve_from_file(self, file_path: str) -> Callable[[float], float]:
        """
        根据扩展名加载校准曲线：``.json`` 直接读表；``.pdf`` 先解析再拟合。

        参数:
            file_path: ``.json`` 或 ``.pdf`` 的绝对/相对路径。

        返回:
            Callable[[float], float]: 输入保留时间，输出 log(M)。
        """
        if not file_path or not os.path.isfile(file_path):
            logger.error(f"校准文件不存在: {file_path}")
            return lambda t: -1.0
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".json":
            return self.get_calibration_curve_from_path(file_path)
        if ext == ".pdf":
            return self.get_calibration_curve_from_pdf(file_path)
        logger.error(f"不支持的校准文件类型（仅 .json / .pdf）: {file_path}")
        return lambda t: -1.0

    def _fit_calibration_curve(self, retention_times: List[float], molecular_weights: List[float]) -> np.ndarray:
        """
        拟合GPC校准曲线（内部方法）
        
        参数:
        retention_times: 保留时间列表（分钟）
        molecular_weights: 分子量列表（道尔顿）
        
        返回:
        np.ndarray: 拟合系数数组
        """
        try:
            logger.info(f"开始拟合GPC校准曲线，拟合阶数: {self.fit_order}")
            
            # 确保输入数据长度一致
            if len(retention_times) != len(molecular_weights):
                logger.error("保留时间和分子量数据长度不一致")
                return None
            
            if len(retention_times) < self.fit_order + 1:
                logger.error(f"数据点数量不足，需要至少 {self.fit_order + 1} 个数据点")
                return None
            
            # 对分子量取对数（以10为底）
            log_molecular_weights = np.log10(molecular_weights)
            
            # 使用多项式拟合log(M)与保留时间T的关系
            coefficients = np.polyfit(retention_times, log_molecular_weights, self.fit_order)
            
            logger.info("GPC校准曲线拟合完成")
            logger.info(f"拟合系数: {coefficients}")
            return coefficients
        except Exception as e:
            logger.error(f"拟合GPC校准曲线失败: {str(e)}")
            return None

# 示例用法
if __name__ == "__main__":
    print("=== GPC校准曲线测试 ===")
    
    # 初始化
    calibration = GPCCalibrationCurve()
    print("✓ 初始化成功")
    
    # 测试获取calibration_curve函数
    # 请根据实际情况修改curve_name
    curve_name = "GPC_03_20250411_Cal002_Copoly_THF_mix"
    cal_func = calibration.get_calibration_curve(curve_name)
    
    if cal_func is not None:
        print(f"✓ 成功获取calibration_curve函数")
        
        # 测试函数调用
        test_rt = 15.0
        log_mw = cal_func(test_rt)
        mw = 10 ** log_mw
        print(f"✓ 保留时间 {test_rt} 分钟对应的log(M): {log_mw:.4f}")
        print(f"✓ 保留时间 {test_rt} 分钟对应的分子量: {mw:.2f} 道尔顿")
    
    print("\n=== 测试完成 ===")
