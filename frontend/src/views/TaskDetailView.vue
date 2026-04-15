<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import SpectrumPreviewChart from '../components/SpectrumPreviewChart.vue'
import {
  getApiBaseUrl,
  getApiErrorMessage,
  getTaskArtifacts,
  getTaskResult,
  getTaskStatus,
  isRequestCanceled,
  previewSpectrum,
} from '../api/specAgentApi'

const route = useRoute()
const router = useRouter()
const taskId = computed(() => route.params.taskId)

const loading = ref(false)
const statusData = ref(null)
const resultData = ref(null)
const artifactItems = ref([])
const previewLoading = ref(false)
const previewData = ref(null)
const activeRequestController = ref(null)
const pollingTimer = ref(null)
const pollingAttempt = ref(0)
const isUnmounted = ref(false)

const structuredData = computed(() => resultData.value?.result?.structured_data || {})
const resultMetadata = computed(() => resultData.value?.result?.metadata || {})
const isNmrTask = computed(() => statusData.value?.task_type === 'nmr_analysis')
const isGpcTask = computed(() => statusData.value?.task_type === 'gpc_analysis')
const isLcmsTask = computed(() => statusData.value?.task_type === 'lcms_analysis')
const isIrRamanTask = computed(() =>
  ['ir_analysis', 'raman_analysis'].includes(String(statusData.value?.task_type || '')),
)
const lcmsPredictedMass = computed(() => {
  const mass = structuredData.value?.predicted_mass
  if (mass === undefined || mass === null || mass === '') {
    return '-'
  }
  const numericMass = Number(mass)
  return Number.isFinite(numericMass) ? numericMass.toFixed(4) : String(mass)
})
const isRunningStatus = computed(() =>
  ['PENDING', 'QUEUED', 'RUNNING'].includes(String(statusData.value?.status || '')),
)
const imageArtifacts = computed(() => artifactItems.value.filter((item) => item.file_type === 'image'))
const apiBaseUrl = getApiBaseUrl()
const backendOrigin = new URL(apiBaseUrl).origin
const treeProps = {
  children: 'children',
  label: 'label',
}

const imageGroups = computed(() => {
  const groups = {
    raw: [],
    process: [],
    peak: [],
    result: [],
    other: [],
  }
  for (const item of imageArtifacts.value) {
    const name = String(item.name || '').toLowerCase()
    if (name.includes('raw') || name.includes('spectrum') || name.endsWith('.fid.png')) {
      groups.raw.push(item)
      continue
    }
    if (name.includes('processing') || name.includes('process') || name.includes('baseline') || name.includes('step')) {
      groups.process.push(item)
      continue
    }
    if (name.includes('peak') || name.includes('roi') || name.includes('integration_region') || name.includes('multiplet')) {
      groups.peak.push(item)
      continue
    }
    if (name.includes('result') || name.includes('detailed_gpc_plot') || name.includes('machine_curve') || name.includes('quant') || name.includes('fit')) {
      groups.result.push(item)
      continue
    }
    groups.other.push(item)
  }
  return groups
})

const gpcRows = computed(() => structuredData.value.analysis_results || [])
const nmrRows = computed(() => structuredData.value.nmr_results || [])

const irRamanMode = computed(() => String(structuredData.value.mode || ''))
const irRamanRawOutput = computed(() => structuredData.value.raw_output)
const irRamanFunctionGroups = computed(() => {
  if (irRamanMode.value !== 'function_groups') {
    return []
  }
  return Array.isArray(irRamanRawOutput.value) ? irRamanRawOutput.value : []
})
const irRamanStructures = computed(() => {
  if (irRamanMode.value === 'function_groups') {
    return []
  }
  if (irRamanMode.value === 'greedy_decode') {
    return Array.isArray(irRamanRawOutput.value) ? irRamanRawOutput.value : []
  }
  if (irRamanRawOutput.value && typeof irRamanRawOutput.value === 'object') {
    const structureList = irRamanRawOutput.value.structure
    return Array.isArray(structureList) ? structureList : []
  }
  return []
})
const irRamanScores = computed(() => {
  if (irRamanRawOutput.value && typeof irRamanRawOutput.value === 'object') {
    const scoreList = irRamanRawOutput.value.score
    return Array.isArray(scoreList) ? scoreList : []
  }
  return []
})
const previewAxisConfig = computed(() => {
  const spectype = String(previewData.value?.spectype || '').toLowerCase()
  if (spectype === 'nmr') {
    return {
      xAxisName: '化学位移 (ppm)',
      yAxisName: '信号强度',
      inverseXAxis: true,
    }
  }
  if (spectype === 'gpc') {
    return {
      xAxisName: '时间 (min)',
      yAxisName: '信号强度 (μRIU)',
      inverseXAxis: false,
    }
  }
  if (spectype === 'lcms') {
    return {
      xAxisName: 'm/z',
      yAxisName: '信号强度',
      inverseXAxis: false,
    }
  }
  return {
    xAxisName: '波数 (cm⁻¹)',
    yAxisName: '强度',
    inverseXAxis: false,
  }
})
const jsonPanelData = computed(() => ({
  structured_data: structuredData.value || {},
  metadata: resultMetadata.value || {},
}))
const structuredTreeData = computed(() => buildJsonTreeData(jsonPanelData.value))

/**
 * 构建可访问的图片 URL。
 *
 * Args:
 *   relativeUrl: 后端返回的静态资源 URL。
 *
 * Returns:
 *   浏览器可访问的完整地址。
 */
function buildImageUrl(relativeUrl) {
  if (!relativeUrl) {
    return ''
  }
  if (relativeUrl.startsWith('http')) {
    return relativeUrl
  }
  return `${backendOrigin}${relativeUrl}`
}

/**
 * 组装分组内图片预览列表。
 *
 * Args:
 *   list: 当前分组图片列表。
 *
 * Returns:
 *   可用于预览的图片 URL 列表。
 */
function buildPreviewUrls(list) {
  return list.map((item) => buildImageUrl(item.url))
}

/**
 * 构建后端分子结构图片 URL。
 *
 * Args:
 *   smiles: 分子 SMILES 字符串。
 *
 * Returns:
 *   图片可访问 URL。
 */
function buildMoleculeImageUrl(smiles) {
  if (!smiles) {
    return ''
  }
  return `${apiBaseUrl}/chemistry/molecule-image?smiles=${encodeURIComponent(smiles)}&size=300`
}

/**
 * 构建后端官能团结构图片 URL。
 *
 * Args:
 *   smarts: 官能团 SMARTS 字符串。
 *
 * Returns:
 *   图片可访问 URL。
 */
function buildFunctionGroupImageUrl(smarts) {
  if (!smarts) {
    return ''
  }
  return `${apiBaseUrl}/chemistry/function-group-image?smarts=${encodeURIComponent(smarts)}&size=260`
}

/**
 * 解析对象为表格展示数组。
 *
 * Args:
 *   source: 任意对象。
 *
 * Returns:
 *   键值对数组。
 */
function toKeyValueRows(source) {
  if (!source || typeof source !== 'object') {
    return []
  }
  return Object.entries(source).map(([key, value]) => ({
    key,
    value: typeof value === 'object' ? JSON.stringify(value) : String(value),
  }))
}

/**
 * 生成 JSON 树节点 ID。
 *
 * Args:
 *   parentPath: 父节点路径。
 *   key: 当前键名。
 *
 * Returns:
 *   树节点唯一 ID。
 */
function buildNodeId(parentPath, key) {
  return parentPath ? `${parentPath}.${String(key)}` : String(key)
}

/**
 * 构建可折叠 JSON 树数据。
 *
 * Args:
 *   source: 任意 JSON 值。
 *
 * Returns:
 *   Element Plus Tree 数据源。
 */
function buildJsonTreeData(source) {
  if (Array.isArray(source)) {
    return source.map((item, index) => buildJsonTreeNode(`[${index}]`, item, `$[${index}]`))
  }
  if (source && typeof source === 'object') {
    return Object.entries(source).map(([key, value]) => buildJsonTreeNode(key, value, `$.${key}`))
  }
  return [buildJsonTreeNode('value', source, '$')]
}

/**
 * 构建单个 JSON 树节点。
 *
 * Args:
 *   key: 键名。
 *   value: 键值。
 *   path: 节点路径。
 *
 * Returns:
 *   树节点对象。
 */
function buildJsonTreeNode(key, value, path) {
  if (Array.isArray(value)) {
    return {
      id: buildNodeId(path, key),
      label: String(key),
      valueText: `Array(${value.length})`,
      children: value.map((item, index) => buildJsonTreeNode(`[${index}]`, item, `${path}[${index}]`)),
    }
  }
  if (value && typeof value === 'object') {
    const entries = Object.entries(value)
    return {
      id: buildNodeId(path, key),
      label: String(key),
      valueText: `Object(${entries.length})`,
      children: entries.map(([childKey, childValue]) => buildJsonTreeNode(childKey, childValue, `${path}.${childKey}`)),
    }
  }
  return {
    id: buildNodeId(path, key),
    label: String(key),
    valueText: value === null ? 'null' : String(value),
    children: [],
  }
}

/**
 * 返回任务中心页面。
 */
function goTaskCenter() {
  router.push('/tasks/center')
}

/**
 * 判断当前任务是否成功结束。
 *
 * Returns:
 *   boolean
 */
function isSuccess() {
  return resultData.value?.status === 'SUCCESS'
}

/**
 * 清理请求控制器。
 */
function clearActiveController() {
  activeRequestController.value = null
}

/**
 * 清理轮询定时器。
 */
function clearPollingTimer() {
  if (!pollingTimer.value) {
    return
  }
  clearTimeout(pollingTimer.value)
  pollingTimer.value = null
}

/**
 * 取消当前进行中的请求。
 */
function cancelActiveRequest() {
  if (!activeRequestController.value) {
    return
  }
  activeRequestController.value.abort()
  clearActiveController()
}

/**
 * 计算轮询间隔时长（毫秒）。
 *
 * Args:
 *   attempt: 轮询尝试次数。
 *
 * Returns:
 *   退避后的轮询间隔。
 */
function getPollingIntervalMs(attempt) {
  const intervals = [2000, 3000, 5000, 8000, 12000]
  return intervals[Math.min(Math.max(attempt, 0), intervals.length - 1)]
}

/**
 * 计划下一次轮询。
 */
function scheduleNextPolling() {
  clearPollingTimer()
  if (isUnmounted.value || !isRunningStatus.value) {
    return
  }
  const waitMs = getPollingIntervalMs(pollingAttempt.value)
  pollingTimer.value = setTimeout(() => {
    fetchDetail({ silent: true, source: 'polling' })
  }, waitMs)
}

/**
 * 自动加载任务输入谱图预览。
 *
 * Returns:
 *   Promise<void>
 */
async function fetchSourcePreview(signal) {
  previewData.value = null
  if (!isSuccess()) {
    return
  }
  const metadata = resultData.value?.result?.metadata || {}
  const inputPath = metadata.input_path
  const spectrumType = String(metadata.spectrum_type || '').toLowerCase()
  if (!inputPath || !['ir', 'raman', 'gpc', 'nmr', 'lcms'].includes(spectrumType)) {
    return
  }

  const formData = new FormData()
  formData.append('spectype', spectrumType)
  formData.append('input_path', inputPath)
  formData.append('max_points', '4096')

  previewLoading.value = true
  try {
    previewData.value = await previewSpectrum(formData, { signal })
  } catch (error) {
    if (isRequestCanceled(error)) {
      return
    }
    previewData.value = null
  } finally {
    previewLoading.value = false
  }
}

/**
 * 加载任务详情数据。
 *
 * Returns:
 *   Promise<void>
 */
async function fetchDetail(options = {}) {
  const silentMode = Boolean(options.silent)
  if (!silentMode) {
    loading.value = true
  }
  clearPollingTimer()
  cancelActiveRequest()
  const controller = new AbortController()
  activeRequestController.value = controller

  try {
    const status = await getTaskStatus(taskId.value, { signal: controller.signal })
    statusData.value = status
    const shouldLoadFullData = ['SUCCESS', 'FAILED'].includes(String(status?.status || ''))
    if (shouldLoadFullData) {
      const result = await getTaskResult(taskId.value, { signal: controller.signal })
      resultData.value = result
      const artifacts = await getTaskArtifacts(taskId.value, { signal: controller.signal })
      artifactItems.value = artifacts.items || []
      await fetchSourcePreview(controller.signal)
    } else {
      resultData.value = null
      artifactItems.value = []
      previewData.value = null
    }

    if (isRunningStatus.value) {
      pollingAttempt.value += 1
      scheduleNextPolling()
    } else {
      pollingAttempt.value = 0
    }
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getApiErrorMessage(error))
    }
  } finally {
    if (activeRequestController.value === controller) {
      clearActiveController()
    }
    if (!silentMode) {
      loading.value = false
    }
  }
}

/**
 * 手动刷新任务详情。
 *
 * Returns:
 *   Promise<void>
 */
async function refreshDetail() {
  pollingAttempt.value = 0
  await fetchDetail({ silent: false, source: 'manual' })
}

onMounted(() => {
  pollingAttempt.value = 0
  fetchDetail({ silent: false, source: 'init' })
})

onBeforeUnmount(() => {
  isUnmounted.value = true
  clearPollingTimer()
  cancelActiveRequest()
})
</script>

<template>
  <div class="page-grid">
    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">任务详情</h3>
        <div class="header-actions">
          <el-button plain @click="goTaskCenter">
            <el-icon><ArrowLeft /></el-icon>
            返回任务中心
          </el-button>
          <el-button type="primary" plain @click="refreshDetail">刷新</el-button>
        </div>
      </div>
      <div class="panel-body" v-loading="loading">
        <el-descriptions v-if="statusData" :column="2" border>
          <el-descriptions-item label="任务ID">{{ statusData.task_id }}</el-descriptions-item>
          <el-descriptions-item label="任务类型">{{ statusData.task_type }}</el-descriptions-item>
          <el-descriptions-item label="任务状态">{{ statusData.status }}</el-descriptions-item>
          <el-descriptions-item label="当前消息">{{ statusData.message }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ statusData.created_at }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ statusData.updated_at }}</el-descriptions-item>
        </el-descriptions>

        <div style="margin-top: 14px">
          <el-progress v-if="statusData" :percentage="statusData.progress" :stroke-width="10" />
        </div>

        <el-divider />

        <el-alert
          v-if="resultData?.status === 'FAILED'"
          type="error"
          :closable="false"
          :title="resultData?.error?.error_message || '任务失败'"
          :description="resultData?.error?.error_detail"
        />

        <template v-if="isSuccess()">
          <el-divider />
          <h4 style="margin: 8px 0">原始谱图预览</h4>
          <div v-loading="previewLoading">
            <SpectrumPreviewChart
              v-if="previewData?.x_values?.length"
              :x-values="previewData.x_values"
              :y-values="previewData.y_values"
              :x-axis-name="previewAxisConfig.xAxisName"
              :y-axis-name="previewAxisConfig.yAxisName"
              :inverse-x-axis="previewAxisConfig.inverseXAxis"
              :title="`${previewData.spectype?.toUpperCase() || ''} 原始谱图`"
            />
            <el-empty v-else description="暂无原始谱图预览数据" />
          </div>
        </template>

        <template v-if="isSuccess() && isGpcTask">
          <h4 style="margin: 8px 0">GPC 结果概览</h4>
          <el-table :data="gpcRows" stripe>
            <el-table-column prop="simple_name" label="样品简称" min-width="120" />
            <el-table-column prop="actual_curve_name" label="曲线名称" min-width="220" />
            <el-table-column label="分子量参数" min-width="280">
              <template #default="scope">
                <el-descriptions :column="1" size="small" border>
                  <el-descriptions-item
                    v-for="row in toKeyValueRows(scope.row.molecular_parameters)"
                    :key="row.key"
                    :label="row.key"
                  >
                    {{ row.value }}
                  </el-descriptions-item>
                </el-descriptions>
              </template>
            </el-table-column>
          </el-table>
        </template>

        <template v-if="isSuccess() && isNmrTask">
          <h4 style="margin: 8px 0">NMR 结果概览</h4>
          <el-table :data="nmrRows" stripe>
            <el-table-column prop="sample_name" label="样品名称" min-width="180" />
            <el-table-column label="积分结果" min-width="280">
              <template #default="scope">
                <el-descriptions :column="1" size="small" border>
                  <el-descriptions-item
                    v-for="row in toKeyValueRows(scope.row.integration_results)"
                    :key="row.key"
                    :label="row.key"
                  >
                    {{ row.value }}
                  </el-descriptions-item>
                </el-descriptions>
              </template>
            </el-table-column>
            <el-table-column label="归一化结果" min-width="280">
              <template #default="scope">
                <el-descriptions :column="1" size="small" border>
                  <el-descriptions-item
                    v-for="row in toKeyValueRows(scope.row.normalized_results)"
                    :key="row.key"
                    :label="row.key"
                  >
                    {{ row.value }}
                  </el-descriptions-item>
                </el-descriptions>
              </template>
            </el-table-column>
          </el-table>
        </template>

        <template v-if="isSuccess() && isLcmsTask">
          <h4 style="margin: 8px 0">LCMS 结果概览</h4>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="预测分子量">{{ lcmsPredictedMass }}</el-descriptions-item>
            <el-descriptions-item label="任务类型">LCMS</el-descriptions-item>
          </el-descriptions>
        </template>

        <template v-if="isSuccess() && isIrRamanTask">
          <el-divider />
          <h4 style="margin: 8px 0">结果预览</h4>
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="光谱类型">{{ structuredData.spectype || '-' }}</el-descriptions-item>
            <el-descriptions-item label="分析模式">{{ irRamanMode || '-' }}</el-descriptions-item>
            <el-descriptions-item label="分析范围">{{ structuredData.x0 }} - {{ structuredData.x1 }}</el-descriptions-item>
          </el-descriptions>

          <template v-if="irRamanMode === 'function_groups'">
            <el-table :data="irRamanFunctionGroups.map((item, idx) => ({ index: idx + 1, smarts: item }))" stripe style="margin-top: 12px">
              <el-table-column prop="index" label="序号" width="80" />
              <el-table-column prop="smarts" label="官能团 SMARTS" min-width="240" />
              <el-table-column label="结构图" min-width="220">
                <template #default="scope">
                  <el-image
                    :src="buildFunctionGroupImageUrl(scope.row.smarts)"
                    fit="contain"
                    style="width: 200px; height: 120px; background: #f6f9ff"
                    :preview-src-list="[buildFunctionGroupImageUrl(scope.row.smarts)]"
                  />
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="irRamanFunctionGroups.length === 0" description="未识别到官能团" />
          </template>

          <template v-else>
            <div class="ir-raman-card-grid">
              <el-card
                v-for="(smiles, index) in irRamanStructures"
                :key="`${smiles}_${index}`"
                class="ir-raman-card"
                shadow="hover"
              >
                <template #header>
                  <div class="ir-raman-card-header">
                    <span>候选 {{ index + 1 }}</span>
                    <span v-if="irRamanScores[index] !== undefined">评分：{{ Number(irRamanScores[index]).toFixed(4) }}</span>
                  </div>
                </template>
                <el-image
                  :src="buildMoleculeImageUrl(smiles)"
                  fit="contain"
                  style="width: 100%; height: 180px; background: #f6f9ff"
                  :preview-src-list="[buildMoleculeImageUrl(smiles)]"
                />
                <div class="smiles-line">{{ smiles }}</div>
              </el-card>
            </div>
            <el-empty v-if="irRamanStructures.length === 0" description="未识别到候选分子结构" />
          </template>
        </template>

        <template v-if="imageArtifacts.length > 0">
          <el-divider />
          <h4 style="margin: 8px 0">分析图像产物</h4>
          <el-tabs type="border-card">
            <el-tab-pane label="原始谱图">
              <el-row :gutter="12">
                <el-col
                  v-for="item in imageGroups.raw"
                  :key="item.relative_path"
                  :xs="24"
                  :sm="12"
                  :lg="8"
                  style="margin-bottom: 12px"
                >
                  <el-card shadow="hover">
                    <template #header>
                      <div style="font-size: 13px; color: #3d5377; word-break: break-all">{{ item.name }}</div>
                    </template>
                    <el-image
                      :src="buildImageUrl(item.url)"
                      fit="contain"
                      style="width: 100%; height: 220px; background: #f6f9ff"
                      :preview-src-list="buildPreviewUrls(imageGroups.raw)"
                      :initial-index="imageGroups.raw.findIndex((x) => x.relative_path === item.relative_path)"
                    />
                  </el-card>
                </el-col>
              </el-row>
              <el-empty v-if="imageGroups.raw.length === 0" description="暂无原始谱图" />
            </el-tab-pane>
            <el-tab-pane label="处理步骤">
              <el-row :gutter="12">
                <el-col
                  v-for="item in imageGroups.process"
                  :key="item.relative_path"
                  :xs="24"
                  :sm="12"
                  :lg="8"
                  style="margin-bottom: 12px"
                >
                  <el-card shadow="hover">
                    <template #header>
                      <div style="font-size: 13px; color: #3d5377; word-break: break-all">{{ item.name }}</div>
                    </template>
                    <el-image
                      :src="buildImageUrl(item.url)"
                      fit="contain"
                      style="width: 100%; height: 220px; background: #f6f9ff"
                      :preview-src-list="buildPreviewUrls(imageGroups.process)"
                      :initial-index="imageGroups.process.findIndex((x) => x.relative_path === item.relative_path)"
                    />
                  </el-card>
                </el-col>
              </el-row>
              <el-empty v-if="imageGroups.process.length === 0" description="暂无处理步骤图" />
            </el-tab-pane>
            <el-tab-pane label="峰检测">
              <el-row :gutter="12">
                <el-col
                  v-for="item in imageGroups.peak"
                  :key="item.relative_path"
                  :xs="24"
                  :sm="12"
                  :lg="8"
                  style="margin-bottom: 12px"
                >
                  <el-card shadow="hover">
                    <template #header>
                      <div style="font-size: 13px; color: #3d5377; word-break: break-all">{{ item.name }}</div>
                    </template>
                    <el-image
                      :src="buildImageUrl(item.url)"
                      fit="contain"
                      style="width: 100%; height: 220px; background: #f6f9ff"
                      :preview-src-list="buildPreviewUrls(imageGroups.peak)"
                      :initial-index="imageGroups.peak.findIndex((x) => x.relative_path === item.relative_path)"
                    />
                  </el-card>
                </el-col>
              </el-row>
              <el-empty v-if="imageGroups.peak.length === 0" description="暂无峰检测图" />
            </el-tab-pane>
            <el-tab-pane label="结果图">
              <el-row :gutter="12">
                <el-col
                  v-for="item in imageGroups.result"
                  :key="item.relative_path"
                  :xs="24"
                  :sm="12"
                  :lg="8"
                  style="margin-bottom: 12px"
                >
                  <el-card shadow="hover">
                    <template #header>
                      <div style="font-size: 13px; color: #3d5377; word-break: break-all">{{ item.name }}</div>
                    </template>
                    <el-image
                      :src="buildImageUrl(item.url)"
                      fit="contain"
                      style="width: 100%; height: 220px; background: #f6f9ff"
                      :preview-src-list="buildPreviewUrls(imageGroups.result)"
                      :initial-index="imageGroups.result.findIndex((x) => x.relative_path === item.relative_path)"
                    />
                  </el-card>
                </el-col>
              </el-row>
              <el-empty v-if="imageGroups.result.length === 0" description="暂无结果图" />
            </el-tab-pane>
            <el-tab-pane label="全部图像">
              <el-row :gutter="12">
                <el-col
                  v-for="item in imageArtifacts"
                  :key="item.relative_path"
                  :xs="24"
                  :sm="12"
                  :lg="8"
                  style="margin-bottom: 12px"
                >
                  <el-card shadow="hover">
                    <template #header>
                      <div style="font-size: 13px; color: #3d5377; word-break: break-all">{{ item.name }}</div>
                    </template>
                    <el-image
                      :src="buildImageUrl(item.url)"
                      fit="contain"
                      style="width: 100%; height: 220px; background: #f6f9ff"
                      :preview-src-list="buildPreviewUrls(imageArtifacts)"
                      :initial-index="imageArtifacts.findIndex((x) => x.relative_path === item.relative_path)"
                    />
                  </el-card>
                </el-col>
              </el-row>
            </el-tab-pane>
          </el-tabs>
        </template>

        <template v-if="isSuccess()">
          <el-divider />
          <h4 style="margin: 8px 0">文本报告</h4>
          <el-input :model-value="resultData?.result?.text_report || ''" type="textarea" :rows="12" readonly />
        </template>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <h3 class="panel-title">结构化结果（JSON）</h3>
      </div>
      <div class="panel-body">
        <el-tree
          class="json-tree"
          :data="structuredTreeData"
          :props="treeProps"
          node-key="id"
          :expand-on-click-node="false"
        >
          <template #default="{ data }">
            <div class="json-tree-node">
              <span class="node-key">{{ data.label }}</span>
              <span class="node-separator">:</span>
              <span class="node-value">{{ data.valueText }}</span>
            </div>
          </template>
        </el-tree>
      </div>
    </div>
  </div>
</template>

<style scoped>
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ir-raman-card-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.ir-raman-card {
  border-radius: 10px;
}

.ir-raman-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #2a466f;
  font-size: 13px;
}

.smiles-line {
  margin-top: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  background: #eef4ff;
  color: #35527f;
  word-break: break-all;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
}

.json-tree {
  background: #081f3e;
  border-radius: 10px;
  padding: 8px 10px;
  color: #d8e7ff;
  max-height: 640px;
  overflow: auto;
}

.json-tree-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.node-key {
  color: #8ec5ff;
}

.node-separator {
  color: #8fa7c8;
}

.node-value {
  color: #d7f0b2;
  word-break: break-all;
}

@media (max-width: 1200px) {
  .ir-raman-card-grid {
    grid-template-columns: 1fr;
  }
}
</style>
