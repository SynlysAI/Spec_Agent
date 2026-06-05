import argparse
import glob
import os
import re
import traceback
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict, NotRequired, Required

from analysis.gpc.tools.gpc_curve_roi_processor import GPCCurveROIProcessor
from analysis.gpc.tools.gpc_data_name_parser import GPCDataNameParser
from analysis.gpc.tools.gpc_validation import GPCValidator
from analysis.gpc.utils.gpc_analyzer import GPCAnalyzer
from analysis.gpc.utils.gpc_plotter import GPCDataPlotter
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("spec_agent.modules.gpc.workflow")


def _parse_manual_interval(value: Optional[str]) -> Optional[List[float]]:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    parts = [x.strip() for x in text.split(",")]
    if len(parts) != 2:
        logger.warning("manual_interval 格式错误: %s", value)
        raise ValueError("manual_interval 格式应为 'start,end'，例如 7.2,8.9")
    start = float(parts[0])
    end = float(parts[1])
    if start >= end:
        logger.warning("manual_interval 区间无效: start=%s, end=%s", start, end)
        raise ValueError("manual_interval 必须满足 start < end")
    return [start, end]


def _strip_upload_file_prefix(file_name: str) -> str:
    """剥离上传文件自动前缀，恢复原始谱图文件名。"""
    if not file_name:
        return file_name
    pattern = r"^f_\d{8}_\d{6}_[0-9a-fA-F]{6}_(.+)$"
    matched = re.match(pattern, file_name)
    if matched and matched.group(1):
        return matched.group(1)
    return file_name


class GPCState(TypedDict, total=False):
    """LangGraph 状态：初始仅含 ``input_path`` / ``detect_mode`` / ``manual_interval``，
    其余由各节点写入；可选显式三色与校准文件。

    可选覆盖（均不填则按样品名在配置目录中匹配三色与校准）：
    - ``three_color_arw_paths``：三条三色 ``.arw`` 的完整路径，顺序为 (绿, 红, 白)。
    - ``calibration_file_path``：校准表 ``.json``（直接读）或 ``.pdf``（解析后拟合）。
    - ``comparison_report_pdf_path``：对比用 GPC 测试报告 PDF；若提供则 ``node_pdf_data_extraction``
      直接解析该文件，不再在 ``gpc_comparison_pdf_dir`` 下按样品名搜索。
    """

    # 初始 invoke 必填
    input_path: Required[str]
    detect_mode: Required[str]
    manual_interval: Required[Optional[List[float]]]

    # 中间变量：扫描到的所有待处理文件列表
    file_paths: NotRequired[List[str]]

    # 统一的分析结果变量，存储所有节点的结果
    analysis_results: NotRequired[List[Dict[str, Any]]]

    errors: NotRequired[List[str]]

    # 可选：(green_arw, red_arw, white_arw) 三个文件的完整路径
    three_color_arw_paths: NotRequired[Tuple[str, str, str]]
    # 可选：校准 JSON 或 PDF 路径
    calibration_file_path: NotRequired[str]
    # 可选：对比实验 GPC 报告 PDF（与 Agent 结果对照）；提供则不再按名称在配置目录中匹配
    comparison_report_pdf_path: NotRequired[str]
    # 可选：上传原始文件名（用于三色曲线匹配）
    source_file_name: NotRequired[str]


class GPCPathWorkflow:
    def __init__(self, output_dir=None):
        self.output_dir = output_dir or str(settings.outputs_root / "gpc_results")
        self.three_color_dir = str(settings.gpc_three_color_dir)
        # 实例变量，避免重复创建
        self.name_parser = GPCDataNameParser()
        self.roi_processor = GPCCurveROIProcessor()
        # 对比报告 PDF：默认在 settings.gpc_comparison_pdf_dir 下按样品名匹配；见 GPCValidator
        self.validator = GPCValidator(
            search_dir=str(settings.gpc_comparison_pdf_dir),
        )

    # --- 节点 1: 路径扫描与验证 ---
    @staticmethod
    def node_scan_path(state: GPCState) -> Dict[str, Any]:
        path = state["input_path"]
        found_files = []
        errors = []

        if not os.path.exists(path):
            return {"errors": [f"路径不存在: {path}"]}

        if os.path.isfile(path):
            if path.lower().endswith(".arw"):
                found_files.append(path)
            else:
                errors.append(f"文件格式错误（仅支持.arw）: {path}")
        elif os.path.isdir(path):
            # 递归查找所有 .arw 文件
            found_files = glob.glob(os.path.join(path, "**", "*.arw"), recursive=True)
            if not found_files:
                errors.append(f"目录中未找到 .arw 文件: {path}")

        logger.info("扫描完成: 找到 %d 个待处理文件", len(found_files))
        return {"file_paths": found_files, "errors": errors}

    # --- 节点 2: 读取数据 ---
    def node_read_data(self, state: GPCState) -> Dict[str, Any]:
        if state.get("errors") or not state["file_paths"]:
            return {}

        origin_data_list = []
        logger.info("开始读取 %d 个谱图文件...", len(state['file_paths']))

        for file_path in state["file_paths"]:
            try:
                # 读取 ARW 文件数据
                actual_curve = pd.read_csv(file_path, sep="\t", header=None, names=["retention_time", "intensity"])
                actual_curve_name = os.path.basename(file_path)
                source_file_name = str(state.get("source_file_name") or "").strip()
                candidate_name = source_file_name if source_file_name and len(state["file_paths"]) == 1 else actual_curve_name
                display_curve_name = _strip_upload_file_prefix(candidate_name)
                simple_name = os.path.splitext(display_curve_name)[0]
                # 准备输出目录
                output_dir = os.path.join(self.output_dir, simple_name)
                os.makedirs(output_dir, exist_ok=True)

                origin_data = {
                    "curve_file": file_path,
                    "actual_curve_name": display_curve_name,
                    "stored_curve_name": actual_curve_name,
                    "source_file_name": source_file_name or None,
                    "simple_name": simple_name,
                    "actual_curve": actual_curve,  # 直接存储原始 DataFrame
                    "output_dir": output_dir
                }
                origin_data_list.append(origin_data)
                logger.info("成功读取: %s", os.path.basename(file_path))
            except Exception as e:
                logger.error("读取文件异常: %s", str(e))

        return {"analysis_results": origin_data_list}

    # --- 节点 3: ROI 识别 ---
    def node_roi_identification(self, state: GPCState) -> Dict[str, Any]:
        if state.get("errors") or not state.get("analysis_results"):
            return {}

        analysis_results = state.get("analysis_results", [])
        logger.info("开始 ROI 识别...")
        
        for data in analysis_results:
            try:
                actual_curve_name = data["actual_curve_name"]
                simple_name = data["simple_name"]

                explicit_three = state.get("three_color_arw_paths")
                cal_file = (state.get("calibration_file_path") or "").strip() or None

                if explicit_three:
                    three_tuple = tuple(explicit_three)
                    if len(three_tuple) != 3:
                        logger.warning("three_color_arw_paths 长度错误: %d", len(three_tuple))
                        raise ValueError("three_color_arw_paths 必须为绿、红、白三条 .arw 路径")
                    roi_result = self.roi_processor.calculate_roi(
                        "",
                        "",
                        three_arw_paths=three_tuple,
                        calibration_file_path=cal_file,
                        return_details=True,
                        visualize=False,
                        output_dir=None,
                    )
                    full_calib_name = roi_result["full_calib_name"]
                    calibration_func = roi_result.get("calibration_func")
                    if calibration_func is None:
                        calibration_func = self.roi_processor.calibration.get_calibration_curve(
                            full_calib_name
                        )
                    roi_start, roi_end = roi_result['roi_start'], roi_result['roi_end']
                else:
                    effective_three_dir = self.three_color_dir
                    candidate_names: list[str] = []
                    for name in [
                        str(data.get("source_file_name") or "").strip(),
                        actual_curve_name,
                        _strip_upload_file_prefix(actual_curve_name),
                        _strip_upload_file_prefix(str(data.get("stored_curve_name") or "")),
                    ]:
                        if name and name not in candidate_names:
                            candidate_names.append(name)

                    three_color_curve_name = None
                    for candidate_name in candidate_names:
                        three_color_curve_name = self.name_parser.match_three_color_curve(
                            candidate_name,
                            effective_three_dir,
                        )
                        if three_color_curve_name:
                            break

                    # 获取校准曲线函数
                    if cal_file:
                        calibration_func = self.roi_processor.calibration.get_calibration_curve_from_file(cal_file)
                        full_calib_name = os.path.splitext(os.path.basename(cal_file))[0]
                    else:
                        # 尝试查找匹配的校准曲线
                        try:
                            from config import GLOBAL_CONFIG
                            json_dir = GLOBAL_CONFIG["data_storage"]["calibration_curves"]
                            json_files = [f for f in os.listdir(json_dir) if f.endswith(".json")]
                            matched_curve = None
                            for json_file in json_files:
                                if actual_curve_name in json_file:
                                    matched_curve = os.path.splitext(json_file)[0]
                                    break
                            if matched_curve:
                                calibration_func = self.roi_processor.calibration.get_calibration_curve(matched_curve)
                                full_calib_name = matched_curve
                            else:
                                calibration_func = lambda t: -0.2 * t + 9.0
                                full_calib_name = "默认校准曲线"
                        except Exception:
                            calibration_func = lambda t: -0.2 * t + 9.0
                            full_calib_name = "默认校准曲线"

                    if three_color_curve_name:
                        # 有三色曲线：完整ROI检测
                        roi_result = self.roi_processor.calculate_roi(
                            three_color_curve_name,
                            effective_three_dir,
                            calibration_file_path=cal_file,
                            return_details=True,
                            visualize=False,
                            output_dir=None,
                        )
                        roi_start, roi_end = roi_result['roi_start'], roi_result['roi_end']
                    else:
                        # 无三色曲线：只按分子量阈值过滤
                        logger.info("无三色曲线，仅按分子量阈值过滤，候选名: %s", candidate_names)
                        mw_start, mw_end = self.roi_processor.find_mw_roi_region(
                            data["actual_curve"], calibration_func
                        )
                        roi_start, roi_end = mw_start, mw_end
                        roi_result = {
                            "roi_start": roi_start,
                            "roi_end": roi_end,
                            "mw_start": mw_start,
                            "mw_end": mw_end,
                        }

                # 提取 ROI 范围内的数据
                actual_curve = data["actual_curve"]
                roi_data = actual_curve[(actual_curve['retention_time'] >= roi_start) &
                                      (actual_curve['retention_time'] <= roi_end)].copy()

                data["roi_result"] = roi_result
                data["roi_data"] = roi_data
                data["calibration_func"] = calibration_func
                logger.info("ROI 识别完成: %s", simple_name)
            except Exception as e:
                logger.error("ROI 识别异常: %s", str(e))

        return {"analysis_results": analysis_results}

    # --- 节点 4: 峰值检测与分子量计算 ---
    def node_peak_detection_and_calculate_mw(self, state: GPCState) -> Dict[str, Any]:
        if state.get("errors") or not state.get("analysis_results"):
            return {}

        analysis_results = state.get("analysis_results", [])
        logger.info("开始峰值检测与分子量计算...")
        # 从 state 中获取 UI 传来的参数
        detect_mode = state.get("detect_mode", "auto")
        manual_interval = state.get("manual_interval", None)
        
        for data in analysis_results:
            try:
                simple_name = data["simple_name"]
                roi_data = data["roi_data"]
                calibration_func = data["calibration_func"]
                
                # 准备数据
                time_data = roi_data["retention_time"].values
                signal_data = roi_data["intensity"].values

                # 峰值检测
                gpc_analyzer = GPCAnalyzer(time_data, signal_data, calibration_func)
                peaks_info = gpc_analyzer.detect_peaks_bounds(height_ratio=0.1)
                # 计算单峰分子量
                molecular_params = gpc_analyzer.calculate_molecular_weights(
                    peak_index=0,
                    detect_mode=detect_mode,
                    manual_interval=manual_interval
                )
                # 直接在原字典中添加新的字段
                data["peaks_info"] = peaks_info
                data["molecular_info"] = [molecular_params]
                data["molecular_parameters"] = {
                    "mn": molecular_params.get("Mn", 0),
                    "mw": molecular_params.get("Mw", 0),
                    "mz": molecular_params.get("Mz", 0),
                    "pdi": molecular_params.get("PDI", 0)
                }
                logger.info("峰值检测与分子量计算完成: %s", simple_name)
            except Exception as e:
                logger.error("峰值检测与分子量计算异常: %s", str(e))

        return {"analysis_results": analysis_results}

    # --- 节点 5: 绘图 ---
    def node_plot_results(self, state: GPCState) -> Dict[str, Any]:
        if state.get("errors") or not state.get("analysis_results"):
            return {}

        analysis_results = state.get("analysis_results", [])
        detect_mode = state.get("detect_mode", "auto")
        manual_interval = state.get("manual_interval", None)
        logger.info("开始绘制分析结果图...")
        
        for data in analysis_results:
            try:
                actual_curve = data["actual_curve"]
                actual_curve_name = data["actual_curve_name"]
                simple_name = data["simple_name"]
                output_dir = data["output_dir"]
                molecular_info = data["molecular_info"]
                peaks_info = data["peaks_info"]
                calibration_func = data["calibration_func"]
                roi_data = data["roi_data"]
                # 准备数据
                time_data = roi_data["retention_time"].values
                signal_data = roi_data["intensity"].values

                # 绘制分析结果图
                gpc_plotter = GPCDataPlotter(
                    time_data=time_data,
                    signal_data=signal_data,
                    calibration_func=calibration_func,
                    peaks_info=peaks_info,
                    molecular_info=molecular_info,
                    output_dir=output_dir,
                    sample_name=simple_name
                )

                # 绘制并保存图表
                gpc_plotter.plot_gpc_machine_curve()

                # 有三色曲线时才绘制ROI结果图
                roi_result = data.get("roi_result", {})
                if "solvent_start" in roi_result:
                    gpc_plotter.plot_roi_result(actual_curve, roi_result, actual_curve_name=actual_curve_name)

                gpc_plotter.plot_peak_detect_process(peak_index=0, detect_mode=detect_mode, manual_interval=manual_interval)
                gpc_plotter.plot_with_cumulative(peak_index=0)
                gpc_plotter.plot_gpc_result(peak_index=0)

                # 返回峰值检测图
                peaks_plotly = gpc_plotter.get_peak_detect_plot(peak_index=0, detect_mode=detect_mode, manual_interval=manual_interval)
                data["peaks_plotly"] = peaks_plotly

                logger.info("绘图完成: %s", simple_name)
            except Exception as e:
                traceback.print_exc()
                logger.error("绘图异常: %s", str(e))

        return {"analysis_results": analysis_results}

    # --- 节点 6: PDF数据提取与对比 ---
    def node_pdf_data_extraction(self, state: GPCState) -> Dict[str, Any]:
        if state.get("errors") or not state.get("analysis_results"):
            return {}

        analysis_results = state.get("analysis_results", [])
        logger.info("开始从PDF报告中提取分子量数据...")
        manual_pdf = (state.get("comparison_report_pdf_path") or "").strip() or None
        shared_pdf_data: Optional[Dict[str, Any]] = None
        if manual_pdf and os.path.isfile(manual_pdf):
            shared_pdf_data = self.validator.extract_molecular_weight_info(manual_pdf)

        for data in analysis_results:
            try:
                curve_file = data.get("curve_file", "")
                base_name = os.path.splitext(os.path.basename(curve_file))[0]
                if shared_pdf_data is not None:
                    pdf_data = shared_pdf_data
                else:
                    # 优先在 .arw 同目录下查找同名 PDF
                    same_dir_pdf = os.path.join(os.path.dirname(curve_file), f"{base_name}.pdf")
                    if os.path.isfile(same_dir_pdf):
                        pdf_data = self.validator.extract_molecular_weight_info(same_dir_pdf)
                    else:
                        pdf_data = self.validator.process_gpc_data(base_name)
                
                # 将PDF提取的数据添加到结果中
                data["pdf_data"] = pdf_data
                logger.info("PDF数据提取完成: %s", base_name)
            except Exception as e:
                logger.error("PDF数据提取异常: %s", str(e))

        return {"analysis_results": analysis_results}

    # --- 节点 7: 保存报告 ---
    def node_save_report(self, state: GPCState) -> Dict[str, Any]:
        if state.get("errors") or not state.get("analysis_results"):
            return {}

        analysis_results = state.get("analysis_results", [])
        logger.info("开始保存分析报告...")
        
        for data in analysis_results:
            try:
                simple_name = data["simple_name"]
                output_dir = data["output_dir"]
                curve_file = data.get("curve_file")
                actual_curve = data.get('actual_curve')
                roi_data = data.get("roi_data")

                report_path = os.path.join(output_dir, f"{simple_name}_report.txt")
                
                # 构建报告内容
                report_content = []
                report_content.append("\n### 实验信息\n")
                report_content.append(f"- 文件路径: {curve_file}\n")
                report_content.append(f"- 样品名称: {simple_name}\n")
                report_content.append(f"- 总数据点数: {len(actual_curve)}\n")
                report_content.append(f"- 处理后数据点数: {len(roi_data)}\n")
                report_content.append(f"- 分析时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

                # 1. 峰值信息
                report_content.append("\n### 峰值信息\n")
                if "peaks_info" in data:
                    peaks_info = data["peaks_info"]
                    peaks_details = peaks_info.get("peaks_details", [])
                    report_content.append(f"- 检测到的峰数量: {len(peaks_details)}\n")
                    if peaks_details:
                        # 只展示首个峰的信息，按照格式
                        first_peak = peaks_details[0]
                        left_time = first_peak["left_time"]
                        peak_time = first_peak["peak_time"]
                        right_time = first_peak["right_time"]
                        peak_height = first_peak["peak_height"]
                        left_bound = first_peak["left_bound"]
                        right_bound = first_peak["right_bound"]
                        peak_idx = first_peak["peak_idx"]
                        peak_width = right_time - left_time
                        report_content.append("\n#### 目标峰信息\n")
                        report_content.append(f"- 峰位置点索引: {peak_idx} \n")
                        report_content.append(f"- 峰位置时间: {peak_time:.2f} min\n")
                        report_content.append(f"- 峰响应高度: {peak_height:.2f}\n")
                        report_content.append(f"- 左边界索引: {left_bound:.2f} min\n")
                        report_content.append(f"- 右边界索引: {right_bound} \n")
                        report_content.append(f"- 左边界时间: {left_time} \n")
                        report_content.append(f"- 右边界时间: {right_time:.2f} min\n")
                        report_content.append(f"- 峰宽度: {peak_width:.2f} min\n")
                else:
                    report_content.append("未获取到峰值信息\n")

                # 2. Agent提取的分子量信息
                report_content.append("\n### Agent提取的分子量信息\n")
                if "molecular_parameters" in data:
                    mp = data["molecular_parameters"]
                    report_content.append(f"- Mn: {mp.get('mn', 'N/A')} g/mol\n")
                    report_content.append(f"- Mw: {mp.get('mw', 'N/A')} g/mol\n")
                    report_content.append(f"- Mz: {mp.get('mz', 'N/A')} g/mol\n")
                    report_content.append(f"- PDI: {mp.get('pdi', 'N/A')}\n")
                else:
                    report_content.append("未获取到分子量参数\n")
                
                # 3. PDF报告提取的分子量信息
                report_content.append("\n### PDF报告提取的分子量信息\n")
                if "pdf_data" in data:
                    pdf_data = data.get("pdf_data", {})
                    report_content.append(f"- Mn: {pdf_data.get('Mn', 'N/A')} g/mol\n")
                    report_content.append(f"- Mw: {pdf_data.get('Mw', 'N/A')} g/mol\n")
                    report_content.append(f"- Mz: {pdf_data.get('Mz', 'N/A')} g/mol\n")
                    report_content.append(f"- PDI: {pdf_data.get('多分散性', 'N/A')}\n")
                    
                    # 计算误差分析
                    agent_data = data.get("molecular_parameters", {})
                    
                    report_content.append("\n### 误差分析结果\n")
                    
                    # 计算误差
                    mn_error = None
                    mw_error = None
                    mz_error = None
                    pdi_error = None
                    
                    if pdf_data.get("Mn") and agent_data.get("mn"):
                        mn_error = abs((agent_data["mn"] - pdf_data["Mn"]) / pdf_data["Mn"] * 100)
                        report_content.append(f"- Mn 误差: {mn_error:.2f}%\n")
                    
                    if pdf_data.get("Mw") and agent_data.get("mw"):
                        mw_error = abs((agent_data["mw"] - pdf_data["Mw"]) / pdf_data["Mw"] * 100)
                        report_content.append(f"- Mw 误差: {mw_error:.2f}%\n")
                    
                    if pdf_data.get("Mz") and agent_data.get("mz"):
                        mz_error = abs((agent_data["mz"] - pdf_data["Mz"]) / pdf_data["Mz"] * 100)
                        report_content.append(f"- Mz 误差: {mz_error:.2f}%\n")
                    
                    if pdf_data.get("多分散性") and agent_data.get("pdi"):
                        pdi_error = abs((agent_data["pdi"] - pdf_data["多分散性"]) / pdf_data["多分散性"] * 100)
                        report_content.append(f"- PDI 误差: {pdi_error:.2f}%\n")
                    
                    if not any([mn_error, mw_error, mz_error, pdi_error]):
                        report_content.append("无法计算误差分析结果\n")
                else:
                    report_content.append("未获取到PDF数据\n")
                
                # 保存报告
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(f"# GPC 分析报告\n")
                    f.writelines(report_content)
                
                logger.info("报告保存完成: %s", report_path)
                # 将报告路径添加到结果中
                data["report_content"] = "".join(report_content)
            except Exception as e:
                logger.error("保存报告异常: %s", str(e))

        return {"analysis_results": analysis_results}

    # --- 构建并编译图 ---
    def build(self):
        workflow = StateGraph(GPCState)

        workflow.add_node("scanner", self.node_scan_path)
        workflow.add_node("read_data", self.node_read_data)
        workflow.add_node("roi_identification", self.node_roi_identification)
        workflow.add_node("peak_detection_and_calculate_mw", self.node_peak_detection_and_calculate_mw)
        workflow.add_node("plot_results", self.node_plot_results)
        workflow.add_node("pdf_extraction", self.node_pdf_data_extraction)
        workflow.add_node("save_report", self.node_save_report)

        workflow.set_entry_point("scanner")

        # 线性连接
        workflow.add_edge("scanner", "read_data")
        workflow.add_edge("read_data", "roi_identification")
        workflow.add_edge("roi_identification", "peak_detection_and_calculate_mw")
        workflow.add_edge("peak_detection_and_calculate_mw", "plot_results")
        workflow.add_edge("plot_results", "pdf_extraction")
        workflow.add_edge("pdf_extraction", "save_report")
        workflow.add_edge("save_report", END)

        return workflow.compile()


def generate_gpc_report(results: list) -> str:
    """生成分析报告"""
    report = "# GPC分析报告\n"
    for i, result_item in enumerate(results):
        report += f"\n## 样品 {i + 1}\n"
        report += result_item.get('report_content')

    return report


def _extract_first_gpc_qa_metrics(analysis_results: list[dict[str, Any]]) -> dict[str, Any]:
    """提取首个样品的验收指标（用于单样品批处理接口）。"""
    qa: dict[str, Any] = {}
    if not analysis_results:
        return qa
    row = analysis_results[0] if isinstance(analysis_results[0], dict) else {}
    mp = row.get("molecular_parameters", {}) if isinstance(row, dict) else {}
    pdf = row.get("pdf_data", {}) if isinstance(row, dict) else {}

    def _safe_float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    mn = _safe_float(mp.get("mn"))
    mw = _safe_float(mp.get("mw"))
    pdi = _safe_float(mp.get("pdi"))
    mn_ref = _safe_float(pdf.get("Mn"))
    mw_ref = _safe_float(pdf.get("Mw"))
    pdi_ref = _safe_float(pdf.get("多分散性"))

    if mn is not None and mn_ref not in (None, 0):
        qa["mn_rd_pct"] = abs((mn - mn_ref) / mn_ref) * 100.0
    if mw is not None and mw_ref not in (None, 0):
        qa["mw_rd_pct"] = abs((mw - mw_ref) / mw_ref) * 100.0
    if pdi is not None and pdi_ref not in (None, 0):
        qa["pdi_rd_pct"] = abs((pdi - pdi_ref) / pdi_ref) * 100.0
    qa["has_reference"] = bool(pdf)
    return qa


def run_gpc_analysis(
    input_path: str,
    *,
    detect_mode: str = "auto",
    manual_interval: Optional[List[float]] = None,
    three_color_arw_paths: Optional[Tuple[str, str, str]] = None,
    calibration_file_path: Optional[str] = None,
    comparison_report_pdf_path: Optional[str] = None,
    source_file_name: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    app = GPCPathWorkflow(output_dir=output_dir).build()
    state: Dict[str, Any] = {
        "input_path": input_path,
        "detect_mode": detect_mode,
        "manual_interval": manual_interval,
        "source_file_name": source_file_name,
    }
    if three_color_arw_paths:
        state["three_color_arw_paths"] = three_color_arw_paths
    if calibration_file_path:
        state["calibration_file_path"] = calibration_file_path
    if comparison_report_pdf_path:
        state["comparison_report_pdf_path"] = comparison_report_pdf_path

    final_state = app.invoke(state, config={"recursion_limit": 50})
    analysis_results = final_state.get("analysis_results") or []
    text_report = generate_gpc_report(analysis_results)
    qa_metrics = _extract_first_gpc_qa_metrics(analysis_results)

    return {
        "structured_data": {
            "analysis_results": analysis_results,
        },
        "text_report": text_report,
        "errors": final_state.get("errors") or [],
        "metadata": {
            "spectrum_type": "gpc",
            "input_path": input_path,
            "detect_mode": detect_mode,
            "source_file_name": source_file_name,
            "sample_count": len(analysis_results),
            "qa_metrics": qa_metrics,
        },
    }


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GPC 谱图一键分析脚本")
    parser.add_argument("input_path", type=str, help="输入 .arw 文件或目录路径")
    parser.add_argument("--detect-mode", type=str, default="auto", choices=["auto", "manual"])
    parser.add_argument(
        "--manual-interval",
        type=str,
        default=None,
        help="手动时间区间，格式 start,end（detect-mode=manual 时可用）",
    )
    parser.add_argument("--green-arw", type=str, default=None, help="三色绿光 .arw 路径")
    parser.add_argument("--red-arw", type=str, default=None, help="三色红光 .arw 路径")
    parser.add_argument("--white-arw", type=str, default=None, help="三色白光 .arw 路径")
    parser.add_argument("--calibration-file", type=str, default=None, help="校准文件路径（json/pdf）")
    parser.add_argument("--comparison-pdf", type=str, default=None, help="对比报告 PDF 路径")
    parser.add_argument("--report-path", type=str, default=None, help="报告输出路径（md）")
    return parser

if __name__ == "__main__":
    args = _build_cli_parser().parse_args()
    # 非终端运行时，可注释掉上一行，使用下面的 args 直接赋值：
    # class Args:
    #     input_path = r"E:\spectrum_files\gpc\spectrum\GPC_03_20240924-1_Cal001_Copoly_THF_mix\GPC_03_20240924-1_Cal001_Copoly_THF_mix.arw"
    #     detect_mode = "auto"
    #     manual_interval = None
    #     green_arw = None
    #     red_arw = None
    #     white_arw = None
    #     calibration_file = None
    #     comparison_pdf = None
    #     report_path = None
    #
    # args = Args()

    manual_interval = _parse_manual_interval(args.manual_interval)

    three_color_arw_paths = None
    if args.green_arw and args.red_arw and args.white_arw:
        three_color_arw_paths = (args.green_arw, args.red_arw, args.white_arw)

    out = run_gpc_analysis(
        input_path=args.input_path,
        detect_mode=args.detect_mode,
        manual_interval=manual_interval,
        three_color_arw_paths=three_color_arw_paths,
        calibration_file_path=args.calibration_file,
        comparison_report_pdf_path=args.comparison_pdf,
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
