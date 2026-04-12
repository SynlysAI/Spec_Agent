"""导出 OpenAPI 文档脚本。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app


def export_openapi(output_path: Path) -> Path:
    """导出 OpenAPI JSON 文件。

    Args:
        output_path: 输出文件路径。

    Returns:
        导出后的文件路径。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "openapi.json"
    path = export_openapi(target)
    print(f"openapi exported: {path}")
