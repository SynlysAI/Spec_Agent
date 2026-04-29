"""NMR 目标峰导出相关测试。"""

from __future__ import annotations

import json
import unittest

from analysis.nmr.multiplet import MultipletResult
from app.modules.nmr.workflow import NMRPathWorkflow


def _make_multiplet_result(
    pattern: str,
    center_ppm: float,
    peak_type: str,
) -> MultipletResult:
    """构造测试用多重峰结果对象。"""
    return MultipletResult(
        pattern=pattern,
        center_ppm=center_ppm,
        j_values=[],
        sub_peaks=[(center_ppm, 1.0, 0.01)],
        intensity_ratio=[1.0],
        region_start=center_ppm + 0.01,
        region_end=center_ppm - 0.01,
        peak_type=peak_type,
    )


class TestNmrPeakExport(unittest.TestCase):
    """验证 NMR 目标峰结构化导出逻辑。"""

    def test_build_peak_annotations_keeps_role_and_pattern(self) -> None:
        """应为每个积分区域补充峰角色与裂分模式。"""
        from app.modules.nmr.export_service import build_peak_annotations

        integration_regions = [
            ("【TMS-TMS】", 0.00, 0.01, 0.00),
            ("【目标峰】 2", 3.18, 3.20, 3.19),
            ("【目标峰】 3 (dd (J=8.9, 2.1 Hz))", 7.02, 7.06, 7.04),
            ("【Solvent-Solvent (CHCl3)】", 7.26, 7.27, 7.27),
        ]
        multiplet_results = [
            _make_multiplet_result("s", 0.00, "TMS-TMS"),
            _make_multiplet_result("s", 3.19, "目标峰"),
            _make_multiplet_result("dd", 7.04, "目标峰"),
            _make_multiplet_result("s", 7.27, "Solvent-Solvent (CHCl3)"),
        ]

        peak_annotations = build_peak_annotations(integration_regions, multiplet_results)

        self.assertEqual(peak_annotations[0]["peak_role"], "tms")
        self.assertFalse(peak_annotations[0]["is_target"])
        self.assertEqual(peak_annotations[1]["peak_role"], "target")
        self.assertTrue(peak_annotations[1]["is_target"])
        self.assertEqual(peak_annotations[2]["multiplet_pattern"], "dd")
        self.assertEqual(peak_annotations[3]["peak_role"], "solvent")

    def test_build_target_peak_export_row_filters_non_target_peaks(self) -> None:
        """导出行应排除杂质、溶剂与 TMS，并将复杂裂分归并为 m。"""
        from app.modules.nmr.export_service import build_target_peak_export_row

        row = build_target_peak_export_row(
            sample_path=r"E:\spectrum_files\nmr\偶氮砜小分子核磁原件+结构\1-H",
            nmr_result={
                "metadata": {"nucleus": "1H", "solvent": "CDCl3"},
                "peak_annotations": [
                    {
                        "region_name": "【TMS-TMS】",
                        "peak_position": 0.00,
                        "peak_role": "tms",
                        "is_target": False,
                        "multiplet_pattern": "s",
                    },
                    {
                        "region_name": "【Impurity-Water】",
                        "peak_position": 1.62,
                        "peak_role": "impurity",
                        "is_target": False,
                        "multiplet_pattern": "s",
                    },
                    {
                        "region_name": "【目标峰】 4",
                        "peak_position": 3.19,
                        "peak_role": "target",
                        "is_target": True,
                        "multiplet_pattern": "s",
                    },
                    {
                        "region_name": "【目标峰】 6 (dd (J=8.9, 2.1 Hz))",
                        "peak_position": 7.04,
                        "peak_role": "target",
                        "is_target": True,
                        "multiplet_pattern": "dd",
                    },
                    {
                        "region_name": "【Solvent-Solvent (CHCl3)】",
                        "peak_position": 7.27,
                        "peak_role": "solvent",
                        "is_target": False,
                        "multiplet_pattern": "s",
                    },
                ],
            },
        )

        self.assertEqual(row["文件名"], '="1-H"')
        self.assertEqual(row["所属谱类型(H/C)"], "H")
        self.assertEqual(row["溶剂"], "CDCl3")
        self.assertEqual(row["目标峰化学位移"], "3.19,7.04")
        self.assertEqual(row["峰裂分类型"], "s,m")
        peaks_json = json.loads(row["全部峰信息JSON"])
        self.assertEqual(peaks_json[0]["peak_role"], "tms")
        self.assertEqual(peaks_json[2]["peak_position"], 3.19)
        self.assertEqual(peaks_json[3]["multiplet_pattern"], "dd")

    def test_build_target_peak_export_row_leaves_carbon_split_empty(self) -> None:
        """13C 导出不应输出裂分峰类型。"""
        from app.modules.nmr.export_service import build_target_peak_export_row

        row = build_target_peak_export_row(
            sample_path=r"E:\spectrum_files\nmr\偶氮砜小分子核磁原件+结构\1-C",
            nmr_result={
                "metadata": {"nucleus": "13C", "solvent": "CDCl3"},
                "peak_annotations": [
                    {
                        "region_name": "【目标峰】 1",
                        "peak_position": 34.83,
                        "peak_role": "target",
                        "is_target": True,
                        "multiplet_pattern": "s",
                    },
                    {
                        "region_name": "【Solvent-Solvent (CDCl3)】",
                        "peak_position": 76.98,
                        "peak_role": "solvent",
                        "is_target": False,
                        "multiplet_pattern": "s",
                    },
                    {
                        "region_name": "【目标峰】 5",
                        "peak_position": 127.37,
                        "peak_role": "target",
                        "is_target": True,
                        "multiplet_pattern": "s",
                    },
                ],
            },
        )

        self.assertEqual(row["文件路径"], '="E:\\spectrum_files\\nmr\\偶氮砜小分子核磁原件+结构\\1-C"')
        self.assertEqual(row["所属谱类型(H/C)"], "C")
        self.assertEqual(row["溶剂"], "CDCl3")
        self.assertEqual(row["目标峰化学位移"], "34.83,127.37")
        self.assertEqual(row["峰裂分类型"], "")

    def test_workflow_serialization_keeps_peak_annotations(self) -> None:
        """工作流序列化结果时应保留结构化峰信息。"""
        workflow = NMRPathWorkflow()
        nmr_results = [{
            "sample_name": "demo",
            "integration_results": {},
            "normalized_results": {},
            "integration_regions": [("【目标峰】 1", 1.0, 1.1, 1.05)],
            "metadata": {"nucleus": "1H"},
            "peak_annotations": [{
                "peak_position": 1.05,
                "peak_role": "target",
                "is_target": True,
                "multiplet_pattern": "s",
            }],
            "peak_details": [{
                "peak_index": 1,
                "peak_name": "【目标峰】 1",
                "peak_type": "目标峰",
                "multiplet_type": "s",
                "j_values_hz": [],
                "peak_position_ppm": 1.05,
                "ppm_range": [1.0, 1.1],
                "integration_result": None,
                "normalized_result": None,
            }],
        }]

        serialized = workflow._build_serializable_nmr_results(nmr_results)

        self.assertIn("peak_annotations", serialized[0])
        self.assertEqual(serialized[0]["peak_annotations"][0]["peak_position"], 1.05)
        self.assertIn("peak_details", serialized[0])
        self.assertEqual(serialized[0]["peak_details"][0]["peak_position_ppm"], 1.05)


if __name__ == "__main__":
    unittest.main()
