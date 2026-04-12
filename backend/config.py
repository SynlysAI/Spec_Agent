import logging
import os
import platform
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent

# 根据操作系统加载对应的 env 文件
if platform.system() == "Windows":  # Windows
    env_file = ROOT_DIR / ".env"
else:  # Linux/MacOS
    env_file = ROOT_DIR / "linux.env"
    
if env_file.exists():
    load_dotenv(env_file)
else:
    # Fallback to default .env if specific one doesn't exist
    load_dotenv(ROOT_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_path(env_name: str, default_relative_path: str) -> str:
    raw_value = os.getenv(env_name)
    path = Path(raw_value) if raw_value else ROOT_DIR / default_relative_path
    return str(path)


def setup_matplotlib_font():
    """统一配置 Matplotlib 中文字体，适配 Windows / Linux 环境。"""

    import matplotlib

    if platform.system() == "Windows":
        matplotlib.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "SimSun"]
    else:
        matplotlib.rcParams["font.sans-serif"] = ["WenQuanYi Micro Hei"]
    matplotlib.rcParams["axes.unicode_minus"] = False


def setup_logging(log_level=logging.INFO, logger_name="spec_agent"):
    """统一主项目日志格式，避免重复注册 handler。"""
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


def _build_global_config():
    """谱图解析全局配置"""
    spectrum_files_root = os.getenv("SPECTRUM_FILES_ROOT", r"E:\spectrum_files")
    database_path = os.getenv("SPECTRUM_DB_PATH", r"E:\spectrum_dbs\spectrum.db")
    outputs_dir = _resolve_path("OUTPUTS_PATH", str(ROOT_DIR.parent / "outputs"))
    calibration_curves = os.path.join(spectrum_files_root, "gpc", "calibration_curves_json")

    data_storage = {
        "calibration_curves": _resolve_path("CALIBRATION_CURVES_PATH", calibration_curves),
        "sample_data": _resolve_path("SAMPLE_DATA_PATH", spectrum_files_root),
        "analysis_results": _resolve_path("ANALYSIS_RESULTS_PATH", outputs_dir),
    }

    return {
        "app_name": "Spec_Agent 智能分析平台",
        "version": os.getenv("SPEC_AGENT_VERSION", "1.0.0"),
        "server_host": os.getenv("SPEC_AGENT_HOST", "0.0.0.0"),
        "server_port": int(os.getenv("SPEC_AGENT_PORT", "8501")),
        "share": _env_bool("SPEC_AGENT_SHARE", False),
        "root_dir": str(ROOT_DIR),
        "database": {
            "type": os.getenv("APP_DB_TYPE", "sqlite"),
            "path": database_path,
            "postgresql": {
                "host": os.getenv("DB_HOST", "localhost"),
                "port": int(os.getenv("DB_PORT", "5432")),
                "user": os.getenv("DB_USER", "postgres"),
                "password": os.getenv("DB_PASSWORD", "password"),
                "database": os.getenv("DB_NAME", "spec_agent_db"),
            },
        },
        "data_storage": data_storage,
        "paths": {
            "outputs": outputs_dir,
            "gpc_results": os.path.join(outputs_dir, "gpc_results"),
            "nmr_results": os.path.join(outputs_dir, "nmr_results"),
            "raman_results": os.path.join(outputs_dir, "raman_results"),
            # 示例的NMR核磁实验数据
            "nmr_dataset": _resolve_path(
                "NMR_DATASET_PATH",
                os.path.join(spectrum_files_root, "nmr", "20250804")
            ),
            "gpc_three_color_dir": os.getenv(
                "GPC_THREE_COLOR_DIR",
                os.path.join(spectrum_files_root, "gpc", "three_color_curve"),
            ),
            # GPC 对比用：在目录中按样品名匹配测试报告 PDF（与 GPCValidator.process_gpc_data 一致）
            "gpc_comparison_pdf_dir": os.getenv(
                "GPC_COMPARISON_PDF_DIR",
                os.path.join(spectrum_files_root, "gpc", "spectrum"),
            ),
            "spectrum_files_root": spectrum_files_root,
        },
        "services": {
            "nmr_server_base_url": os.getenv("NMR_SERVER_BASE_URL", "http://100.84.59.58:8080"),
        },
        "llm": {
            "model": os.getenv("LLM_MODEL", "deepseek-chat"),
            "api_key": os.getenv("LLM_API_KEY", ""),
            "base_url": os.getenv("LLM_BASE_URL", "https://api.agicto.cn/v1"),
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
            "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "8192")),
            "timeout": int(os.getenv("LLM_TIMEOUT", "60")),
            "max_retries": int(os.getenv("LLM_MAX_RETRIES", "2")),
        },
    }


# 模块级应用配置单例（PEP 8：模块常量使用全大写命名）
GLOBAL_CONFIG = _build_global_config()
