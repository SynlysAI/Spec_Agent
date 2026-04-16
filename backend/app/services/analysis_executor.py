"""同步分析执行器。"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import torch

from app.core.config import settings
from app.infra.mongo import get_files_collection
from app.modules.gpc.workflow import run_gpc_analysis
from app.modules.ir_raman.agent import run_ir_raman_analysis_from_file
from app.modules.nmr.service import (
    build_analysis_report,
    build_peak_detection_result,
    build_summary_rows,
    run_integration_analysis,
)
from app.modules.nmr.workflow import _compute_nmr_qa_metrics
from app.schemas.tasks import TaskArtifactItem
from app.services.lcms_service import lcms_service


def _to_basic(value: Any) -> Any:
    """将复杂对象转换为可序列化基础类型。

    Args:
        value: 任意输入对象。

    Returns:
        可安全写入 MongoDB 或 JSON 的基础类型对象。
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_basic(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_basic(v) for v in value]

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    if hasattr(value, "tolist"):
        try:
            data = value.tolist()
            if isinstance(data, list) and len(data) > 2000:
                return data[:2000]
            return _to_basic(data)
        except Exception:
            pass

    if hasattr(value, "to_dict"):
        try:
            return _to_basic(value.to_dict())
        except Exception:
            pass

    if callable(value):
        return str(value)

    return str(value)


def _sanitize_gpc_structured_data(structured_data: dict[str, Any]) -> dict[str, Any]:
    """清洗 GPC 结构化数据。

    Args:
        structured_data: 原始结构化数据。

    Returns:
        清洗后的结构化数据。
    """
    analysis_results = structured_data.get("analysis_results", [])
    safe_results: list[dict[str, Any]] = []
    for row in analysis_results if isinstance(analysis_results, list) else []:
        if not isinstance(row, dict):
            continue
        safe_row = {
            "curve_file": row.get("curve_file"),
            "actual_curve_name": row.get("actual_curve_name"),
            "simple_name": row.get("simple_name"),
            "output_dir": row.get("output_dir"),
            "molecular_parameters": _to_basic(row.get("molecular_parameters", {})),
            "pdf_data": _to_basic(row.get("pdf_data", {})),
            "errors": _to_basic(row.get("errors", [])),
        }
        roi = row.get("roi_result", {})
        if isinstance(roi, dict):
            safe_row["roi_result"] = {
                "curve_name": roi.get("curve_name"),
                "roi_start": _to_basic(roi.get("roi_start")),
                "roi_end": _to_basic(roi.get("roi_end")),
                "solvent_start": _to_basic(roi.get("solvent_start")),
                "solvent_end": _to_basic(roi.get("solvent_end")),
                "mw_start": _to_basic(roi.get("mw_start")),
                "mw_end": _to_basic(roi.get("mw_end")),
            }
        safe_results.append(_to_basic(safe_row))
    return {"analysis_results": safe_results, "llm_insights": _to_basic(structured_data.get("llm_insights", []))}


def _sanitize_nmr_structured_data(structured_data: dict[str, Any]) -> dict[str, Any]:
    """清洗 NMR 结构化数据。

    Args:
        structured_data: 原始结构化数据。

    Returns:
        清洗后的结构化数据。
    """
    nmr_results = structured_data.get("nmr_results", [])
    safe_results: list[dict[str, Any]] = []
    for row in nmr_results if isinstance(nmr_results, list) else []:
        if not isinstance(row, dict):
            continue
        safe_row = {
            "sample_name": row.get("sample_name"),
            "integration_results": _to_basic(row.get("integration_results", {})),
            "normalized_results": _to_basic(row.get("normalized_results", {})),
            "integration_regions": _to_basic(row.get("integration_regions", [])),
            "metadata": _to_basic(row.get("metadata", {})),
        }
        safe_results.append(safe_row)
    return {"nmr_results": safe_results, "summary_rows": _to_basic(structured_data.get("summary_rows", []))}


def _sanitize_ir_raman_structured_data(structured_data: dict[str, Any]) -> dict[str, Any]:
    """清洗 IR/Raman 结构化数据。

    Args:
        structured_data: 原始结构化数据。

    Returns:
        清洗后的结构化数据。
    """
    return {
        "spectype": _to_basic(structured_data.get("spectype")),
        "mode": _to_basic(structured_data.get("mode")),
        "x0": _to_basic(structured_data.get("x0")),
        "x1": _to_basic(structured_data.get("x1")),
        "raw_output": _to_basic(structured_data.get("raw_output")),
    }


def _sanitize_lcms_structured_data(structured_data: dict[str, Any]) -> dict[str, Any]:
    """清洗 LCMS 结构化数据。

    Args:
        structured_data: 原始结构化数据。

    Returns:
        清洗后的结构化数据。
    """
    return {
        "predicted_mass": _to_basic(structured_data.get("predicted_mass")),
        "raw_output": _to_basic(structured_data.get("raw_output")),
    }


def _resolve_input_path(input_data: dict[str, Any]) -> str:
    """解析任务输入路径。

    Args:
        input_data: 任务输入对象。

    Returns:
        可在服务端访问的本地路径。
    """
    input_type = input_data.get("input_type")
    if input_type in {"file_path", "folder_path"}:
        path = input_data.get("input_path")
        if not path:
            raise ValueError("input_path 不能为空")
        return str(path)

    if input_type == "file_id":
        file_id = input_data.get("file_id")
        if not file_id:
            raise ValueError("file_id 不能为空")
        file_doc = get_files_collection().find_one({"file_id": file_id}, {"_id": 0})
        if not file_doc:
            raise ValueError("file_id 不存在")
        storage_path = str(file_doc.get("storage_path", "")).replace("\\", "/")
        return str(settings.project_root / storage_path)

    raise ValueError(f"不支持的 input_type: {input_type}")


def _pick_internal_standard_idx(
    integration_regions: list[Any],
    prefer: list[str] | None,
) -> int | None:
    """按策略自动选择内标峰索引。

    Args:
        integration_regions: 峰检测得到的积分区间列表。
        prefer: 内标选择优先级列表。

    Returns:
        命中的内标峰索引；若无区间则返回 None。
    """
    if not integration_regions:
        return None
    order = prefer or ["solvent", "tms"]
    name_list: list[str] = []
    for region in integration_regions:
        if isinstance(region, (tuple, list)) and len(region) >= 1:
            name_list.append(str(region[0]).lower())
        else:
            name_list.append("")

    for policy in order:
        if policy == "solvent":
            for index, name in enumerate(name_list):
                if "solvent" in name or "溶剂" in name:
                    return index
        if policy == "tms":
            for index, name in enumerate(name_list):
                if "tms" in name:
                    return index
    return 0


def _detect_artifact_type(file_path: Path) -> str:
    """根据文件后缀识别产物类型。

    Args:
        file_path: 产物文件路径。

    Returns:
        产物类型字符串。
    """
    suffix = file_path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".svg"}:
        return "image"
    if suffix in {".txt", ".md", ".json", ".csv"}:
        return "text"
    if suffix in {".pdf"}:
        return "pdf"
    return "other"


def list_output_artifacts(output_dir: Path) -> list[TaskArtifactItem]:
    """枚举输出目录中的产物文件。

    Args:
        output_dir: 输出目录。

    Returns:
        产物列表。
    """
    if not output_dir.exists() or not output_dir.is_dir():
        return []

    items: list[TaskArtifactItem] = []
    for file_path in sorted(output_dir.rglob("*")):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(settings.outputs_root).as_posix()
        items.append(
            TaskArtifactItem(
                name=file_path.name,
                relative_path=relative_path,
                file_type=_detect_artifact_type(file_path),
                url=f"/static/outputs/{relative_path}",
            )
        )
    return items


def _execute_gpc(output_dir: Path, input_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """执行 GPC 实际分析。

    Args:
        output_dir: 输出目录。
        input_data: 任务输入对象。
        params: GPC 分析参数。

    Returns:
        统一结果对象。
    """
    input_path = _resolve_input_path(input_data)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_file_name = str(params.get("source_file_name") or "").strip() or None
    if not source_file_name and input_data.get("input_type") == "file_id":
        file_id = str(input_data.get("file_id") or "").strip()
        if file_id:
            file_doc = get_files_collection().find_one({"file_id": file_id}, {"_id": 0, "file_name": 1})
            source_file_name = str((file_doc or {}).get("file_name") or "").strip() or None

    result = run_gpc_analysis(
        input_path=input_path,
        detect_mode=params.get("detect_mode", "auto"),
        manual_interval=params.get("manual_interval"),
        three_color_arw_paths=tuple(params["three_color_arw_paths"]) if params.get("three_color_arw_paths") else None,
        calibration_file_path=params.get("calibration_file_path"),
        comparison_report_pdf_path=params.get("comparison_report_pdf_path"),
        source_file_name=source_file_name,
        enable_llm=False,
        output_dir=str(output_dir),
    )
    text_report = str(result.get("text_report", ""))
    if text_report:
        (output_dir / "gpc_report.txt").write_text(text_report, encoding="utf-8")

    return {
        "structured_data": _sanitize_gpc_structured_data(result.get("structured_data", {})),
        "text_report": text_report,
        "metadata": _to_basic(
            {
                **(result.get("metadata") or {}),
                "spectrum_type": "gpc",
                "input_path": input_path,
            }
        ),
    }


def _prepare_nmr_input_path(output_dir: Path, input_path: str) -> str:
    """将 NMR 输入路径标准化为可分析的目录路径。

    Args:
        output_dir: 当前执行输出目录。
        input_path: 原始输入路径。

    Returns:
        可供 NMR 分析函数读取的目录路径。
    """
    source_path = Path(input_path)
    if source_path.is_dir():
        return str(source_path)
    if source_path.is_file() and source_path.suffix.lower() == ".zip":
        extract_root = output_dir / "inputs" / "nmr_zip_extract"
        extract_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source_path, "r") as zip_ref:
            zip_ref.extractall(extract_root)
        children = [item for item in extract_root.iterdir() if item.is_dir()]
        if len(children) == 1:
            return str(children[0])
        return str(extract_root)
    raise ValueError("NMR 输入必须是 Bruker 目录路径或 zip 压缩包路径")


def _execute_nmr(output_dir: Path, input_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """执行 NMR 实际分析。

    Args:
        output_dir: 输出目录。
        input_data: 任务输入对象。
        params: NMR 分析参数。

    Returns:
        统一结果对象。
    """
    input_path = _resolve_input_path(input_data)
    output_dir.mkdir(parents=True, exist_ok=True)
    nmr_folder_path = _prepare_nmr_input_path(output_dir=output_dir, input_path=input_path)

    detection_range_mode = "全谱" if params.get("detection_range_mode", "full") == "full" else "自定义范围"
    peak_detection_params = {
        "threshold": params.get("threshold", 0.01),
        "min_distance": params.get("min_distance", 0.3),
        "min_prominence": params.get("min_prominence", 0.01),
        "width_multiplier": params.get("width_multiplier", 1.0),
        "baseline_degree": params.get("baseline_degree", 3),
        "smooth_window": params.get("smooth_window", 5),
        "detection_range_mode": detection_range_mode,
        "detection_range_min": params.get("detection_range_min"),
        "detection_range_max": params.get("detection_range_max"),
        "ppm_offset": params.get("ppm_offset", 0.0),
        "enable_multiplet": bool(params.get("enable_multiplet", True)),
        "max_coupling_hz": float(
            params.get("max_coupling_hz", 40.0 if str(params.get("nucleus", "1H")).upper() == "13C" else 20.0)
        ),
    }
    if str(params.get("nucleus", "1H")).upper() == "13C":
        peak_detection_params.update(
            {"threshold": 0.05, "min_distance": 1.0, "min_prominence": 0.03, "smooth_window": 11}
        )

    peak_results = build_peak_detection_result(
        folder_path=nmr_folder_path,
        integration_mode="自动模式",
        peak_detection_params=peak_detection_params,
        integration_regions_config=None,
        uploaded_data=None,
        experiment_idx=0,
    )
    standard_idx = _pick_internal_standard_idx(
        integration_regions=peak_results.get("integration_regions", []),
        prefer=params.get("internal_standard_prefer"),
    )
    integration_method = params.get("integration_method", "voigt")
    integration_method_label = "Voigt拟合峰形积分（推荐）" if integration_method == "voigt" else "梯形积分（快速、默认）"
    nmr_results = run_integration_analysis(
        peak_results=peak_results,
        internal_standard_idx=standard_idx,
        integration_method_label=integration_method_label,
        output_dir=str(output_dir),
    )
    summary_rows = build_summary_rows(nmr_results)
    text_report = build_analysis_report(
        nmr_results=nmr_results,
        integration_mode="自动模式",
        peak_detection_params=peak_detection_params,
        integration_method=integration_method_label,
        ppm_offset=float(params.get("ppm_offset", 0.0) or 0.0),
    )
    if text_report:
        (output_dir / "nmr_report.md").write_text(text_report, encoding="utf-8")

    qa_metrics: dict[str, Any] = {}
    try:
        qa_metrics = _compute_nmr_qa_metrics(
            input_path=nmr_folder_path,
            structured_data={"nmr_results": nmr_results, "summary_rows": summary_rows},
            baseline_degree=int(params.get("baseline_degree", 3) or 3),
        )
    except Exception:
        qa_metrics = {}

    return {
        "structured_data": _sanitize_nmr_structured_data({"nmr_results": nmr_results, "summary_rows": summary_rows}),
        "text_report": text_report,
        "metadata": _to_basic(
            {
                "spectrum_type": "nmr",
                "input_path": nmr_folder_path,
                "internal_standard_idx": standard_idx,
                "qa_metrics": qa_metrics,
            }
        ),
    }


def _execute_ir_raman(output_dir: Path, input_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """执行 IR/Raman 实际分析。

    Args:
        output_dir: 输出目录。
        input_data: 任务输入对象。
        params: IR/Raman 分析参数。

    Returns:
        统一结果对象。
    """
    input_path = _resolve_input_path(input_data)
    if not Path(input_path).is_file():
        raise ValueError("IR/Raman 输入必须是谱图文件路径")

    spectype = str(params.get("spectype") or "ir").lower()
    mode = str(params.get("mode") or "greedy_decode")
    k = int(params.get("k") or 3)
    x0 = float(params.get("x0") or 400.0)
    x1 = float(params.get("x1") or 4000.0)
    transmittance = bool(params.get("transmittance") or False)
    device_name = str(params.get("device") or "auto").lower()

    device = None
    if device_name in {"cpu", "cuda"}:
        if device_name == "cuda" and not torch.cuda.is_available():
            device = torch.device("cpu")
        else:
            device = torch.device(device_name)

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{Path(input_path).stem}_{spectype}_report.md"
    result = run_ir_raman_analysis_from_file(
        spectrum_file=input_path,
        spectype=spectype,
        mode=mode,
        k=k,
        x0=x0,
        x1=x1,
        transmittance=transmittance,
        device=device,
        report_path=str(report_path),
    )

    errors = result.get("errors") or []
    if errors:
        raise ValueError("; ".join([str(item) for item in errors]))

    return {
        "structured_data": _sanitize_ir_raman_structured_data(result.get("structured_data", {})),
        "text_report": str(result.get("text_report", "")),
        "metadata": _to_basic(
            {
                **(result.get("metadata") or {}),
                "spectrum_type": spectype,
                "mode": mode,
                "input_path": input_path,
            }
        ),
    }


def _execute_lcms(output_dir: Path, input_data: dict[str, Any], _params: dict[str, Any]) -> dict[str, Any]:
    """执行 LCMS 实际分析。

    Args:
        output_dir: 输出目录。
        input_data: 任务输入对象。
        _params: LCMS 参数。

    Returns:
        统一结果对象。
    """
    input_path = _resolve_input_path(input_data)
    input_file = Path(input_path)
    if not input_file.is_file():
        raise ValueError("LCMS 输入必须是文件路径")

    output_dir.mkdir(parents=True, exist_ok=True)
    infer_result = lcms_service.infer_mass(input_path)
    predicted_mass = infer_result.get("predicted_mass") if isinstance(infer_result, dict) else None
    if predicted_mass is None and isinstance(infer_result, dict):
        predicted_mass = infer_result.get("mass")
    if predicted_mass is None and isinstance(infer_result, dict):
        predicted_mass = infer_result.get("molecular_weight")
    if predicted_mass is None:
        raise ValueError("LCMS 返回中未找到分子量字段")

    try:
        normalized_mass: float | str = float(predicted_mass)
    except (TypeError, ValueError):
        normalized_mass = str(predicted_mass)

    text_report = f"LCMS 分析完成。\n\n预测分子量: {normalized_mass}"
    report_path = output_dir / "lcms_report.md"
    report_path.write_text(
        "# LCMS 分析报告\n\n"
        f"- 输入文件: {input_file.name}\n"
        f"- 预测分子量: {normalized_mass}\n",
        encoding="utf-8",
    )

    return {
        "structured_data": _sanitize_lcms_structured_data(
            {"predicted_mass": normalized_mass, "raw_output": infer_result}
        ),
        "text_report": text_report,
        "metadata": _to_basic(
            {
                "spectrum_type": "lcms",
                "input_path": str(input_file),
                "report_path": str(report_path),
            }
        ),
    }


def execute_analysis_sync(
    task_type: str,
    input_data: dict[str, Any],
    params: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """同步执行分析任务。

    Args:
        task_type: 任务类型。
        input_data: 任务输入对象。
        params: 任务参数。
        output_dir: 输出目录。

    Returns:
        包含 structured_data、text_report、metadata、artifacts 的结果对象。
    """
    if task_type == "gpc_analysis":
        result_payload = _execute_gpc(output_dir=output_dir, input_data=input_data, params=params)
    elif task_type == "nmr_analysis":
        result_payload = _execute_nmr(output_dir=output_dir, input_data=input_data, params=params)
    elif task_type in {"ir_analysis", "raman_analysis"}:
        result_payload = _execute_ir_raman(output_dir=output_dir, input_data=input_data, params=params)
    elif task_type == "lcms_analysis":
        result_payload = _execute_lcms(output_dir=output_dir, input_data=input_data, _params=params)
    else:
        raise ValueError(f"不支持的任务类型: {task_type}")

    result_payload["artifacts"] = [item.model_dump(mode="json") for item in list_output_artifacts(output_dir)]
    return result_payload
