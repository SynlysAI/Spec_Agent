<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataAnalysis,
  Document,
  Files,
  Histogram,
  Menu as MenuIcon,
  Monitor,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const menuItems = [
  { index: '/dashboard', label: '工作台', icon: Monitor },
  { index: '/tasks/submit', label: '任务提交', icon: DataAnalysis },
  { index: '/tasks/center', label: '任务中心', icon: Histogram },
  { index: '/docs', label: '接口文档', icon: Document },
  { index: '/files', label: '文件管理', icon: Files },
]

const activeMenu = computed(() => {
  const current = route.path
  if (current.startsWith('/tasks/detail')) {
    return '/tasks/center'
  }
  return current
})

/**
 * 处理菜单跳转动作。
 *
 * Args:
 *   index: 目标路由路径。
 */
function handleMenuSelect(index) {
  if (index === '/docs') {
    window.open('http://127.0.0.1:8000/docs', '_blank')
    return
  }
  if (index === '/files') {
    router.push('/tasks/submit')
    return
  }
  router.push(index)
}
</script>

<template>
  <el-container class="app-shell">
    <el-aside class="app-sidebar" width="220px">
      <div class="brand">
        <div class="brand-logo">S</div>
        <div class="brand-text">
          <div class="brand-title">Spec Agent</div>
          <div class="brand-subtitle">实验谱图智能平台</div>
        </div>
      </div>
      <el-menu
        :default-active="activeMenu"
        class="sidebar-menu"
        background-color="transparent"
        text-color="#d7def0"
        active-text-color="#ffffff"
        @select="handleMenuSelect"
      >
        <el-menu-item v-for="item in menuItems" :key="item.index" :index="item.index">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="app-header">
        <div class="header-left">
          <el-icon><MenuIcon /></el-icon>
          <span>开放平台</span>
        </div>
        <div class="header-right">
          <span class="header-date">2026-04-10</span>
          <el-avatar size="small">管</el-avatar>
          <span>实验室管理员</span>
        </div>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
