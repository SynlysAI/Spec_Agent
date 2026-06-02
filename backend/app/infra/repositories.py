"""MongoDB 仓储封装。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.infra.mongo import (
    get_acceptance_runs_collection,
    get_consistency_runs_collection,
    get_files_collection,
    get_invite_codes_collection,
    get_lab_collect_runs_collection,
    get_molecular_statistics_collection,
    get_results_collection,
    get_spectrum_sample_files_collection,
    get_spectrum_samples_collection,
    get_tasks_collection,
    get_users_collection,
)
from app.schemas.identity_runtime import InviteCodeRecord, UserRecord
from app.schemas.lab_collect import (
    LabCollectRunRecord,
    MolecularStatisticsData,
    SpectrumSampleFileRecord,
    SpectrumSampleRecord,
)
from app.schemas.task_runtime import FileRecord, ResultRecord, TaskErrorInfo, TaskRecord


class TaskRepository:
    """任务仓储。"""

    @staticmethod
    def create(task_record: TaskRecord) -> None:
        """写入任务记录。"""
        get_tasks_collection().insert_one(task_record.model_dump(mode="python"))

    @staticmethod
    def update(task_id: str, **updates: Any) -> None:
        """更新任务记录。"""
        normalized = dict(updates)
        if "error" in normalized and isinstance(normalized["error"], TaskErrorInfo):
            normalized["error"] = normalized["error"].model_dump(mode="python")
        normalized["updated_at"] = datetime.now()
        get_tasks_collection().update_one({"task_id": task_id}, {"$set": normalized})

    @staticmethod
    def find_by_task_id(task_id: str) -> TaskRecord | None:
        """按任务 ID 查询。"""
        doc = get_tasks_collection().find_one({"task_id": task_id}, {"_id": 0})
        return TaskRecord(**doc) if doc else None

    @staticmethod
    def list_paginated(query: dict[str, Any], page: int, page_size: int) -> tuple[int, list[TaskRecord]]:
        """分页查询任务列表。"""
        collection = get_tasks_collection()
        total = collection.count_documents(query)
        cursor = (
            collection.find(query, {"_id": 0})
            .sort([("created_at", -1)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return total, [TaskRecord(**doc) for doc in cursor]

    @staticmethod
    def count(query: dict[str, Any]) -> int:
        """统计任务数量。"""
        return int(get_tasks_collection().count_documents(query))

    @staticmethod
    def find_many(query: dict[str, Any], projection: dict[str, int], limit: int) -> list[dict[str, Any]]:
        """按条件查询任务集合。"""
        cursor = get_tasks_collection().find(query, projection).sort([("created_at", -1)]).limit(limit)
        return list(cursor)


class ResultRepository:
    """结果仓储。"""

    @staticmethod
    def save(result_record: ResultRecord) -> None:
        """保存任务结果。"""
        get_results_collection().update_one(
            {"result_id": result_record.result_id},
            {"$set": result_record.model_dump(mode="python")},
            upsert=True,
        )

    @staticmethod
    def find_by_result_id(result_id: str) -> ResultRecord | None:
        """按结果 ID 查询。"""
        doc = get_results_collection().find_one({"result_id": result_id}, {"_id": 0})
        return ResultRecord(**doc) if doc else None

    @staticmethod
    def find_raw(result_id: str, projection: dict[str, int] | None = None) -> dict[str, Any] | None:
        """按结果 ID 查询原始文档。"""
        fields = dict(projection or {"_id": 0})
        fields.setdefault("_id", 0)
        return get_results_collection().find_one({"result_id": result_id}, fields)


class FileRepository:
    """文件仓储。"""

    @staticmethod
    def save(file_record: FileRecord) -> None:
        """保存文件元数据。"""
        payload = file_record.model_dump(mode="python")
        get_files_collection().update_one(
            {"file_id": file_record.file_id},
            {"$set": payload},
            upsert=True,
        )

    @staticmethod
    def find_by_file_id(file_id: str) -> FileRecord | None:
        """按文件 ID 查询。"""
        doc = get_files_collection().find_one({"file_id": file_id}, {"_id": 0})
        return FileRecord(**doc) if doc else None


class UserRepository:
    """用户仓储。"""

    @staticmethod
    def save(user_record: UserRecord) -> None:
        """保存用户记录。

        Args:
            user_record: 待保存的用户运行态实体。
        """
        get_users_collection().update_one(
            {"user_id": user_record.user_id},
            {"$set": user_record.model_dump(mode="python")},
            upsert=True,
        )

    @staticmethod
    def find_by_username(username: str) -> UserRecord | None:
        """按用户名查询用户记录。

        Args:
            username: 用户名。

        Returns:
            命中的用户记录；若不存在则返回 None。
        """
        doc = get_users_collection().find_one({"username": username}, {"_id": 0})
        return UserRecord(**doc) if doc else None

    @staticmethod
    def find_by_user_id(user_id: str) -> UserRecord | None:
        """按用户 ID 查询用户记录。

        Args:
            user_id: 用户 ID。

        Returns:
            命中的用户记录；若不存在则返回 None。
        """
        doc = get_users_collection().find_one({"user_id": user_id}, {"_id": 0})
        return UserRecord(**doc) if doc else None

    @staticmethod
    def update_last_login(user_id: str) -> None:
        """更新用户最近登录时间。

        Args:
            user_id: 用户 ID。
        """
        get_users_collection().update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "last_login_at": datetime.now(),
                    "updated_at": datetime.now(),
                }
            },
        )

    @staticmethod
    def list_all() -> list[UserRecord]:
        """查询全部用户列表。

        Returns:
            用户记录列表。
        """
        cursor = get_users_collection().find({}, {"_id": 0}).sort([("created_at", -1)])
        return [UserRecord(**doc) for doc in cursor]

    @staticmethod
    def update_status(user_id: str, status: str) -> bool:
        """更新用户状态。

        Args:
            user_id: 用户 ID。
            status: 用户状态。

        Returns:
            是否成功命中并更新用户。
        """
        result = get_users_collection().update_one(
            {"user_id": user_id},
            {"$set": {"status": status, "updated_at": datetime.now()}},
        )
        return result.matched_count > 0


class InviteCodeRepository:
    """邀请码仓储。"""

    @staticmethod
    def save(invite_record: InviteCodeRecord) -> None:
        """保存邀请码记录。

        Args:
            invite_record: 待保存的邀请码运行态实体。
        """
        get_invite_codes_collection().update_one(
            {"invite_id": invite_record.invite_id},
            {"$set": invite_record.model_dump(mode="python")},
            upsert=True,
        )

    @staticmethod
    def find_by_code(invite_code: str) -> InviteCodeRecord | None:
        """按邀请码查询记录。

        Args:
            invite_code: 邀请码。

        Returns:
            命中的邀请码记录；若不存在则返回 None。
        """
        doc = get_invite_codes_collection().find_one({"invite_code": invite_code}, {"_id": 0})
        return InviteCodeRecord(**doc) if doc else None

    @staticmethod
    def consume_available_code(invite_code: str, now: datetime) -> InviteCodeRecord | None:
        """原子消费一个仍可使用的邀请码。

        Args:
            invite_code: 邀请码。
            now: 当前时间。

        Returns:
            消费成功后的邀请码记录；若不可用则返回 None。
        """
        doc = get_invite_codes_collection().find_one_and_update(
            {
                "invite_code": invite_code,
                "status": "active",
                "expires_at": {"$gt": now},
                "$expr": {"$lt": ["$used_count", "$max_uses"]},
            },
            {
                "$inc": {"used_count": 1},
                "$set": {"updated_at": datetime.now()},
            },
            projection={"_id": 0},
            return_document=True,
        )
        return InviteCodeRecord(**doc) if doc else None

    @staticmethod
    def rollback_usage(invite_id: str) -> None:
        """回滚邀请码使用次数。

        Args:
            invite_id: 邀请码 ID。
        """
        get_invite_codes_collection().update_one(
            {"invite_id": invite_id},
            {
                "$inc": {"used_count": -1},
                "$set": {"updated_at": datetime.now()},
            },
        )

    @staticmethod
    def list_all() -> list[InviteCodeRecord]:
        """查询全部邀请码列表。

        Returns:
            邀请码记录列表。
        """
        cursor = get_invite_codes_collection().find({}, {"_id": 0}).sort([("created_at", -1)])
        return [InviteCodeRecord(**doc) for doc in cursor]

    @staticmethod
    def disable(invite_id: str) -> bool:
        """禁用邀请码。

        Args:
            invite_id: 邀请码 ID。

        Returns:
            是否成功命中并更新邀请码。
        """
        result = get_invite_codes_collection().update_one(
            {"invite_id": invite_id},
            {"$set": {"status": "disabled", "updated_at": datetime.now()}},
        )
        return result.matched_count > 0


class AcceptanceRunRepository:
    """验收批次仓储。"""

    @staticmethod
    def collection():
        """返回验收集合。"""
        return get_acceptance_runs_collection()


class ConsistencyRunRepository:
    """一致性评测批次仓储。"""

    @staticmethod
    def collection():
        """返回一致性评测集合。"""
        return get_consistency_runs_collection()


class LabCollectRunRepository:
    """实验室采集批次仓储。"""

    @staticmethod
    def collection():
        """返回采集批次集合。"""
        return get_lab_collect_runs_collection()

    @staticmethod
    def save(run_record: LabCollectRunRecord) -> None:
        """保存采集批次。"""
        payload = run_record.model_dump(mode="python")
        get_lab_collect_runs_collection().update_one(
            {"run_id": run_record.run_id},
            {"$set": payload},
            upsert=True,
        )

    @staticmethod
    def find_by_run_id(run_id: str) -> LabCollectRunRecord | None:
        """按批次 ID 查询采集批次。"""
        doc = get_lab_collect_runs_collection().find_one({"run_id": run_id}, {"_id": 0})
        return LabCollectRunRecord(**doc) if doc else None

    @staticmethod
    def list_recent(limit: int = 20) -> list[LabCollectRunRecord]:
        """查询最近采集批次。"""
        cursor = get_lab_collect_runs_collection().find({}, {"_id": 0}).sort([("created_at", -1)]).limit(limit)
        return [LabCollectRunRecord(**doc) for doc in cursor]


class SpectrumSampleRepository:
    """实验样本主档仓储。"""

    @staticmethod
    def collection():
        """返回样本主档集合。"""
        return get_spectrum_samples_collection()

    @staticmethod
    def save(sample_record: SpectrumSampleRecord) -> None:
        """保存样本主档。"""
        payload = sample_record.model_dump(mode="python")
        get_spectrum_samples_collection().update_one(
            {"sample_key": sample_record.sample_key},
            {"$set": payload},
            upsert=True,
        )

    @staticmethod
    def find_by_sample_key(sample_key: str) -> SpectrumSampleRecord | None:
        """按样本键查询。"""
        doc = get_spectrum_samples_collection().find_one({"sample_key": sample_key}, {"_id": 0})
        return SpectrumSampleRecord(**doc) if doc else None

    @staticmethod
    def find_existing_sample_keys(sample_keys: list[str]) -> set[str]:
        """批量查询已存在的样本键集合。

        Args:
            sample_keys: 待查询的样本键列表。

        Returns:
            数据库中已存在的样本键集合。
        """
        normalized_keys = [str(item).strip() for item in sample_keys if str(item).strip()]
        if not normalized_keys:
            return set()
        cursor = get_spectrum_samples_collection().find(
            {"sample_key": {"$in": normalized_keys}},
            {"sample_key": 1, "_id": 0},
        )
        return {str(doc.get("sample_key")) for doc in cursor if doc.get("sample_key")}

    @staticmethod
    def find_by_sample_id(sample_id: str) -> SpectrumSampleRecord | None:
        """按样本 ID 查询。"""
        doc = get_spectrum_samples_collection().find_one({"sample_id": sample_id}, {"_id": 0})
        return SpectrumSampleRecord(**doc) if doc else None

    @staticmethod
    def list_paginated(query: dict[str, Any], page: int, page_size: int) -> tuple[int, list[SpectrumSampleRecord]]:
        """分页查询样本主档。"""
        collection = get_spectrum_samples_collection()
        total = collection.count_documents(query)
        cursor = (
            collection.find(query, {"_id": 0})
            .sort([("source_date", -1), ("updated_at", -1)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return total, [SpectrumSampleRecord(**doc) for doc in cursor]

    @staticmethod
    def delete_by_sample_id(sample_id: str) -> None:
        """按样本 ID 删除样本主档。"""
        get_spectrum_samples_collection().delete_one({"sample_id": sample_id})


class SpectrumSampleFileRepository:
    """实验样本文件清单仓储。"""

    @staticmethod
    def collection():
        """返回样本文件集合。"""
        return get_spectrum_sample_files_collection()

    @staticmethod
    def replace_for_sample(sample_id: str, file_records: list[SpectrumSampleFileRecord]) -> None:
        """替换指定样本的文件清单。"""
        collection = get_spectrum_sample_files_collection()
        collection.delete_many({"sample_id": sample_id})
        if file_records:
            collection.insert_many([item.model_dump(mode="python") for item in file_records])

    @staticmethod
    def find_by_sample_id(sample_id: str) -> list[SpectrumSampleFileRecord]:
        """按样本 ID 查询文件清单。"""
        cursor = get_spectrum_sample_files_collection().find({"sample_id": sample_id}, {"_id": 0}).sort(
            [("relative_path", 1)]
        )
        return [SpectrumSampleFileRecord(**doc) for doc in cursor]

    @staticmethod
    def delete_by_sample_id(sample_id: str) -> None:
        """按样本 ID 删除文件清单。"""
        get_spectrum_sample_files_collection().delete_many({"sample_id": sample_id})


class MolecularStatisticsRepository:
    """分子统计缓存仓储。"""

    @staticmethod
    def collection():
        """返回分子统计缓存集合。"""
        return get_molecular_statistics_collection()

    @staticmethod
    def save(stats_record: MolecularStatisticsData) -> None:
        """保存分子统计缓存。"""
        payload = stats_record.model_dump(mode="python")
        get_molecular_statistics_collection().update_one(
            {"stats_key": stats_record.stats_key},
            {"$set": payload},
            upsert=True,
        )

    @staticmethod
    def find_by_key(stats_key: str) -> MolecularStatisticsData | None:
        """按缓存键查询分子统计缓存。"""
        doc = get_molecular_statistics_collection().find_one({"stats_key": stats_key}, {"_id": 0})
        return MolecularStatisticsData(**doc) if doc else None
