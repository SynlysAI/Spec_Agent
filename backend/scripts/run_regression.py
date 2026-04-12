"""P0 回归脚本（GPC/NMR）。"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class RegressionCase:
    """定义回归任务用例。"""

    kind: str
    payload: dict[str, Any]
    timeout_seconds: int = 240


def _build_cases() -> list[RegressionCase]:
    """构建 P0 回归用例列表。

    Returns:
        包含 GPC 与 NMR 用例的列表。
    """
    gpc_path = os.getenv(
        "REG_GPC_PATH",
        r"E:\spectrum_files\gpc\spectrum\GPC_03_20240924-1_Cal001_Copoly_THF_mix\GPC_03_20240924-1_Cal001_Copoly_THF_mix.arw",
    )
    nmr_path = os.getenv(
        "REG_NMR_PATH",
        r"E:\spectrum_files\nmr\2026-03-17\WLS-0312-H",
    )
    return [
        RegressionCase(
            kind="gpc",
            payload={
                "input": {"input_type": "file_path", "input_path": gpc_path, "file_id": None},
                "params": {
                    "detect_mode": "auto",
                    "manual_interval": None,
                    "three_color_arw_paths": None,
                    "calibration_file_path": None,
                    "comparison_report_pdf_path": None,
                },
                "options": {"priority": 5, "callback_url": None},
            },
        ),
        RegressionCase(
            kind="nmr",
            payload={
                "input": {"input_type": "folder_path", "input_path": nmr_path, "file_id": None},
                "params": {
                    "nucleus": "1H",
                    "threshold": 0.01,
                    "min_distance": 0.3,
                    "min_prominence": 0.01,
                    "width_multiplier": 1.0,
                    "baseline_degree": 3,
                    "smooth_window": 5,
                    "detection_range_mode": "full",
                    "detection_range_min": None,
                    "detection_range_max": None,
                    "ppm_offset": 0.0,
                    "integration_method": "voigt",
                    "internal_standard_policy": "auto",
                    "internal_standard_prefer": ["solvent", "tms"],
                },
                "options": {"priority": 5, "callback_url": None},
            },
        ),
    ]


def _poll_task(base_url: str, task_id: str, timeout_seconds: int) -> dict[str, Any]:
    """轮询任务直到结束状态。

    Args:
        base_url: API 服务地址前缀。
        task_id: 任务 ID。
        timeout_seconds: 最大等待时间（秒）。

    Returns:
        任务状态查询接口中的 `data` 字段。
    """
    start = time.time()
    while True:
        resp = requests.get(f"{base_url}/tasks/{task_id}", timeout=10)
        resp.raise_for_status()
        data = resp.json()["data"]
        if data["status"] in ("SUCCESS", "FAILED"):
            return data
        if time.time() - start > timeout_seconds:
            raise TimeoutError(f"task timeout: {task_id}")
        time.sleep(1)


def run_regression() -> int:
    """执行 P0 回归测试并返回退出码。

    Returns:
        `0` 表示全部通过，`1` 表示健康检查失败，`2` 表示存在失败用例。
    """
    base_url = os.getenv("REG_BASE_URL", "http://127.0.0.1:8000/api/v1")
    health = requests.get(f"{base_url}/health", timeout=10)
    if health.status_code != 200:
        print("health check failed:", health.status_code, health.text)
        return 1

    all_passed = True
    for case in _build_cases():
        create = requests.post(
            f"{base_url}/tasks/{case.kind}",
            json=case.payload,
            timeout=20,
        )
        if create.status_code != 200:
            print(f"[{case.kind}] create failed:", create.status_code, create.text)
            all_passed = False
            continue
        task_id = create.json().get("data", {}).get("task_id")
        if not task_id:
            print(f"[{case.kind}] missing task_id:", create.text)
            all_passed = False
            continue

        try:
            status = _poll_task(base_url, task_id, case.timeout_seconds)
        except Exception as exc:
            print(f"[{case.kind}] poll failed:", str(exc))
            all_passed = False
            continue

        result = requests.get(f"{base_url}/tasks/{task_id}/result", timeout=20)
        if result.status_code != 200:
            print(f"[{case.kind}] result failed:", result.status_code, result.text)
            all_passed = False
            continue

        result_data = result.json().get("data", {})
        if status["status"] != "SUCCESS" or result_data.get("status") != "SUCCESS":
            print(f"[{case.kind}] not success:", result_data)
            all_passed = False
            continue

        print(f"[{case.kind}] success task_id={task_id}")

    return 0 if all_passed else 2


if __name__ == "__main__":
    raise SystemExit(run_regression())
