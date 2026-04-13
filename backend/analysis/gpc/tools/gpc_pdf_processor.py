import json
import logging
import os
import re
from typing import Dict, Any, List, Tuple

import fitz

from config import setup_logging, GLOBAL_CONFIG


# 配置日志记录
setup_logging(logger_name="GPCPDFProcessor")
logger = logging.getLogger("GPCPDFProcessor")

class GPCPDFProcessor:
    """GPC PDF文件处理器，使用fitz提取GPC校正表数据"""
    
    def __init__(self):
        """初始化GPC PDF处理器"""
        self.pdf_document = None
    
    def __enter__(self):
        """上下文管理器进入方法"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出方法，关闭PDF文档"""
        self.close()
    
    def open_pdf(self, file_path: str) -> bool:
        """
        打开PDF文件
        
        参数:
        file_path: PDF文件路径
        
        返回:
        bool: 打开成功返回True，否则返回False
        """
        try:
            self.pdf_document = fitz.open(file_path)
            logger.info(f"成功打开PDF文件: {file_path}")
            return True
        except Exception as e:
            logger.error(f"打开PDF文件失败: {str(e)}")
            return False
    
    def close(self):
        """关闭PDF文档"""
        if self.pdf_document:
            self.pdf_document.close()
            self.pdf_document = None
            logger.info("PDF文档已关闭")
    
    def extract_text_from_page(self, page_num: int = 0) -> str:
        """
        从指定页提取文本
        
        参数:
        page_num: 页码，默认为0
        
        返回:
        str: 提取的文本
        """
        try:
            if not self.pdf_document:
                logger.error("PDF文档未打开")
                return ""
            
            if page_num < 0 or page_num >= len(self.pdf_document):
                logger.error(f"页码 {page_num} 超出范围")
                return ""
            
            page = self.pdf_document[page_num]
            text = page.get_text()
            logger.info(f"成功从第 {page_num+1} 页提取文本")
            return text
        except Exception as e:
            logger.error(f"提取文本失败: {str(e)}")
            return ""
    
    def extract_gpc_calibration_table(self, file_path: str) -> Dict[str, Any]:
        """
        从GPC校正曲线PDF报告中提取校正表数据
        
        参数:
        file_path: PDF文件路径
        
        返回:
        Dict[str, Any]: 包含校正表数据的字典
        """
        try:
            logger.info(f"开始从PDF提取GPC校正表数据: {file_path}")
            
            # 打开PDF文件
            if not self.open_pdf(file_path):
                return {}
            
            # 提取第一页文本
            text = self.extract_text_from_page(0)
            if not text:
                return {}
            
            # 解析校正表数据
            calibration_data = self._parse_calibration_table(text)
            
            # 合并数据
            result = {
                "calibration_table": calibration_data,
                "file_path": file_path
            }
            
            logger.info("GPC校正表数据提取完成")
            return result
        except Exception as e:
            logger.error(f"提取GPC校正表数据失败: {str(e)}")
            return {}

    @staticmethod
    def _parse_calibration_table(text: str) -> List[Dict[str, float]]:
        """
        解析校正表数据
        
        参数:
        text: 提取的文本
        
        返回:
        List[Dict[str, float]]: 校正表数据列表
        """
        try:
            logger.info("开始解析GPC校正表数据")
            
            # 1. 将文本按行分割，便于逐行分析
            lines = text.split('\n')
            calibration_data = []
            
            # 2. 寻找包含"分子量"的行，确定数据区域
            molecular_weight_lines = []
            for i, line in enumerate(lines):
                if "分子量" in line:
                    molecular_weight_lines.append((i, line))
                    logger.info(f"在第 {i+1} 行找到'分子量'关键词")
            
            # 3. 处理每个找到的"分子量"行
            for mw_line_idx, mw_line in molecular_weight_lines:
                logger.info(f"处理第 {mw_line_idx+1} 行的'分子量'关键词")
                
                # 4. 回溯寻找前面的序号序列
                # 从"分子量"行向前查找，寻找连续的序号行
                found_sequences = []
                current_idx = mw_line_idx - 1
                
                while current_idx >= 0:
                    line = lines[current_idx].strip()
                    if not line:  # 跳过空行
                        current_idx -= 1
                        continue
                    
                    # 提取当前行的所有整数
                    current_numbers = re.findall(r"\b\d+\b", line)
                    if not current_numbers:
                        break  # 如果当前行没有整数，停止回溯
                    
                    # 检查是否为连续的序号
                    sequence = [int(num) for num in current_numbers]
                    is_consecutive = True
                    for i in range(1, len(sequence)):
                        if sequence[i] != sequence[i-1] + 1:
                            is_consecutive = False
                            break
                    
                    if is_consecutive and len(sequence) >= 1:
                        logger.info(f"找到序号序列: {sequence}，在第 {current_idx+1} 行")
                        found_sequences.append((current_idx, sequence))
                        # 继续向前查找，可能还有多个序号行
                        current_idx -= 1
                    else:
                        break  # 如果不是连续序号，停止回溯
                
                if not found_sequences:
                    logger.warning(f"在'分子量'行 {mw_line_idx+1} 前未找到序号序列")
                    continue
                
                # 5. 获取所有序号，按顺序排列
                all_sequence_numbers = []
                for seq_idx, sequence in found_sequences:
                    all_sequence_numbers = sequence + all_sequence_numbers  # 合并序列，保持顺序
                
                num_points = len(all_sequence_numbers)
                logger.info(f"总序号数量: {num_points}，序号序列: {all_sequence_numbers}")
                
                # 6. 寻找包含"残差"的行，确定数据区域开始
                residual_line_idx = -1
                for i in range(mw_line_idx, len(lines)):
                    line = lines[i]
                    if "%残差" in line or "% 残差" in line:
                        residual_line_idx = i
                        logger.info(f"在第 {i+1} 行找到'残差'关键词")
                        break
                
                if residual_line_idx == -1:
                    logger.warning(f"在'分子量'行 {mw_line_idx+1} 后未找到'残差'关键词")
                    continue
                
                # 7. 提取分子量和保留时间数据
                # 首先提取所有数字，用于后续数据匹配
                # 数据应该在'残差'行之后，所以提取从'残差'行开始的后续行
                all_numbers = []
                for i in range(residual_line_idx, len(lines)):
                    line = lines[i]
                    numbers = re.findall(r"\b\d+\.\d+\b|\b\d+\b|\b-\d+\.\d+\b", line)
                    all_numbers.extend([float(num) for num in numbers])
                
                logger.info(f"在'残差'行后提取到 {len(all_numbers)} 个数字")
                
                if len(all_numbers) < num_points * 2:  # 至少需要 num_points 个分子量和 num_points 个保留时间
                    logger.warning(f"'残差'行后数字不足，需要 {num_points*2} 个，实际找到 {len(all_numbers)} 个")
                    continue
                
                # 8. 寻找分子量数据（较大数值，100-10^7范围）
                mw_values = []
                rt_values = []
                
                # 在'残差'行后的数据中寻找连续的num_points个分子量数据
                for i in range(len(all_numbers) - num_points + 1):
                    # 检查是否为分子量数据（较大数值）
                    valid_mw = True
                    for j in range(num_points):
                        val = all_numbers[i+j]
                        if not (100 <= val <= 10**7):
                            valid_mw = False
                            break
                    
                    if valid_mw:
                        mw_values = all_numbers[i:i+num_points]
                        logger.info(f"找到分子量数据: {mw_values}")
                        
                        # 寻找对应的保留时间数据（10-30分钟范围）
                        # 保留时间数据应该在分子量数据之后
                        for j in range(i+num_points, len(all_numbers) - num_points + 1):
                            valid_rt = True
                            for k in range(num_points):
                                val = all_numbers[j+k]
                                if not (10 <= val <= 30):
                                    valid_rt = False
                                    break
                            
                            if valid_rt:
                                rt_values = all_numbers[j:j+num_points]
                                logger.info(f"找到保留时间数据: {rt_values}")
                                break
                        
                        if rt_values:
                            break
                
                if not mw_values or not rt_values:
                    logger.warning("未找到有效的分子量或保留时间数据")
                    continue
                
                # 9. 构建校正表数据
                for i in range(num_points):
                    if i < len(all_sequence_numbers):
                        row = {
                            "number": all_sequence_numbers[i],
                            "molecular_weight": mw_values[i],
                            "retention_time": rt_values[i]
                        }
                        calibration_data.append(row)
                        logger.info(f"解析到数据点: 序号={row['number']}, 分子量={row['molecular_weight']:.0f}, 保留时间={row['retention_time']:.3f}")
            
            # 10. 确保数据按序号排序
            if calibration_data:
                calibration_data.sort(key=lambda x: x["number"])
                logger.info(f"共解析到 {len(calibration_data)} 个数据点")
                return calibration_data
            
            logger.warning("未找到有效的校正表数据")
            return []
            
        except Exception as e:
            logger.error(f"解析校正表数据失败: {str(e)}")
            return []
        
    def get_calibration_curve_data(self, file_path: str) -> Tuple[List[float], List[float]]:
        """
        获取校准曲线的分子量和保留时间数据
        
        参数:
        file_path: PDF文件路径
        
        返回:
        Tuple[List[float], List[float]]: (保留时间列表, 分子量列表)
        """
        try:
            # 提取校正表数据
            result = self.extract_gpc_calibration_table(file_path)
            calibration_table = result.get("calibration_table", [])
            
            if not calibration_table:
                logger.error("未找到校准曲线数据")
                return [], []
            
            # 提取保留时间和分子量
            retention_times = [row["retention_time"] for row in calibration_table]
            molecular_weights = [row["molecular_weight"] for row in calibration_table]
            
            logger.info(f"成功获取校准曲线数据，共 {len(retention_times)} 个数据点")
            return retention_times, molecular_weights
        except Exception as e:
            logger.error(f"获取校准曲线数据失败: {str(e)}")
            return [], []
    
    def save_calibration_to_json(self, file_path: str, output_path: str = None) -> bool:
        """
        将校准曲线数据保存到JSON文件
        
        参数:
        file_path: PDF文件路径
        output_path: JSON输出路径（可选，默认保存到data/gpc_pdf_data目录，使用原始文件名）
        
        返回:
        bool: 保存成功返回True，否则返回False
        """
        try:
            # 提取校正表数据
            result = self.extract_gpc_calibration_table(file_path)
            
            # 处理输出路径
            if output_path is None:
                # 创建输出目录（如果不存在）
                output_dir = GLOBAL_CONFIG["data_storage"]["calibration_curves"]
                os.makedirs(output_dir, exist_ok=True)
                
                # 使用原始文件名（不包含扩展名）
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                output_path = os.path.join(output_dir, f"{base_name}.json")
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            logger.info(f"校准曲线数据已保存到JSON文件: {output_path}")
            return True
        except Exception as e:
            logger.error(f"保存校准曲线到JSON文件失败: {str(e)}")
            return False

# 示例用法
if __name__ == "__main__":    
    print("=== GPC PDF处理器测试 ===")
    
    # 使用用户提供的实际PDF文件进行测试
    # test_pdf_file = "E:\肖旭\光刻胶\工程中心-GPC-数据\工程中心-GPC-校准曲线/GPC_03_20250411_Cal002_Copoly_THF_mix.pdf"
    # test_pdf_file = "E:\肖旭\光刻胶\工程中心-GPC-数据\工程中心-GPC-校准曲线/GPC_03_20240920_Cal001_Copoly_THF_mix.pdf"
    # test_pdf_file = "E:\肖旭\光刻胶\工程中心-GPC-数据\工程中心-GPC-校准曲线/校准曲线1.pdf"
    # test_pdf_file = "E:\肖旭\光刻胶\工程中心-GPC-数据\工程中心-GPC-校准曲线/校准曲线2.pdf"
    test_pdf_file = "E:\肖旭\光刻胶\工程中心-GPC-数据\工程中心-GPC-校准曲线/校准曲线3.pdf"
    
    # 1. 测试初始化和上下文管理器
    with GPCPDFProcessor() as processor:
        print("✓ 初始化和上下文管理器测试成功")
        
        # 2. 使用实际PDF文件测试get_calibration_curve_data方法
        print(f"\n=== 使用实际PDF文件进行测试 ===")
        print(f"测试文件: {test_pdf_file}")
        retention_times, molecular_weights = processor.get_calibration_curve_data(test_pdf_file)
        if isinstance(retention_times, list) and isinstance(molecular_weights, list):
            print(f"✓ get_calibration_curve_data方法返回格式正确")
            print(f"  提取到 {len(retention_times)} 个数据点")
            if len(retention_times) > 0:
                print(f"  示例数据点:")
                for i in range(min(5, len(retention_times))):
                    print(f"    保留时间: {retention_times[i]:.2f} min, 分子量: {molecular_weights[i]:.2f}")
        
        # 3. 测试完整的extract_gpc_calibration_table方法
        calibration_result = processor.extract_gpc_calibration_table(test_pdf_file)
        if calibration_result:
            print(f"\n✓ extract_gpc_calibration_table方法执行成功")
            if "calibration_table" in calibration_result:
                print(f"  校准表数据: {len(calibration_result['calibration_table'])} 行")
            if "curve_info" in calibration_result:
                print(f"  曲线信息: {len(calibration_result['curve_info'])} 项")
                # 打印具体的曲线信息
                print(f"  曲线信息详情:")
                for key, value in calibration_result['curve_info'].items():
                    print(f"    {key}: {value}")
        
        # 4. 测试save_calibration_to_json方法（使用默认输出路径）
        success = processor.save_calibration_to_json(test_pdf_file)
        if success:
            print(f"\n✓ save_calibration_to_json方法执行成功")
            # 显示保存路径
            output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "gpc_pdf_data")
            base_name = os.path.splitext(os.path.basename(test_pdf_file))[0]
            output_path = os.path.join(output_dir, f"{base_name}.json")
            print(f"  结果已保存到: {output_path}")
    
    print("\n=== 所有测试完成 ===")
