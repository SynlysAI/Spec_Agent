<script setup>
import { reactive, ref } from 'vue'
import JSZip from 'jszip'
import { ElMessage } from 'element-plus'
import { createNmrTask, getApiErrorMessage, uploadFile } from '../api/specAgentApi'

const submitting = ref(false)
const folderInputRef = ref(null)
const selectedZipFile = ref(null)
const uploadedFileId = ref('')
const uploadedFilename = ref('')
const lastTaskId = ref('')

const form = reactive({
  inputMode: 'upload',
  inputPath: '',
  nucleus: '1H',
  threshold: 0.01,
  minDistance: 0.3,
  minProminence: 0.01,
  widthMultiplier: 1.0,
  baselineDegree: 3,
  smoothWindow: 5,
  detectionRangeMode: 'full',
  detectionRangeMin: null,
  detectionRangeMax: null,
  ppmOffset: 0.0,
  integrationMethod: 'voigt',
  internalStandardPolicy: 'auto',
  internalStandardPrefer: ['solvent', 'tms'],
  priority: 5,
})

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
  if (form.inputMode === 'path') {
    return {
      input_type: 'folder_path',
      input_path: form.inputPath.trim(),
      file_id: null,
    }
  }
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
  if (form.inputMode === 'path' && !form.inputPath.trim()) {
    ElMessage.warning('请填写 NMR 文件夹路径')
    return
  }
  if (form.inputMode === 'upload' && !uploadedFileId.value) {
    if (!selectedZipFile.value) {
      ElMessage.warning('请先选择 NMR 文件夹')
      return
    }
  }
  if (form.inputMode === 'upload' && selectedZipFile.value) {
    try {
      const data = await uploadFile(selectedZipFile.value, 'nmr')
      uploadedFileId.value = data.file_id
      uploadedFilename.value = data.filename
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error))
      return
    }
  }
  if (form.inputMode === 'upload' && !uploadedFileId.value) {
    ElMessage.warning('上传失败，请重新选择文件夹')
    return
  }
  if (
    form.detectionRangeMode === 'custom' &&
    (form.detectionRangeMin === null || form.detectionRangeMax === null)
  ) {
    ElMessage.warning('自定义检测范围时必须填写最小/最大值')
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
      detection_range_mode: form.detectionRangeMode,
      detection_range_min:
        form.detectionRangeMode === 'custom' ? Number(form.detectionRangeMin) : null,
      detection_range_max:
        form.detectionRangeMode === 'custom' ? Number(form.detectionRangeMax) : null,
      ppm_offset: Number(form.ppmOffset),
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
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h3 class="panel-title">NMR 任务提交</h3>
    </div>
    <div class="panel-body">
      <el-form label-width="190px">
        <el-form-item label="输入方式">
          <el-radio-group v-model="form.inputMode">
            <el-radio value="upload">上传文件</el-radio>
            <el-radio value="path">服务器本地文件夹路径</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="form.inputMode === 'path'" label="NMR 文件夹路径">
          <el-input v-model="form.inputPath" placeholder="示例：E:/spectrum_files/nmr/2026-03-17/WLS-0312-H" />
        </el-form-item>

        <el-form-item v-else label="上传 NMR 文件夹">
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
          <el-tag v-if="uploadedFilename" style="margin-left: 10px">{{ uploadedFilename }}</el-tag>
          <div style="margin-left: 10px; color: #7a8ca8; font-size: 12px">
            将自动打包为 zip，提交任务时上传
          </div>
        </el-form-item>

        <el-divider content-position="left">峰检测参数</el-divider>
        <el-form-item label="检测核种">
          <el-radio-group v-model="form.nucleus">
            <el-radio value="1H">氢谱（1H）</el-radio>
            <el-radio value="13C">碳谱（13C）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="峰检测阈值">
          <el-input-number v-model="form.threshold" :precision="4" :step="0.005" />
        </el-form-item>
        <el-form-item label="最小峰间距">
          <el-input-number v-model="form.minDistance" :precision="3" :step="0.1" />
        </el-form-item>
        <el-form-item label="最小显著性">
          <el-input-number v-model="form.minProminence" :precision="4" :step="0.005" />
        </el-form-item>
        <el-form-item label="峰宽倍率">
          <el-input-number v-model="form.widthMultiplier" :precision="2" :step="0.1" />
        </el-form-item>
        <el-form-item label="基线拟合阶数">
          <el-input-number v-model="form.baselineDegree" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="平滑窗口">
          <el-input-number v-model="form.smoothWindow" :min="1" :max="99" />
        </el-form-item>

        <el-form-item label="检测范围模式">
          <el-radio-group v-model="form.detectionRangeMode">
            <el-radio value="full">全谱范围</el-radio>
            <el-radio value="custom">自定义范围</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.detectionRangeMode === 'custom'" label="自定义检测范围">
          <el-input-number v-model="form.detectionRangeMin" :precision="3" />
          <span style="margin: 0 8px">-</span>
          <el-input-number v-model="form.detectionRangeMax" :precision="3" />
        </el-form-item>

        <el-divider content-position="left">积分与内标</el-divider>
        <el-form-item label="ppm 偏移校正">
          <el-input-number v-model="form.ppmOffset" :precision="3" :step="0.01" />
        </el-form-item>
        <el-form-item label="积分方法">
          <el-radio-group v-model="form.integrationMethod">
            <el-radio value="voigt">Voigt 拟合积分</el-radio>
            <el-radio value="trapezoid">梯形积分</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="内标策略">
          <el-input v-model="form.internalStandardPolicy" disabled />
        </el-form-item>
        <el-form-item label="内标优先级">
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
        description="可在任务中心查看进度和结果。"
      />
    </div>
  </div>
</template>
