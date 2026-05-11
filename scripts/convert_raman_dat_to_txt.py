"""将 Raman `.dat` 文件转换为两列 `.txt` 文件。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.lab_collect_service import LabCollectService


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns:
        命令行参数解析器。
    """
    parser = argparse.ArgumentParser(
        description="将 Raman DAT 文件转换为仅包含 RamanShift 和 Value 两列的 TXT 文件。",
    )
    parser.add_argument(
        "input_path",
        help="输入 DAT 文件路径，或包含 DAT 文件的目录路径。",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default="",
        help="输出目录；未指定时默认输出到源文件同级目录。",
    )
    parser.add_argument(
        "--pattern",
        default="*.dat",
        help="目录模式下的文件匹配规则，默认 `*.dat`。",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="目录模式下是否递归扫描子目录。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="若目标 TXT 已存在，是否覆盖。",
    )
    parser.add_argument(
        "--print-meta",
        action="store_true",
        help="是否打印每个文件提取出的采集元数据。",
    )
    return parser


def iter_dat_files(input_path: Path, pattern: str, recursive: bool) -> list[Path]:
    """收集待转换的 DAT 文件列表。

    Args:
        input_path: 输入文件或目录路径。
        pattern: 目录扫描的匹配规则。
        recursive: 是否递归扫描子目录。

    Returns:
        待转换的 DAT 文件路径列表。
    """
    if input_path.is_file():
        return [input_path]
    if not input_path.exists() or not input_path.is_dir():
        raise FileNotFoundError(f"输入路径不存在或不是有效目录: {input_path}")

    iterator = input_path.rglob(pattern) if recursive else input_path.glob(pattern)
    return sorted(path for path in iterator if path.is_file())


def build_output_path(source_path: Path, input_root: Path, output_dir: Path | None) -> Path:
    """构建目标 TXT 输出路径。

    Args:
        source_path: 源 DAT 文件路径。
        input_root: 输入根路径，用于目录模式下保留相对结构。
        output_dir: 输出根目录；为空时写回源文件同级目录。

    Returns:
        目标 TXT 文件路径。
    """
    if output_dir is None:
        return source_path.with_suffix(".txt")

    if input_root.is_file():
        return output_dir / f"{source_path.stem}.txt"

    relative_parent = source_path.relative_to(input_root).parent
    return output_dir / relative_parent / f"{source_path.stem}.txt"


def convert_single_file(source_path: Path, target_path: Path, force: bool) -> dict[str, object]:
    """转换单个 Raman DAT 文件。

    Args:
        source_path: 源 DAT 文件路径。
        target_path: 目标 TXT 文件路径。
        force: 是否允许覆盖既有目标文件。

    Returns:
        转换后提取的采集元数据。
    """
    if source_path.suffix.lower() != ".dat":
        raise ValueError(f"仅支持转换 .dat 文件: {source_path}")
    if target_path.exists() and not force:
        raise FileExistsError(f"目标文件已存在，请使用 --force 覆盖: {target_path}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    return LabCollectService._convert_raman_dat_to_txt(source_path=source_path, target_path=target_path)


def main() -> int:
    """执行脚本主流程。

    Returns:
        进程退出码。
    """
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input_path).expanduser()
    output_dir = Path(args.output_dir).expanduser() if str(args.output_dir).strip() else None
    dat_files = iter_dat_files(
        input_path=input_path,
        pattern=str(args.pattern),
        recursive=bool(args.recursive),
    )
    if not dat_files:
        print("未找到可转换的 DAT 文件。")
        return 1

    success_count = 0
    for source_path in dat_files:
        target_path = build_output_path(
            source_path=source_path,
            input_root=input_path,
            output_dir=output_dir,
        )
        sample_meta = convert_single_file(
            source_path=source_path,
            target_path=target_path,
            force=bool(args.force),
        )
        success_count += 1
        print(f"[OK] {source_path} -> {target_path}")
        if args.print_meta:
            print(json.dumps(sample_meta, ensure_ascii=False, indent=2))

    print(f"转换完成，共成功处理 {success_count} 个文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
