/**
 * Spec_Agent 原生部署 PM2 简化模式配置。
 *
 * 说明：
 * 1. 适用于 Windows / Linux 原生命令行部署
 * 2. MongoDB / RabbitMQ 建议通过 Docker Compose 单独启动
 * 3. 简化模式仅启动 backend + worker
 * 4. 前端需先执行 `npm run build`，再由 FastAPI 自动托管 frontend/dist
 */
const path = require("path");

const PROJECT_ROOT = process.env.SPEC_AGENT_PROJECT_ROOT || __dirname;
const BACKEND_CWD = path.join(PROJECT_ROOT, "backend");

const UVICORN_BIN = process.env.SPEC_AGENT_UVICORN_BIN || "uvicorn";
const PYTHON_BIN = process.env.SPEC_AGENT_PYTHON_BIN || "python";

const BACKEND_PORT = process.env.SPEC_AGENT_BACKEND_PORT || "8000";
const CELERY_QUEUE = process.env.CELERY_TASK_QUEUE || "spec_agent";
const CELERY_POOL = process.env.SPEC_AGENT_CELERY_POOL || (process.platform === "win32" ? "solo" : "prefork");

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
    }
  ]
};
