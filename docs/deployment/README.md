# 部署文档导航

## 部署模式

### 1. Docker 生产部署

适用场景：

- 华为 Linux 服务器正式发布
- 统一通过容器编排管理前端、后端、Worker 和中间件
- 仅对外暴露 `Nginx` 入口

启动命令：

```bash
cp docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
# 旧版环境可使用：
# docker-compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
```

当前华为服务器无 root 权限时，推荐直接使用：

```bash
bash docker/up.sh
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

## 已知限制

- 当前生产服务器为 `ARM64`，已验证前端、后端、Worker 镜像可构建
- `LCMS` 相关外部工具、`NMRServer`、拉曼仪器采集等外围依赖需按环境单独配置
- `MongoDB`、`RabbitMQ` 在正式 Docker 模式下默认不暴露宿主机端口；原生应用接入时请使用 `docker-compose.native.yml`
- 当前无 root 权限服务器需使用 rootless Docker 的 `vfs` 存储驱动，避免默认 `overlayfs` 出现 `operation not permitted`
