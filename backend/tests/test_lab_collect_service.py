"""实验室数据采集服务测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.schemas.lab_collect import LabCollectRunRecord
from app.schemas.lab_collect import MolecularStatisticsData
from app.schemas.lab_collect import LabCollectRunRequest
from app.schemas.lab_collect import LabCollectRunSummary
from app.services.lab_collect_service import CollectCandidate
from app.services.lab_collect_service import LabCollectService


class TestLabCollectService(unittest.TestCase):
    """验证实验室数据采集服务核心逻辑。"""

    def test_build_date_list(self) -> None:
        """日期范围应按天正确展开。"""
        dates = LabCollectService._build_date_list("2026-04-17", "2026-04-19")
        self.assertEqual(dates, ["2026-04-17", "2026-04-18", "2026-04-19"])

    def test_normalize_sample_name(self) -> None:
        """样品名标准化应符合检索预期。"""
        normalized = LabCollectService._normalize_sample_name("GPC_03_20240924-1 Cal001")
        self.assertEqual(normalized, "gpc_03_20240924_1_cal001")

    def test_pick_gpc_experiment_json_prefers_param_like_name(self) -> None:
        """GPC 参数 JSON 应优先选择更像参数文件的名称。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            other = root / "note.json"
            param = root / "params.json"
            other.write_text("{}", encoding="utf-8")
            param.write_text("{}", encoding="utf-8")
            selected = LabCollectService._pick_gpc_experiment_json([other, param])
            self.assertEqual(selected.name, "params.json")

    def test_append_gpc_experiment_json_meta(self) -> None:
        """GPC JSON 内容应能提升到 sample_meta。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            json_file = root / "experiment_params.json"
            json_file.write_text(json.dumps({"flow_rate": 1.0}, ensure_ascii=False), encoding="utf-8")
            sample_meta: dict[str, object] = {}
            LabCollectService._append_gpc_experiment_json_meta(sample_meta=sample_meta, json_files=[json_file])
            self.assertEqual(sample_meta["experiment_json_name"], "experiment_params.json")
            self.assertEqual(sample_meta["experiment_json_data"], {"flow_rate": 1.0})

    def test_append_gpc_experiment_json_meta_keeps_parse_error(self) -> None:
        """GPC JSON 解析失败时不应抛错，应保留错误信息。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            json_file = root / "params.json"
            json_file.write_text("{bad json", encoding="utf-8")
            sample_meta: dict[str, object] = {}
            LabCollectService._append_gpc_experiment_json_meta(sample_meta=sample_meta, json_files=[json_file])
            self.assertEqual(sample_meta["experiment_json_name"], "params.json")
            self.assertIn("experiment_json_parse_error", sample_meta)

    def test_build_local_sample_path_converts_raman_dat_to_txt_name(self) -> None:
        """Raman DAT 文件落盘时应改为同名 TXT。"""
        candidate = CollectCandidate(
            spectrum_type="raman",
            source_date="2026-05-11",
            sample_name="20260511112859936.dat",
            remote_path=Path("E:/spectrum_files/raman/20260511112859936.dat"),
            remote_date_dir=Path("E:/spectrum_files/raman"),
            sample_mode="file",
            local_root=Path("E:/mock/local"),
            share_key="raman_lab",
            patterns=["*.txt", "*.csv", "*.dat"],
        )
        local_sample_path = LabCollectService._build_local_sample_path(
            candidate=candidate,
            local_date_dir=Path("E:/mock/local/2026-05-11"),
        )
        self.assertEqual(local_sample_path.name, "20260511112859936.txt")

    def test_extract_raman_shift_value_rows(self) -> None:
        """Raman DAT 文件应提取 RamanShift 与 Value 两列。"""
        lines = [
            "bGennerate:0",
            'capture_settings:{"laser":"785"}',
            "Pixel\tWavelength\tRamanShift\tValue",
            "1\t783.174\t-29.69\t6321.000",
            "2\t783.369\t-26.52\t12078.000",
        ]
        extracted_rows = LabCollectService._extract_raman_shift_value_rows(
            lines=lines,
            source_path=Path("E:/mock/raman.dat"),
        )
        self.assertEqual(extracted_rows, ["-29.69\t6321.000", "-26.52\t12078.000"])

    def test_convert_raman_dat_to_txt_extracts_capture_settings(self) -> None:
        """Raman DAT 转换后应生成两列 TXT，并保留采集参数。"""
        dat_content = "\n".join(
            [
                "bGennerate:0",
                'capture_settings:{"laser":"785","acquisitionMode":1}',
                "Pixel\tWavelength\tRamanShift\tValue",
                "1\t783.174\t-29.69\t6321.000",
                "2\t783.369\t-26.52\t12078.000",
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "sample.dat"
            target_path = root / "sample.txt"
            source_path.write_text(dat_content, encoding="utf-8")

            sample_meta = LabCollectService._convert_raman_dat_to_txt(
                source_path=source_path,
                target_path=target_path,
            )

            self.assertTrue(target_path.exists())
            self.assertEqual(
                target_path.read_text(encoding="utf-8"),
                "-29.69\t6321.000\n-26.52\t12078.000\n",
            )
            self.assertEqual(sample_meta["capture_settings"], {"laser": "785", "acquisitionMode": 1})
            self.assertEqual(sample_meta["source_file_format"], "dat")
            self.assertEqual(sample_meta["converted_to_format"], "txt")

    def test_resolve_collect_patterns_appends_raman_dat(self) -> None:
        """Raman 采集规则应自动补充 DAT 匹配。"""
        patterns = LabCollectService._resolve_collect_patterns("raman", ["*.txt", "*.csv"])
        self.assertIn("*.dat", patterns)

    def test_lab_collect_request_overwrite_existing_defaults_false(self) -> None:
        """采集请求默认不覆盖已入库样品。"""
        payload = LabCollectRunRequest(collect_date="2026-04-21", spectrum_types=["ir"])
        self.assertFalse(payload.overwrite_existing)

    def test_build_empty_type_summary_includes_skipped(self) -> None:
        """分类型汇总应包含 skipped 字段。"""
        summary = LabCollectService._build_empty_type_summary()
        self.assertEqual(summary["skipped"], 0)

    def test_collect_single_candidate_skips_existing_when_not_overwriting(self) -> None:
        """未勾选覆盖时，数据库已存在样品应直接跳过。"""
        service = LabCollectService()
        candidate = CollectCandidate(
            spectrum_type="ir",
            source_date="2026-04-21",
            sample_name="sample_001.txt",
            remote_path=Path("E:/mock/source/sample_001.txt"),
            remote_date_dir=Path("E:/mock/source"),
            sample_mode="file",
            local_root=Path("E:/mock/local"),
            share_key="ir_lab",
            patterns=["*.txt"],
        )
        existing = SimpleNamespace(sample_id="sp_existing", collect_count=1, created_at=datetime.now())
        with patch("app.services.lab_collect_service.SpectrumSampleRepository.find_by_sample_key", return_value=existing):
            result = service._collect_single_candidate(
                run_id="run_001",
                candidate=candidate,
                overwrite_existing=False,
            )
        self.assertEqual(result.action, "skipped")
        self.assertEqual(result.sample_id, "sp_existing")

    def test_run_collect_prefilters_existing_candidates_when_overwrite_disabled(self) -> None:
        """未勾选覆盖且样品已入库时，不应再逐条执行单样品采集。"""
        now = datetime.now()
        candidates = [
            CollectCandidate(
                spectrum_type="ir",
                source_date="2026-04-21",
                sample_name=f"sample_{index:03d}.txt",
                remote_path=Path(f"E:/mock/source/sample_{index:03d}.txt"),
                remote_date_dir=Path("E:/mock/source/2026-04-21"),
                sample_mode="file",
                local_root=Path("E:/mock/local"),
                share_key="ir_lab",
                patterns=["*.txt"],
            )
            for index in range(5)
        ]
        run_record = LabCollectRunRecord(
            run_id="run_001",
            status="QUEUED",
            spectrum_types=["ir"],
            overwrite_existing=False,
            date_from="2026-04-21",
            date_to="2026-04-21",
            trigger_mode="single_date",
            config_snapshot={},
            summary=LabCollectRunSummary(),
            errors=[],
            started_at=None,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        existing_keys = {f"ir:2026-04-21:sample_{index:03d}.txt" for index in range(5)}

        with patch.object(LabCollectService, "_ensure_indexes", return_value=None):
            service = LabCollectService()
        with (
            patch(
                "app.services.lab_collect_service.LabCollectRunRepository.find_by_run_id",
                return_value=run_record,
            ),
            patch("app.services.lab_collect_service.LabCollectRunRepository.save") as save_mock,
            patch.object(service, "_scan_candidates", return_value=candidates),
            patch(
                "app.services.lab_collect_service.SpectrumSampleRepository.find_existing_sample_keys",
                return_value=existing_keys,
                create=True,
            ),
            patch.object(service, "_collect_single_candidate") as collect_mock,
        ):
            service.run_collect(run_id="run_001")

        collect_mock.assert_not_called()
        self.assertEqual(run_record.summary.total_candidates, 5)
        self.assertEqual(run_record.summary.skipped, 5)
        self.assertEqual(run_record.summary.progress, 100)
        self.assertLessEqual(save_mock.call_count, 6)

    def test_delete_sample_removes_record_files_and_local_storage(self) -> None:
        """删除样本时应同时移除主档、文件清单和本地存储。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            local_sample_path = Path(temp_dir) / "2026-04-21" / "IR_82680.txt"
            local_sample_path.parent.mkdir(parents=True, exist_ok=True)
            local_sample_path.write_text("mock spectrum", encoding="utf-8")

            sample_record = SimpleNamespace(
                sample_id="sp_001",
                sample_name="IR_82680.txt",
                storage={"local_sample_path": str(local_sample_path)},
            )

            with patch.object(LabCollectService, "_ensure_indexes", return_value=None):
                service = LabCollectService()

            with (
                patch(
                    "app.services.lab_collect_service.SpectrumSampleRepository.find_by_sample_id",
                    return_value=sample_record,
                ),
                patch("app.services.lab_collect_service.SpectrumSampleRepository.delete_by_sample_id") as delete_sample_mock,
                patch(
                    "app.services.lab_collect_service.SpectrumSampleFileRepository.delete_by_sample_id"
                ) as delete_files_mock,
            ):
                deleted = service.delete_sample(sample_id="sp_001")

            self.assertTrue(deleted)
        self.assertFalse(local_sample_path.exists())
        delete_sample_mock.assert_called_once_with(sample_id="sp_001")
        delete_files_mock.assert_called_once_with(sample_id="sp_001")

    def test_get_molecular_statistics_returns_empty_default_when_cache_missing(self) -> None:
        """分子统计缓存不存在时应返回默认空结果。"""
        with patch.object(LabCollectService, "_ensure_indexes", return_value=None):
            service = LabCollectService()
        with patch("app.services.lab_collect_service.MolecularStatisticsRepository.find_by_key", return_value=None):
            result = service.get_molecular_statistics()
        self.assertEqual(result.stats_key, "sample_smiles_overview")
        self.assertTrue(result.is_stale)
        self.assertEqual(result.status, "EMPTY")

    def test_refresh_molecular_statistics_builds_expected_summary(self) -> None:
        """刷新分子统计时应统计唯一 SMILES、骨架和官能团数量。"""
        sample_docs = [
            {"sample_meta": {"smiles": "CCO"}},
            {"sample_meta": {"smiles": "CCO"}},
            {"sample_meta": {"smiles": "c1ccccc1O"}},
            {"sample_meta": {"smiles": ""}},
        ]

        class FakeCollection:
            """最小化模拟样本集合。"""

            @staticmethod
            def find(*args, **kwargs):
                return sample_docs

        saved_stats = []
        with patch.object(LabCollectService, "_ensure_indexes", return_value=None):
            service = LabCollectService()
        with (
            patch("app.services.lab_collect_service.SpectrumSampleRepository.collection", return_value=FakeCollection()),
            patch("app.services.lab_collect_service.MolecularStatisticsRepository.save", side_effect=saved_stats.append),
        ):
            result = service.refresh_molecular_statistics()

        self.assertEqual(result.unique_smiles_count, 2)
        self.assertGreaterEqual(result.unique_scaffold_count, 1)
        self.assertGreaterEqual(result.unique_functional_group_count, 1)
        self.assertEqual(result.source_sample_count, 3)
        self.assertFalse(result.is_stale)
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(saved_stats), 1)
        self.assertIsInstance(saved_stats[0], MolecularStatisticsData)


if __name__ == "__main__":
    unittest.main()
