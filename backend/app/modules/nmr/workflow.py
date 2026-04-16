"""
NMR 谱图 LangGraph 工作流：与 Streamlit 共用的 services/nmr_service 编排，
输出结构化数据 + 文字报告，供一键脚本或后端调用。

本模块**仅支持自动峰检测**（Bruker 样品目录 + 自动模式），不包含手动积分区与上传文件路径。

**图结构**

无头（默认，适合脚本）：峰检测时即传入 ``internal_standard_idx``（默认 0）::

    peak_detection ──► integration ──► finalize ──► END

交互式（可选）：峰检测后**暂停**，等待用户选择内标峰索引，再继续::

    peak_detection ──► select_internal_standard ──► integration ──► finalize ──► END

交互式使用 LangGraph 的 ``interrupt`` / ``Command(resume=...)``，需 **checkpointer**
与固定 ``thread_id``，并**复用同一** :class:`NMRPathWorkflow` 实例编译出的图。
"""

from __future__ import annotations

import argparse
import json
import os
import traceback
from typing import Any, Dict, List, Optional

import numpy as np
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from typing_extensions import NotRequired, Required, TypedDict

from app.modules.nmr.service import (
    build_analysis_report,
    build_peak_detection_result,
    build_summary_rows,
    run_integration_analysis,
)
from config import GLOBAL_CONFIG

# 本 Agent 固定为自动模式，与 services 约定一致
_AUTO_INTEGRATION_MODE = "自动模式"
_DEFAULT_INTEGRATION_METHOD = "Voigt拟合峰形积分（推荐）"


def _resolve_output_dir(raw: Optional[str], default_dir: str) -> str:
    """将 ``output_dir`` 规范为可用目录：``None``、空串、仅空白均回退到 ``default_dir``。"""
    if raw is None:
        return default_dir
    s = str(raw).strip()
    return s if s else default_dir


class NMRState(TypedDict, total=False):
    """NMR LangGraph 状态（仅自动峰检测 + Bruker 目录）。"""

    input_path: Required[str]
    """本机 **Bruker 样品数据目录**。"""
    peak_detection_params: Required[Dict[str, Any]]
    internal_standard_idx: NotRequired[int]
    """内标峰在自动检测积分区域列表中的索引。

    - **无头图**：应在首次 ``invoke`` 时传入（默认 ``0``）。
    - **交互图**：由 :meth:`NMRPathWorkflow.node_select_internal_standard` 在
      ``interrupt`` 恢复后写入，首次调用不要传。
    """
    output_dir: NotRequired[Optional[str]]
    """结果输出根目录。可为 ``None``、省略或空字符串，均使用 ``GLOBAL_CONFIG['paths']['nmr_results']``。"""

    errors: NotRequired[List[str]]
    peak_regions_preview: NotRequired[List[List[Any]]]
    """仅用于交互展示的积分区域预览（纯 Python 基础类型，可被 checkpointer 序列化）。"""
    nmr_results: NotRequired[List[Dict[str, Any]]]
    structured_data: NotRequired[Dict[str, Any]]
    text_report: NotRequired[str]


class NMRPathWorkflow:
    """NMR 分析工作流：峰检测 →（可选人机）→ 积分/归一化 → 汇总与报告。

    节点与 ``services/nmr_service`` 对应关系：

    ==================== ================================ ========================================
    图节点名             类方法                           调用的服务函数
    ==================== ================================ ========================================
    ``peak_detection``   :meth:`node_peak_detection`    :func:`build_peak_detection_result`
    ``select_internal_standard`` :meth:`node_select_internal_standard`  ``interrupt`` / 用户 ``resume``
    ``integration``      :meth:`node_integration`       :func:`run_integration_analysis`
    ``finalize``         :meth:`node_finalize`          :func:`build_summary_rows`、
                                                          :func:`build_analysis_report`
    ==================== ================================ ========================================
    """

    def __init__(self, output_dir=None) -> None:
        self.default_output_dir = output_dir or GLOBAL_CONFIG["paths"]["nmr_results"]
        os.makedirs(self.default_output_dir, exist_ok=True)
        # 交互式断点续跑需持久化在同一 checkpointer 上（同一 Workflow 实例）
        self._checkpointer = MemorySaver()

    @staticmethod
    def _to_builtin_value(value: Any) -> Any:
        """将 numpy/pandas 等标量转换为 Python 内建标量，确保可序列化。"""
        # numpy scalar has `item()`
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                pass
        return value

    def _build_regions_preview(self, integration_regions: List[Any]) -> List[List[Any]]:
        """构建可 checkpoint 的积分区域预览（只保留基础类型）。"""
        preview: List[List[Any]] = []
        for region in integration_regions or []:
            if not isinstance(region, (list, tuple)) or len(region) < 3:
                continue
            name = str(region[0])
            start = float(self._to_builtin_value(region[1]))
            end = float(self._to_builtin_value(region[2]))
            if len(region) >= 4:
                peak = float(self._to_builtin_value(region[3]))
                preview.append([name, start, end, peak])
            else:
                preview.append([name, start, end])
        return preview

    def _build_serializable_nmr_results(self, nmr_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将积分结果裁剪为 checkpoint 友好的结构（去除 numpy 数组等不可序列化字段）。"""
        serializable: List[Dict[str, Any]] = []
        for item in nmr_results or []:
            row: Dict[str, Any] = {
                "sample_name": str(item.get("sample_name", "")),
                "integration_results": {},
                "normalized_results": {},
                "integration_regions": self._build_regions_preview(item.get("integration_regions", [])),
                "metadata": item.get("metadata", {}),
            }
            for k, v in (item.get("integration_results") or {}).items():
                row["integration_results"][str(k)] = float(self._to_builtin_value(v))
            for k, v in (item.get("normalized_results") or {}).items():
                row["normalized_results"][str(k)] = float(self._to_builtin_value(v))
            serializable.append(row)
        return serializable

    def node_peak_detection(self, state: NMRState) -> Dict[str, Any]:
        """图节点 ``peak_detection``：自动峰检测并确定积分区域。

        对应服务：:func:`services.nmr_service.build_peak_detection_result`。
        """
        if state.get("errors"):
            return {}
        try:
            peak = build_peak_detection_result(
                state["input_path"],
                _AUTO_INTEGRATION_MODE,
                state["peak_detection_params"],
                integration_regions_config=None,
                uploaded_data=None,
            )
            preview = self._build_regions_preview(peak.get("integration_regions", []))
            return {"peak_regions_preview": preview, "errors": []}
        except Exception as e:
            traceback.print_exc()
            err = state.get("errors") or []
            err.append(str(e))
            return {"errors": err}

    def node_select_internal_standard(self, state: NMRState) -> Dict[str, Any]:
        """图节点 ``select_internal_standard``：暂停并等待用户选择内标峰索引。

        使用 ``interrupt`` 抛出可恢复断点；用户通过 ``invoke(Command(resume=idx), ...)``
        传入非负整数索引（与 ``peak_result['integration_regions']`` 下标一致）。

        ``resume`` 的值会作为 ``interrupt()`` 的返回值赋给 ``internal_standard_idx``。
        """
        if state.get("errors"):
            return {}
        regions = state.get("peak_regions_preview") or []
        n = len(regions)
        payload = {
            "type": "nmr_internal_standard",
            "message": "请选择内标峰对应的积分区域索引（从 0 开始）",
            "sample_name": str(state.get("input_path", "")),
            "region_count": n,
            "integration_regions": regions,
        }
        idx_raw = interrupt(payload)
        try:
            idx = int(idx_raw)
        except (TypeError, ValueError):
            idx = 0
        if n > 0:
            idx = max(0, min(idx, n - 1))
        else:
            idx = 0
        return {"internal_standard_idx": idx}

    def node_integration(self, state: NMRState) -> Dict[str, Any]:
        """图节点 ``integration``：按区域积分、内标归一化并导出谱图。

        对应服务：:func:`services.nmr_service.run_integration_analysis`。
        """
        if state.get("errors"):
            return {}
        try:
            peak = build_peak_detection_result(
                state["input_path"],
                _AUTO_INTEGRATION_MODE,
                state["peak_detection_params"],
                integration_regions_config=None,
                uploaded_data=None,
            )
            out_dir = _resolve_output_dir(state.get("output_dir"), self.default_output_dir)
            nmr_results = run_integration_analysis(
                peak,
                state.get("internal_standard_idx"),
                _DEFAULT_INTEGRATION_METHOD,
                out_dir,
            )
            safe_results = self._build_serializable_nmr_results(nmr_results)
            return {"nmr_results": safe_results}
        except Exception as e:
            traceback.print_exc()
            err = state.get("errors") or []
            err.append(str(e))
            return {"errors": err}

    def node_finalize(self, state: NMRState) -> Dict[str, Any]:
        """图节点 ``finalize``：生成 Markdown 报告与可序列化结构化结果。"""
        if state.get("errors") or not state.get("nmr_results"):
            return {}
        try:
            nmr_results = state["nmr_results"]
            ppm_offset = float(state["peak_detection_params"].get("ppm_offset", 0.0))
            text = build_analysis_report(
                nmr_results,
                _AUTO_INTEGRATION_MODE,
                state["peak_detection_params"],
                _DEFAULT_INTEGRATION_METHOD,
                ppm_offset,
            )
            summary_rows = build_summary_rows(nmr_results)
            structured = {
                "nmr_results": nmr_results,
                "summary_rows": summary_rows,
            }
            return {
                "structured_data": structured,
                "text_report": text,
            }
        except Exception as e:
            traceback.print_exc()
            err = state.get("errors") or []
            err.append(str(e))
            return {"errors": err}

    def build(self, interactive: bool = False):
        """编译 LangGraph。

        Args:
            interactive: 若为 ``True``，在峰检测与积分之间插入 ``select_internal_standard``
                节点（``interrupt``），并挂载 :attr:`_checkpointer`。无头脚本请保持
                ``False``，并在首次 ``invoke`` 时传入 ``internal_standard_idx``。

        Returns:
            可 ``invoke`` 的已编译图。
        """
        workflow = StateGraph(NMRState)
        workflow.add_node("peak_detection", self.node_peak_detection)
        if interactive:
            workflow.add_node("select_internal_standard", self.node_select_internal_standard)
        workflow.add_node("integration", self.node_integration)
        workflow.add_node("finalize", self.node_finalize)
        workflow.set_entry_point("peak_detection")
        if interactive:
            workflow.add_edge("peak_detection", "select_internal_standard")
            workflow.add_edge("select_internal_standard", "integration")
        else:
            workflow.add_edge("peak_detection", "integration")
        workflow.add_edge("integration", "finalize")
        workflow.add_edge("finalize", END)
        if interactive:
            return workflow.compile(checkpointer=self._checkpointer)
        return workflow.compile()


def default_peak_detection_params(nucleus: str = "1H") -> Dict[str, Any]:
    """与 Streamlit 默认一致的峰检测参数（可按需覆盖）。

    Args:
        nucleus: 检测核类型，支持 ``"1H"``（默认）和 ``"13C"``。
            13C 谱 ppm 范围广、噪声大，需要更保守的检测参数。

    Returns:
        峰检测参数字典，可直接传给 :func:`run_nmr_analysis` 的 ``peak_detection_params``。
    """
    _is_13c = nucleus.strip().upper().replace("<", "").replace(">", "") in ("13C",)

    if _is_13c:
        return {
            "threshold": 0.05,
            "min_distance": 1.0,
            "min_prominence": 0.03,
            "width_multiplier": 1.0,
            "baseline_degree": 3,
            "smooth_window": 11,
            "detection_range_mode": "全谱",
            "detection_range_min": None,
            "detection_range_max": None,
            "ppm_offset": 0.0,
            "enable_multiplet": True,
            "max_coupling_hz": 40,
        }
    # 1H 默认参数
    return {
        "threshold": 0.01,
        "min_distance": 0.3,
        "min_prominence": 0.01,
        "width_multiplier": 1.0,
        "baseline_degree": 3,
        "smooth_window": 5,
        "detection_range_mode": "全谱",
        "detection_range_min": None,
        "detection_range_max": None,
        "ppm_offset": 0.0,
        "enable_multiplet": True,
        "max_coupling_hz": 20,
    }


def nmr_thread_config(thread_id: str, recursion_limit: int = 30) -> Dict[str, Any]:
    """交互式图所需的 ``config``：固定 ``thread_id`` 以便断点续跑。"""
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit}


def _load_solvent_ref() -> dict[str, Any]:
    path = str(GLOBAL_CONFIG["resources"]["solvent_impurities"])
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _compute_nmr_qa_metrics(
    input_path: str,
    structured_data: dict[str, Any],
    baseline_degree: int,
) -> dict[str, Any]:
    qa: dict[str, Any] = {"solvent_ppm_errors": []}
    nmr_results = structured_data.get("nmr_results", [])
    if not isinstance(nmr_results, list) or not nmr_results:
        return qa
    row = nmr_results[0] if isinstance(nmr_results[0], dict) else {}
    regions = row.get("integration_regions", []) or []
    metadata = row.get("metadata", {}) or {}

    # 1) 基线 RMSE（无信号区）
    try:
        from analysis.nmr.nmr_analysis import get_nmr_sample_data
        from analysis.nmr.peak_detection import calculate_baseline

        # 使用同一条谱线数据同时构造 y 与 y_hat，避免口径不一致
        data, ppm_scale, _, _ = get_nmr_sample_data(input_path, index=0)
        data_arr = np.asarray(data, dtype=np.float64)
        ppm_arr = np.asarray(ppm_scale, dtype=np.float64)
        baseline = calculate_baseline(data_arr, degree=baseline_degree)
        corrected = data_arr - np.asarray(baseline, dtype=np.float64)

        # 无信号区掩膜：先排除已识别积分区，再剔除强信号区（防止漏检峰污染）
        mask = np.ones_like(corrected, dtype=bool)
        for region in regions:
            if not isinstance(region, (list, tuple)) or len(region) < 3:
                continue
            try:
                s = float(region[1])
                e = float(region[2])
            except (TypeError, ValueError):
                continue
            low = min(s, e) - 0.03
            high = max(s, e) + 0.03
            mask &= ~((ppm_arr >= low) & (ppm_arr <= high))

        # 额外剔除高强度点（可能是未被积分区覆盖的峰）
        abs_signal = np.abs(data_arr)
        hi_thr = np.percentile(abs_signal, 70)
        mask &= abs_signal <= hi_thr

        if int(mask.sum()) < max(100, int(0.02 * len(mask))):
            abs_corr = np.abs(corrected)
            thr = np.percentile(abs_corr, 40)
            mask = abs_corr <= thr

        if np.any(mask):
            residual = corrected[mask]
            rmse_raw = float(np.sqrt(np.mean(np.square(residual))))
            # 归一化到谱线幅值尺度，保证“<0.2”阈值在不同样品间可比
            scale = float(np.percentile(np.abs(data_arr), 95))
            if scale > 1e-12:
                qa["baseline_rmse"] = rmse_raw / scale
            else:
                qa["baseline_rmse"] = rmse_raw
            qa["baseline_rmse_raw"] = rmse_raw
            qa["baseline_scale_p95"] = scale
    except Exception:
        pass

    # 2) 溶剂峰 ppm 误差
    try:
        solvent_ref = _load_solvent_ref()
        solvent = str(metadata.get("solvent", "")).strip().strip("<>")
        nucleus = str(metadata.get("nucleus", "")).strip().strip("<>")
        nuc_dict = solvent_ref.get(nucleus) or solvent_ref.get("1H") or {}
        ref_list = nuc_dict.get(solvent, []) if isinstance(nuc_dict, dict) else []
        solvent_refs = []
        for item in ref_list:
            if not isinstance(item, dict):
                continue
            if str(item.get("type", "")).lower() != "solvent":
                continue
            try:
                solvent_refs.append(float(item["ppm"]))
            except (TypeError, ValueError, KeyError):
                continue

        tms_offset = 0.0
        try:
            tms_offset = float(metadata.get("tms_offset", 0.0) or 0.0)
        except (TypeError, ValueError):
            tms_offset = 0.0

        errors = []
        if solvent_refs:
            for region in regions:
                if not isinstance(region, (list, tuple)) or len(region) < 3:
                    continue
                name = str(region[0]) if len(region) > 0 else ""
                if "solvent" not in name.lower() and "溶剂" not in name:
                    continue
                center = None
                if len(region) >= 4:
                    try:
                        center = float(region[3])
                    except (TypeError, ValueError):
                        center = None
                if center is None:
                    try:
                        center = (float(region[1]) + float(region[2])) / 2.0
                    except (TypeError, ValueError):
                        continue
                center += tms_offset
                errors.append(float(min(abs(center - ref) for ref in solvent_refs)))
        qa["solvent_ppm_errors"] = errors
    except Exception:
        pass

    return qa


def run_nmr_analysis(
    input_path: str,
    *,
    peak_detection_params: Optional[Dict[str, Any]] = None,
    internal_standard_idx: Optional[int] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """一键分析（**无中断**）：Bruker 目录 + 自动峰检测；内标索引由参数一次性指定。

    Args:
        input_path: 本机 Bruker 样品数据目录。
        peak_detection_params: 可选，覆盖 :func:`default_peak_detection_params` 中的项。
        internal_standard_idx: 自动检测出的积分区域中，内标峰索引。
        output_dir: 输出根目录；可为 ``None`` 或省略，则使用 ``GLOBAL_CONFIG['paths']['nmr_results']``。
            传空字符串或仅空白也会回退为上述默认目录。

    Returns:
        与 :class:`SpectrumAgentResult` 对齐：``structured_data``、``text_report``、``errors``、``metadata``。

    若需在峰检测后由用户选择内标，请使用交互式图：``NMRPathWorkflow().build(interactive=True)``
    与 :func:`nmr_thread_config`，见模块顶部的图结构说明。
    """
    params = {**default_peak_detection_params(), **(peak_detection_params or {})}
    state: Dict[str, Any] = {
        "input_path": input_path,
        "peak_detection_params": params,
        "internal_standard_idx": internal_standard_idx,
        "output_dir": output_dir,
        "errors": [],
    }
    app = NMRPathWorkflow(output_dir=output_dir).build(interactive=False)
    final = app.invoke(state, config={"recursion_limit": 20})
    errors = final.get("errors") or []
    structured_data = final.get("structured_data") or {}
    qa_metrics = _compute_nmr_qa_metrics(
        input_path=input_path,
        structured_data=structured_data,
        baseline_degree=int(params.get("baseline_degree", 3) or 3),
    )

    return {
        "structured_data": structured_data,
        "text_report": final.get("text_report") or "",
        "errors": errors,
        "metadata": {
            "spectrum_type": "nmr",
            "input_path": input_path,
            "qa_metrics": qa_metrics,
        },
    }


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NMR 谱图一键分析脚本")
    parser.add_argument("input_path", type=str, help="输入 Bruker 样品目录路径")
    parser.add_argument("--internal-standard-idx", type=int, default=0, help="内标峰索引，默认0")
    parser.add_argument("--output-dir", type=str, default=None, help="结果输出目录，默认使用配置值")
    parser.add_argument("--threshold", type=float, default=0.01)
    parser.add_argument("--min-distance", type=float, default=0.3)
    parser.add_argument("--min-prominence", type=float, default=0.01)
    parser.add_argument("--width-multiplier", type=float, default=1.0)
    parser.add_argument("--baseline-degree", type=int, default=3)
    parser.add_argument("--smooth-window", type=int, default=5)
    parser.add_argument("--detection-range-mode", type=str, default="全谱")
    parser.add_argument("--detection-range-min", type=float, default=None)
    parser.add_argument("--detection-range-max", type=float, default=None)
    parser.add_argument("--ppm-offset", type=float, default=0.0)
    parser.add_argument("--report-path", type=str, default=None, help="Markdown 报告输出路径")
    return parser


if __name__ == "__main__":
    args = _build_cli_parser().parse_args()
    # 非终端运行时，可注释掉上一行，使用下面的 args 直接赋值：
    # class Args:
    #     input_path = r"E:\spectrum_files\nmr\2026-03-11\20250514-23H"
    #     internal_standard_idx = 0
    #     output_dir = None
    #     threshold = 0.01
    #     min_distance = 0.3
    #     min_prominence = 0.01
    #     width_multiplier = 1.0
    #     baseline_degree = 3
    #     smooth_window = 5
    #     detection_range_mode = "全谱"
    #     detection_range_min = None
    #     detection_range_max = None
    #     ppm_offset = 0.0
    #     report_path = None
    #
    # args = Args()

    peak_detection_params = {
        "threshold": args.threshold,
        "min_distance": args.min_distance,
        "min_prominence": args.min_prominence,
        "width_multiplier": args.width_multiplier,
        "baseline_degree": args.baseline_degree,
        "smooth_window": args.smooth_window,
        "detection_range_mode": args.detection_range_mode,
        "detection_range_min": args.detection_range_min,
        "detection_range_max": args.detection_range_max,
        "ppm_offset": args.ppm_offset,
    }

    out = run_nmr_analysis(
        input_path=args.input_path,
        peak_detection_params=peak_detection_params,
        internal_standard_idx=args.internal_standard_idx,
        output_dir=args.output_dir,
    )

    if args.report_path:
        report_dir = os.path.dirname(args.report_path)
        if report_dir:
            os.makedirs(report_dir, exist_ok=True)
        with open(args.report_path, "w", encoding="utf-8") as f:
            f.write(out.get("text_report", ""))
        out.setdefault("metadata", {})
        out["metadata"]["report_path"] = args.report_path

    print(out.get("text_report", ""))
    if out.get("errors"):
        print("Error:", out["errors"])
