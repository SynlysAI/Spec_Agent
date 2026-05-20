"""执行 NMR 设备重复性评测并输出 Markdown 报告。"""

from __future__ import annotations

import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.consistency_service import consistency_service  # noqa: E402
from app.services.consistency_nmr_service import run_nmr_consistency  # noqa: E402


def main() -> None:
    """执行 NMR 一致性评测脚本。"""
    config = consistency_service._load_config()  # noqa: SLF001
    device_config = (config.get("devices", {}) or {}).get("nmr", {}) or {}
    data_path = str(device_config.get("data_path") or "").strip()
    output_dir = CURRENT_DIR / "reports"
    result = run_nmr_consistency(data_path=data_path, output_dir=output_dir)
    print(result.text_report)
    if result.artifacts:
        print(f"\n报告已保存: {output_dir / 'nmr_consistency_report.md'}")


if __name__ == "__main__":
    main()
