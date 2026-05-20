"""设备重复性评测服务。"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from app.core.config import settings
from app.infra.repositories import ConsistencyRunRepository
from app.schemas.consistency import (
    ConsistencyDeviceConfig,
    ConsistencyDeviceRunItem,
    ConsistencyRunData,
    ConsistencyRunHistoryItem,
    ConsistencyRunSummary,
)
from app.services.consistency_common import DEVICE_LABELS, format_number

class ConsistencyService:
    """提供设备重复性评测配置读取、批次执行与结果查询能力。"""

    def __init__(self) -> None:
        self.config_path = settings.consistency_config_path
        self._ensure_indexes()

    @staticmethod
    def _ensure_indexes() -> None:
        """初始化 consistency_runs 索引。"""
        collection = ConsistencyRunRepository.collection()
        collection.create_index("run_id", unique=True)
        collection.create_index("started_at")
        collection.create_index("status")

    def get_config_summary(self) -> tuple[Path, list[ConsistencyDeviceConfig], int]:
        """读取配置并返回设备摘要。"""
        config = self._load_config()
        devices_config = config.get("devices", {}) or {}
        items: list[ConsistencyDeviceConfig] = []
        for device_type in ("nmr", "gpc", "raman", "lcms"):
            device_config = devices_config.get(device_type, {}) or {}
            data_path = str(device_config.get("data_path") or "").strip()
            group_count = self._count_groups(device_type=device_type, data_path=data_path)
            items.append(
                ConsistencyDeviceConfig(
                    device_type=device_type,
                    label=str(device_config.get("label") or DEVICE_LABELS[device_type]),
                    data_path=data_path,
                    group_count=group_count,
                    enabled=bool(device_config.get("enabled", True)),
                    summary_description=str(device_config.get("summary_description") or ""),
                )
            )
        return self.config_path, items, len(items)

    def create_run(self, device_types: list[str] | None = None) -> ConsistencyRunData:
        """创建并异步启动一致性评测批次。"""
        selected_devices = self._normalize_types(device_types)
        run_id = f"cons_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        run_data = ConsistencyRunData(
            run_id=run_id,
            status="RUNNING",
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            finished_at=None,
            selected_devices=selected_devices,
            summary=ConsistencyRunSummary(total=0, success=0, failed=0, progress=0, duration_seconds=0.0),
            device_results=[],
            report_path=None,
        )
        self._save_run_record(run_data)

        from app.worker.tasks import execute_consistency_run_task

        try:
            execute_consistency_run_task.apply_async(args=[run_id], queue=settings.celery_task_queue)
        except Exception as exc:
            run_data.status = "FAILED"
            run_data.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            run_data.summary.progress = 100
            self._save_run_record(run_data)
            raise RuntimeError(f"Celery 派发失败: {exc}") from exc
        return run_data

    def get_run(self, run_id: str) -> ConsistencyRunData | None:
        """查询批次运行状态。"""
        record = self._load_run_record(run_id)
        if record:
            return record
        return self._load_run_snapshot(run_id)

    def list_runs(self, limit: int = 20) -> list[ConsistencyRunHistoryItem]:
        """查询一致性评测历史列表。"""
        safe_limit = max(1, min(int(limit or 20), 200))
        items: list[ConsistencyRunHistoryItem] = []
        known_run_ids: set[str] = set()
        collection = ConsistencyRunRepository.collection()
        cursor = collection.find({}, {"_id": 0}).sort([("started_at", -1)]).limit(safe_limit * 3)
        for document in cursor:
            run_data = self._deserialize_run_data(document)
            if not run_data or run_data.run_id in known_run_ids:
                continue
            items.append(self._to_history_item(run_data))
            known_run_ids.add(run_data.run_id)

        report_dir = settings.outputs_root / "consistency"
        if report_dir.exists() and report_dir.is_dir():
            snapshot_files = sorted(report_dir.glob("cons_*.json"), key=lambda path: path.name, reverse=True)
            for snapshot_file in snapshot_files:
                run_id = snapshot_file.stem
                if run_id in known_run_ids:
                    continue
                run_data = self._load_run_snapshot(run_id)
                if run_data:
                    items.append(self._to_history_item(run_data))
                    known_run_ids.add(run_id)

        items.sort(key=lambda item: item.started_at, reverse=True)
        return items[:safe_limit]

    def run_batch(self, run_id: str) -> None:
        """后台执行一致性评测批次。"""
        start_time = time.time()
        run_data = self._load_run_record(run_id)
        if not run_data:
            return
        selected_devices = list(run_data.selected_devices)
        total = len(selected_devices)
        run_data.summary.total = total
        self._save_run_record(run_data)
        if total == 0:
            self._finish_run(run_id, start_time)
            return

        success_count = 0
        failed_count = 0
        processed = 0
        config = self._load_config()
        devices_config = config.get("devices", {}) or {}
        for device_type in selected_devices:
            device_config = devices_config.get(device_type, {}) or {}
            data_path = str(device_config.get("data_path") or "").strip()
            device_start_time = time.time()
            try:
                if device_type == "nmr":
                    from app.services.consistency_nmr_service import run_nmr_consistency

                    result_item = run_nmr_consistency(
                        data_path=data_path,
                        output_dir=self._device_output_dir(run_id, device_type),
                    )
                elif device_type == "gpc":
                    from app.services.consistency_gpc_service import run_gpc_consistency

                    result_item = run_gpc_consistency(
                        data_path=data_path,
                        output_dir=self._device_output_dir(run_id, device_type),
                    )
                elif device_type == "raman":
                    from app.services.consistency_raman_service import run_raman_consistency

                    result_item = run_raman_consistency(
                        data_path=data_path,
                        output_dir=self._device_output_dir(run_id, device_type),
                    )
                elif device_type == "lcms":
                    from app.services.consistency_lcms_service import run_lcms_consistency

                    lcms_config_path = str(device_config.get("config_path") or "").strip()
                    result_item = run_lcms_consistency(
                        data_path=data_path,
                        output_dir=self._device_output_dir(run_id, device_type),
                        config_path=lcms_config_path,
                    )
                else:
                    result_item = ConsistencyDeviceRunItem(
                        device_type=device_type,
                        device_label=DEVICE_LABELS.get(device_type, device_type),
                        status="FAILED",
                        duration_seconds=0.0,
                        summary_metrics={},
                        group_results=[],
                        text_report="",
                        artifacts=[],
                        error_message=f"不支持的设备类型: {device_type}",
                    )
            except Exception as exc:
                result_item = ConsistencyDeviceRunItem(
                    device_type=device_type,
                    device_label=DEVICE_LABELS.get(device_type, device_type),
                    status="FAILED",
                    duration_seconds=0.0,
                    summary_metrics={},
                    group_results=[],
                    text_report="",
                    artifacts=[],
                    error_message=str(exc),
                )

            result_item.duration_seconds = time.time() - device_start_time
            run_data = self._load_run_record(run_id)
            if not run_data:
                return
            run_data.device_results.append(result_item)
            if result_item.status == "SUCCESS":
                success_count += 1
            else:
                failed_count += 1
            processed += 1
            run_data.summary.success = success_count
            run_data.summary.failed = failed_count
            run_data.summary.progress = int(processed / total * 100)
            self._save_run_record(run_data)

        self._finish_run(run_id, start_time)

    def _finish_run(self, run_id: str, start_time: float) -> None:
        """收尾批次并保存报告。"""
        run_data = self._load_run_record(run_id)
        if not run_data:
            return
        run_data.status = "FINISHED"
        run_data.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run_data.summary.progress = 100
        run_data.summary.duration_seconds = time.time() - start_time
        report_path = self._save_markdown_report(run_data)
        run_data.report_path = str(report_path)
        self._save_run_record(run_data)
        self._save_run_snapshot(run_data)

    def _load_config(self) -> dict[str, Any]:
        """加载一致性评测配置。"""
        with open(self.config_path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}

    @staticmethod
    def _normalize_types(device_types: list[str] | None) -> list[str]:
        """归一化设备类型列表。"""
        allowed_types = ["nmr", "gpc", "raman", "lcms"]
        if not device_types:
            return allowed_types
        normalized = []
        for device_type in device_types:
            normalized_type = str(device_type).strip().lower()
            if normalized_type in allowed_types and normalized_type not in normalized:
                normalized.append(normalized_type)
        return normalized or allowed_types

    @staticmethod
    def _count_groups(device_type: str, data_path: str) -> int:
        """统计设备配置下的样品组数。"""
        data_dir = Path(data_path)
        if not data_dir.exists():
            return 0
        if device_type == "nmr":
            return len([item for item in data_dir.iterdir() if item.is_dir()])
        if device_type == "gpc":
            group_names: set[str] = set()
            for sample_dir in data_dir.iterdir():
                if not sample_dir.is_dir():
                    continue
                json_files = sorted(file_path for file_path in sample_dir.iterdir() if file_path.suffix.lower() == ".json")
                if not json_files:
                    continue
                try:
                    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
                except Exception:
                    continue
                code = str(payload.get("code") or "").strip()
                if not code:
                    continue
                group_names.add(code.rsplit("_", 1)[0] if "_" in code else code)
            return len(group_names)
        if device_type == "raman":
            return len({item.name.rsplit("_", 1)[0] for item in data_dir.iterdir() if item.is_file() and "_" in item.name})
        if device_type == "lcms":
            file_names = [item.name for item in data_dir.iterdir() if item.is_file() and item.suffix == ".mzML"]
            return len(
                {
                    file_name.rsplit("_", 1)[0]
                    if "_" in file_name and file_name.rsplit("_", 1)[1].replace(".mzML", "").isdigit()
                    else file_name.replace(".mzML", "")
                    for file_name in file_names
                }
            )
        return 0

    @staticmethod
    def _device_output_dir(run_id: str, device_type: str) -> Path:
        """构建设备输出目录。"""
        output_dir = settings.outputs_root / "consistency" / run_id / device_type
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _save_markdown_report(self, run_data: ConsistencyRunData) -> Path:
        """保存批次 Markdown 报告。"""
        report_dir = settings.outputs_root / "consistency"
        report_dir.mkdir(parents=True, exist_ok=True)
        file_path = report_dir / f"{run_data.run_id}.md"
        lines = [
            f"# 设备重复性评测报告 {run_data.run_id}",
            "",
            f"- 状态: {run_data.status}",
            f"- 开始时间: {run_data.started_at}",
            f"- 结束时间: {run_data.finished_at or ''}",
            f"- 设备类型: {', '.join(run_data.selected_devices)}",
            f"- 总设备: {run_data.summary.total}",
            f"- 成功: {run_data.summary.success}",
            f"- 失败: {run_data.summary.failed}",
            f"- 总耗时(秒): {run_data.summary.duration_seconds:.1f}",
            "",
            "## 设备汇总",
            "",
        ]
        for device_result in run_data.device_results:
            lines.append(f"### {device_result.device_label}")
            lines.append(f"- 状态: {device_result.status}")
            for key, value in device_result.summary_metrics.items():
                if isinstance(value, (int, float)):
                    lines.append(f"- {key}: {format_number(value, 4)}")
                else:
                    lines.append(f"- {key}: {value}")
            if device_result.error_message:
                lines.append(f"- 错误: {device_result.error_message}")
            lines.append("")

        lines.append("## 设备明细")
        lines.append("")
        for device_result in run_data.device_results:
            lines.append(f"### {device_result.device_label}")
            lines.append("")
            if not device_result.group_results:
                lines.append("- 无可展示明细")
                lines.append("")
                continue
            for group_result in device_result.group_results:
                lines.append(f"- {group_result.group_name} | {group_result.status} | {group_result.remark}")
            lines.append("")

        file_path.write_text("\n".join(lines), encoding="utf-8")
        return file_path

    def _save_run_snapshot(self, run_data: ConsistencyRunData) -> Path:
        """保存批次结构化快照。"""
        snapshot_path = settings.outputs_root / "consistency" / f"{run_data.run_id}.json"
        snapshot_path.write_text(
            json.dumps(run_data.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return snapshot_path

    def _save_run_record(self, run_data: ConsistencyRunData) -> None:
        """持久化批次记录。"""
        collection = ConsistencyRunRepository.collection()
        payload = run_data.model_dump(mode="json")
        payload["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        collection.update_one({"run_id": run_data.run_id}, {"$set": payload}, upsert=True)

    def _load_run_record(self, run_id: str) -> ConsistencyRunData | None:
        """读取批次记录。"""
        document = ConsistencyRunRepository.collection().find_one({"run_id": run_id}, {"_id": 0})
        return self._deserialize_run_data(document)

    @staticmethod
    def _deserialize_run_data(document: dict[str, Any] | None) -> ConsistencyRunData | None:
        """反序列化运行数据。"""
        if not isinstance(document, dict):
            return None
        normalized = dict(document)
        normalized.pop("updated_at", None)
        try:
            return ConsistencyRunData(**normalized)
        except Exception:
            return None

    def _load_run_snapshot(self, run_id: str) -> ConsistencyRunData | None:
        """从 JSON 快照读取批次信息。"""
        snapshot_path = settings.outputs_root / "consistency" / f"{run_id}.json"
        if not snapshot_path.exists() or not snapshot_path.is_file():
            return None
        try:
            data = json.loads(snapshot_path.read_text(encoding="utf-8"))
            return ConsistencyRunData(**data)
        except Exception:
            return None

    @staticmethod
    def _to_history_item(run_data: ConsistencyRunData) -> ConsistencyRunHistoryItem:
        """将运行对象转为历史项。"""
        return ConsistencyRunHistoryItem(
            run_id=run_data.run_id,
            status=run_data.status,
            started_at=run_data.started_at,
            finished_at=run_data.finished_at,
            selected_devices=list(run_data.selected_devices),
            summary=run_data.summary,
            report_exists=bool(run_data.report_path and Path(run_data.report_path).exists()),
        )


consistency_service = ConsistencyService()
