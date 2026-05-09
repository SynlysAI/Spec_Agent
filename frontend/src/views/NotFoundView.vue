<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

/**
 * 返回工作台首页。
 */
function goDashboard() {
  router.replace('/dashboard')
}
</script>

<template>
  <div class="not-found-page">
    <div class="not-found-card">
      <div class="not-found-code">404</div>
      <h1>页面不存在</h1>
      <p>当前访问地址未匹配到系统页面，请检查链接是否正确。</p>
      <el-button type="primary" @click="goDashboard">返回工作台</el-button>
    </div>
  </div>
</template>

<style scoped>
.not-found-page {
  min-height: 100%;
  display: grid;
  place-items: center;
  padding: 32px 16px;
}

.not-found-card {
  width: min(520px, 100%);
  padding: 36px 32px;
  border-radius: 20px;
  border: 1px solid #d8e5f7;
  background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
  box-shadow: 0 18px 36px rgba(21, 59, 109, 0.08);
  text-align: center;
}

.not-found-code {
  font-size: 64px;
  line-height: 1;
  font-weight: 700;
  color: #1f5eff;
}

.not-found-card h1 {
  margin: 18px 0 10px;
  font-size: 28px;
  color: #183153;
}

.not-found-card p {
  margin: 0 0 24px;
  color: #5f7494;
  line-height: 1.7;
}
</style>
