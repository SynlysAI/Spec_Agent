"""NMR 目标峰结构化导出服务。"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable


_TARGET_PATTERNS = {"s", "d", "t", "m"}


def normalize_nucleus_type(nucleus: Any) -> str:
    """将核类型统一为导出所需的 H/C 标记。"""
    nucleus_text = str(nucleus or "").strip().upper().replace("<", "").replace(">", "")
    if nucleus_text == "13C":
        return "C"
    return "H"


def classify_peak_role(region_name: str, peak_type: str | None = None) -> str:
    """根据区域名或峰类型判断峰角色。"""
    source_text = f"{region_name} {peak_type or ''}".lower()
    if "solvent" in source_text or "溶剂" in source_text:
        return "solvent"
    if "impurity" in source_text or "杂质" in source_text:
        return "impurity"
    if "tms" in source_text:
        return "tms"
    return "target"


def simplify_multiplet_pattern(pattern: Any) -> str:
    """将裂分模式压缩为导出所需格式。"""
    pattern_text = str(pattern or "").strip().lower()
    if not pattern_text:
        return ""
    if pattern_text in _TARGET_PATTERNS:
        return pattern_text
    return "m"


def normalize_multiplet_pattern(pattern: Any) -> str:
    """保留原始裂分模式的标准化写法。"""
    return str(pattern or "").strip().lower()


def translate_peak_role(peak_role: str) -> str:
    """将内部峰角色转换为界面展示文案。"""
    mapping = {
        "target": "目标峰",
        "tms": "TMS",
        "impurity": "杂质",
        "solvent": "溶剂",
    }
    return mapping.get(str(peak_role or "").strip().lower(), "目标峰")


def build_peak_annotations(
    integration_regions: Iterable[tuple[Any, ...]] | list[list[Any]],
    multiplet_results: Iterable[Any] | None = None,
) -> list[dict[str, Any]]:
    """构建峰明细结构，供后续导出与结构化结果复用。"""
    multiplet_list = list(multiplet_results or [])
    annotations: list[dict[str, Any]] = []

    for index, region in enumerate(integration_regions or []):
        if not isinstance(region, (list, tuple)) or len(region) < 3:
            continue

        region_name = str(region[0])
        start = float(region[1])
        end = float(region[2])
        if len(region) >= 4:
            peak_position = float(region[3])
        else:
            peak_position = (start + end) / 2.0

        multiplet = multiplet_list[index] if index < len(multiplet_list) else None
        peak_type = getattr(multiplet, "peak_type", None) if multiplet is not None else None
        peak_role = classify_peak_role(region_name, peak_type)
        pattern = getattr(multiplet, "pattern", None) if multiplet is not None else None

        annotations.append({
            "region_name": region_name,
            "peak_role": peak_role,
            "is_target": peak_role == "target",
            "peak_position": peak_position,
            "region_start": min(start, end),
            "region_end": max(start, end),
            "multiplet_pattern": normalize_multiplet_pattern(pattern),
            "peak_type_label": str(peak_type or ""),
        })

    return annotations


def build_peak_details(
    integration_regions: Iterable[tuple[Any, ...]] | list[list[Any]],
    multiplet_results: Iterable[Any] | None = None,
    integration_results: dict[str, Any] | None = None,
    normalized_results: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """构建峰级明细，供前端表格与结构化结果使用。"""
    integration_value_map = integration_results or {}
    normalized_value_map = normalized_results or {}
    annotations = build_peak_annotations(integration_regions, multiplet_results)
    multiplet_list = list(multiplet_results or [])
    details: list[dict[str, Any]] = []

    for index, annotation in enumerate(annotations):
        multiplet = multiplet_list[index] if index < len(multiplet_list) else None
        region_name = str(annotation.get("region_name", ""))
        pattern = normalize_multiplet_pattern(annotation.get("multiplet_pattern", ""))
        j_values = []
        if multiplet is not None:
            j_values = [
                round(float(value), 4)
                for value in getattr(multiplet, "j_values", []) or []
            ]

        details.append({
            "peak_index": index + 1,
            "peak_name": region_name,
            "peak_type": translate_peak_role(str(annotation.get("peak_role", ""))),
            "multiplet_type": pattern,
            "j_values_hz": j_values,
            "peak_position_ppm": round(float(annotation.get("peak_position", 0.0)), 4),
            "ppm_range": [
                round(float(annotation.get("region_start", 0.0)), 4),
                round(float(annotation.get("region_end", 0.0)), 4),
            ],
            "integration_result": integration_value_map.get(region_name),
            "normalized_result": normalized_value_map.get(region_name),
        })

    return details


def build_target_peak_export_row(sample_path: str, nmr_result: dict[str, Any]) -> dict[str, str]:
    """将单个样品结果转换为 Excel 导出行。"""
    metadata = nmr_result.get("metadata", {}) or {}
    spectrum_type = normalize_nucleus_type(metadata.get("nucleus"))
    solvent = str(metadata.get("solvent", "") or "")
    peak_annotations = nmr_result.get("peak_annotations", []) or []

    target_peaks = [item for item in peak_annotations if item.get("is_target")]
    chemical_shifts = ",".join(f"{float(item['peak_position']):.2f}" for item in target_peaks)

    split_types = ""
    if spectrum_type == "H":
        split_types = ",".join(
            simplify_multiplet_pattern(item.get("multiplet_pattern"))
            for item in target_peaks
        )

    all_peak_details = []
    for item in peak_annotations:
        all_peak_details.append({
            "region_name": str(item.get("region_name", "")),
            "peak_role": str(item.get("peak_role", "")),
            "peak_position": round(float(item.get("peak_position", 0.0)), 4),
            "multiplet_pattern": str(item.get("multiplet_pattern", "")),
        })

    return {
        "文件路径": sample_path,
        "文件名": os.path.basename(sample_path.rstrip("\\/")),
        "所属谱类型(H/C)": spectrum_type,
        "溶剂": solvent,
        "目标峰化学位移": chemical_shifts,
        "峰裂分类型": split_types,
        "全部峰信息JSON": json.dumps(all_peak_details, ensure_ascii=False),
    }
