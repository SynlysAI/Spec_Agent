"""
LLM 客户端服务模块。

从统一配置读取参数，
提供统一的 ``get_llm_config``、``get_llm_client``、``create_llm_client``。
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logging import get_logger


def get_llm_config() -> dict:
    """返回当前 LLM 配置的浅拷贝。

    Returns:
        包含 model、api_key、base_url、temperature、max_tokens、timeout、
        max_retries 等键的配置字典。
    """
    return settings.llm_config.copy()


@lru_cache(maxsize=1)
def get_llm_client() -> ChatOpenAI:
    """获取进程内单例 ChatOpenAI 客户端。

    Returns:
        根据当前 LLM 配置创建的 ChatOpenAI 实例。
    """
    logger = get_logger("spec_agent.app")
    llm_settings = get_llm_config()

    if not llm_settings.get("api_key"):
        logger.warning("LLM API Key 未配置，模型调用可能失败")

    client = ChatOpenAI(
        model=llm_settings["model"],
        api_key=llm_settings["api_key"],
        base_url=llm_settings["base_url"],
        temperature=llm_settings["temperature"],
        max_tokens=llm_settings["max_tokens"],
        timeout=llm_settings["timeout"],
        max_retries=llm_settings["max_retries"],
    )
    logger.info("LLM 客户端初始化成功")
    return client


def create_llm_client(**overrides) -> ChatOpenAI:
    """创建 LLM 客户端。

    Args:
        **overrides: 对默认 LLM 配置的覆盖参数。

    Returns:
        ChatOpenAI 实例；未传覆盖参数时返回缓存单例。
    """
    if not overrides:
        return get_llm_client()

    llm_settings = get_llm_config()
    llm_settings.update(overrides)

    return ChatOpenAI(
        model=llm_settings["model"],
        api_key=llm_settings["api_key"],
        base_url=llm_settings["base_url"],
        temperature=llm_settings["temperature"],
        max_tokens=llm_settings["max_tokens"],
        timeout=llm_settings["timeout"],
        max_retries=llm_settings["max_retries"],
    )


# 兼容旧逻辑：模块级默认模型实例（若初始化失败则保持为 None）。
try:
    CHAT_MODEL = get_llm_client()
except Exception:
    CHAT_MODEL = None
