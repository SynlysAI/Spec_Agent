<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  buildAcceptanceReportUrl,
  createAcceptanceRun,
  getAcceptanceConfig,
  getAcceptanceRun,
  getAcceptanceRuns,
  getApiErrorMessage,
  getStaticBaseUrl,
} from '../api/specAgentApi'

const loadingConfig = ref(false)
const creatingRun = ref(false)
const loadingHistory = ref(false)
const configData = ref(null)
const runSummary = ref(null)
const runFinal = ref(null)
const historyItems = ref([])
const activeRunId = ref('')
const pollingTimer = ref(null)
const detailVisible = ref(false)
const activeSample = ref(null)

const selectedTypes = ref([])

const typeOptions = computed(() => {
  const items = configData.value?.items || []
  return items.map((item) => ({
    label: item.label,
    value: item.spectrum_type,
    countLabel: item.execution_mode === 'remote_summary' ? '远程' : String(item.sample_count ?? 0),
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
const activeArtifacts = computed(() => {
  const baseUrl = getStaticBaseUrl()
  return (activeSample.value?.artifacts || []).map((artifact) => ({
    ...artifact,
    absolute_url: String(artifact?.url || '').startsWith('http')
      ? artifact.url
      : `${baseUrl}${artifact?.url || ''}`,
  }))
})
const activeMetrics = computed(() => activeSample.value?.metrics || {})
const hasRunDetails = computed(() => Array.isArray(runFinal.value?.results) && runFinal.value.results.length > 0)

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
 * 将指标对象转成可展示数组。
 *
 * Args:
 *   metrics: 指标对象。
 *
 * Returns:
 *   指标数组。
 */
function toMetricEntries(metrics) {
  return Object.entries(metrics || {}).map(([key, value]) => ({
    key,
    value: Array.isArray(value) ? value.join(', ') : String(value),
  }))
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
 * 打开历史批次报告。
 *
 * Args:
 *   runId: 批次运行 ID。
 */
function openHistoryReport(runId) {
  if (!runId) {
    return
  }
  window.open(buildAcceptanceReportUrl(runId), '_blank')
}

/**
 * 打开样本详情抽屉。
 *
 * Args:
 *   sample: 样本结果对象。
 */
function openSampleDetail(sample) {
  activeSample.value = sample || null
  detailVisible.value = true
}

/**
 * 关闭样本详情抽屉。
 */
function closeSampleDetail() {
  detailVisible.value = false
}

/**
 * 加载历史批次详情。
 *
 * Args:
 *   runId: 批次运行 ID。
 *
 * Returns:
 *   Promise<void>
 */
async function openHistoryRun(runId) {
  if (!runId) {
    return
  }
  activeRunId.value = runId
  runFinal.value = null
  activeSample.value = null
  await refreshRun()
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
        .filter((item) => item.execution_mode === 'remote_summary' || item.sample_count > 0)
        .map((item) => item.spectrum_type)
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loadingConfig.value = false
  }
}

/**
 * 加载验收历史批次列表。
 *
 * Returns:
 *   Promise<void>
 */
async function loadHistory() {
  loadingHistory.value = true
  try {
    const data = await getAcceptanceRuns(30)
    historyItems.value = data?.items || []
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loadingHistory.value = false
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
    activeSample.value = null
    runSummary.value = {
      run_id: data.run_id,
      status: data.status || 'RUNNING',
      summary: { total: 0, success: 0, failed: 0, progress: 0 },
      report_path: null,
    }
    await refreshRun()
    startPolling()
    await loadHistory()
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
      await loadHistory()
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
  await loadHistory()
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
                  <el-table-column label="执行模式" width="120">
                    <template #default="scope">
                      <el-tag
                        size="small"
                        :type="scope.row.execution_mode === 'remote_summary' ? 'warning' : 'success'"
                      >
                        {{ scope.row.execution_mode === 'remote_summary' ? '远程汇总' : '本地执行' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="样本数" width="90">
                    <template #default="scope">
                      {{ scope.row.execution_mode === 'remote_summary' ? '/' : (scope.row.sample_count ?? 0) }}
                    </template>
                  </el-table-column>
                  <el-table-column label="目录">
                    <template #default="scope">
                      <span class="path-text">
                        {{ scope.row.execution_mode === 'remote_summary' ? '远程脚本执行，不扫描本地目录' : ((scope.row.dirs || []).join('；') || '-') }}
                      </span>
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
                    :label="`${item.label}（${item.countLabel}）`"
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
              description="该模块会按样本配置直接批量执行解析并汇总结果，完成后生成 Markdown 报告。"
            />
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="block-card">
        <template #header>
          <div class="card-header">
            <span>历史批次</span>
            <el-button link type="primary" :loading="loadingHistory" @click="loadHistory">刷新</el-button>
          </div>
        </template>
        <el-table :data="historyItems" size="small" border v-loading="loadingHistory" max-height="280">
          <el-table-column prop="run_id" label="批次ID" min-width="220" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="started_at" label="开始时间" width="170" />
          <el-table-column prop="finished_at" label="结束时间" width="170" />
          <el-table-column label="执行类型" min-width="180">
            <template #default="scope">
              {{ (scope.row.selected_types || []).join(', ') || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="总样本" width="90">
            <template #default="scope">
              {{ scope.row.summary?.total ?? 0 }}
            </template>
          </el-table-column>
          <el-table-column label="成功/失败" width="120">
            <template #default="scope">
              {{ scope.row.summary?.success ?? 0 }} / {{ scope.row.summary?.failed ?? 0 }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="scope">
              <el-button link type="primary" @click="openHistoryRun(scope.row.run_id)">加载详情</el-button>
              <el-button
                link
                type="primary"
                :disabled="!scope.row.report_exists"
                @click="openHistoryReport(scope.row.run_id)"
              >
                打开报告
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

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
              <div>EMR / Top1准确率：{{ formatMetric((aggregateRaman.top1_accuracy ?? null) !== null ? aggregateRaman.top1_accuracy * 100 : null, 1, '%') }}</div>
              <div>Micro-F1：{{ formatMetric(aggregateRaman.micro_f1, 4) }}</div>
              <div>Samples Avg F1：{{ formatMetric(aggregateRaman.samples_avg_f1, 4) }}</div>
              <div>Element Accuracy：{{ formatMetric((aggregateRaman.element_accuracy ?? null) !== null ? aggregateRaman.element_accuracy * 100 : null, 1, '%') }}</div>
            </el-card>
          </el-col>
        </el-row>

        <div class="report-line">
          <el-button type="primary" plain @click="downloadReport">下载批量验收报告</el-button>
        </div>

        <el-alert
          v-if="!hasRunDetails"
          type="warning"
          :closable="false"
          show-icon
          title="历史详情降级"
          description="该历史批次仅存在 Markdown 报告，没有结构化快照，因此只展示批次摘要。"
          class="fallback-alert"
        />

        <el-table v-else :data="runFinal.results || []" size="small" border max-height="420">
          <el-table-column prop="spectrum_type" label="类型" width="90" />
          <el-table-column prop="sample_name" label="样本" min-width="220" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="duration_seconds" label="耗时(s)" width="110" />
          <el-table-column prop="sample_execution_id" label="样本执行ID" min-width="160" />
          <el-table-column prop="error_message" label="错误信息" min-width="220" />
          <el-table-column label="操作" width="110" fixed="right">
            <template #default="scope">
              <el-button link type="primary" @click="openSampleDetail(scope.row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </div>

  <el-drawer
    v-model="detailVisible"
    title="样本详情"
    size="45%"
    destroy-on-close
    @close="closeSampleDetail"
  >
    <template v-if="activeSample">
      <el-descriptions :column="1" border class="detail-section">
        <el-descriptions-item label="样本执行ID">{{ activeSample.sample_execution_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ activeSample.spectrum_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="样本">{{ activeSample.sample_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="路径">{{ activeSample.sample_path || '-' }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ activeSample.status || '-' }}</el-descriptions-item>
        <el-descriptions-item label="耗时(s)">{{ formatMetric(activeSample.duration_seconds, 2) }}</el-descriptions-item>
        <el-descriptions-item label="错误信息">{{ activeSample.error_message || '-' }}</el-descriptions-item>
      </el-descriptions>

      <div class="detail-section">
        <div class="detail-title">关键指标</div>
        <el-empty v-if="toMetricEntries(activeMetrics).length === 0" description="无可展示指标" :image-size="72" />
        <el-table v-else :data="toMetricEntries(activeMetrics)" size="small" border>
          <el-table-column prop="key" label="指标" width="180" />
          <el-table-column prop="value" label="取值" />
        </el-table>
      </div>

      <div class="detail-section">
        <div class="detail-title">文本报告</div>
        <el-empty v-if="!activeSample.text_report" description="无文本报告" :image-size="72" />
        <pre v-else class="report-preview">{{ activeSample.text_report }}</pre>
      </div>

      <div class="detail-section">
        <div class="detail-title">产物文件</div>
        <el-empty v-if="activeArtifacts.length === 0" description="无产物文件" :image-size="72" />
        <el-table v-else :data="activeArtifacts" size="small" border>
          <el-table-column prop="name" label="文件名" min-width="200" />
          <el-table-column prop="file_type" label="类型" width="100" />
          <el-table-column prop="relative_path" label="相对路径" min-width="220" />
          <el-table-column label="操作" width="100">
            <template #default="scope">
              <el-link :href="scope.row.absolute_url" target="_blank" type="primary">打开</el-link>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.block-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.fallback-alert {
  margin-bottom: 12px;
}

.detail-section {
  margin-bottom: 18px;
}

.detail-title {
  margin-bottom: 10px;
  font-weight: 600;
  color: #2b3447;
}

.report-preview {
  max-height: 320px;
  overflow: auto;
  padding: 12px;
  margin: 0;
  background: #f7f9fc;
  border: 1px solid #d8e1ef;
  border-radius: 6px;
  color: #2b3447;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
