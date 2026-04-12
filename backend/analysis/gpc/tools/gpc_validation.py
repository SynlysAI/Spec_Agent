import pymupdf as fitz
import os
import re
import random
import sys
import statistics
from typing import Dict, Any, Optional

# 确保项目根目录被添加到sys.path中


class GPCValidator:
    """GPC PDF验证器，用于从GPC测试报告中提取分子量信息"""

    def __init__(self, search_dir: Optional[str] = None):
        """初始化 GPC 验证器。

        Args:
            search_dir: 在 ``process_gpc_data`` 中按文件名匹配 PDF 时递归扫描的根目录；
                为 ``None`` 时使用 ``GLOBAL_CONFIG['paths']['gpc_comparison_pdf_dir']``。
        """
        self._search_dir = search_dir

    def _get_search_dir(self) -> str:
        if self._search_dir:
            return self._search_dir
        from config import GLOBAL_CONFIG

        return GLOBAL_CONFIG["paths"]["gpc_comparison_pdf_dir"]
    
    def extract_molecular_weight_info(self, file_path: str) -> Dict[str, Any]:
        """
        从GPC测试报告PDF中提取分子量信息
        
        参数:
        file_path: PDF文件路径
        
        返回:
        Dict[str, Any]: 包含分子量信息的字典
        """
        try:
            # 打开PDF文件
            pdf_document = fitz.open(file_path)
            
            # 提取第一页文本
            if pdf_document:
                page = pdf_document[0]
                text = page.get_text()
                pdf_document.close()
            else:
                return {}
            
            # 解析分子量信息
            mw_info = self._parse_molecular_weight_info(text)
            
            # 合并数据
            result = {
                **mw_info,
                "file_path": file_path
            }
            
            return result
        except Exception:
            return {}

    @staticmethod
    def _parse_molecular_weight_info(text: str) -> Dict[str, Any]:
        """
        解析分子量信息
        
        参数:
        text: 提取的文本
        
        返回:
        Dict[str, Any]: 包含分子量信息的字典
        """
        try:
            # 将文本按行分割
            lines = text.split('\n')
            
            # 方法1：直接查找图表上方的分子量信息（格式：Mn=34889）
            result = {}
            for line in lines:
                line = line.strip()
                if "=" in line:
                    # 使用正则表达式一次性匹配所有键值对
                    matches = re.findall(r"(Mn|Mw|MP|Mz|Mz\+1|多分散性|Dispersion)=(\d+\.\d+|\d+)", line)
                    for key, value in matches:
                        # 统一多分散性的键名
                        if key == "Dispersion":
                            result["多分散性"] = float(value)
                        else:
                            result[key] = float(value)
                
                # 额外检查多分散性值，可能出现在单独的行中
                if "多分散性" in line or "Dispersion" in line:
                    # 查找多分散性=XXX或Dispersion=XXX格式
                    poly_match = re.search(r"(?:多分散性|Dispersion)[\s=：:]+(\d+\.\d+|\d+)", line)
                    if poly_match:
                        result["多分散性"] = float(poly_match.group(1))
            
            # 继续执行方法2，确保查找多分散性值
            # 即使方法1找到了基本数据，也需要检查是否包含多分散性值
            
            # 方法2：查找表格形式的分子量信息
            # 寻找表格起始位置的多种可能
            table_start = -1
            for i, line in enumerate(lines):
                if any(keyword in line for keyword in ["分布名称", "分子量分布", "Molecular Weight"]):
                    table_start = i
                    break
            
            # 如果找到表格起始位置
            if table_start != -1:
                # 查找数据行起始位置（第一个数字行）
                data_start = -1
                for i in range(table_start + 1, min(table_start + 30, len(lines))):
                    line = lines[i].strip()
                    if re.match(r"^\d+\.?\d*$", line):  # 纯数字行
                        data_start = i
                        break
                
                if data_start != -1:
                    # 从数据起始行开始，依次读取各数据项
                    data_values = []
                    for i in range(data_start, min(data_start + 15, len(lines))):
                        line = lines[i].strip()
                        if re.match(r"^\d+\.?\d*$", line):  # 纯数字行
                            data_values.append(float(line))
                    
                    # 根据表格结构映射数据，只在缺少数据时设置值
                    if len(data_values) >= 5:
                        if "Mn" not in result:
                            result["Mn"] = data_values[0]  # 第1个数据是Mn
                        if "Mw" not in result:
                            result["Mw"] = data_values[1]  # 第2个数据是Mw
                        if "MP" not in result:
                            result["MP"] = data_values[2]  # 第3个数据是MP
                        if "Mz" not in result:
                            result["Mz"] = data_values[3]  # 第4个数据是Mz
                        if "Mz+1" not in result:
                            result["Mz+1"] = data_values[4]  # 第5个数据是Mz+1
                    if len(data_values) >= 6:
                        # 确保设置多分散性值，无论方法1是否找到
                        result["多分散性"] = data_values[5]  # 第6个数据是多分散性
            
            # 额外检查：如果仍然没有找到多分散性值，尝试计算
            if "多分散性" not in result and "Mn" in result and "Mw" in result:
                if result["Mn"] != 0:
                    result["多分散性"] = result["Mw"] / result["Mn"]
            
            return result
            
        except Exception:
            return {}
    
    def process_gpc_data(
        self,
        test_data_name: str,
        manual_pdf_path: Optional[str] = None,
        search_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        处理GPC测试数据，提取分子量信息。

        参数:
            test_data_name: 测试数据名称（不带扩展名的文件名），用于在目录中匹配 PDF 文件名。
            manual_pdf_path: 若提供且文件存在，则直接解析该 PDF，不再按名称在目录中搜索。
            search_dir: 覆盖实例上的搜索根目录；默认使用全局配置 ``gpc_comparison_pdf_dir``。

        返回:
            包含分子量信息的字典。
        """
        try:
            if manual_pdf_path and os.path.isfile(manual_pdf_path):
                return self.extract_molecular_weight_info(manual_pdf_path)

            base_dir = search_dir or self._get_search_dir()
            if not base_dir or not os.path.isdir(base_dir):
                return {}

            for root, dirs, files in os.walk(base_dir):
                for file in files:
                    if file.endswith(".pdf") and test_data_name in file:
                        pdf_file = os.path.join(root, file)
                        return self.extract_molecular_weight_info(pdf_file)

            return {}
        except Exception:
            return {}
