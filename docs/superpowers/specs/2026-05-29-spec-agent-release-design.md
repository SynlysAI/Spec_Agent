# Spec_Agent 正式发布整理与多平台部署设计

## 1. 背景与目标

当前 `Spec_Agent` 已从早期 `Streamlit Demo` 演进为 `FastAPI + Vue 3 + Celery + MongoDB + RabbitMQ` 的前后端分离系统，业务功能已经相对完整，具备进入正式发布整理阶段的条件。

本次设计目标不是新增业务功能，而是将当前仓库整理为一份可正式交付、可持续维护、可多平台运行的项目版本。重点目标如下：

- 支持 `Windows 原生部署`
- 支持 `Linux 原生部署`
- 支持 `Docker 生产部署`
- `MongoDB` 与 `RabbitMQ` 默认通过 Docker 提供，正式环境仅允许容器内访问
- 外部依赖服务统一配置化，不再阻塞主系统正式发布
- 清理历史遗留的部署残留、无用模板文件、失效文档入口和硬编码环境依赖

本次正式发布主路径为 `Docker 部署`，但原生部署模式仍需保留，作为开发、调试、联调与排障手段。

## 2. 范围与边界

### 2.1 本阶段纳入范围

- 前端 `Vue 3` 应用
- 后端 `FastAPI` 服务
- `Celery Worker`
- `MongoDB`
- `RabbitMQ`
- 正式发布文档、部署文档、配置说明
- Docker 镜像与 `compose` 编排
- `Windows/Linux` 原生启动方式

### 2.2 本阶段不阻塞发布的内容

- `NMRServer`
- `LCMS` 推理服务
- 拉曼仪器采集网络可达性
- 未来域名、HTTPS、内网穿透接入

这些能力仍需保留接入位，但当前若外部地址不可达，不应阻塞主系统整理与正式发布。

## 3. 当前状态问题清单

基于现有仓库和部署文件分析，当前存在以下问题：

### 3.1 部署入口混乱

- 根目录 `ecosystem.config.js` 仍包含旧 `Streamlit` 进程和 `SpecLabOS` 进程定义
- `README.md` 仍以旧部署口径表述项目，未明确 `Docker` 为正式发布主路径
- `frontend/README.md` 仍是默认 `Vite` 模板说明
- 仓库尚无正式 `Dockerfile`、`.dockerignore` 和 `Nginx` 配置

### 3.2 配置示例不适合作为正式版基线

- `backend/.env.example` 中存在固定 IP
- `backend/.env.example` 中存在 `E:\spectrum_files` 等 Windows 绝对路径
- 外部服务配置与本地开发配置混杂，不利于跨平台部署

### 3.3 仓库存在历史遗留噪音

- 前端保留默认模板文件，如 `HelloWorld.vue`、`vite.svg`、`vue.svg`
- 文档目录当前被根 `.gitignore` 忽略，不利于计划文档和部署文档纳管
- 根目录保留了过程性文档，但尚未形成正式分类

### 3.4 代码中仍存在环境耦合点

- 回归脚本默认引用 Windows 路径
- 个别分析脚本存在个人 Linux 路径硬编码示例
- `PM2` 配置写死个人机器的解释器与工作目录

### 3.5 Docker 化风险未显式管理

- 当前华为 Linux 服务器为 `aarch64/ARM64`
- `torch`、`rdkit` 等依赖在 ARM64 上可能与 x86_64 有显著差异
- 需要明确“Docker 发布结构先落地，依赖镜像兼容性单独验证”的策略

## 4. 目标发布架构

### 4.1 统一架构

正式版采用如下结构：

```text
浏览器
  -> Nginx
     -> 前端静态资源
     -> /api -> FastAPI
     -> /static/outputs -> FastAPI

FastAPI
  -> MongoDB
  -> RabbitMQ
  -> 外部服务（按环境变量接入）

Celery Worker
  -> RabbitMQ
  -> MongoDB
  -> 外部服务（按环境变量接入）
```

### 4.2 Docker 模式

- `nginx` 对外暴露端口
- `backend` 与 `worker` 共享同一份应用镜像
- `mongodb`、`rabbitmq` 默认仅容器内访问
- 如需调试数据库或 MQ，通过 debug profile 临时开放端口

### 4.3 原生部署模式

保留以下部署能力：

- `Windows` 原生：前端、后端、Worker 通过命令行或 `PM2` 启动
- `Linux` 原生：前端、后端、Worker 通过命令行或 `PM2` 启动
- `MongoDB` 与 `RabbitMQ` 仍默认通过 Docker 提供

原生部署的定位是开发、调试与联调模式，而不是正式生产主路径。

## 5. 仓库整理策略

### 5.1 保留并规范

- `backend/`
- `frontend/`
- `docker/`
- `scripts/`
- `docs/`
- 根目录正式入口文档

### 5.2 归档和分类

建议将文档拆分到以下目录：

- `docs/deployment/`：部署说明
- `docs/architecture/`：架构说明
- `docs/archive/`：历史过程文档
- `docs/superpowers/`：设计与计划文档

### 5.3 历史残留收敛

- 重写 `ecosystem.config.js`，仅保留 `Spec_Agent` 的前后端与 Worker 启动入口
- 删除前端模板残留文件
- 重写 `frontend/README.md`
- 将默认配置示例改为跨平台安全默认值

## 6. 配置治理方案

### 6.1 原则

- 所有地址、端口、路径、外部依赖服务地址均通过环境变量注入
- 不在正式示例配置中写死个人机器路径、私网 IP、个人开发目录
- Windows、Linux、Docker 共享同一套环境变量语义

### 6.2 关键配置类别

- 应用运行环境：`APP_ENV`
- 登录鉴权配置：`AUTH_*`
- MongoDB 配置：`MONGODB_*`
- RabbitMQ 配置：`RABBITMQ_*`
- 运行时目录配置：`SPEC_AGENT_*`
- 样本目录与资源目录配置
- 外部服务配置：`NMR_SERVER_BASE_URL`、`LCMS_INFER_URL` 等

### 6.3 外部依赖处理策略

- 当前网络不可达的外部服务，不在主系统启动阶段强校验
- 仅在实际调用相关接口时返回上游错误
- 文档中明确各功能的外部依赖条件

## 7. Docker 部署策略

### 7.1 推荐容器角色

- `nginx`
- `backend`
- `worker`
- `mongodb`
- `rabbitmq`

### 7.2 网络策略

- 默认只开放 `nginx`
- `mongodb`、`rabbitmq` 不映射宿主机端口
- 调试场景通过 profile 单独开放 `27017`、`5672`、`15672`

### 7.3 镜像策略

- 前端使用多阶段构建生成静态文件
- 后端与 Worker 共享应用镜像
- 运行时目录通过卷挂载到 `.runtime`
- 大体积模型资源优先保留为宿主机挂载策略，避免镜像过大

### 7.4 ARM64 风险说明

当前生产目标服务器是 `aarch64`。因此：

- Docker 构建需优先验证 `python` 基础镜像与依赖兼容性
- `torch`、`rdkit` 等依赖需单独确认 ARM64 wheel 可用性
- 若相关依赖无法直接在 ARM64 镜像中安装，需要考虑：
  - 调整 Python 版本
  - 改用 Conda/Mamba 方案
  - 将高耦合能力拆分为单独服务

本次设计先完成结构与部署骨架，不在未验证依赖兼容性前承诺 ARM64 镜像一定一次构建成功。

## 8. 风险与处理策略

### 8.1 高风险项

- ARM64 Python 科学计算依赖兼容性
- `LCMS` 相关 Windows 外部软件依赖
- 仪器采集类功能的网络与硬件环境依赖
- 历史脚本是否仍被业务人员手工使用

### 8.2 降风险策略

- 先完成仓库治理、配置治理和部署骨架
- 将外部依赖统一配置化
- 为不稳定功能保留接入位，不强行承诺立即可用
- 文档清楚说明各类运行模式与能力边界

## 9. 实施成功标准

本阶段完成的判定标准如下：

- 仓库存在清晰的正式文档入口
- `docs` 可纳入版本管理
- `Windows/Linux` 原生启动方式有统一说明
- `Docker` 生产部署具备完整骨架
- `MongoDB`、`RabbitMQ` 默认不暴露宿主机端口
- 示例配置不再包含个人开发路径和固定私网 IP
- 旧 `Streamlit`、`SpecLabOS` 部署残留从正式入口中移除
- 历史模板文件和无关资源被清理或隔离

## 10. 结论

推荐采用“多运行模式统一治理”的正式版整理策略：

- `Docker` 作为正式生产发布主路径
- `Windows/Linux` 原生部署作为兼容与调试路径
- 主系统先完成工程化整理和部署骨架建设
- 外部服务通过配置方式后续接回，不阻塞主系统正式发布

该方案能在不推翻现有业务代码的前提下，最大程度降低后续发布和迁移成本。
