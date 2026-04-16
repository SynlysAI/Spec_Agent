"""IR/Raman 模块内部 schema。"""

from typing import Any, Dict, List, NotRequired

from typing_extensions import TypedDict


class SpectrumAgentResult(TypedDict, total=False):
    """单谱图分析的标准化返回结构。"""

    structured_data: Dict[str, Any]
    text_report: str
    errors: List[str]
    metadata: NotRequired[Dict[str, Any]]


__all__ = ["SpectrumAgentResult"]
