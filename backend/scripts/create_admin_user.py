"""创建管理员账号脚本。"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.infra.repositories import UserRepository
from app.schemas.identity_runtime import UserRecord
from app.services.auth_service import AuthService
from app.services.auth_service import ensure_identity_indexes


def build_cli_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns:
        管理员创建脚本的参数解析器。
    """
    parser = argparse.ArgumentParser(description="创建管理员账号。")
    parser.add_argument(
        "--username",
        required=True,
        help="管理员用户名。",
    )
    parser.add_argument(
        "--password",
        default="",
        help="管理员密码；未提供时将进入交互式输入。",
    )
    return parser


def resolve_password(password: str) -> str:
    """解析管理员密码。

    Args:
        password: 命令行传入的原始密码。

    Returns:
        可用于创建管理员账号的明文密码。

    Raises:
        ValueError: 密码为空、两次输入不一致，或非交互环境下未显式提供密码。
    """
    normalized_password = str(password or "").strip()
    if normalized_password:
        return normalized_password
    if not sys.stdin.isatty():
        raise ValueError("非交互环境下必须通过 --password 显式提供管理员密码")

    first_input = getpass.getpass("请输入管理员密码: ").strip()
    second_input = getpass.getpass("请再次输入管理员密码: ").strip()
    if not first_input:
        raise ValueError("管理员密码不能为空")
    if first_input != second_input:
        raise ValueError("两次输入的管理员密码不一致")
    return first_input


def create_admin_user(username: str, password: str) -> UserRecord:
    """创建管理员用户。

    Args:
        username: 管理员用户名。
        password: 管理员明文密码。

    Returns:
        新创建的管理员用户记录。

    Raises:
        ValueError: 用户名或密码不合法，或用户名已存在。
    """
    normalized_username = str(username or "").strip()
    if not normalized_username:
        raise ValueError("管理员用户名不能为空")
    if UserRepository.find_by_username(normalized_username):
        raise ValueError(f"用户名已存在: {normalized_username}")

    now = datetime.now()
    user_record = UserRecord(
        user_id=f"u_{uuid4().hex[:12]}",
        username=normalized_username,
        password_hash=AuthService.hash_password(password),
        role="admin",
        status="active",
        created_at=now,
        updated_at=now,
        last_login_at=None,
        created_by=None,
    )
    UserRepository.save(user_record)
    return user_record


def main() -> int:
    """执行管理员创建脚本。

    Returns:
        进程退出码。
    """
    args = build_cli_parser().parse_args()
    try:
        ensure_identity_indexes()
        password = resolve_password(args.password)
        user = create_admin_user(username=args.username, password=password)
    except ValueError as exc:
        print(f"创建管理员失败: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"创建管理员失败: {exc}", file=sys.stderr)
        return 1

    print(f"管理员创建成功: username={user.username}, user_id={user.user_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
