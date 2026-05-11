"""NMRServer 外部接口服务。"""

from __future__ import annotations

import requests
from requests import Session

from app.core.config import settings
from app.core.logging import get_logger


logger = get_logger("spec_agent.services.nmr_server")


class NmrServerProtocolError(RuntimeError):
    """NMRServer 协议错误。"""


class NmrServerBusinessError(RuntimeError):
    """NMRServer 业务错误。"""


class NmrServerService:
    """NMRServer 外部接口服务封装。"""

    def __init__(self) -> None:
        self.base_url = settings.nmr_server_base_url
        self.connect_timeout = 10
        self.read_timeout = 350
        self.session: Session = requests.Session()

    def _post(self, payload: dict) -> list[dict]:
        """调用外部 NMRServer 统一入口并解析结果。

        Args:
            payload: 按外部服务约定构造的请求体。

        Returns:
            外部服务返回的结果项列表。
        """
        response = self.session.post(
            f"{self.base_url}/sync_nmr_service_mcp",
            json=payload,
            timeout=(self.connect_timeout, self.read_timeout),
        )
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError as exc:
            logger.error("NMRServer 返回非 JSON 响应: %s", exc)
            raise NmrServerProtocolError("NMRServer 返回非 JSON 响应") from exc

        if not isinstance(result, dict):
            logger.error("NMRServer 返回结构不是对象, 实际类型: %s", type(result).__name__)
            raise NmrServerProtocolError("NMRServer 返回结构不是对象")

        if result.get("code") != 0:
            error_msg = result.get("msg", "NMRServer 业务返回异常")
            logger.error("NMRServer 业务错误: code=%s, msg=%s", result.get("code"), error_msg)
            raise NmrServerBusinessError(error_msg)

        data_wrapper = result.get("data")
        if not isinstance(data_wrapper, dict):
            logger.error("NMRServer 返回缺少 data 对象, 实际值: %s", data_wrapper)
            raise NmrServerProtocolError("NMRServer 返回缺少 data 对象")

        result_wrapper = data_wrapper.get("result")
        if not isinstance(result_wrapper, dict):
            logger.error("NMRServer 返回缺少 data.result 对象, 实际值: %s", result_wrapper)
            raise NmrServerProtocolError("NMRServer 返回缺少 data.result 对象")

        items = result_wrapper.get("data")
        if not isinstance(items, list):
            logger.error("NMRServer 返回缺少 data.result.data 列表, 实际值: %s", type(items).__name__)
            raise NmrServerProtocolError("NMRServer 返回缺少 data.result.data 列表")
        return items

    @staticmethod
    def _parse_float_list(raw_text: str) -> list[float]:
        """将逗号分隔字符串解析为浮点数列表。"""
        return [float(item.strip()) for item in raw_text.split(",")] if raw_text.strip() else []

    @staticmethod
    def _parse_text_list(raw_text: str) -> list[str]:
        """将逗号分隔字符串解析为文本列表。"""
        return [item.strip() for item in raw_text.split(",") if item.strip()] if raw_text else []

    def forward_predict(self, smiles_input: str) -> list[dict]:
        """执行正向预测：SMILES -> NMR 化学位移。"""
        smiles_list = [item.strip() for item in smiles_input.strip().split("\n") if item.strip()]
        if not smiles_list:
            logger.warning("正向预测输入 SMILES 为空")
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
        """执行反向预测：化学位移 -> 候选分子结构。"""
        h_shifts = self._parse_float_list(h_shifts_input)
        h_split = self._parse_text_list(h_split_input)
        c_shifts = self._parse_float_list(c_shifts_input)

        reverse_predict_data: dict = {}
        if h_shifts:
            reverse_predict_data["H_shifts"] = h_shifts
        if h_split:
            reverse_predict_data["H_split"] = h_split
        if c_shifts:
            reverse_predict_data["C_shifts"] = c_shifts

        constraints: dict = {}
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
            "input_data": {
                "reverse_predict": reverse_predict_data,
                # 默认配置参数，写死召回50条数据
                "config": {
                  "sigma_h": 1,
                  "sigma_c": 10,
                  "split_coef": 0.8,
                  "max_iter": 2,
                  "num_search": 1000,
                  "num_pool": 1000,
                  "num_filter_pair": 200000,
                  "num_filter_mol": 1000,
                  "num_mutate_mol": 1000,
                  "topk": 50,
                  "max_cycle_length": 6,
                  "use_H_split": False,
                  "use_stereo": False,
                  "optional_halogens": [
                    "F",
                    "Cl",
                    "Br",
                    "I"
                  ],
                  "invalid_patterns": [
                    "[O][O]",
                    "[R]=[R]=[R]",
                    "[r3,r4]=[r3,r4]",
                    "[O][F,Cl,Br,I]"
                  ],
                  "include_active_hs": "yes"
                }
            },
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
        """执行数据库搜索：化学位移 -> 数据库匹配结构。"""
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


nmr_server_service = NmrServerService()
