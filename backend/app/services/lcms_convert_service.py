"""LCMS 数据转化服务。"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from uuid import uuid4

import pandas as pd

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.lcms_convert import LcmsConvertLabelPeak, LcmsConvertResultData


logger = get_logger("spec_agent.service.lcms_convert")


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
    def find_msconvert() -> str:
        """查找可用的 msconvert.exe。"""
        candidate = shutil.which("msconvert")
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

        raise RuntimeError("未找到 msconvert.exe，请先安装 ProteoWizard。")

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
    def convert_raw_to_mzml(cls, raw_dir: Path, msconvert: str, temp_root: Path, alias: str) -> Path:
        """将单个 Waters 目录转换为临时 mzML 文件。"""
        execution_raw = raw_dir if cls.is_ascii_only(raw_dir) else cls.build_safe_ascii_copy(raw_dir, temp_root, alias)
        mzml_path = temp_root / f"{alias}.mzML"

        cmd = [
            msconvert,
            str(execution_raw),
            "--mzML",
            "--outdir",
            str(temp_root),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(f"msconvert 执行失败：{stderr or '未知错误'}") from exc

        generated = temp_root / f"{execution_raw.stem}.mzML"
        if generated.exists() and generated != mzml_path:
            if mzml_path.exists():
                mzml_path.unlink()
            generated.rename(mzml_path)

        if not mzml_path.exists():
            raise RuntimeError(f"未生成 mzML 文件：{mzml_path}")
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

        with tempfile.TemporaryDirectory(prefix="spec_agent_lcms_convert_") as temp_dir_name:
            temp_root = Path(temp_dir_name)
            extracted_root = self.extract_zip_to_temp(zip_bytes=zip_bytes, temp_root=temp_root)
            waters_dir = self.locate_waters_directory(extracted_root=extracted_root)
            msconvert = self.find_msconvert()
            mzml_path = self.convert_raw_to_mzml(
                raw_dir=waters_dir,
                msconvert=msconvert,
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
            "LCMS 数据转化完成: job_id=%s source_name=%s point_count=%s",
            job_id,
            source_name,
            len(apex_mzs),
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
