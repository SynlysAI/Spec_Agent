# Spec_Agent 正式发布整理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `Spec_Agent` 整理为支持 `Windows/Linux` 原生部署与 `Docker` 生产部署的正式发布版，并完成仓库文档、部署骨架和配置治理的第一轮落地。

**Architecture:** 采用 `Nginx + Frontend + FastAPI + Celery Worker + MongoDB + RabbitMQ` 的 Docker 发布结构，同时保留原生命令行和 `PM2` 启动方式。统一使用环境变量管理配置，默认收口数据库和 MQ 到 Docker 内部网络。

**Tech Stack:** FastAPI、Vue 3、Vite、Celery、MongoDB、RabbitMQ、Docker Compose、Nginx、PM2

---

### Task 1: 文档纳管与正式设计落盘

**Files:**
- Modify: `.gitignore`
- Create: `docs/superpowers/specs/2026-05-29-spec-agent-release-design.md`
- Create: `docs/superpowers/plans/2026-05-29-spec-agent-release-plan.md`

- [ ] **Step 1: 调整文档版本管理规则**

确保根 `.gitignore` 不再忽略整个 `docs/`，但继续忽略 `.codegraph/` 等本地工具目录。

- [ ] **Step 2: 写入正式设计文档**

将正式发布目标、架构、配置治理、Docker 策略、多平台兼容要求写入设计文档。

- [ ] **Step 3: 写入实施计划文档**

将后续实施拆解为清晰任务，覆盖仓库整理、部署骨架、配置治理和验证路径。

- [ ] **Step 4: 人工自检文档一致性**

检查设计文档与实施计划中的目标、边界和术语是否一致。

### Task 2: 整理正式部署入口与说明文档

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `frontend/README.md`
- Create: `docs/deployment/README.md`

- [ ] **Step 1: 收敛根 README 为正式入口**

明确 3 种运行方式：`Windows 原生`、`Linux 原生`、`Docker 生产`，并说明数据库与 MQ 默认由 Docker 提供。

- [ ] **Step 2: 修正后端文档接口和部署口径**

确保 `auth`、`Docker`、运行目录、环境变量和当前代码实际行为一致。

- [ ] **Step 3: 重写前端 README**

移除默认 `Vite` 模板说明，补充本项目的开发、构建和接入方式。

- [ ] **Step 4: 增加部署导航文档**

在 `docs/deployment/README.md` 中概述部署模式和对应入口文档。

### Task 3: 收敛旧 PM2 配置与前端模板残留

**Files:**
- Modify: `ecosystem.config.js`
- Delete: `frontend/src/components/HelloWorld.vue`
- Delete: `frontend/src/assets/vite.svg`
- Delete: `frontend/src/assets/vue.svg`
- Delete: `frontend/src/assets/hero.png`

- [ ] **Step 1: 重写 PM2 配置**

只保留 `spec-agent-backend`、`spec-agent-worker`、`spec-agent-frontend` 3 个进程定义，并改成基于环境变量的跨平台配置。

- [ ] **Step 2: 删除无用前端模板文件**

删除未被引用的默认模板组件和图标资源。

- [ ] **Step 3: 检查是否仍有引用**

确认前端源码中不再引用这些模板文件。

### Task 4: 配置示例与开发脚本去环境耦合

**Files:**
- Modify: `backend/.env.example`
- Modify: `frontend/.env.example`
- Modify: `backend/scripts/run_regression.py`
- Modify: `backend/analysis/raman/beam_search.py`

- [ ] **Step 1: 清理后端示例配置中的固定 IP 与 Windows 路径**

将 `MongoDB`、`RabbitMQ`、外部服务地址改为本地安全默认值，将样本路径改为跨平台示例。

- [ ] **Step 2: 补充前端环境变量说明**

让 `frontend/.env.example` 明确适用于原生开发和反向代理两种场景。

- [ ] **Step 3: 收敛回归脚本默认路径**

避免 `run_regression.py` 默认指向固定 Windows 路径，改为要求显式配置或使用仓库内示例路径。

- [ ] **Step 4: 清理分析脚本中的个人路径示例**

将 `beam_search.py` 中 `__main__` 示例改为安全占位或删除。

### Task 5: Docker 与 Nginx 正式部署骨架

**Files:**
- Create: `.dockerignore`
- Create: `docker/backend.Dockerfile`
- Create: `docker/frontend.Dockerfile`
- Create: `docker/nginx/default.conf`
- Modify: `docker/docker-compose.yml`

- [ ] **Step 1: 增加 Docker 构建忽略规则**

避免将 `.git`、`.runtime`、日志、缓存、IDE 文件打包进镜像上下文。

- [ ] **Step 2: 增加后端与 Worker 共用镜像 Dockerfile**

提供基础 Python 镜像安装逻辑，并为 ARM64 风险保留说明。

- [ ] **Step 3: 增加前端多阶段构建 Dockerfile**

前端在构建阶段产出 `dist`，运行期交由 `Nginx` 托管。

- [ ] **Step 4: 增加 Nginx 配置**

托管前端静态资源并将 `/api`、`/static` 转发到后端。

- [ ] **Step 5: 重写 Compose 编排**

包含 `nginx`、`backend`、`worker`、`mongodb`、`rabbitmq`，并确保数据库与 MQ 默认不暴露宿主机端口，仅在 debug profile 下开放。

### Task 6: 基础验证与结果汇总

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `frontend/README.md`
- Modify: `docs/deployment/README.md`

- [ ] **Step 1: 运行基础静态检查**

检查关键文件是否存在、是否有错误引用、文档路径是否可访问。

- [ ] **Step 2: 运行最小测试或语法验证**

至少执行与配置相关的后端测试，以及前端构建验证。

- [ ] **Step 3: 汇总 ARM64 风险与未完成项**

明确哪些项已经落地，哪些项仍需在下一轮继续推进。

- [ ] **Step 4: 更新文档中的验证说明**

将当前实际验证结果与已知限制回写到部署文档中。
