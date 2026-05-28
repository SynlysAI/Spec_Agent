/**
* 通过 pm2 start ecosystem.config.js启动服务
*/
module.exports = {
  apps: [
    {
      // 1. SpecAgent - FastAPI 异步后端服务
      name: "spec-agent-backend",
      script: "C:\\conda_envs\\spec_agent\\Scripts\\uvicorn.exe",
      args: "app.main:app --host 0.0.0.0 --port 8001",
      cwd: "E:\\github_project\\Spec_Agent\\backend",
      interpreter: "none", // 告诉pm2不需要再用node解析，直接运行exe
      watch: false
    },
    {
      // 2. SpecAgent - Celery 异步任务 Worker 消费者
      name: "spec-agent-worker",
      script: "C:\\conda_envs\\spec_agent\\python.exe",
      args: "-m celery -A app.worker.celery_app:celery_app worker --loglevel=info -Q spec_agent -P solo",
      cwd: "E:\\github_project\\Spec_Agent\\backend",
      interpreter: "none",
      watch: false
    },
    {
      // 3. SpecAgent - Streamlit 前端 WebUI 服务 (新增)
      name: "spec-agent-webui",
      cwd: "D:\\Spec_Agent",                             // 👈 注意：这里换成了你 Streamlit 项目所在的 D 盘目录
      script: "C:\\conda_envs\\spec_agent\\Scripts\\streamlit.exe", // 直接调用 conda 环境中的 streamlit 编译器
      args: "run .\\streamlit_webui.py",                 // 传给 streamlit 的启动参数
      interpreter: "none",
      watch: false,
      autorestart: true,
      max_memory_restart: "1G"
    },
    {
      // 4. SpecLabOS - 实验室设备与自动化后端 (新增)
      name: "speclab-os-backend",
      cwd: "E:\\github_project\\SpecLabOS\\backend",           // 👈 切换到 SpecLabOS 的工作目录
      script: "C:\\conda_envs\\SpecLabOS\\Scripts\\uvicorn.exe", // 👈 注意：这里调用的是 SpecLabOS 环境下的 uvicorn
      args: "main:app --host 0.0.0.0 --port 8010",              // 👈 运行在 8010 端口
      interpreter: "none",
      watch: false,
      autorestart: true,
      max_memory_restart: "1G"
    }
  ]
};