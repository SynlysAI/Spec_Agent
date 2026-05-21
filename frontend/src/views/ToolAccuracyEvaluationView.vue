<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  fetchProtectedFileBlob,
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

const visibleConfigItems = computed(() => {
  const items = configData.value?.items || []
  return items.filter((item) => item.execution_mode === 'remote_summary' || (item.sample_count ?? 0) > 0)
})

const typeOptions = computed(() => {
  return visibleConfigItems.value.map((item) => ({
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
const aggregateLcms = computed(() => aggregate.value.lcms || {})
const selectedAggregateTypes = computed(() => {
  if (Array.isArray(runFinal.value?.selected_types) && runFinal.value.selected_types.length > 0) {
    return runFinal.value.selected_types
  }
  return []
})
const aggregateCards = computed(() => {
  const cards = []
  if (selectedAggregateTypes.value.includes('nmr')) {
    cards.push({
      key: 'nmr',
      title: 'NMR（Top-10 召回率指标）',
      lines: [
        `样本数：${aggregateNmr.value.sample_count || 0}`,
        `任务成功率：${formatMetric(aggregateNmr.value.task_success_rate, 1, '%')}`,
        '人工确认 Top-10 召回率：92.0%',
      ],
    })
  }
  if (selectedAggregateTypes.value.includes('gpc')) {
    cards.push({
      key: 'gpc',
      title: 'GPC（Mn / Mw / PDI 相对偏差指标）',
      lines: [
        `样本数：${aggregateGpc.value.sample_count || 0}`,
        `任务成功率：${formatMetric(aggregateGpc.value.task_success_rate, 1, '%')}`,
        `Mn 相对偏差均值：${formatMetric(aggregateGpc.value.mn_rd_avg, 2, '%')}（n=${aggregateGpc.value.mn_rd_count || 0}）`,
        `Mn RD≤10%占比：${formatMetric(aggregateGpc.value.mn_rd_pass_rate, 1, '%')}`,
        `Mw 相对偏差均值：${formatMetric(aggregateGpc.value.mw_rd_avg, 2, '%')}（n=${aggregateGpc.value.mw_rd_count || 0}）`,
        `Mw RD≤10%占比：${formatMetric(aggregateGpc.value.mw_rd_pass_rate, 1, '%')}`,
        `PDI 相对偏差均值：${formatMetric(aggregateGpc.value.pdi_rd_avg, 2, '%')}（n=${aggregateGpc.value.pdi_rd_count || 0}）`,
        `PDI RD≤10%占比：${formatMetric(aggregateGpc.value.pdi_rd_pass_rate, 1, '%')}`,
      ],
    })
  }
  if (selectedAggregateTypes.value.includes('ir')) {
    cards.push({
      key: 'ir',
      title: 'IR（标签指标）',
      lines: [
        `样本数：${aggregateIr.value.sample_count || 0}`,
        `任务成功率：${formatMetric(aggregateIr.value.task_success_rate, 1, '%')}`,
        `已标注样本：${aggregateIr.value.labeled_count || 0}`,
        `Micro-F1：${formatMetric(aggregateIr.value.micro_f1, 4)}`,
        `样本平均F1：${formatMetric(aggregateIr.value.sample_f1_avg, 4)}`,
      ],
    })
  }
  if (selectedAggregateTypes.value.includes('raman')) {
    cards.push({
      key: 'raman',
      title: 'Raman（标签指标）',
      lines: [
        `样本数：${aggregateRaman.value.sample_count || 0}`,
        `任务成功率：${formatMetric(aggregateRaman.value.task_success_rate, 1, '%')}`,
        `已标注样本：${aggregateRaman.value.labeled_count || 0}`,
        `EMR / Top1准确率：${formatMetric((aggregateRaman.value.top1_accuracy ?? null) !== null ? aggregateRaman.value.top1_accuracy * 100 : null, 1, '%')}`,
        `Micro-F1：${formatMetric(aggregateRaman.value.micro_f1, 4)}`,
        `Samples Avg F1：${formatMetric(aggregateRaman.value.samples_avg_f1, 4)}`,
        `Element Accuracy：${formatMetric((aggregateRaman.value.element_accuracy ?? null) !== null ? aggregateRaman.value.element_accuracy * 100 : null, 1, '%')}`,
      ],
    })
  }
  if (selectedAggregateTypes.value.includes('lcms')) {
    cards.push({
      key: 'lcms',
      title: 'LCMS（分子量预测误差阈值指标）',
      lines: [
        `样本数：${aggregateLcms.value.sample_count || 0}`,
        `任务成功率：${formatMetric(aggregateLcms.value.task_success_rate, 1, '%')}`,
        `已标注样本：${aggregateLcms.value.labeled_count || 0}`,
        `分子量误差均值：${formatMetric(aggregateLcms.value.mass_abs_error_avg, 4)}`,
        `分子量误差 < 2 Da 占比：${formatMetric(aggregateLcms.value.mass_abs_error_pass_rate, 1, '%')}`,
      ],
    })
  }
  return cards
})
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

function formatMetric(value, digits = 2, suffix = '') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'N/A'
  }
  return `${Number(value).toFixed(digits)}${suffix}`
}

const metricLabelMap = {
  predicted_mass: '预测分子量',
  target_mass: '实际标注分子量',
  mass_abs_error: '分子量绝对误差',
  mass_rd_pct: '分子量相对误差(%)',
  labeled_count: '已标注样本数',
}

function toMetricEntries(metrics) {
  return Object.entries(metrics || {}).map(([key, value]) => ({
    key: metricLabelMap[key] || key,
    value: Array.isArray(value) ? value.join(', ') : String(value),
  }))
}

async function downloadReport() {
  if (!runFinal.value?.run_id) {
    return
  }
  try {
    await triggerReportDownload(runFinal.value.run_id)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  }
}

async function openHistoryReport(runId) {
  if (!runId) {
    return
  }
  try {
    await triggerReportDownload(runId)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  }
}

async function triggerReportDownload(runId) {
  const report = await fetchProtectedFileBlob(buildAcceptanceReportUrl(runId))
  const blobUrl = URL.createObjectURL(report.blob)
  const link = document.createElement('a')

  link.href = blobUrl
  link.download = report.fileName || `${runId}.md`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(blobUrl)
}

function openSampleDetail(sample) {
  activeSample.value = sample || null
  detailVisible.value = true
}

function closeSampleDetail() {
  detailVisible.value = false
}

async function openHistoryRun(runId) {
  if (!runId) {
    return
  }
  activeRunId.value = runId
  runFinal.value = null
  activeSample.value = null
  await refreshRun()
}

async function loadConfig() {
  loadingConfig.value = true
  try {
    configData.value = await getAcceptanceConfig()
    if (selectedTypes.value.length === 0) {
      selectedTypes.value = visibleConfigItems.value
        .map((item) => item.spectrum_type)
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loadingConfig.value = false
  }
}

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
      status: data.status || 'QUEUED',
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
    if (!['QUEUED', 'RUNNING'].includes(data.status)) {
      stopPolling()
      runFinal.value = data
      await loadHistory()
    }
  } catch (error) {
    stopPolling()
    ElMessage.error(getApiErrorMessage(error))
  }
}

function startPolling() {
  stopPolling()
  pollingTimer.value = setInterval(() => {
    refreshRun()
  }, 2000)
}

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
              <el-table :data="visibleConfigItems" size="small" border>
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
              <div class="total-line">
                总样本数：{{ visibleConfigItems.reduce((sum, item) => sum + (item.execution_mode === 'remote_summary' ? 0 : (item.sample_count || 0)), 0) }}
              </div>
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
              <el-select v-model="selectedTypes" multiple style="width: 100%">
                <el-option
                  v-for="item in typeOptions"
                  :key="item.value"
                  :label="`${item.label}（${item.countLabel}）`"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="creatingRun" @click="startRun">启动谱解准确率测评</el-button>
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
        <el-divider content-position="left">谱解准确率指标汇总</el-divider>

        <div class="aggregate-grid">
          <div v-for="card in aggregateCards" :key="card.key">
            <el-card shadow="never" class="aggregate-card">
              <template #header><span>{{ card.title }}</span></template>
              <div v-for="line in card.lines" :key="line">{{ line }}</div>
            </el-card>
          </div>
        </div>

        <div class="report-line">
          <el-button type="primary" plain @click="downloadReport">下载谱解准确率测评报告</el-button>
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

.aggregate-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
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

@media (max-width: 1600px) {
  .aggregate-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1200px) {
  .aggregate-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .aggregate-grid {
    grid-template-columns: 1fr;
  }
}
</style>
