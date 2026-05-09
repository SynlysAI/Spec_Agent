"""
红外 / 拉曼谱图 Agent：封装 ``analysis.raman.main.main``，
输出结构化结果与简要文字报告，供一键脚本调用。

说明：模型权重位于 ``backend/resources/raman/checkpoints/``，首次调用需确保文件存在。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import torch
import yaml

from app.core.logging import get_logger
from app.modules.ir_raman.schemas import SpectrumAgentResult

logger = get_logger("spec_agent.modules.ir_raman.agent")

# 延迟导入重型依赖，避免未使用 IR/Raman 时拖慢启动
def _run_main(
    spectrum: Union[np.ndarray, List[float]],
    x0: float,
    x1: float,
    *,
    device: Optional[torch.device] = None,
    spectype: str = "raman",
    mode: str = "greedy_decode",
    k: int = 3,
    transmittance: bool = False,
) -> Any:
    from analysis.raman.main import main as raman_main

    spec = np.asarray(spectrum, dtype=np.float64).ravel()
    dev = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return raman_main(
        spec,
        x0=x0,
        x1=x1,
        device=dev,
        spectype=spectype,
        mode=mode,
        k=k,
        transmittance=transmittance,
    )


def _format_text_report(
    spectype: str,
    mode: str,
    raw: Any,
    *,
    source_file: Optional[str] = None,
    x0: Optional[float] = None,
    x1: Optional[float] = None,
) -> str:
    lines = [f"# {spectype.upper()} 谱图智能分析报告", ""]
    lines.append("## 任务信息")
    lines.append("")
    lines.append(f"- 光谱类型: {spectype}")
    lines.append(f"- 分析模式: {mode}")
    if source_file:
        lines.append(f"- 输入文件: {source_file}")
    if x0 is not None and x1 is not None:
        lines.append(f"- 分析范围: x0={x0}, x1={x1}")
    lines.append("")

    if mode == "function_groups":
        lines.append("## 官能团识别结果")
        lines.append("")
        if isinstance(raw, list) and raw:
            lines.append(f"检测到 {len(raw)} 个官能团：")
            lines.append("")
            lines.append("| 序号 | 官能团 (SMARTS) |")
            lines.append("| --- | --- |")
            for i, fg in enumerate(raw, start=1):
                lines.append(f"| {i} | `{fg}` |")
        else:
            lines.append("未检测到官能团。")
    elif mode == "greedy_decode":
        lines.append("## 结构预测结果")
        lines.append("")
        if isinstance(raw, list) and raw:
            lines.append(f"- Top1 SMILES: `{raw[0]}`")
        else:
            lines.append("- 未找到有效分子式。")
    elif isinstance(raw, dict) and "structure" in raw:
        structures = raw.get("structure", [])
        scores = raw.get("score", [])
        lines.append("## Top-K 结构预测")
        lines.append("")
        if structures:
            lines.append("| 排名 | 分子式 (SMILES) | 置信度 |")
            lines.append("| --- | --- | --- |")
            for i, s in enumerate(structures, start=1):
                sc = scores[i - 1] if isinstance(scores, list) and (i - 1) < len(scores) else None
                sc_text = f"{float(sc):.4f}" if sc is not None else "-"
                lines.append(f"| {i} | `{s}` | {sc_text} |")
        else:
            lines.append("未找到有效分子式。")
    else:
        lines.append("## 原始输出")
        lines.append("")
        lines.append("```")
        lines.append(str(raw)[:2000])
        lines.append("```")

    if isinstance(raw, dict) and "spectrum" in raw and mode == "retrieval":
        spectra = raw.get("spectrum", [])
        lines.append("")
        lines.append("## 检索谱图信息")
        lines.append("")
        lines.append(f"- 召回谱图数量: {len(spectra) if isinstance(spectra, list) else 0}")

    return "\n".join(lines)


def _parse_spectrum_file(file_path: Union[str, Path]) -> tuple[np.ndarray, np.ndarray]:
    """解析本地谱图文件，返回 (x_values, y_values)。"""
    p = Path(file_path)
    if not p.exists():
        logger.error("谱图文件不存在: %s", p)
        raise FileNotFoundError(f"谱图文件不存在: {p}")
    if p.is_dir():
        logger.warning("输入路径是目录，不是文件: %s", p)
        raise ValueError(f"输入路径是目录，不是文件: {p}")

    content = None
    for encoding in ("utf-16", "utf-8-sig", "utf-8", "gbk"):
        try:
            content = p.read_text(encoding=encoding)
            break
        except UnicodeError:
            continue
    if content is None:
        logger.warning("无法解析文件编码，请使用 UTF-16/UTF-8/GBK: %s", p)
        raise ValueError("无法解析文件编码，请使用 UTF-16/UTF-8/GBK。")

    rows: List[List[float]] = []
    for line in content.splitlines():
        parts = line.strip().replace(",", " ").split()
        if len(parts) < 2:
            continue
        try:
            rows.append([float(parts[0]), float(parts[1])])
        except ValueError:
            continue

    if not rows:
        logger.warning("未解析到有效谱图数据，请确保文件至少有两列数值: %s", p)
        raise ValueError("未解析到有效谱图数据，请确保文件至少有两列数值。")

    arr = np.asarray(rows, dtype=np.float64)
    if arr.shape[1] < 2:
        logger.warning("谱图文件列数不足，至少需要两列（x, y）: %s", p)
        raise ValueError("谱图文件列数不足，至少需要两列（x, y）。")

    return arr[:, 0], arr[:, 1]


def _norm_smiles(value: Any) -> str:
    if value is None:
        return ""
    return "".join(str(value).strip().split()).lower()


def _resolve_label_candidates(spectrum_file: Union[str, Path], spectype: str) -> list[Path]:
    p = Path(spectrum_file)
    stem = p.stem
    candidates = [
        p.with_suffix(".label.json"),
        p.with_suffix(".label.yaml"),
        p.with_suffix(".label.yml"),
        p.parent / f"{stem}.label.json",
        p.parent / f"{stem}.label.yaml",
        p.parent / f"{stem}.label.yml",
    ]
    # 默认集中标签目录（可选）
    default_root = Path("E:/spectrum_files/acceptance/labels")
    candidates.extend(
        [
            default_root / spectype / f"{stem}.label.json",
            default_root / spectype / f"{stem}.label.yaml",
            default_root / spectype / f"{stem}.label.yml",
            default_root / f"{stem}.label.json",
            default_root / f"{stem}.label.yaml",
            default_root / f"{stem}.label.yml",
        ]
    )
    uniq = []
    seen = set()
    for c in candidates:
        key = str(c).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return uniq


def _load_label(spectrum_file: Union[str, Path], spectype: str) -> Optional[dict[str, Any]]:
    for p in _resolve_label_candidates(spectrum_file, spectype):
        if not p.exists() or not p.is_file():
            continue
        try:
            content = p.read_text(encoding="utf-8-sig")
            if p.suffix.lower() == ".json":
                obj = json.loads(content)
            elif p.suffix.lower() in {".yaml", ".yml"}:
                obj = yaml.safe_load(content)
            else:
                continue
            if isinstance(obj, dict):
                obj["_label_file"] = str(p)
                return obj
        except Exception:
            continue
    return None


def _extract_pred_groups_and_smiles(raw_output: Any, mode: str) -> tuple[set[str], list[str]]:
    groups: set[str] = set()
    smiles_topk: list[str] = []
    if isinstance(raw_output, list):
        if mode == "function_groups":
            groups = {str(x).strip() for x in raw_output if str(x).strip()}
        else:
            smiles_topk = [str(x).strip() for x in raw_output if str(x).strip()]
    elif isinstance(raw_output, dict):
        if isinstance(raw_output.get("function_groups"), list):
            groups = {str(x).strip() for x in raw_output.get("function_groups", []) if str(x).strip()}
        if isinstance(raw_output.get("structure"), list):
            smiles_topk = [str(x).strip() for x in raw_output.get("structure", []) if str(x).strip()]
    return groups, smiles_topk


def _build_qa_metrics(
    spectrum_file: Union[str, Path],
    spectype: str,
    mode: str,
    raw_output: Any,
) -> dict[str, Any]:
    qa: dict[str, Any] = {"labeled": False}
    label = _load_label(spectrum_file, spectype)
    if not label:
        return qa
    qa["labeled"] = True
    qa["label_file"] = str(label.get("_label_file", ""))

    pred_groups, pred_topk = _extract_pred_groups_and_smiles(raw_output, mode)
    gt_groups_raw = label.get("function_groups") or label.get("functional_groups")
    gt_groups = {str(x).strip() for x in gt_groups_raw} if isinstance(gt_groups_raw, list) else set()
    gt_smiles = _norm_smiles(label.get("smiles") or label.get("target_smiles"))
    pred_norm = [_norm_smiles(x) for x in pred_topk if _norm_smiles(x)]

    if spectype == "ir" and gt_groups:
        tp = len(pred_groups & gt_groups)
        fp = len(pred_groups - gt_groups)
        fn = len(gt_groups - pred_groups)
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        qa.update({"tp": tp, "fp": fp, "fn": fn, "f1": f1})
    elif spectype == "raman" and gt_smiles:
        qa["top1_hit"] = int(bool(pred_norm) and pred_norm[0] == gt_smiles)
        qa["recall_at_3_hit"] = int(gt_smiles in pred_norm[:3])

    return qa


class IRRamanSpectrumAgent:
    """IR / Raman 谱图推理 Agent（非 LangGraph，直接调用深度学习管线）。"""

    def __init__(self, device: Optional[torch.device] = None) -> None:
        self.device = device

    def run(
        self,
        spectrum: Union[np.ndarray, List[float]],
        x0: float,
        x1: float,
        *,
        spectype: str = "ir",
        mode: str = "greedy_decode",
        k: int = 3,
        transmittance: bool = False,
    ) -> SpectrumAgentResult:
        """对单条谱线（长度与训练一致，通常为 1024 点）做解析。

        Args:
            spectrum: 强度序列。
            x0, x1: 波数 / 波长范围（与 ``analysis.raman.main.main`` 一致）。
            spectype: ``ir`` 或 ``raman``。
            mode: ``greedy_decode`` / ``beam_search`` / ``retrieval`` / ``function_groups``。
            k: beam search / retrieval 候选数。
            transmittance: 仅 IR 有效，透射谱是否转为吸光度。

        Returns:
            :class:`SpectrumAgentResult`。
        """
        errors: List[str] = []
        try:
            raw = _run_main(
                spectrum,
                x0,
                x1,
                device=self.device,
                spectype=spectype,
                mode=mode,
                k=k,
                transmittance=transmittance,
            )
            structured: Dict[str, Any] = {
                "raw_output": raw,
                "spectype": spectype,
                "mode": mode,
                "x0": x0,
                "x1": x1,
            }
            text = _format_text_report(spectype, mode, raw, x0=x0, x1=x1)
            return {
                "structured_data": structured,
                "text_report": text,
                "errors": errors,
                "metadata": {"spectrum_type": spectype, "mode": mode},
            }
        except Exception as e:
            logger.error("IR/Raman 分析异常: %s", e)
            errors.append(str(e))
            return {
                "structured_data": {},
                "text_report": "",
                "errors": errors,
                "metadata": {"spectrum_type": spectype, "mode": mode},
            }


def run_ir_raman_analysis(
    spectrum: Union[np.ndarray, List[float]],
    x0: float,
    x1: float,
    *,
    spectype: str = "ir",
    mode: str = "greedy_decode",
    k: int = 3,
    transmittance: bool = False,
    device: Optional[torch.device] = None,
) -> Dict[str, Any]:
    """函数式封装，返回普通 dict（与 :class:`SpectrumAgentResult` 字段一致）。"""
    agent = IRRamanSpectrumAgent(device=device)
    result = agent.run(
        spectrum,
        x0,
        x1,
        spectype=spectype,
        mode=mode,
        k=k,
        transmittance=transmittance,
    )
    return dict(result)


def run_ir_raman_analysis_from_file(
    spectrum_file: Union[str, Path],
    *,
    spectype: str = "ir",
    mode: str = "greedy_decode",
    k: int = 3,
    x0: float = 400.0,
    x1: float = 4000.0,
    transmittance: bool = False,
    device: Optional[torch.device] = None,
    report_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """一键脚本入口：输入谱图文件与参数，返回结构化结果并可写出 Markdown 报告。"""
    x_values, y_values = _parse_spectrum_file(spectrum_file)
    actual_x0 = round(float(x_values[0]), 1)
    actual_x1 = round(float(x_values[-1]), 1)

    # TODO 这里暂时没有传手动指定的有效波长范围x0和x1，后面算法中默认写死了400~4000的范围
    result = run_ir_raman_analysis(
        y_values,
        actual_x0,
        actual_x1,
        spectype=spectype,
        mode=mode,
        k=k,
        transmittance=transmittance,
        device=device,
    )

    raw_output = result.get("structured_data", {}).get("raw_output")
    result["text_report"] = _format_text_report(
        spectype=spectype,
        mode=mode,
        raw=raw_output,
        source_file=str(spectrum_file),
        x0=actual_x0,
        x1=actual_x1,
    )

    result.setdefault("metadata", {})
    qa_metrics = _build_qa_metrics(
        spectrum_file=spectrum_file,
        spectype=spectype,
        mode=mode,
        raw_output=raw_output,
    )
    result["metadata"].update(
        {
            "source_file": str(spectrum_file),
            "spectrum_points": int(len(y_values)),
            "x_range": [actual_x0, actual_x1],
            "qa_metrics": qa_metrics,
        }
    )

    if report_path:
        rp = Path(report_path)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(result["text_report"], encoding="utf-8")
        result["metadata"]["report_path"] = str(rp)

    return result


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IR/Raman 谱图一键分析脚本")
    parser.add_argument("spectrum_file", type=str, help="输入谱图文件路径（txt/csv）")
    parser.add_argument("--spectype", type=str, default="ir", choices=["ir", "raman"])
    parser.add_argument(
        "--mode",
        type=str,
        default="greedy_decode",
        choices=["greedy_decode", "beam_search", "retrieval", "function_groups"],
    )
    parser.add_argument("--k", type=int, default=3, help="beam_search/retrieval 候选数")
    parser.add_argument("--x0", type=float, default=400.0, help="分析起始 x，默认 400")
    parser.add_argument("--x1", type=float, default=4000.0, help="分析结束 x，默认 4000")
    parser.add_argument("--transmittance", action="store_true", help="IR 透射率转吸光度")
    parser.add_argument("--device", type=str, default=None, choices=["cpu", "cuda"])
    parser.add_argument("--report-path", type=str, default=None, help="报告输出路径（md）")
    return parser


if __name__ == "__main__":
    args = _build_cli_parser().parse_args()
    # 非终端运行时，可注释掉上一行，使用下面的 args 直接赋值：
    # class Args:
    #     spectrum_file = r"E:\spectrum_files\ir\spectrum\ir_00005.txt"
    #     spectype = "ir"
    #     mode = "beam_search"
    #     k = 3
    #     x0 = 400.0
    #     x1 = 4000.0
    #     transmittance = False
    #     device = None
    #     report_path = None
    # args = Args()

    device = None
    if args.device:
        if args.device == "cuda" and not torch.cuda.is_available():
            logger.error("指定了 CUDA，但当前环境不可用。")
            raise RuntimeError("指定了 CUDA，但当前环境不可用。")
        device = torch.device(args.device)

    out = run_ir_raman_analysis_from_file(
        spectrum_file=args.spectrum_file,
        spectype=args.spectype,
        mode=args.mode,
        k=args.k,
        x0=args.x0,
        x1=args.x1,
        transmittance=args.transmittance,
        device=device,
        report_path=args.report_path,
    )

    print(out.get("text_report", ""))
    if out.get("errors"):
        print("Error:", out["errors"])
