<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createIrTask, createRamanTask, getApiErrorMessage, uploadFile } from '../api/specAgentApi'

const props = defineProps({
  spectype: {
    type: String,
    default: 'ir',
  },
})

const router = useRouter()
const submitting = ref(false)
const selectedUploadFile = ref(null)
const uploadedFileId = ref('')
const uploadedFilename = ref('')
const lastTaskId = ref('')

const pageTitle = computed(() => (props.spectype === 'raman' ? 'Raman 任务提交' : 'IR 任务提交'))
const formatHint = computed(() => (props.spectype === 'raman' ? '支持格式：txt/csv（Raman）' : '支持格式：txt/csv（IR）'))

const form = reactive({
  inputMode: 'upload',
  inputPath: '',
  mode: props.spectype === 'raman' ? 'retrieval' : 'greedy_decode',
  k: 3,
  x0: 400,
  x1: 4000,
  transmittance: false,
  device: 'auto',
  priority: 5,
})

/**
 * 处理文件选择（仅缓存，不立即上传）。
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
 *   IR/Raman 输入参数。
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
 * 提交 IR/Raman 任务。
 *
 * Returns:
 *   Promise<void>
 */
async function submitTask() {
  if (form.inputMode === 'path' && !form.inputPath.trim()) {
    ElMessage.warning('请填写谱图文件路径')
    return
  }
  if (form.inputMode === 'upload' && !uploadedFileId.value) {
    if (!selectedUploadFile.value) {
      ElMessage.warning('请先选择谱图文件')
      return
    }
  }
  if (form.x0 >= form.x1) {
    ElMessage.warning('x0 必须小于 x1')
    return
  }
  if (form.inputMode === 'upload' && selectedUploadFile.value) {
    try {
      const data = await uploadFile(selectedUploadFile.value, props.spectype)
      uploadedFileId.value = data.file_id
      uploadedFilename.value = data.file_name
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error))
      return
    }
  }

  const payload = {
    input: buildInput(),
    params: {
      spectype: props.spectype,
      mode: form.mode,
      k: Number(form.k),
      x0: Number(form.x0),
      x1: Number(form.x1),
      transmittance: props.spectype === 'ir' ? Boolean(form.transmittance) : false,
      device: form.device,
    },
    options: {
      priority: Number(form.priority || 5),
      callback_url: null,
    },
  }

  submitting.value = true
  try {
    const data =
      props.spectype === 'raman'
        ? await createRamanTask(payload)
        : await createIrTask(payload)
    lastTaskId.value = data.task_id
    ElMessage.success(`任务创建成功：${data.task_id}`)
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
      <h3 class="panel-title">{{ pageTitle }}</h3>
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
          <el-input v-model="form.inputPath" placeholder="示例：E:/spectrum_files/ir/spectrum/ir_00005.txt" />
        </el-form-item>

        <el-form-item v-else label="上传谱图文件">
          <el-upload :show-file-list="false" :before-upload="handleUpload" accept=".txt,.csv">
            <el-button type="primary" plain>选择文件</el-button>
          </el-upload>
          <el-tag v-if="uploadedFilename" style="margin-left: 10px">{{ uploadedFilename }}</el-tag>
          <div class="upload-help">{{ formatHint }}，提交任务时自动上传</div>
        </el-form-item>

        <el-divider content-position="left">分析参数</el-divider>
        <el-form-item label="分析模式">
          <el-select v-model="form.mode" style="width: 280px">
            <el-option label="greedy_decode" value="greedy_decode" />
            <el-option label="beam_search" value="beam_search" />
            <el-option label="retrieval" value="retrieval" />
            <el-option label="function_groups" value="function_groups" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.mode === 'beam_search' || form.mode === 'retrieval'" label="候选数量 K">
          <el-input-number v-model="form.k" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="分析范围 x0/x1">
          <el-input-number v-model="form.x0" :min="0" />
          <span style="margin: 0 8px">-</span>
          <el-input-number v-model="form.x1" :min="0" />
        </el-form-item>
        <el-form-item label="推理设备">
          <el-radio-group v-model="form.device">
            <el-radio value="auto">auto</el-radio>
            <el-radio value="cpu">cpu</el-radio>
            <el-radio value="cuda">cuda</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="props.spectype === 'ir'" label="透射率转吸光度">
          <el-switch v-model="form.transmittance" />
        </el-form-item>
        <el-form-item label="任务优先级">
          <el-input-number v-model="form.priority" :min="1" :max="10" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submitTask">提交任务</el-button>
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

:deep(.el-form-item__label) {
  white-space: nowrap;
}
</style>
