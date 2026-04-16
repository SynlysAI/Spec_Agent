"""NMRServer 接口模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NmrServerForwardRequest(BaseModel):
    """NMRServer 正向预测请求模型。

    Args:
        smiles_input: 多行 SMILES 输入文本，每行一个分子。
    """

    smiles_input: str = Field(description="多行 SMILES 输入文本")


class NmrServerReverseRequest(BaseModel):
    """NMRServer 反向预测请求模型。

    Args:
        h_shifts_input: 氢谱化学位移输入字符串。
        h_split_input: 峰裂分类型输入字符串。
        c_shifts_input: 碳谱化学位移输入字符串。
        formula: 可选分子式约束。
        allowed_elements: 可选元素限制字符串。
        candidates: 可选候选分子 SMILES 字符串。
    """

    h_shifts_input: str = Field(default="", description="氢谱化学位移输入")
    h_split_input: str = Field(default="", description="峰裂分类型输入")
    c_shifts_input: str = Field(default="", description="碳谱化学位移输入")
    formula: str = Field(default="", description="可选分子式约束")
    allowed_elements: str = Field(default="", description="可选元素限制")
    candidates: str = Field(default="", description="可选候选分子")


class NmrServerSearchRequest(BaseModel):
    """NMRServer 数据库搜索请求模型。

    Args:
        h_shifts_input: 氢谱化学位移输入字符串。
        h_split_input: 峰裂分类型输入字符串。
        c_shifts_input: 碳谱化学位移输入字符串。
        num_search: 搜索候选数量。
        topk: 返回结果数量。
        allowed_elements: 可选元素限制字符串。
    """

    h_shifts_input: str = Field(default="", description="氢谱化学位移输入")
    h_split_input: str = Field(default="", description="峰裂分类型输入")
    c_shifts_input: str = Field(default="", description="碳谱化学位移输入")
    num_search: int = Field(default=500, ge=10, le=10000, description="搜索候选数量")
    topk: int = Field(default=10, ge=1, le=100, description="返回结果数量")
    allowed_elements: str = Field(default="C,H,N,O", description="可选元素限制")


class NmrServerResultData(BaseModel):
    """NMRServer 统一返回模型。

    Args:
        items: 结果项列表。
    """

    items: list[dict[str, Any]]
