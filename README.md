# Spec Agent

## 项目简介

Spec Agent 是一个面向表征实验谱图的智能解析与分析平台，当前已从原 Streamlit Demo 形态迁移为 **FastAPI 后端 + Vue 前端** 的前后端分离工程。

项目远程仓库仍复用原仓库：

- GitHub：`git@github.com:SynlysAI/Spec_Agent.git`
- 当前重构主线远程分支：`origin/develop-vue`

本地当前分支可能仍为 `master`，如需跟随远程重构主线，可基于团队协作约定切换或建立本地跟踪分支。

当前系统提供以下能力：

- GPC、NMR、IR、Raman、LCMS 谱图任务提交、异步执行、状态查询与结果查看
- 任务产物管理，包括报告、图片、JSON、CSV、PDF 等输出文件访问
- 报告问答对话
- NMRServer 正向预测、反向预测与数据库搜索
- 拉曼光谱仪批量采集
- 评测中心：解析准确性评测、设备重复性评测、历史查询与 Markdown 报告下载
- 实验室共享目录数据采集、样本主档管理与分子资产统计
- 谱图预览、化学结构图与官能团图辅助展示

---

## 技术栈

### 后端

- FastAPI：HTTP API 服务，入口为 `backend/app/main.py`
- Celery：异步任务执行，入口为 `backend/app/worker/celery_app.py`
- RabbitMQ：Celery Broker
- MongoDB：任务、结果、文件元数据、实验采集批次与样本主档存储
- Pydantic：接口请求与响应模型
- Python 分析模块：主线位于 `backend/app/modules`、`backend/app/services`、`backend/resources`

### 前端

- Vue 3
- Vite
- Vue Router
- Element Plus
- Axios
- ECharts
- JSZip

---

## 系统架构

```text
Vue 前端页面
    ↓
Axios API Client
    ↓
FastAPI /api/v1
    ↓
Service 层创建任务并写入 MongoDB
    ↓
Celery 投递任务到 RabbitMQ
    ↓
Worker 执行谱图分析流程
    ↓
结果写入 MongoDB，产物写入 .runtime/outputs
    ↓
前端轮询任务状态并展示结果、报告和产物
```

关键入口：

- 后端应用入口：`backend/app/main.py`
- 后端路由聚合：`backend/app/api/v1/router.py`
- 后端配置：`backend/app/core/config.py`
- Celery 应用：`backend/app/worker/celery_app.py`
- Celery 任务：`backend/app/worker/tasks.py`
- 前端入口：`frontend/src/main.js`
- 前端路由：`frontend/src/router/index.js`
- 前端 API 封装：`frontend/src/api/specAgentApi.js`

---

## 目录结构

```text
Spec_Agent/
├─ backend/
│  ├─ app/
│  │  ├─ api/v1/endpoints/      # FastAPI 接口
│  │  ├─ core/                  # 配置与日志
│  │  ├─ infra/                 # MongoDB 与仓储封装
│  │  ├─ modules/               # 谱图业务模块主线实现
│  │  ├─ schemas/               # 接口 Schema
│  │  ├─ services/              # 应用服务层
│  │  └─ worker/                # Celery Worker
│  ├─ resources/
│  │  ├─ config/                # acceptance、lab_collectors 等配置
│  │  └─ raman/                 # IR/Raman 模型、数据库与 tokenizer 资源
│  ├─ scripts/                  # OpenAPI 导出、回归脚本
│  ├─ logs/                     # 后端运行日志，默认自动创建
│  ├─ requirements.txt
│  └─ README.md
├─ frontend/
│  ├─ src/
│  │  ├─ api/                   # Axios API 封装
│  │  ├─ components/            # 通用图表与展示组件
│  │  ├─ router/                # Vue Router 路由
│  │  ├─ views/                 # 页面视图
│  │  ├─ App.vue
│  │  └─ main.js
│  └─ package.json
├─ .runtime/
│  ├─ uploads/                  # 默认上传文件目录
│  └─ outputs/                  # 默认任务输出目录
├─ docs/
├─ scripts/
├─ AGENTS.md
├─ 重构验收进度表.md
└─ README.md
```

说明：

- `.runtime/uploads` 与 `.runtime/outputs` 是当前默认运行时目录。
- 根目录 `uploads/`、`outputs/` 如存在，多为历史或临时兼容目录，不应作为新功能默认依赖。
- `backend/resources` 存放正式运行所需资源配置，部署时需要随后端一起发布。
- 当前目标是完全独立部署，不再依赖源项目 `E:\github_project\Spec_Agent` 的运行时导入路径。

---

## 环境准备

建议准备：

- Conda 环境：`Spec_Agent`
- Python 3.10+
- Node.js 18+
- MongoDB
- RabbitMQ

项目约定后端运行前激活环境：

```powershell
conda activate Spec_Agent
```

---

## 后端启动

### 1. 安装依赖

```powershell
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
pip install -r requirements.txt
```

### 2. 配置环境变量

复制并按实际环境修改：

```powershell
cd E:/xx_project/Spec_Agent/backend
Copy-Item .env.example .env
```

后端会自动加载 `backend/.env`。

可选本地登录配置：

```powershell
AUTH_ENABLED=true
AUTH_USERNAME=admin
AUTH_PASSWORD=请改成你自己的密码
# AUTH_SECRET=建议生产环境显式配置
AUTH_TOKEN_EXPIRE_HOURS=12
```

说明：

- `AUTH_ENABLED=false` 时，前后端保持当前免登录访问行为。
- `AUTH_ENABLED=true` 时，前端会自动显示登录页，登录成功后才能访问现有功能页面。
- 本地账号密码校验基于 `backend/.env`，适合内网或单实例本地部署场景。

### 3. 启动 API 服务

```powershell
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 启动 Celery Worker

```powershell
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
python -m celery -A app.worker.celery_app:celery_app worker --loglevel=info -Q spec_agent -P solo
```

Windows 下推荐使用 `python -m celery`，避免 `celery.exe` 入口脚本带来的模块路径差异。

### 5. 打开接口文档

```text
http://127.0.0.1:8000/docs
```

---

## 前端启动

### 1. 安装依赖

```powershell
cd E:/xx_project/Spec_Agent/frontend
npm install
```

### 2. 启动开发服务

```powershell
cd E:/xx_project/Spec_Agent/frontend
npm run dev
```

### 3. 构建生产包

```powershell
cd E:/xx_project/Spec_Agent/frontend
npm run build
```

### 4. 本地预览构建产物

```powershell
cd E:/xx_project/Spec_Agent/frontend
npm run preview
```

---

## 环境变量

后端核心配置位于 `backend/app/core/config.py`，默认加载 `backend/.env`。

| 变量名 | 说明 | 默认值                         |
| --- | --- |-----------------------------|
| `APP_ENV` | 运行环境 | `dev`                       |
| `MONGODB_HOST` | MongoDB 主机 | `{工作站IP}`                 |
| `MONGODB_PORT` | MongoDB 端口 | `27017`                     |
| `MONGODB_USERNAME` | MongoDB 用户名 | 空                           |
| `MONGODB_PASSWORD` | MongoDB 密码 | 空                           |
| `MONGODB_DATABASE` | MongoDB 数据库 | `spec_agent`                |
| `RABBITMQ_HOST` | RabbitMQ 主机 | `{工作站IP}`                 |
| `RABBITMQ_PORT` | RabbitMQ 端口 | `5672`                      |
| `RABBITMQ_USERNAME` | RabbitMQ 用户名 | `guest`                     |
| `RABBITMQ_PASSWORD` | RabbitMQ 密码 | `guest`                     |
| `RABBITMQ_VHOST` | RabbitMQ vhost | `/`                         |
| `CELERY_TASK_QUEUE` | Celery 队列名 | `spec_agent`                |
| `NMR_SERVER_BASE_URL` | NMRServer 服务地址 | `http://{工作站IP}:8080`     |
| `LCMS_INFER_URL` | LCMS 推理服务地址 | `http://{工作站IP}:9999/infer` |
| `LLM_MODEL` | 问答模型名称 | `deepseek-chat`             |
| `LLM_API_KEY` | LLM API Key | 空                           |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.agicto.cn/v1`  |
| `SPEC_AGENT_RUNTIME_ROOT` | 运行时根目录 | `.runtime`                  |
| `SPEC_AGENT_UPLOAD_ROOT` | 上传目录 | `.runtime/uploads`          |
| `SPEC_AGENT_OUTPUT_ROOT` | 输出目录 | `.runtime/outputs`          |
| `SPEC_AGENT_LOG_ROOT` | 日志目录 | `backend/logs`              |
| `AUTH_ENABLED` | 是否启用本地登录鉴权 | `false` |
| `AUTH_USERNAME` | 本地登录账号 | `admin` |
| `AUTH_PASSWORD` | 本地登录密码 | `admin123456` |
| `AUTH_SECRET` | 本地登录令牌签名密钥，未配置时自动生成 | 空 |
| `AUTH_TOKEN_EXPIRE_HOURS` | 登录令牌有效期（小时） | `12` |
| `SPECTRUM_FILES_ROOT` | 谱图样本根目录 | `sample_data`               |

前端 API 地址：

| 变量名 | 说明 |
| --- | --- |
| `VITE_API_BASE_URL` | 前端请求后端的 API 根地址，示例：`http://127.0.0.1:8000/api/v1` |

若未设置 `VITE_API_BASE_URL`，前端会按当前页面主机名自动推导 `http(s)://当前主机:8000/api/v1`。

---

## 功能模块

### 工作台

路由：`/dashboard`

页面：`frontend/src/views/DashboardView.vue`

用于展示任务总览、状态分布、近期任务与系统入口。

### 任务提交

路由：

- `/tasks/submit/gpc`
- `/tasks/submit/nmr`
- `/tasks/submit/ir`
- `/tasks/submit/raman`
- `/tasks/submit/lcms`

页面：

- `frontend/src/views/TaskSubmitGpcView.vue`
- `frontend/src/views/TaskSubmitNmrView.vue`
- `frontend/src/views/TaskSubmitIrRamanView.vue`
- `frontend/src/views/TaskSubmitLcmsView.vue`

支持本地路径、目录路径、上传文件 `file_id` 等输入方式。NMR 场景支持前端通过 JSZip 对文件夹进行打包上传。

### 任务中心

路由：`/tasks/center`

页面：`frontend/src/views/TaskCenterView.vue`

能力：

- 任务分页查询
- 按任务类型和状态筛选
- 跳转任务详情

### 任务详情

路由：`/tasks/detail/:taskId`

页面：`frontend/src/views/TaskDetailView.vue`

能力：

- 查看任务状态
- 查看结构化结果
- 查看文本报告
- 查看输出产物
- 渲染图片、谱图、JSON 等结果

### 报告问答

路由：`/dialogue`

页面：`frontend/src/views/DialogueView.vue`

能力：

- 查询分析类型
- 查询历史报告
- 基于报告内容进行问答

### 实验数据采集

路由：`/experiments/collect`

页面：`frontend/src/views/ExperimentCollectView.vue`

能力：

- 读取实验室采集配置
- 从共享目录采集实验数据
- 查询采集批次历史
- 查看采集批次详情

配置文件：

- `backend/resources/config/lab_collectors.yaml`

### 实验样本管理

路由：`/experiments/samples`

页面：`frontend/src/views/ExperimentSampleManageView.vue`

能力：

- 查询样本汇总
- 分页查询样本主档
- 查看样本详情
- 删除样本
- 查看分子资产统计
- 手动刷新分子资产统计缓存

### NMRServer 工具

路由：`/tools/nmrserver`

页面：`frontend/src/views/ToolNmrServerView.vue`

能力：

- 正向预测：SMILES 到 NMR 位移预测
- 反向预测：NMR 位移到结构候选
- 数据库搜索：基于位移搜索匹配分子

### 拉曼批量采集

路由：`/tools/raman-capture`

页面：`frontend/src/views/ToolRamanCaptureView.vue`

能力：

- 配置拉曼光谱仪 IP 与回调端口
- 批量设置中心波数列表与激光功率列表
- 调用后端接口执行采集并展示成功/失败结果

### 评测中心

路由：`/tools/acceptance`

页面：`frontend/src/views/ToolEvaluationCenterView.vue`

能力：

- 解析准确性评测：
  - 读取验收配置摘要
  - 启动解析准确性评测
  - 查询历史批次
  - 查看样本详情
  - 下载 Markdown 报告
- 设备重复性评测：
  - 读取设备重复性评测配置摘要
  - 启动 NMR、GPC、Raman、LCMS 设备重复性评测
  - 查询历史批次
  - 查看设备级汇总与样品组明细
  - 下载 Markdown 报告

配置文件：

- `backend/resources/config/acceptance.yaml`
- `backend/resources/config/consistency.yaml`

---

## API 总览

后端 API 统一前缀：

```text
/api/v1
```

当前路由模块：

- `health`
- `files`
- `tasks`
- `lab-collect`
- `nmrserver`
- `raman-capture`
- `chemistry`
- `spectra`
- `dialogue`
- `acceptance`
- `consistency`

核心接口：

```text
GET    /api/v1/health

POST   /api/v1/files/upload

GET    /api/v1/tasks
POST   /api/v1/tasks/gpc
POST   /api/v1/tasks/nmr
POST   /api/v1/tasks/ir
POST   /api/v1/tasks/raman
POST   /api/v1/tasks/lcms
GET    /api/v1/tasks/{task_id}
GET    /api/v1/tasks/{task_id}/result
GET    /api/v1/tasks/{task_id}/artifacts

POST   /api/v1/spectra/preview

POST   /api/v1/nmrserver/forward
POST   /api/v1/nmrserver/reverse
POST   /api/v1/nmrserver/search

POST   /api/v1/raman-capture/run

GET    /api/v1/dialogue/analysis-types
GET    /api/v1/dialogue/reports
POST   /api/v1/dialogue/chat

GET    /api/v1/lab-collect/config
POST   /api/v1/lab-collect/run
GET    /api/v1/lab-collect/runs
GET    /api/v1/lab-collect/run/{run_id}
GET    /api/v1/lab-collect/samples
GET    /api/v1/lab-collect/samples/summary
GET    /api/v1/lab-collect/molecular-stats
POST   /api/v1/lab-collect/molecular-stats/refresh
GET    /api/v1/lab-collect/samples/{sample_id}
DELETE /api/v1/lab-collect/samples/{sample_id}

GET    /api/v1/acceptance/config
POST   /api/v1/acceptance/run
GET    /api/v1/acceptance/runs
GET    /api/v1/acceptance/run/{run_id}
GET    /api/v1/acceptance/run/{run_id}/report

GET    /api/v1/consistency/config
POST   /api/v1/consistency/run
GET    /api/v1/consistency/runs
GET    /api/v1/consistency/run/{run_id}
GET    /api/v1/consistency/run/{run_id}/report

GET    /api/v1/chemistry/molecule-image
GET    /api/v1/chemistry/function-group-image
```

---

## 开发辅助脚本

### 导出 OpenAPI

```powershell
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
python scripts/export_openapi.py
```

输出：

```text
backend/openapi.json
```

### 执行回归脚本

```powershell
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
python scripts/run_regression.py
```

可选环境变量：

- `REG_BASE_URL`：默认 `http://127.0.0.1:8000/api/v1`
- `REG_GPC_PATH`：GPC 回归样本路径
- `REG_NMR_PATH`：NMR 回归样本路径

---

## 日志与运行时文件

### 日志

默认日志目录：

```text
backend/logs
```

常见日志：

- `backend/logs/app.log`
- `backend/logs/error.log`
- `backend/logs/worker.log`

可通过 `SPEC_AGENT_LOG_ROOT` 覆盖日志目录。

### 上传文件

默认目录：

```text
.runtime/uploads
```

文件上传后，后端会将文件元数据写入 MongoDB，并允许后续任务通过 `file_id` 复用。

### 输出产物

默认目录：

```text
.runtime/outputs
```

任务产物会通过 FastAPI 静态挂载暴露：

```text
/static/outputs
```

当前产物识别类型：

- 图片：`.png`、`.jpg`、`.jpeg`、`.svg`
- 文本：`.txt`、`.md`、`.json`、`.csv`
- PDF：`.pdf`
- 其他类型：`other`

---

## 典型使用流程

### 谱图任务分析

1. 启动 MongoDB 与 RabbitMQ。
2. 启动后端 API。
3. 启动 Celery Worker。
4. 启动前端开发服务或部署前端构建产物。
5. 在前端进入对应谱图任务提交页。
6. 提交任务后进入任务中心或任务详情页查看状态。
7. 任务完成后查看结构化结果、文本报告和输出产物。
8. 如任务失败，优先查看任务详情错误信息与 Worker 日志。

### 评测中心

1. 打开“工具服务 / 评测中心”。
2. 在“解析准确性评测”页签中执行谱解准确性评测，或在“设备重复性评测”页签中执行设备重复性评测。
3. 选择谱图类型或设备类型并启动批次。
4. 等待批次完成。
5. 查看样本详情、设备级汇总、样品组明细与产物链接。
6. 下载 Markdown 报告归档。

### 实验室数据采集

1. 配置 `backend/resources/config/lab_collectors.yaml`。
2. 打开“实验数据 / 数据采集”。
3. 选择采集范围并启动采集批次。
4. 在历史记录中查看采集结果。
5. 打开“实验数据 / 样本管理”查看样本主档与统计信息。

---

## 验证建议

后端基础检查：

- API 服务可启动
- `/api/v1/health` 返回成功
- Celery Worker 可连接 RabbitMQ
- MongoDB 可正常写入任务、结果与采集数据

任务链路检查：

- GPC 任务可提交并完成
- NMR 任务可提交并完成
- IR/Raman/LCMS 任务接口可按配置调用
- 任务状态可从 `PENDING/QUEUED/RUNNING` 流转到 `SUCCESS/FAILED`
- 结果接口与产物接口返回正常

前端检查：

- 工作台可访问
- 任务提交页可访问
- 任务中心可查询任务
- 任务详情可展示结果与产物
- 报告问答、实验采集、样本管理、NMRServer、拉曼批量采集、评测中心页面可进入

---

## 常见问题

### 任务一直停留在 `QUEUED`

优先检查：

- RabbitMQ 是否启动
- Celery Worker 是否启动
- Worker 队列名是否与 `CELERY_TASK_QUEUE` 一致
- Worker 日志是否有连接或导入错误

### 前端请求失败

优先检查：

- 后端 API 是否启动
- `VITE_API_BASE_URL` 是否正确
- 浏览器是否能打开 `http://127.0.0.1:8000/docs`
- 浏览器控制台是否存在跨域、网络或超时错误

### 任务创建成功但结果为空

优先检查：

- Worker 是否实际执行任务
- Worker 日志是否报错
- MongoDB 中任务是否写入 `result_ref`
- `.runtime/outputs` 下是否生成对应产物

### 上传后无法通过 `file_id` 提交任务

优先检查：

- MongoDB 中是否存在文件元数据
- 文件是否落盘到 `.runtime/uploads`
- 提交任务时 `input_type` 与请求参数是否匹配

### Git 分支和远程重构主线不一致

当前远程重构分支是：

```text
origin/develop-vue
```

如果本地仍在 `master`，提交前请确认团队希望继续在本地 `master` 开发，还是切换到跟踪 `origin/develop-vue` 的本地分支。

---

## 参考文档

- `backend/README.md`
- `AGENTS.md`
- `重构验收进度表.md`
- `可优化可重构点总结.md`
- `任务与验收状态流转图.md`
