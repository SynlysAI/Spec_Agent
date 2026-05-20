"""统一日志配置模块。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from concurrent_log_handler import ConcurrentTimedRotatingFileHandler

from app.core.config import settings


LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | "
    "request_id=%(request_id)s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_REQUEST_ID = "-"
APP_ERROR_FILENAME = "app.error.log"
WORKER_ERROR_FILENAME = "worker.error.log"
HANDLER_MARKER = "_spec_agent_managed"


class RequestIdFilter(logging.Filter):
    """为缺失 request_id 的日志记录补默认值。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """补齐 request_id 字段。

        Args:
            record: 待过滤的日志记录。

        Returns:
            始终返回 True，允许日志继续输出。
        """
        if not hasattr(record, "request_id"):
            record.request_id = DEFAULT_REQUEST_ID
        return True


def _ensure_logs_root() -> Path:
    """确保日志目录存在并返回目录路径。"""
    settings.logs_root.mkdir(parents=True, exist_ok=True)
    return settings.logs_root


def _build_file_handler(filename: str, level: int) -> ConcurrentTimedRotatingFileHandler:
    """创建按天轮转的并发安全文件日志处理器。

    Args:
        filename: 日志文件名。
        level: 处理器日志等级。

    Returns:
        配置完成的文件日志处理器。
    """
    logs_root = _ensure_logs_root()
    handler = ConcurrentTimedRotatingFileHandler(
        filename=logs_root / filename,
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    handler.addFilter(RequestIdFilter())
    setattr(handler, HANDLER_MARKER, True)
    return handler


def _reset_logger(logger: logging.Logger, level: int, *, propagate: bool) -> logging.Logger:
    """清理并重建日志记录器的基础状态。

    Args:
        logger: 目标日志记录器。
        level: 记录器日志等级。
        propagate: 是否向父级日志记录器传播。

    Returns:
        已重置的日志记录器。
    """
    logger.setLevel(level)
    logger.propagate = propagate
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    return logger


def _is_managed_handler(handler: logging.Handler) -> bool:
    """判断处理器是否由当前项目日志模块管理。"""
    return bool(getattr(handler, HANDLER_MARKER, False))


def _has_configured_handlers() -> bool:
    """判断根日志记录器是否已完成项目日志处理器配置。"""
    return any(_is_managed_handler(handler) for handler in logging.getLogger().handlers)


def _is_worker_runtime() -> bool:
    """判断当前 Python 进程是否运行在 Celery Worker 上下文中。

    Returns:
        若当前命令行为 Celery Worker 进程则返回 True。
    """
    argv = [arg.lower() for arg in sys.argv if arg]
    if not argv:
        return False
    if "celery" not in argv[0]:
        return False
    return "worker" in argv[1:]


def _normalize_child_logger(logger_name: str) -> logging.Logger:
    """规范化子级日志记录器，避免重复绑定文件处理器。

    Args:
        logger_name: 子级日志记录器名称。

    Returns:
        仅通过根日志记录器输出的子级日志记录器。
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    return logger


def _configure_root_logging(
    filename: str,
    level: int = logging.INFO,
    error_filename: str | None = None,
    *,
    console: bool = False,
) -> logging.Logger:
    """创建进程级根日志记录器。

    Args:
        filename: 主日志文件名。
        level: 日志等级。
        error_filename: 错误日志文件名；未传则不额外输出错误日志。
        console: 是否同时输出到控制台。

    Returns:
        配置完成的日志记录器。
    """
    logger = _reset_logger(logging.getLogger(), level, propagate=False)
    logger.addHandler(_build_file_handler(filename, level))
    if error_filename:
        logger.addHandler(_build_file_handler(error_filename, logging.ERROR))
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        console_handler.addFilter(RequestIdFilter())
        setattr(console_handler, HANDLER_MARKER, True)
        logger.addHandler(console_handler)
    return logger


def configure_named_logger(
    logger_name: str,
    *,
    filename: str,
    level: int = logging.INFO,
    error_filename: str | None = None,
) -> logging.Logger:
    """兼容旧接口，统一转为根日志配置并返回命名日志记录器。

    Args:
        logger_name: 日志记录器名称。
        filename: 主日志文件名。
        level: 日志等级。
        error_filename: 错误日志文件名；未传则不额外输出错误日志。

    Returns:
        配置完成的命名日志记录器。
    """
    if not _has_configured_handlers():
        _configure_root_logging(
            filename=filename,
            level=level,
            error_filename=error_filename,
        )
    return _normalize_child_logger(logger_name)


def configure_app_logging(level: int = logging.INFO) -> logging.Logger:
    """初始化后端应用日志记录器。

    Args:
        level: 应用日志等级。

    Returns:
        应用日志记录器。
    """
    _configure_root_logging(
        filename="app.log",
        level=level,
        error_filename=APP_ERROR_FILENAME,
    )
    logger = _normalize_child_logger("spec_agent.app")
    logger.info("应用日志初始化完成", extra={"request_id": DEFAULT_REQUEST_ID})
    return logger


def configure_worker_logging(level: int = logging.INFO) -> logging.Logger:
    """初始化 Celery Worker 日志记录器。

    Args:
        level: Worker 日志等级。

    Returns:
        Worker 日志记录器。
    """
    _configure_root_logging(
        filename="worker.log",
        level=level,
        error_filename=WORKER_ERROR_FILENAME,
        console=True,
    )
    logger = _normalize_child_logger("spec_agent.worker")
    logger.info("Worker 日志初始化完成", extra={"request_id": DEFAULT_REQUEST_ID})
    return logger


def get_logger(logger_name: str = "spec_agent.app") -> logging.Logger:
    """获取已配置的日志记录器。

    Args:
        logger_name: 日志记录器名称。

    Returns:
        目标日志记录器；若尚未配置则先按应用日志初始化。
    """
    if not _has_configured_handlers():
        if _is_worker_runtime():
            configure_worker_logging(level=logging.INFO)
        else:
            configure_app_logging(level=logging.INFO)

    return _normalize_child_logger(logger_name)
