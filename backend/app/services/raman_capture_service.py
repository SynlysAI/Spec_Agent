"""拉曼光谱仪批量采集服务。"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import requests

from app.schemas.raman_capture import (
    RamanCaptureResultItem,
    RamanCaptureRunData,
    RamanCaptureSummary,
)

logger = logging.getLogger(__name__)


RESULT_POLLING_INTERVAL_SECONDS = 5
RESULT_POLLING_TIMEOUT_SECONDS = 60


@dataclass
class CaptureTask:
    """拉曼采集任务对象。"""

    req_id: str
    sequence: int
    explore_time: float
    integer: int
    power_type: int
    power: float
    grating_index: int
    wavenumber: float
    callback_url: str
    status: str = "pending"
    x_values: list[float] | None = None
    y_values: list[float] | None = None
    point_count: int = 0
    y_min: float | None = None
    y_max: float | None = None
    response_file: str | None = None
    error_msg: str | None = None
    duration_seconds: float = 0.0


class RamanCaptureService:
    """拉曼采集工具服务。"""

    def __init__(self) -> None:
        self.submit_port = 7001
        self.result_port = 7002
        self.connect_timeout = 10
        self.read_timeout = 20
        self.polling_timeout_seconds = RESULT_POLLING_TIMEOUT_SECONDS
        self.polling_interval_seconds = RESULT_POLLING_INTERVAL_SECONDS
        self.session = requests.Session()

    def run_batch_capture(
        self,
        instrument_ip: str,
        callback_url: str,
        submit_port: int,
        result_port: int,
        wavenumber_list: list[float],
        power_list: list[float],
        explore_time: float,
        integer: int,
        power_type: int,
        grating_index: int,
    ) -> RamanCaptureRunData:
        """执行拉曼批量采集并生成内存报告。

        Args:
            instrument_ip: 拉曼光谱仪 IP 地址。
            callback_url: 采集回调地址。
            submit_port: 下发任务接口端口。
            result_port: 查询结果接口端口。
            wavenumber_list: 中心波数列表。
            power_list: 激光功率列表。
            explore_time: 积分时间。
            integer: 积分次数。
            power_type: 功率类型。
            grating_index: 光栅索引。

        Returns:
            拉曼批量采集运行结果。
        """
        if not wavenumber_list:
            raise ValueError("中心波数列表不能为空")
        if not power_list:
            raise ValueError("激光功率列表不能为空")
        if not callback_url.strip():
            raise ValueError("回调地址不能为空")

        started_at = time.time()
        tasks = self._build_tasks(
            callback_url=callback_url.strip(),
            wavenumber_list=wavenumber_list,
            power_list=power_list,
            explore_time=explore_time,
            integer=integer,
            power_type=power_type,
            grating_index=grating_index,
        )

        for task in tasks:
            self._execute_single_task(
                instrument_ip=instrument_ip,
                submit_port=submit_port,
                result_port=result_port,
                task=task,
            )

        duration = time.time() - started_at
        success_count = sum(1 for task in tasks if task.status == "completed")
        summary = RamanCaptureSummary(
            total=len(tasks),
            success=success_count,
            failed=len(tasks) - success_count,
            duration_seconds=round(duration, 3),
        )
        result_items = [self._build_result_item(task=task) for task in tasks]
        report = self._build_report(
            instrument_ip=instrument_ip,
            callback_url=callback_url.strip(),
            summary=summary,
            results=result_items,
        )
        return RamanCaptureRunData(
            instrument_ip=instrument_ip,
            callback_url=callback_url.strip(),
            polling_interval_seconds=self.polling_interval_seconds,
            polling_timeout_seconds=self.polling_timeout_seconds,
            summary=summary,
            results=result_items,
            report=report,
        )

    @staticmethod
    def _build_tasks(
        callback_url: str,
        wavenumber_list: list[float],
        power_list: list[float],
        explore_time: float,
        integer: int,
        power_type: int,
        grating_index: int,
    ) -> list[CaptureTask]:
        """构建批量组合任务列表。

        Args:
            callback_url: 回调地址。
            wavenumber_list: 中心波数列表。
            power_list: 激光功率列表。
            explore_time: 积分时间。
            integer: 积分次数。
            power_type: 功率类型。
            grating_index: 光栅索引。

        Returns:
            采集任务列表。
        """
        tasks = []
        sequence = 1
        for wavenumber in wavenumber_list:
            for power in power_list:
                req_id = uuid.uuid4().hex
                tasks.append(
                    CaptureTask(
                        req_id=req_id,
                        sequence=sequence,
                        explore_time=explore_time,
                        integer=integer,
                        power_type=power_type,
                        power=power,
                        grating_index=grating_index,
                        wavenumber=wavenumber,
                        callback_url=callback_url,
                    )
                )
                sequence += 1
        return tasks

    def _execute_single_task(
        self,
        instrument_ip: str,
        submit_port: int,
        result_port: int,
        task: CaptureTask,
    ) -> None:
        """执行单个拉曼采集任务。

        Args:
            instrument_ip: 拉曼光谱仪 IP 地址。
            submit_port: 下发任务接口端口。
            result_port: 查询结果接口端口。
            task: 采集任务对象。
        """
        started_at = time.time()
        task.status = "submitting"
        submit_url = f"http://{instrument_ip}:{submit_port}/raman/jy/capture"
        payload = {
            "req_id": task.req_id,
            "capture": {
                "explore_time": task.explore_time,
                "integer": task.integer,
                "power_type": task.power_type,
                "laser": task.power,
                "grating_index": task.grating_index,
                "center_wave": task.wavenumber,
                "callback_url": task.callback_url,
            },
        }
        try:
            response = self.session.post(
                submit_url,
                json=payload,
                timeout=(self.connect_timeout, self.read_timeout),
            )
            response.raise_for_status()
            response_payload = response.json()
        except requests.exceptions.RequestException as exc:
            task.status = "failed"
            task.error_msg = f"任务下发失败: {exc}"
            task.duration_seconds = round(time.time() - started_at, 3)
            logger.error("拉曼采集任务 %s 下发失败: %s", task.req_id, exc)
            return
        except ValueError as exc:
            task.status = "failed"
            task.error_msg = f"任务下发返回非 JSON: {exc}"
            task.duration_seconds = round(time.time() - started_at, 3)
            logger.error("拉曼采集任务 %s 返回非 JSON", task.req_id)
            return

        if response_payload.get("code") != 0:
            task.status = "failed"
            task.error_msg = response_payload.get("msg") or f"任务下发失败，返回码 {response_payload.get('code')}"
            task.duration_seconds = round(time.time() - started_at, 3)
            logger.error("拉曼采集任务 %s 业务失败: %s", task.req_id, task.error_msg)
            return

        self._poll_task_result(
            instrument_ip=instrument_ip,
            result_port=result_port,
            task=task,
            started_at=started_at,
        )

    def _poll_task_result(self, instrument_ip: str, result_port: int, task: CaptureTask, started_at: float) -> None:
        """轮询查询拉曼采集结果。

        Args:
            instrument_ip: 拉曼光谱仪 IP 地址。
            result_port: 查询结果接口端口。
            task: 采集任务对象。
            started_at: 任务开始时间戳。
        """
        task.status = "polling"
        result_url = f"http://{instrument_ip}:{result_port}/raman/jy/result"
        deadline = started_at + self.polling_timeout_seconds

        while time.time() <= deadline:
            try:
                response = self.session.get(
                    result_url,
                    params={"req_id": task.req_id},
                    timeout=(self.connect_timeout, self.read_timeout),
                )
                response.raise_for_status()
                response_payload = response.json()
            except requests.exceptions.RequestException as exc:
                task.status = "failed"
                task.error_msg = f"结果查询失败: {exc}"
                task.duration_seconds = round(time.time() - started_at, 3)
                logger.error("拉曼采集任务 %s 查询失败: %s", task.req_id, exc)
                return
            except ValueError as exc:
                task.status = "failed"
                task.error_msg = f"结果查询返回非 JSON: {exc}"
                task.duration_seconds = round(time.time() - started_at, 3)
                logger.error("拉曼采集任务 %s 查询返回非 JSON", task.req_id)
                return

            code = response_payload.get("code")
            if code == 1:
                logger.info("拉曼采集任务 %s 仍在采集中，%s 秒后重试", task.req_id, self.polling_interval_seconds)
                time.sleep(self.polling_interval_seconds)
                continue
            if code == 0:
                self._fill_completed_task(
                    task=task,
                    response_payload=response_payload,
                    duration_seconds=round(time.time() - started_at, 3),
                )
                return
            if code == -1:
                task.status = "failed"
                task.error_msg = response_payload.get("msg") or "任务采集失败"
                task.duration_seconds = round(time.time() - started_at, 3)
                return
            if code == -4:
                task.status = "failed"
                task.error_msg = "未找到 req_id 对应结果"
                task.duration_seconds = round(time.time() - started_at, 3)
                return

            task.status = "failed"
            task.error_msg = response_payload.get("msg") or f"未知结果码: {code}"
            task.duration_seconds = round(time.time() - started_at, 3)
            return

        task.status = "failed"
        task.error_msg = f"结果轮询超时（>{self.polling_timeout_seconds} 秒）"
        task.duration_seconds = round(time.time() - started_at, 3)

    @staticmethod
    def _fill_completed_task(task: CaptureTask, response_payload: dict, duration_seconds: float) -> None:
        """填充已完成任务的谱图结果。

        Args:
            task: 采集任务对象。
            response_payload: 查询结果响应体。
            duration_seconds: 任务总耗时。
        """
        data_wrapper = response_payload.get("data") or {}
        spectrum_data = data_wrapper.get("data") or {}
        x_values = spectrum_data.get("x") or []
        y_values = spectrum_data.get("y") or []
        if not x_values or not y_values or len(x_values) != len(y_values):
            task.status = "failed"
            task.error_msg = "查询结果缺少有效谱图数据"
            task.duration_seconds = duration_seconds
            return

        x_numbers = [float(value) for value in x_values]
        y_numbers = [float(value) for value in y_values]
        y_array = np.array(y_numbers, dtype=float)

        task.status = "completed"
        task.x_values = x_numbers
        task.y_values = y_numbers
        task.point_count = len(y_numbers)
        task.y_min = float(np.min(y_array)) if len(y_array) > 0 else None
        task.y_max = float(np.max(y_array)) if len(y_array) > 0 else None
        task.response_file = data_wrapper.get("response_file")
        task.duration_seconds = duration_seconds
        task.error_msg = None

    @staticmethod
    def _build_result_item(task: CaptureTask) -> RamanCaptureResultItem:
        """构建前端返回结果项。

        Args:
            task: 采集任务对象。

        Returns:
            前端结果项。
        """
        return RamanCaptureResultItem(
            sequence=task.sequence,
            task_id=task.req_id,
            wavenumber=task.wavenumber,
            power=task.power,
            explore_time=task.explore_time,
            integer=task.integer,
            power_type=task.power_type,
            grating_index=task.grating_index,
            status=task.status,
            success=task.status == "completed",
            point_count=task.point_count,
            y_min=task.y_min,
            y_max=task.y_max,
            duration_seconds=task.duration_seconds,
            error_msg=task.error_msg,
            response_file=task.response_file,
            x_values=task.x_values or [],
            y_values=task.y_values or [],
        )

    @staticmethod
    def _build_report(
        instrument_ip: str,
        callback_url: str,
        summary: RamanCaptureSummary,
        results: list[RamanCaptureResultItem],
    ) -> str:
        """生成 Markdown 采集报告。

        Args:
            instrument_ip: 拉曼光谱仪 IP 地址。
            callback_url: 回调地址。
            summary: 采集汇总。
            results: 单条件结果列表。

        Returns:
            Markdown 文本报告。
        """
        lines = [
            "# 拉曼批量采集报告",
            "",
            f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- 仪器地址：{instrument_ip}",
            f"- 回调地址：{callback_url}",
            f"- 轮询间隔：{RESULT_POLLING_INTERVAL_SECONDS} 秒",
            f"- 单任务超时：{RESULT_POLLING_TIMEOUT_SECONDS} 秒",
            f"- 总任务数：{summary.total}",
            f"- 成功数量：{summary.success}",
            f"- 失败数量：{summary.failed}",
            f"- 总耗时：{summary.duration_seconds:.3f} 秒",
            "",
            "## 采集明细",
            "",
            "| 序号 | req_id | 中心波数 | 激光功率 | 状态 | 数据点 | 强度范围 | 结果文件 | 耗时(s) | 错误信息 |",
            "| --- | --- | ---: | ---: | --- | ---: | --- | --- | ---: | --- |",
        ]
        for item in results:
            y_range = "-"
            if item.y_min is not None and item.y_max is not None:
                y_range = f"{item.y_min:.3f} ~ {item.y_max:.3f}"
            lines.append(
                "| "
                f"{item.sequence} | "
                f"{item.task_id} | "
                f"{item.wavenumber:g} | "
                f"{item.power:g} | "
                f"{'成功' if item.success else '失败'} | "
                f"{item.point_count} | "
                f"{y_range} | "
                f"{item.response_file or '-'} | "
                f"{item.duration_seconds:.3f} | "
                f"{item.error_msg or '-'} |"
            )
        return "\n".join(lines)


raman_capture_service = RamanCaptureService()
