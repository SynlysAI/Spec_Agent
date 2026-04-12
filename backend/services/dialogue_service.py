import os
from typing import Iterable

from analysis.gpc.polymer_metrics import calculate_monomer_dp
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from config import GLOBAL_CONFIG


class MonomerDPInput(BaseModel):
    """计算单体聚合度的输入参数。"""

    mn: float = Field(description="GPC测得的数均分子量(Mn)")
    monomer_type: str = Field(
        default=None,
        description="单体类型，如'Styrene'(苯乙烯)、'MMA'(甲基丙烯酸甲酯)、'Ethylene'(乙烯)、'Propylene'(丙烯)、'Vinyl Chloride'(氯乙烯)、'Lactide'(乳酸)",
    )
    custom_m0: float = Field(default=None, description="自定义重复单元分子量（当 monomer_type 为预设值时使用）")
    m_end_groups: float = Field(default=0, description="端基总分子量，默认为 0")


gpc_monomer_dp_tool = StructuredTool.from_function(
    func=calculate_monomer_dp,
    name="calculate_monomer_dp",
    description="""
    计算均聚物的数均聚合度(DPn)。
    当用户询问关于GPC分析中的聚合度、DP、数均聚合度等相关问题时使用此工具。

    支持的单体类型：
    - Styrene (苯乙烯): M0=104.15
    - MMA (甲基丙烯酸甲酯): M0=100.12
    - Ethylene (乙烯): M0=28.05
    - Propylene (丙烯): M0=42.08
    - Vinyl Chloride (氯乙烯): M0=62.5
    - Lactide (乳酸): M0=72.06

    计算公式：DP = (Mn - M_ends) / M0
    """,
    args_schema=MonomerDPInput,
)

GPC_TOOLS = [gpc_monomer_dp_tool]


def get_analysis_types() -> list[str]:
    """返回问答页支持的分析类型列表。"""
    return ["无", "GPC分析", "NMR分析", "LC-MS分析", "Raman分析"]


def get_tools_for_analysis(analysis_type: str):
    """根据分析类型返回可供模型调用的工具集合。

    Args:
        analysis_type: 当前选择的分析类型名称。

    Returns:
        对应的工具列表；若该类型无工具则返回 `None`。
    """
    if analysis_type == "GPC分析":
        return GPC_TOOLS
    return None


def get_report_directory_map() -> dict[str, str]:
    """返回各分析类型对应的报告目录映射。"""
    paths = GLOBAL_CONFIG["paths"]
    return {
        "GPC分析": paths["gpc_results"],
        "NMR分析": paths["nmr_results"],
        "LC-MS分析": os.path.join(paths["outputs"], "lcms_results"),
        "Raman分析": paths["raman_results"],
    }


def iter_report_files(analysis_type: str) -> Iterable[str]:
    """遍历指定分析类型的报告文件。

    Args:
        analysis_type: 页面中选择的分析类型。

    Returns:
        该类型下所有报告文件路径的可迭代列表。
    """
    result_dir = get_report_directory_map().get(analysis_type)
    if not result_dir or not os.path.exists(result_dir):
        return []

    report_files = []
    for root, _, files in os.walk(result_dir):
        for file_name in files:
            if file_name.endswith("_report.txt"):
                report_files.append(os.path.join(root, file_name))
    return sorted(report_files)


def load_report_content(report_path: str) -> str:
    """读取报告文件内容。

    Args:
        report_path: 报告文件路径。

    Returns:
        报告文本；文件不存在时返回空字符串。
    """
    if not os.path.exists(report_path):
        return ""

    with open(report_path, "r", encoding="utf-8") as file:
        return file.read()


def build_enhanced_prompt(system_prompt: str, report_content: str | None) -> str:
    """将报告内容拼接进系统提示词。

    Args:
        system_prompt: 用户当前设置的基础 Prompt。
        report_content: 已加载的报告正文，可为空。

    Returns:
        最终送入模型的增强 Prompt。
    """
    if not report_content:
        return system_prompt
    return f"{system_prompt}\n\n以下是分析报告内容：\n{report_content}"
