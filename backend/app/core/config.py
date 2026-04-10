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
        self.upload_root: Path = self.project_root / "uploads"
        self.outputs_root: Path = self.project_root / "outputs"
        self.max_upload_size_mb: int = 100
        self.api_prefix: str = "/api/v1"
        self.app_env: str = os.getenv("APP_ENV", "dev")
        self.source_spec_agent_root: Path = Path(
            os.getenv("SOURCE_SPEC_AGENT_ROOT", "E:/github_project/Spec_Agent")
        )

        # MongoDB 配置
        self.mongodb_host: str = os.getenv("MONGODB_HOST", "100.84.59.58")
        self.mongodb_port: int = int(os.getenv("MONGODB_PORT", "27018"))
        self.mongodb_username: str = os.getenv("MONGODB_USERNAME", "admin")
        self.mongodb_password: str = os.getenv("MONGODB_PASSWORD", "password123")
        self.mongodb_database: str = os.getenv("MONGODB_DATABASE", "spec_agent")

        # RabbitMQ 配置
        self.rabbitmq_host: str = os.getenv("RABBITMQ_HOST", "100.84.59.58")
        self.rabbitmq_port: int = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.rabbitmq_username: str = os.getenv("RABBITMQ_USERNAME", "admin")
        self.rabbitmq_password: str = os.getenv("RABBITMQ_PASSWORD", "password123")
        self.rabbitmq_vhost: str = os.getenv("RABBITMQ_VHOST", "/")

    @property
    def mongodb_uri(self) -> str:
        """生成 MongoDB 连接 URI。

        函数名称: mongodb_uri
        参数说明:
        - self: 配置对象实例。
        """
        return (
            f"mongodb://{self.mongodb_username}:{self.mongodb_password}"
            f"@{self.mongodb_host}:{self.mongodb_port}"
        )

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


settings = Settings()
