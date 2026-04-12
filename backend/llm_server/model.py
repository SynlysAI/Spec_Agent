"""
LLM 客户端与兼容入口。

从环境变量与 `config.GLOBAL_CONFIG` 中的 ``llm`` 段读取参数，提供统一的
`get_llm_config` / `get_llm_client` / `create_llm_client`。
注意：须先导入 `config`（会加载 `.env`），再使用本模块。
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from config import GLOBAL_CONFIG, setup_logging


def get_llm_config() -> dict:
    """返回当前 LLM 相关配置的浅拷贝，便于调用方安全修改副本。

    Returns:
        包含 model、api_key、base_url、temperature、max_tokens、timeout、max_retries
        等键的字典，来源为 ``GLOBAL_CONFIG["llm"]``。
    """
    return GLOBAL_CONFIG["llm"].copy()


@lru_cache(maxsize=1)
def get_llm_client() -> ChatOpenAI:
    """获取进程内单例的 ChatOpenAI 客户端（带缓存）。

    Returns:
        根据 ``get_llm_config()`` 构造的 ``ChatOpenAI`` 实例。
    """
    logger = setup_logging(logger_name="spec_agent")
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
    """创建 LLM 客户端；无关键字参数时返回与 ``get_llm_client()`` 相同的缓存实例。

    Args:
        **overrides: 覆盖 ``get_llm_config()`` 中的任意键，例如 ``model=``、``temperature=``。

    Returns:
        ``ChatOpenAI`` 实例；无 overrides 时为单例，有 overrides 时为新建实例。
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


# 兼容旧代码：模块级默认模型实例（延迟失败，避免非 LLM 场景导入中断）
try:
    CHAT_MODEL = get_llm_client()
except Exception:
    CHAT_MODEL = None


if __name__ == "__main__":
    print(CHAT_MODEL.invoke("你好"))
