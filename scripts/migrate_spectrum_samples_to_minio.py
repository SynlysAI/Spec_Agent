"""将历史样本路径补充为 MinIO 对象路径字段。"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from pymongo import UpdateOne

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.infra.mongo import (  # noqa: E402
    get_spectrum_sample_files_collection,
    get_spectrum_samples_collection,
)
from app.services.object_storage_service import object_storage_service  # noqa: E402


def build_object_fields(raw_path: str | None) -> dict[str, str]:
    """根据历史路径生成对象存储字段。

    Args:
        raw_path: 历史本地路径、对象 URI 或对象 URL。

    Returns:
        可写入 MongoDB 的对象存储字段。
    """
    return object_storage_service.to_record_fields(raw_path)


def update_nested_object_fields(container: dict[str, Any], raw_path: str | None) -> bool:
    """向嵌套字段写入对象存储信息。

    Args:
        container: 待更新的嵌套字典。
        raw_path: 用于推导对象键的路径。

    Returns:
        是否产生字段变更。
    """
    fields = build_object_fields(raw_path)
    if not fields:
        return False

    changed = False
    for key, value in fields.items():
        if container.get(key) != value:
            container[key] = value
            changed = True
    return changed


def build_sample_update(doc: dict[str, Any]) -> dict[str, Any]:
    """构建 spectrum_samples 单条更新内容。

    Args:
        doc: MongoDB 原始样本主档。

    Returns:
        `$set` 更新字段；无变化时返回空字典。
    """
    updates: dict[str, Any] = {}

    analysis_input = dict(doc.get("analysis_input") or {})
    analysis_path = (
        analysis_input.get("object_uri")
        or analysis_input.get("input_path")
        or analysis_input.get("local_input_path")
    )
    if update_nested_object_fields(analysis_input, str(analysis_path or "")):
        updates["analysis_input"] = analysis_input

    storage = dict(doc.get("storage") or {})
    storage_path = storage.get("object_uri") or storage.get("local_sample_path")
    if update_nested_object_fields(storage, str(storage_path or "")):
        updates["storage"] = storage

    sample_meta = dict(doc.get("sample_meta") or {})
    meta_path = (
        sample_meta.get("object_uri")
        or sample_meta.get("local_file_path")
        or sample_meta.get("local_sample_dir")
    )
    if update_nested_object_fields(sample_meta, str(meta_path or "")):
        updates["sample_meta"] = sample_meta

    return updates


def build_file_update(doc: dict[str, Any]) -> dict[str, Any]:
    """构建 spectrum_sample_files 单条更新内容。

    Args:
        doc: MongoDB 原始样本文件清单。

    Returns:
        `$set` 更新字段；无变化时返回空字典。
    """
    raw_path = doc.get("object_uri") or doc.get("local_path") or doc.get("remote_path")
    fields = build_object_fields(str(raw_path or ""))
    return {
        key: value
        for key, value in fields.items()
        if doc.get(key) != value
    }


def migrate_collection(
    collection,
    query: dict[str, Any],
    projection: dict[str, int],
    build_update,
    id_field: str,
    apply: bool,
    limit: int | None,
    batch_size: int = 1000,
) -> tuple[int, int]:
    """迁移指定集合。

    Args:
        collection: MongoDB 集合对象。
        query: 迁移扫描条件。
        projection: Mongo 查询字段投影。
        build_update: 单文档更新构建函数。
        id_field: 日志中使用的记录 ID 字段。
        apply: 是否实际写入数据库。
        limit: 最大扫描记录数。
        batch_size: 批量写入大小。

    Returns:
        二元组：扫描记录数、可更新记录数。
    """
    total = collection.count_documents(query)
    print(
        f"[START] {collection.name}: total={total}, apply={apply}, "
        f"batch_size={batch_size}, limit={limit if limit is not None else 'none'}",
        flush=True,
    )
    cursor = collection.find(query, projection).batch_size(batch_size)
    if limit:
        cursor = cursor.limit(limit)

    scanned = 0
    changed = 0
    operations: list[UpdateOne] = []
    for doc in cursor:
        scanned += 1
        updates = build_update(doc)
        if not updates:
            continue
        changed += 1
        if apply:
            operations.append(UpdateOne({id_field: doc[id_field]}, {"$set": updates}))
            if len(operations) >= batch_size:
                collection.bulk_write(operations, ordered=False)
                print(
                    f"[BATCH] {collection.name}: scanned={scanned}/{total}, "
                    f"changed={changed}, wrote={len(operations)}",
                    flush=True,
                )
                operations.clear()
        elif scanned % batch_size == 0:
            print(
                f"[PROGRESS] {collection.name}: scanned={scanned}/{total}, changed={changed}",
                flush=True,
            )

    if apply and operations:
        collection.bulk_write(operations, ordered=False)
        print(
            f"[FINAL] {collection.name}: scanned={scanned}/{total}, "
            f"changed={changed}, wrote={len(operations)}",
            flush=True,
        )
    print(
        f"[END] {collection.name}: scanned={scanned}/{total}, changed={changed}",
        flush=True,
    )
    return scanned, changed


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="将历史样本路径补充为 MinIO 对象路径字段")
    parser.add_argument("--apply", action="store_true", help="实际写入 MongoDB；默认只 dry-run")
    parser.add_argument("--limit", type=int, default=None, help="限制每个集合扫描的记录数")
    parser.add_argument("--batch-size", type=int, default=5000, help="Mongo 批量写入大小")
    return parser.parse_args()


def _migrate_samples(args: argparse.Namespace) -> tuple[int, int]:
    """迁移 spectrum_samples 集合。"""
    print("[INFO] 开始迁移 spectrum_samples", flush=True)
    return migrate_collection(
        collection=get_spectrum_samples_collection(),
        query={
            "$or": [
                {"analysis_input.object_uri": {"$exists": False}},
                {"storage.object_uri": {"$exists": False}},
                {"sample_meta.object_uri": {"$exists": False}},
            ]
        },
        projection={"_id": 0, "sample_id": 1, "analysis_input": 1, "storage": 1, "sample_meta": 1},
        build_update=build_sample_update,
        id_field="sample_id",
        apply=args.apply,
        limit=args.limit,
        batch_size=args.batch_size,
    )


def _migrate_sample_files(args: argparse.Namespace) -> tuple[int, int]:
    """迁移 spectrum_sample_files 集合。"""
    print("[INFO] 开始迁移 spectrum_sample_files", flush=True)
    return migrate_collection(
        collection=get_spectrum_sample_files_collection(),
        query={"object_uri": {"$exists": False}},
        projection={"_id": 0, "sample_file_id": 1, "local_path": 1, "remote_path": 1, "object_uri": 1},
        build_update=build_file_update,
        id_field="sample_file_id",
        apply=args.apply,
        limit=args.limit,
        batch_size=args.batch_size,
    )


def main() -> None:
    """执行迁移入口，两张表并行处理。"""
    args = parse_args()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_migrate_samples, args): "samples",
            executor.submit(_migrate_sample_files, args): "sample_files",
        }
        results: dict[str, tuple[int, int]] = {}
        for future in as_completed(futures):
            name = futures[future]
            scanned, changed = future.result()
            results[name] = (scanned, changed)

    sample_scanned, sample_changed = results["samples"]
    file_scanned, file_changed = results["sample_files"]
    mode = "已写入" if args.apply else "仅预览"
    print(
        f"{mode}: samples {sample_changed}/{sample_scanned}, "
        f"sample_files {file_changed}/{file_scanned}",
        flush=True,
    )


if __name__ == "__main__":
    main()
