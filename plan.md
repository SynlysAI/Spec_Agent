# Spec_Agent 重构上线方案（Plan）

## 1. 项目背景与目标

- 当前项目为重构项目，源项目路径：`E:\github_project\Spec_Agent`
- 源项目是一个面向多种表征实验谱图（GPC/NMR/IR/Raman 等）的智能解析 Agent 系统
- 现状为 `streamlit` Demo 形态，已不适合正式上线
- 目标是改造为可正式上线、可持续迭代的工程化系统

### 1.1 重构目标

- 保持源项目核心分析能力与结果口径一致
- 前后端解耦，支持多用户并发与权限管理扩展
- 支持长耗时任务异步执行、可观测、可追踪
- 架构可扩展到更多谱图类型与更多 Agent

## 2. 技术架构选型

## 2.1 总体架构

- 前端：`Vue3 + Vite + Element Plus + Plotly/ECharts`
- 后端 API：`FastAPI`
- 异步任务：`Celery + RabbitMQ`
- 数据存储：`MongoDB`
- 文件存储：本地目录（后续可切换 MinIO/NAS）
- 网关与部署：`Nginx + Docker Compose`（后续可升级 K8s）

## 2.2 选型说明

- 使用 `FastAPI` 替代 `streamlit` 作为线上主服务框架
- 使用 `RabbitMQ` 作为任务队列 Broker（复用现有服务）
- 使用 `MongoDB` 存储任务、结果元数据、日志与会话等文档型数据
- 不强依赖 Redis（当前阶段可不引入）

## 3. 目标系统分层设计

## 3.1 分层结构

- `presentation`：Web 前端（页面、表单、任务看板、结果可视化）
- `api`：统一 HTTP/WebSocket 接口层（鉴权、参数校验、路由）
- `application`：任务编排层（提交任务、查询状态、聚合结果）
- `domain`：谱图分析领域层（复用 `agents/analysis/services` 核心逻辑）
- `infrastructure`：MongoDB、RabbitMQ、文件存储、日志、配置

## 3.2 任务执行模式

- 同步接口只负责“创建任务并返回任务ID”
- 重计算在 Celery Worker 异步执行
- 前端通过轮询/WebSocket 获取任务进度与结果
- 任务失败保留错误堆栈与可重试能力

## 4. 数据与任务模型（建议）

## 4.1 核心集合（MongoDB）

- `tasks`：任务主表（类型、状态、参数、进度、耗时、错误）
- `analysis_results`：结构化结果与报告索引
- `files`：输入/输出文件元数据（路径、hash、大小、归属）
- `audit_logs`：操作审计日志（用户、动作、时间）

## 4.2 任务状态机（统一）

- `PENDING`：已创建
- `QUEUED`：已入队
- `RUNNING`：执行中
- `SUCCESS`：成功
- `FAILED`：失败
- `CANCELED`：已取消（二期）

## 5. API 规划（第一批）

- `POST /api/v1/tasks/gpc`：提交 GPC 分析任务
- `POST /api/v1/tasks/nmr`：提交 NMR 分析任务
- `POST /api/v1/tasks/ir`：提交 IR 分析任务
- `POST /api/v1/tasks/raman`：提交 Raman 分析任务
- `GET /api/v1/tasks/{task_id}`：查询任务状态与进度
- `GET /api/v1/tasks/{task_id}/result`：获取任务结果
- `POST /api/v1/files/upload`：上传谱图文件
- `GET /api/v1/health`：服务健康检查

## 6. 与现有代码的迁移策略

## 6.1 可复用模块

- `agents/*`：保留并改为 API/Worker 调用入口
- `analysis/*`：保留领域算法能力
- `services/*`：逐步去除 Streamlit 会话耦合，沉淀为纯服务层
- `spec_cli/*`：保留为运维/离线任务入口

## 6.2 需要改造模块

- `streamlit_webui.py` 与 `web_pages/*`：退出主流程，改为历史 Demo
- 配置体系：拆分为 `dev/test/prod`，去除硬编码本地路径
- 输出目录：统一按任务ID隔离，便于追踪和归档
- 解析能力迁移：由“运行时复用源项目模块”逐步迁移为“本项目内聚代码”，最终实现独立部署

## 7. 分阶段实施计划

## 7.1 Phase 0：基线确认（1 周）

- 梳理源项目功能清单与输出口径
- 制定“重构不改变核心结果”的验收样本集
- 输出接口契约初稿与任务状态标准

交付物：

- `需求-能力映射表`
- `验收样本清单`
- `API 草案`

## 7.2 Phase 1：后端最小可用（2 周）

- 建立 FastAPI 骨架与统一异常处理
- 建立 Celery + RabbitMQ 任务链路
- 建立 MongoDB 任务与结果持久化
- 打通 GPC/NMR 两类任务提交与查询

交付物：

- 可运行后端服务
- GPC/NMR 任务全链路
- OpenAPI 文档

当前进度（2026-04-10）：

- 已完成：FastAPI 骨架与统一异常处理
- 已完成：Celery + RabbitMQ + MongoDB 任务链路
- 已完成：GPC/NMR 任务提交、执行、查询、结果获取
- 已完成：`backend/scripts/export_openapi.py` 与 `backend/openapi.json`
- 已完成：`backend/scripts/run_regression.py`（真实样本回归通过）
- 未完成：IR/Raman（按决策延后至 P1）


交付物：

- 前端 MVP
- 端到端流程（上传 -> 提交 -> 查看结果）

## 7.4 Phase 3：能力补齐与稳定性（2~3 周）

- 接入 IR/Raman 分析任务
- 增加日志追踪、基础监控、告警
- 增加失败重试与超时控制
- 完成回归测试与性能压测

交付物：

- 全谱图类型支持
- 稳定性报告与压测报告

## 7.5 Phase 4：上线准备（1 周）

- 生产配置固化与发布脚本
- 灰度发布与回滚预案
- 运维手册与应急手册
- 完成独立部署验收：移除对 `E:\\github_project\\Spec_Agent` 的运行时依赖

交付物：

- `docker-compose` 生产部署包
- 上线手册与回滚手册

## 8. 质量与验收标准

- 功能一致性：与源项目核心样本结果偏差在可接受阈值内
- 稳定性：关键任务成功率 >= 99%（剔除无效输入）
- 可观测性：任务可追踪、错误可定位、日志可检索
- 性能：并发场景下任务排队与执行稳定，无服务雪崩

## 9. 风险与应对

- 算法逻辑与 UI 耦合风险：先抽离服务层，再接 API
- 长任务阻塞风险：严格异步化，设置超时和重试策略
- 文件管理混乱风险：统一文件命名与任务目录隔离规范
- 环境差异风险：固定依赖版本，提供标准化镜像

## 10. 下一步执行建议

- 按 Phase 0 先输出“能力映射+验收样本+API 草案”三件套
- 先落地 GPC/NMR 两条链路，快速形成可演示闭环
- 闭环稳定后再扩展 IR/Raman，避免一次性范围过大
- 在功能稳定后启动“代码内聚迁移”专项，确保最终可脱离源项目目录独立运行
