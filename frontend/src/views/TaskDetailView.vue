<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import SpectrumPreviewChart from '../components/SpectrumPreviewChart.vue'
import {
  fetchProtectedImageBlob,
  getApiBaseUrl,
  getStaticBaseUrl,
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
const protectedImageUrlMap = ref({})

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
const staticBaseUrl = getStaticBaseUrl()
const treeProps = {
  children: 'children',
  label: 'label',
}

/**
 * 构建绝对 API 地址，避免 Axios 在相对 baseURL 场景下重复拼接路径。
 *
 * Args:
 *   path: API 相对路径，需以 `/` 开头。
 *
 * Returns:
 *   浏览器可直接访问的绝对接口地址。
 */
function buildAbsoluteApiUrl(path) {
  const normalizedBase = String(apiBaseUrl || '').replace(/\/+$/, '')
  return new URL(`${normalizedBase}${path}`, window.location.origin).toString()
}

const gpcRows = computed(() => structuredData.value.analysis_results || [])
const nmrRows = computed(() => structuredData.value.nmr_results || [])
const nmrPeakRows = computed(() => {
  const rows = []
  for (const sample of nmrRows.value) {
    const peakDetails = Array.isArray(sample?.peak_details) ? sample.peak_details : []
    for (const detail of peakDetails) {
      rows.push({
        sample_name: sample?.sample_name || '-',
        peak_index: detail?.peak_index ?? '-',
        peak_name: detail?.peak_name || '-',
        peak_type: detail?.peak_type || '-',
        multiplet_type: detail?.multiplet_type || '-',
        j_values_hz: formatJValues(detail?.j_values_hz),
        peak_position_ppm: formatNumericValue(detail?.peak_position_ppm, 4),
        ppm_range: formatPpmRange(detail?.ppm_range),
        integration_result: formatNumericValue(detail?.integration_result, 4),
        normalized_result: formatNumericValue(detail?.normalized_result, 4),
      })
    }
  }
  return rows
})

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
const irRamanDisplayRange = computed(() => {
  const x0Raw = resultMetadata.value?.analysis_x0
  const x1Raw = resultMetadata.value?.analysis_x1
  const x0 = Number(x0Raw)
  const x1 = Number(x1Raw)
  if (!Number.isFinite(x0) || !Number.isFinite(x1)) {
    return null
  }
  const minValue = Math.min(x0, x1)
  const maxValue = Math.max(x0, x1)
  return { min: minValue, max: maxValue }
})
const filteredPreviewData = computed(() => {
  const raw = previewData.value
  if (!raw || !Array.isArray(raw.x_values) || !Array.isArray(raw.y_values)) {
    return null
  }
  if (!isIrRamanTask.value || !irRamanDisplayRange.value) {
    return raw
  }
  const { min, max } = irRamanDisplayRange.value
  const filteredX = []
  const filteredY = []
  const length = Math.min(raw.x_values.length, raw.y_values.length)
  for (let index = 0; index < length; index += 1) {
    const xValue = Number(raw.x_values[index])
    const yValue = Number(raw.y_values[index])
    if (!Number.isFinite(xValue) || !Number.isFinite(yValue)) {
      continue
    }
    if (xValue >= min && xValue <= max) {
      filteredX.push(xValue)
      filteredY.push(yValue)
    }
  }
  if (filteredX.length === 0) {
    return raw
  }
  return {
    ...raw,
    x_values: filteredX,
    y_values: filteredY,
    x_min: min,
    x_max: max,
    point_count: filteredX.length,
    display_count: filteredX.length,
  }
})
const irRamanRangeText = computed(() => {
  const range = irRamanDisplayRange.value
  if (!range) {
    return `${structuredData.value.x0 ?? '-'} - ${structuredData.value.x1 ?? '-'}`
  }
  return `${range.min} - ${range.max}`
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
  return `${staticBaseUrl}${relativeUrl}`
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
  return buildAbsoluteApiUrl(`/chemistry/molecule-image?smiles=${encodeURIComponent(smiles)}&size=300`)
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
  return buildAbsoluteApiUrl(`/chemistry/function-group-image?smarts=${encodeURIComponent(smarts)}&size=260`)
}

/**
 * 生成结构图缓存键。
 *
 * Args:
 *   kind: 图片类型。
 *   source: 原始结构标识。
 *
 * Returns:
 *   缓存键字符串。
 */
function buildProtectedImageKey(kind, source) {
  return `${kind}:${String(source || '')}`
}

/**
 * 释放已创建的结构图对象 URL。
 */
function revokeProtectedImageUrls() {
  Object.values(protectedImageUrlMap.value).forEach((item) => {
    if (item?.objectUrl) {
      URL.revokeObjectURL(item.objectUrl)
    }
  })
  protectedImageUrlMap.value = {}
}

/**
 * 读取结构图加载状态。
 *
 * Args:
 *   kind: 图片类型。
 *   source: 原始结构标识。
 *
 * Returns:
 *   结构图状态对象。
 */
function getProtectedImageState(kind, source) {
  return protectedImageUrlMap.value[buildProtectedImageKey(kind, source)] || null
}

/**
 * 获取结构图展示地址。
 *
 * Args:
 *   kind: 图片类型。
 *   source: 原始结构标识。
 *
 * Returns:
 *   可展示的对象 URL。
 */
function getProtectedImageSrc(kind, source) {
  return getProtectedImageState(kind, source)?.objectUrl || ''
}

/**
 * 获取结构图预览列表。
 *
 * Args:
 *   kind: 图片类型。
 *   source: 原始结构标识。
 *
 * Returns:
 *   Element Plus 预览地址数组。
 */
function getProtectedImagePreviewList(kind, source) {
  const objectUrl = getProtectedImageSrc(kind, source)
  return objectUrl ? [objectUrl] : []
}

/**
 * 判断结构图是否加载失败。
 *
 * Args:
 *   kind: 图片类型。
 *   source: 原始结构标识。
 *
 * Returns:
 *   是否加载失败。
 */
function isProtectedImageFailed(kind, source) {
  return Boolean(getProtectedImageState(kind, source)?.failed)
}

/**
 * 预加载受保护的结构图图片。
 *
 * Args:
 *   items: 待加载的图片任务列表。
 *
 * Returns:
 *   Promise<void>
 */
async function preloadProtectedImages(items) {
  revokeProtectedImageUrls()
  if (!Array.isArray(items) || items.length === 0) {
    return
  }

  const nextMap = {}
  await Promise.all(items.map(async (item) => {
    const key = buildProtectedImageKey(item.kind, item.source)
    nextMap[key] = {
      objectUrl: '',
      failed: false,
    }
    try {
      const imageBlob = await fetchProtectedImageBlob(item.url)
      const objectUrl = URL.createObjectURL(imageBlob)
      nextMap[key] = {
        objectUrl,
        failed: false,
      }
    } catch {
      nextMap[key] = {
        objectUrl: '',
        failed: true,
      }
    }
  }))
  protectedImageUrlMap.value = nextMap
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
 * 格式化数值显示。
 *
 * Args:
 *   value: 任意待展示值。
 *   digits: 小数位数。
 *
 * Returns:
 *   格式化后的字符串。
 */
function formatNumericValue(value, digits = 4) {
  if (value === undefined || value === null || value === '') {
    return '-'
  }
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue.toFixed(digits) : String(value)
}

/**
 * 格式化 J 值列表。
 *
 * Args:
 *   values: J 值数组。
 *
 * Returns:
 *   逗号分隔字符串。
 */
function formatJValues(values) {
  if (!Array.isArray(values) || values.length === 0) {
    return '-'
  }
  return values.map((item) => formatNumericValue(item, 4)).join(', ')
}

/**
 * 格式化 ppm 范围显示。
 *
 * Args:
 *   values: ppm 范围数组。
 *
 * Returns:
 *   范围字符串。
 */
function formatPpmRange(values) {
  if (!Array.isArray(values) || values.length < 2) {
    return '-'
  }
  return `${formatNumericValue(values[0], 4)} - ${formatNumericValue(values[1], 4)}`
}

/**
 * 计算 NMR 样品名单元格合并。
 *
 * Args:
 *   param: Element Plus span-method 参数。
 *
 * Returns:
 *   合并行列配置。
 */
function nmrPeakSpanMethod({ row, column, rowIndex }) {
  if (column.property !== 'sample_name') {
    return { rowspan: 1, colspan: 1 }
  }
  if (rowIndex > 0 && nmrPeakRows.value[rowIndex - 1]?.sample_name === row.sample_name) {
    return { rowspan: 0, colspan: 0 }
  }
  let rowspan = 1
  for (let index = rowIndex + 1; index < nmrPeakRows.value.length; index += 1) {
    if (nmrPeakRows.value[index]?.sample_name !== row.sample_name) {
      break
    }
    rowspan += 1
  }
  return { rowspan, colspan: 1 }
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
      if (result?.status === 'SUCCESS' && ['ir_analysis', 'raman_analysis'].includes(String(status?.task_type || ''))) {
        const imageTasks = []
        if (String(result?.result?.structured_data?.mode || '') === 'function_groups') {
          const groups = Array.isArray(result?.result?.structured_data?.raw_output)
            ? result.result.structured_data.raw_output
            : []
          groups.forEach((smarts) => {
            imageTasks.push({
              kind: 'function_group',
              source: smarts,
              url: buildFunctionGroupImageUrl(smarts),
            })
          })
        } else {
          const rawOutput = result?.result?.structured_data?.raw_output
          let structures = []
          if (Array.isArray(rawOutput)) {
            structures = rawOutput
          } else if (rawOutput && typeof rawOutput === 'object' && Array.isArray(rawOutput.structure)) {
            structures = rawOutput.structure
          }
          structures.forEach((smiles) => {
            imageTasks.push({
              kind: 'molecule',
              source: smiles,
              url: buildMoleculeImageUrl(smiles),
            })
          })
        }
        await preloadProtectedImages(imageTasks)
      } else {
        revokeProtectedImageUrls()
      }
      await fetchSourcePreview(controller.signal)
    } else {
      resultData.value = null
      artifactItems.value = []
      previewData.value = null
      revokeProtectedImageUrls()
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
  revokeProtectedImageUrls()
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
              v-if="filteredPreviewData?.x_values?.length"
              :x-values="filteredPreviewData.x_values"
              :y-values="filteredPreviewData.y_values"
              :x-axis-name="previewAxisConfig.xAxisName"
              :y-axis-name="previewAxisConfig.yAxisName"
              :inverse-x-axis="previewAxisConfig.inverseXAxis"
              :title="`${filteredPreviewData.spectype?.toUpperCase() || ''} 原始谱图`"
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
          <el-table :data="nmrPeakRows" stripe :span-method="nmrPeakSpanMethod">
            <el-table-column prop="sample_name" label="样品名称" min-width="140" />
            <el-table-column prop="peak_index" label="峰序号" width="90" />
            <el-table-column prop="peak_name" label="峰名称" min-width="220" />
            <el-table-column prop="peak_type" label="峰类型" width="110" />
            <el-table-column prop="multiplet_type" label="多重峰类型" width="110" />
            <el-table-column prop="j_values_hz" label="J值(Hz)" min-width="140" />
            <el-table-column prop="peak_position_ppm" label="峰ppm位置" width="120" />
            <el-table-column prop="ppm_range" label="峰ppm范围" min-width="170" />
            <el-table-column prop="integration_result" label="积分结果" min-width="140" />
            <el-table-column prop="normalized_result" label="归一化结果" min-width="140" />
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
            <el-descriptions-item label="分析范围">{{ irRamanRangeText }}</el-descriptions-item>
          </el-descriptions>

          <template v-if="irRamanMode === 'function_groups'">
            <el-table :data="irRamanFunctionGroups.map((item, idx) => ({ index: idx + 1, smarts: item }))" stripe style="margin-top: 12px">
              <el-table-column prop="index" label="序号" width="80" />
              <el-table-column prop="smarts" label="官能团 SMARTS" min-width="240" />
              <el-table-column label="结构图" min-width="220">
                <template #default="scope">
                  <div class="protected-image-box">
                    <el-image
                      v-if="getProtectedImageSrc('function_group', scope.row.smarts)"
                      :src="getProtectedImageSrc('function_group', scope.row.smarts)"
                      fit="contain"
                      style="width: 200px; height: 120px; background: #f6f9ff"
                      :preview-src-list="getProtectedImagePreviewList('function_group', scope.row.smarts)"
                    />
                    <el-empty
                      v-else-if="isProtectedImageFailed('function_group', scope.row.smarts)"
                      description="结构图加载失败"
                      :image-size="56"
                    />
                    <div v-else class="protected-image-loading">加载中...</div>
                  </div>
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
                  v-if="getProtectedImageSrc('molecule', smiles)"
                  :src="getProtectedImageSrc('molecule', smiles)"
                  fit="contain"
                  style="width: 100%; height: 180px; background: #f6f9ff"
                  :preview-src-list="getProtectedImagePreviewList('molecule', smiles)"
                />
                <el-empty
                  v-else-if="isProtectedImageFailed('molecule', smiles)"
                  description="结构图加载失败"
                  :image-size="72"
                />
                <div v-else class="protected-image-loading protected-image-loading-large">加载中...</div>
                <div class="smiles-line">{{ smiles }}</div>
              </el-card>
            </div>
            <el-empty v-if="irRamanStructures.length === 0" description="未识别到候选分子结构" />
          </template>
        </template>

        <template v-if="imageArtifacts.length > 0">
          <el-divider />
          <h4 style="margin: 8px 0">分析图像产物（{{ imageArtifacts.length }} 张）</h4>
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

.protected-image-box {
  width: 200px;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
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

.protected-image-loading {
  width: 200px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #7890b2;
  background: #f6f9ff;
  border-radius: 8px;
  font-size: 13px;
}

.protected-image-loading-large {
  width: 100%;
  height: 180px;
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
