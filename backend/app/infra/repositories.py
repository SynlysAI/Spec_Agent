"""MongoDB 仓储封装。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.infra.mongo import (
    get_acceptance_runs_collection,
    get_files_collection,
    get_results_collection,
    get_tasks_collection,
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


class AcceptanceRunRepository:
    """验收批次仓储。"""

    @staticmethod
    def collection():
        """返回验收集合。"""
        return get_acceptance_runs_collection()
