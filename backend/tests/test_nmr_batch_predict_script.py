"""批量 NMR 反推脚本测试。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FakeNmrServerService:
    """用于测试的 NMRServer 服务桩。"""

    def reverse_predict(
        self,
        h_shifts_input: str,
        h_split_input: str,
        c_shifts_input: str,
        formula: str,
        allowed_elements: str,
        candidates: str,
    ) -> list[dict]:
        """返回固定的反向预测结果。"""
        return [
            {"smiles": "C1=CC=CC=C1", "score": 0.9},
            {"smiles": "CCO", "score": 0.5},
        ]

    def database_search(
        self,
        h_shifts_input: str,
        h_split_input: str,
        c_shifts_input: str,
        num_search: int,
        topk: int,
        allowed_elements: str,
    ) -> list[dict]:
        """返回固定的数据库检索结果。"""
        return [
            {"smiles": "CCN", "score": 0.8},
        ]


class FailingNmrServerService(FakeNmrServerService):
    """用于测试异常分支的 NMRServer 服务桩。"""

    def reverse_predict(
        self,
        h_shifts_input: str,
        h_split_input: str,
        c_shifts_input: str,
        formula: str,
        allowed_elements: str,
        candidates: str,
    ) -> list[dict]:
        """模拟反向预测失败。"""
        raise RuntimeError("reverse failed")


class TestNmrBatchPredictScript(unittest.TestCase):
    """验证批量 NMR 反推脚本。"""

    def test_build_result_dataframe_appends_prediction_columns(self) -> None:
        """结果表应保留原列并追加预测结果列。"""
        import sys

        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        from scripts.nmr_predict_batch import build_result_dataframe

        source = pd.DataFrame([{
            "H谱文件路径": "h_path",
            "H谱文件名": "1-H",
            "C谱文件路径": "c_path",
            "C谱文件名": "1-C",
            "H谱化学位移": "1.23,2.34",
            "H谱峰裂分类型": "s,d",
            "C谱化学位移": "10.10,20.20",
        }])

        result = build_result_dataframe(
            dataframe=source,
            service=FakeNmrServerService(),
            num_search=500,
            topk=10,
            formula="",
            allowed_elements="",
            candidates="",
        )

        self.assertEqual(result.columns[-4:].tolist(), [
            "reverse_predict_smiles",
            "database_predict_smiles",
            "reverse_res",
            "database_res",
        ])
        self.assertEqual(
            json.loads(result.loc[0, "reverse_predict_smiles"]),
            ["C1=CC=CC=C1", "CCO"],
        )
        self.assertEqual(
            json.loads(result.loc[0, "database_predict_smiles"]),
            ["CCN"],
        )
        self.assertEqual(
            json.loads(result.loc[0, "reverse_res"])[0]["smiles"],
            "C1=CC=CC=C1",
        )
        self.assertEqual(
            json.loads(result.loc[0, "database_res"])[0]["smiles"],
            "CCN",
        )

    def test_build_result_dataframe_keeps_error_in_result_columns(self) -> None:
        """单行预测失败时应写入错误信息而不是中断整批。"""
        import sys

        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        from scripts.nmr_predict_batch import build_result_dataframe

        source = pd.DataFrame([{
            "H谱文件路径": "h_path",
            "H谱文件名": "1-H",
            "C谱文件路径": "c_path",
            "C谱文件名": "1-C",
            "H谱化学位移": "1.23,2.34",
            "H谱峰裂分类型": "s,d",
            "C谱化学位移": "10.10,20.20",
        }])

        result = build_result_dataframe(
            dataframe=source,
            service=FailingNmrServerService(),
            num_search=500,
            topk=10,
            formula="",
            allowed_elements="",
            candidates="",
        )

        self.assertEqual(json.loads(result.loc[0, "reverse_predict_smiles"]), [])
        self.assertEqual(json.loads(result.loc[0, "database_predict_smiles"]), [])
        self.assertEqual(
            json.loads(result.loc[0, "reverse_res"])["error"],
            "reverse failed",
        )
        self.assertEqual(
            json.loads(result.loc[0, "database_res"])["error"],
            "reverse failed",
        )

    def test_export_result_excel_writes_new_file(self) -> None:
        """导出结果表时应生成新的 Excel 文件。"""
        import sys

        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        from scripts.nmr_predict_batch import export_result_excel

        dataframe = pd.DataFrame([{
            "H谱文件路径": "h_path",
            "reverse_predict_smiles": "[\"CCO\"]",
        }])

        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "result.xlsx"
            exported_path = export_result_excel(dataframe=dataframe, output_path=output_path)

            self.assertEqual(exported_path, output_path)
            self.assertTrue(exported_path.exists())


if __name__ == "__main__":
    unittest.main()
