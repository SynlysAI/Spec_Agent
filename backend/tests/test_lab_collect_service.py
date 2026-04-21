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


if __name__ == "__main__":
    unittest.main()
