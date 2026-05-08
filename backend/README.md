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

AUTH_ENABLED=false
AUTH_USERNAME=admin
AUTH_PASSWORD=admin123456
# AUTH_SECRET=
AUTH_TOKEN_EXPIRE_HOURS=12

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

SPEC_AGENT_LOG_ROOT=E:/xx_project/Spec_Agent/backend/logs
```

## 日志说明

- 后端应用日志默认写入 `backend/logs/app.log`
- 未捕获异常与错误日志默认写入 `backend/logs/error.log`
- Celery Worker 日志默认写入 `backend/logs/worker.log`
- 项目自定义日志默认仅写入文件，不额外输出到服务启动终端
- 日志按天滚动切分，默认保留 14 天
- 可通过 `SPEC_AGENT_LOG_ROOT` 自定义日志目录

## 已实现接口

- `GET /api/v1/health`
- `POST /api/v1/files/upload`
- `GET /api/v1/lab-collect/config`
- `POST /api/v1/lab-collect/run`
- `GET /api/v1/lab-collect/runs`
- `GET /api/v1/lab-collect/run/{run_id}`
- `GET /api/v1/lab-collect/samples`
- `GET /api/v1/lab-collect/samples/{sample_id}`
- `POST /api/v1/tasks/gpc`
- `POST /api/v1/tasks/nmr`
- `POST /api/v1/tasks/ir`
- `POST /api/v1/tasks/raman`
- `POST /api/v1/tasks/lcms`
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
- `backend/resources/config/lab_collectors.yaml` 用于配置 5 类实验仪器的远程共享目录与本地落盘目录。
- 根级 `backend/config.py` 与 `backend/app/models` 仅保留兼容用途，后续新代码应优先使用 `app.core.config.settings`、`app.schemas.*`、`app.modules.*`。
- 根级 `backend/agents`、`backend/services` 已缩减为历史遗留与少量兼容保留文件，不再承载主运行实现。
- 若需启用本地登录保护，可在 `backend/.env` 中设置 `AUTH_ENABLED=true` 并配置 `AUTH_USERNAME`、`AUTH_PASSWORD`。
- `GPC/NMR/IR/Raman` 任务能力已迁入本仓，运行时不再依赖源项目目录。
