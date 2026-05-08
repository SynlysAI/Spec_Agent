<script setup>
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataAnalysis,
  Document,
  FolderOpened,
  Histogram,
  ChatLineRound,
  Monitor,
  SetUp,
  Fold,
  Expand,
  SwitchButton,
} from '@element-plus/icons-vue'

import { getAuthStatus, getApiErrorMessage } from './api/specAgentApi'
import { authState, clearAuthSession, setAuthEnabled, setAuthSession } from './auth/authState'

const route = useRoute()
const router = useRouter()
const sidebarCollapsed = ref(false)
const currentDate = ref(formatCurrentDate())
const isLoginPage = computed(() => route.path === '/login')
const authBootstrapping = ref(true)

/**
 * 解析接口文档地址。
 *
 * Returns:
 *   基于当前页面地址推导的接口文档 URL。
 */
function resolveDocsUrl() {
  if (typeof window === 'undefined') {
    return 'http://127.0.0.1:8000/docs'
  }
  const protocol = window.location.protocol || 'http:'
  const hostname = window.location.hostname || '127.0.0.1'
  return `${protocol}//${hostname}:8000/docs`
}

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
    window.open(resolveDocsUrl(), '_blank')
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
 * 退出当前登录会话。
 */
function handleLogout() {
  clearAuthSession()
  router.replace('/login')
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

/**
 * 初始化服务端登录开关与当前会话状态。
 *
 * Returns:
 *   Promise<void>
 */
async function initializeAuthState() {
  try {
    const data = await getAuthStatus()
    setAuthEnabled(data.auth_enabled)
    if (!data.auth_enabled) {
      if (route.path === '/login') {
        router.replace('/dashboard')
      }
      return
    }
    if (data.authenticated) {
      setAuthSession({
        username: data.username || authState.username,
        tokenType: authState.tokenType,
        accessToken: authState.accessToken,
        expiresAt: authState.expiresAt,
      })
      return
    }
    clearAuthSession()
    if (route.path !== '/login') {
      router.replace({
        path: '/login',
        query: { redirect: route.fullPath },
      })
    }
  } catch (error) {
    clearAuthSession()
    setAuthEnabled(false)
    ElMessage.error(`鉴权状态初始化失败：${getApiErrorMessage(error)}`)
  } finally {
    authBootstrapping.value = false
  }
}

onMounted(initializeAuthState)
</script>

<template>
  <div v-if="authBootstrapping" class="app-loading-shell">
    <div class="app-loading-card">
      <div class="app-loading-title">Spec Agent</div>
      <div class="app-loading-text">正在初始化访问控制...</div>
    </div>
  </div>
  <router-view v-else-if="isLoginPage" />
  <el-container v-else class="app-shell">
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
          <el-menu-item index="/tools/raman-capture">拉曼批量采集</el-menu-item>
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
          <el-tag v-if="authState.authEnabled" type="success" effect="plain">已启用登录保护</el-tag>
          <el-avatar size="small">管</el-avatar>
          <span>{{ authState.authEnabled ? authState.username || '实验室管理员' : '实验室管理员' }}</span>
          <el-button v-if="authState.authEnabled" text class="logout-btn" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            退出登录
          </el-button>
        </div>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
