<script setup>
import { reactive, ref, watch } from 'vue'
import JSZip from 'jszip'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import FormLabelTooltip from '../components/FormLabelTooltip.vue'
import SampleDownloadButton from '../components/SampleDownloadButton.vue'
import { createNmrTask, getApiErrorMessage, uploadFile } from '../api/specAgentApi'

const router = useRouter()
const submitting = ref(false)
const folderInputRef = ref(null)
const selectedZipFile = ref(null)
const uploadedFileId = ref('')
const uploadedFilename = ref('')
const lastTaskId = ref('')

const NMR_PEAK_PRESETS = {
  '1H': {
    threshold: 0.01,
    minDistance: 0.3,
    minProminence: 0.01,
    smoothWindow: 5,
    maxCouplingHz: 20.0,
  },
  '13C': {
    threshold: 0.05,
    minDistance: 1.0,
    minProminence: 0.03,
    smoothWindow: 11,
    maxCouplingHz: 40.0,
  },
}

const form = reactive({
  nucleus: '1H',
  threshold: NMR_PEAK_PRESETS['1H'].threshold,
  minDistance: NMR_PEAK_PRESETS['1H'].minDistance,
  minProminence: NMR_PEAK_PRESETS['1H'].minProminence,
  widthMultiplier: 1.0,
  baselineDegree: 3,
  smoothWindow: NMR_PEAK_PRESETS['1H'].smoothWindow,
  enableMultiplet: true,
  maxCouplingHz: NMR_PEAK_PRESETS['1H'].maxCouplingHz,
  detectionRangeMode: 'full',
  detectionRangeMin: null,
  detectionRangeMax: null,
  ppmOffsetMode: 'auto',
  ppmOffsetManual: 0.0,
  integrationMethod: 'voigt',
  internalStandardPolicy: 'auto',
  internalStandardPrefer: ['solvent', 'tms'],
  priority: 5,
})

const NMR_TOOLTIP_TEXT = {
  threshold: '峰检测阈值。值越高，越不容易把弱峰或噪声识别成有效峰。',
  minDistance: '最小峰间距，单位 ppm。用于避免相邻很近的峰被重复识别。',
  minProminence: '最小峰高阈值。要求峰相对周围基线足够明显，值越高越偏向保留显著峰。',
  widthMultiplier: '峰宽倍率。用于放大或收缩积分和峰宽估计范围，值越大覆盖范围越宽。',
  baselineDegree: '基线拟合阶数。用于扣除基线漂移，阶数越高对复杂基线的拟合更灵活。',
  smoothWindow: '平滑窗口。用于降低噪声；窗口越大越平滑，但可能削弱窄峰细节。',
  enableMultiplet: '多重峰聚合。开启后会把耦合导致的近邻细分峰按多重峰规则合并分析。',
  maxCouplingHz: '耦合常数阈值。用于判断相近峰是否视为同一组多重峰，值越大合并更宽松。',
  detectionRangeMode: '检测范围模式。全谱会扫描全部 ppm 区间，自定义范围只在指定 ppm 内找峰。',
  detectionRange: '自定义检测范围。填写需要检测的 ppm 起止范围，适合只分析局部谱段。',
  ppmOffsetMode: '位移校正方式。自动按内标/TMS 对齐；手动适合你已知整体 ppm 偏移量时使用。',
  ppmOffsetManual: '手动校正值。用于整体平移谱图的 ppm 位置，正负方向按当前谱图坐标解释。',
  integrationMethod: '积分方法。Voigt 拟合更适合峰形重叠场景；梯形积分更直观、速度更快。',
  internalStandardPrefer: '内标优先级。系统自动寻找内标时，会按这里的顺序优先尝试溶剂峰或 TMS。',
}

const NMR_SAMPLE_ASSET_PATH = '/example-spectra/nmr-demo.zip'
const NMR_SAMPLE_DOWNLOAD_NAME = 'nmr-demo.zip'

/**
 * 根据核种应用默认峰检测参数。
 *
 * Args:
 *   nucleus: 核种类型，支持 1H / 13C。
 */
function applyNucleusPreset(nucleus) {
  const preset = NMR_PEAK_PRESETS[nucleus]
  if (!preset) {
    return
  }
  form.threshold = preset.threshold
  form.minDistance = preset.minDistance
  form.minProminence = preset.minProminence
  form.smoothWindow = preset.smoothWindow
  form.maxCouplingHz = preset.maxCouplingHz
}

watch(
  () => form.nucleus,
  (nucleus) => {
    applyNucleusPreset(nucleus)
  },
  { immediate: true },
)

/**
 * 打开目录选择器。
 */
function openFolderPicker() {
  folderInputRef.value?.click()
}

/**
 * 将目录文件列表打包为 zip 文件。
 *
 * Args:
 *   files: 浏览器目录选择得到的文件列表。
 *
 * Returns:
 *   Promise<File>
 */
async function buildZipFromFolder(files) {
  const zip = new JSZip()
  const fileList = Array.from(files || [])
  if (fileList.length === 0) {
    throw new Error('未选择任何文件')
  }
  for (const file of fileList) {
    const relativePath = file.webkitRelativePath || file.name
    zip.file(relativePath, file)
  }
  const rootName = (fileList[0]?.webkitRelativePath || 'nmr_folder').split('/')[0] || 'nmr_folder'
  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })
  return new File([blob], `${rootName}.zip`, { type: 'application/zip' })
}

/**
 * 处理 NMR 目录选择（仅本地打包，不立即上传）。
 *
 * Args:
 *   event: 文件选择事件对象。
 *
 * Returns:
 *   Promise<void>
 */
async function handleFolderChange(event) {
  try {
    const files = event?.target?.files
    const zipFile = await buildZipFromFolder(files)
    selectedZipFile.value = zipFile
    uploadedFileId.value = ''
    uploadedFilename.value = zipFile.name
    ElMessage.success(`已选择文件夹：${zipFile.name}`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    if (event?.target) {
      event.target.value = ''
    }
  }
}

/**
 * 构建 NMR 任务输入对象。
 *
 * Returns:
 *   NMR 输入参数。
 */
function buildInput() {
  return {
    input_type: 'file_id',
    input_path: null,
    file_id: uploadedFileId.value,
  }
}

/**
 * 提交 NMR 分析任务。
 *
 * Returns:
 *   Promise<void>
 */
async function submitTask() {
  if (!uploadedFileId.value) {
    if (!selectedZipFile.value) {
      ElMessage.warning('请先选择 NMR 文件夹')
      return
    }
  }
  if (selectedZipFile.value) {
    try {
      const data = await uploadFile(selectedZipFile.value, 'nmr')
      uploadedFileId.value = data.file_id
      uploadedFilename.value = data.file_name
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error))
      return
    }
  }
  if (!uploadedFileId.value) {
    ElMessage.warning('上传失败，请重新选择文件夹')
    return
  }
  if (
    form.detectionRangeMode === 'custom' &&
    (form.detectionRangeMin === null || form.detectionRangeMax === null)
  ) {
    ElMessage.warning('自定义检测范围（ppm）时必须填写最小/最大值')
    return
  }

  const payload = {
    input: buildInput(),
    params: {
      nucleus: form.nucleus,
      threshold: Number(form.threshold),
      min_distance: Number(form.minDistance),
      min_prominence: Number(form.minProminence),
      width_multiplier: Number(form.widthMultiplier),
      baseline_degree: Number(form.baselineDegree),
      smooth_window: Number(form.smoothWindow),
      enable_multiplet: Boolean(form.enableMultiplet),
      max_coupling_hz: Number(form.maxCouplingHz),
      detection_range_mode: form.detectionRangeMode,
      detection_range_min:
        form.detectionRangeMode === 'custom' ? Number(form.detectionRangeMin) : null,
      detection_range_max:
        form.detectionRangeMode === 'custom' ? Number(form.detectionRangeMax) : null,
      ppm_offset:
        form.ppmOffsetMode === 'manual' ? Number(form.ppmOffsetManual || 0) : 0.0,
      integration_method: form.integrationMethod,
      internal_standard_policy: form.internalStandardPolicy,
      internal_standard_prefer: form.internalStandardPrefer,
    },
    options: {
      priority: Number(form.priority || 5),
      callback_url: null,
    },
  }

  submitting.value = true
  try {
    const data = await createNmrTask(payload)
    lastTaskId.value = data.task_id
    ElMessage.success(`NMR 任务创建成功：${data.task_id}`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    submitting.value = false
  }
}

/**
 * 跳转到任务详情页。
 */
function goTaskDetail() {
  if (!lastTaskId.value) {
    return
  }
  router.push(`/tasks/detail/${lastTaskId.value}`)
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h3 class="panel-title">NMR 任务提交</h3>
    </div>
    <div class="panel-body">
      <el-form class="task-submit-form" label-width="190px">
        <el-form-item label="上传 NMR 文件夹">
          <input
            ref="folderInputRef"
            type="file"
            style="display: none"
            webkitdirectory
            directory
            multiple
            @change="handleFolderChange"
          />
          <el-button type="primary" plain @click="openFolderPicker">
            选择 Bruker 目录
          </el-button>
          <SampleDownloadButton
            :asset-path="NMR_SAMPLE_ASSET_PATH"
            :download-name="NMR_SAMPLE_DOWNLOAD_NAME"
            button-text="下载范例目录"
          />
          <el-tag v-if="uploadedFilename" style="margin-left: 10px">{{ uploadedFilename }}</el-tag>
          <div class="task-submit-help">
            请选择单个 Bruker 数据目录。当前页面用于 1H / 13C NMR 自动分析。
          </div>
        </el-form-item>

        <el-divider content-position="left">峰检测参数</el-divider>
        <el-form-item label="检测核种">
          <el-radio-group v-model="form.nucleus">
            <el-radio value="1H">氢谱（1H）</el-radio>
            <el-radio value="13C">碳谱（13C）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="峰检测阈值" :tooltip="NMR_TOOLTIP_TEXT.threshold" />
          </template>
          <el-input-number v-model="form.threshold" :precision="4" :step="0.005" />
        </el-form-item>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="最小峰间距" :tooltip="NMR_TOOLTIP_TEXT.minDistance" />
          </template>
          <el-input-number v-model="form.minDistance" :precision="3" :step="0.1" />
        </el-form-item>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="最小峰高阈值" :tooltip="NMR_TOOLTIP_TEXT.minProminence" />
          </template>
          <el-input-number v-model="form.minProminence" :precision="4" :step="0.005" />
        </el-form-item>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="峰宽倍率" :tooltip="NMR_TOOLTIP_TEXT.widthMultiplier" />
          </template>
          <el-input-number v-model="form.widthMultiplier" :precision="2" :step="0.1" />
        </el-form-item>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="基线拟合阶数" :tooltip="NMR_TOOLTIP_TEXT.baselineDegree" />
          </template>
          <el-input-number v-model="form.baselineDegree" :min="1" :max="10" />
        </el-form-item>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="平滑窗口" :tooltip="NMR_TOOLTIP_TEXT.smoothWindow" />
          </template>
          <el-input-number v-model="form.smoothWindow" :min="1" :max="99" />
        </el-form-item>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="启用多重峰聚合" :tooltip="NMR_TOOLTIP_TEXT.enableMultiplet" />
          </template>
          <el-switch v-model="form.enableMultiplet" />
        </el-form-item>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="耦合常数阈值（Hz）" :tooltip="NMR_TOOLTIP_TEXT.maxCouplingHz" />
          </template>
          <el-input-number v-model="form.maxCouplingHz" :precision="2" :step="1" :min="0.1" />
        </el-form-item>

        <el-form-item>
          <template #label>
            <FormLabelTooltip label="检测范围模式（ppm）" :tooltip="NMR_TOOLTIP_TEXT.detectionRangeMode" />
          </template>
          <el-radio-group v-model="form.detectionRangeMode">
            <el-radio value="full">全谱范围（ppm）</el-radio>
            <el-radio value="custom">自定义范围（ppm）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.detectionRangeMode === 'custom'">
          <template #label>
            <FormLabelTooltip label="自定义检测范围（ppm）" :tooltip="NMR_TOOLTIP_TEXT.detectionRange" />
          </template>
          <el-input-number v-model="form.detectionRangeMin" :precision="3" />
          <span style="margin: 0 8px">-</span>
          <el-input-number v-model="form.detectionRangeMax" :precision="3" />
        </el-form-item>

        <el-divider content-position="left">积分与内标</el-divider>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="位移校正方式" :tooltip="NMR_TOOLTIP_TEXT.ppmOffsetMode" />
          </template>
          <el-radio-group v-model="form.ppmOffsetMode">
            <el-radio value="auto">自动校正（按 TMS）</el-radio>
            <el-radio value="manual">手动位移校正</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.ppmOffsetMode === 'manual'">
          <template #label>
            <FormLabelTooltip label="手动校正值（ppm）" :tooltip="NMR_TOOLTIP_TEXT.ppmOffsetManual" />
          </template>
          <el-input-number v-model="form.ppmOffsetManual" :precision="3" :step="0.01" />
        </el-form-item>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="积分方法" :tooltip="NMR_TOOLTIP_TEXT.integrationMethod" />
          </template>
          <el-radio-group v-model="form.integrationMethod">
            <el-radio value="voigt">Voigt 拟合积分</el-radio>
            <el-radio value="trapezoid">梯形积分</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="内标策略">
          <el-input v-model="form.internalStandardPolicy" disabled />
        </el-form-item>
        <el-form-item>
          <template #label>
            <FormLabelTooltip label="内标优先级" :tooltip="NMR_TOOLTIP_TEXT.internalStandardPrefer" />
          </template>
          <el-select v-model="form.internalStandardPrefer" multiple style="width: 320px">
            <el-option label="溶剂峰（solvent）" value="solvent" />
            <el-option label="TMS 峰（tms）" value="tms" />
          </el-select>
        </el-form-item>

        <el-form-item label="任务优先级">
          <el-input-number v-model="form.priority" :min="1" :max="10" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submitTask">提交 NMR 任务</el-button>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="lastTaskId"
        type="success"
        :closable="false"
        show-icon
        :title="`任务创建成功：${lastTaskId}`"
      >
        <p>
          可在任务中心查看进度和结果，
          <el-link type="primary" @click="goTaskDetail">点击查看任务详情</el-link>
        </p>
      </el-alert>
    </div>
  </div>
</template>
