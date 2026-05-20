<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  buildConsistencyReportUrl,
  createConsistencyRun,
  fetchProtectedFileBlob,
  getApiErrorMessage,
  getConsistencyConfig,
  getConsistencyRun,
  getConsistencyRuns,
} from '../api/specAgentApi'

const loadingConfig = ref(false)
const creatingRun = ref(false)
const loadingHistory = ref(false)
const configData = ref(null)
const historyItems = ref([])
const activeRunId = ref('')
const runSummary = ref(null)
const runFinal = ref(null)
const pollingTimer = ref(null)
const selectedDevices = ref([])
const selectedDetailDevice = ref('')
const detailVisible = ref(false)
const activeGroup = ref(null)
const activeDeviceType = ref('')

const deviceOptions = computed(() => {
  return (configData.value?.items || []).map((item) => ({
    label: item.label,
    value: item.device_type,
    countLabel: String(item.group_count ?? 0),
  }))
})

const summaryRate = computed(() => {
  const summary = runSummary.value?.summary
  if (!summary || !summary.total) {
    return '0.0%'
  }
  return `${((summary.success / summary.total) * 100).toFixed(1)}%`
})

const deviceResults = computed(() => runFinal.value?.device_results || [])

const filteredGroupResults = computed(() => {
  const selectedType = selectedDetailDevice.value
  const deviceItem = deviceResults.value.find((item) => item.device_type === selectedType)
  return deviceItem?.group_results || []
})

const currentDetailDevice = computed(() => {
  return deviceResults.value.find((item) => item.device_type === selectedDetailDevice.value) || null
})

const currentGroupTableMode = computed(() => selectedDetailDevice.value || '')

function formatMetric(value, digits = 2, suffix = '') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'N/A'
  }
  return `${Number(value).toFixed(digits)}${suffix}`
}

function toMetricEntries(metrics) {
  return Object.entries(metrics || {}).map(([key, value]) => ({
    key,
    value: Array.isArray(value) ? JSON.stringify(value) : typeof value === 'object' ? JSON.stringify(value) : String(value),
  }))
}

async function triggerReportDownload(runId) {
  const report = await fetchProtectedFileBlob(buildConsistencyReportUrl(runId))
  const blobUrl = URL.createObjectURL(report.blob)
  const link = document.createElement('a')
  link.href = blobUrl
  link.download = report.fileName || `${runId}.md`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(blobUrl)
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

async function loadConfig() {
  loadingConfig.value = true
  try {
    configData.value = await getConsistencyConfig()
    if (selectedDevices.value.length === 0) {
      selectedDevices.value = (configData.value?.items || [])
        .filter((item) => item.enabled)
        .map((item) => item.device_type)
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
    const data = await getConsistencyRuns(30)
    historyItems.value = data?.items || []
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loadingHistory.value = false
  }
}

async function startRun() {
  if (selectedDevices.value.length === 0) {
    ElMessage.warning('请至少选择一个设备类型')
    return
  }
  creatingRun.value = true
  try {
    const data = await createConsistencyRun(selectedDevices.value)
    activeRunId.value = data.run_id
    runFinal.value = null
    activeGroup.value = null
    activeDeviceType.value = ''
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

async function refreshRun() {
  if (!activeRunId.value) {
    return
  }
  try {
    const data = await getConsistencyRun(activeRunId.value)
    runSummary.value = {
      run_id: data.run_id,
      status: data.status,
      summary: data.summary,
      report_path: data.report_path || null,
    }
    if (data.status !== 'RUNNING') {
      stopPolling()
      runFinal.value = data
      if (!selectedDetailDevice.value && data.device_results?.length > 0) {
        selectedDetailDevice.value = data.device_results[0].device_type
      }
      await loadHistory()
    }
  } catch (error) {
    stopPolling()
    ElMessage.error(getApiErrorMessage(error))
  }
}

async function openHistoryRun(runId) {
  if (!runId) {
    return
  }
  activeRunId.value = runId
  runFinal.value = null
  activeGroup.value = null
  activeDeviceType.value = ''
  await refreshRun()
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

function selectDetailDevice(deviceType) {
  selectedDetailDevice.value = deviceType
}

function openGroupDetail(deviceType, groupItem) {
  activeDeviceType.value = deviceType
  activeGroup.value = groupItem || null
  detailVisible.value = true
}

function closeGroupDetail() {
  detailVisible.value = false
}

function buildGroupMetricSummary(group) {
  const metrics = group?.metrics || {}
  if (currentGroupTableMode.value === 'gpc') {
    return `重均分子量（Mw）CV=${formatMetric(metrics.mw_cv, 4)}%，数均分子量（Mn）CV=${formatMetric(metrics.mn_cv, 4)}%`
  }
  if (currentGroupTableMode.value === 'nmr') {
    return `溶剂峰化学位移 CV=${formatMetric(metrics.mean_pos_cv, 4)}%`
  }
  if (currentGroupTableMode.value === 'raman') {
    return `特征峰峰位偏移 CV=${formatMetric(metrics.mean_pos_cv, 4)}%，峰强度 CV=${formatMetric(metrics.mean_int_cv, 4)}%`
  }
  if (currentGroupTableMode.value === 'lcms') {
    const peaks = metrics.peaks || []
    return `TIC/EIC 峰目标数=${peaks.length}`
  }
  return '-'
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
            <div class="card-header">评测配置</div>
          </template>
          <el-skeleton :loading="loadingConfig" animated :rows="5">
            <template #default>
              <div class="config-path">配置文件：{{ configData?.config_path || '-' }}</div>
              <el-table :data="configData?.items || []" size="small" border>
                <el-table-column prop="label" label="设备类型" min-width="120" />
                <el-table-column prop="group_count" label="样品组数" width="90" />
                <el-table-column prop="summary_description" label="统计对象说明" min-width="160" />
                <el-table-column label="可执行状态" width="100">
                  <template #default="scope">
                    <el-tag size="small" :type="scope.row.enabled ? 'success' : 'info'">
                      {{ scope.row.enabled ? '可执行' : '已禁用' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="data_path" label="数据源目录" min-width="260" />
              </el-table>
              <div class="total-line">设备类型总数：{{ configData?.total_devices || 0 }}</div>
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
            <el-form-item label="设备类型">
              <el-select v-model="selectedDevices" multiple style="width: 100%">
                <el-option
                  v-for="item in deviceOptions"
                  :key="item.value"
                  :label="`${item.label}（${item.countLabel} 组）`"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="creatingRun" @click="startRun">启动设备重复性评测</el-button>
              <el-button :disabled="!activeRunId" @click="refreshRun">刷新状态</el-button>
            </el-form-item>
          </el-form>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="说明"
            description="该模块会按设备类型执行重复性评测，并生成设备级汇总、样品组明细和 Markdown 报告。"
          />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="card-header">
          <span>历史评测批次</span>
          <el-button link type="primary" :loading="loadingHistory" @click="loadHistory">刷新</el-button>
        </div>
      </template>
      <el-table :data="historyItems" size="small" border v-loading="loadingHistory" max-height="280">
        <el-table-column prop="run_id" label="批次ID" min-width="220" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column prop="started_at" label="开始时间" width="170" />
        <el-table-column prop="finished_at" label="结束时间" width="170" />
        <el-table-column label="设备类型" min-width="180">
          <template #default="scope">
            {{ (scope.row.selected_devices || []).join(', ') || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="设备数" width="90">
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
        <el-col :span="4"><el-statistic title="总设备" :value="runSummary.summary.total" /></el-col>
        <el-col :span="4"><el-statistic title="成功" :value="runSummary.summary.success" /></el-col>
        <el-col :span="4"><el-statistic title="失败" :value="runSummary.summary.failed" /></el-col>
        <el-col :span="4"><el-statistic title="成功率" :value="summaryRate" /></el-col>
        <el-col :span="4"><el-statistic title="进度" :value="`${runSummary.summary.progress}%`" /></el-col>
      </el-row>
      <el-progress :percentage="runSummary.summary.progress || 0" :stroke-width="14" />
      <div class="running-tip" v-if="runSummary.status === 'RUNNING'">
        运行中，完成后将一次性展示设备级汇总与样品组明细。
      </div>
    </el-card>

    <el-card v-if="runFinal && runFinal.status !== 'RUNNING'" shadow="never" class="block-card">
      <template #header>
        <div class="card-header">运行结果（{{ runFinal.run_id }}）</div>
      </template>
      <el-divider content-position="left">设备级汇总</el-divider>

      <div class="aggregate-grid">
        <el-card v-for="deviceItem in deviceResults" :key="deviceItem.device_type" shadow="never" class="aggregate-card">
          <template #header>
            <div class="card-header">
              <span>{{ deviceItem.device_label }}</span>
              <el-button link type="primary" @click="selectDetailDevice(deviceItem.device_type)">查看明细</el-button>
            </div>
          </template>
          <div>状态：{{ deviceItem.status }}</div>
          <div>样品组数：{{ deviceItem.summary_metrics?.group_count ?? 0 }}</div>
          <div v-if="deviceItem.device_type === 'gpc'">
            重均分子量（Mw）CV：{{ formatMetric(deviceItem.summary_metrics?.mw_cv_avg, 4, '%') }}
          </div>
          <div v-if="deviceItem.device_type === 'gpc'">
            数均分子量（Mn）CV：{{ formatMetric(deviceItem.summary_metrics?.mn_cv_avg, 4, '%') }}
          </div>
          <div v-if="deviceItem.device_type === 'nmr'">
            溶剂峰化学位移 CV：{{ formatMetric(deviceItem.summary_metrics?.mean_pos_cv_avg, 4, '%') }}
          </div>
          <div v-if="deviceItem.device_type === 'raman'">
            特征峰峰位偏移 CV：{{ formatMetric(deviceItem.summary_metrics?.mean_pos_cv_avg, 4, '%') }}
          </div>
          <div v-if="deviceItem.device_type === 'raman'">
            峰强度 CV：{{ formatMetric(deviceItem.summary_metrics?.mean_int_cv_avg, 4, '%') }}
          </div>
          <div v-if="deviceItem.device_type === 'lcms'">
            TIC 主峰保留时间 CV：{{ formatMetric(deviceItem.summary_metrics?.rt_cv_avg, 4, '%') }}
          </div>
          <div v-if="deviceItem.device_type === 'lcms'">
            TIC 主峰峰面积 CV：{{ formatMetric(deviceItem.summary_metrics?.area_cv_avg, 4, '%') }}
          </div>
          <div>失败组数：{{ deviceItem.summary_metrics?.failed_group_count ?? 0 }}</div>
        </el-card>
      </div>

      <div class="report-line">
        <el-button type="primary" plain @click="downloadReport">下载设备重复性报告</el-button>
      </div>

      <el-divider content-position="left">设备明细</el-divider>
      <div class="device-switcher">
        <el-radio-group v-model="selectedDetailDevice" size="small">
          <el-radio-button v-for="deviceItem in deviceResults" :key="deviceItem.device_type" :value="deviceItem.device_type">
            {{ deviceItem.device_label }}
          </el-radio-button>
        </el-radio-group>
      </div>

      <el-table :data="filteredGroupResults" size="small" border max-height="420">
        <el-table-column prop="group_name" label="样品组" min-width="180" />
        <el-table-column prop="replicate_count" label="重复数" width="90" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="指标摘要" min-width="220">
          <template #default="scope">
            {{ buildGroupMetricSummary(scope.row) }}
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="220" />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="openGroupDetail(selectedDetailDevice, scope.row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>

  <el-drawer
    v-model="detailVisible"
    title="样品组详情"
    size="45%"
    destroy-on-close
    @close="closeGroupDetail"
  >
    <template v-if="activeGroup">
      <el-descriptions :column="1" border class="detail-section">
        <el-descriptions-item label="设备类型">{{ activeDeviceType || '-' }}</el-descriptions-item>
        <el-descriptions-item label="样品组">{{ activeGroup.group_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ activeGroup.status || '-' }}</el-descriptions-item>
        <el-descriptions-item label="重复数">{{ activeGroup.replicate_count ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="备注">{{ activeGroup.remark || '-' }}</el-descriptions-item>
      </el-descriptions>

      <div class="detail-section">
        <div class="detail-title">关键指标</div>
        <el-empty v-if="toMetricEntries(activeGroup.metrics).length === 0" description="无可展示指标" :image-size="72" />
        <el-table v-else :data="toMetricEntries(activeGroup.metrics)" size="small" border>
          <el-table-column prop="key" label="指标" width="180" />
          <el-table-column prop="value" label="取值" />
        </el-table>
      </div>

      <div class="detail-section">
        <div class="detail-title">设备报告</div>
        <el-empty v-if="!currentDetailDevice?.text_report" description="无文本报告" :image-size="72" />
        <pre v-else class="report-preview">{{ currentDetailDevice.text_report }}</pre>
      </div>

      <div class="detail-section">
        <div class="detail-title">产物文件</div>
        <el-empty v-if="!(currentDetailDevice?.artifacts || []).length" description="无产物文件" :image-size="72" />
        <el-table v-else :data="currentDetailDevice.artifacts" size="small" border>
          <el-table-column prop="name" label="文件名" min-width="200" />
          <el-table-column prop="file_type" label="类型" width="100" />
          <el-table-column prop="relative_path" label="相对路径" min-width="220" />
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
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.aggregate-card {
  font-size: 13px;
  line-height: 1.8;
}

.report-line {
  margin-bottom: 12px;
}

.device-switcher {
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

@media (max-width: 1400px) {
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
