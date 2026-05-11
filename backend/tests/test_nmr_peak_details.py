"""NMR 峰明细结构测试。"""

from __future__ import annotations

import unittest

from analysis.nmr.multiplet import MultipletResult
from app.services.task_executors import sanitize_nmr_structured_data


def _make_multiplet_result(
    pattern: str,
    center_ppm: float,
    peak_type: str,
    j_values: list[float] | None = None,
) -> MultipletResult:
    """构造测试用多重峰结果对象。"""
    return MultipletResult(
        pattern=pattern,
        center_ppm=center_ppm,
        j_values=j_values or [],
        sub_peaks=[(center_ppm, 1.0, 0.01)],
        intensity_ratio=[1.0],
        region_start=center_ppm + 0.01,
        region_end=center_ppm - 0.01,
        peak_type=peak_type,
    )


class TestNmrPeakDetails(unittest.TestCase):
    """验证 NMR 峰明细结构。"""

    def test_sanitize_nmr_structured_data_keeps_peak_details(self) -> None:
        """清洗任务结果时应保留峰识别明细。"""
        structured = sanitize_nmr_structured_data({
            "nmr_results": [{
                "sample_name": "2-H",
                "integration_results": {"【目标峰】 4 (d (J=3.6 Hz))": 2521650.13},
                "normalized_results": {"【目标峰】 4 (d (J=3.6 Hz))": 26.5006},
                "integration_regions": [["【目标峰】 4 (d (J=3.6 Hz))", 3.10, 3.20, 3.16]],
                "metadata": {"nucleus": "1H", "solvent": "CDCl3"},
                "peak_details": [{
                    "peak_index": 4,
                    "peak_name": "【目标峰】 4 (d (J=3.6 Hz))",
                    "peak_type": "目标峰",
                    "multiplet_type": "d",
                    "j_values_hz": [3.6],
                    "peak_position_ppm": 3.16,
                    "ppm_range": [3.10, 3.20],
                    "integration_result": 2521650.13,
                    "normalized_result": 26.5006,
                }],
            }],
            "summary_rows": [],
        })

        peak_details = structured["nmr_results"][0]["peak_details"]
        self.assertEqual(peak_details[0]["peak_index"], 4)
        self.assertEqual(peak_details[0]["multiplet_type"], "d")
        self.assertEqual(peak_details[0]["j_values_hz"], [3.6])

    def test_build_peak_details_aligns_regions_and_integrals(self) -> None:
        """峰明细应将区域信息、多重峰信息和积分结果对齐。"""
        from app.modules.nmr.export_service import build_peak_details

        integration_regions = [
            ("【Impurity-Water】", 1.57, 1.67, 1.62),
            ("【目标峰】 4 (d (J=3.6 Hz))", 3.10, 3.20, 3.16),
            ("【Solvent-Solvent (CHCl3)】(内标峰)", 7.25, 7.27, 7.26),
        ]
        multiplet_results = [
            _make_multiplet_result("s", 1.62, "Impurity-Water"),
            _make_multiplet_result("d", 3.16, "目标峰", [3.6]),
            _make_multiplet_result("s", 7.26, "Solvent-Solvent (CHCl3)"),
        ]
        integration_results = {
            "【Impurity-Water】": 101660.53,
            "【目标峰】 4 (d (J=3.6 Hz))": 2521650.13,
            "【Solvent-Solvent (CHCl3)】(内标峰)": 95154.25,
        }
        normalized_results = {
            "【Impurity-Water】": 1.0684,
            "【目标峰】 4 (d (J=3.6 Hz))": 26.5006,
            "【Solvent-Solvent (CHCl3)】(内标峰)": 1.0,
        }

        peak_details = build_peak_details(
            integration_regions=integration_regions,
            multiplet_results=multiplet_results,
            integration_results=integration_results,
            normalized_results=normalized_results,
        )

        self.assertEqual(peak_details[0]["peak_type"], "杂质")
        self.assertEqual(peak_details[1]["peak_index"], 2)
        self.assertEqual(peak_details[1]["peak_type"], "目标峰")
        self.assertEqual(peak_details[1]["j_values_hz"], [3.6])
        self.assertEqual(peak_details[2]["peak_type"], "溶剂")
        self.assertEqual(peak_details[2]["normalized_result"], 1.0)


if __name__ == "__main__":
    unittest.main()
