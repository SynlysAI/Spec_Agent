"""批量验收测试服务。"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from app.core.config import settings
from app.infra.mongo import get_acceptance_runs_collection
from app.schemas.acceptance import (
    AcceptanceRunData,
    AcceptanceRunHistoryItem,
    AcceptanceRunItem,
    AcceptanceRunSummary,
    AcceptanceTypeConfig,
)
from app.schemas.tasks import TaskArtifactItem
from app.services.analysis_executor import execute_analysis_sync
from app.services.remote_acceptance_service import remote_acceptance_service

TYPE_LABELS = {
    "nmr": "NMR 核磁",
    "gpc": "GPC 凝胶色谱",
    "ir": "IR 红外",
    "raman": "Raman 拉曼",
}

TYPE_TO_TASK_KIND = {
    "nmr": "nmr_analysis",
    "gpc": "gpc_analysis",
    "ir": "ir_analysis",
    "raman": "raman_analysis",
}


@dataclass
class AcceptanceSample:
    """验收样本对象。"""

    spectrum_type: str
    sample_name: str
    sample_path: str


class AcceptanceService:
    """提供验收配置读取、批次执行与结果查询能力。"""

    def __init__(self) -> None:
        self.config_path = settings.acceptance_config_path
        self._run_store: dict[str, AcceptanceRunData] = {}
        self._lock = threading.Lock()
        self._ensure_indexes()

    @staticmethod
    def _ensure_indexes() -> None:
        """初始化 acceptance_runs 索引。"""
        collection = get_acceptance_runs_collection()
        collection.create_index("run_id", unique=True)
        collection.create_index("started_at")
        collection.create_index("status")

    def get_config_summary(self) -> tuple[Path, list[AcceptanceTypeConfig], int]:
        """读取配置并返回样本摘要。

        Returns:
            (配置路径, 每类型统计, 总样本数) 元组。
        """
        config = self._load_config()
        samples_config = config.get("samples", {})
        total_samples = 0
        items: list[AcceptanceTypeConfig] = []
        for spectrum_type in ("nmr", "gpc", "ir", "raman"):
            type_config = samples_config.get(spectrum_type, {}) or {}
            execution_mode = self._get_execution_mode(type_config=type_config)
            samples = [] if execution_mode == "remote_summary" else self._scan_samples(
                spectrum_type=spectrum_type,
                type_config=type_config,
            )
            dirs = [str(item) for item in type_config.get("dirs", []) if str(item).strip()]
            count = len(samples)
            total_samples += count
            items.append(
                AcceptanceTypeConfig(
                    spectrum_type=spectrum_type,
                    label=TYPE_LABELS[spectrum_type],
                    execution_mode=execution_mode,
                    sample_count=count,
                    dirs=dirs,
                )
            )
        return self.config_path, items, total_samples

    def create_run(self, spectrum_types: list[str] | None = None) -> AcceptanceRunData:
        """创建并异步启动批量验收运行。

        Args:
            spectrum_types: 指定执行的谱图类型列表。

        Returns:
            新建运行对象。
        """
        selected_types = self._normalize_types(spectrum_types)
        run_id = f"acc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        run_data = AcceptanceRunData(
            run_id=run_id,
            status="RUNNING",
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            finished_at=None,
            selected_types=selected_types,
            summary=AcceptanceRunSummary(total=0, success=0, failed=0, progress=0, duration_seconds=0.0),
            aggregate_metrics=self._build_aggregate_metrics(results=[]),
            results=[],
            report_path=None,
        )
        with self._lock:
            self._run_store[run_id] = run_data
        self._save_run_record(run_data=run_data)

        thread = threading.Thread(target=self._run_batch, args=(run_id,), daemon=True)
        thread.start()
        return run_data

    def get_run(self, run_id: str) -> AcceptanceRunData | None:
        """查询批次运行状态。

        Args:
            run_id: 批次运行 ID。

        Returns:
            运行对象，不存在时返回 None。
        """
        with self._lock:
            data = self._run_store.get(run_id)
            if data:
                return data.model_copy(deep=True)
        record = self._load_run_record(run_id=run_id)
        if record:
            return record
        return self._load_run_snapshot(run_id=run_id)

    def list_runs(self, limit: int = 20) -> list[AcceptanceRunHistoryItem]:
        """查询验收批次历史列表。

        Args:
            limit: 返回条数上限。

        Returns:
            历史批次列表（按开始时间倒序）。
        """
        safe_limit = max(1, min(int(limit or 20), 200))
        history: list[AcceptanceRunHistoryItem] = []
        known_run_ids: set[str] = set()

        with self._lock:
            current_runs = list(self._run_store.values())
        for run_data in current_runs:
            history.append(self._to_history_item(run_data=run_data))
            known_run_ids.add(run_data.run_id)

        collection = get_acceptance_runs_collection()
        cursor = collection.find({}, {"_id": 0}).sort([("started_at", -1)]).limit(safe_limit * 3)
        for doc in cursor:
            run_data = self._deserialize_run_data(doc)
            if not run_data or run_data.run_id in known_run_ids:
                continue
            history.append(self._to_history_item(run_data=run_data))
            known_run_ids.add(run_data.run_id)

        report_dir = settings.outputs_root / "acceptance"
        if report_dir.exists() and report_dir.is_dir():
            snapshot_files = sorted(report_dir.glob("acc_*.json"), key=lambda path: path.name, reverse=True)
            for snapshot_file in snapshot_files:
                run_id = snapshot_file.stem
                if run_id in known_run_ids:
                    continue
                run_data = self._load_run_snapshot(run_id=run_id)
                if run_data:
                    history.append(self._to_history_item(run_data=run_data))
                    known_run_ids.add(run_id)

            report_files = sorted(report_dir.glob("acc_*.md"), key=lambda path: path.name, reverse=True)
            for report_file in report_files:
                run_id = report_file.stem
                if run_id in known_run_ids:
                    continue
                history.append(self._parse_report_file(report_file=report_file))

        history.sort(
            key=lambda item: self._parse_datetime_text(item.started_at) or datetime.min,
            reverse=True,
        )
        return history[:safe_limit]

    def _run_batch(self, run_id: str) -> None:
        """后台执行批量验收任务。

        Args:
            run_id: 批次运行 ID。
        """
        start_time = time.time()
        with self._lock:
            run_data = self._run_store.get(run_id)
            if not run_data:
                return
            selected_types = list(run_data.selected_types)

        config = self._load_config()
        all_samples: list[AcceptanceSample] = []
        remote_types: list[tuple[str, dict[str, Any]]] = []
        for spectrum_type in selected_types:
            type_config = (config.get("samples", {}) or {}).get(spectrum_type, {}) or {}
            if self._get_execution_mode(type_config=type_config) == "remote_summary":
                remote_types.append((spectrum_type, type_config))
                continue
            all_samples.extend(self._scan_samples(spectrum_type=spectrum_type, type_config=type_config))

        total_work = len(all_samples) + len(remote_types)
        self._update_run_summary(run_id=run_id, total=total_work, success=0, failed=0, progress=0)
        if total_work == 0:
            self._finish_run(run_id=run_id, status="FINISHED", start_time=start_time)
            return

        success_count = 0
        failed_count = 0
        processed_count = 0
        for spectrum_type, type_config in remote_types:
            item = self._execute_remote_summary_type(
                run_id=run_id,
                spectrum_type=spectrum_type,
                type_config=type_config,
            )
            if item.status == "SUCCESS":
                success_count += 1
            else:
                failed_count += 1
            processed_count += 1
            self._append_run_item(
                run_id=run_id,
                item=item,
                success=success_count,
                failed=failed_count,
                progress=int(processed_count / total_work * 100),
            )

        for sample in all_samples:
            item = self._execute_single_sample(run_id=run_id, sample=sample)
            if item.status == "SUCCESS":
                success_count += 1
            else:
                failed_count += 1
            processed_count += 1
            self._append_run_item(
                run_id=run_id,
                item=item,
                success=success_count,
                failed=failed_count,
                progress=int(processed_count / total_work * 100),
            )

        self._finish_run(run_id=run_id, status="FINISHED", start_time=start_time)

    def _execute_single_sample(self, run_id: str, sample: AcceptanceSample) -> AcceptanceRunItem:
        """执行单样本验收。

        Args:
            run_id: 批次运行 ID。
            sample: 验收样本。

        Returns:
            单样本执行结果。
        """
        started_at = time.time()
        sample_execution_id = f"{sample.spectrum_type}_{uuid4().hex[:8]}"
        output_dir = settings.outputs_root / "acceptance" / run_id / sample_execution_id
        try:
            payload = self._build_task_payload(sample=sample)
            result_payload = execute_analysis_sync(
                task_type=payload["task_type"],
                input_data=payload["input"],
                params=payload["params"],
                output_dir=output_dir,
            )
            metrics = self._extract_sample_metrics(
                result_payload=result_payload,
                spectrum_type=sample.spectrum_type,
            )
            return AcceptanceRunItem(
                sample_execution_id=sample_execution_id,
                spectrum_type=sample.spectrum_type,
                sample_name=sample.sample_name,
                sample_path=sample.sample_path,
                status="SUCCESS",
                duration_seconds=time.time() - started_at,
                metrics=metrics,
                text_report=str(result_payload.get("text_report", "")),
                artifacts=[
                    TaskArtifactItem(**artifact)
                    if isinstance(artifact, dict)
                    else artifact
                    for artifact in result_payload.get("artifacts", [])
                ],
                error_message=None,
            )
        except Exception as exc:
            return AcceptanceRunItem(
                sample_execution_id=sample_execution_id,
                spectrum_type=sample.spectrum_type,
                sample_name=sample.sample_name,
                sample_path=sample.sample_path,
                status="FAILED",
                duration_seconds=time.time() - started_at,
                metrics={},
                text_report="",
                artifacts=self._load_artifacts_from_dir(output_dir=output_dir),
                error_message=str(exc),
            )

    def _execute_remote_summary_type(
        self,
        run_id: str,
        spectrum_type: str,
        type_config: dict[str, Any],
    ) -> AcceptanceRunItem:
        """执行远程汇总类型验收。

        Args:
            run_id: 批次运行 ID。
            spectrum_type: 谱图类型。
            type_config: 类型配置。

        Returns:
            远程汇总结果。
        """
        started_at = time.time()
        sample_execution_id = f"{spectrum_type}_{uuid4().hex[:8]}"
        try:
            remote_payload = remote_acceptance_service.run_remote_summary(type_config=type_config)
            metrics = self._build_remote_summary_metrics(
                spectrum_type=spectrum_type,
                payload=remote_payload,
            )
            sample_count = int(remote_payload.get("sample_count") or 0)
            report_text = self._build_remote_summary_text_report(
                spectrum_type=spectrum_type,
                payload=remote_payload,
            )
            return AcceptanceRunItem(
                sample_execution_id=sample_execution_id,
                spectrum_type=spectrum_type,
                sample_name=f"{TYPE_LABELS.get(spectrum_type, spectrum_type)} 远程汇总",
                sample_path=str(((type_config or {}).get("remote", {}) or {}).get("script") or ""),
                status="SUCCESS" if remote_payload.get("success", False) else "FAILED",
                duration_seconds=time.time() - started_at,
                metrics=metrics,
                text_report=report_text,
                artifacts=[],
                error_message=None if remote_payload.get("success", False) else str(remote_payload.get("error_message") or "remote summary failed"),
            )
        except Exception as exc:
            return AcceptanceRunItem(
                sample_execution_id=sample_execution_id,
                spectrum_type=spectrum_type,
                sample_name=f"{TYPE_LABELS.get(spectrum_type, spectrum_type)} 远程汇总",
                sample_path=str(((type_config or {}).get("remote", {}) or {}).get("script") or ""),
                status="FAILED",
                duration_seconds=time.time() - started_at,
                metrics={},
                text_report="",
                artifacts=[],
                error_message=str(exc),
            )

    def _append_run_item(
        self,
        run_id: str,
        item: AcceptanceRunItem,
        success: int,
        failed: int,
        progress: int,
    ) -> None:
        """向批次结果中追加一条执行结果。

        Args:
            run_id: 批次运行 ID。
            item: 样本结果项。
            success: 当前成功数。
            failed: 当前失败数。
            progress: 当前进度。
        """
        with self._lock:
            run_data = self._run_store.get(run_id)
            if not run_data:
                return
            run_data.results.append(item)
            run_data.summary.success = success
            run_data.summary.failed = failed
            run_data.summary.progress = progress
            run_data.aggregate_metrics = self._build_aggregate_metrics(results=run_data.results)
            snapshot = run_data.model_copy(deep=True)
        self._save_run_record(run_data=snapshot)

    def _build_task_payload(self, sample: AcceptanceSample) -> dict[str, Any]:
        """构建批量验收执行参数。

        Args:
            sample: 验收样本。

        Returns:
            执行入参字典。
        """
        spectrum_type = sample.spectrum_type
        if spectrum_type == "gpc":
            return {
                "task_type": TYPE_TO_TASK_KIND[spectrum_type],
                "input": {"input_type": "file_path", "input_path": sample.sample_path, "file_id": None},
                "params": {
                    "detect_mode": "auto",
                    "manual_interval": None,
                    "three_color_arw_paths": None,
                    "calibration_file_path": None,
                    "comparison_report_pdf_path": None,
                },
            }
        if spectrum_type == "nmr":
            return {
                "task_type": TYPE_TO_TASK_KIND[spectrum_type],
                "input": {"input_type": "folder_path", "input_path": sample.sample_path, "file_id": None},
                "params": {
                    "nucleus": "1H",
                    "threshold": 0.01,
                    "min_distance": 0.3,
                    "min_prominence": 0.01,
                    "width_multiplier": 1.0,
                    "baseline_degree": 3,
                    "smooth_window": 5,
                    "detection_range_mode": "full",
                    "detection_range_min": None,
                    "detection_range_max": None,
                    "ppm_offset": 0.0,
                    "integration_method": "voigt",
                    "internal_standard_policy": "auto",
                    "internal_standard_prefer": ["solvent", "tms"],
                },
            }
        return {
            "task_type": TYPE_TO_TASK_KIND[spectrum_type],
            "input": {"input_type": "file_path", "input_path": sample.sample_path, "file_id": None},
            "params": {
                "spectype": spectrum_type,
                "mode": "retrieval" if spectrum_type == "raman" else "greedy_decode",
                "k": 3,
                "x0": 400,
                "x1": 4000,
                "transmittance": False,
                "device": "auto",
            },
        }

    @staticmethod
    def _get_execution_mode(type_config: dict[str, Any]) -> str:
        """获取执行模式。

        Args:
            type_config: 类型配置。

        Returns:
            执行模式字符串。
        """
        mode = str((type_config or {}).get("execution_mode") or "local").strip().lower()
        return mode if mode in {"local", "remote_summary"} else "local"

    def _scan_samples(self, spectrum_type: str, type_config: dict) -> list[AcceptanceSample]:
        """扫描指定类型样本路径。

        Args:
            spectrum_type: 谱图类型。
            type_config: 配置项。

        Returns:
            样本列表。
        """
        dirs = [Path(str(item)) for item in (type_config.get("dirs", []) or []) if str(item).strip()]
        patterns = [str(item) for item in (type_config.get("patterns", []) or []) if str(item).strip()]
        sample_paths: list[Path] = []

        if spectrum_type == "nmr":
            for sample_dir in dirs:
                if not sample_dir.exists() or not sample_dir.is_dir():
                    continue
                sample_paths.extend([item for item in sample_dir.iterdir() if item.is_dir()])
        elif spectrum_type == "gpc":
            if not patterns:
                patterns = ["*.arw"]
            for root_dir in dirs:
                if not root_dir.exists() or not root_dir.is_dir():
                    continue
                for pattern in patterns:
                    sample_paths.extend([item for item in root_dir.rglob(pattern) if item.is_file()])
        else:
            if not patterns:
                patterns = ["*"]
            for root_dir in dirs:
                if not root_dir.exists() or not root_dir.is_dir():
                    continue
                for pattern in patterns:
                    sample_paths.extend([item for item in root_dir.glob(pattern) if item.is_file()])

        unique_paths: dict[str, Path] = {str(path): path for path in sample_paths}
        samples: list[AcceptanceSample] = []
        for path in unique_paths.values():
            samples.append(
                AcceptanceSample(
                    spectrum_type=spectrum_type,
                    sample_name=path.name,
                    sample_path=str(path),
                )
            )
        samples.sort(key=lambda item: item.sample_name)
        return samples

    def _load_config(self) -> dict[str, Any]:
        """加载验收配置文件。

        Returns:
            配置字典。
        """
        if not self.config_path.exists():
            return {"samples": {}}
        content = self.config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}
        return data if isinstance(data, dict) else {"samples": {}}

    def _build_remote_summary_metrics(self, spectrum_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """将远程汇总 JSON 转为统一指标格式。

        Args:
            spectrum_type: 谱图类型。
            payload: 远程汇总结果。

        Returns:
            指标字典。
        """
        aggregate = payload.get("aggregate_metrics", {}) or {}
        metrics: dict[str, Any] = {
            "remote_sample_count": [int(payload.get("sample_count") or 0)],
        }
        if spectrum_type == "raman":
            exact_match_rate = self._safe_float(payload.get("exact_match_rate"))
            element_accuracy = self._safe_float(payload.get("element_accuracy"))
            micro_avg = aggregate.get("micro_avg", {}) if isinstance(aggregate, dict) else {}
            samples_avg = aggregate.get("samples_avg", {}) if isinstance(aggregate, dict) else {}
            macro_avg = aggregate.get("macro_avg", {}) if isinstance(aggregate, dict) else {}
            if exact_match_rate is not None:
                metrics["top1_accuracy"] = [exact_match_rate]
            if element_accuracy is not None:
                metrics["element_accuracy"] = [element_accuracy]
            micro_f1 = self._safe_float((micro_avg or {}).get("f1_score"))
            samples_f1 = self._safe_float((samples_avg or {}).get("f1_score"))
            macro_f1 = self._safe_float((macro_avg or {}).get("f1_score"))
            if micro_f1 is not None:
                metrics["micro_f1"] = [micro_f1]
            if samples_f1 is not None:
                metrics["samples_avg_f1"] = [samples_f1]
            if macro_f1 is not None:
                metrics["macro_f1"] = [macro_f1]
        return metrics

    def _build_remote_summary_text_report(self, spectrum_type: str, payload: dict[str, Any]) -> str:
        """构建远程汇总文本报告。

        Args:
            spectrum_type: 谱图类型。
            payload: 远程汇总结果。

        Returns:
            文本报告字符串。
        """
        aggregate = payload.get("aggregate_metrics", {}) or {}
        lines = [
            f"## {TYPE_LABELS.get(spectrum_type, spectrum_type)} 远程汇总结果",
            "",
            f"- success: {payload.get('success')}",
            f"- sample_count: {payload.get('sample_count')}",
            f"- duration_seconds: {payload.get('duration_seconds')}",
            f"- exact_match_rate: {payload.get('exact_match_rate')}",
            f"- element_accuracy: {payload.get('element_accuracy')}",
            "",
            "### aggregate_metrics",
        ]
        if isinstance(aggregate, dict):
            for key, value in aggregate.items():
                lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
        return "\n".join(lines)

    @staticmethod
    def _normalize_types(spectrum_types: list[str] | None) -> list[str]:
        """规范化验收类型列表。

        Args:
            spectrum_types: 用户输入的类型列表。

        Returns:
            过滤后的类型列表。
        """
        if not spectrum_types:
            return ["nmr", "gpc", "ir", "raman"]
        valid_set = set(TYPE_LABELS.keys())
        normalized = [str(item).lower() for item in spectrum_types if str(item).lower() in valid_set]
        return normalized or ["nmr", "gpc", "ir", "raman"]

    def _update_run_summary(self, run_id: str, total: int, success: int, failed: int, progress: int) -> None:
        """更新批次汇总信息。

        Args:
            run_id: 批次运行 ID。
            total: 总样本数。
            success: 成功数。
            failed: 失败数。
            progress: 当前进度。
        """
        with self._lock:
            run_data = self._run_store.get(run_id)
            if not run_data:
                return
            run_data.summary.total = total
            run_data.summary.success = success
            run_data.summary.failed = failed
            run_data.summary.progress = progress
            snapshot = run_data.model_copy(deep=True)
        self._save_run_record(run_data=snapshot)

    def _finish_run(self, run_id: str, status: str, start_time: float) -> None:
        """结束批次运行并保存结果文件。

        Args:
            run_id: 批次运行 ID。
            status: 最终状态。
            start_time: 批次开始时间戳。
        """
        duration = time.time() - start_time
        with self._lock:
            run_data = self._run_store.get(run_id)
            if not run_data:
                return
            run_data.status = status
            run_data.summary.duration_seconds = duration
            run_data.summary.progress = 100
            run_data.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            run_data.aggregate_metrics = self._build_aggregate_metrics(results=run_data.results)
            report_path = self._save_markdown_report(run_data=run_data)
            run_data.report_path = str(report_path)
            self._save_run_snapshot(run_data=run_data)
            snapshot = run_data.model_copy(deep=True)
        self._save_run_record(run_data=snapshot)

    @staticmethod
    def _build_aggregate_metrics(results: list[AcceptanceRunItem]) -> dict[str, Any]:
        """构建验收指标汇总。

        Args:
            results: 当前批次样本结果列表。

        Returns:
            与原项目字段命名兼容的指标汇总字典。
        """
        thresholds = {
            "nmr_baseline_rmse": 0.2,
            "nmr_solvent_ppm_error": 0.05,
            "gpc_rd": 10.0,
        }

        def _slice(stype: str) -> list[AcceptanceRunItem]:
            return [item for item in results if item.spectrum_type == stype]

        def _rate(items: list[AcceptanceRunItem]) -> float | None:
            if not items:
                return None
            passed = sum(1 for item in items if item.status == "SUCCESS")
            return passed / len(items) * 100.0

        nmr_items = _slice("nmr")
        gpc_items = _slice("gpc")
        ir_items = _slice("ir")
        raman_items = _slice("raman")

        nmr_baseline_rmse: list[float] = []
        nmr_solvent_ppm_errors: list[float] = []
        for item in nmr_items:
            metrics = item.metrics or {}
            nmr_baseline_rmse.extend(
                [value for value in (AcceptanceService._safe_float(v) for v in metrics.get("baseline_rmse", [])) if value is not None]
            )
            nmr_solvent_ppm_errors.extend(
                [value for value in (AcceptanceService._safe_float(v) for v in metrics.get("solvent_ppm_errors", [])) if value is not None]
            )

        gpc_mn_rd: list[float] = []
        gpc_mw_rd: list[float] = []
        gpc_pdi_rd: list[float] = []
        for item in gpc_items:
            metrics = item.metrics or {}
            gpc_mn_rd.extend(
                [value for value in (AcceptanceService._safe_float(v) for v in metrics.get("mn_rd_pct", [])) if value is not None]
            )
            gpc_mw_rd.extend(
                [value for value in (AcceptanceService._safe_float(v) for v in metrics.get("mw_rd_pct", [])) if value is not None]
            )
            gpc_pdi_rd.extend(
                [value for value in (AcceptanceService._safe_float(v) for v in metrics.get("pdi_rd_pct", [])) if value is not None]
            )

        raman_top1_accuracy: list[float] = []
        raman_micro_f1: list[float] = []
        raman_samples_avg_f1: list[float] = []
        raman_element_accuracy: list[float] = []
        raman_remote_sample_count = 0
        for item in raman_items:
            metrics = item.metrics or {}
            raman_top1_accuracy.extend(
                [value for value in (AcceptanceService._safe_float(v) for v in metrics.get("top1_accuracy", [])) if value is not None]
            )
            raman_micro_f1.extend(
                [value for value in (AcceptanceService._safe_float(v) for v in metrics.get("micro_f1", [])) if value is not None]
            )
            raman_samples_avg_f1.extend(
                [value for value in (AcceptanceService._safe_float(v) for v in metrics.get("samples_avg_f1", [])) if value is not None]
            )
            raman_element_accuracy.extend(
                [value for value in (AcceptanceService._safe_float(v) for v in metrics.get("element_accuracy", [])) if value is not None]
            )
            remote_count_values = [
                value for value in (AcceptanceService._safe_float(v) for v in metrics.get("remote_sample_count", [])) if value is not None
            ]
            if remote_count_values:
                raman_remote_sample_count += int(remote_count_values[0])

        return {
            "thresholds": thresholds,
            "nmr": {
                "sample_count": len(nmr_items),
                "task_success_rate": _rate(nmr_items),
                "baseline_rmse_count": len(nmr_baseline_rmse),
                "baseline_rmse_avg": AcceptanceService._avg(nmr_baseline_rmse),
                "baseline_rmse_pass_rate": AcceptanceService._pass_rate(
                    nmr_baseline_rmse, thresholds["nmr_baseline_rmse"]
                ),
                "solvent_ppm_error_count": len(nmr_solvent_ppm_errors),
                "solvent_ppm_error_avg": AcceptanceService._avg(nmr_solvent_ppm_errors),
                "solvent_ppm_error_pass_rate": AcceptanceService._pass_rate(
                    nmr_solvent_ppm_errors, thresholds["nmr_solvent_ppm_error"]
                ),
            },
            "gpc": {
                "sample_count": len(gpc_items),
                "task_success_rate": _rate(gpc_items),
                "mn_rd_count": len(gpc_mn_rd),
                "mn_rd_avg": AcceptanceService._avg(gpc_mn_rd),
                "mn_rd_pass_rate": AcceptanceService._pass_rate(gpc_mn_rd, thresholds["gpc_rd"]),
                "mw_rd_count": len(gpc_mw_rd),
                "mw_rd_avg": AcceptanceService._avg(gpc_mw_rd),
                "mw_rd_pass_rate": AcceptanceService._pass_rate(gpc_mw_rd, thresholds["gpc_rd"]),
                "pdi_rd_count": len(gpc_pdi_rd),
                "pdi_rd_avg": AcceptanceService._avg(gpc_pdi_rd),
                "pdi_rd_pass_rate": AcceptanceService._pass_rate(gpc_pdi_rd, thresholds["gpc_rd"]),
            },
            "ir": {
                "sample_count": len(ir_items),
                "task_success_rate": _rate(ir_items),
                "labeled_count": 0,
                "micro_f1": None,
                "sample_f1_avg": None,
            },
            "raman": {
                "sample_count": raman_remote_sample_count or len(raman_items),
                "task_success_rate": _rate(raman_items),
                "labeled_count": raman_remote_sample_count or 0,
                "top1_accuracy": AcceptanceService._avg(raman_top1_accuracy),
                "micro_f1": AcceptanceService._avg(raman_micro_f1),
                "samples_avg_f1": AcceptanceService._avg(raman_samples_avg_f1),
                "element_accuracy": AcceptanceService._avg(raman_element_accuracy),
                "recall_at_3": None,
            },
        }

    def _extract_sample_metrics(self, result_payload: dict[str, Any], spectrum_type: str) -> dict[str, Any]:
        """提取单样本可聚合指标。

        Args:
            result_payload: 同步执行结果。
            spectrum_type: 谱图类型。

        Returns:
            指标字典。
        """
        metadata = result_payload.get("metadata", {}) or {}
        qa_metrics = metadata.get("qa_metrics", {}) if isinstance(metadata, dict) else {}
        if isinstance(qa_metrics, dict) and qa_metrics:
            metrics: dict[str, Any] = {}
            if spectrum_type == "nmr":
                baseline_rmse = self._safe_float(qa_metrics.get("baseline_rmse"))
                if baseline_rmse is not None:
                    metrics["baseline_rmse"] = [baseline_rmse]
                solvent_ppm_errors = qa_metrics.get("solvent_ppm_errors")
                if isinstance(solvent_ppm_errors, list):
                    metrics["solvent_ppm_errors"] = [
                        value for value in (self._safe_float(v) for v in solvent_ppm_errors) if value is not None
                    ]
            for key in ("mn_rd_pct", "mw_rd_pct", "pdi_rd_pct"):
                val = self._safe_float(qa_metrics.get(key))
                if val is not None:
                    metrics[key] = [val]
            if metrics:
                return metrics

        if spectrum_type != "gpc":
            return {}
        return self._extract_gpc_metrics_from_structured_data(result_payload.get("structured_data", {}) or {})

    def _extract_gpc_metrics_from_structured_data(self, structured_data: dict[str, Any]) -> dict[str, Any]:
        """从 GPC 结构化结果中提取分子量偏差指标。

        Args:
            structured_data: 结构化结果。

        Returns:
            包含 mn/mw/pdi 偏差数组的字典。
        """
        analysis_results = structured_data.get("analysis_results", [])
        if not isinstance(analysis_results, list):
            return {}

        metrics = {"mn_rd_pct": [], "mw_rd_pct": [], "pdi_rd_pct": []}
        for row in analysis_results:
            if not isinstance(row, dict):
                continue
            molecular = row.get("molecular_parameters", {}) or {}
            pdf_data = row.get("pdf_data", {}) or {}
            for model_key, ref_key, target_key in (
                ("mn", "Mn", "mn_rd_pct"),
                ("mw", "Mw", "mw_rd_pct"),
                ("pdi", "多分散性", "pdi_rd_pct"),
            ):
                model_value = self._safe_float(molecular.get(model_key))
                ref_value = self._safe_float(pdf_data.get(ref_key))
                if model_value is None or ref_value is None or abs(ref_value) < 1e-12:
                    continue
                metrics[target_key].append(abs((model_value - ref_value) / ref_value) * 100.0)
        return metrics

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """安全转换浮点值。

        Args:
            value: 原始值。

        Returns:
            可用浮点值或 None。
        """
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if parsed != parsed or parsed in (float("inf"), float("-inf")):
            return None
        return parsed

    @staticmethod
    def _avg(values: list[float]) -> float | None:
        """计算均值。

        Args:
            values: 数值列表。

        Returns:
            均值或 None。
        """
        if not values:
            return None
        return float(sum(values) / len(values))

    @staticmethod
    def _pass_rate(values: list[float], threshold: float) -> float | None:
        """计算达标率（值 <= 阈值）。

        Args:
            values: 数值列表。
            threshold: 阈值。

        Returns:
            达标率百分比或 None。
        """
        if not values:
            return None
        passed = sum(1 for value in values if value <= threshold)
        return float(passed / len(values) * 100.0)

    def _save_markdown_report(self, run_data: AcceptanceRunData) -> Path:
        """保存批次运行 Markdown 报告。

        Args:
            run_data: 批次运行数据。

        Returns:
            报告文件路径。
        """
        report_dir = settings.outputs_root / "acceptance"
        report_dir.mkdir(parents=True, exist_ok=True)
        file_path = report_dir / f"{run_data.run_id}.md"
        lines = [
            f"# 批量验收报告 {run_data.run_id}",
            "",
            f"- 状态: {run_data.status}",
            f"- 开始时间: {run_data.started_at}",
            f"- 结束时间: {run_data.finished_at or ''}",
            f"- 执行类型: {', '.join(run_data.selected_types)}",
            f"- 总样本: {run_data.summary.total}",
            f"- 成功: {run_data.summary.success}",
            f"- 失败: {run_data.summary.failed}",
            f"- 总耗时(秒): {run_data.summary.duration_seconds:.1f}",
            "",
            "## 验收指标汇总",
            "",
        ]
        aggregate_metrics = run_data.aggregate_metrics or {}
        nmr_metrics = aggregate_metrics.get("nmr", {}) if isinstance(aggregate_metrics, dict) else {}
        gpc_metrics = aggregate_metrics.get("gpc", {}) if isinstance(aggregate_metrics, dict) else {}
        ir_metrics = aggregate_metrics.get("ir", {}) if isinstance(aggregate_metrics, dict) else {}
        raman_metrics = aggregate_metrics.get("raman", {}) if isinstance(aggregate_metrics, dict) else {}

        lines.extend(
            [
                "### NMR（可自动计算）",
                f"- 样本数: {nmr_metrics.get('sample_count', 0)}",
                f"- 任务成功率: {self._format_percent(nmr_metrics.get('task_success_rate'))}",
                f"- 基线RMSE均值: {self._format_number(nmr_metrics.get('baseline_rmse_avg'), 4)}",
                f"- 基线达标率: {self._format_percent(nmr_metrics.get('baseline_rmse_pass_rate'))}",
                f"- 溶剂峰ppm误差均值: {self._format_number(nmr_metrics.get('solvent_ppm_error_avg'), 4)}",
                f"- 溶剂峰达标率: {self._format_percent(nmr_metrics.get('solvent_ppm_error_pass_rate'))}",
                "",
                "### GPC（分子量偏差验收）",
                f"- 样本数: {gpc_metrics.get('sample_count', 0)}",
                f"- 任务成功率: {self._format_percent(gpc_metrics.get('task_success_rate'))}",
                f"- Mn偏差均值: {self._format_number(gpc_metrics.get('mn_rd_avg'), 2, '%')} (n={gpc_metrics.get('mn_rd_count', 0)})",
                f"- Mn达标率: {self._format_percent(gpc_metrics.get('mn_rd_pass_rate'))}",
                f"- Mw偏差均值: {self._format_number(gpc_metrics.get('mw_rd_avg'), 2, '%')} (n={gpc_metrics.get('mw_rd_count', 0)})",
                f"- Mw达标率: {self._format_percent(gpc_metrics.get('mw_rd_pass_rate'))}",
                f"- PDI偏差均值: {self._format_number(gpc_metrics.get('pdi_rd_avg'), 2, '%')} (n={gpc_metrics.get('pdi_rd_count', 0)})",
                f"- PDI达标率: {self._format_percent(gpc_metrics.get('pdi_rd_pass_rate'))}",
                "",
                "### IR（标签指标）",
                f"- 样本数: {ir_metrics.get('sample_count', 0)}",
                f"- 任务成功率: {self._format_percent(ir_metrics.get('task_success_rate'))}",
                f"- 已标注样本: {ir_metrics.get('labeled_count', 0)}",
                f"- Micro-F1: {self._format_number(ir_metrics.get('micro_f1'), 4)}",
                f"- 样本平均F1: {self._format_number(ir_metrics.get('sample_f1_avg'), 4)}",
                "",
                "### Raman（标签指标）",
                f"- 样本数: {raman_metrics.get('sample_count', 0)}",
                f"- 任务成功率: {self._format_percent(raman_metrics.get('task_success_rate'))}",
                f"- 已标注样本: {raman_metrics.get('labeled_count', 0)}",
                f"- Top1准确率: {self._format_percent(raman_metrics.get('top1_accuracy'))}",
                f"- Micro-F1: {self._format_number(raman_metrics.get('micro_f1'), 4)}",
                f"- Samples Avg F1: {self._format_number(raman_metrics.get('samples_avg_f1'), 4)}",
                f"- Element Accuracy: {self._format_percent(raman_metrics.get('element_accuracy'))}",
                f"- Recall@3: {self._format_percent(raman_metrics.get('recall_at_3'))}",
                "",
                "## 样本明细",
                "",
                "| 类型 | 样本 | 状态 | 耗时(s) | 样本执行ID | 错误 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in run_data.results:
            lines.append(
                f"| {item.spectrum_type} | {item.sample_name} | {item.status} | "
                f"{item.duration_seconds:.1f} | {item.sample_execution_id} | {item.error_message or ''} |"
            )
        file_path.write_text("\n".join(lines), encoding="utf-8")
        return file_path

    def _save_run_snapshot(self, run_data: AcceptanceRunData) -> Path:
        """保存批次结构化快照。

        Args:
            run_data: 批次运行数据。

        Returns:
            快照文件路径。
        """
        snapshot_path = settings.outputs_root / "acceptance" / f"{run_data.run_id}.json"
        snapshot_path.write_text(
            json.dumps(run_data.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return snapshot_path

    @staticmethod
    def _format_number(value: Any, digits: int, suffix: str = "") -> str:
        """格式化数值输出，空值时返回 N/A。"""
        parsed = AcceptanceService._safe_float(value)
        if parsed is None:
            return "N/A"
        return f"{parsed:.{digits}f}{suffix}"

    @staticmethod
    def _format_percent(value: Any) -> str:
        """格式化百分比输出，空值时返回 N/A。"""
        parsed = AcceptanceService._safe_float(value)
        if parsed is None:
            return "N/A"
        return f"{parsed:.1f}%"

    def _load_run_snapshot(self, run_id: str) -> AcceptanceRunData | None:
        """从历史快照或报告文件加载批次信息。

        Args:
            run_id: 批次运行 ID。

        Returns:
            运行数据对象；若文件不存在则返回 None。
        """
        snapshot_path = settings.outputs_root / "acceptance" / f"{run_id}.json"
        if snapshot_path.exists() and snapshot_path.is_file():
            try:
                data = json.loads(snapshot_path.read_text(encoding="utf-8"))
                return AcceptanceRunData(**data)
            except Exception:
                pass

        report_path = settings.outputs_root / "acceptance" / f"{run_id}.md"
        if not report_path.exists() or not report_path.is_file():
            return None
        parsed = self._parse_report_file(report_file=report_path)
        return AcceptanceRunData(
            run_id=parsed.run_id,
            status=parsed.status,
            started_at=parsed.started_at,
            finished_at=parsed.finished_at,
            selected_types=parsed.selected_types,
            summary=parsed.summary,
            aggregate_metrics={},
            results=[],
            report_path=str(report_path),
        )

    def _save_run_record(self, run_data: AcceptanceRunData) -> None:
        """将批次记录持久化到 acceptance_runs 集合。

        Args:
            run_data: 批次运行数据。
        """
        collection = get_acceptance_runs_collection()
        payload = run_data.model_dump(mode="json")
        payload["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload["execution_config"] = self._build_execution_config(selected_types=run_data.selected_types)
        collection.update_one(
            {"run_id": run_data.run_id},
            {"$set": payload},
            upsert=True,
        )

    def _load_run_record(self, run_id: str) -> AcceptanceRunData | None:
        """从 acceptance_runs 集合读取批次记录。

        Args:
            run_id: 批次运行 ID。

        Returns:
            批次运行对象，不存在时返回 None。
        """
        collection = get_acceptance_runs_collection()
        doc = collection.find_one({"run_id": run_id}, {"_id": 0})
        return self._deserialize_run_data(doc)

    @staticmethod
    def _deserialize_run_data(doc: dict[str, Any] | None) -> AcceptanceRunData | None:
        """将 Mongo 文档反序列化为批次运行对象。

        Args:
            doc: Mongo 文档。

        Returns:
            批次运行对象，不可用时返回 None。
        """
        if not isinstance(doc, dict):
            return None
        normalized = dict(doc)
        normalized.pop("updated_at", None)
        normalized.pop("execution_config", None)
        try:
            return AcceptanceRunData(**normalized)
        except Exception:
            return None

    def _build_execution_config(self, selected_types: list[str]) -> dict[str, str]:
        """构建本次批次的执行模式快照。

        Args:
            selected_types: 执行类型列表。

        Returns:
            `谱图类型 -> 执行模式` 映射。
        """
        config = self._load_config()
        samples_config = config.get("samples", {}) or {}
        result: dict[str, str] = {}
        for spectrum_type in selected_types:
            type_config = samples_config.get(spectrum_type, {}) or {}
            result[spectrum_type] = self._get_execution_mode(type_config=type_config)
        return result

    def _parse_report_file(self, report_file: Path) -> AcceptanceRunHistoryItem:
        """解析验收报告文件，提取历史展示信息。

        Args:
            report_file: 验收报告文件路径。

        Returns:
            历史批次列表项。
        """
        run_id = report_file.stem
        content = report_file.read_text(encoding="utf-8", errors="ignore")

        status = self._extract_line_value(content, "状态") or "FINISHED"
        started_at = self._extract_line_value(content, "开始时间") or ""
        finished_at = self._extract_line_value(content, "结束时间") or None
        selected_types_text = self._extract_line_value(content, "执行类型") or ""
        selected_types = [item.strip() for item in selected_types_text.split(",") if item.strip()]

        summary = AcceptanceRunSummary(
            total=self._extract_int_value(content, "总样本"),
            success=self._extract_int_value(content, "成功"),
            failed=self._extract_int_value(content, "失败"),
            progress=100,
            duration_seconds=self._extract_float_value(content, "总耗时(秒)"),
        )
        return AcceptanceRunHistoryItem(
            run_id=run_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            selected_types=selected_types,
            summary=summary,
            report_exists=True,
        )

    @staticmethod
    def _extract_line_value(content: str, key: str) -> str:
        """从 Markdown 列表行中提取键对应的值。"""
        pattern = re.compile(rf"-\s*{re.escape(key)}\s*[:：]\s*(.+)")
        match = pattern.search(content)
        if not match:
            return ""
        return match.group(1).strip()

    def _extract_int_value(self, content: str, key: str) -> int:
        """从报告键值中提取整数值。"""
        raw = self._extract_line_value(content, key)
        if not raw:
            return 0
        digits_match = re.search(r"[-+]?\d+", raw)
        if not digits_match:
            return 0
        return int(digits_match.group(0))

    def _extract_float_value(self, content: str, key: str) -> float:
        """从报告键值中提取浮点值。"""
        raw = self._extract_line_value(content, key)
        if not raw:
            return 0.0
        number_match = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
        if not number_match:
            return 0.0
        return float(number_match.group(0))

    @staticmethod
    def _parse_datetime_text(value: str) -> datetime | None:
        """将字符串时间解析为 datetime。"""
        if not value:
            return None
        value = str(value).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d_%H%M%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    def _to_history_item(self, run_data: AcceptanceRunData) -> AcceptanceRunHistoryItem:
        """将运行对象转换为历史列表项。

        Args:
            run_data: 批次运行对象。

        Returns:
            历史列表项。
        """
        return AcceptanceRunHistoryItem(
            run_id=run_data.run_id,
            status=run_data.status,
            started_at=run_data.started_at,
            finished_at=run_data.finished_at,
            selected_types=list(run_data.selected_types),
            summary=run_data.summary,
            report_exists=bool(run_data.report_path and Path(run_data.report_path).exists()),
        )

    def _load_artifacts_from_dir(self, output_dir: Path) -> list[TaskArtifactItem]:
        """从输出目录读取已有产物。

        Args:
            output_dir: 输出目录。

        Returns:
            产物列表。
        """
        if not output_dir.exists() or not output_dir.is_dir():
            return []

        items: list[TaskArtifactItem] = []
        for file_path in sorted(output_dir.rglob("*")):
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix in {".png", ".jpg", ".jpeg", ".svg"}:
                file_type = "image"
            elif suffix in {".txt", ".md", ".json", ".csv"}:
                file_type = "text"
            elif suffix in {".pdf"}:
                file_type = "pdf"
            else:
                file_type = "other"
            relative_path = file_path.relative_to(settings.outputs_root).as_posix()
            items.append(
                TaskArtifactItem(
                    name=file_path.name,
                    relative_path=relative_path,
                    file_type=file_type,
                    url=f"/static/outputs/{relative_path}",
                )
            )
        return items


acceptance_service = AcceptanceService()
