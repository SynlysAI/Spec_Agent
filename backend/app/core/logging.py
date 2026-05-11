"""统一日志配置模块。"""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.core.config import settings


LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | "
    "request_id=%(request_id)s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_REQUEST_ID = "-"


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


def _build_file_handler(filename: str, level: int) -> TimedRotatingFileHandler:
    """创建按天轮转的文件日志处理器。

    Args:
        filename: 日志文件名。
        level: 处理器日志等级。

    Returns:
        配置完成的文件日志处理器。
    """
    logs_root = _ensure_logs_root()
    handler = TimedRotatingFileHandler(
        filename=logs_root / filename,
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    handler.addFilter(RequestIdFilter())
    return handler


def _reset_logger(logger: logging.Logger, level: int) -> logging.Logger:
    """清理并重建日志记录器的基础状态。

    Args:
        logger: 目标日志记录器。
        level: 记录器日志等级。

    Returns:
        已重置的日志记录器。
    """
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    return logger


def _has_configured_handlers(logger_name: str) -> bool:
    """判断指定日志记录器是否已完成处理器配置。

    Args:
        logger_name: 日志记录器名称。

    Returns:
        若日志记录器已绑定至少一个处理器则返回 True。
    """
    return bool(logging.getLogger(logger_name).handlers)


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


def _should_use_worker_log(logger_name: str) -> bool:
    """判断当前日志记录器是否应写入 worker 日志文件。

    Args:
        logger_name: 目标日志记录器名称。

    Returns:
        若当前处于 worker 日志上下文则返回 True。
    """
    if logger_name.startswith("spec_agent.worker"):
        return True
    if not _is_worker_runtime():
        return False
    return _has_configured_handlers("spec_agent.worker")


def configure_named_logger(
    logger_name: str,
    *,
    filename: str,
    level: int = logging.INFO,
    error_filename: str | None = None,
) -> logging.Logger:
    """创建指定名称的双写日志记录器。

    Args:
        logger_name: 日志记录器名称。
        filename: 主日志文件名。
        level: 日志等级。
        error_filename: 错误日志文件名；未传则不额外输出错误日志。

    Returns:
        配置完成的日志记录器。
    """
    logger = _reset_logger(logging.getLogger(logger_name), level)
    logger.addHandler(_build_file_handler(filename, level))
    if error_filename:
        logger.addHandler(_build_file_handler(error_filename, logging.ERROR))
    return logger


def configure_app_logging(level: int = logging.INFO) -> logging.Logger:
    """初始化后端应用日志记录器。

    Args:
        level: 应用日志等级。

    Returns:
        应用日志记录器。
    """
    logger = configure_named_logger(
        "spec_agent.app",
        filename="app.log",
        level=level,
        error_filename="error.log",
    )
    logger.info("应用日志初始化完成", extra={"request_id": DEFAULT_REQUEST_ID})
    return logger


def configure_worker_logging(level: int = logging.INFO) -> logging.Logger:
    """初始化 Celery Worker 日志记录器。

    Args:
        level: Worker 日志等级。

    Returns:
        Worker 日志记录器。
    """
    logger = configure_named_logger(
        "spec_agent.worker",
        filename="worker.log",
        level=level,
        error_filename="error.log",
    )
    logger.info("Worker 日志初始化完成", extra={"request_id": DEFAULT_REQUEST_ID})
    return logger


def get_logger(logger_name: str = "spec_agent.app") -> logging.Logger:
    """获取已配置的日志记录器。

    Args:
        logger_name: 日志记录器名称。

    Returns:
        目标日志记录器；若尚未配置则先按应用日志初始化。
    """
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger
    if _should_use_worker_log(logger_name):
        return configure_named_logger(
            logger_name,
            filename="worker.log",
            level=logging.INFO,
            error_filename="error.log",
        )
    return configure_named_logger(
        logger_name,
        filename="app.log",
        level=logging.INFO,
        error_filename="error.log",
    )
