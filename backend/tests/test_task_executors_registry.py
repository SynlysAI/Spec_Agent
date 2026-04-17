"""任务执行器注册表测试。"""

from __future__ import annotations

import unittest

from app.services.task_executors import (
    GpcTaskExecutor,
    IrRamanTaskExecutor,
    LcmsTaskExecutor,
    NmrTaskExecutor,
    detect_artifact_type,
    task_executor_registry,
)


class TestTaskExecutorRegistry(unittest.TestCase):
    """验证任务类型与执行器映射。"""

    def test_registry_contains_expected_executors(self) -> None:
        """各任务类型应映射到固定执行器。"""
        executors = task_executor_registry._executors
        self.assertIsInstance(executors["gpc_analysis"], GpcTaskExecutor)
        self.assertIsInstance(executors["nmr_analysis"], NmrTaskExecutor)
        self.assertIsInstance(executors["ir_analysis"], IrRamanTaskExecutor)
        self.assertIsInstance(executors["raman_analysis"], IrRamanTaskExecutor)
        self.assertIsInstance(executors["lcms_analysis"], LcmsTaskExecutor)

    def test_detect_artifact_type(self) -> None:
        """产物类型识别应符合约定。"""
        from pathlib import Path

        self.assertEqual(detect_artifact_type(Path("a.png")), "image")
        self.assertEqual(detect_artifact_type(Path("a.md")), "text")
        self.assertEqual(detect_artifact_type(Path("a.pdf")), "pdf")
        self.assertEqual(detect_artifact_type(Path("a.bin")), "other")


if __name__ == "__main__":
    unittest.main()
