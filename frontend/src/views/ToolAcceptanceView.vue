<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  buildAcceptanceReportUrl,
  createAcceptanceRun,
  getAcceptanceConfig,
  getAcceptanceRun,
  getApiErrorMessage,
} from '../api/specAgentApi'

const router = useRouter()
const loadingConfig = ref(false)
const creatingRun = ref(false)
const configData = ref(null)
const runSummary = ref(null)
const runFinal = ref(null)
const activeRunId = ref('')
const pollingTimer = ref(null)

const selectedTypes = ref([])

const typeOptions = computed(() => {
  const items = configData.value?.items || []
  return items.map((item) => ({
    label: item.label,
    value: item.spectrum_type,
    count: item.sample_count,
  }))
})

const summaryRate = computed(() => {
  const summary = runSummary.value?.summary
  if (!summary || !summary.total) {
    return '0.0%'
  }
  return `${((summary.success / summary.total) * 100).toFixed(1)}%`
})

const aggregate = computed(() => runFinal.value?.aggregate_metrics || {})
const aggregateNmr = computed(() => aggregate.value.nmr || {})
const aggregateGpc = computed(() => aggregate.value.gpc || {})
const aggregateIr = computed(() => aggregate.value.ir || {})
const aggregateRaman = computed(() => aggregate.value.raman || {})

/**
 * 格式化指标显示值。
 *
 * Args:
 *   value: 原始指标值。
 *   digits: 小数位数。
 *   suffix: 单位后缀。
 *
 * Returns:
 *   格式化后的字符串。
 */
function formatMetric(value, digits = 2, suffix = '') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'N/A'
  }
  return `${Number(value).toFixed(digits)}${suffix}`
}

/**
 * 打开任务详情页（新窗口）。
 *
 * Args:
 *   taskId: 任务 ID。
 */
function openTaskDetail(taskId) {
  if (!taskId) {
    return
  }
  const detailUrl = router.resolve({ path: `/tasks/detail/${taskId}` }).href
  window.open(detailUrl, '_blank')
}

/**
 * 下载当前批次验收报告。
 */
function downloadReport() {
  if (!runFinal.value?.run_id) {
    return
  }
  window.open(buildAcceptanceReportUrl(runFinal.value.run_id), '_blank')
}

/**
 * 加载验收配置摘要。
 *
 * Returns:
 *   Promise<void>
 */
async function loadConfig() {
  loadingConfig.value = true
  try {
    configData.value = await getAcceptanceConfig()
    if (selectedTypes.value.length === 0) {
      selectedTypes.value = (configData.value?.items || [])
        .filter((item) => item.sample_count > 0)
        .map((item) => item.spectrum_type)
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loadingConfig.value = false
  }
}

/**
 * 启动批量验收运行。
 *
 * Returns:
 *   Promise<void>
 */
async function startRun() {
  if (selectedTypes.value.length === 0) {
    ElMessage.warning('请至少选择一个谱图类型')
    return
  }
  creatingRun.value = true
  try {
    const data = await createAcceptanceRun(selectedTypes.value)
    activeRunId.value = data.run_id
    runFinal.value = null
    runSummary.value = {
      run_id: data.run_id,
      status: data.status || 'RUNNING',
      summary: { total: 0, success: 0, failed: 0, progress: 0 },
      report_path: null,
    }
    await refreshRun()
    startPolling()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    creatingRun.value = false
  }
}

/**
 * 查询当前批次状态。
 *
 * Returns:
 *   Promise<void>
 */
async function refreshRun() {
  if (!activeRunId.value) {
    return
  }
  try {
    const data = await getAcceptanceRun(activeRunId.value)
    runSummary.value = {
      run_id: data.run_id,
      status: data.status,
      summary: data.summary,
      report_path: data.report_path || null,
    }
    if (data.status !== 'RUNNING') {
      stopPolling()
      runFinal.value = data
    }
  } catch (error) {
    stopPolling()
    ElMessage.error(getApiErrorMessage(error))
  }
}

/**
 * 启动状态轮询。
 */
function startPolling() {
  stopPolling()
  pollingTimer.value = setInterval(() => {
    refreshRun()
  }, 2000)
}

/**
 * 停止状态轮询。
 */
function stopPolling() {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

onMounted(async () => {
  await loadConfig()
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h3 class="panel-title">批量验收测试</h3>
    </div>
    <div class="panel-body">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-card shadow="never" class="block-card">
            <template #header>
              <div class="card-header">样本配置</div>
            </template>
            <el-skeleton :loading="loadingConfig" animated :rows="5">
              <template #default>
                <div class="config-path">配置文件：{{ configData?.config_path || '-' }}</div>
                <el-table :data="configData?.items || []" size="small" border>
                  <el-table-column prop="label" label="类型" min-width="120" />
                  <el-table-column prop="sample_count" label="样本数" width="90" />
                  <el-table-column label="目录">
                    <template #default="scope">
                      <span class="path-text">{{ (scope.row.dirs || []).join('；') || '-' }}</span>
                    </template>
                  </el-table-column>
                </el-table>
                <div class="total-line">总样本数：{{ configData?.total_samples || 0 }}</div>
              </template>
            </el-skeleton>
          </el-card>
        </el-col>

        <el-col :span="12">
          <el-card shadow="never" class="block-card">
            <template #header>
              <div class="card-header">执行控制</div>
            </template>
            <el-form label-position="top">
              <el-form-item label="执行类型">
                <el-select
                  v-model="selectedTypes"
                  multiple
                  style="width: 100%"
                >
                  <el-option
                    v-for="item in typeOptions"
                    :key="item.value"
                    :label="`${item.label}（${item.count}）`"
                    :value="item.value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="creatingRun" @click="startRun">启动批量验收</el-button>
                <el-button :disabled="!activeRunId" @click="refreshRun">刷新状态</el-button>
              </el-form-item>
            </el-form>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              title="说明"
              description="该模块会按样本配置自动创建任务并轮询状态，结果会生成 Markdown 报告。"
            />
          </el-card>
        </el-col>
      </el-row>

      <el-card v-if="runSummary" shadow="never" class="block-card">
        <template #header>
          <div class="card-header">运行状态（{{ runSummary.run_id }}）</div>
        </template>
        <el-row :gutter="16" class="metrics-row">
          <el-col :span="4"><el-statistic title="状态" :value="runSummary.status" /></el-col>
          <el-col :span="4"><el-statistic title="总样本" :value="runSummary.summary.total" /></el-col>
          <el-col :span="4"><el-statistic title="成功" :value="runSummary.summary.success" /></el-col>
          <el-col :span="4"><el-statistic title="失败" :value="runSummary.summary.failed" /></el-col>
          <el-col :span="4"><el-statistic title="成功率" :value="summaryRate" /></el-col>
          <el-col :span="4"><el-statistic title="进度" :value="`${runSummary.summary.progress}%`" /></el-col>
        </el-row>
        <el-progress :percentage="runSummary.summary.progress || 0" :stroke-width="14" />
        <div class="running-tip" v-if="runSummary.status === 'RUNNING'">
          运行中，完成后将一次性展示全部样本明细与指标汇总。
        </div>
      </el-card>

      <el-card v-if="runFinal && runFinal.status !== 'RUNNING'" shadow="never" class="block-card">
        <template #header>
          <div class="card-header">运行结果（{{ runFinal.run_id }}）</div>
        </template>
        <el-divider content-position="left">验收指标汇总</el-divider>

        <el-row :gutter="12" class="aggregate-row">
          <el-col :span="6">
            <el-card shadow="never" class="aggregate-card">
              <template #header><span>NMR（可自动计算）</span></template>
              <div>样本数：{{ aggregateNmr.sample_count || 0 }}</div>
              <div>任务成功率：{{ formatMetric(aggregateNmr.task_success_rate, 1, '%') }}</div>
              <div>基线RMSE均值：{{ formatMetric(aggregateNmr.baseline_rmse_avg, 4) }}</div>
              <div>基线达标率：{{ formatMetric(aggregateNmr.baseline_rmse_pass_rate, 1, '%') }}</div>
              <div>溶剂峰ppm误差均值：{{ formatMetric(aggregateNmr.solvent_ppm_error_avg, 4) }}</div>
              <div>溶剂峰达标率：{{ formatMetric(aggregateNmr.solvent_ppm_error_pass_rate, 1, '%') }}</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never" class="aggregate-card">
              <template #header><span>GPC（分子量偏差验收）</span></template>
              <div>样本数：{{ aggregateGpc.sample_count || 0 }}</div>
              <div>任务成功率：{{ formatMetric(aggregateGpc.task_success_rate, 1, '%') }}</div>
              <div>Mn偏差均值：{{ formatMetric(aggregateGpc.mn_rd_avg, 2, '%') }}（n={{ aggregateGpc.mn_rd_count || 0 }}）</div>
              <div>Mn达标率：{{ formatMetric(aggregateGpc.mn_rd_pass_rate, 1, '%') }}</div>
              <div>Mw偏差均值：{{ formatMetric(aggregateGpc.mw_rd_avg, 2, '%') }}（n={{ aggregateGpc.mw_rd_count || 0 }}）</div>
              <div>Mw达标率：{{ formatMetric(aggregateGpc.mw_rd_pass_rate, 1, '%') }}</div>
              <div>PDI偏差均值：{{ formatMetric(aggregateGpc.pdi_rd_avg, 2, '%') }}（n={{ aggregateGpc.pdi_rd_count || 0 }}）</div>
              <div>PDI达标率：{{ formatMetric(aggregateGpc.pdi_rd_pass_rate, 1, '%') }}</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never" class="aggregate-card">
              <template #header><span>IR（标签指标）</span></template>
              <div>样本数：{{ aggregateIr.sample_count || 0 }}</div>
              <div>任务成功率：{{ formatMetric(aggregateIr.task_success_rate, 1, '%') }}</div>
              <div>已标注样本：{{ aggregateIr.labeled_count || 0 }}</div>
              <div>Micro-F1：{{ formatMetric(aggregateIr.micro_f1, 4) }}</div>
              <div>样本平均F1：{{ formatMetric(aggregateIr.sample_f1_avg, 4) }}</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never" class="aggregate-card">
              <template #header><span>Raman（标签指标）</span></template>
              <div>样本数：{{ aggregateRaman.sample_count || 0 }}</div>
              <div>任务成功率：{{ formatMetric(aggregateRaman.task_success_rate, 1, '%') }}</div>
              <div>已标注样本：{{ aggregateRaman.labeled_count || 0 }}</div>
              <div>Top1准确率：{{ formatMetric((aggregateRaman.top1_accuracy ?? null) !== null ? aggregateRaman.top1_accuracy * 100 : null, 1, '%') }}</div>
              <div>Recall@3：{{ formatMetric((aggregateRaman.recall_at_3 ?? null) !== null ? aggregateRaman.recall_at_3 * 100 : null, 1, '%') }}</div>
            </el-card>
          </el-col>
        </el-row>

        <div class="report-line">
          <el-button type="primary" plain @click="downloadReport">下载批量验收报告</el-button>
        </div>
        <el-table :data="runFinal.results || []" size="small" border max-height="420">
          <el-table-column prop="spectrum_type" label="类型" width="90" />
          <el-table-column prop="sample_name" label="样本" min-width="220" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="duration_seconds" label="耗时(s)" width="110" />
          <el-table-column prop="task_id" label="任务ID" min-width="240" />
          <el-table-column prop="error_message" label="错误信息" min-width="220" />
          <el-table-column label="操作" width="110" fixed="right">
            <template #default="scope">
              <el-button link type="primary" @click="openTaskDetail(scope.row.task_id)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.block-card {
  margin-bottom: 16px;
}

.card-header {
  font-weight: 600;
  color: #2b3447;
}

.config-path {
  margin-bottom: 8px;
  color: #627089;
  font-size: 13px;
}

.total-line {
  margin-top: 10px;
  font-weight: 600;
}

.path-text {
  color: #5f6d84;
  font-size: 12px;
}

.metrics-row {
  margin-bottom: 12px;
}

.running-tip {
  margin-top: 10px;
  color: #627089;
  font-size: 13px;
}

.aggregate-row {
  margin-bottom: 12px;
}

.aggregate-card {
  font-size: 13px;
  line-height: 1.8;
}

.report-line {
  margin-bottom: 10px;
  color: #5f6d84;
}
</style>



