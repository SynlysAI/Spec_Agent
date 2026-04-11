<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createGpcTask, getApiErrorMessage, uploadFile } from '../api/specAgentApi'

const submitting = ref(false)
const selectedUploadFile = ref(null)
const uploadedFileId = ref('')
const uploadedFilename = ref('')
const lastTaskId = ref('')

const form = reactive({
  inputMode: 'upload',
  inputPath: '',
  detectMode: 'auto',
  manualStart: null,
  manualEnd: null,
  threeColorPathText: '',
  calibrationFilePath: '',
  comparisonReportPdfPath: '',
  priority: 5,
})

/**
 * 处理 GPC 文件选择（仅缓存，不立即上传）。
 *
 * Args:
 *   file: 上传文件对象。
 *
 * Returns:
 *   boolean
 */
async function handleUpload(file) {
  selectedUploadFile.value = file
  uploadedFileId.value = ''
  uploadedFilename.value = file?.name || ''
  ElMessage.success(`已选择文件：${uploadedFilename.value}`)
  return false
}

/**
 * 构建任务输入对象。
 *
 * Returns:
 *   GPC 输入参数。
 */
function buildInput() {
  if (form.inputMode === 'path') {
    return {
      input_type: 'file_path',
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
 * 解析三色曲线文本输入。
 *
 * Returns:
 *   string[] | null
 */
function parseThreeColorPaths() {
  const items = form.threeColorPathText
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
  return items.length > 0 ? items : null
}

/**
 * 提交 GPC 分析任务。
 *
 * Returns:
 *   Promise<void>
 */
async function submitTask() {
  if (form.inputMode === 'path' && !form.inputPath.trim()) {
    ElMessage.warning('请填写 GPC 文件路径')
    return
  }
  if (form.inputMode === 'upload' && !uploadedFileId.value) {
    if (!selectedUploadFile.value) {
      ElMessage.warning('请先选择 GPC 文件')
      return
    }
  }
  if (form.inputMode === 'upload' && selectedUploadFile.value) {
    try {
      const data = await uploadFile(selectedUploadFile.value, 'gpc')
      uploadedFileId.value = data.file_id
      uploadedFilename.value = data.filename
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error))
      return
    }
  }
  if (form.inputMode === 'upload' && !uploadedFileId.value) {
    ElMessage.warning('上传失败，请重新选择文件')
    return
  }
  if (form.detectMode === 'manual' && (form.manualStart === null || form.manualEnd === null)) {
    ElMessage.warning('手动模式下必须填写检测区间')
    return
  }

  const payload = {
    input: buildInput(),
    params: {
      detect_mode: form.detectMode,
      manual_interval:
        form.detectMode === 'manual' ? [Number(form.manualStart), Number(form.manualEnd)] : null,
      three_color_arw_paths: parseThreeColorPaths(),
      calibration_file_path: form.calibrationFilePath.trim() || null,
      comparison_report_pdf_path: form.comparisonReportPdfPath.trim() || null,
    },
    options: {
      priority: Number(form.priority || 5),
      callback_url: null,
    },
  }

  submitting.value = true
  try {
    const data = await createGpcTask(payload)
    lastTaskId.value = data.task_id
    ElMessage.success(`GPC 任务创建成功：${data.task_id}`)
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
      <h3 class="panel-title">GPC 任务提交</h3>
    </div>
    <div class="panel-body">
      <el-form label-width="180px">
        <el-form-item label="输入方式">
          <el-radio-group v-model="form.inputMode">
            <el-radio value="upload">上传文件</el-radio>
            <el-radio value="path">服务器本地文件路径</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="form.inputMode === 'path'" label="谱图文件路径">
          <el-input v-model="form.inputPath" placeholder="示例：E:/spectrum_files/gpc/spectrum/demo.arw" />
        </el-form-item>

        <el-form-item v-else label="上传谱图文件">
          <el-upload :show-file-list="false" :before-upload="handleUpload" accept=".arw,.pdf,.json">
            <el-button type="primary" plain>选择文件</el-button>
          </el-upload>
          <el-tag v-if="uploadedFilename" style="margin-left: 10px">{{ uploadedFilename }}</el-tag>
          <div style="margin-left: 10px; color: #7a8ca8; font-size: 12px">提交任务时自动上传</div>
        </el-form-item>

        <el-divider content-position="left">峰检测参数</el-divider>
        <el-form-item label="峰检测模式">
          <el-radio-group v-model="form.detectMode">
            <el-radio value="auto">自动检测</el-radio>
            <el-radio value="manual">手动区间</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="form.detectMode === 'manual'" label="手动检测区间">
          <el-input-number v-model="form.manualStart" :precision="4" />
          <span style="margin: 0 8px">-</span>
          <el-input-number v-model="form.manualEnd" :precision="4" />
        </el-form-item>

        <el-form-item label="三色曲线路径列表">
          <el-input
            v-model="form.threeColorPathText"
            type="textarea"
            :rows="3"
            placeholder="每行一个路径，可选；为空则传 null"
          />
        </el-form-item>

        <el-form-item label="校准文件路径">
          <el-input v-model="form.calibrationFilePath" placeholder="可选，设置 calibration_file_path" />
        </el-form-item>

        <el-form-item label="对比报告PDF路径">
          <el-input v-model="form.comparisonReportPdfPath" placeholder="可选，设置 comparison_report_pdf_path" />
        </el-form-item>

        <el-form-item label="任务优先级">
          <el-input-number v-model="form.priority" :min="1" :max="10" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submitTask">提交 GPC 任务</el-button>
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
