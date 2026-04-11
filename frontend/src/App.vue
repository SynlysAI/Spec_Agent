<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataAnalysis,
  Document,
  Files,
  Histogram,
  Monitor,
  Operation,
  Fold,
  Expand,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const sidebarCollapsed = ref(false)

const activeMenu = computed(() => {
  const current = route.path
  if (current.startsWith('/tasks/detail')) {
    return '/tasks/center'
  }
  if (current.startsWith('/tasks/submit/')) {
    return current
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
    router.push('/tasks/submit/gpc')
    return
  }
  router.push(index)
}

/**
 * 切换左侧菜单展开状态。
 */
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}
</script>

<template>
  <el-container class="app-shell">
    <el-aside class="app-sidebar" :class="{ collapsed: sidebarCollapsed }" :width="sidebarCollapsed ? '66px' : '220px'">
      <div class="brand">
        <div class="brand-logo">S</div>
        <div v-if="!sidebarCollapsed" class="brand-text">
          <div class="brand-title">Spec Agent</div>
          <div class="brand-subtitle">实验谱图智能平台</div>
        </div>
      </div>
      <el-menu
        :default-active="activeMenu"
        class="sidebar-menu"
        :collapse="sidebarCollapsed"
        :collapse-transition="false"
        background-color="transparent"
        text-color="#d7def0"
        active-text-color="#ffffff"
        @select="handleMenuSelect"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Monitor /></el-icon>
          <span>工作台</span>
        </el-menu-item>

        <el-sub-menu index="/tasks/submit">
          <template #title>
            <el-icon><DataAnalysis /></el-icon>
            <span>任务提交</span>
          </template>
          <el-menu-item index="/tasks/submit/gpc">GPC 提交</el-menu-item>
          <el-menu-item index="/tasks/submit/nmr">NMR 提交</el-menu-item>
          <el-menu-item index="/tasks/submit/ir">IR 提交</el-menu-item>
          <el-menu-item index="/tasks/submit/raman">Raman 提交</el-menu-item>
        </el-sub-menu>

        <el-menu-item index="/tasks/center">
          <el-icon><Histogram /></el-icon>
          <span>任务中心</span>
        </el-menu-item>
        <el-menu-item index="/docs">
          <el-icon><Document /></el-icon>
          <span>接口文档</span>
        </el-menu-item>
        <el-menu-item index="/files">
          <el-icon><Files /></el-icon>
          <span>文件管理</span>
        </el-menu-item>
        <el-menu-item index="/ops" disabled>
          <el-icon><Operation /></el-icon>
          <span>运维管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="app-header">
        <div class="header-left">
          <el-button circle text class="collapse-btn" @click="toggleSidebar">
            <el-icon v-if="sidebarCollapsed"><Expand /></el-icon>
            <el-icon v-else><Fold /></el-icon>
          </el-button>
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
