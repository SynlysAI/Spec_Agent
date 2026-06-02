<script setup>
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataAnalysis,
  Document,
  FolderOpened,
  Histogram,
  ChatLineRound,
  Key,
  Monitor,
  SetUp,
  Fold,
  Expand,
  SwitchButton,
  User,
} from '@element-plus/icons-vue'

import { getAuthStatus, getApiErrorMessage, getCurrentUser } from './api/specAgentApi'
import { authState, clearAuthSession, setAuthEnabled, setAuthSession } from './auth/authState'

const route = useRoute()
const router = useRouter()
const AUTH_PUBLIC_PATHS = new Set(['/login', '/register'])
const sidebarCollapsed = ref(false)
const currentDate = ref(formatCurrentDate())
const isAuthPage = computed(() => route.path === '/login' || route.path === '/register')
const authBootstrapping = ref(true)
const AUTH_EXPIRED_EVENT_NAME = 'spec-agent-auth-expired'
const APP_VERSION = '1.2.9'
const canAccessAdminFeatures = computed(() => !authState.authEnabled || authState.role === 'admin')
const currentUserDisplayName = computed(() => {
  if (!authState.authEnabled) {
    return '实验室管理员'
  }
  return authState.username || '当前用户'
})
const currentUserRoleLabel = computed(() => {
  if (!authState.authEnabled) {
    return ''
  }
  if (authState.role === 'admin') {
    return '管理员'
  }
  if (authState.role === 'user') {
    return '普通用户'
  }
  return ''
})
const currentUserAvatarText = computed(() => currentUserDisplayName.value.slice(0, 1) || 'S')
const isAuthPublicRoute = computed(() => AUTH_PUBLIC_PATHS.has(route.path))

/**
 * 解析接口文档地址。
 *
 * Returns:
 *   基于当前页面地址推导的接口文档 URL。
 */
function resolveDocsUrl() {
  if (typeof window === 'undefined') {
    return '/docs'
  }
  const port = window.location.port
  // Dev (5173) / Preview (4173): 前端开发服务器没有 /docs 代理，直连后端
  if (port === '5173' || port === '4173') {
    const protocol = window.location.protocol || 'http:'
    const hostname = window.location.hostname || '127.0.0.1'
    return `${protocol}//${hostname}:8000/docs`
  }
  // 生产环境（80/443 等）: 假设 nginx 已反向代理 /docs 到后端
  return `${window.location.origin}/docs`
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
  if (current.startsWith('/admin/')) {
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
 * 判断鉴权请求是否因登录态失效而失败。
 *
 * Args:
 *   error: API 异常对象。
 *
 * Returns:
 *   是否为 401/403 鉴权失败。
 */
function isAuthenticationError(error) {
  return error?.status === 401 || error?.status === 403
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
 * 将当前页面跳转到登录页。
 */
function redirectToLogin() {
  if (isAuthPublicRoute.value) {
    return
  }
  router.replace({
    path: '/login',
    query: { redirect: route.fullPath },
  })
}

/**
 * 使用当前缓存令牌与服务端用户信息重建会话。
 *
 * Args:
 *   currentUser: `/auth/me` 返回的用户信息。
 */
function syncCurrentUserSession(currentUser) {
  setAuthSession({
    userId: currentUser.user_id,
    username: currentUser.username || authState.username,
    role: currentUser.role || authState.role,
    status: currentUser.status || authState.status,
    tokenType: authState.tokenType,
    accessToken: authState.accessToken,
    expiresAt: authState.expiresAt,
  })
}

/**
 * 处理 `/auth/me` 初始化失败后的兜底逻辑。
 *
 * Args:
 *   error: `/auth/me` 请求失败异常。
 *
 * Returns:
 *   Promise<void>
 */
async function recoverAuthBootstrap(error) {
  try {
    const statusData = await getAuthStatus()
    setAuthEnabled(statusData.auth_enabled)
    if (!statusData.auth_enabled) {
      if (isAuthPublicRoute.value) {
        router.replace('/dashboard')
      }
      return
    }
    if (statusData.authenticated && authState.authenticated) {
      return
    }
    clearAuthSession()
    redirectToLogin()
    if (!isAuthenticationError(error)) {
      ElMessage.error(`鉴权状态初始化失败：${getApiErrorMessage(error)}`)
    }
  } catch (statusError) {
    clearAuthSession()
    setAuthEnabled(true)
    ElMessage.error(`鉴权状态初始化失败：${getApiErrorMessage(statusError)}`)
    redirectToLogin()
  }
}

/**
 * 初始化服务端登录开关与当前会话状态。
 *
 * Returns:
 *   Promise<void>
 */
async function initializeAuthState() {
  try {
    const data = await getCurrentUser()
    setAuthEnabled(data.auth_enabled)
    if (!data.auth_enabled) {
      if (isAuthPublicRoute.value) {
        router.replace('/dashboard')
      }
      return
    }
    if (data.authenticated) {
      syncCurrentUserSession(data)
      return
    }
    clearAuthSession()
    redirectToLogin()
  } catch (error) {
    await recoverAuthBootstrap(error)
  } finally {
    authBootstrapping.value = false
  }
}

/**
 * 处理登录态失效事件。
 */
function handleAuthExpired() {
  clearAuthSession()
  if (!authState.authEnabled || isAuthPublicRoute.value) {
    return
  }
  router.replace({
    path: '/login',
    query: { redirect: route.fullPath },
  })
}

onMounted(() => {
  window.addEventListener(AUTH_EXPIRED_EVENT_NAME, handleAuthExpired)
  initializeAuthState()
})

onBeforeUnmount(() => {
  window.removeEventListener(AUTH_EXPIRED_EVENT_NAME, handleAuthExpired)
})
</script>

<template>
  <div v-if="authBootstrapping" class="app-loading-shell">
    <div class="app-loading-card">
      <div class="app-loading-title">Spec Agent</div>
      <div class="app-loading-text">正在初始化访问控制...</div>
    </div>
  </div>
  <router-view v-else-if="isAuthPage" />
  <el-container v-else class="app-shell">
    <el-aside class="app-sidebar" :class="{ collapsed: sidebarCollapsed }" :width="sidebarCollapsed ? '66px' : '220px'">
      <div class="brand">
        <div class="brand-logo">S</div>
        <div v-if="!sidebarCollapsed" class="brand-text">
          <div class="brand-title">Spec Agent</div>
          <div class="brand-subtitle">谱图智能分析平台</div>
        </div>
      </div>
      <div class="sidebar-nav">
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
            <el-menu-item index="/tools/lcms-convert">LCMS 数据转化</el-menu-item>
            <el-menu-item v-if="canAccessAdminFeatures" index="/tools/acceptance">评测中心</el-menu-item>
          </el-sub-menu>
          <el-sub-menu v-if="canAccessAdminFeatures" index="/experiments">
            <template #title>
              <el-icon><FolderOpened /></el-icon>
              <span>实验管理</span>
            </template>
            <el-menu-item index="/experiments/collect">数据采集</el-menu-item>
            <el-menu-item index="/experiments/samples">样本管理</el-menu-item>
          </el-sub-menu>
          <el-sub-menu v-if="canAccessAdminFeatures" index="/admin">
            <template #title>
              <el-icon><SetUp /></el-icon>
              <span>系统管理</span>
            </template>
            <el-menu-item index="/admin/users">
              <el-icon><User /></el-icon>
              <span>用户管理</span>
            </el-menu-item>
            <el-menu-item index="/admin/invite-codes">
              <el-icon><Key /></el-icon>
              <span>邀请码管理</span>
            </el-menu-item>
          </el-sub-menu>
          <el-menu-item index="/docs">
            <el-icon><Document /></el-icon>
            <span>接口文档</span>
          </el-menu-item>
        </el-menu>
      </div>
      <div class="sidebar-version" :class="{ collapsed: sidebarCollapsed }">
        <span class="sidebar-version-label">版本</span>
        <span class="sidebar-version-value">{{ APP_VERSION }}</span>
      </div>
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
          <el-tag v-if="currentUserRoleLabel" effect="plain">{{ currentUserRoleLabel }}</el-tag>
          <el-avatar size="small">{{ currentUserAvatarText }}</el-avatar>
          <span>{{ currentUserDisplayName }}</span>
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
