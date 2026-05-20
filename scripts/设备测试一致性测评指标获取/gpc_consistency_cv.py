"""基于GPC解析结果计算同一分布样品重复测试的Mw、Mn CV系数。"""

import json
import os
import sys
import numpy as np
from collections import defaultdict

# 确保可以导入 backend 下的模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from app.modules.gpc.workflow import run_gpc_analysis


TEST_DIR = r"E:\spectrum_files\gpc\0000一致性测试"
REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")


def _get_sample_code(sample_dir: str) -> str | None:
    """从样品目录中的JSON文件读取code字段，返回样品组名（如001）。"""
    json_files = [f for f in os.listdir(sample_dir) if f.endswith(".json")]
    if not json_files:
        return None
    json_path = os.path.join(sample_dir, json_files[0])
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    code = data.get("code", "")
    # code形如 "001_1"，取下划线前部分作为样品组名
    return code.rsplit("_", 1)[0] if "_" in code else code


def _find_arw_file(sample_dir: str) -> str | None:
    """查找样品目录中的.arw谱图文件。"""
    for f in os.listdir(sample_dir):
        if f.lower().endswith(".arw"):
            return os.path.join(sample_dir, f)
    return None


def _extract_mw_mn(arw_path: str) -> dict:
    """调用GPC工作流解析谱图，提取Mw和Mn。

    Args:
        arw_path: .arw谱图文件路径。

    Returns:
        包含mw和mn的字典，解析失败时返回错误信息。
    """
    try:
        result = run_gpc_analysis(arw_path)
        analysis_results = result.get("structured_data", {}).get("analysis_results", [])
        if not analysis_results:
            return {"error": "解析结果为空"}
        mp = analysis_results[0].get("molecular_parameters", {})
        mw = _safe_float(mp.get("mw"))
        mn = _safe_float(mp.get("mn"))
        if mw is None or mn is None:
            return {"error": f"分子量缺失: mw={mp.get('mw')}, mn={mp.get('mn')}"}
        return {"mw": mw, "mn": mn}
    except Exception as e:
        return {"error": str(e)}


def _safe_float(v) -> float | None:
    """安全转换为浮点数。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _calc_cv(values: list[float]) -> float:
    """计算CV系数（%）。

    Args:
        values: 数值列表。

    Returns:
        CV值（%），均值为零时返回NaN。
    """
    arr = np.array(values)
    mean = np.mean(arr)
    if mean == 0:
        return float("nan")
    return (np.std(arr, ddof=1) / mean) * 100


def main():
    """遍历所有样品目录，分组计算Mw和Mn的CV系数。"""
    # 扫描目录，按样品组名分组
    sample_dirs = sorted([
        d for d in os.listdir(TEST_DIR)
        if os.path.isdir(os.path.join(TEST_DIR, d))
    ])

    groups: dict[str, list[str]] = defaultdict(list)
    for dir_name in sample_dirs:
        full_path = os.path.join(TEST_DIR, dir_name)
        group_name = _get_sample_code(full_path)
        if group_name:
            groups[group_name].append(dir_name)

    # 逐组解析并计算CV
    results = []
    for group_name in sorted(groups.keys()):
        dir_list = groups[group_name]
        mw_list = []
        mn_list = []
        errors = []

        for dir_name in sorted(dir_list):
            full_path = os.path.join(TEST_DIR, dir_name)
            arw_path = _find_arw_file(full_path)
            if not arw_path:
                errors.append(f"{dir_name}: 未找到.arw文件")
                continue

            print(f"  解析中: {dir_name} ...")
            res = _extract_mw_mn(arw_path)
            if "error" in res:
                errors.append(f"{dir_name}: {res['error']}")
                continue

            mw_list.append(res["mw"])
            mn_list.append(res["mn"])

        if len(mw_list) < 2:
            results.append({"name": group_name, "error": f"有效数据不足({len(mw_list)}次): {'; '.join(errors)}"})
            continue

        mw_cv = _calc_cv(mw_list)
        mn_cv = _calc_cv(mn_list)
        results.append({
            "name": group_name,
            "num_tests": len(mw_list),
            "mw_mean": np.mean(mw_list),
            "mw_cv": mw_cv,
            "mn_mean": np.mean(mn_list),
            "mn_cv": mn_cv,
            "errors": errors,
        })

    # 构建报告
    lines = []
    lines.append("# GPC 一致性测试报告 — Mw/Mn CV 系数")
    lines.append("")
    lines.append(f"**测试目录**: `{TEST_DIR}`")
    lines.append(f"**样品组数**: {len(groups)} 组")
    lines.append("")
    lines.append("## 汇总结果")
    lines.append("")
    lines.append("| 样品组 | 测试次数 | Mw均值(Da) | Mw CV(%) | Mn均值(Da) | Mn CV(%) | 备注 |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")

    for r in results:
        if "error" in r:
            lines.append(f"| {r['name']} | | | | | | {r['error']} |")
            continue
        err_str = "; ".join(r["errors"]) if r.get("errors") else ""
        lines.append(
            f"| {r['name']} | {r['num_tests']} | {r['mw_mean']:.2f} | {r['mw_cv']:.4f} | "
            f"{r['mn_mean']:.2f} | {r['mn_cv']:.4f} | {err_str} |"
        )

    # 汇总统计
    valid = [r for r in results if "error" not in r]
    if valid:
        avg_mw_cv = np.mean([r["mw_cv"] for r in valid])
        avg_mn_cv = np.mean([r["mn_cv"] for r in valid])
        lines.append(f"| **汇总（{len(valid)} 组）** | | | **{avg_mw_cv:.4f}** | | **{avg_mn_cv:.4f}** | |")

    report_text = "\n".join(lines)

    # 控制台输出
    print(report_text)

    # 保存为 md 文件
    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(REPORT_DIR, "gpc_cv_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n报告已保存: {report_path}")


if __name__ == "__main__":
    main()
