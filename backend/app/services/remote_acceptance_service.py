"""远程验收汇总执行服务。"""

from __future__ import annotations

import json
import time
from typing import Any

import paramiko

from app.core.logging import get_logger

logger = get_logger("spec_agent.services.remote_acceptance")


class RemoteAcceptanceService:
    """通过 SSH 执行远程验收脚本并解析 JSON 输出。"""

    @staticmethod
    def run_remote_summary(type_config: dict[str, Any]) -> dict[str, Any]:
        """执行远程汇总脚本。

        Args:
            type_config: 当前谱图类型配置。

        Returns:
            远程脚本返回的 JSON 字典。
        """
        remote = (type_config or {}).get("remote", {}) or {}
        host = str(remote.get("host") or "").strip()
        user = str(remote.get("user") or "").strip()
        script = str(remote.get("script") or "").strip()
        password = str(remote.get("password") or "").strip()
        if not host or not user or not script:
            logger.warning("remote_summary 模式缺少 host/user/script 配置")
            raise ValueError("remote_summary 模式缺少 host/user/script 配置")

        port = int(remote.get("port") or 22)
        timeout_seconds = int(remote.get("timeout_seconds") or 7200)
        workdir = str(remote.get("workdir") or "").strip()
        env_map = remote.get("env", {}) or {}
        if not isinstance(env_map, dict):
            env_map = {}

        command = RemoteAcceptanceService._build_remote_command(
            script=script,
            workdir=workdir,
            env_map=env_map,
        )
        started_at = time.time()
        stdout_text, stderr_text, exit_status = RemoteAcceptanceService._run_ssh_command(
            host=host,
            port=port,
            user=user,
            password=password,
            command=command,
            timeout_seconds=timeout_seconds,
        )
        payload = RemoteAcceptanceService._extract_json_payload(stdout_text=stdout_text)
        payload["remote_command"] = command
        payload["remote_stderr"] = stderr_text.strip()
        payload["remote_duration_seconds"] = round(time.time() - started_at, 3)
        payload["remote_exit_status"] = exit_status
        return payload

    @staticmethod
    def _build_remote_command(script: str, workdir: str, env_map: dict[str, Any]) -> str:
        """构建远端执行命令。

        Args:
            script: 远端脚本路径或命令。
            workdir: 工作目录。
            env_map: 环境变量字典。

        Returns:
            可在远端 shell 中执行的命令字符串。
        """
        env_pairs: list[str] = []
        for key, value in env_map.items():
            escaped_value = str(value).replace("'", "'\"'\"'")
            env_pairs.append(f"{key}='{escaped_value}'")
        env_prefix = " ".join(env_pairs)
        command_parts = []
        if workdir:
            command_parts.append(f"cd {workdir}")
        script_command = script if script.startswith("bash ") else f"bash {script}"
        if env_prefix:
            command_parts.append(f"{env_prefix} {script_command}")
        else:
            command_parts.append(script_command)
        return " && ".join(command_parts)

    @staticmethod
    def _run_ssh_command(
        host: str,
        port: int,
        user: str,
        password: str,
        command: str,
        timeout_seconds: int,
    ) -> tuple[str, str, int]:
        """执行 SSH 命令并返回输出。

        Args:
            host: 远端主机。
            port: SSH 端口。
            user: 用户名。
            password: 密码。
            command: 待执行命令。
            timeout_seconds: 超时时间。

        Returns:
            `(stdout, stderr, exit_status)` 元组。
        """
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            connect_kwargs: dict[str, Any] = {
                "hostname": host,
                "port": port,
                "username": user,
                "timeout": 20,
                # 这里目前会寻找本机公钥
                # "look_for_keys": False,
                # "allow_agent": False,
            }
            if password:
                connect_kwargs["password"] = password
            client.connect(**connect_kwargs)

            stdin, stdout, stderr = client.exec_command(command, timeout=timeout_seconds)
            stdout_text = stdout.read().decode("utf-8", errors="ignore")
            stderr_text = stderr.read().decode("utf-8", errors="ignore")
            exit_status = int(stdout.channel.recv_exit_status())
            return stdout_text, stderr_text, exit_status
        finally:
            client.close()

    @staticmethod
    def _extract_json_payload(stdout_text: str) -> dict[str, Any]:
        """从 stdout 中提取 JSON。

        Args:
            stdout_text: 远端标准输出文本。

        Returns:
            JSON 字典。
        """
        lines = stdout_text.splitlines()
        start_index = None
        for index, line in enumerate(lines):
            if line.strip().startswith("{"):
                start_index = index
                break
        if start_index is None:
            logger.error("远程脚本未输出 JSON 结果, stdout 前 500 字符: %s", stdout_text[:500])
            raise ValueError("远程脚本未输出 JSON 结果")
        json_text = "\n".join(lines[start_index:]).strip()
        payload = json.loads(json_text)
        if not isinstance(payload, dict):
            logger.error("远程脚本 JSON 结果格式非法, 实际类型: %s", type(payload).__name__)
            raise ValueError("远程脚本 JSON 结果格式非法")
        return payload


remote_acceptance_service = RemoteAcceptanceService()
