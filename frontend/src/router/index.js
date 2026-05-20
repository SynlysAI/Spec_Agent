import { createRouter, createWebHistory } from 'vue-router'

import { authState } from '../auth/authState'
import DashboardView from '../views/DashboardView.vue'
import DialogueView from '../views/DialogueView.vue'
import ExperimentCollectView from '../views/ExperimentCollectView.vue'
import ExperimentSampleManageView from '../views/ExperimentSampleManageView.vue'
import LoginView from '../views/LoginView.vue'
import NotFoundView from '../views/NotFoundView.vue'
import TaskCenterView from '../views/TaskCenterView.vue'
import TaskDetailView from '../views/TaskDetailView.vue'
import TaskSubmitGpcView from '../views/TaskSubmitGpcView.vue'
import TaskSubmitIrRamanView from '../views/TaskSubmitIrRamanView.vue'
import TaskSubmitLcmsView from '../views/TaskSubmitLcmsView.vue'
import TaskSubmitNmrView from '../views/TaskSubmitNmrView.vue'
import ToolAcceptanceView from '../views/ToolAcceptanceView.vue'
import ToolLcmsConvertView from '../views/ToolLcmsConvertView.vue'
import ToolNmrServerView from '../views/ToolNmrServerView.vue'
import ToolRamanCaptureView from '../views/ToolRamanCaptureView.vue'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', component: LoginView, meta: { public: true } },
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
  { path: '/experiments/collect', component: ExperimentCollectView },
  { path: '/experiments/samples', component: ExperimentSampleManageView },
  { path: '/tools/nmrserver', component: ToolNmrServerView },
  { path: '/tools/raman-capture', component: ToolRamanCaptureView },
  { path: '/tools/lcms-convert', component: ToolLcmsConvertView },
  { path: '/tools/acceptance', component: ToolAcceptanceView },
  { path: '/:pathMatch(.*)*', component: NotFoundView, meta: { public: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (!authState.authEnabled) {
    if (to.path === '/login') {
      return '/dashboard'
    }
    return true
  }

  if (!authState.initialized) {
    return true
  }

  if (to.meta.public === true) {
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
  return true
})

export default router
