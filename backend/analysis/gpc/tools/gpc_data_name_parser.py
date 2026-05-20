import logging
import os
import re
from typing import Dict, Any, Optional, List

from config import setup_logging, GLOBAL_CONFIG

# 确保项目根目录被添加到sys.path中

# 配置日志记录
setup_logging(logger_name="GPCDataNameParser")
logger = logging.getLogger("GPCDataNameParser")

class GPCDataNameParser:
    """GPC数据名称解析器"""
    
    def __init__(self):
        """初始化GPC数据名称解析器"""
        # 仪器编号正则：支持带连字符的编号，如 GPC_01 或 GPC_01-2279
        _instrument = r"GPC_\d+(?:-\d+)?"

        # 仪器特性曲线编码正则表达式
        # 完整格式：GPC_01_20241121_Cal001_PS_THF
        # 短格式：GPC_03_20240920_Cal001（无样品和溶剂信息）
        # 支持：带连字符编号、中文字符
        self.curve_pattern = re.compile(
            rf"^({_instrument})_(\d{{8}})_(Cal\d{{3}})(?:_([^_]+))?(?:_([^_]+))?$"
        )

        # 原始数据编码正则表达式
        # 完整格式：GPC_01_20241121-1_Cal001_(PS,0.2mg/ml,6000)_THF_pure
        # 简化格式（无样品信息）：GPC_01-2279_20260518-1_Cal002_四氢呋喃_pure4904
        # 样品信息为可选字段
        self.data_pattern = re.compile(
            rf"^({_instrument})_(\d{{8}}-\d+)_(Cal\d{{3}})(?:_([^_]+))?_([^_]+)_([^_]+)$"
        )

        # 简化的数据文件名正则表达式（用于匹配可能的变体）
        self.simple_data_pattern = re.compile(rf"^({_instrument})_(.+)$")

    
    def parse_curve_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        解析仪器特性曲线文件名
        
        参数:
        filename: 仪器特性曲线文件名（不包含路径）
        
        返回:
        Optional[Dict[str, Any]]: 解析结果字典，解析失败返回None
        """
        try:
            logger.info(f"开始解析仪器特性曲线文件名: {filename}")
            
            # 移除文件扩展名
            base_name = os.path.splitext(filename)[0]
            
            # 匹配正则表达式
            match = self.curve_pattern.match(base_name)
            if not match:
                logger.warning(f"仪器特性曲线文件名格式不匹配: {filename}")
                return None
            
            # 提取各部分信息
            instrument_info = match.group(1)
            test_date = match.group(2)
            curve_number = match.group(3)
            sample_info = match.group(4)  # 可选字段，可能为None
            solvent_info = match.group(5)  # 可选字段，可能为None

            # 解析仪器类型和编号
            instrument_parts = instrument_info.split('_')
            instrument_type = instrument_parts[0]
            instrument_number = instrument_parts[1] if len(instrument_parts) > 1 else ""

            # 构建解析结果
            result = {
                "filename": filename,
                "base_name": base_name,
                "file_type": "calibration_curve",
                "instrument_type": instrument_type,
                "instrument_number": instrument_number,
                "instrument_info": instrument_info,
                "curve_number": curve_number,
                "test_date": test_date,
                "full_pattern_matched": True
            }
            if sample_info:
                result["sample_info"] = sample_info
            if solvent_info:
                result["solvent_info"] = solvent_info
            
            logger.info(f"仪器特性曲线文件名解析成功: {filename}")
            return result
        except Exception as e:
            logger.error(f"解析仪器特性曲线文件名失败: {str(e)}")
            return None
    
    def parse_data_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        解析原始数据文件名
        
        参数:
        filename: 原始数据文件名（不包含路径）
        
        返回:
        Optional[Dict[str, Any]]: 解析结果字典，解析失败返回None
        """
        try:
            logger.info(f"开始解析原始数据文件名: {filename}")
            
            # 移除文件扩展名
            base_name = os.path.splitext(filename)[0]
            
            # 匹配正则表达式
            match = self.data_pattern.match(base_name)
            if match:
                # 提取各部分信息
                instrument_info = match.group(1)
                test_date = match.group(2)
                curve_number = match.group(3)
                sample_info_str = match.group(4)  # 可选字段，可能为None
                solvent_info = match.group(5)
                mix_type = match.group(6)

                # 解析仪器类型和编号
                instrument_parts = instrument_info.split('_')
                instrument_type = instrument_parts[0]
                instrument_number = instrument_parts[1] if len(instrument_parts) > 1 else ""

                # 解析样品信息（可选字段）
                sample_info = self._parse_sample_info(sample_info_str) if sample_info_str else {}

                # 构建解析结果
                result = {
                    "filename": filename,
                    "base_name": base_name,
                    "file_type": "raw_data",
                    "instrument_type": instrument_type,
                    "instrument_number": instrument_number,
                    "instrument_info": instrument_info,
                    "test_date": test_date,
                    "curve_number": curve_number,
                    "sample_info": sample_info,
                    "solvent_info": solvent_info,
                    "mix_type": mix_type,
                    "full_pattern_matched": True
                }
                if sample_info_str:
                    result["sample_info_raw"] = sample_info_str
                
                logger.info(f"原始数据文件名解析成功: {filename}")
                return result
            else:
                # 尝试简化匹配
                simple_match = self.simple_data_pattern.match(base_name)
                if simple_match:
                    logger.warning(f"原始数据文件名格式不完全匹配，使用简化解析: {filename}")
                    instrument_info = simple_match.group(1)
                    remaining_part = simple_match.group(2)

                    instrument_parts = instrument_info.split('_')
                    instrument_type = instrument_parts[0]
                    instrument_number = instrument_parts[1] if len(instrument_parts) > 1 else ""

                    # 尝试从剩余部分提取标定曲线编号
                    curve_number = None
                    curve_match = re.search(r'(Cal\d{3})', remaining_part)
                    if curve_match:
                        curve_number = curve_match.group(1)

                    # 构建简化解析结果
                    result = {
                        "filename": filename,
                        "base_name": base_name,
                        "file_type": "raw_data",
                        "instrument_type": instrument_type,
                        "instrument_number": instrument_number,
                        "instrument_info": instrument_info,
                        "curve_number": curve_number,
                        "remaining_part": remaining_part,
                        "full_pattern_matched": False
                    }
                    
                    return result
                else:
                    logger.warning(f"原始数据文件名格式不匹配: {filename}")
                    return None
        except Exception as e:
            logger.error(f"解析原始数据文件名失败: {str(e)}")
            return None

    @staticmethod
    def _parse_sample_info(sample_info_str: str) -> Dict[str, Any]:
        """
        解析样品信息字符串
        
        参数:
        sample_info_str: 样品信息字符串，格式如 "PS,0.2mg/ml,6000"
        
        返回:
        Dict[str, Any]: 解析后的样品信息
        """
        try:
            sample_info = {}
            
            # 分割样品信息
            parts = sample_info_str.split(',')
            
            if len(parts) >= 1:
                sample_info["sample_type"] = parts[0].strip()
            
            if len(parts) >= 2:
                # 解析浓度
                concentration_str = parts[1].strip()
                concentration_match = re.search(r"([\d.]+)([a-zA-Z/]+)", concentration_str)
                if concentration_match:
                    sample_info["concentration_value"] = float(concentration_match.group(1))
                    sample_info["concentration_unit"] = concentration_match.group(2)
                    sample_info["concentration"] = concentration_str
                else:
                    sample_info["concentration"] = concentration_str
            
            if len(parts) >= 3:
                # 解析预期分子量
                expected_mw_str = parts[2].strip()
                expected_mw_match = re.search(r"([\d.]+)", expected_mw_str)
                if expected_mw_match:
                    sample_info["expected_mw"] = float(expected_mw_match.group(1))
                else:
                    sample_info["expected_mw"] = None
            
            return sample_info
        except Exception as e:
            logger.error(f"解析样品信息失败: {str(e)}")
            return {"raw": sample_info_str}
    
    def parse_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        通用文件名解析方法，自动判断文件类型并解析
        
        参数:
        filename: 文件名（不包含路径）
        
        返回:
        Optional[Dict[str, Any]]: 解析结果字典，解析失败返回None
        """
        # 先尝试解析为仪器特性曲线文件
        curve_result = self.parse_curve_filename(filename)
        if curve_result:
            return curve_result
        
        # 再尝试解析为原始数据文件
        data_result = self.parse_data_filename(filename)
        if data_result:
            return data_result
        
        # 解析失败
        logger.warning(f"无法解析文件名: {filename}")
        return None

    @staticmethod
    def _get_available_curve_files() -> List[str]:
        """
        获取可用的仪器特性曲线文件列表
        
        返回:
        List[str]: 仪器特性曲线文件名列表
        """
        try:
            curve_dir = GLOBAL_CONFIG["data_storage"]["calibration_curves"]
            
            # 获取目录中的所有JSON文件
            curve_files = []
            if os.path.exists(curve_dir):
                for file in os.listdir(curve_dir):
                    if file.endswith(".json"):
                        curve_files.append(file)
            
            return curve_files
        except Exception as e:
            logger.error(f"获取可用曲线文件失败: {str(e)}")
            return []
    
    def match_three_color_curve(self, actual_curve_name: str, three_color_curves_dir: str) -> Optional[str]:
        """
        根据仪器名称和标定曲线名称匹配对应的三色曲线文件
        
        参数:
        actual_curve_name: 实际洗脱曲线文件名
        three_color_curves_dir: 三色曲线文件所在目录
        
        返回:
        Optional[str]: 匹配到的三色曲线文件名（不带扩展名），匹配失败返回None
        """
        try:
            logger.info(f"开始匹配实际洗脱曲线 {actual_curve_name} 的三色曲线文件")
            
            # 解析实际洗脱曲线名称
            actual_parsed = self.parse_filename(actual_curve_name)
            if not actual_parsed:
                logger.warning(f"无法解析实际洗脱曲线文件名: {actual_curve_name}")
                return None
            
            # 提取匹配关键字：仪器名称和标定曲线名称
            instrument_info = actual_parsed.get('instrument_info')
            curve_number = actual_parsed.get('curve_number')

            # 提取基础仪器编号（去掉连字符后的批次部分），如 GPC_01-2279 → GPC_01
            base_instrument_match = re.match(r'GPC_\d+', instrument_info or '')
            base_instrument = base_instrument_match.group(0) if base_instrument_match else instrument_info

            if not instrument_info:
                logger.warning(f"无法获取实际洗脱曲线的仪器信息: {actual_curve_name}")
                return None

            if not curve_number:
                logger.warning(f"无法获取实际洗脱曲线的标定曲线名称: {actual_curve_name}")
                return None
            
            # 获取三色曲线目录中的所有文件
            three_color_files = []
            if os.path.exists(three_color_curves_dir):
                for file in os.listdir(three_color_curves_dir):
                    three_color_files.append(file)
            else:
                logger.warning(f"三色曲线目录不存在: {three_color_curves_dir}")
                return None
            
            if not three_color_files:
                logger.warning(f"三色曲线目录中没有文件: {three_color_curves_dir}")
                return None
            
            # 遍历三色曲线文件，寻找匹配的文件
            matched_curve_name = None
            
            # 先尝试严格匹配，找到基础三色曲线名称
            for file in three_color_files:
                # 移除文件扩展名和颜色后缀
                base_name = os.path.splitext(file)[0]
                
                # 检查文件名是否包含颜色后缀
                color_suffixes = ['_green', '_red', '_white']
                curve_base_name = None
                for suffix in color_suffixes:
                    if base_name.endswith(suffix):
                        curve_base_name = base_name[:-len(suffix)]
                        break
                
                if curve_base_name:
                    # 解析三色曲线基础名称
                    three_color_parsed = self.parse_curve_filename(f"{curve_base_name}.pdf")
                    if three_color_parsed:
                        three_color_instrument_info = three_color_parsed.get('instrument_info')
                        three_color_curve_number = three_color_parsed.get('curve_number')
                        
                        # 检查匹配关键字（支持完整匹配和基础仪器号匹配）
                        if three_color_curve_number == curve_number and (
                            three_color_instrument_info == instrument_info
                            or three_color_instrument_info == base_instrument
                        ):
                            logger.info(f"成功匹配三色曲线文件: {curve_base_name} 对应实际洗脱曲线: {actual_curve_name}")
                            matched_curve_name = curve_base_name
                            break
            
            # 如果严格匹配失败，尝试宽松匹配
            if not matched_curve_name:
                for file in three_color_files:
                    # 移除文件扩展名和颜色后缀
                    base_name = os.path.splitext(file)[0]
                    
                    # 检查文件名是否包含颜色后缀
                    color_suffixes = ['_green', '_red', '_white']
                    curve_base_name = None
                    for suffix in color_suffixes:
                        if base_name.endswith(suffix):
                            curve_base_name = base_name[:-len(suffix)]
                            break
                    
                    if curve_base_name:
                        # 检查文件名中是否包含仪器信息和曲线编号
                        if curve_number in curve_base_name and (
                            instrument_info in curve_base_name or base_instrument in curve_base_name
                        ):
                            logger.info(f"宽松匹配三色曲线文件: {curve_base_name} 对应实际洗脱曲线: {actual_curve_name}")
                            matched_curve_name = curve_base_name
                            break
            
            return matched_curve_name

        except Exception as e:
            logger.error(f"匹配三色曲线文件失败: {str(e)}")
            return None

