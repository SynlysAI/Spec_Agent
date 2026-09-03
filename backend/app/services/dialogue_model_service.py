"""问答模型服务。"""

from __future__ import annotations

import json
from typing import Any

import requests

from app.core.config import settings
from app.core.logging import get_logger


logger = get_logger("spec_agent.services.dialogue_model")


class DialogueModelUnavailableError(RuntimeError):
    """问答模型当前不可用异常。"""


class DialogueModelService:
    """封装问答模型列表与调用逻辑。"""

    @staticmethod
    def list_models() -> list[dict[str, str]]:
        """返回问答模型列表。

        Returns:
            模型配置摘要列表。
        """
        items: list[dict[str, str]] = []
        for item in settings.dialogue_model_catalog:
            items.append(
                {
                    "model_key": str(item["model_key"]),
                    "label": str(item["label"]),
                }
            )
        return items

    @staticmethod
    def get_default_model_key() -> str:
        """返回默认问答模型键。

        Returns:
            默认模型键；配置异常时回退到目录首项。
        """
        model_map = settings.dialogue_model_map
        configured_key = settings.dialogue_model_default_key
        if configured_key in model_map:
            return configured_key
        if model_map:
            return next(iter(model_map.keys()))
        return ""

    @staticmethod
    def chat(model_key: str, messages: list[dict[str, str]]) -> str:
        """调用指定问答模型。

        Args:
            model_key: 问答模型键。
            messages: OpenAI 兼容消息列表。

        Returns:
            模型返回的文本内容。

        Raises:
            ValueError: 模型键非法。
            DialogueModelUnavailableError: 模型接口不可用或返回异常。
        """
        model_config = DialogueModelService._get_model_config(model_key=model_key)
        api_key = settings.dialogue_llm_api_key
        base_url = str(model_config.get("base_url") or "").rstrip("/")
        if not api_key or not base_url:
            logger.error(
                "问答模型配置缺失，无法调用: model_key=%s base_url=%s api_key_configured=%s",
                model_key,
                base_url,
                bool(api_key),
            )
            raise DialogueModelUnavailableError("该模型暂不可用")

        payload = DialogueModelService._build_payload(model_config=model_config, messages=messages)
        request_url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(max(settings.dialogue_llm_max_retries, 0) + 1):
            try:
                response = requests.post(
                    request_url,
                    headers=headers,
                    json=payload,
                    timeout=settings.dialogue_llm_timeout,
                )
                return DialogueModelService._parse_response(
                    model_key=model_key,
                    request_url=request_url,
                    response=response,
                )
            except DialogueModelUnavailableError:
                raise
            except requests.RequestException as exc:
                if attempt >= settings.dialogue_llm_max_retries:
                    logger.error(
                        "问答模型请求失败: model_key=%s url=%s error=%s",
                        model_key,
                        request_url,
                        exc,
                    )
                    raise DialogueModelUnavailableError("该模型暂不可用") from exc

        raise DialogueModelUnavailableError("该模型暂不可用")

    @staticmethod
    def chat_stream(model_key: str, messages: list[dict[str, str]]):
        """流式调用指定问答模型，逐段 yield 文本 delta。

        Args:
            model_key: 问答模型键。
            messages: OpenAI 兼容消息列表。

        Yields:
            模型生成的文本片段。

        Raises:
            ValueError: 模型键非法。
            DialogueModelUnavailableError: 模型接口不可用或返回异常。
        """
        model_config = DialogueModelService._get_model_config(model_key=model_key)
        api_key = settings.dialogue_llm_api_key
        base_url = str(model_config.get("base_url") or "").rstrip("/")
        if not api_key or not base_url:
            logger.error(
                "问答模型配置缺失，无法调用: model_key=%s base_url=%s api_key_configured=%s",
                model_key,
                base_url,
                bool(api_key),
            )
            raise DialogueModelUnavailableError("该模型暂不可用")

        payload = DialogueModelService._build_payload(model_config=model_config, messages=messages)
        payload["stream"] = True
        request_url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                request_url,
                headers=headers,
                json=payload,
                timeout=settings.dialogue_llm_timeout,
                stream=True,
            )
        except requests.RequestException as exc:
            logger.error(
                "问答模型流式请求失败: model_key=%s url=%s error=%s",
                model_key,
                request_url,
                exc,
            )
            raise DialogueModelUnavailableError("该模型暂不可用") from exc

        if response.status_code >= 400:
            logger.error(
                "问答模型流式 HTTP 响应异常: model_key=%s status=%s url=%s",
                model_key,
                response.status_code,
                request_url,
            )
            raise DialogueModelUnavailableError("该模型暂不可用")

        # 网关 SSE 响应头未带 charset，requests 对 text/* 默认按 ISO-8859-1 解码会导致中文乱码
        response.encoding = "utf-8"
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data: "):
                continue
            data_text = raw_line[len("data: "):]
            if data_text == "[DONE]":
                break
            try:
                data = json.loads(data_text)
            except ValueError:
                continue
            choices = data.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta", {}) or {}
            content_delta = delta.get("content")
            if content_delta:
                yield content_delta

    @staticmethod
    def _get_model_config(model_key: str) -> dict[str, object]:
        """获取指定模型配置。

        Args:
            model_key: 问答模型键。

        Returns:
            模型配置字典。

        Raises:
            ValueError: 模型键不在支持范围内。
        """
        normalized_key = model_key.strip()
        model_config = settings.dialogue_model_map.get(normalized_key)
        if not model_config:
            raise ValueError("不支持的问答模型")
        return model_config

    @staticmethod
    def _build_payload(model_config: dict[str, object], messages: list[dict[str, str]]) -> dict[str, Any]:
        """构建模型请求体。

        Args:
            model_config: 模型配置字典。
            messages: 对话消息列表。

        Returns:
            OpenAI 兼容请求体。
        """
        payload: dict[str, Any] = {
            "model": str(model_config["model"]),
            "messages": messages,
            "temperature": settings.dialogue_llm_temperature,
            "max_tokens": settings.dialogue_llm_max_tokens,
        }
        if bool(model_config.get("supports_thinking_toggle")):
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        return payload

    @staticmethod
    def _parse_response(model_key: str, request_url: str, response: requests.Response) -> str:
        """解析模型返回。

        Args:
            model_key: 问答模型键。
            request_url: 请求地址。
            response: HTTP 响应对象。

        Returns:
            回复文本。

        Raises:
            DialogueModelUnavailableError: HTTP 状态或响应格式异常。
        """
        try:
            payload = response.json()
        except ValueError as exc:
            logger.error(
                "问答模型返回非 JSON 响应: model_key=%s status=%s url=%s",
                model_key,
                response.status_code,
                request_url,
            )
            raise DialogueModelUnavailableError("该模型暂不可用") from exc

        if response.status_code >= 400:
            logger.error(
                "问答模型 HTTP 响应异常: model_key=%s status=%s url=%s payload=%s",
                model_key,
                response.status_code,
                request_url,
                payload,
            )
            raise DialogueModelUnavailableError("该模型暂不可用")

        if not isinstance(payload, dict):
            logger.error("问答模型响应格式异常: model_key=%s payload=%s", model_key, payload)
            raise DialogueModelUnavailableError("该模型暂不可用")

        if payload.get("code") not in {None, 0} and not payload.get("choices"):
            logger.error(
                "问答模型业务返回异常: model_key=%s url=%s payload=%s",
                model_key,
                request_url,
                payload,
            )
            raise DialogueModelUnavailableError("该模型暂不可用")

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            logger.error("问答模型缺少 choices: model_key=%s payload=%s", model_key, payload)
            raise DialogueModelUnavailableError("该模型暂不可用")

        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        content = (message or {}).get("content", "")
        return DialogueModelService._normalize_content(content)

    @staticmethod
    def _normalize_content(content: Any) -> str:
        """归一化模型返回的内容块。

        Args:
            content: 原始 content 字段。

        Returns:
            纯文本内容。
        """
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                else:
                    parts.append(str(block))
            return "\n".join(part for part in parts if part).strip()
        return str(content).strip()


dialogue_model_service = DialogueModelService()
