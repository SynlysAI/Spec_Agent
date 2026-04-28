"""Raman 光谱预处理测试。"""

from __future__ import annotations

import unittest

import torch

from analysis.raman.greedy_search import preprocess_spectrum


class TestPreprocessSpectrum(unittest.TestCase):
    """验证谱图预处理输出顺序。"""

    def test_preprocess_spectrum_keeps_descending_model_order(self) -> None:
        """无论输入方向如何，输出都应统一为倒序 1024 点。"""
        ascending = preprocess_spectrum(
            x0=400,
            x1=4000,
            intensities=[0.0, 0.5, 1.0],
            target_range=(400, 4000),
            target_points=3,
            spectype="raman",
        )
        descending = preprocess_spectrum(
            x0=4000,
            x1=400,
            intensities=[1.0, 0.5, 0.0],
            target_range=(400, 4000),
            target_points=3,
            spectype="raman",
        )

        expected = torch.tensor([[[1.0, 0.5, 0.0]]], dtype=torch.float32)
        self.assertTrue(torch.allclose(ascending, expected))
        self.assertTrue(torch.allclose(descending, expected))


if __name__ == "__main__":
    unittest.main()
