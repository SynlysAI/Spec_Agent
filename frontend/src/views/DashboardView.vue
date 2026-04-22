<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getApiErrorMessage,
  getLabCollectRuns,
  getMolecularStatistics,
  refreshMolecularStatistics,
  getSpectrumSampleSummary,
  listTasks,
} from '../api/specAgentApi'

const router = useRouter()
const loading = ref(false)
const molecularRefreshing = ref(false)
const sampleSummary = ref(null)
const molecularStats = ref(null)
const taskSummary = ref({
  total: 0,
  queued: 0,
  running: 0,
  success: 0,
  failed: 0,
})
const taskTypeItems = ref([])
const systemDynamics = ref([])

const molecularCards = computed(() => [
  { title: '去重 SMILES', value: molecularStats.value?.unique_smiles_count ?? 0, featured: true },
  { title: '分子骨架', value: molecularStats.value?.unique_scaffold_count ?? 0 },
  { title: '官能团类型', value: molecularStats.value?.unique_functional_group_count ?? 0 },
])

const sampleCards = computed(() => {
  const typeCounts = sampleSummary.value?.type_counts || {}
  return [
    { title: '总样本数', value: sampleSummary.value?.total_samples ?? 0, featured: true },
    { title: 'NMR', value: typeCounts.nmr ?? 0 },
    { title: 'GPC', value: typeCounts.gpc ?? 0 },
    { title: 'IR', value: typeCounts.ir ?? 0 },
    { title: 'RAMAN', value: typeCounts.raman ?? 0 },
    { title: 'LCMS', value: typeCounts.lcms ?? 0 },
  ]
})

/**
 * 格式化显示时间。
 *
 * Args:
 *   value: 原始时间值。
 *
 * Returns:
 *   可读时间字符串。
 */
function formatDisplayTime(value) {
  if (!value) {
    return '--'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return String(value)
  }
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hour}:${minute}`
}

/**
 * 加载工作台首页数据。
 *
 * Returns:
 *   Promise<void>
 */
async function loadDashboard() {
  loading.value = true
  try {
    const [
      sampleData,
      molecularData,
      all,
      queued,
      running,
      success,
      failed,
      latestCollect,
      latestFailed,
      gpc,
      nmr,
      ir,
      raman,
      lcms,
    ] = await Promise.all([
      getSpectrumSampleSummary(),
      getMolecularStatistics(),
      listTasks({ page: 1, page_size: 1 }),
      listTasks({ page: 1, page_size: 1, status: 'QUEUED' }),
      listTasks({ page: 1, page_size: 1, status: 'RUNNING' }),
      listTasks({ page: 1, page_size: 1, status: 'SUCCESS' }),
      listTasks({ page: 1, page_size: 1, status: 'FAILED' }),
      getLabCollectRuns(1),
      listTasks({ page: 1, page_size: 1, status: 'FAILED' }),
      listTasks({ page: 1, page_size: 1, task_type: 'gpc_analysis' }),
      listTasks({ page: 1, page_size: 1, task_type: 'nmr_analysis' }),
      listTasks({ page: 1, page_size: 1, task_type: 'ir_analysis' }),
      listTasks({ page: 1, page_size: 1, task_type: 'raman_analysis' }),
      listTasks({ page: 1, page_size: 1, task_type: 'lcms_analysis' }),
    ])

    sampleSummary.value = sampleData
    molecularStats.value = molecularData
    taskSummary.value = {
      total: all.total,
      queued: queued.total,
      running: running.total,
      success: success.total,
      failed: failed.total,
    }
    taskTypeItems.value = [
      { label: 'GPC', value: gpc.total, route: '/tasks/submit/gpc' },
      { label: 'NMR', value: nmr.total, route: '/tasks/submit/nmr' },
      { label: 'IR', value: ir.total, route: '/tasks/submit/ir' },
      { label: 'RAMAN', value: raman.total, route: '/tasks/submit/raman' },
      { label: 'LCMS', value: lcms.total, route: '/tasks/submit/lcms' },
    ]

    const latestRun = latestCollect.items?.[0] || null
    const latestFailedTask = latestFailed.items?.[0] || null
    systemDynamics.value = [
      {
        title: '最近采集批次',
        value: latestRun ? `${latestRun.run_id} · ${latestRun.status}` : '暂无采集记录',
        hint: latestRun ? `${latestRun.date_from} ~ ${latestRun.date_to}` : '等待首次采集',
      },
      {
        title: '最近失败任务',
        value: latestFailedTask ? `${latestFailedTask.task_id} · ${latestFailedTask.task_type}` : '当前无失败任务',
        hint: latestFailedTask ? `状态：${latestFailedTask.status}` : '任务运行正常',
      },
      {
        title: '最近数据更新时间',
        value: formatDisplayTime(sampleData?.latest_updated_at || latestRun?.updated_at || null),
        hint: sampleData?.latest_updated_at ? '来自样本主档更新时间' : '暂无样本更新时间',
      },
    ]
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

/**
 * 手动刷新分子资产统计。
 *
 * Returns:
 *   Promise<void>
 */
async function updateMolecularStatistics() {
  molecularRefreshing.value = true
  try {
    molecularStats.value = await refreshMolecularStatistics()
    ElMessage.success('分子资产统计已更新')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    molecularRefreshing.value = false
  }
}

/**
 * 跳转到指定页面。
 *
 * Args:
 *   path: 页面路由。
 */
function goTo(path) {
  router.push(path)
}

onMounted(loadDashboard)
</script>

<template>
  <div class="page-grid dashboard-grid">
    <div class="dashboard-main">
      <section class="panel">
        <div class="panel-header">
          <h3 class="panel-title">样本资产概览</h3>
          <el-button type="primary" plain :loading="loading" @click="loadDashboard">刷新</el-button>
        </div>
        <div class="panel-body" v-loading="loading">
          <div class="dashboard-sample-grid">
            <div v-for="item in sampleCards" :key="item.title" class="sample-card" :class="{ featured: item.featured }">
              <div class="sample-card-title">{{ item.title }}</div>
              <div class="sample-card-value">{{ item.value }}</div>
            </div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3 class="panel-title">分子资产概览</h3>
          <el-button type="primary" plain :loading="molecularRefreshing" @click="updateMolecularStatistics">
            更新统计
          </el-button>
        </div>
        <div class="panel-body" v-loading="loading || molecularRefreshing">
          <div class="dashboard-sample-grid">
            <div v-for="item in molecularCards" :key="item.title" class="sample-card" :class="{ featured: item.featured }">
              <div class="sample-card-title">{{ item.title }}</div>
              <div class="sample-card-value">{{ item.value }}</div>
            </div>
          </div>
          <div class="molecular-meta">
            <div>最近更新时间：{{ formatDisplayTime(molecularStats?.updated_at) }}</div>
            <div>统计状态：{{ molecularStats?.status || 'EMPTY' }}</div>
            <div>数据来源：样本库 `sample_meta.smiles` 去重统计</div>
            <div v-if="molecularStats?.is_stale" class="stale-text">样本库已变更，建议手动更新统计</div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3 class="panel-title">任务运行态势</h3>
        </div>
        <div class="panel-body">
          <div class="dashboard-task-grid">
            <div class="stat-card">
              <div class="stat-title">任务总数</div>
              <div class="stat-value">{{ taskSummary.total }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-title">排队中</div>
              <div class="stat-value">{{ taskSummary.queued }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-title">执行中</div>
              <div class="stat-value">{{ taskSummary.running }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-title">已成功</div>
              <div class="stat-value">{{ taskSummary.success }}</div>
            </div>
            <div class="stat-card danger-card">
              <div class="stat-title">已失败</div>
              <div class="stat-value">{{ taskSummary.failed }}</div>
            </div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3 class="panel-title">任务类型分布</h3>
        </div>
        <div class="panel-body">
          <div class="dashboard-type-grid">
            <div v-for="item in taskTypeItems" :key="item.label" class="type-card">
              <div class="type-card-top">
                <div class="type-card-title">{{ item.label }}</div>
                <div class="type-card-value">{{ item.value }}</div>
              </div>
              <el-button link type="primary" @click="goTo(item.route)">去提交</el-button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <div class="dashboard-side">
      <section class="panel">
        <div class="panel-header">
          <h3 class="panel-title">系统动态</h3>
        </div>
        <div class="panel-body" v-loading="loading">
          <div v-for="item in systemDynamics" :key="item.title" class="dynamic-item">
            <div class="dynamic-title">{{ item.title }}</div>
            <div class="dynamic-value">{{ item.value }}</div>
            <div class="dynamic-hint">{{ item.hint }}</div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <h3 class="panel-title">快捷入口</h3>
        </div>
        <div class="panel-body">
          <div class="quick-link-grid">
            <el-button plain @click="goTo('/tasks/submit/gpc')">GPC 提交</el-button>
            <el-button plain @click="goTo('/tasks/submit/nmr')">NMR 提交</el-button>
            <el-button plain @click="goTo('/tasks/submit/ir')">IR 提交</el-button>
            <el-button plain @click="goTo('/tasks/submit/raman')">Raman 提交</el-button>
            <el-button plain @click="goTo('/tasks/submit/lcms')">LCMS 提交</el-button>
            <el-button plain @click="goTo('/experiments/collect')">数据采集</el-button>
            <el-button plain @click="goTo('/experiments/samples')">样本管理</el-button>
            <el-button plain @click="goTo('/tasks/center')">任务中心</el-button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.dashboard-grid {
  align-items: start;
}

.dashboard-main,
.dashboard-side {
  display: grid;
  gap: 16px;
}

.dashboard-sample-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.sample-card {
  padding: 16px;
  border: 1px solid #deebfb;
  border-radius: 12px;
  background: linear-gradient(180deg, #fbfdff 0%, #f4f8ff 100%);
}

.sample-card.featured {
  background: linear-gradient(135deg, #f4f8ff 0%, #e7f0ff 100%);
  border-color: #cfe0fb;
}

.sample-card-title {
  color: #6d81a1;
  font-size: 13px;
}

.sample-card-value {
  margin-top: 10px;
  color: #1e4375;
  font-size: 28px;
  font-weight: 700;
}

.molecular-meta {
  margin-top: 14px;
  color: #7083a2;
  font-size: 13px;
  line-height: 1.9;
}

.stale-text {
  color: #c56a00;
  font-weight: 600;
}

.dashboard-task-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.danger-card {
  border-color: #f3d5d8;
  background: linear-gradient(180deg, #fffafb 0%, #fff2f4 100%);
}

.dashboard-type-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.type-card {
  padding: 14px 16px;
  border: 1px solid #deebfb;
  border-radius: 12px;
  background: #ffffff;
}

.type-card-top {
  margin-bottom: 10px;
}

.type-card-title {
  color: #6d81a1;
  font-size: 13px;
}

.type-card-value {
  margin-top: 8px;
  color: #224777;
  font-size: 24px;
  font-weight: 700;
}

.dynamic-item + .dynamic-item {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid #edf2fa;
}

.dynamic-title {
  color: #7385a2;
  font-size: 13px;
}

.dynamic-value {
  margin-top: 6px;
  color: #2a3f62;
  font-size: 14px;
  font-weight: 600;
  word-break: break-all;
}

.dynamic-hint {
  margin-top: 6px;
  color: #8d9db8;
  font-size: 12px;
}

.quick-link-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.quick-link-grid .el-button {
  margin-left: 0;
  justify-content: flex-start;
}

@media (max-width: 1200px) {
  .dashboard-sample-grid,
  .dashboard-task-grid,
  .dashboard-type-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .dashboard-sample-grid,
  .dashboard-task-grid,
  .dashboard-type-grid,
  .quick-link-grid {
    grid-template-columns: 1fr;
  }
}
</style>
