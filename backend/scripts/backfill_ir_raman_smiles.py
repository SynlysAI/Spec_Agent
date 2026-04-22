"""回填 IR/RAMAN 样本的 SMILES 元数据。"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pymongo import UpdateOne

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.infra.mongo import get_spectrum_samples_collection


DEFAULT_SQLITE_DB_PATH = Path(r"E:\spectrum_dbs\spectrum.db")
BULK_BATCH_SIZE = 1000
SPECTRUM_TABLES = {
    "ir": "ir_spectrum",
    "raman": "raman_spectrum",
}


@dataclass
class BackfillStats:
    """记录单个谱图类型的回填统计。"""

    spectrum_type: str
    total: int = 0
    matched: int = 0
    updated: int = 0
    skipped_missing: int = 0
    skipped_empty_smiles: int = 0
    skipped_existing: int = 0


def normalize_lookup_name(sample_name: str) -> str:
    """将样本名转换为谱图库查询名。

    Args:
        sample_name: MongoDB 中的样本名。

    Returns:
        去除后缀并转大写后的样本名。
    """
    return Path(str(sample_name or "").strip()).stem.upper()


def load_smiles_map(sqlite_db_path: Path, table_name: str) -> dict[str, str]:
    """加载指定谱图库表的样本 SMILES 映射。

    Args:
        sqlite_db_path: SQLite 数据库路径。
        table_name: 谱图库表名。

    Returns:
        样本名到 SMILES 的映射。
    """
    with sqlite3.connect(sqlite_db_path) as conn:
        print(f"[load] 开始加载 SQLite 表: {table_name}", flush=True)
        started_at = time.time()
        cursor = conn.execute(f"SELECT sample_name, smiles FROM {table_name}")
        result = {}
        for sample_name, smiles in cursor.fetchall():
            clean_name = str(sample_name or "").strip()
            clean_smiles = str(smiles or "").strip()
            if clean_name and clean_smiles:
                result[clean_name] = clean_smiles
        duration = time.time() - started_at
        print(f"[load] 完成加载 SQLite 表: {table_name}, smiles_count={len(result)}, duration={duration:.2f}s", flush=True)
        return result


def backfill_smiles(sqlite_db_path: Path, dry_run: bool = True, overwrite: bool = False) -> list[BackfillStats]:
    """回填 IR/RAMAN 样本的 sample_meta.smiles。

    Args:
        sqlite_db_path: SQLite 谱图库路径。
        dry_run: 是否只预览不写入。
        overwrite: 是否覆盖已有 sample_meta.smiles。

    Returns:
        各谱图类型的回填统计。
    """
    collection = get_spectrum_samples_collection()
    all_stats = []
    smiles_maps = {
        spectrum_type: load_smiles_map(sqlite_db_path=sqlite_db_path, table_name=table_name)
        for spectrum_type, table_name in SPECTRUM_TABLES.items()
    }

    for spectrum_type in SPECTRUM_TABLES:
        print(f"[{spectrum_type}] 开始扫描 Mongo 样本，dry_run={dry_run}, overwrite={overwrite}", flush=True)
        started_at = time.time()
        stats = BackfillStats(spectrum_type=spectrum_type)
        cursor = collection.find(
            {"spectrum_type": spectrum_type},
            {"_id": 0, "sample_id": 1, "sample_name": 1, "sample_meta": 1},
        )
        operations: list[UpdateOne] = []
        for sample in cursor:
            stats.total += 1
            sample_meta = sample.get("sample_meta") or {}
            if not overwrite and str(sample_meta.get("smiles") or "").strip():
                stats.skipped_existing += 1
                continue

            lookup_name = normalize_lookup_name(sample_name=str(sample.get("sample_name") or ""))
            smiles = smiles_maps[spectrum_type].get(lookup_name)
            if smiles is None:
                stats.skipped_missing += 1
                continue
            if not smiles.strip():
                stats.skipped_empty_smiles += 1
                continue

            stats.matched += 1
            if stats.matched <= 3:
                print(
                    f"[{spectrum_type}] 匹配样例: sample_name={sample.get('sample_name')}, "
                    f"lookup_name={lookup_name}, smiles={smiles}",
                    flush=True,
                )
            operations.append(
                UpdateOne(
                    {"sample_id": str(sample["sample_id"])},
                    {"$set": {"sample_meta.smiles": smiles.strip()}},
                )
            )

            if stats.total % 10000 == 0:
                print(
                    f"[{spectrum_type}] 扫描进度: total={stats.total}, matched={stats.matched}, "
                    f"skipped_existing={stats.skipped_existing}, skipped_missing={stats.skipped_missing}",
                    flush=True,
                )

        print(
            f"[{spectrum_type}] 扫描完成: total={stats.total}, 待写入={len(operations)}, "
            f"skipped_existing={stats.skipped_existing}, skipped_missing={stats.skipped_missing}, "
            f"skipped_empty_smiles={stats.skipped_empty_smiles}",
            flush=True,
        )

        if not dry_run:
            if operations:
                write_started_at = time.time()
                total_batches = (len(operations) + BULK_BATCH_SIZE - 1) // BULK_BATCH_SIZE
                for index in range(0, len(operations), BULK_BATCH_SIZE):
                    batch_no = index // BULK_BATCH_SIZE + 1
                    batch = operations[index:index + BULK_BATCH_SIZE]
                    batch_started_at = time.time()
                    collection.bulk_write(batch, ordered=False)
                    batch_duration = time.time() - batch_started_at
                    print(
                        f"[{spectrum_type}] 写入批次完成: batch={batch_no}/{total_batches}, "
                        f"batch_size={len(batch)}, duration={batch_duration:.2f}s",
                        flush=True,
                    )
                write_duration = time.time() - write_started_at
                print(f"[{spectrum_type}] 写入完成: updated={len(operations)}, duration={write_duration:.2f}s", flush=True)
            else:
                print(f"[{spectrum_type}] 无需写入", flush=True)
        stats.updated = len(operations) if not dry_run else 0
        duration = time.time() - started_at
        print(f"[{spectrum_type}] 处理完成: duration={duration:.2f}s", flush=True)
        all_stats.append(stats)

    return all_stats


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Returns:
        命令行参数对象。
    """
    parser = argparse.ArgumentParser(description="回填 IR/RAMAN 样本 sample_meta.smiles")
    parser.add_argument(
        "--sqlite-db",
        default=str(DEFAULT_SQLITE_DB_PATH),
        help="SQLite 谱图库路径。",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="实际写入 MongoDB；默认只预览。",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已有 sample_meta.smiles；默认跳过已有值。",
    )
    return parser.parse_args()


def main() -> int:
    """执行命令行回填任务。

    Returns:
        进程退出码。
    """
    args = parse_args()
    sqlite_db_path = Path(args.sqlite_db)
    if not sqlite_db_path.exists():
        print(f"SQLite 数据库不存在: {sqlite_db_path}")
        return 1

    stats = backfill_smiles(
        sqlite_db_path=sqlite_db_path,
        dry_run=not args.write,
        overwrite=bool(args.overwrite),
    )
    mode = "写入" if args.write else "预览"
    print(f"IR/RAMAN SMILES 回填{mode}完成")
    for item in stats:
        print(
            {
                "spectrum_type": item.spectrum_type,
                "total": item.total,
                "matched": item.matched,
                "updated": item.updated,
                "skipped_missing": item.skipped_missing,
                "skipped_empty_smiles": item.skipped_empty_smiles,
                "skipped_existing": item.skipped_existing,
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
