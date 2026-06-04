import { createRouter, createWebHistory } from 'vue-router'

import { authState } from '../auth/authState'
import AdminInviteCodeManageView from '../views/AdminInviteCodeManageView.vue'
import AdminUserManageView from '../views/AdminUserManageView.vue'
import DashboardView from '../views/DashboardView.vue'
import DialogueView from '../views/DialogueView.vue'
import ExperimentCollectView from '../views/ExperimentCollectView.vue'
import ExperimentSampleManageView from '../views/ExperimentSampleManageView.vue'
import LoginView from '../views/LoginView.vue'
import NotFoundView from '../views/NotFoundView.vue'
import RegisterView from '../views/RegisterView.vue'
import TaskCenterView from '../views/TaskCenterView.vue'
import TaskDetailView from '../views/TaskDetailView.vue'
import TaskSubmitGpcView from '../views/TaskSubmitGpcView.vue'
import TaskSubmitIrRamanView from '../views/TaskSubmitIrRamanView.vue'
import TaskSubmitLcmsView from '../views/TaskSubmitLcmsView.vue'
import TaskSubmitNmrView from '../views/TaskSubmitNmrView.vue'
import ToolEvaluationCenterView from '../views/ToolEvaluationCenterView.vue'
import ToolLcmsConvertView from '../views/ToolLcmsConvertView.vue'
import ToolNmrServerView from '../views/ToolNmrServerView.vue'
import ToolRamanCaptureView from '../views/ToolRamanCaptureView.vue'

const AUTH_PUBLIC_PATHS = new Set(['/login', '/register'])

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', component: LoginView, meta: { public: true, title: '账号登录' } },
  { path: '/register', component: RegisterView, meta: { public: true, title: '邀请码注册' } },
  { path: '/dashboard', component: DashboardView, meta: { title: '工作台' } },
  { path: '/tasks/submit', redirect: '/tasks/submit/gpc' },
  { path: '/tasks/submit/gpc', component: TaskSubmitGpcView, meta: { section: '任务提交', title: 'GPC 提交' } },
  { path: '/tasks/submit/nmr', component: TaskSubmitNmrView, meta: { section: '任务提交', title: 'NMR 提交' } },
  { path: '/tasks/submit/ir', component: TaskSubmitIrRamanView, props: { spectype: 'ir' }, meta: { section: '任务提交', title: 'IR 提交' } },
  { path: '/tasks/submit/raman', component: TaskSubmitIrRamanView, props: { spectype: 'raman' }, meta: { section: '任务提交', title: 'Raman 提交' } },
  { path: '/tasks/submit/lcms', component: TaskSubmitLcmsView, meta: { section: '任务提交', title: 'LCMS 提交' } },
  { path: '/tasks/center', component: TaskCenterView, meta: { section: '任务中心', title: '任务列表' } },
  { path: '/tasks/detail/:taskId', component: TaskDetailView, props: true, meta: { section: '任务中心', title: '任务详情' } },
  { path: '/dialogue', component: DialogueView, meta: { title: '问答对话' } },
  { path: '/experiments/collect', component: ExperimentCollectView, meta: { requiresRole: 'admin', section: '实验管理', title: '数据采集' } },
  { path: '/experiments/samples', component: ExperimentSampleManageView, meta: { requiresRole: 'admin', section: '实验管理', title: '样本管理' } },
  { path: '/admin/users', component: AdminUserManageView, meta: { requiresRole: 'admin', section: '系统管理', title: '用户管理' } },
  { path: '/admin/invite-codes', component: AdminInviteCodeManageView, meta: { requiresRole: 'admin', section: '系统管理', title: '邀请码管理' } },
  { path: '/tools/nmrserver', component: ToolNmrServerView, meta: { section: '工具服务', title: '核磁预测服务' } },
  { path: '/tools/raman-capture', component: ToolRamanCaptureView, meta: { requiresRole: 'admin', section: '工具服务', title: '拉曼批量采集' } },
  { path: '/tools/lcms-convert', component: ToolLcmsConvertView, meta: { section: '工具服务', title: 'LCMS 数据转化' } },
  { path: '/tools/acceptance', component: ToolEvaluationCenterView, meta: { requiresRole: 'admin', section: '工具服务', title: '评测中心' } },
  { path: '/:pathMatch(.*)*', component: NotFoundView, meta: { public: true, title: '页面不存在' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const isAuthPublicRoute = AUTH_PUBLIC_PATHS.has(to.path)

  if (!authState.authEnabled) {
    if (isAuthPublicRoute) {
      return '/dashboard'
    }
    return true
  }

  if (!authState.initialized) {
    return true
  }

  if (isAuthPublicRoute) {
    if (authState.authenticated) {
      return '/dashboard'
    }
    return true
  }

  if (!authState.authenticated) {
    return {
      path: '/login',
      query: { redirect: to.fullPath },
    }
  }

  if (to.meta.requiresRole && authState.role !== to.meta.requiresRole) {
    return '/dashboard'
  }

  return true
})

export default router
