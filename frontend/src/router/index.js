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
  { path: '/login', component: LoginView, meta: { public: true } },
  { path: '/register', component: RegisterView, meta: { public: true } },
  { path: '/dashboard', component: DashboardView },
  { path: '/tasks/submit', redirect: '/tasks/submit/gpc' },
  { path: '/tasks/submit/gpc', component: TaskSubmitGpcView },
  { path: '/tasks/submit/nmr', component: TaskSubmitNmrView },
  { path: '/tasks/submit/ir', component: TaskSubmitIrRamanView, props: { spectype: 'ir' } },
  { path: '/tasks/submit/raman', component: TaskSubmitIrRamanView, props: { spectype: 'raman' } },
  { path: '/tasks/submit/lcms', component: TaskSubmitLcmsView },
  { path: '/tasks/center', component: TaskCenterView },
  { path: '/tasks/detail/:taskId', component: TaskDetailView, props: true },
  { path: '/dialogue', component: DialogueView },
  { path: '/experiments/collect', component: ExperimentCollectView, meta: { requiresRole: 'admin' } },
  { path: '/experiments/samples', component: ExperimentSampleManageView, meta: { requiresRole: 'admin' } },
  { path: '/admin/users', component: AdminUserManageView, meta: { requiresRole: 'admin' } },
  { path: '/admin/invite-codes', component: AdminInviteCodeManageView, meta: { requiresRole: 'admin' } },
  { path: '/tools/nmrserver', component: ToolNmrServerView },
  { path: '/tools/raman-capture', component: ToolRamanCaptureView },
  { path: '/tools/lcms-convert', component: ToolLcmsConvertView },
  { path: '/tools/acceptance', component: ToolEvaluationCenterView, meta: { requiresRole: 'admin' } },
  { path: '/:pathMatch(.*)*', component: NotFoundView, meta: { public: true } },
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
