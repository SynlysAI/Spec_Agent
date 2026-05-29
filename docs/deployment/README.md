# 部署文档导航

## 部署模式

### 1. Docker 生产部署

适用场景：

- 统一通过容器编排管理前端、后端、Worker 和中间件
- 仅对外暴露 `Nginx` 入口

启动命令：

```bash
cp docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.infra.yml up -d --build
# 旧版环境可使用：
# docker-compose --env-file docker/.env -f docker/docker-compose.yml -f docker/docker-compose.infra.yml up -d --build
```

若使用外部 `MongoDB` 与 `RabbitMQ`，请修改 `docker/.env` 中以下变量：

```bash
MONGODB_HOST=你的MongoDB地址
MONGODB_PORT=你的MongoDB端口
MONGODB_USERNAME=你的MongoDB用户名
MONGODB_PASSWORD=你的MongoDB密码
MONGODB_DATABASE=spec_agent

RABBITMQ_HOST=你的RabbitMQ地址
RABBITMQ_PORT=你的RabbitMQ端口
RABBITMQ_USERNAME=你的RabbitMQ用户名
RABBITMQ_PASSWORD=你的RabbitMQ密码
RABBITMQ_VHOST=/
```

然后只启动应用编排：

```bash
docker compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
# 旧版环境可使用：
# docker-compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
```

使用外部 `MongoDB` 与 `RabbitMQ` 时，`MONGO_INITDB_ROOT_USERNAME`、`MONGO_INITDB_ROOT_PASSWORD`、`RABBITMQ_DEFAULT_USER`、`RABBITMQ_DEFAULT_PASS` 这些仅供容器版基础设施使用的变量可以保留默认值，也可以按需忽略。

### 2. Windows / Linux 原生部署

适用场景：

- 日常开发
- 快速联调
- 本机排障

建议先通过 Docker 启动 `MongoDB` 与 `RabbitMQ`：

```bash
docker compose --env-file docker/.env -f docker/docker-compose.infra.yml up -d mongodb rabbitmq
# 旧版环境可使用：
# docker-compose --env-file docker/.env -f docker/docker-compose.infra.yml up -d mongodb rabbitmq
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
- `docker/docker-compose.yml`：应用服务编排
- `docker/docker-compose.infra.yml`：MongoDB / RabbitMQ 基础设施编排

## 注意事项

- `LCMS` 相关外部工具、`NMRServer`、拉曼仪器采集等外围依赖需按环境单独配置
- `MongoDB`、`RabbitMQ` 在基础设施编排中默认不暴露宿主机端口
- 若使用外部 `MongoDB`、`RabbitMQ`，只启动 `docker-compose.yml` 即可

### 特定环境说明

以下内容仅适用于部分服务器环境，不属于通用部署要求：

- 无 root 权限服务器：
  - 可使用 rootless Docker
  - 若默认 `overlayfs` 出现 `operation not permitted`，可改用 `vfs` 存储驱动
  - 可直接使用 `bash docker/up.sh`

- `ARM64` 服务器：
  - 需额外确认基础镜像与 Python 科学计算依赖的兼容性
  - 当前项目已在一台 `ARM64` 服务器上验证通过前端、后端、Worker 镜像构建
