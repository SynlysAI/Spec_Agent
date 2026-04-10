import { createRouter, createWebHistory } from 'vue-router'

import DashboardView from '../views/DashboardView.vue'
import TaskSubmitView from '../views/TaskSubmitView.vue'
import TaskCenterView from '../views/TaskCenterView.vue'
import TaskDetailView from '../views/TaskDetailView.vue'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', component: DashboardView },
  { path: '/tasks/submit', component: TaskSubmitView },
  { path: '/tasks/center', component: TaskCenterView },
  { path: '/tasks/detail/:taskId', component: TaskDetailView, props: true },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
