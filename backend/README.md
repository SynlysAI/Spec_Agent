# Spec Agent 后端技术文档

## 启动服务

### 安装依赖

```bash
cd backend
conda activate Spec_Agent
pip install -r requirements.txt
```

### 配置环境变量

```bash
cp .env.example .env
```

后端自动加载 `backend/.env`，详见下方环境变量表。

### 配套中间件启动

若采用 `Windows/Linux` 原生方式启动应用，建议仍通过 Docker 提供 `MongoDB` 与 `RabbitMQ`：

```bash
docker compose --env-file docker/.env -f docker/docker-compose.infra.yml up -d mongodb rabbitmq
# 旧版环境可使用：
# docker-compose --env-file docker/.env -f docker/docker-compose.infra.yml up -d mongodb rabbitmq
```

原生部署时，`backend/.env` 中的 `MONGODB_HOST`、`RABBITMQ_HOST` 可指向本机容器服务，也可直接配置为外部服务地址。

### Docker 正式部署

正式环境推荐使用完整 Docker 部署：

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.infra.yml up -d --build
# 旧版环境可使用：
# docker-compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.infra.yml up -d --build
```

默认对外仅开放 `Nginx` 端口，`MongoDB` 与 `RabbitMQ` 默认仅容器内访问。

### 前端静态文件托管

后端会自动检测 `frontend/dist/` 目录，存在时将前端作为 SPA 静态文件挂载到 `/`，无需单独启动前端服务。

首次部署或前端代码更新后需先构建：

```bash
cd frontend
npm install
npm run build
```

### 启动 API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 启动 Celery Worker

```bash
python -m celery -A app.worker.celery_app:celery_app worker --loglevel=info -Q spec_agent -P solo
```

Windows 下推荐 `python -m celery` 形式，避免 `celery.exe` 的模块路径差异。

### 接口文档

启动后访问：http://127.0.0.1:8000/docs

---

## 架构概览

```text
FastAPI /api/v1
  ├── endpoints/     # 路由层，14 个模块
  ├── schemas/       # Pydantic 请求/响应模型
  ├── services/      # 应用服务层（20+ 服务）
  ├── modules/       # 谱图业务模块（gpc / nmr / ir_raman / common / data）
  ├── infra/         # MongoDB 连接与仓储封装
  ├── models/        # 领域模型
  ├── core/          # 配置、日志、鉴权
  └── worker/        # Celery Worker 与任务定义

analysis/            # 算法分析层（独立于 app）
  ├── gpc/           # GPC 校准曲线、ROI 处理、PDF 处理
  ├── nmr/           # NMR 峰检测与多峰分析
  └── raman/         # Raman 光谱分析
      └── models/    # Graphormer、FCN、MLP-Mixer、Transformer
```

### 关键入口

| 文件 | 职责 |
| --- | --- |
| `app/main.py` | FastAPI 应用入口 |
| `app/api/v1/router.py` | 路由聚合，注册所有 endpoints |
| `app/core/config.py` | 全局配置（`settings` 单例） |
| `app/core/auth.py` | 本地登录鉴权中间件 |
| `app/core/logging.py` | 日志初始化 |
| `app/infra/mongo.py` | MongoDB 连接管理 |
| `app/infra/repositories.py` | Mongo 仓储封装 |
| `app/services/task_executors.py` | 注册式任务执行器 |
| `app/services/task_service.py` | 任务 CRUD 服务 |
| `app/worker/celery_app.py` | Celery 应用初始化 |
| `app/worker/tasks.py` | Celery 任务定义 |

---

## 环境变量

配置位于 `app/core/config.py`，默认加载 `backend/.env`。

### 基础

| 变量名 | 说明 | 默认值 |
| --- | --- | --- |
| `APP_ENV` | 运行环境 | `dev` |

### MongoDB

| 变量名 | 说明 | 默认值 |
| --- | --- | --- |
| `MONGODB_HOST` | 主机 | `127.0.0.1` |
| `MONGODB_PORT` | 端口 | `27017` |
| `MONGODB_USERNAME` | 用户名 | 空 |
| `MONGODB_PASSWORD` | 密码 | 空 |
| `MONGODB_DATABASE` | 数据库名 | `spec_agent` |

### RabbitMQ / Celery

| 变量名 | 说明 | 默认值 |
| --- | --- | --- |
| `RABBITMQ_HOST` | 主机 | `127.0.0.1` |
| `RABBITMQ_PORT` | 端口 | `5672` |
| `RABBITMQ_USERNAME` | 用户名 | `guest` |
| `RABBITMQ_PASSWORD` | 密码 | `guest` |
| `RABBITMQ_VHOST` | vhost | `/` |
| `CELERY_TASK_QUEUE` | 队列名 | `spec_agent` |

### 外部服务

| 变量名 | 说明 | 默认值 |
| --- | --- | --- |
| `NMR_SERVER_BASE_URL` | NMRServer 地址 | `http://127.0.0.1:8080` |
| `LCMS_INFER_URL` | LCMS 推理地址 | `http://127.0.0.1:9999/infer` |
| `RAMAN_CAPTURE_INSTRUMENT_IP` | 拉曼光谱仪 IP | `47.113.220.254` |
| `RAMAN_CAPTURE_CALLBACK_URL` | 拉曼采集回调 | `http://127.0.0.1:8099/raman/jy/callback` |
| `RAMAN_CAPTURE_SUBMIT_PORT` | 拉曼提交端口 | `7001` |
| `RAMAN_CAPTURE_RESULT_PORT` | 拉曼结果端口 | `7002` |

### LLM

| 变量名 | 说明 | 默认值 |
| --- | --- | --- |
| `LLM_MODEL` | 模型名称 | `deepseek-chat` |
| `LLM_API_KEY` | API Key | 空 |
| `LLM_BASE_URL` | API 地址 | `https://api.agicto.cn/v1` |
| `LLM_TEMPERATURE` | 生成温度 | `0.7` |
| `LLM_MAX_TOKENS` | 最大 token | `8192` |
| `LLM_TIMEOUT` | 超时（秒） | `60` |
| `LLM_MAX_RETRIES` | 最大重试 | `2` |

### 路径

| 变量名 | 说明 | 默认值 |
| --- | --- | --- |
| `SPEC_AGENT_RUNTIME_ROOT` | 运行时根目录 | `.runtime` |
| `SPEC_AGENT_UPLOAD_ROOT` | 上传目录 | `.runtime/uploads` |
| `SPEC_AGENT_OUTPUT_ROOT` | 输出目录 | `.runtime/outputs` |
| `SPEC_AGENT_LOG_ROOT` | 日志目录 | `backend/logs` |
| `SPECTRUM_FILES_ROOT` | 谱图样本根目录 | `sample_data` |

### 鉴权

| 变量名 | 说明 | 默认值 |
| --- | --- | --- |
| `AUTH_ENABLED` | 启用登录鉴权 | `false` |
| `AUTH_USERNAME` | 登录账号 | `admin` |
| `AUTH_PASSWORD` | 登录密码 | `admin123456` |
| `AUTH_SECRET` | JWT 签名密钥（未配置时自动生成） | 空 |
| `AUTH_TOKEN_EXPIRE_HOURS` | Token 有效期（小时） | `12` |

### 前端

| 变量名 | 说明 |
| --- | --- |
| `VITE_API_BASE_URL` | 前端 API 根地址，示例：`http://127.0.0.1:8000/api/v1` |
| `VITE_DEV_API_PROXY_TARGET` | 前端开发代理目标，示例：`http://127.0.0.1:8000` |

未设置 `VITE_API_BASE_URL` 时前端默认使用相对路径 `/api/v1`。前端开发模式下可通过 `VITE_DEV_API_PROXY_TARGET` 控制代理目标。

### ARM64 说明

当前华为 Linux 服务器环境为 `aarch64/ARM64`。`torch`、`rdkit` 等科学计算依赖在 Docker 镜像中的可安装性需要单独验证，部署结构已支持 Docker 化，但不应在未验证依赖兼容性前假定 ARM64 镜像一定一次构建成功。

---

## API 接口

统一前缀：`/api/v1`

### health — 健康检查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 服务状态（含 Worker 探活） |

### auth — 登录鉴权

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/login` | 登录获取 Token |
| GET | `/auth/status` | 获取登录开关与当前会话状态 |

### files — 文件管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/files/upload` | 上传文件 |

### tasks — 谱图任务

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/tasks` | 任务列表（分页） |
| POST | `/tasks/gpc` | 提交 GPC 任务 |
| POST | `/tasks/nmr` | 提交 NMR 任务 |
| POST | `/tasks/ir` | 提交 IR 任务 |
| POST | `/tasks/raman` | 提交 Raman 任务 |
| POST | `/tasks/lcms` | 提交 LCMS 任务 |
| GET | `/tasks/{task_id}` | 任务详情 |
| GET | `/tasks/{task_id}/result` | 任务结果 |
| GET | `/tasks/{task_id}/artifacts` | 任务产物列表 |

### lab-collect — 实验数据采集

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/lab-collect/config` | 采集配置 |
| POST | `/lab-collect/run` | 启动采集 |
| GET | `/lab-collect/runs` | 采集历史 |
| GET | `/lab-collect/run/{run_id}` | 批次详情 |
| GET | `/lab-collect/samples` | 样本列表 |
| GET | `/lab-collect/samples/summary` | 样本汇总 |
| GET | `/lab-collect/samples/{sample_id}` | 样本详情 |
| DELETE | `/lab-collect/samples/{sample_id}` | 删除样本 |
| GET | `/lab-collect/molecular-stats` | 分子资产统计 |
| POST | `/lab-collect/molecular-stats/refresh` | 刷新统计缓存 |

### nmrserver — NMRServer 工具

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/nmrserver/forward` | 正向预测（SMILES → NMR） |
| POST | `/nmrserver/reverse` | 反向预测（NMR → 结构候选） |
| POST | `/nmrserver/search` | 数据库搜索 |

### raman-capture — 拉曼批量采集

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/raman-capture/focus` | 自动对焦 |
| POST | `/raman-capture/run` | 执行批量采集 |

### lcms-convert — LCMS 数据转化

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/tools/lcms-convert/run` | 上传 zip 并转化 |
| GET | `/tools/lcms-convert/download/{job_id}` | 下载转化结果 CSV |

### chemistry — 化学结构

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/chemistry/molecule-image` | 分子结构图 |
| GET | `/chemistry/function-group-image` | 官能团图 |

### spectra — 谱图预览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/spectra/preview` | 谱图预览数据 |

### dialogue — 报告问答

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/dialogue/analysis-types` | 分析类型列表 |
| GET | `/dialogue/reports` | 历史报告列表 |
| POST | `/dialogue/chat` | 问答对话 |

### acceptance — 解析准确性评测

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/acceptance/config` | 验收配置摘要 |
| POST | `/acceptance/run` | 启动评测 |
| GET | `/acceptance/runs` | 历史批次 |
| GET | `/acceptance/run/{run_id}` | 批次详情 |
| GET | `/acceptance/run/{run_id}/report` | 下载报告 |

### consistency — 设备重复性评测

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/consistency/config` | 评测配置摘要 |
| POST | `/consistency/run` | 启动评测 |
| GET | `/consistency/runs` | 历史批次 |
| GET | `/consistency/run/{run_id}` | 批次详情 |
| GET | `/consistency/run/{run_id}/report` | 下载报告 |

---

## 目录结构

```text
backend/
├─ analysis/                    # 算法分析层（含深度学习模型）
│  ├─ gpc/                      # GPC 分析
│  │  ├─ tools/                 # 校准曲线、ROI 处理、PDF 处理
│  │  └─ utils/                 # 分析器、绘图器
│  ├─ nmr/                      # NMR 峰检测与多峰分析
│  └─ raman/                    # Raman 光谱分析
│     ├─ models/                # Graphormer、FCN、MLP-Mixer、Transformer
│     ├─ beam_search.py         # 束搜索
│     ├─ greedy_search.py       # 贪心搜索
│     └─ retrieval.py           # 检索匹配
├─ agents/                      # Agent schema（兼容层）
├─ app/
│  ├─ api/v1/endpoints/         # 路由（14 个模块）
│  ├─ core/                     # config / logging / auth
│  ├─ infra/                    # MongoDB 连接与仓储
│  ├─ models/                   # 领域模型
│  ├─ modules/                  # 业务模块
│  │  ├─ common/                # LLM 服务、报告生成
│  │  ├─ data/                  # 数据库服务
│  │  ├─ gpc/                   # GPC 服务与工作流
│  │  ├─ ir_raman/              # IR/Raman Agent
│  │  └─ nmr/                   # NMR 服务、工作流与导出
│  ├─ schemas/                  # 请求/响应 Schema
│  ├─ services/                 # 应用服务层
│  └─ worker/                   # Celery Worker
├─ resources/
│  ├─ config/                   # acceptance / consistency / lab_collectors 配置
│  └─ raman/                    # 模型 checkpoint、数据库、tokenizer
├─ scripts/                     # OpenAPI 导出、回归脚本
├─ tests/                       # 单元测试
├─ logs/                        # 运行日志（自动创建）
├─ config.py                    # 兼容配置层（算法层过渡使用）
└─ requirements.txt
```

---

## 日志

默认目录：`backend/logs`

| 日志文件 | 内容 |
| --- | --- |
| `app.log` | 应用日志 |
| `error.log` | 错误日志 |
| `worker.log` | Celery Worker 日志 |

- 按天滚动切分，默认保留 14 天
- 可通过 `SPEC_AGENT_LOG_ROOT` 自定义目录

---

## 运行时文件

| 目录 | 用途 |
| --- | --- |
| `.runtime/uploads` | 上传文件（元数据写入 MongoDB，可通过 `file_id` 复用） |
| `.runtime/outputs` | 任务产物（通过 `/static/outputs` 静态挂载暴露） |

产物识别类型：图片（`.png/.jpg/.jpeg/.svg`）、文本（`.txt/.md/.json/.csv`）、PDF（`.pdf`）、其他。

---

## 开发脚本

### 导出 OpenAPI

```bash
python scripts/export_openapi.py
# 输出：openapi.json
```

### 回归测试

```bash
python scripts/run_regression.py
```

环境变量：`REG_BASE_URL`（默认 `http://127.0.0.1:8000/api/v1`）、`REG_GPC_PATH`、`REG_NMR_PATH`

### 其他脚本

| 脚本 | 用途 |
| --- | --- |
| `scripts/backfill_ir_raman_smiles.py` | 回填 IR/Raman SMILES 数据 |

---

## 说明

- `backend/config.py` 是兼容配置层，新代码应使用 `app.core.config.settings`
- `backend/agents/`、根级 `backend/services/` 是历史兼容层，主实现在 `app/modules` 和 `app/services`
- `backend/resources/` 和 `backend/analysis/` 部署时需随后端一起发布
- LCMS Waters `.raw` 格式转化需安装 [ProteoWizard](http://proteowizard.sourceforge.net/)
- GPC/NMR/IR/Raman 任务已完全迁入本仓，运行时不依赖外部项目
