"""根据 LCMS 原始数据批量生成验收标签文件。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


SOURCE_JSON_PATH = Path(r"E:/spectrum_files/acceptance/labels/test_ESI_data_filtered.json")
SPECTRUM_DIR = Path(r"E:/spectrum_files/acceptance/lcms")
LABEL_DIR = Path(r"E:/spectrum_files/acceptance/labels/lcms")
SPECTRUM_SUFFIX = "-MS峰表"


@dataclass(frozen=True)
class LabelGenerationSummary:
    """表示标签文件批量生成结果。"""

    total_source_records: int
    total_spectrum_files: int
    matched_count: int
    generated_count: int
    skipped_count: int
    unmatched_files: list[str]


def load_source_records(source_json_path: Path) -> list[dict]:
    """读取 LCMS 原始数据列表。

    Args:
        source_json_path: LCMS 原始 JSON 文件路径。

    Returns:
        原始记录列表。
    """
    payload = json.loads(source_json_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise ValueError("LCMS 原始数据必须是列表结构")
    return payload


def normalize_compound_name(file_stem: str) -> str:
    """将 LCMS 样品文件 stem 还原为 compound_name。

    Args:
        file_stem: LCMS 样品文件去后缀后的名称。

    Returns:
        可用于匹配原始 JSON 中 compound_name 的标准名称。
    """
    normalized_name = file_stem.strip()
    if normalized_name.endswith(SPECTRUM_SUFFIX):
        return normalized_name[: -len(SPECTRUM_SUFFIX)].strip()
    return normalized_name


def build_exact_mass_mapping(records: list[dict]) -> dict[str, float]:
    """构建 compound_name 到 exact_mass 的映射。

    Args:
        records: LCMS 原始记录列表。

    Returns:
        `compound_name -> exact_mass` 的映射字典。
    """
    exact_mass_mapping: dict[str, float] = {}
    for record in records:
        compound_name = str(record.get("compound_name") or "").strip()
        exact_mass = record.get("exact_mass")
        if not compound_name:
            continue
        try:
            exact_mass_mapping[compound_name] = float(exact_mass)
        except (TypeError, ValueError):
            continue
    return exact_mass_mapping


def build_label_payload(compound_name: str, exact_mass: float, source_index: int | None) -> dict[str, object]:
    """构建单个 LCMS 标签文件内容。

    Args:
        compound_name: 样品名称。
        exact_mass: 样品真实分子量。
        source_index: 原始 JSON 中的索引字段。

    Returns:
        可直接写入 `.label.json` 的标签内容。
    """
    return {
        "true_mass": exact_mass,
        "compound_name": compound_name,
        "source_index": source_index,
        "note": "由 test_ESI_data_filtered.json 自动生成；验收逻辑会读取 true_mass 作为 LCMS 真实分子量。",
    }


def generate_label_files(
    source_json_path: Path,
    spectrum_dir: Path,
    label_dir: Path,
) -> LabelGenerationSummary:
    """根据原始 JSON 与 LCMS 样品目录生成标签文件。

    Args:
        source_json_path: LCMS 原始 JSON 文件路径。
        spectrum_dir: LCMS 验收谱图目录。
        label_dir: LCMS 标签输出目录。

    Returns:
        批量生成结果摘要。
    """
    records = load_source_records(source_json_path=source_json_path)
    exact_mass_mapping = build_exact_mass_mapping(records=records)
    source_index_mapping = {
        str(record.get("compound_name") or "").strip(): record.get("index")
        for record in records
        if str(record.get("compound_name") or "").strip()
    }
    spectrum_files = sorted(
        [
            *spectrum_dir.glob("*.csv"),
            *spectrum_dir.glob("*.txt"),
        ],
        key=lambda path: path.name.lower(),
    )
    label_dir.mkdir(parents=True, exist_ok=True)

    matched_count = 0
    generated_count = 0
    skipped_count = 0
    unmatched_files: list[str] = []

    for spectrum_file in spectrum_files:
        compound_name = normalize_compound_name(file_stem=spectrum_file.stem)
        exact_mass = exact_mass_mapping.get(compound_name)
        if exact_mass is None:
            skipped_count += 1
            unmatched_files.append(spectrum_file.name)
            continue

        matched_count += 1
        label_path = label_dir / f"{spectrum_file.stem}.label.json"
        label_payload = build_label_payload(
            compound_name=compound_name,
            exact_mass=exact_mass,
            source_index=source_index_mapping.get(compound_name),
        )
        label_path.write_text(
            json.dumps(label_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        generated_count += 1

    return LabelGenerationSummary(
        total_source_records=len(records),
        total_spectrum_files=len(spectrum_files),
        matched_count=matched_count,
        generated_count=generated_count,
        skipped_count=skipped_count,
        unmatched_files=unmatched_files,
    )


def main() -> int:
    """执行 LCMS 标签文件批量生成。"""
    summary = generate_label_files(
        source_json_path=SOURCE_JSON_PATH,
        spectrum_dir=SPECTRUM_DIR,
        label_dir=LABEL_DIR,
    )
    print(f"原始记录数: {summary.total_source_records}")
    print(f"谱图文件数: {summary.total_spectrum_files}")
    print(f"成功匹配数: {summary.matched_count}")
    print(f"生成标签数: {summary.generated_count}")
    print(f"未匹配数: {summary.skipped_count}")
    if summary.unmatched_files:
        print("未匹配文件:")
        for file_name in summary.unmatched_files:
            print(f"- {file_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
