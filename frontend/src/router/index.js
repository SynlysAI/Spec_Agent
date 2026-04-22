import { createRouter, createWebHistory } from 'vue-router'

import DashboardView from '../views/DashboardView.vue'
import TaskSubmitGpcView from '../views/TaskSubmitGpcView.vue'
import TaskSubmitNmrView from '../views/TaskSubmitNmrView.vue'
import TaskCenterView from '../views/TaskCenterView.vue'
import TaskDetailView from '../views/TaskDetailView.vue'
import TaskSubmitIrRamanView from '../views/TaskSubmitIrRamanView.vue'
import TaskSubmitLcmsView from '../views/TaskSubmitLcmsView.vue'
import ToolNmrServerView from '../views/ToolNmrServerView.vue'
import ToolRamanCaptureView from '../views/ToolRamanCaptureView.vue'
import DialogueView from '../views/DialogueView.vue'
import ToolAcceptanceView from '../views/ToolAcceptanceView.vue'
import ExperimentCollectView from '../views/ExperimentCollectView.vue'
import ExperimentSampleManageView from '../views/ExperimentSampleManageView.vue'

const routes = [
  { path: '/', redirect: '/dashboard' },
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
  { path: '/tools/acceptance', component: ToolAcceptanceView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
