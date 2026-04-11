<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createGpcTask, createNmrTask, uploadFile } from '../api/specAgentApi'

const submitting = ref(false)
const uploading = ref(false)
const uploadedFileId = ref('')
const uploadedFilename = ref('')

const form = reactive({
  taskKind: 'gpc',
  inputMode: 'path',
  inputPath: '',
  detectMode: 'auto',
  manualStart: null,
  manualEnd: null,
  nucleus: '1H',
})

const isGpc = computed(() => form.taskKind === 'gpc')

/**
 * 处理文件上传动作。
 *
 * Args:
 *   file: 用户选择的文件对象。
 *
 * Returns:
 *   Promise<boolean>
 */
async function handleUpload(file) {
  try {
    uploading.value = true
    const data = await uploadFile(file, form.taskKind)
    uploadedFileId.value = data.file_id
    uploadedFilename.value = data.file_name
    ElMessage.success(`文件上传成功：${data.file_name}`)
  } catch (error) {
    ElMessage.error(error?.message || '文件上传失败')
  } finally {
    uploading.value = false
  }
  return false
}

/**
 * 构建任务输入对象。
 *
 * Returns:
 *   任务输入参数。
 */
function buildInput() {
  if (form.inputMode === 'path') {
    return {
      input_type: isGpc.value ? 'file_path' : 'folder_path',
      input_path: form.inputPath,
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
 * 提交分析任务。
 *
 * Returns:
 *   Promise<void>
 */
async function submitTask() {
  if (form.inputMode === 'path' && !form.inputPath.trim()) {
    ElMessage.warning('请填写本地输入路径')
    return
  }
  if (form.inputMode === 'upload' && !uploadedFileId.value) {
    ElMessage.warning('请先上传文件')
    return
  }

  submitting.value = true
  try {
    if (isGpc.value) {
      const payload = {
        input: buildInput(),
        params: {
          detect_mode: form.detectMode,
          manual_interval:
            form.detectMode === 'manual' && form.manualStart !== null && form.manualEnd !== null
              ? [Number(form.manualStart), Number(form.manualEnd)]
              : null,
          three_color_arw_paths: null,
          calibration_file_path: null,
          comparison_report_pdf_path: null,
        },
        options: { priority: 5, callback_url: null },
      }
      const data = await createGpcTask(payload)
      ElMessage.success(`GPC 任务已创建：${data.task_id}`)
    } else {
      const payload = {
        input: buildInput(),
        params: {
          nucleus: form.nucleus,
          threshold: 0.01,
          min_distance: 0.3,
          min_prominence: 0.01,
          width_multiplier: 1,
          baseline_degree: 3,
          smooth_window: 5,
          detection_range_mode: 'full',
          detection_range_min: null,
          detection_range_max: null,
          ppm_offset: 0,
          integration_method: 'voigt',
          internal_standard_policy: 'auto',
          internal_standard_prefer: ['solvent', 'tms'],
        },
        options: { priority: 5, callback_url: null },
      }
      const data = await createNmrTask(payload)
      ElMessage.success(`NMR 任务已创建：${data.task_id}`)
    }
  } catch (error) {
    ElMessage.error(error?.message || '任务提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h3 class="panel-title">任务提交</h3>
    </div>
    <div class="panel-body">
      <el-form label-width="120px">
        <el-form-item label="分析类型">
          <el-radio-group v-model="form.taskKind">
            <el-radio value="gpc">GPC</el-radio>
            <el-radio value="nmr">NMR</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="输入方式">
          <el-radio-group v-model="form.inputMode">
            <el-radio value="path">服务器路径</el-radio>
            <el-radio value="upload">上传文件</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="form.inputMode === 'path'" label="输入路径">
          <el-input
            v-model="form.inputPath"
            :placeholder="isGpc ? '示例：E:/spectrum_files/gpc/demo.arw' : '示例：E:/spectrum_files/nmr/sample_folder'"
          />
        </el-form-item>

        <el-form-item v-else label="上传文件">
          <el-upload :show-file-list="false" :before-upload="handleUpload" accept=".arw,.txt,.csv,.zip,.json,.pdf">
            <el-button :loading="uploading" type="primary" plain>选择文件并上传</el-button>
          </el-upload>
          <el-tag v-if="uploadedFileId" style="margin-left: 10px">{{ uploadedFilename }}</el-tag>
        </el-form-item>

        <template v-if="isGpc">
          <el-form-item label="峰检测模式">
            <el-radio-group v-model="form.detectMode">
              <el-radio value="auto">自动</el-radio>
              <el-radio value="manual">手动</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="form.detectMode === 'manual'" label="手动区间">
            <el-input-number v-model="form.manualStart" :precision="3" />
            <span style="margin: 0 8px">-</span>
            <el-input-number v-model="form.manualEnd" :precision="3" />
          </el-form-item>
        </template>

        <template v-else>
          <el-form-item label="核类型">
            <el-radio-group v-model="form.nucleus">
              <el-radio value="1H">1H</el-radio>
              <el-radio value="13C">13C</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-alert type="info" :closable="false" show-icon>
            NMR 任务为单阶段模式，首次提交即带完整参数，内标按 solvent -> tms 自动选择。
          </el-alert>
        </template>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submitTask">提交任务</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>
