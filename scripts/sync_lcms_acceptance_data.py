"""同步 LCMS 验收样品与标注文件。"""

from __future__ import annotations

import json
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path


SOURCE_JSON_PATH = Path(r"E:/spectrum_files/acceptance/labels/test_ESI_data_filtered.json")
SOURCE_SPECTRUM_DIR = Path(r"E:/spectrum_files/lcms/spectrum/2026-05-18")
ACCEPTANCE_SPECTRUM_DIR = Path(r"E:/spectrum_files/acceptance/lcms")
ACCEPTANCE_LABEL_DIR = Path(r"E:/spectrum_files/acceptance/labels/lcms")
SPECTRUM_SUFFIX = "-MS峰表"


@dataclass(frozen=True)
class SyncSummary:
    """表示 LCMS 验收同步结果。"""

    source_total: int
    matched_total: int
    copied_total: int
    label_total: int
    exact_match_total: int
    normalized_match_total: int
    ambiguous_total: int
    unmatched_total: int


def load_source_records(source_json_path: Path) -> list[dict[str, object]]:
    """读取 LCMS 原始样本数据。

    Args:
        source_json_path: 原始 JSON 文件路径。

    Returns:
        原始样本记录列表。
    """
    payload = json.loads(source_json_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise ValueError("LCMS 原始数据必须是列表结构")
    records: list[dict[str, object]] = []
    for item in payload:
        if isinstance(item, dict):
            records.append(item)
    return records


def normalize_text(value: str) -> str:
    """标准化名称，便于做宽松匹配。

    Args:
        value: 原始名称。

    Returns:
        归一化后的名称。
    """
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    replacements = {
        "（": "(",
        "）": ")",
        "，": ",",
        "。": ".",
        "、": ",",
        "－": "-",
        "—": "-",
        "–": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "　": "",
        " ": "",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


def strip_spectrum_suffix(file_stem: str) -> str:
    """去掉 LCMS 样品文件名尾部的谱图标记。

    Args:
        file_stem: 不含扩展名的文件名。

    Returns:
        去掉 `-MS峰表` 标记后的样品名。
    """
    normalized = unicodedata.normalize("NFKC", file_stem).strip()
    for suffix in (SPECTRUM_SUFFIX, SPECTRUM_SUFFIX.lower(), "_MS峰表", "_ms峰表"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)].strip()
    return normalized


def build_compound_index(records: list[dict[str, object]]) -> tuple[dict[str, dict[str, object]], dict[str, list[dict[str, object]]]]:
    """构建样品名索引。

    Args:
        records: 原始样本记录列表。

    Returns:
        精确索引和归一化索引。
    """
    exact_index: dict[str, dict[str, object]] = {}
    normalized_index: dict[str, list[dict[str, object]]] = {}
    for record in records:
        compound_name = str(record.get("compound_name") or "").strip()
        if not compound_name:
            continue
        exact_index[compound_name] = record
        normalized_key = normalize_text(compound_name)
        normalized_index.setdefault(normalized_key, []).append(record)
    return exact_index, normalized_index


def resolve_record(
    sample_name: str,
    exact_index: dict[str, dict[str, object]],
    normalized_index: dict[str, list[dict[str, object]]],
) -> tuple[dict[str, object] | None, str | None]:
    """解析样品名对应的原始记录。

    Args:
        sample_name: 样品名。
        exact_index: 精确索引。
        normalized_index: 归一化索引。

    Returns:
        解析到的原始记录及匹配方式，若未命中则返回 `(None, None)`。
    """
    exact_record = exact_index.get(sample_name)
    if exact_record is not None:
        return exact_record, "exact"

    normalized_key = normalize_text(sample_name)
    candidates = normalized_index.get(normalized_key, [])
    if len(candidates) == 1:
        return candidates[0], "normalized"
    return None, None


def build_label_payload(record: dict[str, object], sample_name: str, source_file_name: str) -> dict[str, object]:
    """构建 LCMS 标签文件内容。

    Args:
        record: 原始样本记录。
        sample_name: 样品名。
        source_file_name: 源谱图文件名。

    Returns:
        可写入 `.label.json` 的标签内容。
    """
    return {
        "true_mass": record.get("exact_mass"),
        "compound_name": record.get("compound_name"),
        "sample_name": sample_name,
        "source_file_name": source_file_name,
        "source_index": record.get("index"),
        "note": "由 test_ESI_data_filtered.json 自动生成；验收逻辑读取 true_mass 作为 LCMS 真实分子量。",
    }


def sync_lcms_acceptance_data(
    source_json_path: Path,
    source_spectrum_dir: Path,
    acceptance_spectrum_dir: Path,
    acceptance_label_dir: Path,
) -> SyncSummary:
    """同步 LCMS 验收目录与标注文件。

    Args:
        source_json_path: 原始 JSON 文件路径。
        source_spectrum_dir: 源 LCMS 谱图目录。
        acceptance_spectrum_dir: 验收谱图目录。
        acceptance_label_dir: 验收标签目录。

    Returns:
        同步结果摘要。
    """
    records = load_source_records(source_json_path=source_json_path)
    exact_index, normalized_index = build_compound_index(records=records)
    source_files = sorted(
        [*source_spectrum_dir.glob("*.csv"), *source_spectrum_dir.glob("*.txt")],
        key=lambda path: path.name.lower(),
    )

    matched_files: list[Path] = []
    matched_records: list[dict[str, object]] = []
    exact_match_total = 0
    normalized_match_total = 0
    ambiguous_total = 0
    unmatched_total = 0

    for source_file in source_files:
        sample_name = strip_spectrum_suffix(source_file.stem)
        record, match_mode = resolve_record(
            sample_name=sample_name,
            exact_index=exact_index,
            normalized_index=normalized_index,
        )
        if record is None:
            ambiguous_candidates = normalized_index.get(normalize_text(sample_name), [])
            if len(ambiguous_candidates) > 1:
                ambiguous_total += 1
            else:
                unmatched_total += 1
            continue

        matched_files.append(source_file)
        matched_records.append(record)
        if match_mode == "exact":
            exact_match_total += 1
        else:
            normalized_match_total += 1

    acceptance_spectrum_dir.mkdir(parents=True, exist_ok=True)
    acceptance_label_dir.mkdir(parents=True, exist_ok=True)

    for file_path in acceptance_spectrum_dir.iterdir():
        if file_path.is_file():
            file_path.unlink()

    for file_path in acceptance_label_dir.glob("*.label.json"):
        file_path.unlink()

    for source_file, record in zip(matched_files, matched_records, strict=True):
        shutil.copy2(source_file, acceptance_spectrum_dir / source_file.name)
        label_path = acceptance_label_dir / f"{source_file.stem}.label.json"
        label_path.write_text(
            json.dumps(
                build_label_payload(
                    record=record,
                    sample_name=strip_spectrum_suffix(source_file.stem),
                    source_file_name=source_file.name,
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return SyncSummary(
        source_total=len(source_files),
        matched_total=len(matched_files),
        copied_total=len(matched_files),
        label_total=len(list(acceptance_label_dir.glob("*.label.json"))),
        exact_match_total=exact_match_total,
        normalized_match_total=normalized_match_total,
        ambiguous_total=ambiguous_total,
        unmatched_total=unmatched_total,
    )


def main() -> int:
    """执行 LCMS 验收数据同步。"""
    summary = sync_lcms_acceptance_data(
        source_json_path=SOURCE_JSON_PATH,
        source_spectrum_dir=SOURCE_SPECTRUM_DIR,
        acceptance_spectrum_dir=ACCEPTANCE_SPECTRUM_DIR,
        acceptance_label_dir=ACCEPTANCE_LABEL_DIR,
    )
    print(f"源样本数: {summary.source_total}")
    print(f"匹配样本数: {summary.matched_total}")
    print(f"已复制样本数: {summary.copied_total}")
    print(f"已生成标签数: {summary.label_total}")
    print(f"精确匹配数: {summary.exact_match_total}")
    print(f"归一化匹配数: {summary.normalized_match_total}")
    print(f"歧义样本数: {summary.ambiguous_total}")
    print(f"未匹配样本数: {summary.unmatched_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
