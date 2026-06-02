<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createGpcTask, getApiErrorMessage, uploadFile } from '../api/specAgentApi'

const router = useRouter()
const submitting = ref(false)
const selectedUploadFile = ref(null)
const uploadedFileId = ref('')
const uploadedFilename = ref('')
const lastTaskId = ref('')

const form = reactive({
  detectMode: 'auto',
  manualStart: null,
  manualEnd: null,
  priority: 5,
})

// 三色曲线文件（红/绿/白）
const curveFiles = reactive({
  red: { file: null, fileId: '', filename: '' },
  green: { file: null, fileId: '', filename: '' },
  white: { file: null, fileId: '', filename: '' },
})

// 校准文件
const calibrationFile = reactive({ file: null, fileId: '', filename: '' })

// 对比报告 PDF
const comparisonPdf = reactive({ file: null, fileId: '', filename: '' })

/**
 * 处理 GPC 谱图文件选择（仅缓存，不立即上传）。
 */
async function handleUpload(file) {
  selectedUploadFile.value = file
  uploadedFileId.value = ''
  uploadedFilename.value = file?.name || ''
  ElMessage.success(`已选择文件：${uploadedFilename.value}`)
  return false
}

/**
 * 处理可选文件选择（通用）。
 */
function handleOptionalFile(file, target) {
  target.file = file
  target.fileId = ''
  target.filename = file?.name || ''
  ElMessage.success(`已选择文件：${target.filename}`)
  return false
}

/**
 * 清除可选文件。
 */
function clearOptionalFile(target) {
  target.file = null
  target.fileId = ''
  target.filename = ''
}

/**
 * 上传单个文件并返回 file_id。
 */
async function uploadSingleFile(file, bizType) {
  const data = await uploadFile(file, bizType)
  return data.file_id
}

/**
 * 构建任务输入对象。
 */
function buildInput() {
  return {
    input_type: 'file_id',
    input_path: null,
    file_id: uploadedFileId.value,
  }
}

/**
 * 提交 GPC 分析任务。
 *
 * Returns:
 *   Promise<void>
 */
async function submitTask() {
  if (!uploadedFileId.value) {
    if (!selectedUploadFile.value) {
      ElMessage.warning('请先选择 GPC 文件')
      return
    }
  }
  if (selectedUploadFile.value) {
    try {
      const data = await uploadFile(selectedUploadFile.value, 'gpc')
      uploadedFileId.value = data.file_id
      uploadedFilename.value = data.file_name
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error))
      return
    }
  }
  if (!uploadedFileId.value) {
    ElMessage.warning('上传失败，请重新选择文件')
    return
  }
  if (form.detectMode === 'manual' && (form.manualStart === null || form.manualEnd === null)) {
    ElMessage.warning('手动模式下必须填写检测区间')
    return
  }

  // 三色曲线：如果有一个选了，就必须三个都选
  const curveColors = ['red', 'green', 'white']
  const hasAnyCurve = curveColors.some((c) => curveFiles[c].file)
  if (hasAnyCurve) {
    const missing = curveColors.filter((c) => !curveFiles[c].file)
    if (missing.length > 0) {
      const nameMap = { red: '红色', green: '绿色', white: '白色' }
      ElMessage.warning(`三色曲线必须传完整，缺少：${missing.map((c) => nameMap[c]).join('、')}`)
      return
    }
  }

  submitting.value = true
  try {
    // 上传可选文件
    let threeColorFileIds = null
    if (hasAnyCurve) {
      threeColorFileIds = []
      for (const color of curveColors) {
        const fid = await uploadSingleFile(curveFiles[color].file, 'gpc')
        curveFiles[color].fileId = fid
        threeColorFileIds.push(fid)
      }
    }

    let calibrationFileId = null
    if (calibrationFile.file) {
      calibrationFileId = await uploadSingleFile(calibrationFile.file, 'gpc')
      calibrationFile.fileId = calibrationFileId
    }

    let comparisonPdfFileId = null
    if (comparisonPdf.file) {
      comparisonPdfFileId = await uploadSingleFile(comparisonPdf.file, 'gpc')
      comparisonPdf.fileId = comparisonPdfFileId
    }

    const payload = {
      input: buildInput(),
      params: {
        detect_mode: form.detectMode,
        manual_interval:
          form.detectMode === 'manual' ? [Number(form.manualStart), Number(form.manualEnd)] : null,
        three_color_arw_file_ids: threeColorFileIds,
        calibration_file_id: calibrationFileId,
        comparison_report_pdf_file_id: comparisonPdfFileId,
        source_file_name: uploadedFilename.value || null,
      },
      options: {
        priority: Number(form.priority || 5),
        callback_url: null,
      },
    }

    const data = await createGpcTask(payload)
    lastTaskId.value = data.task_id
    ElMessage.success(`GPC 任务创建成功：${data.task_id}`)
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
      <h3 class="panel-title">GPC 任务提交</h3>
    </div>
    <div class="panel-body">
      <el-form label-width="180px">
        <el-form-item label="上传谱图文件">
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

        <el-divider content-position="left">可选附件</el-divider>

        <el-form-item label="三色曲线文件">
          <div style="display: flex; gap: 16px; flex-wrap: wrap">
            <div v-for="color in ['red', 'green', 'white']" :key="color" style="display: flex; align-items: center; gap: 8px">
              <span style="min-width: 40px">{{ { red: '红色', green: '绿色', white: '白色' }[color] }}：</span>
              <el-upload :show-file-list="false" :before-upload="(file) => handleOptionalFile(file, curveFiles[color])" accept=".arw">
                <el-button size="small" plain>选择文件</el-button>
              </el-upload>
              <el-tag v-if="curveFiles[color].filename" closable @close="clearOptionalFile(curveFiles[color])" size="small">
                {{ curveFiles[color].filename }}
              </el-tag>
            </div>
          </div>
          <div style="color: #7a8ca8; font-size: 12px; margin-top: 4px">可选，传则三个颜色必须传完整（.arw）</div>
        </el-form-item>

        <el-form-item label="校准文件">
          <el-upload :show-file-list="false" :before-upload="(file) => handleOptionalFile(file, calibrationFile)" accept=".json,.arw">
            <el-button plain>选择文件</el-button>
          </el-upload>
          <el-tag v-if="calibrationFile.filename" closable @close="clearOptionalFile(calibrationFile)" style="margin-left: 10px">
            {{ calibrationFile.filename }}
          </el-tag>
          <div style="margin-left: 10px; color: #7a8ca8; font-size: 12px">可选，不传则使用默认校准文件</div>
        </el-form-item>

        <el-form-item label="对比报告PDF">
          <el-upload :show-file-list="false" :before-upload="(file) => handleOptionalFile(file, comparisonPdf)" accept=".pdf">
            <el-button plain>选择文件</el-button>
          </el-upload>
          <el-tag v-if="comparisonPdf.filename" closable @close="clearOptionalFile(comparisonPdf)" style="margin-left: 10px">
            {{ comparisonPdf.filename }}
          </el-tag>
          <div style="margin-left: 10px; color: #7a8ca8; font-size: 12px">可选，不传则不进行对比报告分析</div>
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
      >
        <p>
          可在任务中心查看进度和结果，
          <el-link type="primary" @click="goTaskDetail">点击查看任务详情</el-link>
        </p>
      </el-alert>
    </div>
  </div>
</template>
