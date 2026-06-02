<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createLcmsTask, getApiErrorMessage, uploadFile } from '../api/specAgentApi'

const router = useRouter()
const submitting = ref(false)
const selectedUploadFile = ref(null)
const uploadedFileId = ref('')
const uploadedFilename = ref('')
const lastTaskId = ref('')

const form = reactive({
  priority: 5,
})

/**
 * 处理 LCMS 文件选择（仅缓存，不立即上传）。
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
 * 构建 LCMS 任务输入对象。
 *
 * Returns:
 *   LCMS 输入参数。
 */
function buildInput() {
  return {
    input_type: 'file_id',
    input_path: null,
    file_id: uploadedFileId.value,
  }
}

/**
 * 提交 LCMS 分析任务。
 *
 * Returns:
 *   Promise<void>
 */
async function submitTask() {
  if (!uploadedFileId.value) {
    if (!selectedUploadFile.value) {
      ElMessage.warning('请先选择 LCMS 文件')
      return
    }
    try {
      const data = await uploadFile(selectedUploadFile.value, 'lcms')
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

  const payload = {
    input: buildInput(),
    params: {
      source_file_name: uploadedFilename.value || null,
    },
    options: {
      priority: Number(form.priority || 5),
      callback_url: null,
    },
  }

  submitting.value = true
  try {
    const data = await createLcmsTask(payload)
    lastTaskId.value = data.task_id
    ElMessage.success(`LCMS 任务创建成功：${data.task_id}`)
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
      <h3 class="panel-title">LCMS 任务提交</h3>
    </div>
    <div class="panel-body">
      <el-form label-width="180px">
        <el-form-item label="上传谱图文件">
          <el-upload :show-file-list="false" :before-upload="handleUpload" accept=".txt,.csv">
            <el-button type="primary" plain>选择文件</el-button>
          </el-upload>
          <el-tag v-if="uploadedFilename" style="margin-left: 10px">{{ uploadedFilename }}</el-tag>
          <div class="upload-help">支持格式：txt/csv（LCMS），提交任务时自动上传</div>
        </el-form-item>

        <el-form-item label="任务优先级">
          <el-input-number v-model="form.priority" :min="1" :max="10" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submitTask">提交 LCMS 任务</el-button>
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

<style scoped>
.upload-help {
  margin-left: 10px;
  color: #7a8ca8;
  font-size: 12px;
}
</style>
