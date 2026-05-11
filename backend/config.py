"""旧目录结构兼容配置层。

说明：
    本文件仅作为历史算法模块与兼容代码的稳定入口，避免旧代码大量
    `from config import ...` 在重构期间失效。

约束：
    1. 新代码不要再从本文件读取配置，请统一使用 `app.core.config.settings`。
    2. 本文件只保留兼容导出，不再承担主配置中心职责。
    3. 如需新增配置项，应优先落到 `app.core.config.Settings`，再由本文件映射。
"""

from __future__ import annotations

import logging
import platform
import sys
from typing import Any

from app.core.config import settings
from app.core.logging import configure_named_logger


COMPATIBILITY_NOTE = (
    "backend/config.py 为兼容层；新代码请改用 app.core.config.settings。"
)


def _is_worker_runtime() -> bool:
    """判断当前 Python 进程是否运行在 Celery Worker 上下文中。"""
    argv = [arg.lower() for arg in sys.argv if arg]
    if not argv:
        return False
    if "celery" not in argv[0]:
        return False
    return "worker" in argv[1:]


def setup_matplotlib_font() -> None:
    """统一配置 Matplotlib 中文字体。"""
    import matplotlib

    if platform.system() == "Windows":
        matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "SimSun"]
    else:
        matplotlib.rcParams["font.sans-serif"] = ["WenQuanYi Micro Hei"]
    matplotlib.rcParams["axes.unicode_minus"] = False


def setup_logging(log_level: int = logging.INFO, logger_name: str = "spec_agent") -> logging.Logger:
    """统一日志初始化，兼容旧模块调用方式。"""
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger
    if "worker" in logger_name.lower():
        filename = "worker.log"
    else:
        worker_logger = logging.getLogger("spec_agent.worker")
        filename = "worker.log" if _is_worker_runtime() and worker_logger.handlers else "app.log"
    return configure_named_logger(logger_name, filename=filename, level=log_level, error_filename="error.log")


def _build_database_config() -> dict[str, Any]:
    """构建旧版数据库配置兼容字典。"""
    return {
        "type": "sqlite",
        "path": "",
        "postgresql": {
            "host": "localhost",
            "port": 5432,
            "user": "postgres",
            "password": "password",
            "database": "spec_agent_db",
        },
    }


def _build_data_storage_config() -> dict[str, str]:
    """构建旧版数据存储配置兼容字典。"""
    return {
        "calibration_curves": str(settings.calibration_curves_root),
        "sample_data": str(settings.spectrum_files_root),
        "analysis_results": str(settings.analysis_results_root),
    }


def _build_paths_config() -> dict[str, str]:
    """构建旧版路径配置兼容字典。"""
    return {
        "outputs": str(settings.outputs_root),
        "logs": str(settings.logs_root),
        "gpc_results": str(settings.outputs_root / "gpc_results"),
        "nmr_results": str(settings.outputs_root / "nmr_results"),
        "raman_results": str(settings.outputs_root / "raman_results"),
        "nmr_dataset": str(settings.spectrum_files_root / "nmr" / "20250804"),
        "gpc_three_color_dir": str(settings.gpc_three_color_dir),
        "gpc_comparison_pdf_dir": str(settings.gpc_comparison_pdf_dir),
        "spectrum_files_root": str(settings.spectrum_files_root),
    }


def _build_services_config() -> dict[str, str]:
    """构建旧版服务配置兼容字典。"""
    return {
        "nmr_server_base_url": settings.nmr_server_base_url,
    }


def _build_resources_config() -> dict[str, str]:
    """构建旧版资源配置兼容字典。"""
    return {
        "backend_root": str(settings.backend_root),
        "resources_root": str(settings.resources_root),
        "acceptance_config": str(settings.acceptance_config_path),
        "solvent_impurities": str(settings.solvent_impurities_path),
        "raman_checkpoints_root": str(settings.raman_checkpoints_root),
        "raman_database_root": str(settings.raman_database_root),
        "raman_tokenizer_root": str(settings.raman_tokenizer_root),
    }


def _build_global_config() -> dict[str, object]:
    """构建旧模块兼容使用的全局配置字典。"""
    return {
        "app_name": "Spec_Agent 智能分析平台",
        "version": "1.0.0",
        "server_host": "0.0.0.0",
        "server_port": 8501,
        "share": False,
        "root_dir": str(settings.backend_root),
        "database": _build_database_config(),
        "data_storage": _build_data_storage_config(),
        "paths": _build_paths_config(),
        "services": _build_services_config(),
        "llm": settings.llm_config.copy(),
        "resources": _build_resources_config(),
    }


GLOBAL_CONFIG = _build_global_config()

__all__ = [
    "COMPATIBILITY_NOTE",
    "GLOBAL_CONFIG",
    "settings",
    "setup_logging",
    "setup_matplotlib_font",
]
