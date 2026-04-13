# Spec_Agent 重构计划与进展（更新于 2026-04-13）

## 1. 目标与边界

- 源项目：`E:\github_project\Spec_Agent`（`streamlit_webui.py` + `web_pages/*`）
- 重构项目：`E:\xx_project\Spec_Agent`（前后端分离）
- 当前阶段目标：完成工程化收口，进入可上线治理阶段
- 最终目标：正式发布版本必须可独立部署，运行时不依赖 `E:\github_project\Spec_Agent`

## 2. 源项目能力基线（按入口 `streamlit_webui.py`）

源项目共 9 类入口能力：

1. 服务状态
2. GPC 分析
3. NMR 分析
4. NMRServer（正向/反向/数据库搜索）
5. Raman/IR 分析
6. LC-MS（占位）
7. 数据管理
8. 问答对话
9. 验收测试

## 3. 当前重构进展评估

## 3.1 文档与基线（Phase 0）

- 已完成：`需求-能力映射表.md`
- 已完成：`验收样本清单.md`
- 已完成：`API草案-v1.md`
- 已完成：`重构验收进度表.md` 持续维护

结论：基线文档可支撑持续验收与排期管理。

## 3.2 后端（FastAPI + Celery + RabbitMQ + MongoDB）

已实现接口（以 `backend/openapi.json` 与路由实现为准）：

- `GET /api/v1/health`
- `POST /api/v1/files/upload`
- `GET /api/v1/tasks`
- `POST /api/v1/tasks/gpc`
- `POST /api/v1/tasks/nmr`
- `POST /api/v1/tasks/ir`
- `POST /api/v1/tasks/raman`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/result`
- `GET /api/v1/tasks/{task_id}/artifacts`
- `POST /api/v1/nmrserver/forward`
- `POST /api/v1/nmrserver/reverse`
- `POST /api/v1/nmrserver/search`
- `POST /api/v1/chemistry/render`
- `POST /api/v1/spectra/preview`
- `GET /api/v1/dialogue/analysis-types`
- `GET /api/v1/dialogue/reports`
- `POST /api/v1/dialogue/chat`
- `GET /api/v1/acceptance/config`
- `POST /api/v1/acceptance/run`
- `GET /api/v1/acceptance/run/{run_id}`
- `GET /api/v1/acceptance/run/{run_id}/report`

已完成能力：

- 统一响应结构与异常处理
- 任务状态机流转（`PENDING -> QUEUED -> RUNNING -> SUCCESS/FAILED`）
- GPC/NMR/IR/Raman 异步任务执行与结果落库
- 文件上传入库（`files` 集合）与任务输入 `file_id` 解析
- 输出产物静态托管（`/static/outputs`）
- NMRServer 三能力、问答首版、验收首版
- OpenAPI 导出脚本与回归脚本

当前关键缺口：

- 数据管理 API 尚未落地（列表、筛选、删除、索引）
- `health` 中 `worker` 状态仍为固定 `"up"`，缺少真实探活
- 任务 `options`（如 `priority/callback_url`）尚未进入调度与回调链路
- 验收运行态使用进程内存存储，服务重启后状态不可恢复
- 缺少鉴权、审计日志、可观测性指标与统一追踪 ID

## 3.3 前端（Vue3 + Vite + Element Plus）

已完成页面：

- 工作台：`/dashboard`
- 任务提交：`/tasks/submit/gpc`、`/tasks/submit/nmr`、`/tasks/submit/ir`、`/tasks/submit/raman`
- 任务中心：`/tasks/center`
- 任务详情：`/tasks/detail/:taskId`
- 问答：`/dialogue`
- 工具服务：`/tools/nmrserver`、`/tools/acceptance`

已打通链路：

- 上传 -> 提交任务 -> 轮询查询 -> 查看结构化结果/文本报告/图像产物
- 问答：分析类型/报告列表/问答闭环
- 验收：触发批量运行 -> 查询进度 -> 下载报告

当前关键缺口：

- 数据管理页面未迁移
- 服务状态页未按源项目能力重建（当前为基础任务看板）
- 缺少登录鉴权与用户维度权限控制

## 3.4 本轮同步更新（2026-04-13）

- 同步修正文档口径：将已落地的 IR/Raman、NMRServer、问答、验收接口与页面标记为“已实现”
- 明确当前真实阻塞项：数据管理、运行治理、可观测与上线规范
- 将后续计划从“功能补齐为主”调整为“上线治理为主，数据管理并行”

## 3.5 结论（截至 2026-04-13）

- 当前状态：功能能力已接近源项目等价覆盖（除数据管理、LC-MS占位）
- 覆盖情况：源项目 9 类能力中，已实装 7 类主能力（GPC/NMR/IR/Raman/NMRServer/问答/验收）
- 最大阻塞项：数据管理中心与工程化上线治理能力

## 4. 阶段状态看板

| 阶段 | 范围 | 当前状态 | 完成度 |
| --- | --- | --- | --- |
| Phase 0 | 基线梳理与文档 | 已完成 | 100% |
| Phase 1 | 后端 P0 主链路（GPC/NMR） | 已完成并稳定运行 | 96% |
| Phase 2 | 前端 P0/P1 页面闭环 | 已完成主要功能迁移 | 90% |
| Phase 3 | 能力补齐（IR/Raman/NMRServer/数据/问答/验收） | 基本完成，剩余数据管理 | 88% |
| Phase 4 | 工程化上线（独立部署、监控、发布） | 进行中 | 32% |

## 5. 后续计划（按优先级）

## 5.1 上线治理收口（优先级 P0，目标 1~2 周）

1. 健康检查补齐 worker 真探活（替换固定 `worker=up`）。
2. 增加统一追踪 ID（请求链路、任务链路、错误链路）。
3. 增加结构化日志与基础指标（任务耗时、失败率、队列深度）。
4. 明确并实现任务 `options` 契约（优先级、回调）。
5. 验收批次状态入库，避免进程重启丢失。

交付物：

- 上线治理验收清单（Markdown）
- 观测与探活方案说明

## 5.2 能力补齐（优先级 P1，目标 1~2 周）

1. 新增数据管理 API（结果查询、分页、删除、文件索引）。
2. 新增数据管理前端页面并接入路由与权限位。
3. 补齐问答会话持久化与历史会话查询。

交付物：

- 功能等价迁移清单（目标 9/9，LC-MS 保持占位说明）
- P1 功能验收报告

## 5.3 独立部署与发布规范（优先级 P0/P1 并行，目标 2 周）

1. 完成配置分层（`dev/test/prod`）与敏感配置脱敏。
2. 输出 `docker-compose` 部署、灰度与回滚流程。
3. 增加长任务可靠性策略：超时、重试、失败分类标准化。

交付物：

- 独立部署验收证明
- 部署手册、回滚手册

## 6. 近期执行清单（建议直接按此排期）

第 1 周：

- 完成 worker 真探活与 request_id 链路
- 明确并落地 `options` 契约

第 2 周：

- 完成数据管理后端 API + 前端页面 MVP
- 验收运行态持久化改造

第 3~4 周：

- 完成观测指标与结构化日志
- 完成部署脚本、灰度与回滚演练

## 7. 风险与应对

- 运行治理风险：先补探活与可观测，再扩大并发与外部联调。
- 数据模型漂移风险：为结构化结果维护字段版本与兼容层。
- 线上稳定性风险：验收批次状态必须持久化，避免重启丢失进度。
- 发布风险：必须在独立部署环境完成全量回归后再发布。
