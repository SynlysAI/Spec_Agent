"""对象存储路径解析与读取服务。"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("spec_agent.services.object_storage")

SPECTRUM_TYPE_ROOTS = {"nmr", "gpc", "ir", "raman", "lcms"}


@dataclass(frozen=True)
class ObjectStorageRef:
    """对象存储引用。"""

    bucket: str
    object_key: str


class ObjectStorageService:
    """统一处理谱图对象存储路径。"""

    @staticmethod
    def build_uri(ref: ObjectStorageRef) -> str:
        """构建对象存储 URI。

        Args:
            ref: 对象存储引用。

        Returns:
            `minio://bucket/key` 格式 URI。
        """
        return f"minio://{ref.bucket}/{ref.object_key}"

    def build_public_url(self, ref: ObjectStorageRef) -> str:
        """构建对象公开访问 URL。

        Args:
            ref: 对象存储引用。

        Returns:
            基于 `MINIO_PUBLIC_BASE_URL` 的对象 URL。
        """
        if not settings.minio_public_base_url:
            return ""
        object_key = quote(ref.object_key, safe="/")
        return f"{settings.minio_public_base_url}/{ref.bucket}/{object_key}"

    def build_uri_for_path(self, raw_path: str | Path | None) -> str | None:
        """把本地谱图路径转换为对象存储 URI。

        Args:
            raw_path: 本地路径、对象 URI 或对象 URL。

        Returns:
            可转换时返回对象 URI，否则返回 None。
        """
        ref = self.resolve_reference(raw_path)
        return self.build_uri(ref) if ref else None

    def resolve_reference(self, raw_path: str | Path | None) -> ObjectStorageRef | None:
        """解析对象存储引用。

        Args:
            raw_path: 本地路径、对象 URI 或对象 URL。

        Returns:
            对象存储引用；无法解析时返回 None。
        """
        value = str(raw_path or "").strip().strip('"').strip("'")
        if not value or not settings.minio_bucket:
            return None

        parsed = urlparse(value)
        if parsed.scheme in {"minio", "s3"}:
            key = unquote(parsed.path.lstrip("/"))
            if parsed.netloc and key:
                return ObjectStorageRef(bucket=parsed.netloc, object_key=key)
            return None
        if parsed.scheme in {"http", "https"}:
            return self._resolve_http_reference(parsed_path=parsed.path)

        object_key = self._build_object_key_from_path(value)
        if object_key:
            return ObjectStorageRef(bucket=settings.minio_bucket, object_key=object_key)
        return None

    def read_bytes(self, ref: ObjectStorageRef) -> bytes:
        """读取对象内容。

        Args:
            ref: 对象存储引用。

        Returns:
            对象二进制内容。
        """
        if settings.minio_access_key and settings.minio_secret_key:
            return self._read_bytes_with_sdk(ref=ref)
        url = self.build_public_url(ref)
        if not url:
            raise ValueError("未配置 MINIO_PUBLIC_BASE_URL，无法读取对象")
        response = requests.get(url, timeout=60)
        if response.status_code == 404:
            raise ValueError(f"MinIO 对象不存在: {self.build_uri(ref)}")
        response.raise_for_status()
        return response.content

    def download_prefix_to_dir(self, ref: ObjectStorageRef, target_dir: Path) -> list[Path]:
        """下载对象前缀下的所有文件到指定目录。

        Args:
            ref: 对象存储目录引用。
            target_dir: 下载目标目录。

        Returns:
            已下载文件路径列表。
        """
        client = self._create_minio_client()
        prefix = ref.object_key.strip("/")
        prefix = f"{prefix}/" if prefix else ""
        downloaded: list[Path] = []

        objects = client.list_objects(ref.bucket, prefix=prefix, recursive=True)
        for item in objects:
            object_name = str(item.object_name or "")
            if not object_name or object_name.endswith("/"):
                continue
            relative_name = object_name[len(prefix):] if object_name.startswith(prefix) else Path(object_name).name
            target_path = target_dir / relative_name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            response = client.get_object(ref.bucket, object_name)
            try:
                target_path.write_bytes(response.read())
            finally:
                response.close()
                response.release_conn()
            downloaded.append(target_path)

        if not downloaded:
            raise ValueError(f"MinIO 前缀下未找到文件: {self.build_uri(ref)}")
        return downloaded

    def sync_spectrum_file(self, *, local_root: Path, local_path: Path, spectrum_type: str) -> ObjectStorageRef:
        """将单个谱图文件同步到对象存储。

        Args:
            local_root: 采集配置中的本地类型根目录。
            local_path: 待同步文件路径。
            spectrum_type: 谱图类型。

        Returns:
            已同步文件对应的对象存储引用。
        """
        ref = self.build_spectrum_object_ref(
            local_root=local_root,
            local_path=local_path,
            spectrum_type=spectrum_type,
        )
        client = self._create_minio_client()
        content_type, _ = mimetypes.guess_type(str(local_path))
        client.fput_object(
            ref.bucket,
            ref.object_key,
            str(local_path),
            content_type=content_type or "application/octet-stream",
        )
        return ref

    def sync_spectrum_files(
        self,
        *,
        local_root: Path,
        local_files: list[Path],
        spectrum_type: str,
    ) -> list[ObjectStorageRef]:
        """将一组谱图文件同步到对象存储。

        Args:
            local_root: 采集配置中的本地类型根目录。
            local_files: 待同步的文件列表。
            spectrum_type: 谱图类型。

        Returns:
            已同步文件对应的对象存储引用列表。
        """
        refs: list[ObjectStorageRef] = []
        for local_file in local_files:
            if not local_file.exists() or not local_file.is_file():
                continue
            refs.append(
                self.sync_spectrum_file(
                    local_root=local_root,
                    local_path=local_file,
                    spectrum_type=spectrum_type,
                )
            )
        return refs

    def build_spectrum_object_ref(
        self,
        *,
        local_root: Path,
        local_path: Path,
        spectrum_type: str,
    ) -> ObjectStorageRef:
        """按采集目录结构构建对象存储引用。

        Args:
            local_root: 采集配置中的本地类型根目录。
            local_path: 本地文件或目录路径。
            spectrum_type: 谱图类型。

        Returns:
            对象存储引用。
        """
        try:
            relative_path = local_path.relative_to(local_root).as_posix().strip("/")
        except ValueError as exc:
            logger.warning("本地路径不在采集根目录下: local_root=%s, local_path=%s", local_root, local_path)
            raise ValueError(f"本地路径不在采集根目录下: {local_path}") from exc
        object_key = f"{spectrum_type}/spectrum/{relative_path}" if relative_path else f"{spectrum_type}/spectrum"
        object_key = self._apply_object_prefix(object_key)
        return ObjectStorageRef(bucket=settings.minio_bucket, object_key=object_key)

    def to_record_fields(self, raw_path: str | Path | None) -> dict[str, str]:
        """生成可写入数据库的对象存储字段。

        Args:
            raw_path: 本地路径、对象 URI 或对象 URL。

        Returns:
            对象存储字段字典；无法解析时返回空字典。
        """
        ref = self.resolve_reference(raw_path)
        if not ref:
            return {}
        fields = {
            "object_bucket": ref.bucket,
            "object_key": ref.object_key,
            "object_uri": self.build_uri(ref),
        }
        public_url = self.build_public_url(ref)
        if public_url:
            fields["object_url"] = public_url
        return fields

    @staticmethod
    def _create_minio_client():
        """创建 MinIO SDK 客户端。"""
        if not settings.minio_access_key or not settings.minio_secret_key:
            raise ValueError("目录对象读取需要配置 MINIO_ACCESS_KEY 和 MINIO_SECRET_KEY")
        try:
            from minio import Minio
        except ImportError as exc:
            raise ValueError("缺少 minio 依赖，请安装 backend/requirements.txt 中的 minio 包") from exc

        endpoint = settings.minio_endpoint
        endpoint = endpoint.replace("http://", "").replace("https://", "").strip("/")
        return Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def _read_bytes_with_sdk(self, ref: ObjectStorageRef) -> bytes:
        """通过 MinIO SDK 读取对象。"""
        client = self._create_minio_client()
        response = client.get_object(ref.bucket, ref.object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def _resolve_http_reference(self, parsed_path: str) -> ObjectStorageRef | None:
        """从 HTTP URL 路径解析对象引用。"""
        path_parts = [unquote(part) for part in parsed_path.strip("/").split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] == settings.minio_bucket:
            return ObjectStorageRef(bucket=path_parts[0], object_key="/".join(path_parts[1:]))
        return None

    def _build_object_key_from_path(self, raw_path: str) -> str | None:
        """从历史本地路径推导 MinIO 对象键。"""
        normalized = self._normalize_path_text(raw_path)
        if not normalized:
            return None
        bucket_prefix = f"{settings.minio_bucket}/"
        if normalized.startswith(bucket_prefix):
            return self._apply_object_prefix(normalized[len(bucket_prefix):])

        for root in self._legacy_roots():
            if normalized.lower() == root.lower():
                return None
            if normalized.lower().startswith(f"{root.lower()}/"):
                return self._apply_object_prefix(normalized[len(root) + 1:])

        parts = [part for part in normalized.split("/") if part]
        for index, part in enumerate(parts):
            if part.lower() == "spectrum_files" and index + 1 < len(parts):
                return self._apply_object_prefix("/".join(parts[index + 1:]))
        if parts and parts[0].lower() in SPECTRUM_TYPE_ROOTS:
            return self._apply_object_prefix("/".join(parts))
        return None

    @staticmethod
    def _normalize_path_text(raw_path: str) -> str:
        """标准化路径分隔符和首尾空白。"""
        return str(raw_path or "").strip().replace("\\", "/").strip("/")

    def _legacy_roots(self) -> list[str]:
        """返回可识别的历史谱图根目录。"""
        roots = list(settings.spectrum_files_legacy_roots)
        roots.append(str(settings.spectrum_files_root))
        normalized_roots = []
        for root in roots:
            normalized = self._normalize_path_text(root)
            if normalized and normalized not in normalized_roots:
                normalized_roots.append(normalized)
        return normalized_roots

    @staticmethod
    def _apply_object_prefix(object_key: str) -> str:
        """套用对象存储前缀配置。"""
        key = object_key.strip("/")
        prefix = settings.spectrum_files_object_prefix
        if not prefix:
            return key
        if key == prefix or key.startswith(f"{prefix}/"):
            return key
        return f"{prefix}/{key}"


object_storage_service = ObjectStorageService()
