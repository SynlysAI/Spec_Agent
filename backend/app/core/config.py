"""应用配置模块。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_ROOT / ".env")


class Settings:
    """配置对象。

    函数名称: Settings.__init__
    参数说明:
    - 无显式参数，初始化时按项目目录推导默认配置。
    """

    def __init__(self) -> None:
        self.project_root: Path = Path(__file__).resolve().parents[3]
        self.backend_root: Path = self.project_root / "backend"
        self.runtime_root: Path = Path(
            os.getenv("SPEC_AGENT_RUNTIME_ROOT", str(self.project_root / ".runtime"))
        )
        self.upload_root: Path = Path(
            os.getenv("SPEC_AGENT_UPLOAD_ROOT", str(self.runtime_root / "uploads"))
        )
        self.outputs_root: Path = Path(
            os.getenv("SPEC_AGENT_OUTPUT_ROOT", str(self.runtime_root / "outputs"))
        )
        self.logs_root: Path = Path(
            os.getenv("SPEC_AGENT_LOG_ROOT", str(self.backend_root / "logs"))
        )
        self.resources_root: Path = self.backend_root / "resources"
        self.max_upload_size_mb: int = 100
        self.api_prefix: str = "/api/v1"
        self.app_env: str = os.getenv("APP_ENV", "dev")
        self.auth_enabled: bool = os.getenv("AUTH_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.auth_username: str = os.getenv("AUTH_USERNAME", "admin")
        self.auth_password: str = os.getenv("AUTH_PASSWORD", "admin123456")
        self.auth_secret: str = os.getenv("AUTH_SECRET", "")
        self.auth_token_expire_hours: int = int(os.getenv("AUTH_TOKEN_EXPIRE_HOURS", "12"))

        # MongoDB 配置
        self.mongodb_host: str = os.getenv("MONGODB_HOST", "127.0.0.1")
        self.mongodb_port: int = int(os.getenv("MONGODB_PORT", "27017"))
        self.mongodb_username: str = os.getenv("MONGODB_USERNAME", "")
        self.mongodb_password: str = os.getenv("MONGODB_PASSWORD", "")
        self.mongodb_database: str = os.getenv("MONGODB_DATABASE", "spec_agent")

        # RabbitMQ 配置
        self.rabbitmq_host: str = os.getenv("RABBITMQ_HOST", "127.0.0.1")
        self.rabbitmq_port: int = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.rabbitmq_username: str = os.getenv("RABBITMQ_USERNAME", "guest")
        self.rabbitmq_password: str = os.getenv("RABBITMQ_PASSWORD", "guest")
        self.rabbitmq_vhost: str = os.getenv("RABBITMQ_VHOST", "/")
        self.celery_task_queue: str = os.getenv("CELERY_TASK_QUEUE", "spec_agent")

        # NMRServer 外部服务配置
        self.nmr_server_base_url: str = os.getenv("NMR_SERVER_BASE_URL", "http://127.0.0.1:8080")
        self.lcms_infer_url: str = os.getenv("LCMS_INFER_URL", "http://127.0.0.1:9999/infer")
        self.raman_capture_instrument_ip: str = os.getenv("RAMAN_CAPTURE_INSTRUMENT_IP", "47.113.220.254")
        self.raman_capture_callback_url: str = os.getenv(
            "RAMAN_CAPTURE_CALLBACK_URL",
            "http://127.0.0.1:8099/raman/jy/callback",
        )
        self.raman_capture_submit_port: int = int(os.getenv("RAMAN_CAPTURE_SUBMIT_PORT", "7001"))
        self.raman_capture_result_port: int = int(os.getenv("RAMAN_CAPTURE_RESULT_PORT", "7002"))

        # LLM 配置
        self.llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
        self.llm_api_key: str = os.getenv("LLM_API_KEY", "")
        self.llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.agicto.cn/v1")
        self.llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        self.llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "8192"))
        self.llm_timeout: int = int(os.getenv("LLM_TIMEOUT", "60"))
        self.llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "2"))

        # GPC 兼容配置
        self.spectrum_files_root: Path = Path(
            os.getenv("SPECTRUM_FILES_ROOT", str(self.project_root / "sample_data"))
        )
        self.analysis_results_root: Path = Path(os.getenv("ANALYSIS_RESULTS_PATH", str(self.outputs_root)))
        self.calibration_curves_root: Path = Path(
            os.getenv(
                "CALIBRATION_CURVES_PATH",
                str(self.spectrum_files_root / "gpc" / "calibration_curves_json"),
            )
        )
        self.gpc_three_color_dir: Path = Path(
            os.getenv(
                "GPC_THREE_COLOR_DIR",
                str(self.spectrum_files_root / "gpc" / "three_color_curve"),
            )
        )
        self.gpc_comparison_pdf_dir: Path = Path(
            os.getenv(
                "GPC_COMPARISON_PDF_DIR",
                str(self.spectrum_files_root / "gpc" / "spectrum"),
            )
        )

        # 资源文件路径
        self.acceptance_config_path: Path = self.resources_root / "config" / "acceptance.yaml"
        self.lab_collectors_config_path: Path = self.resources_root / "config" / "lab_collectors.yaml"
        self.solvent_impurities_path: Path = self.resources_root / "config" / "solvent_impurities.json"
        self.raman_resources_root: Path = self.resources_root / "raman"
        self.raman_checkpoints_root: Path = self.raman_resources_root / "checkpoints"
        self.raman_database_root: Path = self.raman_resources_root / "database"
        self.raman_tokenizer_root: Path = self.raman_resources_root / "moltokenizer"
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.outputs_root.mkdir(parents=True, exist_ok=True)
        self.logs_root.mkdir(parents=True, exist_ok=True)

    @property
    def mongodb_uri(self) -> str:
        """生成 MongoDB 连接 URI。

        函数名称: mongodb_uri
        参数说明:
        - self: 配置对象实例。
        """
        credential = ""
        if self.mongodb_username:
            credential = self.mongodb_username
            if self.mongodb_password:
                credential = f"{credential}:{self.mongodb_password}"
            credential = f"{credential}@"
        return f"mongodb://{credential}{self.mongodb_host}:{self.mongodb_port}"

    @property
    def rabbitmq_broker_url(self) -> str:
        """生成 RabbitMQ Broker 连接 URI。

        函数名称: rabbitmq_broker_url
        参数说明:
        - self: 配置对象实例。
        """
        vhost = self.rabbitmq_vhost
        if not vhost.startswith("/"):
            vhost = f"/{vhost}"
        return (
            f"amqp://{self.rabbitmq_username}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}{vhost}"
        )

    @property
    def llm_config(self) -> dict[str, object]:
        """返回统一 LLM 配置。"""
        return {
            "model": self.llm_model,
            "api_key": self.llm_api_key,
            "base_url": self.llm_base_url,
            "temperature": self.llm_temperature,
            "max_tokens": self.llm_max_tokens,
            "timeout": self.llm_timeout,
            "max_retries": self.llm_max_retries,
        }


settings = Settings()
