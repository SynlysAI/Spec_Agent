# Spec Agent 前端说明

## 开发启动

```bash
cd frontend
npm install
npm run dev
```

默认开发地址：`http://127.0.0.1:5173`

## 开发代理

前端开发服务会将 `/api` 与 `/static` 请求代理到后端服务。

如需修改代理目标，可在 `frontend/.env` 中设置：

```bash
VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8000
```

未设置时默认代理到 `http://127.0.0.1:8000`。

## 构建

```bash
npm run build
```

构建产物输出到 `frontend/dist/`。

## 预览构建产物

```bash
npm run preview -- --host 0.0.0.0 --port 4173
```

## 生产接入方式

- 原生部署场景：可在构建前端后由后端自动托管 `frontend/dist/`
- Docker 部署场景：由 `Nginx` 容器托管前端静态资源并反向代理 `/api`
