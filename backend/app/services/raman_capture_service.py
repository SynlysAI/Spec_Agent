"""拉曼光谱仪批量采集服务。"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from queue import Queue
from typing import Callable

import numpy as np
import requests

from app.schemas.raman_capture import (
    RamanCaptureResultItem,
    RamanCaptureRunData,
    RamanCaptureSummary,
)

logger = logging.getLogger(__name__)


@dataclass
class CaptureResult:
    """采集结果。"""

    success: bool
    task_id: str
    x_data: np.ndarray | None = None
    y_data: np.ndarray | None = None
    error_msg: str | None = None
    duration: float = 0.0


class CaptureTask:
    """拉曼采集任务对象。"""

    def __init__(self, req_id: str, params: dict, sequence: int = 0) -> None:
        """初始化采集任务。

        Args:
            req_id: 任务请求 ID。
            params: 采集参数。
            sequence: 任务序号。
        """
        self.req_id = req_id
        self.params = params
        self.sequence = sequence
        self.status = "pending"
        self.result: CaptureResult | None = None
        self.submit_time: float | None = None
        self.complete_time: float | None = None
        self.event = threading.Event()

    def set_completed(self, x_data: np.ndarray, y_data: np.ndarray) -> None:
        """标记任务采集成功。

        Args:
            x_data: 光谱横轴数据。
            y_data: 光谱强度数据。
        """
        self.status = "completed"
        self.complete_time = time.time()
        self.result = CaptureResult(
            success=True,
            task_id=self.req_id,
            x_data=x_data,
            y_data=y_data,
            duration=self.complete_time - self.submit_time if self.submit_time else 0.0,
        )
        self.event.set()
        logger.info("拉曼采集任务 %s [%s] 完成", self.sequence, self.req_id[:8])

    def set_failed(self, error_msg: str) -> None:
        """标记任务采集失败。

        Args:
            error_msg: 失败原因。
        """
        self.status = "failed"
        self.complete_time = time.time()
        self.result = CaptureResult(
            success=False,
            task_id=self.req_id,
            error_msg=error_msg,
            duration=self.complete_time - self.submit_time if self.submit_time else 0.0,
        )
        self.event.set()
        logger.error("拉曼采集任务 %s [%s] 失败: %s", self.sequence, self.req_id[:8], error_msg)

    def wait(self, timeout: float | None = None) -> CaptureResult:
        """等待任务完成并返回采集结果。

        Args:
            timeout: 等待超时时间，单位秒。

        Returns:
            采集结果。
        """
        finished = self.event.wait(timeout)
        if finished and self.result:
            return self.result
        self.set_failed("采集等待超时")
        return self.result or CaptureResult(success=False, task_id=self.req_id, error_msg="采集等待超时")


class _CallbackHandler(BaseHTTPRequestHandler):
    """光谱仪采集完成回调处理器。"""

    controller: "RamanSpectrometerController | None" = None

    def log_message(self, format: str, *args: object) -> None:
        """写入回调服务访问日志。

        Args:
            format: 日志格式。
            args: 日志参数。
        """
        logger.debug("[RamanCallback] %s", args[0] if args else format)

    def do_POST(self) -> None:
        """处理光谱仪 POST 回调。"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))
            req_id = data.get("req_id")
            task = self.controller.find_task(req_id) if self.controller else None

            if not task:
                logger.warning("未知拉曼采集任务回调: %s", req_id)
                self._respond(404, "Task not found")
                return

            if data.get("code", 0) != 0:
                task.set_failed(data.get("msg", "Instrument error"))
                self.controller.schedule_next(task)
                self._respond(0, "Error recorded")
                return

            payload = data.get("data", {})
            x_list = payload.get("x", [])
            y_list = payload.get("y", [])
            if not x_list or not y_list or len(x_list) != len(y_list):
                task.set_failed("Invalid data format")
                self.controller.schedule_next(task)
                self._respond(0, "Invalid data")
                return

            task.set_completed(np.array(x_list), np.array(y_list))
            self.controller.schedule_next(task)
            self._respond(0, "Success")
        except Exception as exc:
            logger.error("拉曼采集回调处理异常: %s", traceback.format_exc())
            self._respond(500, f"Server error: {exc}")

    def _respond(self, code: int, msg: str) -> None:
        """返回回调处理结果。

        Args:
            code: 业务状态码。
            msg: 响应消息。
        """
        response_body = json.dumps({"code": code, "msg": msg}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)


class RamanSpectrometerController:
    """拉曼光谱仪队列化采集控制器。"""

    def __init__(
        self,
        instrument_ip: str,
        instrument_port: int = 8088,
        callback_port: int = 9000,
        callback_host: str = "0.0.0.0",
    ) -> None:
        """初始化控制器并启动本机回调服务。

        Args:
            instrument_ip: 拉曼光谱仪 IP 地址。
            instrument_port: 拉曼光谱仪 HTTP 服务端口。
            callback_port: 本机回调服务监听端口。
            callback_host: 本机回调服务监听地址。
        """
        self.instrument_base = f"http://{instrument_ip}:{instrument_port}"
        self.capture_endpoint = f"{self.instrument_base}/raman/jy/capture"
        self.callback_url = f"http://{self._get_host_ip()}:{callback_port}/raman/jy/callback"
        self.callback_port = callback_port
        self.callback_host = callback_host
        self.task_queue: Queue[CaptureTask] = Queue()
        self.running_task: CaptureTask | None = None
        self.completed_tasks: list[CaptureTask] = []
        self.all_tasks: dict[str, CaptureTask] = {}
        self.lock = threading.Lock()
        self.queue_event = threading.Event()
        self._closed = False
        self._server: HTTPServer | None = None

        self._start_callback_server()
        self.scheduler_thread = threading.Thread(target=self._queue_scheduler, daemon=True)
        self.scheduler_thread.start()
        logger.info("拉曼采集控制器启动，回调地址: %s", self.callback_url)

    @staticmethod
    def _get_host_ip() -> str:
        """获取当前主机局域网 IP。

        Returns:
            当前主机 IP 地址，失败时返回 127.0.0.1。
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"
        finally:
            sock.close()

    def _start_callback_server(self) -> None:
        """启动光谱仪回调 HTTP 服务。"""
        _CallbackHandler.controller = self
        self._server = HTTPServer((self.callback_host, self.callback_port), _CallbackHandler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        time.sleep(0.2)

    def find_task(self, req_id: str) -> CaptureTask | None:
        """通过请求 ID 查找采集任务。

        Args:
            req_id: 任务请求 ID。

        Returns:
            匹配的任务对象，未找到返回 None。
        """
        with self.lock:
            return self.all_tasks.get(req_id)

    def _queue_scheduler(self) -> None:
        """后台队列调度线程，确保任务按顺序发送。"""
        while not self._closed:
            self.queue_event.wait()
            self.queue_event.clear()
            if self._closed:
                break

            with self.lock:
                if self.running_task is not None or self.task_queue.empty():
                    continue
                task = self.task_queue.get()
                self.running_task = task
            self._send_capture_command(task)

    def _send_capture_command(self, task: CaptureTask) -> None:
        """向拉曼光谱仪发送采集指令。

        Args:
            task: 待发送的采集任务。
        """
        task.status = "running"
        task.submit_time = time.time()
        payload = {
            "req_id": task.req_id,
            "capture": {
                **task.params,
                "callback_url": self.callback_url,
            },
        }

        try:
            response = requests.post(self.capture_endpoint, json=payload, timeout=10)
            response.raise_for_status()
            resp_data = response.json()
            if resp_data.get("code") != 0:
                error_msg = resp_data.get("msg", "Unknown error")
                task.set_failed(f"仪器拒绝: {error_msg}")

                if "正在执行" in error_msg or "忙" in error_msg or "wait" in error_msg.lower():
                    logger.warning("拉曼采集任务 %s 遇到仪器忙，准备重试", task.sequence)
                    task.status = "pending"
                    task.event.clear()
                    with self.lock:
                        self.running_task = None
                        temp_list = list(self.task_queue.queue)
                        self.task_queue = Queue()
                        self.task_queue.put(task)
                        for item in temp_list:
                            self.task_queue.put(item)
                    threading.Timer(1.0, self.queue_event.set).start()
                    return

                self.schedule_next(task)
            else:
                logger.info("拉曼采集任务 %s [%s] 已发送仪器", task.sequence, task.req_id[:8])
        except Exception as exc:
            task.set_failed(f"网络错误: {exc}")
            self.schedule_next(task)

    def schedule_next(self, completed_task: CaptureTask) -> None:
        """结束当前任务并触发下一个任务。

        Args:
            completed_task: 已结束的任务。
        """
        with self.lock:
            self.running_task = None
            if completed_task not in self.completed_tasks:
                self.completed_tasks.append(completed_task)
        self.queue_event.set()

    def add_task(self, explore_time: float, integer: int, laser: float, center_wave: float) -> CaptureTask:
        """添加采集任务到队列。

        Args:
            explore_time: 积分时间。
            integer: 积分次数。
            laser: 激光功率。
            center_wave: 中心波数。

        Returns:
            已创建的采集任务对象。
        """
        req_id = str(uuid.uuid4())
        params = {
            "explore_time": explore_time,
            "integer": integer,
            "laser": laser,
            "center_wave": center_wave,
        }
        with self.lock:
            sequence = len(self.all_tasks) + 1
            task = CaptureTask(req_id, params, sequence)
            self.all_tasks[req_id] = task
            self.task_queue.put(task)
        if sequence == 1 or self.running_task is None:
            self.queue_event.set()
        return task

    def batch_capture(
        self,
        conditions: list[tuple[float, int, float, float]],
        wait_all: bool = True,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[CaptureResult] | list[CaptureTask]:
        """批量采集拉曼光谱。

        Args:
            conditions: 采集条件列表，元素为 explore_time、integer、laser、center_wave。
            wait_all: 是否等待全部任务完成。
            progress_callback: 进度回调函数。

        Returns:
            采集结果列表或任务列表。
        """
        tasks = [self.add_task(et, it, ls, cw) for et, it, ls, cw in conditions]
        if not wait_all:
            return tasks

        results = []
        for index, task in enumerate(tasks):
            result = task.wait(timeout=60.0)
            results.append(result)
            if progress_callback:
                progress_callback(index + 1, len(tasks), f"完成 {task.params['laser']}/{task.params['center_wave']}")
        return results

    def shutdown(self) -> None:
        """关闭控制器和本机回调服务。"""
        self._closed = True
        self.queue_event.set()
        with self.lock:
            while not self.task_queue.empty():
                task = self.task_queue.get()
                task.set_failed("Controller shutdown")
            if self.running_task and self.running_task.status == "running":
                self.running_task.set_failed("Controller shutdown")
        if self._server:
            self._server.shutdown()
            self._server.server_close()


class RamanCaptureService:
    """拉曼采集工具服务。"""

    @staticmethod
    def run_batch_capture(
        instrument_ip: str,
        callback_port: int,
        wavenumber_list: list[float],
        power_list: list[float],
    ) -> RamanCaptureRunData:
        """执行拉曼批量采集并生成内存报告。

        Args:
            instrument_ip: 拉曼光谱仪 IP 地址。
            callback_port: 本机回调服务监听端口。
            wavenumber_list: 中心波数列表。
            power_list: 激光功率列表。

        Returns:
            拉曼批量采集运行结果。
        """
        if not wavenumber_list:
            raise ValueError("中心波数列表不能为空")
        if not power_list:
            raise ValueError("激光功率列表不能为空")

        started_at = time.time()
        controller = RamanSpectrometerController(instrument_ip=instrument_ip, callback_port=callback_port)
        try:
            conditions = [(1.0, 1, power, wavenumber) for wavenumber in wavenumber_list for power in power_list]
            raw_results = controller.batch_capture(conditions, wait_all=True)
            result_items = RamanCaptureService._build_result_items(
                tasks=list(controller.all_tasks.values()),
                raw_results=raw_results,
            )
            duration = time.time() - started_at
            success_count = sum(1 for item in result_items if item.success)
            summary = RamanCaptureSummary(
                total=len(result_items),
                success=success_count,
                failed=len(result_items) - success_count,
                duration_seconds=round(duration, 3),
            )
            report = RamanCaptureService._build_report(
                instrument_ip=instrument_ip,
                callback_port=callback_port,
                callback_url=controller.callback_url,
                summary=summary,
                results=result_items,
            )
            return RamanCaptureRunData(
                instrument_ip=instrument_ip,
                callback_port=callback_port,
                callback_url=controller.callback_url,
                summary=summary,
                results=result_items,
                report=report,
            )
        finally:
            controller.shutdown()

    @staticmethod
    def _build_result_items(
        tasks: list[CaptureTask],
        raw_results: list[CaptureResult] | list[CaptureTask],
    ) -> list[RamanCaptureResultItem]:
        """转换采集任务为前端展示结果。

        Args:
            tasks: 采集任务列表。
            raw_results: 原始采集结果列表。

        Returns:
            前端展示结果列表。
        """
        results_by_id = {
            result.task_id: result
            for result in raw_results
            if isinstance(result, CaptureResult)
        }
        items = []
        for task in sorted(tasks, key=lambda item: item.sequence):
            result = results_by_id.get(task.req_id) or task.result
            y_data = result.y_data if result and result.y_data is not None else None
            items.append(
                RamanCaptureResultItem(
                    sequence=task.sequence,
                    task_id=task.req_id,
                    wavenumber=float(task.params["center_wave"]),
                    power=float(task.params["laser"]),
                    status=task.status,
                    success=bool(result.success if result else False),
                    point_count=int(len(y_data)) if y_data is not None else 0,
                    y_min=float(np.min(y_data)) if y_data is not None and len(y_data) > 0 else None,
                    y_max=float(np.max(y_data)) if y_data is not None and len(y_data) > 0 else None,
                    duration_seconds=round(float(result.duration), 3) if result else 0.0,
                    error_msg=result.error_msg if result else "任务未返回结果",
                )
            )
        return items

    @staticmethod
    def _build_report(
        instrument_ip: str,
        callback_port: int,
        callback_url: str,
        summary: RamanCaptureSummary,
        results: list[RamanCaptureResultItem],
    ) -> str:
        """生成 Markdown 采集报告。

        Args:
            instrument_ip: 拉曼光谱仪 IP 地址。
            callback_port: 本机回调服务监听端口。
            callback_url: 实际回调地址。
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
            f"- 回调端口：{callback_port}",
            f"- 回调地址：{callback_url}",
            f"- 总任务数：{summary.total}",
            f"- 成功数量：{summary.success}",
            f"- 失败数量：{summary.failed}",
            f"- 总耗时：{summary.duration_seconds:.3f} 秒",
            "",
            "## 采集明细",
            "",
            "| 序号 | 中心波数 | 激光功率 | 状态 | 数据点 | 强度范围 | 耗时(s) | 错误信息 |",
            "| --- | ---: | ---: | --- | ---: | --- | ---: | --- |",
        ]
        for item in results:
            y_range = "-"
            if item.y_min is not None and item.y_max is not None:
                y_range = f"{item.y_min:.3f} ~ {item.y_max:.3f}"
            lines.append(
                "| "
                f"{item.sequence} | "
                f"{item.wavenumber:g} | "
                f"{item.power:g} | "
                f"{'成功' if item.success else '失败'} | "
                f"{item.point_count} | "
                f"{y_range} | "
                f"{item.duration_seconds:.3f} | "
                f"{item.error_msg or '-'} |"
            )
        return "\n".join(lines)


raman_capture_service = RamanCaptureService()
