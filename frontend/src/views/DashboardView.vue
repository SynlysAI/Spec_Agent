<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listTasks } from '../api/specAgentApi'

const router = useRouter()
const loading = ref(false)
const summary = ref({
  total: 0,
  queued: 0,
  running: 0,
  success: 0,
  failed: 0,
})
const recentTasks = ref([])

/**
 * 加载工作台汇总信息。
 *
 * Returns:
 *   Promise<void>
 */
async function loadDashboard() {
  loading.value = true
  try {
    const [all, queued, running, success, failed] = await Promise.all([
      listTasks({ page: 1, page_size: 8 }),
      listTasks({ page: 1, page_size: 1, status: 'QUEUED' }),
      listTasks({ page: 1, page_size: 1, status: 'RUNNING' }),
      listTasks({ page: 1, page_size: 1, status: 'SUCCESS' }),
      listTasks({ page: 1, page_size: 1, status: 'FAILED' }),
    ])
    summary.value = {
      total: all.total,
      queued: queued.total,
      running: running.total,
      success: success.total,
      failed: failed.total,
    }
    recentTasks.value = all.items || []
  } finally {
    loading.value = false
  }
}

/**
 * 跳转到任务详情页。
 *
 * Args:
 *   taskId: 任务 ID。
 */
function goTaskDetail(taskId) {
  router.push(`/tasks/detail/${taskId}`)
}

onMounted(loadDashboard)
</script>

<template>
  <div class="page-grid">
    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">工作台概览</h3>
        <el-button type="primary" plain @click="loadDashboard">刷新</el-button>
      </div>
      <div class="panel-body">
        <div class="stat-grid">
          <div class="stat-card">
            <div class="stat-title">任务总数</div>
            <div class="stat-value">{{ summary.total }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-title">排队中</div>
            <div class="stat-value">{{ summary.queued }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-title">执行中</div>
            <div class="stat-value">{{ summary.running }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-title">已成功</div>
            <div class="stat-value">{{ summary.success }}</div>
          </div>
        </div>

        <el-divider />

        <el-table :data="recentTasks" v-loading="loading" stripe>
          <el-table-column prop="task_id" label="任务ID" min-width="240" />
          <el-table-column prop="task_type" label="任务类型" width="130" />
          <el-table-column prop="status" label="状态" width="110" />
          <el-table-column prop="progress" label="进度" width="110" />
          <el-table-column label="操作" width="100">
            <template #default="scope">
              <el-button link type="primary" @click="goTaskDetail(scope.row.task_id)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">公告</h3>
      </div>
      <div class="panel-body">
        <el-timeline>
          <el-timeline-item timestamp="2026-04-10" type="primary">Phase 2 前端实施启动</el-timeline-item>
          <el-timeline-item timestamp="2026-04-10" type="success">GPC/NMR API 链路已打通</el-timeline-item>
          <el-timeline-item timestamp="2026-04-10">下一步：任务中心与提交页完善</el-timeline-item>
        </el-timeline>
      </div>
    </div>
  </div>
</template>
