"""任务执行器注册表测试。"""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

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
        self.assertEqual(detect_artifact_type(Path("a.png")), "image")
        self.assertEqual(detect_artifact_type(Path("a.md")), "text")
        self.assertEqual(detect_artifact_type(Path("a.pdf")), "pdf")
        self.assertEqual(detect_artifact_type(Path("a.bin")), "other")

    def test_prepare_nmr_input_path_descends_into_single_sample_dir_from_zip(self) -> None:
        """ZIP 解压后若仅含一个样品目录，应自动下钻到样品目录。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            zip_path = temp_path / "sample.zip"
            output_dir = temp_path / "task_output"
            output_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, "w") as zip_file:
                zip_file.writestr("3-H/acqu", "")
                zip_file.writestr("3-H/acqus", "")
                zip_file.writestr("3-H/fid", "")
                zip_file.writestr("3-H/pdata/1/1r", "")

            prepared_path = NmrTaskExecutor._prepare_nmr_input_path(output_dir=output_dir, input_path=str(zip_path))

            self.assertTrue(prepared_path.endswith("3-H"))


if __name__ == "__main__":
    unittest.main()
