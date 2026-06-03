"""LCMS 数据转化服务。"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pandas as pd

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.lcms_convert import LcmsConvertLabelPeak, LcmsConvertResultData


logger = get_logger("spec_agent.service.lcms_convert")


@dataclass(frozen=True)
class MsconvertRuntime:
    """描述 LCMS 转换所使用的 msconvert 执行方式。"""

    kind: str
    command: str


class LcmsConvertService:
    """LCMS 数据转化服务。"""

    FILTER_MIN_RELATIVE_INTENSITY = 0.10
    MS_LABEL_MAX_COUNT = 8
    MS_LABEL_MIN_RELATIVE_INTENSITY = 0.10
    MS_LABEL_MIN_MZ_SPACING = 8.0
    WATER_SENTINEL_FILES = ("_header.txt", "_extern.inf", "_functns.inf", "_chroms.inf")

    @staticmethod
    def _load_mzml_reader():
        """按需加载 pyteomics.mzml 读取器。"""
        try:
            mzml_module = importlib.import_module("pyteomics.mzml")
        except ModuleNotFoundError as exc:
            raise RuntimeError("未检测到 pyteomics，请先在后端环境中安装该依赖。") from exc
        return mzml_module

    @staticmethod
    def _normalize_msconvert_mode() -> str:
        """返回归一化后的 msconvert 执行模式。"""
        mode = str(settings.lcms_msconvert_mode or "auto").strip().lower()
        if mode not in {"auto", "binary", "docker"}:
            raise RuntimeError("LCMS_MSCONVERT_MODE 仅支持 auto、binary 或 docker。")
        return mode

    @staticmethod
    def find_msconvert_binary() -> str | None:
        """查找本机可执行的 msconvert 程序。"""
        configured = str(settings.lcms_msconvert_path or "").strip()
        if configured:
            configured_path = Path(configured).expanduser()
            if configured_path.exists():
                return str(configured_path)

            configured_candidate = shutil.which(configured)
            if configured_candidate:
                return configured_candidate

            raise RuntimeError("LCMS_MSCONVERT_PATH 指定的 msconvert 不存在或不可执行。")

        candidate = shutil.which("msconvert") or shutil.which("msconvert.exe")
        if candidate:
            return candidate

        common_paths = [
            Path(r"C:\Program Files\ProteoWizard\msconvert.exe"),
            Path(r"C:\Program Files (x86)\ProteoWizard\msconvert.exe"),
            Path(r"D:\Program Files\ProteoWizard\msconvert.exe"),
        ]
        for path in common_paths:
            if path.exists():
                return str(path)

        for base in [
            Path(r"C:\Program Files\ProteoWizard"),
            Path(r"C:\Program Files (x86)\ProteoWizard"),
            Path(r"D:\Program Files\ProteoWizard"),
        ]:
            if not base.exists():
                continue
            matches = sorted(base.rglob("msconvert.exe"))
            if matches:
                return str(matches[-1])

        return None

    @staticmethod
    def find_docker_binary() -> str | None:
        """查找可用的 Docker 命令。"""
        docker_bin = str(settings.lcms_msconvert_docker_bin or "docker").strip() or "docker"
        return shutil.which(docker_bin)

    @classmethod
    def validate_docker_runtime(cls) -> None:
        """校验 Docker 模式所需的基础配置。"""
        if not str(settings.lcms_msconvert_docker_image or "").strip():
            raise RuntimeError("LCMS_MSCONVERT_DOCKER_IMAGE 不能为空。")

        shared_root = settings.lcms_msconvert_shared_root
        if settings.app_env == "docker" and shared_root is None:
            raise RuntimeError(
                "当前后端运行在 Docker 容器内；启用 LCMS_MSCONVERT_MODE=docker 时，"
                "需额外设置 LCMS_MSCONVERT_SHARED_ROOT 为宿主机与后端容器共享的绝对路径。"
            )

        if settings.app_env == "docker" and shared_root is not None and not shared_root.is_absolute():
            raise RuntimeError("Docker 容器部署下，LCMS_MSCONVERT_SHARED_ROOT 必须为绝对路径。")

    @classmethod
    def resolve_msconvert_runtime(cls) -> MsconvertRuntime:
        """解析当前应使用的 msconvert 执行方式。"""
        mode = cls._normalize_msconvert_mode()

        if mode in {"auto", "binary"}:
            binary = cls.find_msconvert_binary()
            if binary:
                return MsconvertRuntime(kind="binary", command=binary)
            if mode == "binary":
                raise RuntimeError("未找到 msconvert，请先安装 ProteoWizard 或设置 LCMS_MSCONVERT_PATH。")

        if mode in {"auto", "docker"}:
            docker_bin = cls.find_docker_binary()
            if docker_bin:
                cls.validate_docker_runtime()
                return MsconvertRuntime(kind="docker", command=docker_bin)
            if mode == "docker":
                raise RuntimeError(
                    "未找到 Docker 命令，请先安装 Docker 或设置 LCMS_MSCONVERT_DOCKER_BIN。"
                )

        raise RuntimeError(
            "未找到可用的 msconvert 执行方式。"
            "请安装 ProteoWizard，或启用 Docker 并设置 LCMS_MSCONVERT_MODE=docker。"
        )

    @classmethod
    def resolve_shared_temp_root(cls) -> Path | None:
        """解析 LCMS 转换所使用的共享临时目录根路径。"""
        shared_root = settings.lcms_msconvert_shared_root
        if shared_root is None:
            return None

        resolved_root = shared_root.expanduser()
        if not resolved_root.is_absolute():
            resolved_root = (settings.project_root / resolved_root).resolve()
        resolved_root.mkdir(parents=True, exist_ok=True)
        return resolved_root

    @classmethod
    def create_temp_directory(cls) -> tempfile.TemporaryDirectory:
        """创建本次 LCMS 转换所使用的临时工作目录。"""
        shared_root = cls.resolve_shared_temp_root()
        if shared_root is None:
            return tempfile.TemporaryDirectory(prefix="spec_agent_lcms_convert_")
        return tempfile.TemporaryDirectory(prefix="spec_agent_lcms_convert_", dir=str(shared_root))

    @staticmethod
    def format_command_for_log(command: list[str]) -> str:
        """格式化命令参数，便于写入日志。"""
        return subprocess.list2cmdline([str(item) for item in command])

    @staticmethod
    def is_ascii_only(path: Path) -> bool:
        """判断路径是否仅包含 ASCII 字符。"""
        try:
            str(path).encode("ascii")
            return True
        except UnicodeEncodeError:
            return False

    @staticmethod
    def build_safe_ascii_copy(raw_dir: Path, temp_root: Path, alias: str) -> Path:
        """复制原始目录到 ASCII 安全临时路径。"""
        safe_dir = temp_root / f"{alias}.raw"
        if safe_dir.exists():
            shutil.rmtree(safe_dir)
        shutil.copytree(raw_dir, safe_dir)
        return safe_dir

    @staticmethod
    def _ensure_zip_safe(zip_file: zipfile.ZipFile, extract_root: Path) -> None:
        """校验 zip 解压目标路径，避免目录穿越。"""
        for member in zip_file.infolist():
            member_path = (extract_root / member.filename).resolve()
            if extract_root.resolve() not in member_path.parents and member_path != extract_root.resolve():
                raise ValueError("zip 文件包含非法路径，无法解压。")

    @classmethod
    def extract_zip_to_temp(cls, zip_bytes: bytes, temp_root: Path) -> Path:
        """解压上传 zip 到临时目录。"""
        extract_root = temp_root / "unzipped"
        extract_root.mkdir(parents=True, exist_ok=True)

        zip_path = temp_root / "upload.zip"
        zip_path.write_bytes(zip_bytes)

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_file:
                cls._ensure_zip_safe(zip_file, extract_root)
                zip_file.extractall(extract_root)
        except zipfile.BadZipFile as exc:
            raise ValueError("上传文件不是有效的 zip 压缩包。") from exc

        if not any(extract_root.iterdir()):
            raise ValueError("zip 解压后内容为空。")
        return extract_root

    @classmethod
    def _is_waters_directory(cls, directory: Path) -> bool:
        """判断目录是否像 Waters 原始数据目录。"""
        if not directory.is_dir():
            return False

        file_names = {item.name.lower() for item in directory.iterdir() if item.is_file()}
        sentinel_hits = sum(1 for item in cls.WATER_SENTINEL_FILES if item in file_names)
        has_func_dat = any(name.startswith("_func") and name.endswith(".dat") for name in file_names)
        has_func_idx = any(name.startswith("_func") and name.endswith(".idx") for name in file_names)
        has_chro_dat = any(name.startswith("_chro") and name.endswith(".dat") for name in file_names)

        if directory.name.lower().endswith(".raw") and (has_func_dat or has_chro_dat):
            return True
        return sentinel_hits >= 2 and has_func_dat and has_func_idx

    @classmethod
    def locate_waters_directory(cls, extracted_root: Path) -> Path:
        """在解压目录中定位目标 Waters 原始数据目录。"""
        candidates: list[Path] = []
        if cls._is_waters_directory(extracted_root):
            candidates.append(extracted_root)

        for path in extracted_root.rglob("*"):
            if cls._is_waters_directory(path):
                candidates.append(path)

        if not candidates:
            raise ValueError("解压后未识别到有效的 Waters 数据目录。")

        unique_candidates = sorted(
            {item.resolve() for item in candidates},
            key=lambda item: (len(item.parts), str(item).lower()),
        )
        return unique_candidates[0]

    @classmethod
    def build_msconvert_command(
        cls,
        runtime: MsconvertRuntime,
        execution_raw: Path,
        temp_root: Path,
    ) -> list[str]:
        """构建 msconvert 执行命令。

        Args:
            runtime: 当前解析出的 msconvert 执行方式。
            execution_raw: 本次实际传给 msconvert 的原始数据目录。
            temp_root: 当前转换任务的临时工作目录。

        Returns:
            可直接传给 subprocess.run 的命令参数列表。
        """
        if runtime.kind == "binary":
            command = [
                runtime.command,
                str(execution_raw),
                "--mzML",
                "--outdir",
                str(temp_root),
            ]
            logger.info(
                "LCMS 本机 msconvert 路径映射: input=%s outdir=%s",
                execution_raw,
                temp_root,
            )
            return command

        if runtime.kind == "docker":
            docker_work_root = "/work"
            docker_outdir = r"Z:\work"
            try:
                relative_input = execution_raw.resolve().relative_to(temp_root.resolve())
            except ValueError as exc:
                raise RuntimeError("Docker 模式下 msconvert 输入目录不在临时工作目录内。") from exc
            docker_input = fr"Z:\work\{str(relative_input).replace('/', '\\')}"
            command = [
                runtime.command,
                "run",
                "--rm",
                "-v",
                f"{temp_root.resolve()}:{docker_work_root}",
                settings.lcms_msconvert_docker_image,
                "wine",
                "msconvert",
                docker_input,
                "--mzML",
                "--outdir",
                docker_outdir,
            ]
            logger.info(
                "LCMS Docker 路径映射: host_temp_root=%s container_work_root=%s wine_input=%s wine_outdir=%s",
                temp_root.resolve(),
                docker_work_root,
                docker_input,
                docker_outdir,
            )
            return command

        raise RuntimeError(f"不支持的 msconvert 执行模式：{runtime.kind}")

    @classmethod
    def convert_raw_to_mzml(
        cls,
        raw_dir: Path,
        runtime: MsconvertRuntime,
        temp_root: Path,
        alias: str,
    ) -> Path:
        """将单个 Waters 目录转换为临时 mzML 文件。

        Args:
            raw_dir: 识别出的 Waters 原始数据目录。
            runtime: 当前解析出的 msconvert 执行方式。
            temp_root: 当前转换任务的临时工作目录。
            alias: 生成临时文件时使用的 ASCII 安全别名。

        Returns:
            转换完成后的 mzML 文件路径。
        """
        execution_raw = raw_dir if cls.is_ascii_only(raw_dir) else cls.build_safe_ascii_copy(raw_dir, temp_root, alias)
        mzml_path = temp_root / f"{alias}.mzML"
        logger.info(
            "LCMS 开始执行 msconvert: runtime=%s raw_dir=%s execution_raw=%s temp_root=%s ascii_safe_copy=%s target_mzml=%s",
            runtime.kind,
            raw_dir,
            execution_raw,
            temp_root,
            execution_raw != raw_dir,
            mzml_path,
        )

        cmd = cls.build_msconvert_command(runtime=runtime, execution_raw=execution_raw, temp_root=temp_root)
        try:
            logger.info("LCMS msconvert 执行命令: %s", cls.format_command_for_log(cmd))
            completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
            stdout = (completed.stdout or "").strip()
            if stdout:
                logger.info("LCMS msconvert 标准输出: %s", stdout)
        except subprocess.CalledProcessError as exc:
            stdout = (exc.stdout or "").strip()
            stderr = (exc.stderr or exc.stdout or "").strip()
            logger.error(
                "LCMS msconvert 执行失败: runtime=%s command=%s stdout=%s stderr=%s",
                runtime.kind,
                cls.format_command_for_log(cmd),
                stdout or "-",
                stderr or "-",
            )
            raise RuntimeError(
                f"msconvert 执行失败（{runtime.kind}）：{stderr or '未知错误'}"
            ) from exc

        generated = temp_root / f"{execution_raw.stem}.mzML"
        if generated.exists() and generated != mzml_path:
            if mzml_path.exists():
                mzml_path.unlink()
            generated.rename(mzml_path)

        if not mzml_path.exists():
            raise RuntimeError(f"未生成 mzML 文件：{mzml_path}")
        logger.info("LCMS msconvert 输出文件已就绪: generated=%s final=%s", generated, mzml_path)
        return mzml_path

    @staticmethod
    def extract_scan_time(spec: dict) -> float | None:
        """提取扫描时间，并统一为分钟。"""
        scans = spec.get("scanList", {}).get("scan", [])
        if not scans:
            return None
        rt = scans[0].get("scan start time")
        if rt is None:
            return None
        unit = str(scans[0].get("unitName", "minute")).lower()
        rt_value = float(rt)
        return rt_value / 60.0 if "second" in unit else rt_value

    @classmethod
    def iter_ms1_trace_and_apex(
        cls,
        mzml_path: Path,
    ) -> tuple[list[float], list[float], float, float, list[float], list[float]]:
        """遍历 mzML 中的 MS1 扫描，并返回 RT 曲线与 apex 谱图。"""
        rt_x_values: list[float] = []
        rt_y_values: list[float] = []
        apex_rt: float | None = None
        apex_tic = -1.0
        apex_mzs: list[float] | None = None
        apex_intensities: list[float] | None = None

        mzml_module = cls._load_mzml_reader()
        with mzml_module.read(str(mzml_path)) as reader:
            for spec in reader:
                if spec.get("ms level") != 1:
                    continue
                rt = cls.extract_scan_time(spec)
                if rt is None:
                    continue

                mzs = [float(value) for value in spec.get("m/z array", [])]
                intensities = [float(value) for value in spec.get("intensity array", [])]
                tic = float(sum(intensities)) if intensities else 0.0

                rt_x_values.append(rt)
                rt_y_values.append(tic)

                if tic > apex_tic:
                    apex_tic = tic
                    apex_rt = rt
                    apex_mzs = mzs
                    apex_intensities = intensities

        if apex_rt is None or apex_mzs is None or apex_intensities is None:
            raise ValueError("未在文件中找到有效的 MS1 谱图。")

        return rt_x_values, rt_y_values, apex_rt, apex_tic, apex_mzs, apex_intensities

    @classmethod
    def filter_ms_peaks(cls, mzs: list[float], intensities: list[float]) -> tuple[list[float], list[float]]:
        """按相对强度阈值过滤 MS 峰。"""
        if not mzs or not intensities or len(mzs) != len(intensities):
            return [], []

        max_intensity = max(float(value) for value in intensities)
        if max_intensity <= 0:
            return [], []

        threshold = max_intensity * cls.FILTER_MIN_RELATIVE_INTENSITY
        filtered_pairs = [
            (float(mz), float(intensity))
            for mz, intensity in zip(mzs, intensities)
            if float(intensity) >= threshold
        ]
        return [item[0] for item in filtered_pairs], [item[1] for item in filtered_pairs]

    @classmethod
    def pick_label_peaks(cls, mzs: list[float], intensities: list[float]) -> list[LcmsConvertLabelPeak]:
        """选取用于前端标注的代表峰。"""
        if not mzs or not intensities or len(mzs) != len(intensities):
            return []

        max_intensity = max(float(value) for value in intensities)
        if max_intensity <= 0:
            return []

        threshold = max_intensity * cls.MS_LABEL_MIN_RELATIVE_INTENSITY
        candidate_indexes = [
            index
            for index, intensity in enumerate(intensities)
            if float(intensity) >= threshold
        ]
        candidate_indexes.sort(key=lambda index: float(intensities[index]), reverse=True)

        selected_indexes: list[int] = []
        for index in candidate_indexes:
            mz = float(mzs[index])
            if all(abs(mz - float(mzs[selected])) >= cls.MS_LABEL_MIN_MZ_SPACING for selected in selected_indexes):
                selected_indexes.append(index)
            if len(selected_indexes) >= cls.MS_LABEL_MAX_COUNT:
                break

        selected_indexes.sort(key=lambda index: float(mzs[index]))
        return [
            LcmsConvertLabelPeak(mz=float(mzs[index]), intensity=float(intensities[index]))
            for index in selected_indexes
        ]

    @staticmethod
    def save_csv(out_path: Path, mzs: list[float], intensities: list[float]) -> None:
        """保存转换后的两列 MS 峰表。"""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data_frame = pd.DataFrame({"m/z": mzs, "Intensity": intensities})
        data_frame.to_csv(out_path, index=False, encoding="utf-8-sig")

    @staticmethod
    def _sanitize_stem(name: str) -> str:
        """将源名称规整为适合文件名的 stem。"""
        sanitized = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in name)
        sanitized = sanitized.strip("_")
        return sanitized or "lcms_sample"

    @staticmethod
    def _build_job_id() -> str:
        """生成本次工具转换的任务 ID。"""
        return f"lcms_convert_{uuid4().hex[:12]}"

    @staticmethod
    def _build_output_dir(job_id: str) -> Path:
        """构建本次转换的输出目录。"""
        return settings.outputs_root / "lcms_convert" / job_id

    @classmethod
    def resolve_download_file(cls, job_id: str) -> Path:
        """根据任务 ID 定位下载文件。"""
        output_dir = cls._build_output_dir(job_id)
        if not output_dir.exists():
            raise FileNotFoundError("转换结果不存在。")
        csv_files = sorted(output_dir.glob("*.csv"))
        if not csv_files:
            raise FileNotFoundError("转换结果文件不存在。")
        return csv_files[0]

    def run_from_zip(self, zip_bytes: bytes, upload_name: str) -> LcmsConvertResultData:
        """从上传 zip 执行 LCMS 转换。"""
        if not zip_bytes:
            raise ValueError("上传文件内容为空。")

        job_id = self._build_job_id()
        output_dir = self._build_output_dir(job_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        runtime = self.resolve_msconvert_runtime()
        logger.info(
            "LCMS 数据转化任务开始: job_id=%s upload_name=%s output_dir=%s runtime_kind=%s runtime_command=%s",
            job_id,
            upload_name,
            output_dir,
            runtime.kind,
            runtime.command,
        )

        with self.create_temp_directory() as temp_dir_name:
            temp_root = Path(temp_dir_name).resolve()
            extracted_root = self.extract_zip_to_temp(zip_bytes=zip_bytes, temp_root=temp_root)
            waters_dir = self.locate_waters_directory(extracted_root=extracted_root)
            logger.info(
                "LCMS 数据转化临时目录信息: job_id=%s temp_root=%s extracted_root=%s waters_dir=%s",
                job_id,
                temp_root,
                extracted_root,
                waters_dir,
            )
            mzml_path = self.convert_raw_to_mzml(
                raw_dir=waters_dir,
                runtime=runtime,
                temp_root=temp_root,
                alias="single_sample",
            )
            rt_x_values, rt_y_values, apex_rt, apex_tic, apex_mzs, apex_intensities = self.iter_ms1_trace_and_apex(
                mzml_path=mzml_path
            )

        filtered_mzs, filtered_intensities = self.filter_ms_peaks(apex_mzs, apex_intensities)
        label_peaks = self.pick_label_peaks(apex_mzs, apex_intensities)
        source_name = waters_dir.name
        csv_name = f"{self._sanitize_stem(source_name)}_apex_ms1.csv"
        csv_path = output_dir / csv_name
        self.save_csv(csv_path, apex_mzs, apex_intensities)

        logger.info(
            "LCMS 数据转化完成: job_id=%s source_name=%s point_count=%s csv_path=%s",
            job_id,
            source_name,
            len(apex_mzs),
            csv_path,
        )

        return LcmsConvertResultData(
            job_id=job_id,
            source_name=source_name,
            apex_rt=float(apex_rt),
            apex_tic=float(apex_tic),
            rt_x_values=[float(value) for value in rt_x_values],
            rt_y_values=[float(value) for value in rt_y_values],
            ms_full_x_values=[float(value) for value in apex_mzs],
            ms_full_y_values=[float(value) for value in apex_intensities],
            ms_filtered_x_values=[float(value) for value in filtered_mzs],
            ms_filtered_y_values=[float(value) for value in filtered_intensities],
            label_peaks=label_peaks,
            point_count_full=len(apex_mzs),
            point_count_filtered=len(filtered_mzs),
            download_url=f"{settings.api_prefix}/tools/lcms-convert/download/{job_id}",
        )


lcms_convert_service = LcmsConvertService()
