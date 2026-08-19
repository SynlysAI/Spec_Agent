/**
 * Spec_Agent PM2 启动配置 - Linux 专用版本
 *
 * 说明：
 * 1. 适用于 Linux 原生部署（conda 环境：spec_agent）
 * 2. MongoDB / RabbitMQ 建议通过 Docker Compose 单独启动
 * 3. 仅启动 backend + worker 两个服务（前端作为静态文件部署）
 */
const path = require("path");

const PROJECT_ROOT = process.env.SPEC_AGENT_PROJECT_ROOT || __dirname;
const BACKEND_CWD = path.join(PROJECT_ROOT, "backend");

// Linux conda 环境路径
const CONDA_ENV_PATH = process.env.SPEC_AGENT_CONDA_PATH || "/polymer/conda/envs/spec_agent";
const UVICORN_BIN = process.env.SPEC_AGENT_UVICORN_BIN || path.join(CONDA_ENV_PATH, "bin/uvicorn");
const PYTHON_BIN = process.env.SPEC_AGENT_PYTHON_BIN || path.join(CONDA_ENV_PATH, "bin/python");

const BACKEND_PORT = process.env.SPEC_AGENT_BACKEND_PORT || "8001";
const CELERY_QUEUE = process.env.CELERY_TASK_QUEUE || "spec_agent";
const CELERY_POOL = process.env.SPEC_AGENT_CELERY_POOL || "prefork";

// ── 实验室公共配置注入（读取共享密钥；文件缺失时返回空对象，本地开发不受影响）──
const COMMON_ENV = (() => {
  try {
    const out = {};
    for (const line of require("fs")
      .readFileSync("/home/fangyikai/lab-common.env", "utf-8")
      .split(/\r?\n/)) {
      if (line.trim().startsWith("#")) continue;
      const idx = line.indexOf("=");
      if (idx > 0) out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
    }
    return out;
  } catch {
    return {};
  }
})();

module.exports = {
  apps: [
    {
      // 1. SpecAgent - FastAPI 异步后端服务
      name: "spec-agent-backend",
      cwd: BACKEND_CWD,
      script: UVICORN_BIN,
      args: `app.main:app --host 0.0.0.0 --port ${BACKEND_PORT}`,
      interpreter: "none",
      watch: false,
      autorestart: true,
      max_memory_restart: "2G",
      env: {
        ...COMMON_ENV,
        PYTHONPATH: BACKEND_CWD
      }
    },
    {
      // 2. SpecAgent - Celery 异步任务 Worker 消费者
      name: "spec-agent-worker",
      cwd: BACKEND_CWD,
      script: PYTHON_BIN,
      args: `-m celery -A app.worker.celery_app:celery_app worker --loglevel=info -Q ${CELERY_QUEUE} -P ${CELERY_POOL}`,
      interpreter: "none",
      watch: false,
      autorestart: true,
      max_memory_restart: "2G",
      env: {
        ...COMMON_ENV,
        PYTHONPATH: BACKEND_CWD
      }
    }
  ]
};
