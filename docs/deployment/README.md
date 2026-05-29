# 部署文档导航

## 部署模式

### 1. Docker 生产部署

适用场景：

- 统一通过容器编排管理前端、后端、Worker 和中间件
- 仅对外暴露 `Nginx` 入口

启动命令：

```bash
cp docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
# 旧版环境可使用：
# docker-compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
```

### 2. Windows / Linux 原生部署

适用场景：

- 日常开发
- 快速联调
- 本机排障

建议先通过 Docker 启动 `MongoDB` 与 `RabbitMQ`：

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.native.yml up -d mongodb rabbitmq
# 旧版环境可使用：
# docker-compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.native.yml up -d mongodb rabbitmq
```

随后按根 `README.md` 中说明启动：

- 前端
- FastAPI
- Celery Worker

PM2 支持两种模式：

- 全量模式：`pm2 start ecosystem.config.js`
- 简化模式：`pm2 start ecosystem.slim.config.js`

## 配置文件

- `backend/.env.example`：原生部署环境变量模板
- `frontend/.env.example`：前端开发环境变量模板
- `docker/.env.example`：Docker Compose 环境变量模板

## 注意事项

- `LCMS` 相关外部工具、`NMRServer`、拉曼仪器采集等外围依赖需按环境单独配置
- `MongoDB`、`RabbitMQ` 在正式 Docker 模式下默认不暴露宿主机端口；原生应用接入时请使用 `docker-compose.native.yml`

### 特定环境说明

以下内容仅适用于部分服务器环境，不属于通用部署要求：

- 无 root 权限服务器：
  - 可使用 rootless Docker
  - 若默认 `overlayfs` 出现 `operation not permitted`，可改用 `vfs` 存储驱动
  - 可直接使用 `bash docker/up.sh`

- `ARM64` 服务器：
  - 需额外确认基础镜像与 Python 科学计算依赖的兼容性
  - 当前项目已在一台 `ARM64` 服务器上验证通过前端、后端、Worker 镜像构建
