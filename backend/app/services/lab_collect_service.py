"""实验室数据采集服务。"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from rdkit import Chem
from rdkit.Chem import Fragments
from rdkit.Chem.Scaffolds import MurckoScaffold

from app.core.config import settings
from app.core.logging import get_logger
from app.infra.repositories import (
    LabCollectRunRepository,
    MolecularStatisticsRepository,
    SpectrumSampleFileRepository,
    SpectrumSampleRepository,
)
from app.schemas.lab_collect import (
    LabCollectConfigData,
    LabCollectRunCreateData,
    LabCollectRunError,
    LabCollectRunRecord,
    LabCollectRunSummary,
    LabCollectorTypeConfig,
    MolecularStatisticsData,
    SpectrumSampleDetailData,
    SpectrumSampleFileRecord,
    SpectrumSampleListData,
    SpectrumSampleListItem,
    SpectrumSampleRecord,
    SpectrumSampleSummaryData,
)


TYPE_INPUT_KIND = {
    "nmr": "folder_path",
    "gpc": "file_path",
    "ir": "file_path",
    "raman": "file_path",
    "lcms": "file_path",
}

logger = get_logger("spec_agent.services.lab_collect")

COLLECT_SUMMARY_KEYS = ("candidates", "imported", "updated", "skipped", "failed")
SAMPLE_SUMMARY_TYPES = ("nmr", "gpc", "ir", "raman", "lcms")
RUN_PROGRESS_SAVE_INTERVAL = 100
MOLECULAR_STATS_KEY = "sample_smiles_overview"


@dataclass
class CollectCandidate:
    """待采集候选样本。"""

    spectrum_type: str
    source_date: str
    sample_name: str
    remote_path: Path
    remote_date_dir: Path
    sample_mode: str
    local_root: Path
    share_key: str
    patterns: list[str]


@dataclass
class CollectSingleCandidateResult:
    """单个候选样品采集结果。"""

    action: str
    sample_id: str | None = None


class LabCollectService:
    """实验室共享目录采集服务。"""

    def __init__(self) -> None:
        self.config_path = settings.lab_collectors_config_path
        self._ensure_indexes()

    @staticmethod
    def _ensure_indexes() -> None:
        """初始化集合索引。"""
        LabCollectRunRepository.collection().create_index("run_id", unique=True)
        LabCollectRunRepository.collection().create_index([("created_at", -1)])
        LabCollectRunRepository.collection().create_index([("status", 1), ("created_at", -1)])

        SpectrumSampleRepository.collection().create_index("sample_key", unique=True)
        SpectrumSampleRepository.collection().create_index(
            [("spectrum_type", 1), ("source_date", -1), ("sample_name", 1)]
        )
        SpectrumSampleRepository.collection().create_index(
            [("source_date", -1), ("spectrum_type", 1), ("sample_name_normalized", 1)]
        )
        SpectrumSampleRepository.collection().create_index([("latest_run_id", 1)])

        SpectrumSampleFileRepository.collection().create_index(
            [("sample_id", 1), ("relative_path", 1)],
            unique=True,
        )
        SpectrumSampleFileRepository.collection().create_index([("sample_key", 1)])
        SpectrumSampleFileRepository.collection().create_index([("spectrum_type", 1), ("file_ext", 1)])
        MolecularStatisticsRepository.collection().create_index("stats_key", unique=True)

    def get_config_summary(self) -> LabCollectConfigData:
        """读取采集配置摘要。"""
        config = self._load_config()
        items: list[LabCollectorTypeConfig] = []
        for spectrum_type in ("nmr", "gpc", "ir", "raman", "lcms"):
            item = (config.get("collectors", {}) or {}).get(spectrum_type, {}) or {}
            items.append(
                LabCollectorTypeConfig(
                    spectrum_type=spectrum_type,
                    enabled=bool(item.get("enabled", False)),
                    share_key=str(item.get("share_key") or ""),
                    remote_root=str(item.get("remote_root") or ""),
                    local_root=str(item.get("local_root") or ""),
                    sample_mode=str(item.get("sample_mode") or ("directory" if spectrum_type in {"nmr", "gpc"} else "file")),
                    patterns=[str(pattern) for pattern in (item.get("patterns", []) or []) if str(pattern).strip()],
                )
            )
        return LabCollectConfigData(config_path=str(self.config_path), items=items)

    def create_run(
        self,
        collect_date: str | None,
        date_from: str | None,
        date_to: str | None,
        spectrum_types: list[str] | None,
        overwrite_existing: bool = False,
    ) -> LabCollectRunCreateData:
        """创建采集批次并异步执行。"""
        selected_types = self._normalize_types(spectrum_types=spectrum_types)
        trigger_mode = "single_date" if collect_date else "date_range"
        normalized_from = collect_date or str(date_from)
        normalized_to = collect_date or str(date_to)
        config = self._load_config()
        snapshot = {
            spectrum_type: ((config.get("collectors", {}) or {}).get(spectrum_type, {}) or {})
            for spectrum_type in selected_types
        }
        now = datetime.now()
        run_id = f"lcr_{now.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        run_record = LabCollectRunRecord(
            run_id=run_id,
            status="PENDING",
            spectrum_types=selected_types,
            overwrite_existing=bool(overwrite_existing),
            date_from=normalized_from,
            date_to=normalized_to,
            trigger_mode=trigger_mode,
            config_snapshot=snapshot,
            summary=LabCollectRunSummary(),
            errors=[],
            started_at=None,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        LabCollectRunRepository.save(run_record)

        from app.worker.tasks import execute_lab_collect_run_task

        try:
            execute_lab_collect_run_task.apply_async(args=[run_id], queue=settings.celery_task_queue)
            run_record.status = "QUEUED"
            run_record.updated_at = datetime.now()
            LabCollectRunRepository.save(run_record)
        except Exception as exc:
            logger.error("采集批次 %s Celery 派发失败: %s", run_id, exc)
            run_record.status = "FAILED"
            run_record.finished_at = datetime.now()
            run_record.updated_at = datetime.now()
            run_record.summary.failed = 1
            run_record.summary.progress = 100
            run_record.errors.append(
                LabCollectRunError(
                    spectrum_type=selected_types[0] if selected_types else "nmr",
                    source_date=normalized_from,
                    remote_path="",
                    sample_name="dispatch",
                    error_message=f"Celery 派发失败: {exc}",
                )
            )
            LabCollectRunRepository.save(run_record)
        return LabCollectRunCreateData(run_id=run_id, status=run_record.status)

    def get_run(self, run_id: str) -> LabCollectRunRecord | None:
        """查询采集批次。"""
        return LabCollectRunRepository.find_by_run_id(run_id)

    def list_runs(self, limit: int = 20) -> list[LabCollectRunRecord]:
        """查询采集批次列表。"""
        safe_limit = max(1, min(int(limit or 20), 200))
        return LabCollectRunRepository.list_recent(limit=safe_limit)

    def list_samples(
        self,
        page: int = 1,
        page_size: int = 20,
        spectrum_type: str | None = None,
        source_date: str | None = None,
        sample_name: str | None = None,
    ) -> SpectrumSampleListData:
        """分页查询样本主档。"""
        safe_page = max(1, int(page or 1))
        safe_size = max(1, min(int(page_size or 20), 100))
        query: dict[str, Any] = {}
        if spectrum_type:
            query["spectrum_type"] = str(spectrum_type).strip().lower()
        if source_date:
            query["source_date"] = str(source_date).strip()
        if sample_name:
            normalized = self._normalize_sample_name(sample_name)
            query["sample_name_normalized"] = {"$regex": re.escape(normalized)}
        total, records = SpectrumSampleRepository.list_paginated(query=query, page=safe_page, page_size=safe_size)
        items = [
            SpectrumSampleListItem(
                sample_id=record.sample_id,
                sample_key=record.sample_key,
                spectrum_type=record.spectrum_type,
                source_date=record.source_date,
                sample_name=record.sample_name,
                collect_status=record.collect_status,
                latest_run_id=record.latest_run_id,
                updated_at=record.updated_at,
                analysis_input=record.analysis_input,
            )
            for record in records
        ]
        return SpectrumSampleListData(total=total, page=safe_page, page_size=safe_size, items=items)

    def get_sample_detail(self, sample_id: str) -> SpectrumSampleDetailData | None:
        """查询样本详情。"""
        sample = SpectrumSampleRepository.find_by_sample_id(sample_id=sample_id)
        if not sample:
            return None
        files = SpectrumSampleFileRepository.find_by_sample_id(sample_id=sample_id)
        return SpectrumSampleDetailData(sample=sample, files=files)

    def delete_sample(self, sample_id: str) -> bool:
        """删除样本及其本地存储。"""
        sample = SpectrumSampleRepository.find_by_sample_id(sample_id=sample_id)
        if not sample:
            return False

        local_sample_path = Path(str((sample.storage or {}).get("local_sample_path") or "")).expanduser()
        if str(local_sample_path).strip() and local_sample_path.exists():
            if local_sample_path.is_dir():
                shutil.rmtree(local_sample_path)
            else:
                local_sample_path.unlink()

        SpectrumSampleFileRepository.delete_by_sample_id(sample_id=sample_id)
        SpectrumSampleRepository.delete_by_sample_id(sample_id=sample_id)
        self._mark_molecular_statistics_stale()
        return True

    def get_sample_summary(self) -> SpectrumSampleSummaryData:
        """汇总样本资产概览数据。"""
        collection = SpectrumSampleRepository.collection()
        total_samples = int(collection.count_documents({}))
        type_counts = {spectrum_type: 0 for spectrum_type in SAMPLE_SUMMARY_TYPES}

        cursor = collection.aggregate(
            [
                {"$group": {"_id": "$spectrum_type", "count": {"$sum": 1}}},
            ]
        )
        for item in cursor:
            spectrum_type = str(item.get("_id") or "").strip().lower()
            if spectrum_type in type_counts:
                type_counts[spectrum_type] = int(item.get("count") or 0)

        latest_doc = collection.find_one({}, {"updated_at": 1, "_id": 0}, sort=[("updated_at", -1)])
        latest_updated_at = latest_doc.get("updated_at") if latest_doc else None
        return SpectrumSampleSummaryData(
            total_samples=total_samples,
            type_counts=type_counts,
            latest_updated_at=latest_updated_at,
        )

    def get_molecular_statistics(self) -> MolecularStatisticsData:
        """获取缓存的分子资产统计结果。"""
        cached = MolecularStatisticsRepository.find_by_key(stats_key=MOLECULAR_STATS_KEY)
        if cached:
            return cached
        return MolecularStatisticsData(stats_key=MOLECULAR_STATS_KEY)

    def refresh_molecular_statistics(self) -> MolecularStatisticsData:
        """重新计算并刷新分子资产统计缓存。"""
        sample_collection = SpectrumSampleRepository.collection()
        cursor = sample_collection.find(
            {"sample_meta.smiles": {"$exists": True, "$nin": ["", None]}},
            {"_id": 0, "sample_meta.smiles": 1},
        )

        raw_smiles_list = [
            str(((item.get("sample_meta") or {}).get("smiles") or "")).strip()
            for item in cursor
            if str(((item.get("sample_meta") or {}).get("smiles") or "")).strip()
        ]
        unique_smiles = sorted(set(raw_smiles_list))
        unique_scaffolds: set[str] = set()
        unique_functional_groups: set[str] = set()

        for smiles in unique_smiles:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                continue
            try:
                scaffold_mol = MurckoScaffold.GetScaffoldForMol(mol)
                scaffold_smiles = Chem.MolToSmiles(scaffold_mol)
                if scaffold_smiles:
                    unique_scaffolds.add(scaffold_smiles)
            except Exception:
                pass

            for func_name in dir(Fragments):
                if not func_name.startswith("fr_"):
                    continue
                fg_func = getattr(Fragments, func_name)
                try:
                    if fg_func(mol) > 0:
                        unique_functional_groups.add(func_name)
                except Exception:
                    continue

        stats_record = MolecularStatisticsData(
            stats_key=MOLECULAR_STATS_KEY,
            unique_smiles_count=len(unique_smiles),
            unique_scaffold_count=len(unique_scaffolds),
            unique_functional_group_count=len(unique_functional_groups),
            functional_groups=sorted(unique_functional_groups),
            source_sample_count=len(raw_smiles_list),
            source_smiles_count=len(raw_smiles_list),
            is_stale=False,
            status="SUCCESS",
            updated_at=datetime.now(),
            error_message=None,
        )
        MolecularStatisticsRepository.save(stats_record)
        return stats_record

    def run_collect(self, run_id: str) -> None:
        """执行采集批次。"""
        run_record = LabCollectRunRepository.find_by_run_id(run_id=run_id)
        if not run_record:
            return
        run_record.status = "RUNNING"
        run_record.started_at = datetime.now()
        run_record.updated_at = datetime.now()
        LabCollectRunRepository.save(run_record)

        dates = self._build_date_list(date_from=run_record.date_from, date_to=run_record.date_to)
        candidates: list[CollectCandidate] = []
        errors: list[LabCollectRunError] = []
        for spectrum_type in run_record.spectrum_types:
            try:
                candidates.extend(self._scan_candidates(spectrum_type=spectrum_type, dates=dates))
            except Exception as exc:
                errors.append(
                    LabCollectRunError(
                        spectrum_type=spectrum_type,
                        source_date=run_record.date_from,
                        remote_path="",
                        sample_name="scan",
                        error_message=str(exc),
                    )
                )

        run_record.summary.total_days = len(dates)
        run_record.summary.total_candidates = len(candidates)
        LabCollectRunRepository.save(run_record)

        imported = 0
        updated = 0
        skipped = 0
        failed = len(errors)
        processed = 0
        total_work = max(len(candidates), 1)
        type_stats = self._build_empty_type_stats(run_record.spectrum_types)

        for candidate in candidates:
            type_stats.setdefault(candidate.spectrum_type, self._build_empty_type_summary())
            type_stats[candidate.spectrum_type]["candidates"] += 1

        for error in errors:
            type_stats.setdefault(error.spectrum_type, self._build_empty_type_summary())
            type_stats[error.spectrum_type]["failed"] += 1

        run_record.summary.type_stats = type_stats
        LabCollectRunRepository.save(run_record)

        skipped_candidates: list[CollectCandidate] = []
        pending_candidates = candidates
        if not run_record.overwrite_existing and candidates:
            candidate_keys = [self._build_sample_key(candidate=candidate) for candidate in candidates]
            existing_keys = SpectrumSampleRepository.find_existing_sample_keys(sample_keys=candidate_keys)
            pending_candidates = []
            for candidate in candidates:
                if self._build_sample_key(candidate=candidate) in existing_keys:
                    skipped_candidates.append(candidate)
                    continue
                pending_candidates.append(candidate)

        skipped = len(skipped_candidates)
        processed = skipped
        for candidate in skipped_candidates:
            type_stats[candidate.spectrum_type]["skipped"] += 1

        self._save_run_progress(
            run_record=run_record,
            imported=imported,
            updated=updated,
            skipped=skipped,
            failed=failed,
            processed=processed,
            total_work=total_work,
            type_stats=type_stats,
            errors=errors,
        )

        for candidate in pending_candidates:
            try:
                result = self._collect_single_candidate(
                    run_id=run_id,
                    candidate=candidate,
                    overwrite_existing=run_record.overwrite_existing,
                )
                if result.action == "skipped":
                    skipped += 1
                    type_stats[candidate.spectrum_type]["skipped"] += 1
                elif result.action == "updated":
                    updated += 1
                    type_stats[candidate.spectrum_type]["updated"] += 1
                else:
                    imported += 1
                    type_stats[candidate.spectrum_type]["imported"] += 1
            except Exception as exc:
                failed += 1
                type_stats.setdefault(candidate.spectrum_type, self._build_empty_type_summary())
                type_stats[candidate.spectrum_type]["failed"] += 1
                errors.append(
                    LabCollectRunError(
                        spectrum_type=candidate.spectrum_type,
                        source_date=candidate.source_date,
                        remote_path=str(candidate.remote_path),
                        sample_name=candidate.sample_name,
                        error_message=str(exc),
                    )
                )
            processed += 1
            if processed % RUN_PROGRESS_SAVE_INTERVAL == 0 or processed == total_work:
                self._save_run_progress(
                    run_record=run_record,
                    imported=imported,
                    updated=updated,
                    skipped=skipped,
                    failed=failed,
                    processed=processed,
                    total_work=total_work,
                    type_stats=type_stats,
                    errors=errors,
                )

        run_record.status = "FAILED" if failed and not (imported or updated) else ("PARTIAL_SUCCESS" if failed else "SUCCESS")
        run_record.summary.imported = imported
        run_record.summary.updated = updated
        run_record.summary.skipped = skipped
        run_record.summary.failed = failed
        run_record.summary.progress = 100
        run_record.summary.type_stats = type_stats
        run_record.errors = errors
        run_record.finished_at = datetime.now()
        run_record.updated_at = datetime.now()
        LabCollectRunRepository.save(run_record)

    @staticmethod
    def _build_empty_type_summary() -> dict[str, int]:
        """构建单个谱图类型的空汇总。"""
        return {key: 0 for key in COLLECT_SUMMARY_KEYS}

    @classmethod
    def _build_empty_type_stats(cls, spectrum_types: list[str]) -> dict[str, dict[str, int]]:
        """为本次批次初始化按类型汇总。"""
        return {spectrum_type: cls._build_empty_type_summary() for spectrum_type in spectrum_types}

    def _collect_single_candidate(
        self,
        run_id: str,
        candidate: CollectCandidate,
        overwrite_existing: bool,
    ) -> CollectSingleCandidateResult:
        """采集单个样本。"""
        sample_key = self._build_sample_key(candidate=candidate)
        existed = SpectrumSampleRepository.find_by_sample_key(sample_key=sample_key)
        if existed and not overwrite_existing:
            return CollectSingleCandidateResult(action="skipped", sample_id=existed.sample_id)
        sample_id = existed.sample_id if existed else f"sp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        local_date_dir = candidate.local_root / candidate.source_date
        local_date_dir.mkdir(parents=True, exist_ok=True)
        local_sample_path = local_date_dir / candidate.sample_name

        if local_sample_path.exists():
            if local_sample_path.is_dir():
                shutil.rmtree(local_sample_path)
            else:
                local_sample_path.unlink()

        if candidate.sample_mode == "directory":
            shutil.copytree(candidate.remote_path, local_sample_path)
            local_files = [path for path in sorted(local_sample_path.rglob("*")) if path.is_file()]
        else:
            shutil.copy2(candidate.remote_path, local_sample_path)
            local_files = [local_sample_path]

        file_records, analysis_input, sample_meta, total_size = self._build_sample_files_and_meta(
            sample_id=sample_id,
            sample_key=sample_key,
            candidate=candidate,
            local_sample_path=local_sample_path,
            local_files=local_files,
        )

        now = datetime.now()
        sample_record = SpectrumSampleRecord(
            sample_id=sample_id,
            sample_key=sample_key,
            spectrum_type=candidate.spectrum_type,
            source_date=candidate.source_date,
            sample_name=candidate.sample_name,
            sample_name_normalized=self._normalize_sample_name(candidate.sample_name),
            source={
                "share_key": candidate.share_key,
                "remote_date_dir": str(candidate.remote_date_dir),
                "remote_sample_path": str(candidate.remote_path),
                "identity_mode": "spectrum_type+source_date+sample_name",
            },
            storage={
                "local_root": str(candidate.local_root),
                "local_sample_path": str(local_sample_path),
            },
            analysis_input=analysis_input,
            collect_status="SUCCESS",
            collect_stats={
                "file_count": len(file_records),
                "primary_file_count": sum(1 for item in file_records if item.is_primary_input),
                "total_size": total_size,
            },
            sample_meta=sample_meta,
            latest_run_id=run_id,
            collect_count=(existed.collect_count + 1) if existed else 1,
            created_at=existed.created_at if existed else now,
            updated_at=now,
        )
        SpectrumSampleRepository.save(sample_record)
        SpectrumSampleFileRepository.replace_for_sample(sample_id=sample_id, file_records=file_records)
        self._mark_molecular_statistics_stale()
        return CollectSingleCandidateResult(
            action="updated" if existed else "imported",
            sample_id=sample_id,
        )

    def _mark_molecular_statistics_stale(self) -> None:
        """将分子资产统计缓存标记为过期。"""
        cached = MolecularStatisticsRepository.find_by_key(stats_key=MOLECULAR_STATS_KEY)
        if not cached:
            return
        cached.is_stale = True
        MolecularStatisticsRepository.save(cached)

    def _build_sample_files_and_meta(
        self,
        sample_id: str,
        sample_key: str,
        candidate: CollectCandidate,
        local_sample_path: Path,
        local_files: list[Path],
    ) -> tuple[list[SpectrumSampleFileRecord], dict[str, Any], dict[str, Any], int]:
        """构建文件清单、分析输入和样本元数据。"""
        total_size = 0
        file_records: list[SpectrumSampleFileRecord] = []
        copied_at = datetime.now()
        primary_input_path = str(local_sample_path)
        sample_meta: dict[str, Any] = {}
        gpc_json_candidates: list[Path] = []
        gpc_primary_arw: Path | None = None
        gpc_validation_pdf: Path | None = None

        for local_file in local_files:
            total_size += int(local_file.stat().st_size)
            relative_path = (
                local_file.relative_to(local_sample_path).as_posix()
                if local_sample_path.is_dir()
                else local_file.name
            )
            remote_file_path = (
                candidate.remote_path / relative_path
                if candidate.sample_mode == "directory"
                else candidate.remote_path
            )
            role = self._detect_file_role(
                spectrum_type=candidate.spectrum_type,
                local_file=local_file,
                local_sample_path=local_sample_path,
            )
            is_primary_input = False
            if candidate.spectrum_type == "gpc" and role == "primary_spectrum" and gpc_primary_arw is None:
                gpc_primary_arw = local_file
                is_primary_input = True
            elif candidate.spectrum_type in {"ir", "raman", "lcms"} and role == "primary_spectrum":
                is_primary_input = True
                primary_input_path = str(local_file)
            elif candidate.spectrum_type == "nmr":
                primary_input_path = str(local_sample_path)

            if candidate.spectrum_type == "gpc":
                if role == "validation_pdf" and gpc_validation_pdf is None:
                    gpc_validation_pdf = local_file
                if role == "experiment_json":
                    gpc_json_candidates.append(local_file)

            file_records.append(
                SpectrumSampleFileRecord(
                    sample_file_id=f"spf_{uuid4().hex[:10]}",
                    sample_id=sample_id,
                    sample_key=sample_key,
                    spectrum_type=candidate.spectrum_type,
                    role=role,
                    file_name=local_file.name,
                    file_ext=local_file.suffix.lower(),
                    relative_path=relative_path,
                    remote_path=str(remote_file_path),
                    local_path=str(local_file),
                    file_size=int(local_file.stat().st_size),
                    sha256=None,
                    modified_at=datetime.fromtimestamp(local_file.stat().st_mtime),
                    copied_at=copied_at,
                    is_primary_input=is_primary_input,
                )
            )

        if candidate.spectrum_type == "gpc":
            if gpc_primary_arw is None:
                logger.warning("GPC 样本目录未找到 .arw 主文件: %s", local_sample_path)
                raise ValueError(f"GPC 样本目录未找到 .arw 主文件: {local_sample_path}")
            primary_input_path = str(gpc_primary_arw)
            sample_meta = {
                "input_kind": "folder",
                "remote_sample_dir": str(candidate.remote_path),
                "local_sample_dir": str(local_sample_path),
                "primary_arw_name": gpc_primary_arw.name,
                "primary_arw_path": str(gpc_primary_arw),
                "validation_pdf_name": gpc_validation_pdf.name if gpc_validation_pdf else None,
                "validation_pdf_path": str(gpc_validation_pdf) if gpc_validation_pdf else None,
            }
            self._append_gpc_experiment_json_meta(sample_meta=sample_meta, json_files=gpc_json_candidates)
        elif candidate.spectrum_type == "nmr":
            dir_names = sorted({path.parent.name for path in local_files if path.parent != local_sample_path})
            sample_meta = {
                "input_kind": "folder",
                "remote_sample_dir": str(candidate.remote_path),
                "local_sample_dir": str(local_sample_path),
                "has_fid": any(path.name.lower() == "fid" for path in local_files),
                "has_pdata": any("pdata" in path.parts for path in local_files),
                "experiment_dir_names": dir_names,
            }
        else:
            suffix = Path(primary_input_path).suffix.lower().lstrip(".")
            sample_meta = {
                "input_kind": "file",
                "remote_file_path": str(candidate.remote_path),
                "local_file_path": str(primary_input_path),
                "file_format": suffix,
            }

        analysis_input = {
            "input_type": TYPE_INPUT_KIND[candidate.spectrum_type],
            "input_path": primary_input_path,
        }
        return file_records, analysis_input, sample_meta, total_size

    @staticmethod
    def _append_gpc_experiment_json_meta(sample_meta: dict[str, Any], json_files: list[Path]) -> None:
        """将 GPC 实验参数 JSON 提升到 sample_meta。"""
        if not json_files:
            return
        selected = LabCollectService._pick_gpc_experiment_json(json_files=json_files)
        sample_meta["experiment_json_name"] = selected.name
        sample_meta["experiment_json_path"] = str(selected)
        try:
            content = selected.read_text(encoding="utf-8-sig")
            payload = json.loads(content)
            if isinstance(payload, dict):
                sample_meta["experiment_json_data"] = payload
            else:
                sample_meta["experiment_json_data"] = {"raw": payload}
        except Exception as exc:
            sample_meta["experiment_json_parse_error"] = str(exc)

    @staticmethod
    def _pick_gpc_experiment_json(json_files: list[Path]) -> Path:
        """选择主实验参数 JSON。"""
        keywords = ("param", "params", "parameter", "config", "setting", "experiment", "method")
        sorted_files = sorted(json_files, key=lambda item: item.name.lower())
        preferred = [
            item for item in sorted_files
            if item.parent == sorted_files[0].parent and any(keyword in item.stem.lower() for keyword in keywords)
        ]
        if preferred:
            return preferred[0]
        root_level = [item for item in sorted_files if item.parent == sorted_files[0].parent]
        if root_level:
            return root_level[0]
        return sorted_files[0]

    @staticmethod
    def _detect_file_role(spectrum_type: str, local_file: Path, local_sample_path: Path) -> str:
        """识别样本文件角色。"""
        suffix = local_file.suffix.lower()
        if spectrum_type == "gpc":
            if suffix == ".arw":
                return "primary_spectrum"
            if suffix == ".pdf":
                return "validation_pdf"
            if suffix == ".json":
                return "experiment_json"
            return "other"
        if spectrum_type in {"ir", "raman", "lcms"}:
            if suffix in {".txt", ".csv"}:
                return "primary_spectrum"
            return "other"
        relative_parts = local_file.relative_to(local_sample_path).parts if local_sample_path.is_dir() else ()
        lower_name = local_file.name.lower()
        if lower_name == "fid":
            return "raw_data"
        if "pdata" in relative_parts:
            return "processed_data"
        if suffix in {".acqus", ".proc", ".txt", ".csv", ".json", ".xml"}:
            return "metadata"
        return "other"

    def _scan_candidates(self, spectrum_type: str, dates: list[str]) -> list[CollectCandidate]:
        """扫描指定类型候选样本。"""
        config = ((self._load_config().get("collectors", {}) or {}).get(spectrum_type, {}) or {})
        if not bool(config.get("enabled", False)):
            return []
        remote_root = Path(str(config.get("remote_root") or ""))
        local_root = Path(str(config.get("local_root") or ""))
        share_key = str(config.get("share_key") or spectrum_type)
        sample_mode = str(config.get("sample_mode") or ("directory" if spectrum_type in {"nmr", "gpc"} else "file"))
        patterns = [str(pattern) for pattern in (config.get("patterns", []) or []) if str(pattern).strip()]
        candidates: list[CollectCandidate] = []

        for date_text in dates:
            remote_date_dir = remote_root / date_text
            if not remote_date_dir.exists() or not remote_date_dir.is_dir():
                continue
            if sample_mode == "directory":
                for sample_dir in sorted([item for item in remote_date_dir.iterdir() if item.is_dir()]):
                    if spectrum_type == "gpc" and not any(file_path.suffix.lower() == ".arw" for file_path in sample_dir.iterdir() if file_path.is_file()):
                        continue
                    candidates.append(
                        CollectCandidate(
                            spectrum_type=spectrum_type,
                            source_date=date_text,
                            sample_name=sample_dir.name,
                            remote_path=sample_dir,
                            remote_date_dir=remote_date_dir,
                            sample_mode=sample_mode,
                            local_root=local_root,
                            share_key=share_key,
                            patterns=patterns,
                        )
                    )
            else:
                if not patterns:
                    patterns = ["*.txt", "*.csv"]
                for sample_file in sorted([item for item in remote_date_dir.iterdir() if item.is_file()]):
                    if not any(fnmatch.fnmatch(sample_file.name.lower(), pattern.lower()) for pattern in patterns):
                        continue
                    candidates.append(
                        CollectCandidate(
                            spectrum_type=spectrum_type,
                            source_date=date_text,
                            sample_name=sample_file.name,
                            remote_path=sample_file,
                            remote_date_dir=remote_date_dir,
                            sample_mode=sample_mode,
                            local_root=local_root,
                            share_key=share_key,
                            patterns=patterns,
                        )
                    )
        return candidates

    @staticmethod
    def _build_date_list(date_from: str, date_to: str) -> list[str]:
        """构建日期范围列表。"""
        start = datetime.strptime(date_from, "%Y-%m-%d").date()
        end = datetime.strptime(date_to, "%Y-%m-%d").date()
        if start > end:
            logger.warning("date_from 不能大于 date_to: %s > %s", date_from, date_to)
            raise ValueError("date_from 不能大于 date_to")
        items: list[str] = []
        current = start
        while current <= end:
            items.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        return items

    @staticmethod
    def _normalize_sample_name(sample_name: str) -> str:
        """标准化样品名。"""
        lowered = str(sample_name or "").strip().lower()
        normalized = re.sub(r"[^0-9a-zA-Z]+", "_", lowered)
        return normalized.strip("_")

    @staticmethod
    def _build_sample_key(candidate: CollectCandidate) -> str:
        """构建样本唯一键。

        Args:
            candidate: 待处理的候选样本。

        Returns:
            样本唯一键。
        """
        return f"{candidate.spectrum_type}:{candidate.source_date}:{candidate.sample_name}"

    @staticmethod
    def _save_run_progress(
        run_record: LabCollectRunRecord,
        imported: int,
        updated: int,
        skipped: int,
        failed: int,
        processed: int,
        total_work: int,
        type_stats: dict[str, dict[str, int]],
        errors: list[LabCollectRunError],
    ) -> None:
        """保存采集批次进度。

        Args:
            run_record: 当前采集批次记录。
            imported: 已新增导入数量。
            updated: 已覆盖更新数量。
            skipped: 已跳过数量。
            failed: 已失败数量。
            processed: 已处理数量。
            total_work: 总处理数量。
            type_stats: 分类型统计。
            errors: 失败项列表。
        """
        run_record.summary.imported = imported
        run_record.summary.updated = updated
        run_record.summary.skipped = skipped
        run_record.summary.failed = failed
        run_record.summary.progress = int(processed / max(total_work, 1) * 100)
        run_record.summary.type_stats = type_stats
        run_record.errors = errors
        run_record.updated_at = datetime.now()
        LabCollectRunRepository.save(run_record)

    @staticmethod
    def _normalize_types(spectrum_types: list[str] | None) -> list[str]:
        """归一化谱图类型列表。"""
        allowed = {"nmr", "gpc", "ir", "raman", "lcms"}
        if not spectrum_types:
            return ["nmr", "gpc", "ir", "raman", "lcms"]
        items = []
        for item in spectrum_types:
            normalized = str(item or "").strip().lower()
            if normalized in allowed and normalized not in items:
                items.append(normalized)
        if not items:
            logger.warning("未提供有效的 spectrum_types: %s", spectrum_types)
            raise ValueError("未提供有效的 spectrum_types")
        return items

    def _load_config(self) -> dict[str, Any]:
        """读取 YAML 配置。"""
        if not self.config_path.exists():
            return {"collectors": {}}
        content = self.config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}
        return data if isinstance(data, dict) else {"collectors": {}}


lab_collect_service = LabCollectService()
