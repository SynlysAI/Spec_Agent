"""异步任务执行模块。"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.infra.mongo import get_files_collection, get_results_collection, get_tasks_collection
from app.worker.celery_app import celery_app


def _update_task(task_id: str, **kwargs: Any) -> None:
    """更新任务记录。

    Args:
        task_id: 任务 ID。
        **kwargs: 需要更新的任务字段。
    """
    updates = dict(kwargs)
    updates["updated_at"] = datetime.now()
    get_tasks_collection().update_one({"task_id": task_id}, {"$set": updates})


def _ensure_source_import_path() -> None:
    """确保源项目路径已加入 Python 导入路径。"""
    source_root = str(settings.source_spec_agent_root)
    if source_root not in sys.path:
        sys.path.insert(0, source_root)


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
        return path

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
            for idx, name in enumerate(name_list):
                if "solvent" in name or "溶剂" in name:
                    return idx
        if policy == "tms":
            for idx, name in enumerate(name_list):
                if "tms" in name:
                    return idx
    return 0


def _execute_gpc(task_id: str, input_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """执行 GPC 实际分析。

    Args:
        task_id: 任务 ID。
        input_data: 任务输入对象。
        params: GPC 分析参数。

    Returns:
        统一结果对象，包含 structured_data、text_report、metadata。
    """
    _ensure_source_import_path()
    input_path = _resolve_input_path(input_data)
    output_dir = settings.outputs_root / "tasks" / task_id
    output_dir.mkdir(parents=True, exist_ok=True)

    gpc_module = importlib.import_module("agents.langraph_gpc_agent")
    run_gpc_analysis = getattr(gpc_module, "run_gpc_analysis")
    result = run_gpc_analysis(
        input_path=input_path,
        detect_mode=params.get("detect_mode", "auto"),
        manual_interval=params.get("manual_interval"),
        three_color_arw_paths=tuple(params["three_color_arw_paths"]) if params.get("three_color_arw_paths") else None,
        calibration_file_path=params.get("calibration_file_path"),
        comparison_report_pdf_path=params.get("comparison_report_pdf_path"),
        enable_llm=False,
        output_dir=str(output_dir),
    )
    return {
        "structured_data": result.get("structured_data", {}),
        "text_report": result.get("text_report", ""),
        "metadata": result.get("metadata", {"spectrum_type": "gpc"}),
    }


def _execute_nmr(task_id: str, input_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """执行 NMR 实际分析（单阶段自动内标）。

    Args:
        task_id: 任务 ID。
        input_data: 任务输入对象。
        params: NMR 分析参数。

    Returns:
        统一结果对象，包含 structured_data、text_report、metadata。
    """
    _ensure_source_import_path()
    input_path = _resolve_input_path(input_data)
    output_dir = settings.outputs_root / "tasks" / task_id
    output_dir.mkdir(parents=True, exist_ok=True)

    nmr_service = importlib.import_module("services.nmr_service")
    build_peak_detection_result = getattr(nmr_service, "build_peak_detection_result")
    run_integration_analysis = getattr(nmr_service, "run_integration_analysis")
    build_summary_rows = getattr(nmr_service, "build_summary_rows")
    build_analysis_report = getattr(nmr_service, "build_analysis_report")

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
        "enable_multiplet": True,
    }
    if str(params.get("nucleus", "1H")).upper() == "13C":
        peak_detection_params.update({"threshold": 0.05, "min_distance": 1.0, "min_prominence": 0.03, "smooth_window": 11})

    peak_results = build_peak_detection_result(
        folder_path=input_path,
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
    return {
        "structured_data": {"nmr_results": nmr_results, "summary_rows": summary_rows},
        "text_report": text_report,
        "metadata": {
            "spectrum_type": "nmr",
            "input_path": input_path,
            "internal_standard_idx": standard_idx,
        },
    }


@celery_app.task(name="app.worker.tasks.execute_analysis_task")
def execute_analysis_task(task_id: str) -> None:
    """执行谱图分析任务。

    Args:
        task_id: 任务 ID。
    """
    tasks = get_tasks_collection()
    results = get_results_collection()
    task = tasks.find_one({"task_id": task_id})
    if not task:
        return

    try:
        _update_task(task_id, status="RUNNING", progress=20, message="running")
        task_type = task.get("task_type", "unknown")
        input_data = task.get("input", {})
        params = task.get("params", {})
        _update_task(task_id, progress=45, message="preparing")

        if task_type == "gpc_analysis":
            result_payload = _execute_gpc(task_id=task_id, input_data=input_data, params=params)
        elif task_type == "nmr_analysis":
            result_payload = _execute_nmr(task_id=task_id, input_data=input_data, params=params)
        else:
            raise ValueError(f"不支持的任务类型: {task_type}")

        _update_task(task_id, progress=90, message="saving result")
        result_id = f"r_{task_id}"
        results.update_one(
            {"result_id": result_id},
            {
                "$set": {
                    "result_id": result_id,
                    "task_id": task_id,
                    "task_type": task_type,
                    "structured_data": result_payload.get("structured_data", {}),
                    "text_report": result_payload.get("text_report", ""),
                    "metadata": result_payload.get("metadata", {}),
                    "created_at": datetime.now(),
                }
            },
            upsert=True,
        )
        _update_task(task_id, status="SUCCESS", progress=100, message="finished", result_ref=result_id, error=None)
    except Exception as exc:
        _update_task(task_id, status="FAILED", progress=100, message="failed", error={"detail": str(exc)})
