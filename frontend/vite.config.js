import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiProxyTarget = String(env.VITE_DEV_API_PROXY_TARGET || 'http://127.0.0.1:8000').trim()

  return {
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
        '/static': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
