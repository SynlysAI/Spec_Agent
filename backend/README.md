# Spec_Agent Backend（P0）

## 启动 API 服务

```bash
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 启动 Celery Worker

```bash
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
python -m celery -A app.worker.celery_app:celery_app worker --loglevel=info -Q spec_agent -P solo
```

推荐使用 `python -m celery` 形式，避免 Windows 下 `celery.exe` 入口脚本的模块路径差异问题。

## 环境变量（可选）

```bash
APP_ENV=dev

MONGODB_HOST=100.84.59.58
MONGODB_PORT=27018
MONGODB_USERNAME=admin
MONGODB_PASSWORD=password123
MONGODB_DATABASE=spec_agent

RABBITMQ_HOST=100.84.59.58
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=admin
RABBITMQ_PASSWORD=password123
RABBITMQ_VHOST=/
```

## 已实现接口

- `GET /api/v1/health`
- `POST /api/v1/files/upload`
- `POST /api/v1/tasks/gpc`
- `POST /api/v1/tasks/nmr`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/result`

## 导出 OpenAPI

```bash
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
python scripts/export_openapi.py
```

导出文件：

- `backend/openapi.json`

## 执行回归脚本（P0）

```bash
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
python scripts/run_regression.py
```

可选环境变量：

- `REG_BASE_URL`：默认 `http://127.0.0.1:8000/api/v1`
- `REG_GPC_PATH`：默认真实 GPC 样本路径
- `REG_NMR_PATH`：默认真实 NMR 样本路径

## 说明

- 任务链路为 `FastAPI + Celery + RabbitMQ + MongoDB`。
- 当前后端主干目录已统一收敛到 `backend/app`。
- `backend/app/schemas` 存放接口模型；`backend/app/modules` 作为业务模块兼容聚合层。
- `backend/resources` 存放静态资源，如 `acceptance.yaml`、`solvent_impurities.json`、Raman 模型权重与数据库。
- 根级 `backend/config.py` 与 `backend/app/models` 仅保留兼容用途，后续新代码应优先使用 `app.core.config.settings`、`app.schemas.*`、`app.modules.*`。
- 根级 `backend/agents`、`backend/services` 已缩减为历史遗留与少量兼容保留文件，不再承载主运行实现。
- `GPC/NMR/IR/Raman` 任务能力已迁入本仓，运行时不再依赖源项目目录。
