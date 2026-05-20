<script setup>
import { computed, ref } from 'vue'
import JSZip from 'jszip'
import { ElMessage } from 'element-plus'
import SpectrumPreviewChart from '../components/SpectrumPreviewChart.vue'
import MsStickSpectrumChart from '../components/MsStickSpectrumChart.vue'
import {
  buildLcmsConvertDownloadUrl,
  fetchProtectedFileBlob,
  getApiErrorMessage,
  runLcmsConvert,
} from '../api/specAgentApi'

const directoryInputRef = ref(null)
const selectedFiles = ref([])
const selectedDirectoryName = ref('')
const packaging = ref(false)
const submitting = ref(false)
const stageText = ref('')
const resultData = ref(null)
const activeMsView = ref('filtered')

/**
 * 计算目录文件数量。
 *
 * Returns:
 *   当前已选择文件数量。
 */
const fileCount = computed(() => selectedFiles.value.length)

/**
 * 计算目录总大小。
 *
 * Returns:
 *   当前目录字节总数。
 */
const totalSize = computed(() =>
  selectedFiles.value.reduce((sum, item) => sum + Number(item?.size || 0), 0),
)

/**
 * 计算格式化后的文件大小文本。
 *
 * Returns:
 *   便于展示的大小字符串。
 */
const totalSizeLabel = computed(() => formatSize(totalSize.value))

/**
 * 计算当前 MS 图视图标题。
 *
 * Returns:
 *   当前视图标题。
 */
const currentMsTitle = computed(() =>
  activeMsView.value === 'full' ? 'MS 原始谱图' : 'MS 高峰视图（>= 10% 最大峰强度）',
)

/**
 * 计算当前 MS 图横轴数据。
 *
 * Returns:
 *   当前视图 m/z 数据。
 */
const currentMsXValues = computed(() =>
  activeMsView.value === 'full'
    ? resultData.value?.ms_full_x_values || []
    : resultData.value?.ms_filtered_x_values || [],
)

/**
 * 计算当前 MS 图纵轴数据。
 *
 * Returns:
 *   当前视图 intensity 数据。
 */
const currentMsYValues = computed(() =>
  activeMsView.value === 'full'
    ? resultData.value?.ms_full_y_values || []
    : resultData.value?.ms_filtered_y_values || [],
)

/**
 * 打开目录选择器。
 */
function openDirectoryPicker() {
  directoryInputRef.value?.click()
}

/**
 * 格式化文件体积。
 *
 * Args:
 *   size: 原始字节数。
 *
 * Returns:
 *   格式化后的大小文本。
 */
function formatSize(size) {
  const value = Number(size)
  if (!Number.isFinite(value) || value <= 0) {
    return '0 B'
  }
  if (value < 1024) {
    return `${value} B`
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`
  }
  if (value < 1024 * 1024 * 1024) {
    return `${(value / 1024 / 1024).toFixed(1)} MB`
  }
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`
}

/**
 * 重置已选择目录状态。
 */
function resetSelection() {
  selectedFiles.value = []
  selectedDirectoryName.value = ''
  resultData.value = null
  activeMsView.value = 'filtered'
  if (directoryInputRef.value) {
    directoryInputRef.value.value = ''
  }
}

/**
 * 处理目录选择结果。
 *
 * Args:
 *   event: 原生文件选择事件。
 */
function handleDirectoryChange(event) {
  const files = Array.from(event?.target?.files || [])
  if (files.length === 0) {
    resetSelection()
    return
  }

  const firstRelativePath = String(files[0]?.webkitRelativePath || '')
  const directoryName = firstRelativePath.split('/')[0] || files[0]?.name || ''

  if (!directoryName) {
    ElMessage.warning('未能识别目录名称，请重新选择目录')
    resetSelection()
    return
  }

  selectedFiles.value = files
  selectedDirectoryName.value = directoryName
  resultData.value = null
  activeMsView.value = 'filtered'
  ElMessage.success(`已选择目录：${directoryName}`)
}

/**
 * 将目录文件打包为 zip 文件。
 *
 * Returns:
 *   Promise<File>
 */
async function buildZipFile() {
  if (selectedFiles.value.length === 0 || !selectedDirectoryName.value) {
    throw new Error('请先选择 Waters 数据目录')
  }

  packaging.value = true
  stageText.value = '正在打包目录'
  try {
    const zip = new JSZip()
    for (const file of selectedFiles.value) {
      const relativePath = String(file.webkitRelativePath || file.name || '').trim()
      if (!relativePath) {
        continue
      }
      zip.file(relativePath, file)
    }
    const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE', compressionOptions: { level: 6 } })
    return new File([blob], `${selectedDirectoryName.value}.zip`, { type: 'application/zip' })
  } finally {
    packaging.value = false
  }
}

/**
 * 提交 LCMS 数据转化请求。
 *
 * Returns:
 *   Promise<void>
 */
async function submitConvert() {
  if (selectedFiles.value.length === 0) {
    ElMessage.warning('请先选择 Waters 数据目录')
    return
  }

  submitting.value = true
  resultData.value = null
  try {
    const zipFile = await buildZipFile()
    stageText.value = '正在上传'
    const formData = new FormData()
    formData.append('file', zipFile)

    stageText.value = '正在解析 LCMS 数据'
    const data = await runLcmsConvert(formData, { timeout: 900000 })
    resultData.value = data
    activeMsView.value = 'filtered'
    stageText.value = '正在生成谱图结果'
    ElMessage.success(`转换完成：${data.source_name}`)
  } catch (error) {
    resultData.value = null
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    stageText.value = ''
    submitting.value = false
  }
}

/**
 * 下载转换结果 CSV。
 *
 * Returns:
 *   Promise<void>
 */
async function downloadCsv() {
  if (!resultData.value?.job_id) {
    return
  }

  try {
    const fileData = await fetchProtectedFileBlob(buildLcmsConvertDownloadUrl(resultData.value.job_id))
    const objectUrl = URL.createObjectURL(fileData.blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = fileData.fileName || `${selectedDirectoryName.value || 'lcms'}_apex_ms1.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(objectUrl)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  }
}
</script>

<template>
  <div class="panel lcms-convert-panel">
    <div class="panel-header">
      <h3 class="panel-title">LCMS 数据转化</h3>
      <div class="panel-subtitle">单个 Waters 数据目录转两列 MS 谱图，并在线预览 RT 曲线与质谱峰图</div>
    </div>
    <div class="panel-body">
      <input
        ref="directoryInputRef"
        type="file"
        webkitdirectory
        directory
        multiple
        class="hidden-directory-input"
        @change="handleDirectoryChange"
      />

      <div class="hero-shell">
        <div class="hero-copy">
          <div class="hero-kicker">Tool Service / LCMS</div>
          <h4 class="hero-title">上传设备导出的 Waters 数据目录，直接转换为谱解可用的 MS 两列 CSV</h4>
          <p class="hero-text">
            浏览器会自动读取单个目录并打包上传。当前结果会返回 apex RT、apex TIC、RT-Intensity 曲线，以及原始与高峰两个 MS 视图。
          </p>
          <div class="hero-actions">
            <el-button type="primary" size="large" @click="openDirectoryPicker">选择 Waters 数据目录</el-button>
            <el-button plain size="large" :disabled="fileCount === 0 || submitting || packaging" @click="submitConvert">
              开始转换
            </el-button>
            <el-button text size="large" :disabled="fileCount === 0 || submitting || packaging" @click="resetSelection">
              清空选择
            </el-button>
          </div>
          <div v-if="stageText" class="stage-text">{{ stageText }}</div>
        </div>

        <div class="hero-meta">
          <div class="meta-card">
            <div class="meta-label">目录名称</div>
            <div class="meta-value">{{ selectedDirectoryName || '未选择' }}</div>
          </div>
          <div class="meta-card">
            <div class="meta-label">文件数量</div>
            <div class="meta-value">{{ fileCount }}</div>
          </div>
          <div class="meta-card">
            <div class="meta-label">目录体积</div>
            <div class="meta-value">{{ totalSizeLabel }}</div>
          </div>
        </div>
      </div>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="info-alert"
        title="当前仅支持单个 Waters 数据目录"
        description="目录通常为 .raw，但系统不会强依赖目录后缀；上传时会在浏览器端自动打包为 zip。"
      />

      <el-row v-if="resultData" :gutter="16" class="summary-row">
        <el-col :lg="6" :md="12" :sm="12" :xs="24">
          <div class="summary-card">
            <div class="summary-label">源目录</div>
            <div class="summary-value long">{{ resultData.source_name }}</div>
          </div>
        </el-col>
        <el-col :lg="4" :md="12" :sm="12" :xs="24">
          <div class="summary-card">
            <div class="summary-label">Apex RT</div>
            <div class="summary-value">{{ Number(resultData.apex_rt).toFixed(4) }} min</div>
          </div>
        </el-col>
        <el-col :lg="4" :md="12" :sm="12" :xs="24">
          <div class="summary-card">
            <div class="summary-label">Apex TIC</div>
            <div class="summary-value">{{ Number(resultData.apex_tic).toFixed(2) }}</div>
          </div>
        </el-col>
        <el-col :lg="3" :md="12" :sm="12" :xs="24">
          <div class="summary-card">
            <div class="summary-label">原始点数</div>
            <div class="summary-value">{{ resultData.point_count_full }}</div>
          </div>
        </el-col>
        <el-col :lg="3" :md="12" :sm="12" :xs="24">
          <div class="summary-card">
            <div class="summary-label">高峰点数</div>
            <div class="summary-value">{{ resultData.point_count_filtered }}</div>
          </div>
        </el-col>
        <el-col :lg="4" :md="24" :sm="24" :xs="24">
          <div class="summary-card action">
            <div class="summary-label">结果文件</div>
            <el-button type="primary" plain @click="downloadCsv">下载 CSV</el-button>
          </div>
        </el-col>
      </el-row>

      <el-row v-if="resultData" :gutter="16" class="chart-row">
        <el-col :lg="11" :md="24">
          <el-card shadow="never" class="block-card">
            <template #header>
              <div class="card-header">
                <span>RT-Intensity 曲线</span>
                <span class="card-tip">当前导出的 MS 谱取自 TIC 顶点扫描点</span>
              </div>
            </template>
            <SpectrumPreviewChart
              :x-values="resultData.rt_x_values"
              :y-values="resultData.rt_y_values"
              title="Retention Time - Intensity"
              x-axis-name="Retention Time (min)"
              y-axis-name="Intensity"
            />
          </el-card>
        </el-col>

        <el-col :lg="13" :md="24">
          <el-card shadow="never" class="block-card">
            <template #header>
              <div class="card-header ms-header">
                <span>MS 谱图</span>
                <el-radio-group v-model="activeMsView" size="small">
                  <el-radio-button value="filtered">高峰视图</el-radio-button>
                  <el-radio-button value="full">原始谱图</el-radio-button>
                </el-radio-group>
              </div>
            </template>
            <MsStickSpectrumChart
              :x-values="currentMsXValues"
              :y-values="currentMsYValues"
              :label-peaks="resultData.label_peaks"
              :title="currentMsTitle"
            />
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<style scoped>
.hidden-directory-input {
  display: none;
}

.lcms-convert-panel {
  overflow: hidden;
}

.panel-subtitle {
  margin-top: 6px;
  color: #7d90ad;
  font-size: 13px;
}

.hero-shell {
  display: grid;
  grid-template-columns: 1.5fr 0.9fr;
  gap: 18px;
  padding: 22px;
  margin-bottom: 18px;
  border: 1px solid #dbe4f1;
  border-radius: 22px;
  background:
    radial-gradient(circle at top right, rgba(13, 124, 109, 0.14), transparent 32%),
    linear-gradient(135deg, #fbfcff 0%, #f4f8ff 48%, #eef6f3 100%);
}

.hero-kicker {
  color: #0f7b6c;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-title {
  margin: 10px 0 12px;
  color: #203556;
  font-size: 24px;
  line-height: 1.35;
}

.hero-text {
  max-width: 720px;
  color: #536988;
  line-height: 1.75;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 18px;
}

.stage-text {
  margin-top: 14px;
  color: #0f7b6c;
  font-weight: 600;
}

.hero-meta {
  display: grid;
  gap: 12px;
}

.meta-card,
.summary-card {
  border: 1px solid rgba(120, 142, 173, 0.18);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 12px 30px rgba(33, 63, 98, 0.06);
}

.meta-card {
  padding: 16px 18px;
}

.meta-label,
.summary-label {
  color: #7185a2;
  font-size: 12px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.meta-value,
.summary-value {
  margin-top: 8px;
  color: #203556;
  font-size: 22px;
  font-weight: 700;
  line-height: 1.35;
}

.meta-value {
  font-size: 18px;
}

.summary-row {
  margin: 4px 0 6px;
}

.summary-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 118px;
  padding: 18px 18px 16px;
}

.summary-card.action {
  align-items: flex-start;
}

.summary-value.long {
  font-size: 16px;
  word-break: break-all;
}

.info-alert {
  margin-bottom: 16px;
}

.chart-row {
  margin-top: 8px;
}

.block-card {
  margin-bottom: 16px;
  border-radius: 18px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 600;
  color: #203556;
}

.card-tip {
  color: #7185a2;
  font-size: 12px;
  font-weight: 500;
}

.ms-header {
  flex-wrap: wrap;
}

@media (max-width: 1024px) {
  .hero-shell {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .hero-shell {
    padding: 18px;
    border-radius: 18px;
  }

  .hero-title {
    font-size: 20px;
  }

  .summary-card {
    min-height: 98px;
  }
}
</style>
