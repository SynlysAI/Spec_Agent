"""后端日志基础设施测试。"""

from __future__ import annotations

import importlib
import logging
import os
import types
import sys
import tempfile
import unittest
from pathlib import Path


class TestLoggingSetup(unittest.TestCase):
    """验证统一日志配置与应用接入。"""

    def setUp(self) -> None:
        """隔离环境变量与模块缓存。"""
        self.original_runtime_root = os.environ.get("SPEC_AGENT_RUNTIME_ROOT")
        self.original_log_root = os.environ.get("SPEC_AGENT_LOG_ROOT")
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["SPEC_AGENT_RUNTIME_ROOT"] = self.temp_dir.name
        os.environ["SPEC_AGENT_LOG_ROOT"] = str(Path(self.temp_dir.name) / "logs")
        self._clear_modules()

    def tearDown(self) -> None:
        """恢复环境变量并清理临时目录。"""
        self._close_loggers()
        if self.original_runtime_root is None:
            os.environ.pop("SPEC_AGENT_RUNTIME_ROOT", None)
        else:
            os.environ["SPEC_AGENT_RUNTIME_ROOT"] = self.original_runtime_root
        if self.original_log_root is None:
            os.environ.pop("SPEC_AGENT_LOG_ROOT", None)
        else:
            os.environ["SPEC_AGENT_LOG_ROOT"] = self.original_log_root
        self._clear_modules()
        self.temp_dir.cleanup()

    @staticmethod
    def _clear_modules() -> None:
        """清理受测模块缓存，确保测试隔离。"""
        for module_name in (
            "app.core.config",
            "app.core.logging",
            "app.main",
            "app.api.v1.router",
        ):
            sys.modules.pop(module_name, None)

    @staticmethod
    def _close_loggers() -> None:
        """关闭测试过程中创建的日志处理器。"""
        for logger_name in ("spec_agent.app", "spec_agent.worker"):
            logger = logging.getLogger(logger_name)
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                handler.close()

    def test_configure_app_logging_creates_log_files(self) -> None:
        """应用日志初始化后应创建 app 与 error 日志文件。"""
        logging_module = importlib.import_module("app.core.logging")

        logging_module.configure_app_logging()

        logs_dir = Path(self.temp_dir.name) / "logs"
        self.assertTrue((logs_dir / "app.log").exists())
        self.assertTrue((logs_dir / "error.log").exists())

    def test_create_app_initializes_request_logging(self) -> None:
        """创建 FastAPI 应用后应初始化应用日志记录器。"""
        from fastapi import APIRouter

        router_module = types.ModuleType("app.api.v1.router")
        router_module.api_router = APIRouter()
        sys.modules["app.api.v1.router"] = router_module
        main_module = importlib.import_module("app.main")

        main_module.create_app()

        app_logger = logging.getLogger("spec_agent.app")
        file_handler_paths = {
            Path(handler.baseFilename).name
            for handler in app_logger.handlers
            if hasattr(handler, "baseFilename")
        }
        self.assertIn("app.log", file_handler_paths)
        stream_handler_count = sum(
            1
            for handler in app_logger.handlers
            if isinstance(handler, logging.StreamHandler) and not hasattr(handler, "baseFilename")
        )
        self.assertEqual(stream_handler_count, 0)

    def test_configure_worker_logging_creates_worker_log_file(self) -> None:
        """Worker 日志初始化后应创建 worker 日志文件。"""
        logging_module = importlib.import_module("app.core.logging")

        worker_logger = logging_module.configure_worker_logging()

        logs_dir = Path(self.temp_dir.name) / "logs"
        self.assertTrue((logs_dir / "worker.log").exists())
        stream_handler_count = sum(
            1
            for handler in worker_logger.handlers
            if isinstance(handler, logging.StreamHandler) and not hasattr(handler, "baseFilename")
        )
        self.assertEqual(stream_handler_count, 0)


if __name__ == "__main__":
    unittest.main()
