# Spec Agent

## 项目简介

Spec Agent 是一个面向谱图分析场景的智能分析平台，提供任务提交、异步执行、结果查询、报告查看、问答对话、批量验收和 NMR 预测等能力。

当前项目采用前后端分离架构：

- 后端基于 **FastAPI + Celery + MongoDB + RabbitMQ** 提供 API、任务调度与结果持久化能力。
- 前端基于 **Vue 3 + Vite + Element Plus** 提供任务管理、分析结果查看和工具化交互界面。
- 算法与分析能力主要位于 `backend/analysis`、`backend/agents`、`backend/services`。

支持的主要分析/工具能力：

- GPC 任务分析
- NMR 任务分析
- IR 任务分析
- Raman 任务分析
- LCMS 任务分析
- 报告问答对话
- NMRServer 正向/反向/检索工具
- 批量验收测试与 Markdown 报告下载
- 实验室共享目录数据采集与样本主档管理

---

## 技术栈总览

### 后端

- FastAPI：API 服务入口，见 `backend/app/main.py`
- Celery：异步任务执行，见 `backend/app/worker/celery_app.py`
- MongoDB：任务、结果、文件元数据存储，见 `backend/app/infra/mongo.py`
- MongoDB：同时承载实验采集批次、样本主档与样本文件清单
- RabbitMQ：Celery Broker，见 `backend/app/core/config.py`
- Python 分析模块：位于 `backend/analysis`、`backend/agents`、`backend/services`

### 前端

- Vue 3：应用框架，见 `frontend/src/main.js`
- Vue Router：页面路由，见 `frontend/src/router/index.js`
- Element Plus：UI 组件库
- Axios：API 调用封装，见 `frontend/src/api/specAgentApi.js`
- ECharts：谱图与图表展示
- JSZip：NMR 文件夹前端打包上传能力

---

## 系统架构与任务链路

### 整体架构

```text
前端 Vue 页面
    ↓
FastAPI API（/api/v1）
    ↓
TaskService 创建任务并写入 MongoDB
    ↓
Celery 投递到 RabbitMQ 队列
    ↓
Worker 执行分析任务
    ↓
分析结果写入 MongoDB / 输出文件写入 outputs/
    ↓
前端轮询状态并读取结果、产物、报告
```

### 后端关键入口

- 应用入口：`backend/app/main.py:17`
- 路由聚合：`backend/app/api/v1/router.py:16`
- 任务服务：`backend/app/services/task_service.py:26`
- Worker 执行主逻辑：`backend/app/worker/tasks.py:246`

### 前端关键入口

- 应用启动：`frontend/src/main.js:1`
- 应用壳层：`frontend/src/App.vue:1`
- 路由定义：`frontend/src/router/index.js:13`
- API 封装：`frontend/src/api/specAgentApi.js:3`

---

## 目录结构说明

```text
Spec_Agent/
├─ backend/                  # 后端服务、任务执行、算法与脚本
│  ├─ app/                   # FastAPI 应用主干
│  │  ├─ api/v1/endpoints/   # 各业务接口
│  │  ├─ core/               # 配置
│  │  ├─ infra/              # Mongo 等基础设施
│  │  ├─ models/             # Pydantic 数据模型
│  │  ├─ services/           # 业务服务层
│  │  └─ worker/             # Celery Worker
│  ├─ agents/                # 分析流程编排
│  ├─ analysis/              # 算法实现、模型权重、数据资源
│  ├─ config/                # 业务配置
│  ├─ scripts/               # OpenAPI 导出、回归脚本
│  ├─ requirements.txt       # Python 依赖
│  └─ README.md              # 后端局部说明
├─ frontend/                 # Vue 前端
│  ├─ src/
│  │  ├─ api/                # Axios API 封装
│  │  ├─ components/         # 通用组件
│  │  ├─ router/             # 路由定义
│  │  ├─ views/              # 页面视图
│  │  ├─ App.vue             # 应用壳层
│  │  └─ main.js             # 启动入口
│  └─ package.json           # 前端依赖与脚本
├─ uploads/                  # 上传输入文件目录
├─ outputs/                  # 任务输出产物、报告目录
└─ API草案-v1.md             # 接口设计草案
```

---

## 环境准备

建议本地准备以下基础环境：

- Python 3.10+
- Node.js 18+
- MongoDB
- RabbitMQ

如果使用 Conda，可为后端单独准备一个虚拟环境。

---

## 后端安装与启动

后端已有基础启动说明，见 `backend/README.md:3`。

### 1. 安装依赖

```bash
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
pip install -r requirements.txt
```

### 2. 启动 API 服务

```bash
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 启动 Celery Worker

```bash
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
python -m celery -A app.worker.celery_app:celery_app worker --loglevel=info -Q spec_agent -P solo
```

推荐使用 `python -m celery` 形式，避免 Windows 下 `celery.exe` 入口脚本的模块路径差异问题。

### 4. 接口文档

后端应用默认提供 Swagger 文档；前端“接口文档”菜单会直接打开：

- `http://127.0.0.1:8000/docs`

前端该入口见 `frontend/src/App.vue:42`。

---

## 前端安装与启动

前端启动脚本定义在 `frontend/package.json:6`。

### 1. 安装依赖

```bash
cd E:/xx_project/Spec_Agent/frontend
npm install
```

### 2. 启动开发环境

```bash
cd E:/xx_project/Spec_Agent/frontend
npm run dev
```

### 3. 构建生产包

```bash
cd E:/xx_project/Spec_Agent/frontend
npm run build
```

### 4. 本地预览构建产物

```bash
cd E:/xx_project/Spec_Agent/frontend
npm run preview
```

---

## 环境变量说明

后端通过 `backend/app/core/config.py:11` 自动加载 `backend/.env`，变量样例可参考 `backend/.env.example:1`。

### 核心变量

| 变量名 | 说明 |
| --- | --- |
| `APP_ENV` | 运行环境标记，默认 `dev` |
| `MONGODB_HOST` | MongoDB 主机 |
| `MONGODB_PORT` | MongoDB 端口 |
| `MONGODB_USERNAME` | MongoDB 用户名 |
| `MONGODB_PASSWORD` | MongoDB 密码 |
| `MONGODB_DATABASE` | MongoDB 数据库名 |
| `RABBITMQ_HOST` | RabbitMQ 主机 |
| `RABBITMQ_PORT` | RabbitMQ 端口 |
| `RABBITMQ_USERNAME` | RabbitMQ 用户名 |
| `RABBITMQ_PASSWORD` | RabbitMQ 密码 |
| `RABBITMQ_VHOST` | RabbitMQ vhost |
| `CELERY_TASK_QUEUE` | Celery 队列名，默认 `spec_agent` |
| `NMR_SERVER_BASE_URL` | 外部 NMRServer 服务地址 |

### 后端默认目录约定

以下目录由配置对象自动推导：

- 上传目录：`uploads/`
- 输出目录：`outputs/`
- API 前缀：`/api/v1`

相关代码见 `backend/app/core/config.py:24`。

### 前端环境变量

前端 API 基础地址定义在 `frontend/src/api/specAgentApi.js:3`：

- `VITE_API_BASE_URL`

若未配置，则默认使用：

- `http://127.0.0.1:8000/api/v1`

> 注意：`backend/.env.example` 中当前包含真实风格地址与口令示例，仅应作为格式参考，实际部署前请改为本地或正式环境配置。

---

## 核心功能说明

### 1. 工作台

页面：`frontend/src/views/DashboardView.vue`

用于展示任务总览、状态分布和近期任务，作为平台首页入口。

### 2. 任务提交

路由定义见 `frontend/src/router/index.js:16`。

目前包含四类任务提交页：

- `/tasks/submit/gpc`
- `/tasks/submit/nmr`
- `/tasks/submit/ir`
- `/tasks/submit/raman`
- `/tasks/submit/lcms`

对应页面：

- `frontend/src/views/TaskSubmitGpcView.vue`
- `frontend/src/views/TaskSubmitNmrView.vue`
- `frontend/src/views/TaskSubmitIrRamanView.vue`

支持的输入方式包括：

- 本地文件路径
- 本地目录路径
- 上传文件后通过 `file_id` 复用

### 3. 任务中心

页面：`frontend/src/views/TaskCenterView.vue`

能力包括：

- 任务列表分页查询
- 按状态/任务类型筛选
- 跳转任务详情

后端接口位于：`backend/app/api/v1/endpoints/tasks.py:25`。

### 4. 任务详情与产物查看

页面：`frontend/src/views/TaskDetailView.vue`

能力包括：

- 查看任务状态
- 查看结构化结果
- 查看文本报告
- 查看任务产物列表
- 渲染图像、谱图或 JSON 结果

任务产物接口见：`backend/app/api/v1/endpoints/tasks.py:163`。

### 5. 报告问答对话

页面：`frontend/src/views/DialogueView.vue`

能力包括：

- 查询分析类型列表
- 查询历史报告列表
- 基于报告进行问答对话

前端调用封装见：

- `frontend/src/api/specAgentApi.js:144`
- `frontend/src/api/specAgentApi.js:158`
- `frontend/src/api/specAgentApi.js:174`

### 6. NMRServer 工具

页面：`frontend/src/views/ToolNmrServerView.vue`

支持三类能力：

- 正向预测
- 反向预测
- 数据库搜索

对应前端接口封装见：

- `frontend/src/api/specAgentApi.js:83`
- `frontend/src/api/specAgentApi.js:88`
- `frontend/src/api/specAgentApi.js:93`

### 7. 批量验收测试

页面：`frontend/src/views/ToolAcceptanceView.vue`

后端接口见 `backend/app/api/v1/endpoints/acceptance.py:23`，支持：

- 读取验收配置摘要
- 启动验收批次（直接批量执行解析，不提交任务中心）
- 查询批次历史
- 查看批次状态
- 下载 Markdown 验收报告
- 查看页内样本详情与产物链接

---

## 典型使用流程

### 任务分析主流程

1. 启动 MongoDB、RabbitMQ、后端 API、Celery Worker、前端页面。
2. 在左侧菜单进入对应任务提交页。
3. 选择输入方式并填写分析参数。
4. 提交任务后记录返回的 `task_id`。
5. 在“任务中心”或“任务详情”页轮询任务状态。
6. 任务成功后查看：
   - 结构化结果
   - 文本报告
   - 输出产物
7. 如任务失败，在详情中查看失败状态与错误信息。

### 批量验收流程

1. 打开“工具服务 / 批量验收测试”。
2. 读取后端验收配置摘要。
3. 选择谱图类型并启动批量运行。
4. 轮询批次状态。
5. 完成后在当前页面查看总体指标、样本详情与产物链接。
6. 如需归档，打开历史记录或下载 Markdown 报告。

### 报告问答流程

1. 打开“问答对话”页面。
2. 选择分析类型。
3. 选择报告。
4. 输入问题并发起请求。
5. 查看多轮问答结果。

---

## API 与开发辅助脚本

### API 路由总览

后端通过 `backend/app/api/v1/router.py:16` 聚合以下模块：

- `health`
- `files`
- `tasks`
- `nmr_server`
- `chemistry`
- `spectra`
- `dialogue`
- `acceptance`

### 已确认的核心接口

- `GET /api/v1/health`
- `POST /api/v1/files/upload`
- `GET /api/v1/tasks`
- `POST /api/v1/tasks/gpc`
- `POST /api/v1/tasks/nmr`
- `POST /api/v1/tasks/ir`
- `POST /api/v1/tasks/raman`
- `POST /api/v1/tasks/lcms`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/result`
- `GET /api/v1/tasks/{task_id}/artifacts`
- `GET /api/v1/acceptance/config`
- `POST /api/v1/acceptance/run`
- `GET /api/v1/acceptance/runs`
- `GET /api/v1/acceptance/run/{run_id}`
- `GET /api/v1/acceptance/run/{run_id}/report`
- `GET /api/v1/lab-collect/config`
- `POST /api/v1/lab-collect/run`
- `GET /api/v1/lab-collect/runs`
- `GET /api/v1/lab-collect/run/{run_id}`
- `GET /api/v1/lab-collect/samples`
- `GET /api/v1/lab-collect/samples/{sample_id}`

### 导出 OpenAPI

脚本：`backend/scripts/export_openapi.py:16`

```bash
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
python scripts/export_openapi.py
```

导出文件：

- `backend/openapi.json`

### 回归脚本

脚本：`backend/scripts/run_regression.py:100`

```bash
cd E:/xx_project/Spec_Agent/backend
conda activate Spec_Agent
python scripts/run_regression.py
```

该脚本当前会执行：

- 健康检查
- GPC 用例提交与轮询
- NMR 用例提交与轮询
- 结果接口检查

相关环境变量：

- `REG_BASE_URL`
- `REG_GPC_PATH`
- `REG_NMR_PATH`

---

## 测试与回归

当前仓库更偏向脚本式回归验证，已明确可用入口为：

- `backend/scripts/run_regression.py`

建议至少执行以下检查：

### 后端检查

- API 能正常启动
- `/api/v1/health` 返回成功
- Celery Worker 能连接 RabbitMQ
- MongoDB 可写入任务与结果

### 任务链路检查

- 可成功提交 GPC 任务
- 可成功提交 NMR 任务
- 任务状态可从 `PENDING/QUEUED/RUNNING` 流转到 `SUCCESS/FAILED`
- 结果接口与产物接口可正确返回

### 前端检查

- 工作台可访问
- 任务提交页可打开
- 任务中心可查询到任务
- 任务详情页可展示结果
- 问答、NMRServer、批量验收页面可进入

---

## 常见目录说明

### `uploads/`

用于存放上传的原始输入文件。后端在文件上传成功后会记录文件元数据，并支持通过 `file_id` 进行后续任务提交。

### `outputs/`

用于存放任务执行产物与报告。当前任务产物查询逻辑会扫描：

- `outputs/tasks/{task_id}`

对应代码见：`backend/app/services/task_service.py:191`。

当前支持识别的产物类型包括：

- 图片：`.png`、`.jpg`、`.jpeg`、`.svg`
- 文本：`.txt`、`.md`、`.json`、`.csv`
- PDF：`.pdf`
- 其他类型：归类为 `other`

并通过 `/static/outputs/...` 形式暴露访问地址，见 `backend/app/main.py:33`。

---

## FAQ

### 1. 为什么任务一直停留在 `QUEUED`？

优先检查：

- RabbitMQ 是否正常启动
- Celery Worker 是否已启动
- 队列名是否与 `CELERY_TASK_QUEUE` 一致

### 2. 为什么前端请求失败？

优先检查：

- 后端 API 是否启动
- `VITE_API_BASE_URL` 是否正确
- 浏览器访问 `/docs` 是否可打开

### 3. 为什么任务创建成功但结果为空？

优先检查：

- Worker 日志是否报错
- MongoDB 是否成功写入 `result_ref`
- `outputs/tasks/{task_id}` 下是否存在产物

### 4. 为什么上传后无法通过 `file_id` 提交任务？

优先检查：

- MongoDB 中对应文件元数据是否存在
- 上传文件是否实际落盘到 `uploads/`
- `input_type` 是否与提交方式匹配

---

## 参考文件

- 可优化/可重构点总结：`可优化可重构点总结.md`
- 后端局部说明：`backend/README.md`
- 接口草案：`API草案-v1.md`
- 后端入口：`backend/app/main.py`
- 路由聚合：`backend/app/api/v1/router.py`
- 任务服务：`backend/app/services/task_service.py`
- Worker：`backend/app/worker/tasks.py`
- 前端入口：`frontend/src/main.js`
- 前端路由：`frontend/src/router/index.js`
- 前端 API：`frontend/src/api/specAgentApi.js`
