/**
 * Spec_Agent 原生部署 PM2 全量模式配置。
 *
 * 说明：
 * 1. 适用于 Windows / Linux 原生命令行部署
 * 2. MongoDB / RabbitMQ 建议通过 Docker Compose 单独启动
 * 3. 当前文件为全量模式：启动 frontend + backend + worker
 * 4. 若仅需 backend + worker，请使用 ecosystem.slim.config.js
 * 5. 前端默认使用 `vite preview` 托管已构建产物，首次启动前请先执行 `npm run build`
 */
const path = require("path");

const PROJECT_ROOT = process.env.SPEC_AGENT_PROJECT_ROOT || __dirname;
const BACKEND_CWD = path.join(PROJECT_ROOT, "backend");
const FRONTEND_CWD = path.join(PROJECT_ROOT, "frontend");

const UVICORN_BIN = process.env.SPEC_AGENT_UVICORN_BIN || "uvicorn";
const PYTHON_BIN = process.env.SPEC_AGENT_PYTHON_BIN || "python";

const IS_WIN32 = process.platform === "win32";

const BACKEND_PORT = process.env.SPEC_AGENT_BACKEND_PORT || "8000";
const FRONTEND_PORT = process.env.SPEC_AGENT_FRONTEND_PORT || "4173";
const CELERY_QUEUE = process.env.CELERY_TASK_QUEUE || "spec_agent";
const CELERY_POOL = process.env.SPEC_AGENT_CELERY_POOL || (IS_WIN32 ? "solo" : "prefork");

module.exports = {
  apps: [
    {
      name: "spec-agent-backend",
      cwd: BACKEND_CWD,
      script: UVICORN_BIN,
      args: `app.main:app --host 0.0.0.0 --port ${BACKEND_PORT}`,
      interpreter: "none",
      watch: false,
      autorestart: true,
      max_memory_restart: "2G"
    },
    {
      name: "spec-agent-worker",
      cwd: BACKEND_CWD,
      script: PYTHON_BIN,
      args: `-m celery -A app.worker.celery_app:celery_app worker --loglevel=info -Q ${CELERY_QUEUE} -P ${CELERY_POOL}`,
      interpreter: "none",
      watch: false,
      autorestart: true,
      max_memory_restart: "2G"
    },
    {
      name: "spec-agent-frontend",
      cwd: FRONTEND_CWD,
      script: "./node_modules/vite/bin/vite.js",
      args: `preview --host 0.0.0.0 --port ${FRONTEND_PORT}`,
      watch: false,
      autorestart: true,
      max_memory_restart: "1G"
    }
  ]
};
