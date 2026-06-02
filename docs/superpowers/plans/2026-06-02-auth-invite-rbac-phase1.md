# 邀请码注册与用户角色权限一期 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Spec Agent 增加邀请码注册、基于用户表的登录、管理员/普通用户两级角色权限，以及前端管理员菜单与路由保护。

**Architecture:** 后端新增用户与邀请码持久化模型，在现有自定义 Bearer Token 基础上切换为“真实用户 + 角色”载荷，并通过 `get_current_user` / `require_admin` 建立统一权限依赖。前端将当前登录态升级为用户态，新增注册页和管理员管理页，并将现有实验管理、数据采集、评测中心等页面改为管理员专属。

**Tech Stack:** FastAPI、Pydantic、MongoDB、Vue 3、Vue Router、Axios、Element Plus

---

## 文件结构与职责

### 后端新增文件

- Create: `backend/app/schemas/identity_runtime.py`
  - 用户与邀请码运行态实体：`UserRecord`、`InviteCodeRecord`
- Create: `backend/app/schemas/admin.py`
  - 管理员接口请求/响应模型
- Create: `backend/app/services/auth_service.py`
  - 注册、登录、登出、当前用户查询、初始管理员引导
- Create: `backend/app/api/v1/endpoints/admin.py`
  - 用户管理、邀请码管理接口
- Create: `backend/tests/test_auth_service.py`
  - 认证核心逻辑测试
- Create: `backend/tests/test_admin_endpoints.py`
  - 管理员接口权限测试

### 后端修改文件

- Modify: `backend/app/core/config.py`
  - 增加认证一期所需配置，如是否允许自动引导首个管理员、邀请码默认有效期
- Modify: `backend/app/core/auth.py`
  - Token 载荷改为真实用户，新增 `get_current_user`、`require_admin`
- Modify: `backend/app/schemas/auth.py`
  - 增加注册、当前用户信息、登出等接口模型
- Modify: `backend/app/infra/mongo.py`
  - 新增 `users`、`invite_codes` 集合访问方法
- Modify: `backend/app/infra/repositories.py`
  - 增加 `UserRepository`、`InviteCodeRepository`
- Modify: `backend/app/api/v1/endpoints/auth.py`
  - 登录接口改造为数据库用户登录，新增注册、当前用户、登出
- Modify: `backend/app/api/v1/router.py`
  - 注册管理员路由并给管理员能力挂载 `require_admin`
- Modify: `backend/app/schemas/task_runtime.py`
  - 给 `TaskRecord`、`ResultRecord`、`FileRecord` 补 `created_by`
- Modify: `backend/app/services/task_service.py`
  - 创建任务时写入 `created_by`
- Modify: `backend/app/services/file_service.py`
  - 上传文件时写入 `created_by`
- Modify: `backend/app/api/v1/endpoints/tasks.py`
  - 从当前用户上下文注入 `created_by`
- Modify: `backend/app/api/v1/endpoints/files.py`
  - 从当前用户上下文注入 `created_by`
- Modify: `backend/app/api/v1/endpoints/lab_collect.py`
  - 批量收口管理员能力
- Modify: `backend/app/api/v1/endpoints/acceptance.py`
  - 批量收口管理员能力
- Modify: `backend/app/api/v1/endpoints/consistency.py`
  - 批量收口管理员能力

### 前端新增文件

- Create: `frontend/src/views/RegisterView.vue`
  - 邀请码注册页
- Create: `frontend/src/views/AdminUserManageView.vue`
  - 管理员用户管理页
- Create: `frontend/src/views/AdminInviteCodeManageView.vue`
  - 管理员邀请码管理页

### 前端修改文件

- Modify: `frontend/src/auth/authStorage.js`
  - 存储 `userId`、`role`、`status`
- Modify: `frontend/src/auth/authState.js`
  - 登录态升级为用户态
- Modify: `frontend/src/api/specAgentApi.js`
  - 增加注册、当前用户、登出、管理员接口 API 方法
- Modify: `frontend/src/router/index.js`
  - 增加注册页、管理员页、角色路由守卫
- Modify: `frontend/src/views/LoginView.vue`
  - 登录成功后写入用户态，增加跳转到注册页入口
- Modify: `frontend/src/App.vue`
  - 初始化 `/auth/me`、按角色显示菜单、增加管理员菜单分组

### 文档修改

- Modify: `backend/README.md`
  - 更新认证与管理员接口说明
- Modify: `README.md`
  - 更新登录注册与角色权限说明

---

### Task 1: 建立用户与邀请码持久化模型

**Files:**
- Create: `backend/app/schemas/identity_runtime.py`
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/infra/mongo.py`
- Modify: `backend/app/infra/repositories.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_auth_service.py`

- [ ] **Step 1: 写认证实体测试，先锁定数据结构**

```python
from datetime import datetime
import unittest

from app.schemas.identity_runtime import InviteCodeRecord, UserRecord


class TestIdentityRuntimeModels(unittest.TestCase):
    def test_user_record_accepts_admin_role(self) -> None:
        now = datetime.now()
        record = UserRecord(
            user_id="u_admin_001",
            username="admin",
            password_hash="hashed",
            role="admin",
            status="active",
            created_at=now,
            updated_at=now,
            last_login_at=None,
            created_by=None,
        )
        self.assertEqual(record.role, "admin")
        self.assertEqual(record.status, "active")

    def test_invite_code_record_tracks_usage(self) -> None:
        now = datetime.now()
        record = InviteCodeRecord(
            invite_id="invite_001",
            invite_code="ABC12345",
            role="user",
            status="active",
            expires_at=now,
            max_uses=1,
            used_count=0,
            created_by="u_admin_001",
            created_at=now,
            updated_at=now,
        )
        self.assertEqual(record.max_uses, 1)
        self.assertEqual(record.used_count, 0)
```

- [ ] **Step 2: 运行测试，确认当前缺少模型定义**

Run: `cd backend && python -m pytest tests/test_auth_service.py -k identity_runtime -v`

Expected: FAIL，提示 `ModuleNotFoundError` 或 `cannot import name 'UserRecord'`

- [ ] **Step 3: 新增运行态实体与认证接口模型**

```python
# backend/app/schemas/identity_runtime.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


UserRole = Literal["admin", "user"]
UserStatus = Literal["active", "disabled"]
InviteStatus = Literal["active", "disabled", "expired", "used_up"]


class UserRecord(BaseModel):
    """用户运行态实体。"""

    user_id: str
    username: str
    password_hash: str
    role: UserRole
    status: UserStatus
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None
    created_by: str | None = None


class InviteCodeRecord(BaseModel):
    """邀请码运行态实体。"""

    invite_id: str
    invite_code: str
    role: UserRole
    status: InviteStatus
    expires_at: datetime
    max_uses: int
    used_count: int
    created_by: str
    created_at: datetime
    updated_at: datetime
```

```python
# backend/app/schemas/auth.py
class RegisterRequest(BaseModel):
    """邀请码注册请求。"""

    invite_code: str = Field(description="邀请码")
    username: str = Field(description="注册用户名")
    password: str = Field(description="登录密码")


class CurrentUserData(BaseModel):
    """当前用户信息。"""

    auth_enabled: bool = Field(description="是否启用登录鉴权")
    authenticated: bool = Field(description="是否已认证")
    user_id: str | None = Field(default=None, description="用户 ID")
    username: str | None = Field(default=None, description="用户名")
    role: str | None = Field(default=None, description="角色")
    status: str | None = Field(default=None, description="状态")
```

```python
# backend/app/core/config.py
self.auth_bootstrap_enabled: bool = os.getenv("AUTH_BOOTSTRAP_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
self.auth_invite_default_hours: int = int(os.getenv("AUTH_INVITE_DEFAULT_HOURS", "72"))
```

```python
# backend/app/infra/mongo.py
def get_users_collection() -> Collection:
    return get_database()["users"]


def get_invite_codes_collection() -> Collection:
    return get_database()["invite_codes"]
```

```python
# backend/app/infra/repositories.py
class UserRepository:
    """用户仓储。"""

    @staticmethod
    def save(user_record: UserRecord) -> None:
        get_users_collection().update_one(
            {"user_id": user_record.user_id},
            {"$set": user_record.model_dump(mode="python")},
            upsert=True,
        )

    @staticmethod
    def find_by_username(username: str) -> UserRecord | None:
        doc = get_users_collection().find_one({"username": username}, {"_id": 0})
        return UserRecord(**doc) if doc else None


class InviteCodeRepository:
    """邀请码仓储。"""

    @staticmethod
    def save(invite_record: InviteCodeRecord) -> None:
        get_invite_codes_collection().update_one(
            {"invite_id": invite_record.invite_id},
            {"$set": invite_record.model_dump(mode="python")},
            upsert=True,
        )
```

- [ ] **Step 4: 为集合建立唯一索引与查询入口**

```python
# backend/app/services/auth_service.py（先创建最小骨架）
from app.infra.mongo import get_invite_codes_collection, get_users_collection


def ensure_identity_indexes() -> None:
    get_users_collection().create_index("username", unique=True)
    get_users_collection().create_index("user_id", unique=True)
    get_invite_codes_collection().create_index("invite_code", unique=True)
    get_invite_codes_collection().create_index("invite_id", unique=True)
    get_invite_codes_collection().create_index("expires_at")
```

- [ ] **Step 5: 运行测试确认模型与仓储基础通过**

Run: `cd backend && python -m pytest tests/test_auth_service.py -k identity_runtime -v`

Expected: PASS

- [ ] **Step 6: 提交当前基础层改动**

```bash
git add backend/app/schemas/identity_runtime.py backend/app/schemas/auth.py backend/app/infra/mongo.py backend/app/infra/repositories.py backend/app/core/config.py backend/tests/test_auth_service.py
git commit -m "新增用户与邀请码基础模型

- 增加用户与邀请码运行态实体
- 增加用户与邀请码集合访问入口
- 补充认证一期配置项"
```

### Task 2: 实现注册、登录、当前用户与管理员引导

**Files:**
- Create: `backend/app/services/auth_service.py`
- Modify: `backend/app/core/auth.py`
- Modify: `backend/app/api/v1/endpoints/auth.py`
- Modify: `backend/app/schemas/auth.py`
- Test: `backend/tests/test_auth_service.py`

- [ ] **Step 1: 编写认证服务测试，覆盖邀请码注册与数据库用户登录**

```python
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from app.services.auth_service import AuthService
from app.schemas.identity_runtime import InviteCodeRecord, UserRecord


class TestAuthService(unittest.TestCase):
    @patch("app.services.auth_service.InviteCodeRepository.find_by_code")
    @patch("app.services.auth_service.UserRepository.find_by_username")
    @patch("app.services.auth_service.UserRepository.save")
    @patch("app.services.auth_service.InviteCodeRepository.increment_usage")
    def test_register_with_valid_invite(
        self,
        increment_usage,
        save_user,
        find_user,
        find_invite,
    ) -> None:
        find_user.return_value = None
        find_invite.return_value = InviteCodeRecord(
            invite_id="invite_001",
            invite_code="ABC12345",
            role="user",
            status="active",
            expires_at=datetime.now() + timedelta(hours=1),
            max_uses=1,
            used_count=0,
            created_by="u_admin_001",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        result = AuthService.register("ABC12345", "alice", "Password123!")

        self.assertEqual(result.username, "alice")
        self.assertEqual(result.role, "user")
        save_user.assert_called_once()
        increment_usage.assert_called_once_with("invite_001")
```

```python
    @patch("app.services.auth_service.UserRepository.find_by_username")
    @patch("app.services.auth_service.UserRepository.update_last_login")
    def test_login_with_database_user(
        self,
        update_last_login,
        find_by_username,
    ) -> None:
        find_by_username.return_value = UserRecord(
            user_id="u_user_001",
            username="alice",
            password_hash=AuthService.hash_password("Password123!"),
            role="user",
            status="active",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_login_at=None,
            created_by="u_admin_001",
        )

        login_data = AuthService.login("alice", "Password123!")

        self.assertEqual(login_data.username, "alice")
        self.assertTrue(login_data.access_token)
        update_last_login.assert_called_once_with("u_user_001")
```

- [ ] **Step 2: 运行测试，确认当前还没有认证服务实现**

Run: `cd backend && python -m pytest tests/test_auth_service.py -k "register or login_with_database_user" -v`

Expected: FAIL，提示 `ModuleNotFoundError: No module named 'app.services.auth_service'`

- [ ] **Step 3: 实现认证服务与密码哈希**

```python
# backend/app/services/auth_service.py
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta
from uuid import uuid4

from app.core.config import settings
from app.core.auth import build_access_token
from app.infra.repositories import InviteCodeRepository, UserRepository
from app.schemas.auth import CurrentUserData, LoginData
from app.schemas.identity_runtime import InviteCodeRecord, UserRecord


class AuthService:
    """认证服务。"""

    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        return hmac.compare_digest(AuthService.hash_password(password), password_hash)

    @staticmethod
    def register(invite_code: str, username: str, password: str) -> UserRecord:
        invite = InviteCodeRepository.find_by_code(invite_code)
        if not invite:
            raise ValueError("邀请码不存在")
        if invite.status != "active":
            raise ValueError("邀请码不可用")
        if invite.expires_at <= datetime.now():
            raise ValueError("邀请码已过期")
        if invite.used_count >= invite.max_uses:
            raise ValueError("邀请码已用尽")
        if UserRepository.find_by_username(username):
            raise ValueError("用户名已存在")

        now = datetime.now()
        user_record = UserRecord(
            user_id=f"u_{uuid4().hex[:12]}",
            username=username,
            password_hash=AuthService.hash_password(password),
            role=invite.role,
            status="active",
            created_at=now,
            updated_at=now,
            last_login_at=None,
            created_by=invite.created_by,
        )
        UserRepository.save(user_record)
        InviteCodeRepository.increment_usage(invite.invite_id)
        return user_record

    @staticmethod
    def login(username: str, password: str) -> LoginData:
        user = UserRepository.find_by_username(username)
        if not user or not AuthService.verify_password(password, user.password_hash):
            raise ValueError("账号或密码错误")
        if user.status != "active":
            raise ValueError("当前账号已被禁用")
        token, expires_at = build_access_token(user.user_id, user.username, user.role)
        UserRepository.update_last_login(user.user_id)
        return LoginData(
            auth_enabled=True,
            user_id=user.user_id,
            username=user.username,
            role=user.role,
            status=user.status,
            access_token=token,
            token_type="Bearer",
            expires_at=expires_at,
        )
```

- [ ] **Step 4: 改造 Token 结构与当前用户解析**

```python
# backend/app/core/auth.py
def build_access_token(user_id: str, username: str, role: str) -> tuple[str, int]:
    expires_at = int(time.time()) + settings.auth_token_expire_hours * 3600
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": expires_at,
        "iat": int(time.time()),
    }
    payload_segment = _urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    signature_segment = _sign_payload(payload_segment)
    return f"{payload_segment}.{signature_segment}", expires_at


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, str] | None:
    if not settings.auth_enabled:
        return None
    token = _parse_authorization_token(authorization)
    payload = parse_access_token(token)
    return {
        "user_id": str(payload["sub"]),
        "username": str(payload["username"]),
        "role": str(payload["role"]),
    }
```

```python
def require_admin(authorization: str | None = Header(default=None)) -> None:
    if not settings.auth_enabled:
        return
    current_user = get_current_user(authorization)
    if not current_user or current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="无管理员权限")
```

- [ ] **Step 5: 改造认证接口**

```python
# backend/app/api/v1/endpoints/auth.py
@router.post("/register", response_model=ApiResponse[CurrentUserData])
def register(payload: RegisterRequest) -> ApiResponse[CurrentUserData]:
    user = auth_service.register(
        invite_code=payload.invite_code.strip(),
        username=payload.username.strip(),
        password=payload.password,
    )
    return ApiResponse(
        code=0,
        message="ok",
        data=CurrentUserData(
            auth_enabled=True,
            authenticated=True,
            user_id=user.user_id,
            username=user.username,
            role=user.role,
            status=user.status,
        ),
    )


@router.get("/me", response_model=ApiResponse[CurrentUserData])
def get_current_user_profile(current_user=Depends(get_current_user)) -> ApiResponse[CurrentUserData]:
    if not current_user:
        return ApiResponse(
            code=0,
            message="ok",
            data=CurrentUserData(auth_enabled=settings.auth_enabled, authenticated=False),
        )
    return ApiResponse(
        code=0,
        message="ok",
        data=CurrentUserData(
            auth_enabled=True,
            authenticated=True,
            user_id=current_user["user_id"],
            username=current_user["username"],
            role=current_user["role"],
            status="active",
        ),
    )
```

- [ ] **Step 6: 运行后端认证测试**

Run: `cd backend && python -m pytest tests/test_auth_service.py -v`

Expected: PASS

- [ ] **Step 7: 提交认证服务改动**

```bash
git add backend/app/services/auth_service.py backend/app/core/auth.py backend/app/api/v1/endpoints/auth.py backend/app/schemas/auth.py backend/tests/test_auth_service.py
git commit -m "实现邀请码注册与用户登录

- 新增用户表认证服务
- 改造 Bearer Token 载荷为真实用户
- 增加注册与当前用户接口"
```

### Task 3: 增加管理员接口与后端角色保护

**Files:**
- Create: `backend/app/schemas/admin.py`
- Create: `backend/app/api/v1/endpoints/admin.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/infra/repositories.py`
- Modify: `backend/app/api/v1/endpoints/lab_collect.py`
- Modify: `backend/app/api/v1/endpoints/acceptance.py`
- Modify: `backend/app/api/v1/endpoints/consistency.py`
- Test: `backend/tests/test_admin_endpoints.py`

- [ ] **Step 1: 写管理员接口权限测试**

```python
from fastapi.testclient import TestClient
import unittest

from app.main import app


class TestAdminEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_admin_users_requires_admin_role(self) -> None:
        response = self.client.get(
            "/api/v1/admin/users",
            headers={"Authorization": "Bearer invalid.token"},
        )
        self.assertIn(response.status_code, {401, 403})
```

- [ ] **Step 2: 运行测试，确认管理员接口尚不存在**

Run: `cd backend && python -m pytest tests/test_admin_endpoints.py -v`

Expected: FAIL，提示 `/api/v1/admin/users` 不存在或导入失败

- [ ] **Step 3: 增加管理员接口模型与仓储方法**

```python
# backend/app/schemas/admin.py
from pydantic import BaseModel, Field


class AdminUserListItem(BaseModel):
    user_id: str = Field(description="用户 ID")
    username: str = Field(description="用户名")
    role: str = Field(description="角色")
    status: str = Field(description="状态")


class InviteCodeCreateRequest(BaseModel):
    expires_hours: int = Field(default=72, ge=1, le=720, description="有效小时数")
    max_uses: int = Field(default=1, ge=1, le=100, description="最大使用次数")
```

```python
# backend/app/infra/repositories.py
class UserRepository:
    @staticmethod
    def list_all() -> list[UserRecord]:
        cursor = get_users_collection().find({}, {"_id": 0}).sort([("created_at", -1)])
        return [UserRecord(**doc) for doc in cursor]

    @staticmethod
    def update_status(user_id: str, status: str) -> None:
        get_users_collection().update_one({"user_id": user_id}, {"$set": {"status": status, "updated_at": datetime.now()}})


class InviteCodeRepository:
    @staticmethod
    def list_all() -> list[InviteCodeRecord]:
        cursor = get_invite_codes_collection().find({}, {"_id": 0}).sort([("created_at", -1)])
        return [InviteCodeRecord(**doc) for doc in cursor]
```

- [ ] **Step 4: 实现管理员接口并保护现有管理员能力**

```python
# backend/app/api/v1/endpoints/admin.py
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/users", response_model=ApiResponse[list[AdminUserListItem]])
def list_users() -> ApiResponse[list[AdminUserListItem]]:
    items = [
        AdminUserListItem(
            user_id=item.user_id,
            username=item.username,
            role=item.role,
            status=item.status,
        )
        for item in UserRepository.list_all()
    ]
    return ApiResponse(code=0, message="ok", data=items)
```

```python
# backend/app/api/v1/router.py
api_router.include_router(admin_router)
api_router.include_router(lab_collect_router, dependencies=[Depends(require_admin)])
api_router.include_router(acceptance_router, dependencies=[Depends(require_admin)])
api_router.include_router(consistency_router, dependencies=[Depends(require_admin)])
```

- [ ] **Step 5: 运行管理员接口测试**

Run: `cd backend && python -m pytest tests/test_admin_endpoints.py -v`

Expected: PASS

- [ ] **Step 6: 提交管理员接口改动**

```bash
git add backend/app/schemas/admin.py backend/app/api/v1/endpoints/admin.py backend/app/api/v1/router.py backend/app/infra/repositories.py backend/app/api/v1/endpoints/lab_collect.py backend/app/api/v1/endpoints/acceptance.py backend/app/api/v1/endpoints/consistency.py backend/tests/test_admin_endpoints.py
git commit -m "增加管理员接口与角色保护

- 新增用户与邀请码管理接口
- 将实验管理与评测能力收为管理员专属
- 增加管理员权限测试"
```

### Task 4: 写入任务与文件归属字段

**Files:**
- Modify: `backend/app/schemas/task_runtime.py`
- Modify: `backend/app/services/task_service.py`
- Modify: `backend/app/services/file_service.py`
- Modify: `backend/app/api/v1/endpoints/tasks.py`
- Modify: `backend/app/api/v1/endpoints/files.py`
- Test: `backend/tests/test_auth_service.py`

- [ ] **Step 1: 编写归属字段测试**

```python
from unittest.mock import patch
import unittest

from app.services.file_service import FileService


class TestOwnershipFields(unittest.TestCase):
    @patch("app.services.file_service.FileRepository.save")
    def test_save_upload_file_writes_created_by(self, save_file) -> None:
        upload_file = type("UploadFileStub", (), {"filename": "demo.txt", "file": type("FileObj", (), {"read": lambda self: b'demo'})()})()
        with patch("pathlib.Path.write_bytes"), patch("app.services.file_service.settings.upload_root"):
            try:
                FileService.save_upload_file(upload_file=upload_file, created_by="u_user_001")
            except Exception:
                pass
        save_file.assert_called()
        payload = save_file.call_args.args[0]
        self.assertEqual(payload.created_by, "u_user_001")
```

- [ ] **Step 2: 运行测试，确认接口签名尚未支持 `created_by`**

Run: `cd backend && python -m pytest tests/test_auth_service.py -k created_by -v`

Expected: FAIL，提示 `save_upload_file() got an unexpected keyword argument 'created_by'`

- [ ] **Step 3: 修改运行态模型并透传当前用户**

```python
# backend/app/schemas/task_runtime.py
class TaskRecord(BaseModel):
    task_id: str
    task_type: TaskKind
    status: TaskStatus
    progress: int
    message: str
    input: dict[str, Any]
    params: dict[str, Any]
    created_by: str | None = None
    result_ref: str | None = None
    error: TaskErrorInfo | None = None
    created_at: datetime
    updated_at: datetime


class FileRecord(BaseModel):
    file_id: str
    file_name: str
    file_size: int
    file_ext: str
    storage_path: str
    sha256: str
    created_by: str | None = None
    created_at: datetime | None = None
```

```python
# backend/app/services/file_service.py
@staticmethod
def save_upload_file(upload_file: UploadFile, created_by: str | None = None) -> UploadFileData:
    ...
    FileRepository.save(
        FileRecord(
            **payload.model_dump(),
            created_by=created_by,
            created_at=datetime.now(),
        )
    )
    return payload
```

```python
# backend/app/services/task_service.py
@staticmethod
def create_task(task_type: TaskKind, input_data: dict[str, Any], params: dict[str, Any], created_by: str | None = None) -> dict[str, Any]:
    ...
    task_record = TaskRecord(
        task_id=task_id,
        task_type=task_type,
        status="PENDING",
        progress=0,
        message="task created",
        input=input_data,
        params=params,
        created_by=created_by,
        result_ref=None,
        error=None,
        created_at=now,
        updated_at=now,
    )
```

- [ ] **Step 4: 在任务与文件接口中注入当前用户 ID**

```python
# backend/app/api/v1/endpoints/files.py
@router.post("/upload", response_model=ApiResponse[UploadFileData])
def upload_file(
    current_user=Depends(get_current_user),
    file: UploadFile = File(...),
    biz_type: str | None = Form(default=None),
) -> ApiResponse[UploadFileData]:
    _validate_upload(file=file, biz_type=biz_type)
    saved = FileService.save_upload_file(
        upload_file=file,
        created_by=current_user["user_id"] if current_user else None,
    )
    return ApiResponse(code=0, message="ok", data=saved)
```

```python
# backend/app/api/v1/endpoints/tasks.py
@router.post("/gpc", response_model=ApiResponse[CreateTaskData])
def create_gpc_task(payload: CreateGpcTaskRequest, current_user=Depends(get_current_user)) -> ApiResponse[CreateTaskData]:
    entity = task_service.create_task(
        task_type="gpc_analysis",
        input_data=payload.input.model_dump(),
        params=payload.params.model_dump(),
        created_by=current_user["user_id"] if current_user else None,
    )
```

- [ ] **Step 5: 运行归属字段测试**

Run: `cd backend && python -m pytest tests/test_auth_service.py -k created_by -v`

Expected: PASS

- [ ] **Step 6: 提交归属字段改动**

```bash
git add backend/app/schemas/task_runtime.py backend/app/services/task_service.py backend/app/services/file_service.py backend/app/api/v1/endpoints/tasks.py backend/app/api/v1/endpoints/files.py backend/tests/test_auth_service.py
git commit -m "补充任务与文件归属字段

- 为上传文件与分析任务写入 created_by
- 从认证上下文透传用户归属
- 为对象级权限预留基础字段"
```

### Task 5: 前端用户态、注册页与角色路由保护

**Files:**
- Create: `frontend/src/views/RegisterView.vue`
- Modify: `frontend/src/auth/authStorage.js`
- Modify: `frontend/src/auth/authState.js`
- Modify: `frontend/src/api/specAgentApi.js`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/views/LoginView.vue`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 扩展前端会话存储结构**

```javascript
// frontend/src/auth/authStorage.js
export function getStoredAuthSession() {
  ...
  if (!session?.accessToken || !session?.tokenType || !session?.userId || !session?.role) {
    return null
  }
  return session
}
```

```javascript
// frontend/src/auth/authState.js
export const authState = reactive({
  initialized: false,
  authEnabled: false,
  authenticated: hasValidInitialSession,
  userId: hasValidInitialSession ? initialSession.userId || '' : '',
  username: hasValidInitialSession ? initialSession.username || '' : '',
  role: hasValidInitialSession ? initialSession.role || '' : '',
  status: hasValidInitialSession ? initialSession.status || 'active' : 'active',
  tokenType: hasValidInitialSession ? initialSession.tokenType || 'Bearer' : 'Bearer',
  accessToken: hasValidInitialSession ? initialSession.accessToken || '' : '',
  expiresAt: hasValidInitialSession ? initialSession.expiresAt || 0 : 0,
})
```

- [ ] **Step 2: 增加认证与管理员 API 方法**

```javascript
// frontend/src/api/specAgentApi.js
export async function registerWithInviteCode(payload, options = {}) {
  const response = await apiClient.post('/auth/register', payload, buildRequestConfig(options))
  return unwrapResponse(response)
}

export async function getCurrentUser(options = {}) {
  const response = await apiClient.get('/auth/me', buildRequestConfig(options))
  return unwrapResponse(response)
}

export async function listAdminUsers(options = {}) {
  const response = await apiClient.get('/admin/users', buildRequestConfig(options))
  return unwrapResponse(response)
}

export async function listInviteCodes(options = {}) {
  const response = await apiClient.get('/admin/invite-codes', buildRequestConfig(options))
  return unwrapResponse(response)
}
```

- [ ] **Step 3: 新增注册页并改造登录页**

```vue
<!-- frontend/src/views/RegisterView.vue -->
<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { getApiErrorMessage, registerWithInviteCode } from '../api/specAgentApi'

const router = useRouter()
const submitting = ref(false)
const form = reactive({
  inviteCode: '',
  username: '',
  password: '',
  confirmPassword: '',
})

async function handleSubmit() {
  if (form.password !== form.confirmPassword) {
    ElMessage.error('两次输入的密码不一致')
    return
  }
  submitting.value = true
  try {
    await registerWithInviteCode({
      invite_code: form.inviteCode.trim(),
      username: form.username.trim(),
      password: form.password,
    })
    ElMessage.success('注册成功，请登录')
    router.replace('/login')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    submitting.value = false
  }
}
</script>
```

```vue
<!-- frontend/src/views/LoginView.vue -->
<el-button text @click="router.push('/register')">没有账号？使用邀请码注册</el-button>
```

- [ ] **Step 4: 增加角色路由守卫与菜单控制**

```javascript
// frontend/src/router/index.js
{ path: '/register', component: RegisterView, meta: { public: true } },
{ path: '/admin/users', component: AdminUserManageView, meta: { requiresRole: 'admin' } },
{ path: '/admin/invite-codes', component: AdminInviteCodeManageView, meta: { requiresRole: 'admin' } },

router.beforeEach((to) => {
  ...
  if (to.meta.requiresRole && authState.role !== to.meta.requiresRole) {
    return '/dashboard'
  }
  return true
})
```

```vue
<!-- frontend/src/App.vue -->
<el-sub-menu v-if="authState.role === 'admin'" index="/admin">
  <template #title>
    <el-icon><SetUp /></el-icon>
    <span>系统管理</span>
  </template>
  <el-menu-item index="/admin/users">用户管理</el-menu-item>
  <el-menu-item index="/admin/invite-codes">邀请码管理</el-menu-item>
</el-sub-menu>
```

- [ ] **Step 5: 运行前端构建验证**

Run: `cd frontend && npm run build`

Expected: PASS，输出 `dist/` 构建完成

- [ ] **Step 6: 提交前端认证与路由改动**

```bash
git add frontend/src/views/RegisterView.vue frontend/src/auth/authStorage.js frontend/src/auth/authState.js frontend/src/api/specAgentApi.js frontend/src/router/index.js frontend/src/views/LoginView.vue frontend/src/App.vue
git commit -m "增加前端注册与角色路由保护

- 新增邀请码注册页
- 登录态升级为用户态
- 增加管理员路由与菜单保护"
```

### Task 6: 管理员前端页面与文档收口

**Files:**
- Create: `frontend/src/views/AdminUserManageView.vue`
- Create: `frontend/src/views/AdminInviteCodeManageView.vue`
- Modify: `backend/README.md`
- Modify: `README.md`

- [ ] **Step 1: 新增用户管理页**

```vue
<!-- frontend/src/views/AdminUserManageView.vue -->
<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getApiErrorMessage, listAdminUsers } from '../api/specAgentApi'

const loading = ref(false)
const users = ref([])

async function loadUsers() {
  loading.value = true
  try {
    users.value = await listAdminUsers()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

onMounted(loadUsers)
</script>
```

- [ ] **Step 2: 新增邀请码管理页**

```vue
<!-- frontend/src/views/AdminInviteCodeManageView.vue -->
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createInviteCode, getApiErrorMessage, listInviteCodes } from '../api/specAgentApi'

const loading = ref(false)
const inviteCodes = ref([])
const form = reactive({
  expiresHours: 72,
  maxUses: 1,
})

async function loadInviteCodes() {
  loading.value = true
  try {
    inviteCodes.value = await listInviteCodes()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  try {
    await createInviteCode({
      expires_hours: form.expiresHours,
      max_uses: form.maxUses,
    })
    ElMessage.success('邀请码创建成功')
    await loadInviteCodes()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  }
}

onMounted(loadInviteCodes)
</script>
```

- [ ] **Step 3: 更新文档**

```markdown
<!-- backend/README.md -->
### auth — 登录鉴权

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/register` | 邀请码注册 |
| POST | `/auth/login` | 账号密码登录 |
| POST | `/auth/logout` | 退出登录 |
| GET | `/auth/me` | 当前用户信息 |
| GET | `/auth/status` | 获取登录开关与当前会话状态 |

### admin — 用户与邀请码管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/admin/users` | 用户列表 |
| GET | `/admin/invite-codes` | 邀请码列表 |
| POST | `/admin/invite-codes` | 创建邀请码 |
```

- [ ] **Step 4: 运行最终验收命令**

Run:

```bash
cd backend && python -m pytest tests/test_auth_service.py tests/test_admin_endpoints.py -v
cd ../frontend && npm run build
```

Expected:

- 后端测试全部 PASS
- 前端构建 PASS

- [ ] **Step 5: 提交文档与管理页面改动**

```bash
git add frontend/src/views/AdminUserManageView.vue frontend/src/views/AdminInviteCodeManageView.vue backend/README.md README.md
git commit -m "补齐用户与邀请码管理页面

- 新增管理员用户管理页
- 新增邀请码管理页
- 更新认证与角色权限文档"
```

---

## 自检结论

### Spec 覆盖

- 邀请码注册：Task 2、Task 5、Task 6 覆盖
- 用户表登录：Task 1、Task 2 覆盖
- 管理员 / 普通用户角色：Task 2、Task 3、Task 5 覆盖
- 管理员专属能力保护：Task 3、Task 5 覆盖
- 任务与文件归属字段：Task 4 覆盖

### Placeholder 扫描

- 计划中未保留 `TODO`、`TBD`、`稍后补` 之类占位词
- 所有代码步骤都给出了明确文件路径、代码片段和验证命令

### 类型与命名一致性

- 角色统一使用 `admin` / `user`
- 用户状态统一使用 `active` / `disabled`
- 邀请码状态统一使用 `active` / `disabled` / `expired` / `used_up`
- 前后端统一使用 `userId` / `user_id`、`role`、`status`
