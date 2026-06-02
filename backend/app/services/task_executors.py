"""任务执行器注册表与各谱图执行器。"""

from __future__ import annotations

import json
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings
from app.core.logging import get_logger
from app.infra.repositories import FileRepository
from app.schemas.tasks import TaskArtifactItem, TaskKind
from app.services.lcms_service import lcms_service

logger = get_logger("spec_agent.services.task_executors")


def _to_basic(value: Any) -> Any:
    """将复杂对象转换为可序列化基础类型。"""
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


def detect_artifact_type(file_path: Path) -> str:
    """根据文件后缀识别产物类型。"""
    suffix = file_path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".svg"}:
        return "image"
    if suffix in {".txt", ".md", ".json", ".csv"}:
        return "text"
    if suffix in {".pdf"}:
        return "pdf"
    return "other"


def list_output_artifacts(output_dir: Path) -> list[TaskArtifactItem]:
    """枚举输出目录中的产物文件。"""
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
                file_type=detect_artifact_type(file_path),
                url=f"/static/outputs/{relative_path}",
            )
        )
    return items


def resolve_input_path(input_data: dict[str, Any]) -> str:
    """解析任务输入路径。"""
    input_type = input_data.get("input_type")
    if input_type in {"file_path", "folder_path"}:
        path = input_data.get("input_path")
        if not path:
            logger.warning("input_path 为空, input_type=%s", input_type)
            raise ValueError("input_path 不能为空")
        return str(path)
    if input_type == "file_id":
        file_id = input_data.get("file_id")
        if not file_id:
            logger.warning("file_id 为空")
            raise ValueError("file_id 不能为空")
        file_record = FileRepository.find_by_file_id(file_id)
        if not file_record:
            logger.warning("file_id 不存在: %s", file_id)
            raise ValueError("file_id 不存在")
        storage_path = str(file_record.storage_path).replace("\\", "/")
        return str(settings.project_root / storage_path)
    logger.warning("不支持的 input_type: %s", input_type)
    raise ValueError(f"不支持的 input_type: {input_type}")


def resolve_file_id_to_path(file_id: str) -> str:
    """将 file_id 解析为存储路径。

    函数名称: resolve_file_id_to_path
    参数说明:
    - file_id: 上传文件 ID。
    """
    file_record = FileRepository.find_by_file_id(file_id)
    if not file_record:
        logger.warning("file_id 不存在: %s", file_id)
        raise ValueError(f"file_id 不存在: {file_id}")
    storage_path = str(file_record.storage_path).replace("\\", "/")
    return str(settings.project_root / storage_path)


def sanitize_gpc_structured_data(structured_data: dict[str, Any]) -> dict[str, Any]:
    """清洗 GPC 结构化数据。"""
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


def sanitize_nmr_structured_data(structured_data: dict[str, Any]) -> dict[str, Any]:
    """清洗 NMR 结构化数据。"""
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
            "peak_annotations": _to_basic(row.get("peak_annotations", [])),
            "peak_details": _to_basic(row.get("peak_details", [])),
        }
        safe_results.append(safe_row)
    return {"nmr_results": safe_results, "summary_rows": _to_basic(structured_data.get("summary_rows", []))}


def sanitize_ir_raman_structured_data(structured_data: dict[str, Any]) -> dict[str, Any]:
    """清洗 IR/Raman 结构化数据。"""
    return {
        "spectype": _to_basic(structured_data.get("spectype")),
        "mode": _to_basic(structured_data.get("mode")),
        "x0": _to_basic(structured_data.get("x0")),
        "x1": _to_basic(structured_data.get("x1")),
        "raw_output": _to_basic(structured_data.get("raw_output")),
    }


def sanitize_lcms_structured_data(structured_data: dict[str, Any]) -> dict[str, Any]:
    """清洗 LCMS 结构化数据。"""
    return {
        "predicted_mass": _to_basic(structured_data.get("predicted_mass")),
        "raw_output": _to_basic(structured_data.get("raw_output")),
    }


def resolve_lcms_label_candidates(input_file: Path) -> list[Path]:
    """解析 LCMS 标签候选路径。"""
    stem = input_file.stem
    default_root = settings.spectrum_files_root / "acceptance" / "labels" / "lcms"
    candidates = [
        input_file.with_suffix(".label.json"),
        input_file.with_suffix(".label.yaml"),
        input_file.with_suffix(".label.yml"),
        input_file.parent / f"{stem}.label.json",
        input_file.parent / f"{stem}.label.yaml",
        input_file.parent / f"{stem}.label.yml",
        default_root / f"{stem}.label.json",
        default_root / f"{stem}.label.yaml",
        default_root / f"{stem}.label.yml",
    ]
    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)
    return unique_candidates


def load_lcms_label(input_file: Path) -> dict[str, Any] | None:
    """读取 LCMS 标签文件。"""
    for candidate in resolve_lcms_label_candidates(input_file=input_file):
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            content = candidate.read_text(encoding="utf-8-sig")
            if candidate.suffix.lower() == ".json":
                payload = json.loads(content)
            else:
                payload = yaml.safe_load(content)
            if isinstance(payload, dict):
                payload["_label_file"] = str(candidate)
                return payload
        except Exception:
            continue
    return None


def build_lcms_qa_metrics(input_file: Path, predicted_mass: float | str) -> dict[str, Any]:
    """构建 LCMS 验收指标。"""
    qa_metrics: dict[str, Any] = {"labeled": False}
    label_payload = load_lcms_label(input_file=input_file)
    if not label_payload:
        return qa_metrics

    target_mass = (
        label_payload.get("true_mass")
        or label_payload.get("target_mass")
        or label_payload.get("molecular_weight")
        or label_payload.get("mass")
    )
    try:
        target_mass_value = float(target_mass)
        predicted_mass_value = float(predicted_mass)
    except (TypeError, ValueError):
        return qa_metrics

    if abs(target_mass_value) < 1e-12:
        return qa_metrics

    qa_metrics["labeled"] = True
    qa_metrics["label_file"] = str(label_payload.get("_label_file") or "")
    qa_metrics["target_mass"] = target_mass_value
    qa_metrics["predicted_mass"] = predicted_mass_value
    qa_metrics["mass_abs_error"] = abs(predicted_mass_value - target_mass_value)
    qa_metrics["mass_rd_pct"] = abs((predicted_mass_value - target_mass_value) / target_mass_value) * 100.0
    return qa_metrics


def pick_internal_standard_idx(integration_regions: list[Any], prefer: list[str] | None) -> int | None:
    """按策略自动选择内标峰索引。"""
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


class BaseTaskExecutor(ABC):
    """任务执行器基类。"""

    @abstractmethod
    def execute(self, input_data: dict[str, Any], params: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        """执行单类任务。"""


class GpcTaskExecutor(BaseTaskExecutor):
    """GPC 执行器。"""

    def execute(self, input_data: dict[str, Any], params: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        from app.modules.gpc.workflow import run_gpc_analysis

        input_path = resolve_input_path(input_data)
        output_dir.mkdir(parents=True, exist_ok=True)
        source_file_name = str(params.get("source_file_name") or "").strip() or None
        if not source_file_name and input_data.get("input_type") == "file_id":
            file_id = str(input_data.get("file_id") or "").strip()
            if file_id:
                file_record = FileRepository.find_by_file_id(file_id)
                source_file_name = file_record.file_name if file_record else None

        # 解析可选文件 file_id 为路径
        three_color_file_ids = params.get("three_color_arw_file_ids")
        three_color_paths = None
        if three_color_file_ids and len(three_color_file_ids) == 3:
            three_color_paths = tuple(resolve_file_id_to_path(fid) for fid in three_color_file_ids)

        calibration_file_path = None
        if params.get("calibration_file_id"):
            calibration_file_path = resolve_file_id_to_path(params["calibration_file_id"])

        comparison_report_pdf_path = None
        if params.get("comparison_report_pdf_file_id"):
            comparison_report_pdf_path = resolve_file_id_to_path(params["comparison_report_pdf_file_id"])

        result = run_gpc_analysis(
            input_path=input_path,
            detect_mode=params.get("detect_mode", "auto"),
            manual_interval=params.get("manual_interval"),
            three_color_arw_paths=three_color_paths,
            calibration_file_path=calibration_file_path,
            comparison_report_pdf_path=comparison_report_pdf_path,
            source_file_name=source_file_name,
            enable_llm=False,
            output_dir=str(output_dir),
        )
        text_report = str(result.get("text_report", ""))
        if text_report:
            (output_dir / "gpc_report.txt").write_text(text_report, encoding="utf-8")
        return {
            "structured_data": sanitize_gpc_structured_data(result.get("structured_data", {})),
            "text_report": text_report,
            "metadata": _to_basic({**(result.get("metadata") or {}), "spectrum_type": "gpc", "input_path": input_path}),
        }


class NmrTaskExecutor(BaseTaskExecutor):
    """NMR 执行器。"""

    @staticmethod
    def _prepare_nmr_input_path(output_dir: Path, input_path: str) -> str:
        """将 NMR 输入路径标准化为可分析的目录路径。"""
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
        logger.warning("NMR 输入路径不合法: %s", source_path)
        raise ValueError("NMR 输入必须是 Bruker 目录路径或 zip 压缩包路径")

    def execute(self, input_data: dict[str, Any], params: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        from app.modules.nmr.service import (
            build_analysis_report,
            build_peak_detection_result,
            build_summary_rows,
            run_integration_analysis,
        )
        from app.modules.nmr.workflow import _compute_nmr_qa_metrics

        input_path = resolve_input_path(input_data)
        output_dir.mkdir(parents=True, exist_ok=True)
        nmr_folder_path = self._prepare_nmr_input_path(output_dir=output_dir, input_path=input_path)
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
                {"threshold": 0.05, "min_distance": 1.0, "min_prominence": 0.08, "smooth_window": 11}
            )
        peak_results = build_peak_detection_result(
            folder_path=nmr_folder_path,
            integration_mode="自动模式",
            peak_detection_params=peak_detection_params,
            integration_regions_config=None,
            uploaded_data=None,
            experiment_idx=0,
        )
        standard_idx = pick_internal_standard_idx(
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
            "structured_data": sanitize_nmr_structured_data({"nmr_results": nmr_results, "summary_rows": summary_rows}),
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


class IrRamanTaskExecutor(BaseTaskExecutor):
    """IR/Raman 执行器。"""

    def execute(self, input_data: dict[str, Any], params: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        import torch
        from app.modules.ir_raman.agent import run_ir_raman_analysis_from_file

        input_path = resolve_input_path(input_data)
        if not Path(input_path).is_file():
            logger.warning("IR/Raman 输入必须是谱图文件路径: %s", input_path)
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
            error_msg = "; ".join([str(item) for item in errors])
            logger.error("IR/Raman 分析失败: %s", error_msg)
            raise ValueError(error_msg)
        return {
            "structured_data": sanitize_ir_raman_structured_data(result.get("structured_data", {})),
            "text_report": str(result.get("text_report", "")),
            "metadata": _to_basic(
                {
                    **(result.get("metadata") or {}),
                    "spectrum_type": spectype,
                    "mode": mode,
                    "input_path": input_path,
                    "analysis_x0": x0,
                    "analysis_x1": x1,
                }
            ),
        }


class LcmsTaskExecutor(BaseTaskExecutor):
    """LCMS 执行器。"""

    def execute(self, input_data: dict[str, Any], params: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        del params
        input_path = resolve_input_path(input_data)
        input_file = Path(input_path)
        if not input_file.is_file():
            logger.warning("LCMS 输入必须是文件路径: %s", input_path)
            raise ValueError("LCMS 输入必须是文件路径")
        output_dir.mkdir(parents=True, exist_ok=True)
        infer_result = lcms_service.infer_mass(input_path)
        predicted_mass = infer_result.get("predicted_mass") if isinstance(infer_result, dict) else None
        if predicted_mass is None and isinstance(infer_result, dict):
            predicted_mass = infer_result.get("mass")
        if predicted_mass is None and isinstance(infer_result, dict):
            predicted_mass = infer_result.get("molecular_weight")
        if predicted_mass is None:
            logger.error("LCMS 返回中未找到分子量字段, 原始返回: %s", infer_result)
            raise ValueError("LCMS 返回中未找到分子量字段")
        try:
            normalized_mass: float | str = float(predicted_mass)
        except (TypeError, ValueError):
            normalized_mass = str(predicted_mass)
        qa_metrics = build_lcms_qa_metrics(input_file=input_file, predicted_mass=normalized_mass)
        text_report_lines = [
            "LCMS 分析完成。",
            "",
            f"预测分子量: {normalized_mass}",
        ]
        if qa_metrics.get("labeled"):
            text_report_lines.append(f"实际标注分子量: {qa_metrics.get('target_mass')}")
        text_report = "\n".join(text_report_lines)
        report_path = output_dir / "lcms_report.md"
        report_lines = [
            "# LCMS 分析报告",
            "",
            f"- 输入文件: {input_file.name}",
            f"- 预测分子量: {normalized_mass}",
        ]
        if qa_metrics.get("labeled"):
            report_lines.append(f"- 实际标注分子量: {qa_metrics.get('target_mass')}")
        report_path.write_text(
            "\n".join(report_lines) + "\n",
            encoding="utf-8",
        )
        return {
            "structured_data": sanitize_lcms_structured_data({"predicted_mass": normalized_mass, "raw_output": infer_result}),
            "text_report": text_report,
            "metadata": _to_basic(
                {
                    "spectrum_type": "lcms",
                    "input_path": str(input_file),
                    "report_path": str(report_path),
                    "qa_metrics": qa_metrics,
                }
            ),
        }


class TaskExecutorRegistry:
    """任务执行器注册表。"""

    def __init__(self) -> None:
        self._executors: dict[TaskKind, BaseTaskExecutor] = {
            "gpc_analysis": GpcTaskExecutor(),
            "nmr_analysis": NmrTaskExecutor(),
            "ir_analysis": IrRamanTaskExecutor(),
            "raman_analysis": IrRamanTaskExecutor(),
            "lcms_analysis": LcmsTaskExecutor(),
        }

    def execute(
        self,
        task_type: TaskKind,
        input_data: dict[str, Any],
        params: dict[str, Any],
        output_dir: Path,
    ) -> dict[str, Any]:
        """执行指定任务类型。"""
        executor = self._executors.get(task_type)
        if not executor:
            logger.warning("不支持的任务类型: %s", task_type)
            raise ValueError(f"不支持的任务类型: {task_type}")
        result_payload = executor.execute(input_data=input_data, params=params, output_dir=output_dir)
        result_payload["artifacts"] = [item.model_dump(mode="json") for item in list_output_artifacts(output_dir)]
        return result_payload


task_executor_registry = TaskExecutorRegistry()
