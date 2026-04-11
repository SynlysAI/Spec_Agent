# Spec_Agent Backend（P0）

## 启动 API 服务

```bash
cd E:/xx_project/Spec_Agent/backend
conda activate spec_agent
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 启动 Celery Worker

```bash
cd E:/xx_project/Spec_Agent/backend
conda activate spec_agent
celery -A app.worker.celery_app.celery_app worker --loglevel=info -Q celery -P solo
```

## 环境变量（可选）

```bash
APP_ENV=dev
SOURCE_SPEC_AGENT_ROOT=E:/github_project/Spec_Agent

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
conda activate spec_agent
python scripts/export_openapi.py
```

导出文件：

- `backend/openapi.json`

## 执行回归脚本（P0）

```bash
cd E:/xx_project/Spec_Agent/backend
conda activate spec_agent
python scripts/run_regression.py
```

可选环境变量：

- `REG_BASE_URL`：默认 `http://127.0.0.1:8000/api/v1`
- `REG_GPC_PATH`：默认真实 GPC 样本路径
- `REG_NMR_PATH`：默认真实 NMR 样本路径

## 说明

- 任务链路为 `FastAPI + Celery + RabbitMQ + MongoDB`。
- `GPC/NMR` 任务已调用源项目解析能力（通过 `SOURCE_SPEC_AGENT_ROOT` 指定源项目路径）。
