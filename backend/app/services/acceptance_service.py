"""批量验收测试服务。"""

from __future__ import annotations

import threading
import time
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from app.core.config import settings
from app.schemas.acceptance import (
    AcceptanceRunHistoryItem,
    AcceptanceRunData,
    AcceptanceRunItem,
    AcceptanceRunSummary,
    AcceptanceTypeConfig,
)
from app.services.task_service import task_service

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
            samples = self._scan_samples(spectrum_type=spectrum_type, type_config=type_config)
            dirs = [str(item) for item in type_config.get("dirs", []) if str(item).strip()]
            count = len(samples)
            total_samples += count
            items.append(
                AcceptanceTypeConfig(
                    spectrum_type=spectrum_type,
                    label=TYPE_LABELS[spectrum_type],
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
        return self._load_run_from_report(run_id)

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
            history.append(
                AcceptanceRunHistoryItem(
                    run_id=run_data.run_id,
                    status=run_data.status,
                    started_at=run_data.started_at,
                    finished_at=run_data.finished_at,
                    selected_types=list(run_data.selected_types),
                    summary=run_data.summary,
                    report_exists=bool(run_data.report_path and Path(run_data.report_path).exists()),
                )
            )
            known_run_ids.add(run_data.run_id)

        report_dir = settings.outputs_root / "acceptance"
        if report_dir.exists() and report_dir.is_dir():
            report_files = sorted(report_dir.glob("acc_*.md"), key=lambda path: path.name, reverse=True)
            for report_file in report_files:
                run_id = report_file.stem
                if run_id in known_run_ids:
                    continue
                parsed = self._parse_report_file(report_file=report_file)
                history.append(parsed)

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
        for spectrum_type in selected_types:
            type_config = (config.get("samples", {}) or {}).get(spectrum_type, {}) or {}
            all_samples.extend(self._scan_samples(spectrum_type=spectrum_type, type_config=type_config))

        self._update_run_summary(run_id=run_id, total=len(all_samples), success=0, failed=0, progress=0)
        if not all_samples:
            self._finish_run(run_id=run_id, status="FINISHED", start_time=start_time)
            return

        success_count = 0
        failed_count = 0
        for index, sample in enumerate(all_samples, start=1):
            item = self._execute_single_sample(sample=sample)
            if item.status == "SUCCESS":
                success_count += 1
            else:
                failed_count += 1
            progress = int(index / len(all_samples) * 100)
            with self._lock:
                run_data = self._run_store.get(run_id)
                if not run_data:
                    return
                run_data.results.append(item)
                run_data.summary.success = success_count
                run_data.summary.failed = failed_count
                run_data.summary.progress = progress

        self._finish_run(run_id=run_id, status="FINISHED", start_time=start_time)

    def _execute_single_sample(self, sample: AcceptanceSample) -> AcceptanceRunItem:
        """执行单样本验收。

        Args:
            sample: 验收样本。

        Returns:
            单样本执行结果。
        """
        created_at = time.time()
        try:
            payload = self._build_task_payload(sample=sample)
            created = task_service.create_task(
                task_type=payload["task_type"],
                input_data=payload["input"],
                params=payload["params"],
            )
            task_id = str(created.get("task_id", ""))
            timeout_seconds = int(payload.get("timeout_seconds", 240))
            final_status = self._poll_task(task_id=task_id, timeout_seconds=timeout_seconds)
            duration = time.time() - created_at
            if final_status == "SUCCESS":
                metrics = self._extract_sample_metrics(task_id=task_id, spectrum_type=sample.spectrum_type)
                return AcceptanceRunItem(
                    spectrum_type=sample.spectrum_type,
                    sample_name=sample.sample_name,
                    sample_path=sample.sample_path,
                    task_id=task_id,
                    status="SUCCESS",
                    duration_seconds=duration,
                    metrics=metrics,
                    error_message=None,
                )

            task_data = task_service.get_task_status(task_id=task_id)
            detail = None
            if task_data and task_data.error:
                detail = str(task_data.error.get("detail"))
            return AcceptanceRunItem(
                spectrum_type=sample.spectrum_type,
                sample_name=sample.sample_name,
                sample_path=sample.sample_path,
                task_id=task_id,
                status="FAILED",
                duration_seconds=duration,
                metrics={},
                error_message=detail or "task failed",
            )
        except Exception as exc:
            return AcceptanceRunItem(
                spectrum_type=sample.spectrum_type,
                sample_name=sample.sample_name,
                sample_path=sample.sample_path,
                task_id="",
                status="FAILED",
                duration_seconds=time.time() - created_at,
                metrics={},
                error_message=str(exc),
            )

    @staticmethod
    def _poll_task(task_id: str, timeout_seconds: int = 240) -> str:
        """轮询任务状态直到结束。

        Args:
            task_id: 任务 ID。
            timeout_seconds: 超时时间。

        Returns:
            最终任务状态。
        """
        start_time = time.time()
        while True:
            task_data = task_service.get_task_status(task_id=task_id)
            if not task_data:
                return "FAILED"
            if task_data.status in {"SUCCESS", "FAILED"}:
                return task_data.status
            if time.time() - start_time > timeout_seconds:
                return "FAILED"
            time.sleep(1.0)

    def _build_task_payload(self, sample: AcceptanceSample) -> dict:
        """构建批量验收任务参数。

        Args:
            sample: 验收样本。

        Returns:
            任务入参字典。
        """
        spectrum_type = sample.spectrum_type
        if spectrum_type == "gpc":
            return {
                "task_type": TYPE_TO_TASK_KIND[spectrum_type],
                "timeout_seconds": 240,
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
                "timeout_seconds": 240,
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
            "timeout_seconds": 240,
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
                    # GPC 需兼容两种组织形态：
                    # 1) 根目录下直接放谱图文件；
                    # 2) 样品目录中再包含谱图文件。
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

    def _load_config(self) -> dict:
        """加载验收配置文件。

        Returns:
            配置字典。
        """
        if not self.config_path.exists():
            return {"samples": {}}
        content = self.config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}
        return data if isinstance(data, dict) else {"samples": {}}

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

    def _finish_run(self, run_id: str, status: str, start_time: float) -> None:
        """结束批次运行并保存摘要报告。

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

    @staticmethod
    def _build_aggregate_metrics(results: list[AcceptanceRunItem]) -> dict:
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
                "sample_count": len(raman_items),
                "task_success_rate": _rate(raman_items),
                "labeled_count": 0,
                "top1_accuracy": None,
                "recall_at_3": None,
            },
        }

    def _extract_sample_metrics(self, task_id: str, spectrum_type: str) -> dict[str, Any]:
        """提取单样本可聚合指标。

        Args:
            task_id: 任务 ID。
            spectrum_type: 谱图类型。

        Returns:
            指标字典。
        """
        result_data = task_service.get_task_result(task_id=task_id)
        if not result_data or result_data.status != "SUCCESS" or not result_data.result:
            return {}

        result_payload = result_data.result or {}
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
                f"- Recall@3: {self._format_percent(raman_metrics.get('recall_at_3'))}",
                "",
                "## 样本明细",
                "",
                "| 类型 | 样本 | 状态 | 耗时(s) | 任务ID | 错误 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in run_data.results:
            lines.append(
                f"| {item.spectrum_type} | {item.sample_name} | {item.status} | "
                f"{item.duration_seconds:.1f} | {item.task_id} | {item.error_message or ''} |"
            )
        file_path.write_text("\n".join(lines), encoding="utf-8")
        return file_path

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


    def _load_run_from_report(self, run_id: str) -> AcceptanceRunData | None:
        """从历史报告文件加载批次基础信息。

        Args:
            run_id: 批次运行 ID。

        Returns:
            运行数据对象；若报告不存在则返回 None。
        """
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
        pattern = re.compile(rf"-\\s*{re.escape(key)}\\s*[:：]\\s*(.+)")
        match = pattern.search(content)
        if not match:
            return ""
        return match.group(1).strip()

    def _extract_int_value(self, content: str, key: str) -> int:
        """从报告键值中提取整数值。"""
        raw = self._extract_line_value(content, key)
        if not raw:
            return 0
        digits_match = re.search(r"[-+]?\\d+", raw)
        if not digits_match:
            return 0
        return int(digits_match.group(0))

    def _extract_float_value(self, content: str, key: str) -> float:
        """从报告键值中提取浮点值。"""
        raw = self._extract_line_value(content, key)
        if not raw:
            return 0.0
        number_match = re.search(r"[-+]?\\d+(?:\\.\\d+)?", raw)
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


acceptance_service = AcceptanceService()
