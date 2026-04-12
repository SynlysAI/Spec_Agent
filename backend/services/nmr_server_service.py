from __future__ import annotations

import requests

from config import GLOBAL_CONFIG


class NMRServerService:
    """NMRServer 外部接口服务封装。

    该服务用于对接外部提供的 NMR 分子式双向预测与数据库检索能力，
    页面层仅负责收集输入和展示结果，具体 HTTP 通信由本类统一处理。
    """

    def __init__(self, base_url: str | None = None):
        """初始化外部 NMRServer 客户端。

        Args:
            base_url: 外部服务根地址；未传入时使用统一配置中的默认地址。
        """
        self.base_url = base_url or GLOBAL_CONFIG["services"]["nmr_server_base_url"]

    def _post(self, payload: dict) -> list[dict]:
        """向 NMRServer 发送请求并解析标准返回格式。

        Args:
            payload: 按外部接口规范构造的 JSON 请求体。

        Returns:
            接口返回的结果数据列表。

        Raises:
            RuntimeError: 当外部服务返回业务错误时抛出。
        """
        response = requests.post(
            f"{self.base_url}/sync_nmr_service_mcp",
            json=payload,
            timeout=360,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("code") != 0 or "data" not in result:
            raise RuntimeError(result.get("msg", "未知错误"))
        return result["data"]["result"]["data"]

    @staticmethod
    def _parse_float_list(raw_text: str) -> list[float]:
        """将逗号分隔的数字字符串解析为浮点数列表。"""
        return [float(item.strip()) for item in raw_text.split(",")] if raw_text.strip() else []

    @staticmethod
    def _parse_text_list(raw_text: str) -> list[str]:
        """将逗号分隔的文本解析为字符串列表。"""
        return [item.strip() for item in raw_text.split(",") if item.strip()] if raw_text else []

    def forward_predict(self, smiles_input: str) -> list[dict]:
        """执行正向预测：SMILES -> NMR 化学位移。

        Args:
            smiles_input: 多行 SMILES 输入文本，每行一个分子。

        Returns:
            外部服务返回的预测结果列表。
        """
        smiles_list = [item.strip() for item in smiles_input.strip().split("\n") if item.strip()]
        if not smiles_list:
            raise ValueError("请输入至少一个有效的 SMILES")

        payload = {
            "name": "case_predict",
            "input_data": {
                "predict": {
                    "smiles_list": smiles_list,
                    "H_shifts": None,
                    "C_shifts": None,
                    "H_split": None,
                }
            },
        }
        return self._post(payload)

    def reverse_predict(
        self,
        h_shifts_input: str,
        h_split_input: str,
        c_shifts_input: str,
        formula: str,
        allowed_elements: str,
        candidates: str,
    ) -> list[dict]:
        """执行反向预测：化学位移 -> 候选分子结构。

        Args:
            h_shifts_input: 氢谱化学位移输入字符串。
            h_split_input: 氢谱峰裂分输入字符串。
            c_shifts_input: 碳谱化学位移输入字符串。
            formula: 可选的分子式约束。
            allowed_elements: 允许元素列表字符串。
            candidates: 候选分子字符串。

        Returns:
            外部服务返回的候选分子结果列表。
        """
        h_shifts = self._parse_float_list(h_shifts_input)
        h_split = self._parse_text_list(h_split_input)
        c_shifts = self._parse_float_list(c_shifts_input)

        reverse_predict_data = {}
        if h_shifts:
            reverse_predict_data["H_shifts"] = h_shifts
        if h_split:
            reverse_predict_data["H_split"] = h_split
        if c_shifts:
            reverse_predict_data["C_shifts"] = c_shifts

        constraints = {}
        if formula:
            constraints["formula"] = formula.strip()
        constraints["allowed_elements"] = (
            self._parse_text_list(allowed_elements)
            if allowed_elements
            else ["C", "H", "O", "N", "S", "P", "F", "Cl", "Br", "I"]
        )
        if constraints:
            reverse_predict_data["constraints"] = constraints

        candidates_list = self._parse_text_list(candidates)
        if candidates_list:
            reverse_predict_data["candidates"] = candidates_list

        payload = {
            "name": "case_reverse_predict",
            "input_data": {"reverse_predict": reverse_predict_data},
        }
        return self._post(payload)

    def database_search(
        self,
        h_shifts_input: str,
        h_split_input: str,
        c_shifts_input: str,
        num_search: int,
        topk: int,
        allowed_elements: str,
    ) -> list[dict]:
        """执行数据库搜索：化学位移 -> 数据库匹配结构。

        Args:
            h_shifts_input: 氢谱化学位移输入字符串。
            h_split_input: 氢谱峰裂分输入字符串。
            c_shifts_input: 碳谱化学位移输入字符串。
            num_search: 数据库检索的候选分子数量。
            topk: 最终返回的 Top-K 结果数量。
            allowed_elements: 允许元素列表字符串。

        Returns:
            外部服务返回的数据库匹配结果列表。
        """
        search_data = {
            "num_search": num_search,
            "topk": topk,
            "allowed_elements": self._parse_text_list(allowed_elements) if allowed_elements else ["C", "H", "O", "N"],
        }
        h_shifts = self._parse_float_list(h_shifts_input)
        h_split = self._parse_text_list(h_split_input)
        c_shifts = self._parse_float_list(c_shifts_input)

        if h_shifts:
            search_data["H_shifts"] = h_shifts
        if h_split:
            search_data["H_split"] = h_split
        if c_shifts:
            search_data["C_shifts"] = c_shifts

        payload = {
            "name": "case_search",
            "input_data": {"search": search_data},
        }
        return self._post(payload)
