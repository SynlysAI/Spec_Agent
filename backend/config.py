"""旧目录结构兼容配置层。"""

from __future__ import annotations

import logging
import platform

from app.core.config import settings


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
    logger.setLevel(log_level)

    if not logger.handlers:
        stream_handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - [%(filename)s:%(lineno)d] - %(levelname)s - %(message)s"
        )
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        logger.propagate = False

    return logger


def _build_global_config() -> dict[str, object]:
    """构建旧模块兼容使用的全局配置字典。"""
    return {
        "app_name": "Spec_Agent 智能分析平台",
        "version": "1.0.0",
        "server_host": "0.0.0.0",
        "server_port": 8501,
        "share": False,
        "root_dir": str(settings.backend_root),
        "database": {
            "type": "sqlite",
            "path": "",
            "postgresql": {
                "host": "localhost",
                "port": 5432,
                "user": "postgres",
                "password": "password",
                "database": "spec_agent_db",
            },
        },
        "data_storage": {
            "calibration_curves": str(settings.calibration_curves_root),
            "sample_data": str(settings.spectrum_files_root),
            "analysis_results": str(settings.analysis_results_root),
        },
        "paths": {
            "outputs": str(settings.outputs_root),
            "gpc_results": str(settings.outputs_root / "gpc_results"),
            "nmr_results": str(settings.outputs_root / "nmr_results"),
            "raman_results": str(settings.outputs_root / "raman_results"),
            "nmr_dataset": str(settings.spectrum_files_root / "nmr" / "20250804"),
            "gpc_three_color_dir": str(settings.gpc_three_color_dir),
            "gpc_comparison_pdf_dir": str(settings.gpc_comparison_pdf_dir),
            "spectrum_files_root": str(settings.spectrum_files_root),
        },
        "services": {
            "nmr_server_base_url": settings.nmr_server_base_url,
        },
        "llm": settings.llm_config.copy(),
        "resources": {
            "backend_root": str(settings.backend_root),
            "resources_root": str(settings.resources_root),
            "acceptance_config": str(settings.acceptance_config_path),
            "solvent_impurities": str(settings.solvent_impurities_path),
            "raman_checkpoints_root": str(settings.raman_checkpoints_root),
            "raman_database_root": str(settings.raman_database_root),
            "raman_tokenizer_root": str(settings.raman_tokenizer_root),
        },
    }


GLOBAL_CONFIG = _build_global_config()
