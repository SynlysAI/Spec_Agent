"""配置默认值回归测试。"""

from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path


class TestConfigRuntimeDefaults(unittest.TestCase):
    """验证运行目录与安全默认值。"""

    def test_runtime_defaults_are_safe(self) -> None:
        """显式覆盖为空时应回退到安全默认值。"""
        original = {key: os.environ.get(key) for key in (
            "SPEC_AGENT_RUNTIME_ROOT",
            "SPEC_AGENT_UPLOAD_ROOT",
            "SPEC_AGENT_OUTPUT_ROOT",
            "MONGODB_HOST",
            "MONGODB_PORT",
            "MONGODB_USERNAME",
            "MONGODB_PASSWORD",
            "RABBITMQ_HOST",
            "RABBITMQ_USERNAME",
            "RABBITMQ_PASSWORD",
        )}
        try:
            for key in original:
                os.environ.pop(key, None)
            os.environ["MONGODB_HOST"] = "127.0.0.1"
            os.environ["MONGODB_PORT"] = "27017"
            os.environ["MONGODB_USERNAME"] = ""
            os.environ["MONGODB_PASSWORD"] = ""
            os.environ["RABBITMQ_HOST"] = "127.0.0.1"
            os.environ["RABBITMQ_USERNAME"] = "guest"
            os.environ["RABBITMQ_PASSWORD"] = "guest"
            sys.modules.pop("app.core.config", None)
            config_module = importlib.import_module("app.core.config")
            settings = config_module.Settings()

            self.assertTrue(str(settings.runtime_root).endswith(".runtime"))
            self.assertEqual(settings.mongodb_host, "127.0.0.1")
            self.assertEqual(settings.mongodb_port, 27017)
            self.assertEqual(settings.rabbitmq_host, "127.0.0.1")
            self.assertEqual(settings.rabbitmq_username, "guest")
            self.assertEqual(settings.rabbitmq_password, "guest")
            self.assertTrue(Path(settings.upload_root).exists())
            self.assertTrue(Path(settings.outputs_root).exists())
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            sys.modules.pop("app.core.config", None)
            importlib.import_module("app.core.config")


if __name__ == "__main__":
    unittest.main()
