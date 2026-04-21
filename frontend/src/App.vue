<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataAnalysis,
  Document,
  Files,
  FolderOpened,
  Histogram,
  ChatLineRound,
  Monitor,
  SetUp,
  Fold,
  Expand,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const sidebarCollapsed = ref(false)
const currentDate = ref(formatCurrentDate())

const activeMenu = computed(() => {
  const current = route.path
  if (current.startsWith('/tasks/detail')) {
    return '/tasks/center'
  }
  if (current.startsWith('/tasks/submit/')) {
    return current
  }
  if (current.startsWith('/tools/')) {
    return current
  }
  if (current.startsWith('/experiments/')) {
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
  router.push(index)
}

/**
 * 切换左侧菜单展开状态。
 */
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

/**
 * 生成当前日期字符串（YYYY-MM-DD）。
 *
 * Returns:
 *   当前日期字符串。
 */
function formatCurrentDate() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
</script>

<template>
  <el-container class="app-shell">
    <el-aside class="app-sidebar" :class="{ collapsed: sidebarCollapsed }" :width="sidebarCollapsed ? '66px' : '220px'">
      <div class="brand">
        <div class="brand-logo">S</div>
        <div v-if="!sidebarCollapsed" class="brand-text">
          <div class="brand-title">Spec Agent</div>
          <div class="brand-subtitle">谱图智能分析平台</div>
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
          <el-menu-item index="/tasks/submit/lcms">LCMS 提交</el-menu-item>
        </el-sub-menu>

        <el-menu-item index="/tasks/center">
          <el-icon><Histogram /></el-icon>
          <span>任务中心</span>
        </el-menu-item>
        <el-menu-item index="/dialogue">
          <el-icon><ChatLineRound /></el-icon>
          <span>问答对话</span>
        </el-menu-item>
        <el-sub-menu index="/tools">
          <template #title>
            <el-icon><SetUp /></el-icon>
            <span>工具服务</span>
          </template>
          <el-menu-item index="/tools/nmrserver">核磁预测服务</el-menu-item>
          <el-menu-item index="/tools/acceptance">批量验收测试</el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="/experiments">
          <template #title>
            <el-icon><FolderOpened /></el-icon>
            <span>实验管理</span>
          </template>
          <el-menu-item index="/experiments/collect">数据采集</el-menu-item>
          <el-menu-item index="/experiments/samples">样本管理</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/docs">
          <el-icon><Document /></el-icon>
          <span>接口文档</span>
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
          <span class="header-date">{{ currentDate }}</span>
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
