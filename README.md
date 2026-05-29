# Spec Agent

面向表征实验谱图的智能解析与分析平台。

基于 **FastAPI + Vue 3 + Celery + MongoDB** 构建的前后端分离工程化系统，支持 GPC、NMR、IR、Raman、LCMS 等多种谱图的智能解析、任务管理与评测。

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 谱图智能解析 | GPC / NMR / IR / Raman / LCMS 任务提交、异步执行、结果查看 |
| 报告问答 | 基于 LLM 的报告内容问答对话 |
| NMRServer 工具 | 正向预测、反向预测、数据库搜索 |
| 拉曼批量采集 | 光谱仪远程采集，含信噪比指标与谱图下载 |
| LCMS 数据转化 | 原始数据格式转化（依赖 ProteoWizard） |
| 评测中心 | 解析准确性评测、设备重复性评测、Markdown 报告下载 |
| 实验数据管理 | 共享目录采集、样本主档管理、分子资产统计 |
| 登录鉴权 | 本地账号密码登录（可选启用） |

## 技术栈

**后端：** FastAPI / Celery / RabbitMQ / MongoDB / PyTorch（Graphormer 等深度学习模型）

**前端：** Vue 3 + Vite + Element Plus

**部署：** Docker Compose / PM2 / 命令行

## 系统架构

```text
Vue 前端 → Axios (Token 鉴权) → FastAPI /api/v1
  → Service 层 → Celery + RabbitMQ → Worker 执行分析
  → 结果写入 MongoDB + .runtime/outputs
  → 前端轮询展示
```

## 快速开始

### 环境要求

- Python 3.12+ / Conda 环境 `Spec_Agent`
- Node.js 18+（仅构建前端时需要）
- Docker / Docker Compose（推荐）
- MongoDB / RabbitMQ

## 部署模式

### Docker 生产部署

正式环境推荐使用完整 Docker 部署，对外仅暴露 `Nginx` 端口，`MongoDB` 与 `RabbitMQ` 默认仅容器内访问。

```bash
cp docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
# 旧版环境可使用：
# docker-compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
```

默认访问地址：`http://127.0.0.1:20080`

无 root 权限服务器可使用：

```bash
bash docker/up.sh
```

### Windows / Linux 原生部署

若需要保留原生部署方式，建议仍使用 Docker 提供 `MongoDB` 与 `RabbitMQ`，并通过 native override 暴露为本机回环端口：

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.native.yml up -d mongodb rabbitmq
# 旧版环境可使用：
# docker-compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.native.yml up -d mongodb rabbitmq
```

随后通过命令行或 `PM2` 启动服务。

PM2 支持两种模式：

- 全量模式：前端 `vite preview` + backend + worker
  ```bash
  pm2 start ecosystem.config.js
  ```
- 简化模式：仅 backend + worker，前端需先 `npm run build`，再由 FastAPI 自动托管 `frontend/dist`
  ```bash
  pm2 start ecosystem.slim.config.js
  ```

当前华为服务器因无 root 权限，已验证可通过 rootless Docker 的 `vfs` 存储驱动运行。脚本入口见 `docker/rootless-vfs-start.sh` 与 `docker/up.sh`。

### 后端启动

```bash
cd backend
conda activate Spec_Agent
cp .env.example .env          # 按需修改配置
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 另起终端启动 Worker
python -m celery -A app.worker.celery_app:celery_app worker --loglevel=info -Q spec_agent -P solo
```

当 `frontend/dist/` 存在时，后端自动托管前端静态文件，访问 http://127.0.0.1:8000 即可使用。

### 前端构建（首次或更新后）

```bash
cd frontend
npm install
npm run build
```

开发调试时可单独启动前端热重载服务：

```bash
npm run dev
```

如需修改前端开发代理目标，可在 `frontend/.env` 中设置 `VITE_DEV_API_PROXY_TARGET`。

接口文档：http://127.0.0.1:8000/docs

## 目录结构

```text
Spec_Agent/
├─ backend/
│  ├─ analysis/         # 算法分析层（GPC/NMR/Raman，含深度学习模型）
│  ├─ app/              # FastAPI 应用（API / 服务 / 模块 / Worker）
│  ├─ resources/        # 配置文件与模型资源
│  ├─ scripts/          # OpenAPI 导出、回归测试脚本
│  └─ tests/            # 后端单元测试
├─ frontend/
│  └─ src/              # Vue 3 前端源码
├─ scripts/             # 独立工具脚本（NMR 预测、一致性评测等）
├─ docs/                # 设计文档
└─ .runtime/            # 运行时目录（uploads / outputs）
```

## 文档

- [后端技术文档](backend/README.md) — API 接口、环境变量、架构详解、开发脚本
- [部署文档导航](docs/deployment/README.md) — Docker、原生部署与已知限制
- [重构验收进度表](重构验收进度表.md) — 各模块完成度与里程碑
- [CLAUDE.md](CLAUDE.md) — AI 编码行为准则
