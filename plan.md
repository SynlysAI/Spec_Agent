# Spec_Agent 重构计划与进展（更新于 2026-04-12）

## 1. 目标与边界

- 源项目：`E:\github_project\Spec_Agent`（`streamlit_webui.py` + `web_pages/*`）
- 重构项目：`E:\xx_project\Spec_Agent`（前后端分离）
- 当前阶段目标：先完成 `GPC + NMR + 任务中心 + 文件上传` 主链路，形成可演示闭环
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

结论：Phase 0 基线文档已落地，可作为后续迭代验收标准。

## 3.2 后端（FastAPI + Celery + RabbitMQ + MongoDB）

已实现接口（以 `backend/openapi.json` 为准）：

- `GET /api/v1/health`
- `POST /api/v1/files/upload`
- `GET /api/v1/tasks`
- `POST /api/v1/tasks/gpc`
- `POST /api/v1/tasks/nmr`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/result`
- `GET /api/v1/tasks/{task_id}/artifacts`

已完成能力：

- 统一响应结构与异常处理
- 任务状态机流转（`PENDING -> QUEUED -> RUNNING -> SUCCESS/FAILED`）
- GPC/NMR 异步任务执行与结果落库
- 文件上传入库（`files` 集合）与任务输入 `file_id` 解析
- 输出产物静态托管（`/static/outputs`）
- OpenAPI 导出脚本与 P0 回归脚本

当前关键缺口：

- IR/Raman、NMRServer、数据管理、问答、验收等 API 尚未落地
- Worker 仍通过 `SOURCE_SPEC_AGENT_ROOT` 动态导入源项目模块，尚未独立部署
- `health` 中 `worker` 状态当前为固定 `"up"`，缺少真实探活
- 缺少鉴权、审计日志、可观测性指标与统一追踪 ID

## 3.3 前端（Vue3 + Vite + Element Plus）

已完成页面：

- 工作台：`/dashboard`
- 任务提交：`/tasks/submit/gpc`、`/tasks/submit/nmr`
- 任务中心：`/tasks/center`
- 任务详情：`/tasks/detail/:taskId`
- IR/Raman 提交占位页

已打通链路：

- 上传 -> 提交任务 -> 轮询查询 -> 查看结构化结果/文本报告/图像产物

当前关键缺口：

- NMRServer、数据管理、问答对话、验收测试页面未迁移
- 服务状态页未按源项目能力重建（当前仅具备基础任务看板）
- 存在字段对齐问题风险：上传响应使用 `file_name`，部分前端代码读取 `filename`

## 3.4 本轮新增进展（2026-04-12）

- 已完成：批量验收页面交互优化（运行中仅显示总进度，完成后一次性展示明细）
- 已完成：验收报告支持下载接口与前端下载按钮
- 已完成：NMR 解析链路新增 QA 指标产出
  - `baseline_rmse`（基线 RMSE）
  - `solvent_ppm_errors`（溶剂峰 ppm 误差）
- 已完成：批量验收聚合新增 NMR 指标均值与达标率计算
  - `baseline_rmse_avg / baseline_rmse_pass_rate`
  - `solvent_ppm_error_avg / solvent_ppm_error_pass_rate`
- 已完成：补齐 `backend/config/solvent_impurities.json`，用于溶剂峰误差口径计算

## 3.5 结论（截至 2026-04-12）

- 当前状态：P0/P1 能力持续收口中，批量验收与指标链路已基本可用，仍未达到“可上线”标准
- 覆盖情况：源项目 9 类能力中，已实装核心任务链路（GPC/NMR/IR/Raman）与验收主流程
- 最大阻塞项：数据管理中心、并发与异常回归、工程化观测与部署规范仍待补齐

## 4. 阶段状态看板

| 阶段 | 范围 | 当前状态 | 完成度 |
| --- | --- | --- | --- |
| Phase 0 | 基线梳理与文档 | 已完成 | 100% |
| Phase 1 | 后端 P0 主链路（GPC/NMR） | 已完成并持续优化 | 95% |
| Phase 2 | 前端 P0 MVP | 已可演示并完成多轮交互优化 | 85% |
| Phase 3 | 能力补齐（IR/Raman/NMRServer/数据/问答/验收） | 进行中 | 65% |
| Phase 4 | 工程化上线（独立部署、监控、发布） | 未开始 | 5% |

## 5. 后续计划（按优先级）

## 5.1 P0 收口（优先级 P0，目标 1 周）

1. 修复前后端字段与契约不一致项（含上传返回字段等）。
2. 补齐回归脚本到“上传链路 + 错误场景 + 并发任务”。
3. 完成任务详情结果结构稳定化（GPC/NMR JSON 字段版本约束）。
4. 输出 P0 验收记录（与 `验收样本清单.md` 对齐）。

交付物：

- P0 验收报告（Markdown）
- 契约一致性修订记录

## 5.2 能力补齐（优先级 P1，目标 2~3 周）

1. 后端新增 `POST /api/v1/tasks/ir`、`POST /api/v1/tasks/raman`。
2. 新增 NMRServer 三接口：正向预测/反向预测/数据库搜索。
3. 新增数据管理 API（结果查询、分页、删除、文件索引）。
4. 新增问答 API（会话管理、报告增强、上下文持久化）。
5. 新增验收测试 API（触发、进度、报告下载）。
6. 前端同步补齐对应页面，达到源项目功能等价覆盖。

交付物：

- 功能等价迁移清单（9/9）
- P1 功能验收报告

## 5.3 工程化与独立部署（优先级 P0/P1 并行，目标 2 周）

1. 将 `SOURCE_SPEC_AGENT_ROOT` 依赖改为本仓内聚实现（分模块迁移 `agents/analysis/services`）。
2. 增加配置分层（`dev/test/prod`）与敏感配置脱敏方案。
3. 增加观测能力：结构化日志、任务追踪 ID、基础指标（任务耗时/失败率/队列深度）。
4. 增加任务可靠性策略：超时、重试、失败原因标准化。
5. 输出 `docker-compose` 部署与回滚方案。

交付物：

- 独立部署验收证明（不依赖 `E:\github_project\Spec_Agent`）
- 部署手册、回滚手册

## 6. 近期执行清单（建议直接按此排期）

第 1 周：

- 完成 P0 收口与契约修复
- 固化回归与验收报告模板

第 2~3 周：

- 先补 IR/Raman，再补 NMRServer
- 前后端同步完成功能迁移

第 4~5 周：

- 完成数据管理/问答/验收接口与页面
- 启动独立部署迁移与压测

第 6 周：

- 完成上线前联调、灰度与回滚演练

## 7. 风险与应对

- 源项目耦合风险：先迁移执行入口，再迁移算法模块，避免一次性大改。
- 长任务稳定性风险：统一超时、重试、幂等键与失败分类。
- 数据模型漂移风险：为结构化结果定义版本字段并维护兼容层。
- 上线风险：必须在独立部署环境完成全量回归后再发布。
